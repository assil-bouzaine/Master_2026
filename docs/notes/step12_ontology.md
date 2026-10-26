# Step 12: Phase 3, ontology and knowledge graph

**Latest CQ revision (2026-10-24):** see
[step12c_competency_review.md](step12c_competency_review.md). The entries below
record the earlier work and its historical examples; the current requirements
are in [competency_questions.md](../competency_questions.md).

## 12.1 Competency questions (draft, 2026-10-23)

### What was done
- Drafted 13 competency questions in `docs/competency_questions.md` (16 after the revision
  below). Each one has:
  - the parts of the project it feeds: graph, inputs, constraints, explanations,
    validation, framing
  - a priority (MUST / SHOULD / COULD)
  - an example answer computed from dataset v3
- Started from the 10 questions of the critical review (`docs/feedback.md` §7.1) and added
  three:
  - **CQ11**, same-unit neighbours at a similar depth: the one positive signal of the
    knowledge-graph pre-check.
  - **CQ12**, annual abstraction by unit and use: the Pliocene framing.
  - **CQ13**, stacked and nested wells: the anchors for RQ3 and the evidence against a
    head-ordering rule.

### Why
A competency question is a question the ontology must be able to answer. The list is the
ontology's specification and, later, its test suite:
- A class or relation enters the ontology only if a question needs it.
- Each question becomes a SPARQL query in `tests/`, whose answer is compared with one computed
  separately from the parquet tables.

This keeps Phase 3 inside its time-box and gives Gate 3 an objective "done".

### What the example answers already tell us
- **CQ2 is the bottleneck.** Only 240 of the 2,137 groundwater abstraction points carry a
  BSS code; around W1, 4 of 148. Linking pumps to aquifer units needs its own data step
  (rules plus a confidence level).
- **Around Millas (W2), 110 Mm³ of drinking water** was pumped within 5 km over 2012–2023,
  against 17 Mm³ of irrigation. Whether it came from the Têt alluvium or from the Pliocene
  below matters for both layers.
- **Depth matters inside the Pliocene.** W1's three same-unit neighbours, 2.8 km away
  (DEM'TER 1–3), have investigation depths of 15, 60 and 111 m; only one is at a depth
  similar to W1's 97 m.

### Revision after the project review (same day)
The review (`docs/review_2026-10-23.md`) found four errors in the first draft. All are fixed
in `docs/competency_questions.md`:
1. **Depth.** `profondeur_investigation` is the borehole's *investigation* depth, not its
   screen depth (screens are only in the BSS logs).
2. **Depth classes.** Fixed classes were not supported by the pre-check (p = 0.52), while
   the continuous depth difference was (p = 0.002). Depth stays a number.
3. **Restriction orders are not a model input** (CQ9): they would leak the target or are
   used only for the imputation.
4. **GWML2 has no `overlies`.** That relation is ours.

It also added three questions:
- CQ14, confinement
- CQ15, irrigation derived from satellite data (the subject's remote-sensing objective)
- CQ16, the dashboard scenario query

The ontology reuse plan changes too:
- GWML2 has no official OWL; the OWL rendering in SAWGraph's water ontology is used instead.
- SWEET, named in the subject, is added.
- WHOW-KG is kept as the architecture pattern only; it has no water-use module.
- **Two questions lack data:** canal command areas (CQ6) and restriction zones (CQ9). They are
  COULD.

### What to consider
- **Review the list** (add, drop, priorities). Open points:
  - the distance within which a pump can affect a well
  - what counts as a "similar depth"
  - a citable source for the irrigation demand of each crop group
  - a minimum contact area for `overlies` edges
- **Next:** step 2, reuse (find each term in the standard vocabularies, or define it in
  `lulcw:`); then the CQ2 data step.
- Two references, both checked on Crossref:
  - Grüninger & Fox 1995 (doi:10.1007/978-0-387-34847-6_3), the origin of competency
    questions.
  - Wiśniewski et al. 2019 (doi:10.1016/j.websem.2019.100534), how competency questions
    are written as SPARQL.

## 12.2 Reuse table and modelling patterns (started 2026-10-23)

### What was done
`docs/ontology_design.md` holds the plan for the ontology:
- the namespaces, each marked "checked" (seen at its source today) or "to check"
- the classes and properties, each linked to a competency question
- four modelling patterns, each with a small Turtle example:
  - causal `Influence` nodes
  - SOSA observations for annual facts
  - `UnitAttribution` nodes for uncertain pump → unit links
  - the written rule that types the BD LISA units
- the quality gates

### Why
- Nothing is written in Turtle before every term has a source or a definition (CLAUDE.md
  rule 12).
- The patterns settle two needs before the code exists:
  - how a link carries its sign, distance, confidence and evidence
  - how a fact carries its date

### What to consider
Open points, all for step 12.4:
- the namespace (w3id.org needs a pull request from Assil's GitHub account)
- the licence of SAWGraph's OWL rendering of GWML2
- the HY_Features river class
- the HILUCS value IRIs
- units: QUDT or documented datatypes

## 12.3 Pump → aquifer unit: the evidence (started 2026-10-23)

### What was done
- New ingest script, `src/ingest/hubeau_qualite_stations.py`, which downloads the 1,094
  Hub'Eau groundwater-quality stations of dept 66 (logged in `data/README.md`).
- **211 of the 235** BNPE points with a BSS code are among these stations, and each has a
  BD LISA entity code: direct evidence of the unit they pump from.
- BNPE has a second clue: the flag `nappe_accompagnement`, set when the pumped aquifer is
  connected to a river. Checked against the 211 coded points:

  | Unit of the coded point | Flag True | Flag False |
  |---|---|---|
  | alluvium (recent or ancient) | 30 | 8 |
  | Pliocene | 3 | 50 |

### Why it matters
- The review worried that only about 11 % of pumps could be tied to a layer.
- With the flag, most pumps of the plain get at least a "probable" layer: 1,067 flagged
  True, 603 False, 220 empty.
- The accuracy of the flag is *measured* on the 211 coded points, not assumed.
- This is the information every baseline lacked (Gate 2 finding 2).

### What to consider
- The 211 coded points are mostly drinking-water boreholes. The flag may be less reliable
  for irrigation boreholes; say so in the paper.
- The official (Sandre) definition of the flag is still to confirm.
- Next: the attribution table itself (point → unit, method, confidence), which becomes the
  `UnitAttribution` nodes of the KG.

### Correction and result (later on 2026-10-23, after the second review)
The table above counts **Pliocene points that are False** (a recall). A rule needs the
other direction: when the flag is False, how often is the unit the Pliocene?
- On the coded points of the plain, only 53 of 112.
- With the stack (False **and** the Pliocene under the point): 92 % of the recorded
  boreholes.

The attribution table is built (`src/kg/pump_attribution.py`,
`data/interim/pump_unit_attribution.parquet`). Its rules, their measured precision, the
depth check of the records and the coverage by volume and use are in
`docs/notes/step12b_review_fixes.md`. Task 12.3 is done.

## Decisions of 2026-10-23 (the supervisor left the choices to Assil)

`docs/supervisor_questions.md` §1 lists each decision with its reason. For the ontology:
- **Framing.** The Pliocene use conflict is the main story, so the pump → unit links (CQ2)
  and the abstraction per unit and use (CQ12) are MUST. Canal-return recharge (CQ6) stays
  a secondary case study.
- **Main model.** The hybrid gives each causal `Influence` type its own sign-constrained
  response function. The ontology's causal patterns (`docs/ontology_design.md` §4.1) are
  therefore exactly what the model consumes.
- **Scope.** Every objective of the subject gets at least a small, measured version: the
  SWEET/INSPIRE/AGROVOC alignment, the satellite rule (CQ15) and the dashboard queries
  (CQ16).

## 12.4 Ontology module, version 0.1.0 (2026-10-24)

### What was done
- **The `lulcw` bridging module** (`ontology/lulcw.ttl`): 191 terms, each with one English
  and one French label and an English definition.
  - Version 0.1.0 covers the six MUST competency questions (CQ1, CQ2, CQ3, CQ8, CQ11, CQ12)
    and the common answer contract of `docs/competency_questions.md` §2. The SHOULD and
    COULD modules follow the work order of that document.
  - Classes for wells and stations, hydrogeological units (alluvial, multilayer system,
    karst, confining; pairwise disjoint), unit groups, BD LISA polygons and their stack
    layers, abstraction facilities, annual abstraction records (SOSA observations) and
    accounting results.
  - Qualified, evidence-carrying assertions: `UnitAttribution` (role, rule, rank,
    confidence, resolution, status, or an explicit unknown with a reason),
    `StratigraphicRelation` (with the polygons that witness it), `WellLink`, `Influence`
    (mechanism, driver variable, conditions, response sign, constraint eligibility),
    `VolumeAllocation`.
  - Twelve SKOS concept schemes: answer status, evidence kind, assessment status,
    confidence, resolution, role, water use, water source, record kind, response sign,
    mechanism, driver group, constraint eligibility, stratigraphic relation kind.
- **Local copies of the reused terms** (`ontology/imports/`): SOSA, PROV-O, OWL-Time, SKOS
  and GeoSPARQL 1.1, downloaded from their official addresses and cut by ROBOT to the
  terms we use (`src/kg/build_imports.py`); SWEET likewise; GWML2 and HyFO by hand from the
  SAWGraph page. Every term was checked at its source on 2026-10-24.
- **Alignment modules** (`ontology/alignments/`): to GWML2/HyFO (subclass and subproperty
  axioms where they hold for every instance) and to SWEET (close matches only).
- **The meta-ontology** (`ontology/lulcw-meta.ttl`) imports the module and the alignments;
  `ontology/catalog-v001.xml` resolves every import to a local file, for Protégé, ROBOT
  and the tests.
- **Quality gates** (`python -m tests.test_ontology`, 16 s): all modules load offline;
  metadata; labels and definitions; every lulcw IRI declared and every reused term taken
  from a checked local copy; ELK and HermiT find the network consistent; a negative control
  (a unit both alluvial and karst) is rejected; ROBOT's report finds no error.

### Why
- **Qualified assertions instead of plain links.** A link "this pump pumps from the
  Pliocene" would hide that only 27 % of the volume has a direct record. The attribution
  node keeps the rule, its measured precision at its resolution, the alternatives and the
  unknowns, so the model can select links by policy without the graph forgetting how
  certain each one is.
- **Disjoint unit types and a negative control.** A gate that never fails proves nothing.
  The test inserts a contradiction on purpose and checks that the reasoner catches it.
- **MIREOT extracts.** Importing all of PROV-O or OWL-Time would make the network large,
  and HermiT rejects OWL-Time's `xsd:date` ranges. Copying only the declarations, labels
  and hierarchy of the terms we use keeps the reuse traceable and the reasoner working.
- **Names.** `AquiferUnit` (a working name) became `HydrogeologicalUnit`: GWML2's
  `GW_AquiferUnit` covers only aquifer-related units, and BD LISA entities include others.
  `AbstractionPoint` became `AbstractionFacility`: a BNPE code identifies a facility, not a
  borehole (CQ2). Units are written in the property names (`…M`, `…M2`, `…M3`), not with QUDT.

### What to consider
- **Namespace.** The IRIs use `https://w3id.org/lulcw#`, which does not resolve yet. Making
  it resolve needs a pull request to github.com/perma-id/w3id.org from Assil's GitHub
  account, pointing to a public copy of the files (GitHub Pages). It is a public action, so
  it waits for his decision; the IRIs stay valid identifiers meanwhile.
- **OOPS!** (the pitfall scanner) is a web service: the module is sent to it. Run it once
  before Gate 3.
- **Next (12.5):** instantiate the graph from the parquet tables, in the work order of the
  CQ document: wells, stations, units, polygon stacks and stratigraphic relations (CQ1,
  CQ3), well links (CQ11), then pump attributions and annual records (CQ2, CQ12).

## 12.5 The knowledge graph, filled from our tables (2026-10-24)

### What was done
- **`src/kg/build_kg.py`** turns the source tables into the knowledge graph
  (`PFE_DATASET=v4 python -m src.kg.build_kg`, 61 s): `data/processed/kg/lulcw_kg_v4.ttl`,
  205,650 triples (14.5 MB of Turtle), written by rdflib and loaded back by pyoxigraph.
  It covers the six MUST competency questions, in the work order of the CQ document:
  - **Wells (CQ1).** The 65 wells of dataset v4, each with its monitoring station, a
    reference to its weekly head series (variable, datum NGF-IGN69, weekly step, first and
    last week, file and key, quality policy), its WFD groundwater body (9 bodies), its
    position, its BD LISA polygon and the stack under it. One **monitoring attribution** per
    well: the unit recorded in ADES (60 wells; confident when that unit is under the point or
    within 1 km of it, else probable), or an explicit unknown with its reason (5 wells).
  - **Geology (CQ3).** 47 BD LISA units typed by the written rule (1 multilayer system,
    10 alluvial aquifers, 5 karst aquifers, 8 confining units, 23 others), 5 unit groups,
    and 201 elementary polygons (the 180 of the plain box, plus 21 under a well or a pump)
    with their area, outline and 296 stack layers.
  - **Pumps (CQ2).** All 2,187 groundwater abstraction facilities of the BNPE snapshot
    (2026-10-20), each with its intake, position, polygon and Sandre identifier, and the
    pump → unit attributions of task 12.3 with their rule, rank, confidence, resolution,
    evidence and provenance. The rule measurements (precision, sample, use, resolution)
    are stored as 4 rule evaluations.
  - **Volumes (CQ12).** The 12,951 annual declared groundwater volumes (2012–2024) as SOSA
    observations, each with its year, use, and how it was obtained (direct measurement,
    indirect measurement or flat-rate volume).
  - **Provenance.** 6 data releases with their dates, 10 named rules, 2 rule executions
    with their code versions (this build, and the commit that produced the 12.3 table),
    and the 3 export policies (main, confident only, all links).
- **"Right group, wrong layer" is now explicit (the CQ2 contract).** The "connected to a
  river" clue (flag_true) finds the alluvium 95 % of the time, but the exact alluvial unit
  only 63 % of the time (19 recorded boreholes). The 12.3 table had one confidence per
  link. In the graph, each of the 21 drinking-water pumps concerned gets two statements:
  "pumps from the alluvium (recent or ancient): probable" and "pumps from 671AB04, say:
  possible". A filter that asks for exact units can no longer pick up a group-level clue.
  The main runs keep their volume (Assil's decision): the probable link is at group level.
- **Ontology 0.1.1.** One new water use, `EnergyUse` (2 BNPE rows use code ENE), and
  GeoSPARQL's `hasMetricArea` added to the local copies for polygon areas. All gates pass
  (192 terms; ELK and HermiT consistent).
- **`tests/test_kg.py`** (3 s): 8 checks, each against a value computed again from the
  tables with pandas. Among them: the CQ1 cases (W1: 97 m, unit 671AA00; W2: stack 718BP02 >
  671AA00), the volumes per year and use equal the BNPE snapshot (in the plain's facility
  extent: 711.5 Mm³ over 2012–2024), and two negative controls (an undeclared property, an
  exact-unit link upgraded to probable) that the checks must catch.

### Why
- **Facts here, links later.** The links that become the model's graph (layer above layer,
  well to well, pump to well) are not computed by this script. Task 12.6 derives them inside
  the graph with SHACL-AF rules, and task 12.8 compares them with the same links computed by
  pandas. If both came from the same Python code, the comparison would prove nothing.
- **Declared volumes only.** The model uses weekly volumes that were spread and partly
  imputed (2024+, the 2018 break). Those are model inputs and stay in parquet. CQ12 needs
  the declarations as declared, so a total never mixes what was reported with what we
  filled in.
- **Every groundwater facility.** 50 of the 2,187 facilities are not in dataset v4 (their
  declarations are all zero or have no use code: 0.04 Mm³ in total). They are in the graph
  with an explicit "not attributed" reason, so CQ12's denominator is complete.
- **Lambert-93 geometry** (EPSG:2154, metres), the projection of every distance and area of
  the project, so that the 12.6 rules can test a distance.

### What to consider
- **Flat-rate irrigation volumes.** 60 % of the declared groundwater irrigation volume
  (2012–2024) is a flat-rate estimate, not a measurement; drinking water is 98 % measured.
  So irrigation pumping is uncertain twice: in its layer (at best "possible") and in its
  volume. The graph keeps the acquisition mode of every record, for the paper and the
  sensitivity runs.
- **Wells without a known layer:** Saint-Féliu-d'Amont (MAS CONTE), a 332 m borehole at
  Canet, and three shallow wetland piezometers at Formiguères. Two recorded units are not
  under their point: ALENYA (718BP03 recorded, the map says 718BP04 > 671AA00) and CARRIE
  (760AE09, absent from the Occitanie extract); both are "probable".
- **4 facilities** lie outside every polygon of the Occitanie extract.
- **SPARQL syntax:** a prefixed name cannot contain "/", so the queries use
  `BASE <https://w3id.org/lulcw/data/>` and relative IRIs such as `<rule/pump-flag-true>`.
- **Distances in the 12.6 rules:** SPARQL 1.1 has no square root. A rule can still test
  "within r" by comparing squared distances; the distance value needs XPath's `math:sqrt`,
  registered as a custom function in rdflib (pySHACL runs its rules through rdflib).
- **Two statements, one candidate.** The 21 split candidates keep one rank for both their
  exact and their group statement, so 12.6's shape "one main candidate" counts per
  resolution, and the CQ12 accounting must never add the two.
- **Next (12.6):** the SHACL shapes of `docs/ontology_design.md` §5, and the SHACL-AF rules
  for stratigraphic relations and `overlies` (with their witness polygons), same-unit well
  links (CQ11), pump → well influences (CQ8) and the policy selections.

## 12.6 Rules and shape checks inside the graph (2026-10-25)

### Recurring check (CLAUDE.md §7, review of 2026-10-25), answered before starting
1. *Chain link advanced:* water → model. The links the model's graph will be made of (layer
   above layer, well with well, pump to well) and which of them may carry a sign constraint.
2. *Where dated land use enters:* not in this part. The land-use rules (zone-year crop
   observations, crop classes, `HighIrrigationDemandZone`) come next, with the land-use module
   of the ontology; the crop-demand index exists outside the graph (step 12d).
3. *Observed / inferred / assumed / unknown:* stacks are observed (BD LISA); stratigraphic
   relations are inferred by a rule (geology, not hydraulics); well links and influences are
   inferred from candidate attributions plus an assumed reference radius; an explicit unknown
   attribution never becomes a link.
4. *Evidence vs plan:* rules and shapes implemented and tested here; the export to the model
   (12.8) and the use of the signs (Phase 4) remain plans.
5. *Next model experiment:* none directly; 12.8 turns these links into the graphs of arms C–F.
6. *Still missing from the subject:* land use in the graph (next), satellite semantics (12.10),
   explanations of real outputs (CQ10), the scenario (CQ16), the CQ query tests (12.7), the
   export (12.8).

### What was done
- **Rules (`ontology/rules/lulcw-rules.ttl`, SHACL-AF, run by pySHACL in advanced mode through
  `src/kg/apply_rules.py`).** They read the facts of 12.5 and write the links into a separate
  file, `lulcw_kg_v4_rules.ttl` (40,225 derived triples; 65 s including loading the graph):
  - **Layer order (CQ3).** For each of the 201 map polygons, every pair of units of its stack:
    95 direct contacts and 13 orderings with a unit in between, each witnessed
    by its polygon, plus the `overlies` shortcut (28 unit pairs). Pairs are formed
    inside one stack only, so "A on B here, B on C elsewhere" never gives "A above C". The
    direct contacts of the plain's polygons are exactly Step 6b's 26 `overlies` edges, with the
    same polygon counts.
  - **Policy selections (CQ1, CQ2).** Each export policy now states which confidence levels it
    admits (`lulcw:admitsConfidence`), and a rule selects the matching attributions: main
    375, confident only 233, all links 1,763. `lulcw:monitors` (60)
    and `lulcw:pumpsFrom` (294) are the main policy's view, exact units only: the
    group-level clue of 12.5 never becomes a `pumpsFrom` to one unit.
  - **Neighbouring wells (CQ11).** 47 pairs of wells recorded in the same unit within
    5 km (inclusive), each with its distance and, for 42 of them, the difference of
    investigation depths (a missing depth stays missing). Stored once per pair.
  - **Pump → well influences (CQ8).** 1,848 candidate paths (one per pair of attributions)
    from a facility to a well within 5 km through a shared unit: 1,830 at the exact unit,
    with the non-increasing sign of pumping drawdown and "eligible" to constrain a model;
    18 through a unit group only ("the alluvium", from the river flag), with the sign
    left unknown and not eligible. Selected by the main policy: 434 paths (416 of them
    eligible), joining 178 facilities to 43 wells; by the confident-only policy 134; by the
    all-links policy all 1,848, on 1,839 facility–well pairs (1,040 facilities, 54 wells).
  - **A path is selected only if both its ends are**, by every policy.
- **Shapes (`ontology/shapes/lulcw-shapes.ttl`, gate 4 of `docs/ontology_design.md` §5):**
  attributions are either resolved (one target, a confidence, a resolution) or an explicit
  unknown (a reason, nothing else); one main candidate per entity, role and resolution;
  every piezometer and facility has an attribution; every stratigraphic relation is shown by
  its witness polygon's stack, intervening units included; `overlies`, `monitors`, `pumpsFrom`
  are backed by their qualified nodes; well links are unordered pairs without duplicates, with
  depth differences only where both depths exist; an eligible influence has a known sign and
  rests on exact-unit attributions; an unknown attribution never supports a link; a path is
  selected only if its segments are. Result on the real graph (51 s): no violation, no warning,
  and 8 notes for the wells without an investigation depth.
- **Ontology 0.2.0:** `admitsConfidence`, `searchRadiusM`; constraint eligibility reworded
  (below). All quality gates pass (194 terms; ELK and HermiT consistent).
- **`tests/test_kg_rules.py`:** the acceptance cases of the CQ document on a small synthetic
  graph (a 4,999 m pair is linked, a 5,001 m pair is not; a stack A > B > C; two disjoint
  polygons; an exact, a group-level, an unknown and an out-of-range pump), 9 deliberate
  errors that the shapes must report, and pandas oracles on the real graph (relations from the
  BD LISA stack table, well pairs from `wells.parquet`, exact influences from the attribution
  table and the BNPE coordinates, Step 6b's edges, policy counts).

### Why
- **Links derived inside the graph, from facts written by another program.** Task 12.8 will
  compare these links with the same links computed by pandas. Because the two derivations
  share nothing but the source tables, their agreement is a real check (the equivalence test
  of the analysis plan, §10).
- **"Eligible" is decided from the evidence; the policy decides whether it is used.** A sign
  constraint says "more pumping from this facility cannot raise this well's level". It is
  safe where the facility pumps the very unit the well monitors. If the facility is known only
  to pump from "the alluvium", it may pump a neighbouring member of that group, and irrigation
  pumping can even raise a shallow head through return flow; so those paths stay unsigned
  edges. Whether a path is used at all is the policy's choice (main runs: confident and
  probable, Assil's decision of 2026-10-24): a path counts as accepted by a policy only when
  both its attributions are.
- **One influence per evidence path.** A facility with two candidate units (or one candidate
  stated at two resolutions) gives two paths to the same well, each with its own confidence
  (9 facility–well pairs under the all-links policy). Nothing is merged or summed in the
  graph; the export (12.8) must take each facility's volume once per well.
- **Facts and derived links in separate files**, so every query and test states whether it
  reads facts or rule outputs (CQ document §6).
- **Parameters as data.** The 5 km radii and the admitted confidence levels are triples of the
  rule and policy nodes, so an answer can cite them and a sensitivity run changes data, not code.

### What to consider
- **rdflib is slow, so the heavy rules run once over the whole graph.** pySHACL runs a rule
  once per focus node. Run once per well, the pumping rule took 34 s for one well: rdflib
  joined its candidate list with a quadratic loop each time. Run once, with its own rule node
  as focus (which also holds the radius), the whole rule run takes 65 s, loading included. The nested
  NOT EXISTS of the path selection was replaced by a count (over a minute per policy before).
  The validation had two more traps: pySHACL gives rdflib the text of each SPARQL check again
  for every item, and rdflib parses it every time; and rdflib orders a query's patterns before
  it knows the item ($this), so the "one main candidate" check started from all rank-1
  attributions on both sides (87 s for one facility). During the runs, each check text is now
  parsed once and the patterns that mention the item go first (0.05 s); only the work changes,
  and the fixture test gives the same results (52 s → 13 s for the whole test).
  pySHACL also needed two workarounds: the ontology is added to the validated graph by hand
  (its `ont_graph` option copies only the class tree, not the concepts that `sh:class`
  checks), and XPath's `math:sqrt` is registered as an rdflib function.
- **To settle at Gate 3:** may a group-level path of a *drinking-water* facility carry the
  sign? Drinking-water pumping cannot raise a head, connected or not (zero is
  "non-increasing"), so a ≤ 0 constraint is harmless there; for irrigation it is not.
  The current rule keeps every group-level path unsigned.
- **The 5 km radius** is the reference query of the CQ document, not a hydraulic limit. The
  baselines' pumping features use 3 km; the export applies a threshold frozen on the training
  period, which must stay ≤ 5 km unless the rule is re-run with a larger radius.
- **What the shapes found:** nothing to fix. The 8 notes are wells without an investigation
  depth (they stay in the graph and in distance-only policies), and no two units are stacked
  in opposite orders anywhere (the warning shape found none).
- **Next:** the land-use rules (zone-year crop observations from the clipped areas, the crop
  classes with their FAO-56 parameters, a dated `HighIrrigationDemandZone` assessment with a
  threshold frozen on the training years), which need the land-use module of the ontology;
  then 12.7 (CQ queries and fixtures) and 12.8 (export and equivalence test).

## 12.6 (continued) Land use inside the graph (2026-10-25)

### What was done
- **Ontology 0.3.0, the land-use module** (39 terms; all quality gates pass, 233 terms in all):
  RPG crop codes and crop classes as SKOS concepts, the irrigation assumptions (usually,
  partly, rainfed, not cropped), a crop demand zone per well, three kinds of observations
  (clipped crop area per code, crop class area, potential irrigation demand per calendar
  year) and a dated irrigation-demand assessment with its two categories.
- **Facts (`src/kg/landuse.py`, called by `build_kg`; the graph grows to 356,377 triples):**
  198 RPG crop codes with their official label and group (2023 table, else 2024), the 14
  crop classes plus an "unmapped" bucket with their FAO-56 coefficients and stages (each citing
  its Table 11/12 row) and their irrigation assumption (citing the two Agreste 2020 census
  reports), one 3 km zone per well, 13,684 clipped crop areas (zone × RPG edition × code, each
  edition for its own year) and 1,430 calendar-year demand estimates (2015–2025, main and
  wide). Every source is a release with its URL or file and date: the 11 RPG editions, the two
  code tables, FAO-56 (checked page), the two census reports, the class table, the derived
  tables of LU-3 and the commit that produced them.
- **Rules:**
  - *crop class of each code:* overrides first (AGR → citrus, ART → artichoke), then the RPG
    group, else none: 198 of 198 codes get a class (none unmapped);
  - *class areas:* 5,465 zone × year × class sums, each citing the code areas it adds;
  - *high irrigation demand:* a dated category for each zone and year; the threshold is the
    upper tercile of the main estimates of 2015–2019 (training years only), computed by the
    runner from the graph: 597,028 m³ per zone and year. 248 of 715 zone-years
    are "high".
- **Shapes:** a code has at most one class; a cropped class has all its FAO-56 parameters; an
  RPG edition answers only for its own year; a class area equals the sum of the code areas it
  cites, cites all of them and only matching ones; the wide estimate is never below the main
  one; each category agrees with its estimate and the threshold. Result: no violation (the same 8 notes on wells without an investigation depth); but the validation of the larger graph took 26 min (51 s before the land-use facts): to speed up.
- **Tests:** the CQ7 acceptance cases on the fixture (an override beats the group; an unknown
  code stays in the totals as unmapped; the threshold of two training values 1000 and 400 m³ is
  800 m³), 4 more deliberate errors (13 in all), and pandas oracles on the real graph: the
  class of every code equals `code_to_class`, the class areas equal the clipped areas summed by
  pandas, the demand estimates equal the weekly index spread over its days and summed by year
  (a different computation from the builder's), the threshold and the categories follow.

### Why
- **Per-code observations, classes by a rule.** CQ7 asks for the original codes, their mapped
  class and the unmapped area. Keeping the code-level areas and deriving the classes inside the
  graph makes the mapping itself inspectable (the RPG → AGROVOC experiment of 12.9 will add
  its alignments to the same code concepts).
- **Each RPG edition for its own year.** A crop map of 2023 cannot describe 2020. The
  years before 2015 (backfilled with the 2015 edition in the model's index) and the unfinished
  2026 are not stated as observations.
- **Demand stays a potential requirement.** It is computed outside OWL (FAO-56 with SAFRAN)
  and stored as an estimate with its method; the category is dated and relative to a stated
  threshold, never a timeless "irrigated zone".
- **Calendar years, not 53-week years.** The weekly index is labelled by Sundays; summing
  labels would give some years 371 days. The week across 1 January is split by days.

### What to consider
- **The threshold is relative to these 65 zones** (an upper tercile), useful for templated
  explanations (CQ10) and the dashboard (SO5); it is not an agronomic norm.
- **No crop-demand influence yet.** The analysis plan (§14 item 13) wants the pathway from crop
  demand to the head and its sign settled at Gate 3, without counting a withdrawal twice
  (reconstruction 3 already follows the crop calendar).
- **The greedy pattern order.** The first land-use run hung on the evidence rule: the earlier
  "$this first" fix put an unrelated pattern next to it (3,500 class areas × 13,684 code areas).
  The runner now orders patterns greedily (fewest unknown variables, joined to what is bound);
  the fixture results are unchanged.
- **Numbers in the Turtle files keep 7 significant digits.** rdflib writes doubles as
  `5.970276e+05`: areas above 1,000 ha lose digits beyond 0.001 ha, volumes above a million m³
  beyond 1 m³. Far below any precision we use, but the data tests compare with a relative
  tolerance for that reason (and estimates are stored to 0.1 m³).
- **The tercile falls on a data value.** With 325 training zone-years, numpy's linear tercile is
  exactly the 217th value, so one zone-year sits on the threshold and counts as high (≥).
- **Next:** speed up the validation of the larger graph (time each land-use shape, as for the
  links part), then 12.7, the CQ queries with their fixtures (CQ7 can now be answered from the
  graph), and 12.8, the export and the equivalence test.

## 12.6 (fix) and 12.7 (2026-10-26)

### Recurring check (CLAUDE.md §7, review of 2026-10-25), answered before starting
1. *Chain link advanced:* land use → water inside the graph (the crop facts must pass their own
   shapes when read back from the files), and the CQ queries that will answer CQ7 and the
   groundwater questions from the graph (12.7), the step before the model export (12.8).
2. *Where dated land use enters:* the weekly crop-thirst index (dataset side), now tested by
   LU-4: no detectable information on the core wells (step 12d note). In the graph: clipped crop
   areas per zone and RPG edition, class areas, demand estimates and dated categories (12.6). Not
   yet in a model graph (12.8) or an explanation (CQ10).
3. *Observed / inferred / assumed / unknown:* crop codes and clipped areas are observed (RPG);
   classes are inferred by a written mapping; Kc values and irrigation status are assumed (FAO-56,
   2020 census); the parcel → water source link is unknown; the index's predictive contribution
   is now measured (null on the core wells).
4. *Evidence vs plan:* LU-4 done; rules and shapes implemented and tested; the CQ query tests
   (12.7), the export (12.8), the AGROVOC alignment (12.9) and the satellite rule (12.10) remain
   plans.
5. *Next model experiment:* none now. Colab session 2 completes the v4 baselines (no new
   question); the next experiment that answers an open question is Phase 4 (arms A–F), after 12.8.
6. *Still missing from the subject:* satellite semantics (12.10, needs the Earth Engine login),
   the RPG → AGROVOC alignment (12.9), explanations of real outputs (CQ10), the scenario (CQ16),
   the end-to-end land-use example (LU-6).

### 12.6 fix: the 26-minute validation, and numbers that changed on the way to disk
- **Timing first.** Each node shape on the real v4 graph (`use_shapes`, facts + saved rule
  outputs + ontology), then each SPARQL check of the slow one on 10 class areas, as pySHACL runs
  it ($this pre-bound, `fast_sparql`): "a code area of the class in this zone and year is not
  counted" took **0.39 s per class area**, about 36 min for the 5,465 class areas (CPU shared with
  the browser; 26 min alone): the whole cost. The other two class-area checks take 0.006 and
  0.009 s per class area, the crop-area observation shape 30 s in all. The check searched, from
  each class area, every observation of its zone (about 330 of all kinds) and tested each one.
- **The replacement** (`ontology/shapes/lulcw-shapes.ttl`):
  - on each code-area observation, a SHACL Core qualified-value constraint: it is cited
    (`prov:wasDerivedFrom`, inverse path) by exactly one class area. No SPARQL; pySHACL follows
    one inverse link per observation;
  - one query over the whole graph, run once (`CropClassAreaKeyShape`, its focus is the
    class-area rule): no two class areas share a zone, an RPG year and a class;
  - unchanged: each cited code area matches its class area's zone, year and class; the class
    area equals the sum of what it cites.
  Together they say what the old check said, and more: every code area is counted once, by the
  class area of its own zone, year and class, also when that class area is missing (the old
  check could not see a missing class area, nor two copies of one that both counted everything).
- **The numbers were not stored exactly.** Timing on the saved files showed one sampled class
  area failing "differs from the sum of the code areas it cites". rdflib's Turtle writer prints
  an `xsd:double` as `f"{x:e}"`, 7 significant digits, so **2,068 of the 5,465 stored class
  areas** differed from the sum of their stored code areas by more than the shape's 1e-6 ha
  (relative error at most 5e-7). The validation passed only because it ran on the graph in memory:
  the files, the product, would not have passed their own shapes. `build_kg.ExactTurtle` now
  writes each double as the shortest decimal that reads back as the same number, with an exponent
  so that it stays a double (`2786.8495e0`); used by `build_kg` and `apply_rules`. Checked on 2,012
  values, edge cases included (−0.0, infinity, NaN, a subnormal): all read back exactly in rdflib
  and pyoxigraph.
- **Result:** facts rebuilt (356,377 triples, unchanged), rules 121 s (115,192 derived triples),
  **validation 134 s instead of 26 min**, no violation, the same 8 notes; every derived count
  unchanged (5,465 class areas, 248 high-demand zone-years, threshold 597,027.6 m³).
- **Tests** (`tests/test_kg_rules.py`): 3 more deliberate errors (16 in all): a code area that no
  class area counts, one counted by two class areas, two class areas for one zone, year and
  class. On the stored files: each class area equals the sum of the stored code areas it cites
  (1e-6 ha); the data tolerances lose their "7 digits" term (class areas 1e-4 ha, the rounding of
  the code areas; estimates 0.05 m³).

### Why
- **Validate what is published.** A shape that the graph passes in memory but its files fail
  is a check on the wrong object. Exact storage removes the gap; the stored-file sum check keeps
  it closed.
- **Native constraints before SPARQL.** rdflib evaluates SPARQL in Python, with a fixed cost of
  milliseconds per focus node; a SHACL Core path constraint costs a dictionary lookup. A rule
  that ties many nodes together (a key, a completeness check) is cheaper as one query over the
  graph than as one query per node.

### What to consider
- The other per-node SPARQL checks cost 5–10 ms per focus node: about 80 s for the class
  areas, 30 s for the crop-area observations. The parcel-season observations of CQ15 (tens of
  thousands of parcels × seasons) will need the native or whole-graph form from the start.
- The alternative to exact doubles, `xsd:decimal`, would also be exact, but changes the
  datatypes the shapes and queries expect; not needed.

## 12.7 CQ queries, first group: CQ1, CQ3, CQ11 (2026-10-26)

### What was done
- **`tests/cq/`**: one SPARQL file per question or part of one, each with a header (parameters,
  what it reads: asserted facts or rule outputs, no OWL reasoning; the columns and their units):
  CQ1 `cq01_assignments` (unit candidates or unknowns with their sources, investigation depth,
  a screen only from a construction record), `cq01_bodies`, `cq01_stack`, `cq01_series`; CQ3
  `cq03_relations` (one row per relation and witness polygon); CQ11 `cq11_neighbours`. Each
  question has a **status query** (`*_status.rq`): supported, partial, unknown, conflicting or
  not_applicable, with a reason (the common answer contract, CQ document §2), so that an empty
  answer is "none found" only when the search covered the case.
- **`tests/test_cq.py`**, run with pyoxigraph (the store a dashboard would use):
  - fixtures (the graph of `test_kg_rules` plus a well with two recorded candidates, a body and
    a series, a well with an explicit unknown, a local stack), through the same rules and shapes:
    CQ1 supported / partial (missing depth kept) / conflicting (both candidates with sources) /
    unknown (with its reason) / not applicable, no screen from an investigation depth; CQ3 direct
    and indirect relations inside one stack, none across polygons, unknown for a unit in no
    stack; CQ11 4,999 m in, 5,001 m out, a missing depth difference stays missing, policy
    selection, an empty but supported answer, partial beyond the rule's radius;
  - data (v4), against the source tables: CQ1 anchors (NYLS-1 97 m in 671AA00; C2-1 stack
    718BP02 > 671AA00); for all 65 wells the unit, depth, polygon (GeoPandas point in polygon)
    and stack (TABLE_PILE) equal the sources, statuses 53 supported, 7 partial (no depth),
    5 unknown (no recorded unit); CQ3 all 47 units, 216 relation-polygon rows = the stacks,
    4 units in no stack are unknown; CQ11 the 47 pairs and their distances = `wells.parquet`.
  11 s in all.

### Why
- **Parameters through substitution, not string formatting.** pyoxigraph pre-binds variables
  (SEP-0007) but only those of the SELECT list, and a sub-SELECT sees a parameter only if it
  projects it. So every query returns its parameters on each row, which also records them in
  the answer, as the CQ contract asks.
- **A status per question.** "No neighbour" from a well whose unit is unknown, or from a radius
  beyond the one the rule searched, is not an answer: the status query says which case it is.
- **Oracles from the source tables** (dataset, BD LISA GeoPackage), never from the exporter.

### What to consider
- "Conflicting" for a well with two recorded units: the KG cannot tell alternatives from a
  borehole screened in two units; both stay in the answer with their ranks and sources.
- The CQ3 intervening units are returned unordered; their order is in the witness polygon's
  stack (`cq01_stack` for a well, or the polygon's layers).
- **Next:** CQ2 and CQ12 (pump evidence and accounting: resolution-aware candidates, the 100 m³
  facility with two candidates never counted as 200 m³), CQ7 (land use from the graph), CQ8
  (influences and constraint eligibility); then the SHOULD/COULD fixtures (missing-evidence
  behaviour) and CQ10/CQ15 once their inputs exist.
