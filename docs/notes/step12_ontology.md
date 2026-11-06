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
- **Parameters through a VALUES clause** (corrected the same day, with CQ7): the test inserts
  `VALUES (?W ?r …) { (…) }` at the top of the query's WHERE block, standard SPARQL that any
  engine evaluates first. pyoxigraph's own substitutions (SEP-0007), used at first, accept only
  variables of the SELECT list and act as a join after evaluation in 0.5: harmless for plain
  patterns (0.04 s instead of 0.001 s), but a status query then evaluated every well and year,
  and a well-year without data could not keep its "unknown" row. Every query still returns its
  parameters on each row, which records them in the answer, as the CQ contract asks.
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

## 12.7, second group: CQ2 and CQ12 (2026-10-26)

### What was done
- **CQ2** `cq02_candidates` (facilities within ?r whose candidate is the well's unit, or a unit
  group containing it: distance, rank, resolution, confidence, evidence, rule, the use a measured
  confidence applies to, the policy's selection, the facility's alternatives, its declared uses
  and years), `cq02_unresolved` (nearby facilities with only explicit unknowns, with the reason),
  `cq02_status`. Distances need XPath 3.1 `math:sqrt`, which the test registers in pyoxigraph (as
  `apply_rules` does in rdflib).
- **CQ12** `cq12_accounting` (per year, extent and policy: the declared volume of each facility
  goes **once** to its best-ranked attribution that the policy selects, an exact unit before a
  unit group at equal rank, else "unresolved"), `cq12_declared` (the declared total it partitions,
  by use and acquisition mode). Records without a use code count as "UseNotRecorded".
- **Fixtures:** a deep borehole F6 (rank 1 the unit by depth, probable; rank 2 the recorded unit,
  possible) and 2020 declarations for F1–F6. CQ2: exact and group-level candidates keep their
  resolution, F6's alternative is shown, the unknown F3 is reported apart, and the three policies
  change only the selection column. CQ12: **F6's 100 m³ is counted once, never 200**, its
  alternative unit gets nothing, group-level and unresolved volumes stay apart, and for every use
  and policy the parts add up to the declared total; a year without declarations has no row.
- **Data (v4):** CQ2 for every well: 1,830 exact and 18 group-level candidate rows within 5 km =
  the attribution table and the BNPE points (the same numbers as the influences of 12.6, derived
  here without the rules), 1,097 unresolved neighbours = the facilities without a unit. CQ12 for
  every year 2012–2024 and the three policies: declared totals = the BNPE snapshot; allocations =
  a pandas restatement of the attribution table and its rule evaluation (a measured rule is
  probable at a resolution only with enough cases, precision and its use); the parts add up.
  **Main policy, 2012–2024: 61.8 % of the 711.5 Mm³ declared at an exact unit, 72.3 % with the
  unit groups**: the two figures of `docs/pump_coverage.md`, computed separately on the dataset's
  reconstruction.
- **33 s for the whole CQ test** (7 min 23 s before the rewrite below).

### What to consider
- **pyoxigraph join order.** A triple pattern written after a BIND or a UNION forms a separate
  block that pyoxigraph 0.5 evaluates on its own and joins slowly: `cq02_candidates` took 8.3 s
  per well, 0.25 s once written as one block of patterns, with the exact-or-group UNION replaced
  by one property path (`candidateUnit|(candidateGroup/hasMemberUnit)`) and the alternatives and
  uses as plain OPTIONALs aggregated by GROUP BY; `cq02_unresolved` 1.8 s → 0.04 s with a HAVING
  count instead of FILTER NOT EXISTS. Rule for the next queries: all triple patterns first.
- **Best-ranked selected, or rank 1?** In v4 they coincide: the 7 facilities with a second
  candidate (the depth rule) have a probable rank 1. The accounting rule is stated for the case
  where they would not.
- **Scope of CQ12:** declared withdrawals of facilities in the extent, not all abstraction from a
  unit, nor consumption; weighted allocations ("an explicit allocation with weights ≤ 1") are not
  implemented, since no policy asks for one.

## 12.7, third group: CQ7 and CQ8 (2026-10-26)

### What was done
- **CQ7** `cq07_crops` (the RPG codes observed in a well's 3 km zone in one edition: original code,
  label, RPG group, mapped class or "unmapped", irrigation assumption, clipped area, release, and
  SKOS alignments when they exist), `cq07_classes` (class areas, the unmapped area included, with
  the number of codes they add up), `cq07_demand` (main and wide potential demand, m³ per calendar
  year, procedure, the dated category with its threshold and rule), `cq07_status` (unknown when no
  edition of that year exists: an edition answers only its own year; partial while codes are not
  aligned to a shared vocabulary).
- **CQ8** `cq08_influences` (driver, variable, mechanism, proposed sign, driver group, distance,
  resolution, confidence, eligibility and its reason, conditions, the path: both attributions and
  the shared unit or group, and whether the policy accepts it), `cq08_status` (partial for every
  well with a unit: only pumping-drawdown pathways exist so far; rain recharge, canal return and
  river exchange are not yet Influence records, so their absence says nothing).
- **Fixtures:** CQ7 an override before the group (AGR is citrus), the unmapped area kept in the
  total, synthetic alignments (our own namespace, no unverified external IRI) giving "supported",
  2020 unknown, 2016 unknown although a demand estimate exists (no crops observed); CQ8 the exact
  path: non-increasing sign, eligible; the group-level path: no sign; an unaccepted segment (a
  possible attribution) blocks the path under the main policy.
- **Data (v4):** CQ7 for all 65 wells × 11 editions: 13,684 code rows, class areas and demand
  estimates = the clipped-area table, the class table (`code_to_class`) and the weekly index summed
  by calendar year (threshold 597,028 m³); every answer partial (no alignment before 12.9); 2014 and
  2026 unknown. CQ8: all 1,848 influences (rule outputs) = the CQ2 candidates (read from the
  attributions): two derivations, the same paths, signs and eligibility by resolution, the same
  selections and distances.
- **Parameters now bound by VALUES** (see the first group's "Why"), and two more pyoxigraph lessons:
  an EXISTS that joins two subjects took 4 s per evaluation (once per crop code: cq07_status over
  60 s → 0.15 s with OPTIONAL counts), and the patterns-before-BIND rule of the second group.
  Whole test: 2 min 49 s, mostly the 3,575 CQ7 queries.

### What is left of 12.7
- **CQ10** (explanations of real outputs) needs the model results (Phase 4–5); **CQ15** (probable
  irrigation) needs the satellite rule (12.10). Both MUST: their queries and fixtures come with
  their inputs.
- **SHOULD/COULD** (CQ4, 5, 6, 9, 13, 14, 16): fixture contracts for their missing-evidence
  behaviour (an answer "unknown" with its reason, never an empty "supported").
- CQ7's alignment columns fill in with 12.9 (RPG → AGROVOC); the status then turns supported.

## 12.8 design proposal (2026-10-26, before any code; decisions for Assil marked ❓, taken the same evening: see "12.8 decisions" below)

The export turns the graph into the PyG `HeteroData` that arms C–F share (analysis plan §10:
one node inventory, one backbone, only the edge rule changes). Arm C's rules are those of
`src/models/taccari.py`; arm D's come from SPARQL on the KG. What the KG knows today decides
which relations D can take from it:

| Relation (source → piezometer) | Arm C (distance rule, Taccari) | Arm D (knowledge graph) | In the KG today |
|---|---|---|---|
| piezometer ↔ piezometer | 3 nearest, weight exp(−d/σ) | same unit (CQ11 well links) within r, depth difference ≤ a threshold frozen on training | ✅ 47 links ≤ 5 km |
| abstraction → piezometer | 5 km fields within 10 km, exp(−d/5 km) | influences selected by the policy (CQ8), sign-eligible ones flagged | ✅ 434 paths (main) |
| weather cell → piezometer | nearest SAFRAN cell | the well's cell, or outcrop-weighted cells (CQ4) | ❌ CQ4 is SHOULD |
| river gauge → piezometer | 2 nearest gauges | reaches associated with the unit (CQ5) | ❌ CQ5 is SHOULD, evidence incomplete |
| canal → piezometer | plain node → plain wells | supply areas over the unit (CQ6) | ❌ CQ6 is COULD, evidence missing |

**❓ 1. The three relations the KG does not hold yet.** Recommended: in D they keep C's
distance rules, declared as shared non-semantic edges, so D vs C isolates the two relations the
KG actually holds (well ↔ well, pump → well). The alternative, building CQ4–CQ6 first, would
add weeks for links whose evidence is partly missing (CQ5, CQ6), and a D that loses its weather
or river inputs would differ from C by more than edge semantics.

**❓ 2. Abstraction nodes: facilities or 5 km fields.** The KG works per facility (178 in the
main policy's paths, 1,040 in all links); Taccari groups facilities in 5 km cells. The inventory
must be the same in C and D. Recommended: facility nodes in both (C keeps its distance rule on
facilities), because a field mixes facilities that the KG attributes to different units, so D's
semantics would be lost in the aggregation.

**❓ 3. The depth threshold of the well links.** The design says "a |Δ depth| threshold chosen on
the training period". Recommended rule, frozen before any arm runs: the threshold that maximises
the median training-period correlation of weekly head anomalies of linked pairs, among
{10, 20, 50 m, none}; a pair without a depth enters only the "none" variant (CQ11).

**Fixed by the existing decisions (no question):** main runs use the main policy, sensitivities
confident-only and all links (§3); an influence is stored per evidence path, so the export takes
each facility once per well (the best-ranked path, as in CQ12); unattributed pumping enters every
arm as its explicit input (§3); eligibility travels with each edge as a mask, used only by the
constrained variants; the export records the KG release, the policy and the rule versions in the
HeteroData metadata; PyG (`torch_geometric`) is installed and pinned when the export is written.

**The equivalence test** (analysis plan §10, third review): pandas builds the same `HeteroData`
from the source tables only (wells, BD LISA, attribution table, BNPE points, policies), and the
test compares node identity and order, relation directions, edge lists and weights, features and
units, masks, time alignment and eligibility, then a forward pass with fixed weights (tolerance
1e-6). Most of the pandas side exists already as the oracles of `tests/test_kg_rules.py` and
`tests/test_cq.py`.

## 12.9 plan (2026-10-26; nothing downloaded yet)

RPG crop codes → AGROVOC, the main alignment experiment (subject SO1; roadmap 3.9; LU-2):
1. **AGROVOC snapshot.** Recommended: the AGROVOC Core release in N-Triples, downloaded once
   into `data/raw/agrovoc/<release>/` and logged in `data/README.md` (a dated release makes the
   gold set and the matchers reproducible, and OntoAligner needs the target vocabulary as a
   file on Colab). Its size was not yet checked (the FAO release page states none): check it
   before the download and ask Assil. The alternative, the FAO SPARQL endpoint, needs no
   download but answers from a moving release.
2. **Candidates** for the 198 codes: French labels (RPG `LIBELLE_CULTURE`) against AGROVOC French
   and English pref/alt labels, exact then fuzzy, top 5 per code, written to
   `configs/lu_agrovoc_candidates.csv` (code, label, candidate IRI, candidate labels, score).
   Every IRI comes from the snapshot, so none is written unseen (working rule 12).
3. **Gold set:** Assil validates each code: SKOS relation to one concept (exact, close, broad,
   narrow) or none, with a note → `configs/lu_agrovoc_gold.csv`; ambiguous codes ("Autre verger")
   are expected to take broadMatch.
4. **Experiment** on Colab (local open LLM, never a paid API): OntoAligner's fuzzy, retrieval and
   LLM matchers against the gold set: precision, recall, F1 per matcher, with the candidates
   tables kept.
5. **Into the graph:** the validated alignments as `skos:*Match` on the crop-code concepts; CQ7
   then turns from partial to supported where every code is aligned.

## 2026-10-26 evening: Colab session 2 ends, the 12.8 decisions, 12.9 steps 1–3, a label fix

### Recurring check (CLAUDE.md §7, review of 2026-10-25), answered before starting
1. *Chain link advanced:* land use → shared vocabulary (12.9: RPG codes → AGROVOC, the
   subject's alignment objective SO1), and the model's graph (the 12.8 decisions: which
   semantic relations reach the model, and that CQ4–CQ6 come first).
2. *Where dated land use enters:* the weekly crop-thirst index (dataset; LU-4: no detectable
   information on the core wells) and the graph's dated crop areas, classes and demand
   categories (12.6, CQ7). It enters no model graph yet (12.8) and no explanation (CQ10).
3. *Observed / inferred / assumed / unknown:* crop codes and areas observed (RPG); classes
   inferred by a written mapping; Kc and irrigation status assumed (FAO-56, census); the
   code → AGROVOC relations will be **judged** (Assil's gold set), the matchers' relations
   **inferred** and scored against it; parcel → water source unknown.
4. *Evidence vs plan:* done tonight: the AGROVOC snapshot, the candidate table, the gold-set
   template and its checks. Still plans: the gold set itself, the OntoAligner run (Colab),
   the alignments in the graph, CQ4–CQ6, the export.
5. *Next model experiment:* none. `chronos2_ft` completes the v4 baselines (no new
   question). The next experiment that answers an open question is Phase 4, after CQ4–CQ6
   and 12.8.
6. *Still missing from the subject:* satellite semantics (12.10, Earth Engine login),
   explanations of real outputs (CQ10), the scenario (CQ16); the alignment experiment is
   under way.

### Colab session 2 (ended 17:14 UTC)
- Read on Drive (`pfe_colab/results_gpu`): Chronos-2 zero-shot and cross-learning done
  (14:51–15:10 UTC); `chronos2_ft` failed at once (Colab's `datasets` 4.8.5 against the
  pyarrow pin, step note of the afternoon); the Taccari regimes finished: left-out-well
  folds 2–4 (fold 0 and fold 1's first seeds came from session 1), 25 %, 50 % and the refit,
  the last seeds saved at 17:14 UTC, and the assembled left-out-well predictions written.
  The run log on Drive (291 KB) cannot be read to its end in Drive's viewer, which stops at
  256 KiB; the folder listing shows every run complete.
- **No GPU tonight:** the notebook opened at 19:18 UTC on a new runtime without a GPU
  (`nvidia-smi: command not found`, CPU backend), although the runtime type is T4: the free
  GPU quota of the day is used up. The empty CPU runtime was deleted. `chronos2_ft` waits for
  the next GPU session (about 20 min on a T4).
- **Pull:** Assil approved downloading the six new run folders (about 125 MB). Drive zipped
  them, but the file did not reach `~/Downloads` (Chrome may be waiting on a prompt the
  extension cannot see). The local `results/v4` has none of them yet.

### 12.8 decisions (Assil, 2026-10-26; analysis plan §14 item 14)
1. **Weather, river and canal edges of arm D come from the KG: CQ4, CQ5 and CQ6 are built
   before the export.** Not the recommendation (C's distance rules as shared edges); the
   cost was stated (weeks of KG work, partial evidence for CQ5 and CQ6). It fits the D vs C
   contract (same node inventory, only the edge rule changes) if the inventory of weather,
   river and canal nodes is the union of what either rule connects. Consequences: where the
   KG documents no link, D has no edge for that well, so D vs C also differs in which
   exogenous inputs reach each well; the share of wells without each relation is reported
   with every D vs C result. CQ6 has no supply-area polygons yet; its contract says to keep
   it as a documented gap rather than invent coverage, so D's canal relation may stay
   partial.
2. **One node per facility** in every arm (C's 10 km rule applied to facilities).
3. **Depth rule:** the threshold among {10, 20, 50 m, none} with the highest median
   training-period correlation of weekly head anomalies of linked pairs, frozen first.

**Work order that follows** (Phase 3 ends 6 Dec): CQ4 (BD LISA outcrops × SAFRAN cells, no
new data) → CQ5 (river reaches: reach geometry, gauge-to-reach rule, documented exchange) →
CQ6 (search for canal command areas; else the documented gap) → 12.8. Each one as before:
ontology terms, facts or rules, shapes, a CQ query with fixtures and source-table oracles.

### 12.9 steps 1–3 (snapshot, candidates, gold-set tools)
- **Snapshot** (`src/ingest/agrovoc.py`): AGROVOC Core N-Triples of 2026-10-26, 74.4 MB
  (size checked by a HEAD request first; download approved by Assil), md5 = ETag
  `dfcebf9f…`. FAO serves only the newest release at its fixed URL, so the snapshot is kept
  under its date with the VoID file and `release.json`, and never fetched again (`--check`
  compares it with the online release). 42,082 concepts (1 deprecated); labels are SKOS-XL
  only: 42,082 preferred labels in French and in English, 8,527 French and 13,006 English
  alternatives; 42,530 broader links (data log).
- **Candidates** (`src/kg/agrovoc_candidates.py` → `configs/lu_agrovoc_candidates.csv`,
  1,615 rows): the 198 codes of the well zones, up to 8 candidates from the code's label
  (full, head, tail) and 2 from its group label, with the preferred labels and the broader
  concepts. 64 codes have an exact label match, 131 only word overlap, 3 none (CML Cameline,
  PAQ Pâquerette, VER Véronique: AGROVOC names them by their Latin names, e.g. Camelina
  sativa). Three traps found on the largest codes and handled: **homonyms** (RPG "Pêche" is
  the fruit; AGROVOC's French "pêche" is fishing and the fruit is "pêche (fruits)", so a
  qualified label also matches on its base, and equal scores are broken in favour of the
  crop and land branches: concepts under "plants", "Plantae", "plant products", "land
  resources" or "land cover", 6,246 concepts); **negations** ("non" is not a stop word:
  "terre non arable" ≠ "terre arable"); **exclusions** (the tail of "Vigne (sauf vigne
  rouge)" is not matched). PVT now has peaches first, JAC fallow before arable land.
- **Gold set tools** (`src/kg/agrovoc_gold.py`): `template` wrote
  `configs/lu_agrovoc_gold.csv` (198 codes, most area first; 13 codes cover 90 % of the zone
  area, 57 cover 99 %), `search "<words>"` finds concepts by whole words in their French and
  English labels (e.g. "pêcher" → Prunus persica), `check` validates relations, IRIs
  against the snapshot, duplicates and missing codes.
- **A label fix found on the way** (`src/kg/landuse.py`): the 2023 RPG code table is
  Windows-1252, but was read as latin-1, so ’ and … (bytes 0x92, 0x85) became the control
  characters U+0092 and U+0085 in 23 of the 198 crop-code labels of the graph ("Blé dur
  d\u0092hiver"; U+0085 is a line break in Unicode). `src/analysis/rpg_profile.py` already
  read it as cp1252. Now cp1252; graph rebuilt (356,377 triples, unchanged; rules and shapes:
  no violation); `tests/test_kg.py` check 9: no literal of the graph holds a control
  character (a U+0085 probe is caught), and the 2023 and 2024 tables give their 144 shared
  codes the same labels (14 of them differed, as read before).

### What to consider
- **Plant or product?** AGROVOC often has both a crop or plant concept (grapevines;
  Prunus persica, alt. "pêcher") and a product concept (peaches, in "plant products"). A
  parcel code describes what grows on the land, so the plant or crop concept fits better as
  an exact or close match, the product as a related one. Assil decides the rule before
  filling the gold set, and applies it to every code.
- **Gold-set bias.** Candidates come from word matching; a gold set limited to them would
  favour word matchers in step 4. Hence the search command and the rule "search before none".
  A second annotator (the supervisor, on the 57 codes covering 99 % of the area) would give an
  agreement figure; optional.
- **Depth rule, small samples:** the 10 m variant may keep few pairs, and its median
  correlation is then noisy; the number of pairs per variant is reported beside the choice.

## CQ4 design proposal (2026-10-26 evening, before any code; ❓ decided the same evening: (b), local 5 km)

**Inputs checked.** SAFRAN grid points every 80 hm in both directions in Lambert II étendu
(`grid_cells_66.parquet`, 141 points); the SIM2 documentation calls LAMBX/LAMBY "the grid
point's coordinate", so each cell is taken as the 8 km square centred on its point (a stated
assumption of the procedure); the 141 squares cover 9,003 km². BD LISA: a unit is mapped at
outcrop where it is order 1 of an elementary polygon's stack; 638 polygons of 114 units touch
the cells. The whole outcrop of every unit monitored by the wells lies inside the cells
(Pliocene 671AA00 71 polygons, 291.9 km²; Têt alluvium 718BP02 116.5 km²; Corbières karst
681AM00 252.8 km²; the other alluvial units 47–99 km²), so the cells clip none of them;
760AE09 has no polygon (absent from the Occitanie extract).

**What the graph will hold (independent of the choice below):** weather cells (geometry, grid
point, the forcing series they key in `forcing_weekly.parquet`, including drainage below the
root zone `DRAINC` and effective rain `PE`, the recharge-related variables); the outcrop
polygons of the graph's units; one polygon × cell intersection area per pair (GeoPandas,
EPSG:2154, a fact with its procedure); then rules for outcrop area, covered fraction and cell
weights per unit and extent (weights renormalised over the covered area, labelled so), and the
CQ4 query with the contract's fixtures (60/40 ha → 0.6/0.4; 80 of 100 ha covered → 0.8; a unit
without outcrop in S → "no mapped outcrop in S", never zero recharge).

**❓ The extent S of arm D's weather edges** (which outcrop feeds which well). Measured on the
65 wells: 59 have a unit with mapped outcrop (5 have no recorded unit, 1 is in 760AE09).

| | at the well | within 5 km | within 8 km | median distance | cells if unit-wide |
|---|---|---|---|---|---|
| Pliocene (31 wells) | 3 | 26 | 29 | 1.3 km | 23 |
| Corbières karst (7) | 6 | 7 | 7 | 0 | 11 |
| ancient alluvium (3) | 3 | 3 | 3 | 0 | 10 |
| recent alluvium (5) | 3 | 5 | 5 | 0 | 8 |
| other (19; 13 with outcrop) | 10 | 13 | 13 | 0 | 4 |

- (a) *Unit-wide* (S = all cells): every well of a unit gets the same weighted cells (the
  Pliocene's 23): the regional recharge of the unit, with no difference between its wells.
- (b) *Local, 5 km* (S = a disc of 5 km around the well, the radius of the pumping
  influences): the cells weighted by the unit's outcrop inside the disc. 54 of the 59 wells
  get edges, each its own set; 5 Pliocene wells with no Pliocene outcrop within 5 km get none.
- (c) *Local, 8 km* (one cell): 57 of 59.
- Recommended: (b), with (a) as a sensitivity row. It keeps the local variation that C's
  nearest-cell rule has, it takes its radius from a rule already in the graph, and the
  difference from C is then the outcrop semantics, not a change of scale. Leakage from the
  alluvium into the confined Pliocene (the cover of CQ14) is a different pathway and is not
  counted here.

**Decided by Assil (2026-10-26, before any CQ4 code): (b), the local 5 km disc**, with the
unit-wide extent (a) as a sensitivity row. Analysis plan §14 item 14 updated.

### CQ4, increment 1: where it stopped (2026-10-26, 21:10; uncommitted)
- **Done:** ontology 0.4.0 (`WellZone` over the crop and outcrop zones, `WeatherCell`,
  `OutcropSearchZone`, `PolygonCellIntersection`, `OutcropCoverage`, `CellWeight`,
  `SoilDrainage`, `hasForcingSeries`; gates pass); `src/kg/forcing.py`: cells (8 km squares
  densified every 250 m before reprojection, so that neighbours keep their shared edges), the
  forcing extent, 65 search zones, 1,769 polygon-cell intersection areas (pieces under 1 m²
  dropped); the builder adds the outcrop polygons of the graph's units to closure: 176 polygons
  in 2 passes, because the added stacks hold 3 units not met before (657AH00, 681AO00, 699AG04),
  whose own outcrops (8 polygons) needed the second pass. **Correction:** my exploratory check
  had found "no new unit"; it compared integer polygon codes with the stack table's text codes,
  so it matched nothing; the builder's closure and its assertion now settle it. Rules
  (coverage, evidence, weights), shapes (native constraints, per-coverage sums, whole-graph
  keys) and the four CQ4 queries are written; the CQ7 queries now name their zone class.
- **Not done:** the rule run on the new facts (stopped), the CQ4 tests, the commit. The rules
  output on disk predates the CQ4 facts. Resume order: CLAUDE.md §7, "Resume here".

## 2026-10-27: CQ4 increment 1 finished, the Codex review of 2026-10-26 answered

### Recurring check (CLAUDE.md §7), answered before starting
1. *Chain link advanced:* water → model: CQ4 gives the weather cells over each well's unit
   outcrop, the first of the three relations (weather, river, canal) that arm D takes from the
   graph (analysis plan §14 item 14). The review's points also protect the model → explanation
   link (exact support, graph releases).
2. *Where dated land use enters:* unchanged since 2026-10-26: the weekly crop-thirst index
   (LU-4: no detectable improvement on the core wells) and the graph's dated crop areas,
   classes and demand categories (CQ7); no model graph yet.
3. *Observed / inferred / assumed / unknown:* outcrop polygons and cell grid observed (BD LISA,
   SIM2 grid points); the 8 km squares around the points assumed (stated); coverages and
   weights inferred by rules; recharge itself unknown: outcrop is a proxy, weak for the
   Pliocene (below).
4. *Evidence vs plan:* done today: the CQ4 release, its tests and oracle, the release guard,
   exact support, the run inventory, the gold-set protocol. Plans: CQ4 increment 2 (recharge
   influences), CQ5, CQ6, the export, the two-well executable path.
5. *Next model experiment:* none before the export; `chronos2_ft` completes the baselines only.
6. *Still missing from the subject:* satellite semantics (12.10), explanations of real outputs
   (CQ10), the scenario (CQ16); the AGROVOC gold set (Assil) and the OntoAligner run.

### What was done
- **The rules that never finished.** Last night's run of the CQ4 rules was stopped after 25
  minutes; today's ran as long before the laptop shut down. Profiled on the CQ4 part of the
  graph (12,722 triples): the first rule alone took 216 s, the evidence rule crossed 1,769
  pieces with 317 coverages. Cause: rdflib sorts the patterns of a block **again when it
  evaluates it**, by how many of their terms are still unbound (a stable sort). A pattern with a
  constant (`?l lulcw:layerOrder 1`) or a one-variable class test (`?x a
  lulcw:PolygonCellIntersection`) counts as nearly bound and jumps ahead of the patterns that
  should bind its variable first, so every piece met every layer (and every coverage). The
  order set by `fast_sparql` survives only when `$this` binds the first pattern, which is why
  the older rules were fast. Fix: the order becomes a variable tested by a FILTER, the class
  test is dropped where the property's domain implies it. The whole derivation now takes
  about 5 minutes (rules 2 minutes, validation about 2.5–3). Rule for future rules, written in
  the rules file: no constant or lone class pattern ahead of the pattern that binds its subject.
- **Graph releases** (`src/kg/release.py`, Codex §1): `apply_rules` removes the release file
  when it starts and writes `lulcw_kg_v4_release.json` only after a validation without
  violation: the SHA-256 of the facts, rules, shapes, the 11 ontology files and the two
  outputs. Every reader checks it: after today's ontology edit, the tests refused the old
  derivation ("the graph of v4 changed since its derivation (ontology, shapes)") until the
  rules ran again. The CQ4 status query also needs a completed search before it says "no
  mapped outcrop": the facts alone (no rule outputs) now answer unknown for MILLAS C2-1's unit
  718BP02, where Codex had found the false negative.
- **The unit's whole outcrop.** The forcing extent is the union of the 141 cells, so a unit's
  coverage there was 1 by construction. Measured on the whole BD LISA extract: 681AF00 has 15 %
  of its mapped outcrop outside the cells, 681AO00 9 %, the 45 other units none. Each unit now
  records its mapped outcrop (`lulcw:mappedOutcropAreaM2`), the coverage query gives the share
  of it inside S, and the unit-wide answer for those two units is partial ("S clips the unit").
  In a 5 km search zone the share is reported but not turned into partial: the zone clips by
  design.
- **CQ4 tests.** Fixtures (60/40 and 80-of-100 cases, a unit only below order 1, a unit
  outside BD LISA, a clipped unit, the facts without their derivation) and 9 negative controls
  (weights not summing to one, pieces larger than their polygon, a duplicate piece, a sliver,
  a coverage citing another extent, a wrong fraction, an orphan weight, a coverage larger than
  the unit's outcrop, two coverages for one key). Data: the 317 coverages and 1,134 cell
  weights equal a GeoPandas oracle written apart from `src/kg/forcing.py` (overlay of the BD
  LISA polygons with squares rebuilt from the raw grid; areas within 50 m², weights within
  1e-5; first run off by 82 m² because the oracle rounded the well positions to 0.1 m); MILLAS
  C2-1 / 718BP02: 27.08 km², Codex's figure.
- **What the stratigraphy gained.** The 176 outcrop polygons added for CQ4 bring their stacks:
  150 direct contacts and 16 indirect orderings (95 and 13 before), 38 `overlies` pairs (28).
  The plain's 26 contacts of Step 6b are unchanged; the oracle covers all 377 polygons.
- **Exact support** (Codex §2): each scored group stores a digest of its exact weeks; `paired`
  compares them. The 61 v4 tables were rescored; no contrast against the reference had hidden
  different weeks, and LU-4's numbers are unchanged.
- **Reproducibility** (Codex §8): manifests now hash rivers, gauges, pumping points and the raw
  SAFRAN grid; panel caches record their dataset files; `docs/run_inventory_v4.md`: 38 runs
  replayable, 4 recomputable, 18 predictions only (the main LSTM, ST-GNN and Taccari runs of
  Colab session 1 have no checkpoints), EA-LSTM folds 1 of 5.
- **Gold-set protocol** (Codex §6): before the first label; `split` 40 dev / 158 eval, a
  30-code second-annotator subset (78 % of the area), `alternatives`; see
  `src/kg/agrovoc_gold.py`.
- **Checks on the release of 2026-10-27** (facts 373,306 triples, rule outputs 129,479, no
  violation): `test_ontology` (255 terms, ELK and HermiT consistent), `test_kg`, `test_kg_rules`
  (25 negative controls; CQ4 oracle: 317 coverages, mapped outcrop of the 47 units, the forcing
  cells clip 681AF00 and 681AO00), `test_cq` (CQ4 statuses: 315 supported, 2 partial; the
  recorded units of 5 Pliocene wells have no outcrop within 5 km: "no mapped outcrop", the 5
  wells without a weather edge in D; MILLAS 27.08 km²; facts alone: unknown), `test_release`,
  `test_stats`, `test_checkpoint`, `test_run_cache`, `test_land_use_inputs`,
  `test_regime_boundaries`: all pass. The rescoring of the 61 v4 tables added the digests;
  the paired results recomputed afterwards (LU-4: +0.015919 [−0.041644, +0.051254] and
  +0.001311 [−0.045913, +0.163209]) equal those of the step 12d note and of Codex.
- **Two sources read** (Codex §5): the SMNPR page on how the aquifers work and the BRGM report
  RP-71486-FR on canal, river and groundwater exchanges in the Têt valley. Both say the Pliocene
  is fed mainly from elsewhere (the Têt and its alluvium upstream, the Corbières karst, the
  border massifs, leakage from the Quaternary pulled down by Pliocene pumping), not by rain on
  its own outcrop near a well. Analysis plan §14 item 15 lists what the 5 km rule omits.

### What to consider
- **Recharge edges are a proxy.** For the 20 Pliocene core wells, the local-outcrop weather
  edge is the weakest of the three pathways the sources name. CQ4 increment 2 should label its
  influences "recharge proxy" and keep the omitted pathways visible (CQ3 for leakage, CQ5 for
  the Têt, CQ6 for the canals); the domain review of the two LU-6 wells is the check.
- **PE and DRAINC are one water.** In our forcing file, PE = rain − actual evaporation (within
  0.13 %) and ≈ drainage + runoff: a model given both as separate recharge drivers counts the
  drainage twice.
- **The depth rule has almost nothing to choose from:** 0 pairs within 10 m, 2 within 20 m, 13
  within 50 m, 47 without a threshold. The minimum-support proposal (plan §14 item 15) decides
  in practice between 50 m and none.

## 2026-10-27 (continued): CQ4 increment 2, recharge-proxy influences

### Recurring check (CLAUDE.md §7), answered before starting
1. *Chain link advanced:* water → model. The weather inputs of arm D become qualified
   `lulcw:Influence` records (cell → well, through the well's unit and its outcrop), with a sign,
   an eligibility and the pathways they leave out, so that the export (12.8) and the
   explanations (CQ10) read them from the graph instead of from model code.
2. *Where dated land use enters:* unchanged: the weekly crop-thirst index (LU-4: no detectable
   improvement on the core wells) and the graph's dated crop areas, classes and demand
   categories (CQ7). Recharge proxies are climate inputs, not land use; land use reaches no model
   graph until the export.
3. *Observed / inferred / assumed / unknown:* outcrop polygons and the cell grid are observed
   (BD LISA, SIM2 points); coverages, weights and now the influences are inferred by rules; the
   sign (more effective rain on the unit's own outcrop does not lower its head) is an assumption
   of the mechanism, and recharge itself stays unknown: effective rain is a proxy of it, and the
   pathways the sources name for the Pliocene (the Têt and its alluvium upstream, the karst and
   border massifs, leakage from the Quaternary, canals) are not represented.
4. *Evidence vs plan:* CQ4 increment 1 is done and tested; this increment derives the
   influences. Still plans: CQ5, CQ6, the export, the two-well path to a model output.
5. *Next model experiment:* none before the export.
6. *Still missing from the subject:* satellite semantics (12.10), explanations of real outputs
   (CQ10), the scenario (CQ16), the AGROVOC gold set (Assil) and the OntoAligner run.

### Facts checked before writing the rule (release of 2026-10-27, dataset v4)
- The join well attribution → its unit → the coverage of that unit in the well's 5 km search
  zone → cell weights gives **193 cell → well pairs for 54 wells** (each well its own 1–5 cells,
  median 4); none of the 54 coverages is partial (every outcrop piece of a zone lies inside a
  cell). No influence for 6 wells with a unit: the 5 Pliocene wells whose unit has no outcrop
  within 5 km (BAR3, BAR4, TOR3, F3N4, F; a completed search found none: "no mapped outcrop",
  not zero recharge) and CARRIE, whose unit 760AE09 is not in the Occitanie extract (unknown).
  The unit-wide extent (sensitivity) gives 960 pairs for 59 wells.
- The 60 monitoring attributions with a unit: 56 confident, 4 probable.
- **Weekly effective rainfall is negative in 56 % of cell-weeks** (PE = rain − actual
  evaporation exactly, in every cell; minimum −44 mm): a dry week has a negative recharge proxy.
  The sign stated by the influence is about an increase of PE, so it holds for negative values.
- **The cells of one well carry nearly the same weekly PE:** over the 280 pairs of cells that
  share a well (training weeks, to 2019) the correlation has median 0.999, 10th percentile 0.90,
  minimum 0.76 (DRAINC: 0.945, 0.71, 0.47). Their separate contributions cannot be identified,
  so they form one driver group.

### What was done
- **Ontology 0.5.0** (262 terms; ELK and HermiT consistent, ROBOT report without error):
  `GroundwaterRecharge`, an observable property that nothing in the graph measures; `proxyFor`
  (the influence's driver stands in for it); `omitsPathway` with two new mechanisms,
  `LateralInflow` (from neighbouring formations such as the Corbières karst and the border
  massifs, or from the unit beyond the extent) and `VerticalLeakage` (between superposed units,
  e.g. the Quaternary → Pliocene leakage of BRGM/RP-71486-FR), beside `RiverExchange` and
  `CanalReturnFlow`; the driver group `RechargeProxies`; `appliesInExtent` (a rule's fixed
  extents); `EffectiveRainfall` now says what PE is (rain minus actual evapotranspiration,
  negative in dry weeks).
- **The rule** (order 61, after the coverages): one `lulcw:Influence` per weather cell and well
  attribution, where the cell holds outcrop of the exact unit the well is attributed to, in the
  well's 5 km search zone (`influence/recharge/local/<cell>/to/<well>/<rank>`) or in the forcing
  extent (`…/unit-wide/…`, the sensitivity). Driver: the cell's weekly effective rainfall,
  `proxyFor` groundwater recharge; mechanism diffuse recharge; sign non-decreasing; eligible,
  with the reason stating that its use as a constraint and the choice of proxy are settled at
  Gate 3; the four omitted pathways; the cell's share and the covered fraction in the
  conditions (unit-wide: the share of the unit's outcrop the extent holds, when it clips it). It
  cites the well's attribution, the coverage and the cell weight, so a policy selects it exactly
  when it selects the attribution. The path selection moved from order 40 to 90 (last), so that
  it also sees these paths; its results for the older paths are unchanged.
- **Shapes:** a recharge proxy must state what it stands in for, its extent and its omitted
  pathways; its driver is effective rainfall or soil drainage; its path must join the cell to the
  well (the well's attribution, that unit's coverage in the influence's extent, the cell's weight
  in it); its extent is the well's own search zone or a fixed extent of its rule; whole-graph
  checks: no two proxies of one cell on one attribution in one extent (effective rainfall and soil
  drainage would count one surplus twice), and every cell weight of a well's unit in its zone (or
  the unit-wide extent) has its influence, so a missing derivation is a violation, never a silent
  "no recharge pathway". The pumping-only checks now say so (mechanism filter); the exact-unit
  check covers both mechanisms.
- **Queries:** `cq08_influences` returns both mechanisms (driver code = BNPE code or SAFRAN cell,
  proxy, extent, cell weight, omitted pathways); `cq08_status` adds `recharge` = derived /
  none_found (a completed search: the zone holds BD LISA pieces, the unit is described, none of
  it at outcrop) / unknown.
- **Tests:** fixtures W7 (unit X at outcrop in its zone, 0.8 inside the cells: 0.625 / 0.375) and
  W8 (no outcrop of Y in its zone: none locally, one unit-wide cell; probable, so not selected by
  confident-only); W1's zone holds outcrop of other units only and gets nothing; 7 new negative
  controls (32 in all); data checks against the GeoPandas oracle (`test_kg_rules`) and against
  CQ4's own answers for every well (`test_cq`).
- **`src/analysis/lu6_example.py`** reports pumping and recharge proxies apart (a new section 4
  per well), and its list of gaps no longer counts rain recharge among the missing pathways. The
  two wells: MILLAS C2-1 gets 5 cells over the 27.08 km² of 718BP02 within 5 km (23 % of the
  unit's mapped outcrop; shares 0.77, 0.13, 0.09, 0.02, <0.01), PONTEILLA NYLS-1 5 cells over
  59.00 km² of 671AA00 (20 %; 0.67, 0.20, 0.11, 0.03, <0.01); unit-wide, 10 and 23 cells.
- **Release of 2026-10-27 (evening):** facts 373,306 triples (unchanged), rule outputs 160,669
  (+31,190: the recharge proxies and their selections), no violation (the 8 infos of the wells
  without an investigation depth), rules 140 s, total 5 min 20 s. Pumping influences unchanged
  (1,848; main policy 434, confident-only 134). Recharge proxies: **193 in the search zones for
  54 wells** (52 distinct cells; confident-only selects 188: the 5 cells of the 3 wells whose unit is
  probable drop) and
  **960 unit-wide for 59 wells** (79 cells; confident-only 946). 172 of the 1,153 have a share
  under 0.0005 (12 of them local): slivers where a cell barely touches the outcrop, together at
  most 0.13 % of any well's weights; the graph keeps them (they are geometry), and their
  conditions say "a share under 0.001" (the first run printed "0.0"; fixed before this release).

- **Two slow queries, found by the test time** (13.7 min for `test_cq`, against 5.5 after the
  fix). `cq08_status` grouped its rows by its flags, so its six EXISTS tests ran once per
  influence row (10 s for a Pliocene well): the mechanisms are now aggregated in a sub-select and
  the flags evaluated once (0.09 s). `cq08_influences` took 0.44 s a well because pyoxigraph 0.5
  evaluates the inside of an OPTIONAL on its own, in the written order, before joining it: the
  recharge block began with `prov:wasDerivedFrom`, whose self-join meets the thousands of
  observations the crop-class areas cite; each block now starts from its most selective pattern
  (the cell weights, the attributions): 0.07 s, the same rows.
- **Checks, release of 2026-10-27 evening:** `test_ontology` (262 terms), `test_kg_rules` (32
  negative controls; sections 4–6 on the data, the recharge proxies = the GeoPandas oracle;
  1 min 39 s), `test_cq` (CQ8 fixtures and data: every well's proxies = CQ4's cells and weights;
  statuses derived 54, none_found 5, unknown 1, no unit 5; 5 min 35 s), `test_kg`, `test_release`:
  all pass.

### What to consider
- **The sign is eligible, not applied.** Assil settles at Gate 3 whether recharge signs constrain
  the model and with which proxy (PE main, DRAINC as a replacing sensitivity). Until then the
  export carries the edges and their sign mask, and no constrained variant uses them.
- **PE is negative in 56 % of the weeks.** A response linear in PE lowers the head in dry weeks
  as Pastas' recharge does (rain minus a share of evaporation); a clipped proxy, max(PE, 0), would
  be a different proxy with its own sign statement. A Gate 3 point with the proxy choice.
- **Sliver cells.** Whether the export drops cells with a share under 0.001 must be fixed before
  any arm runs: it changes D's edge count (sparsity, compared in E and F), not its weighted inputs.
- **What D gets and does not get.** 54 of the 60 wells with a unit have local weather edges; the 5
  Pliocene wells without Pliocene outcrop within 5 km and CARRIE have none in the main runs (the
  per-well inventory of 12.8 reports it), while C gives every well its nearest cell.
- **Still partial:** river exchange (CQ5) and canal return flow (CQ6) are not influences yet; for
  the Pliocene they, and the leakage the sources describe, matter more than local rain.

## 2026-11-06: CQ5 and CQ6, sources and design proposal (before any CQ5 code; ❓ for Assil)

### Recurring check (CLAUDE.md §7), answered before starting
1. *Chain link advanced:* water → model (the river and canal relations of arm D, the last two
   that analysis plan §14 item 14 takes from the graph), and land use → water through CQ6: canal
   irrigation → return flow to the alluvium, the agricultural pathway the data can carry (review
   response of 2026-10-25, §2 item 2).
2. *Where dated land use enters:* unchanged: the weekly crop-thirst index (LU-4: no detectable
   improvement on the core wells) and the graph's dated crop areas, classes and demand categories
   (CQ7). CQ6 would tie canal irrigation to the alluvium, but without command-area maps no parcel
   can be tied to a canal, so dated land use still reaches no model graph.
3. *Observed / inferred / assumed / unknown:* observed: reach geometry (BD TOPO), the official
   river water-body sections (Sandre), the gauge records (Hub'Eau), the units under each reach (BD
   LISA stacks); documented (literature, with page): low-flow exchange qualifications per water
   body (groundwater-body sheets, 2021) and the Têt gauging campaign of 11–13 September 2017
   (BRGM); inferred: reach–unit associations (geometry) and gauge representativeness; assumed: a
   gauge's discharge stands in for the river stage near a well; unknown: exchange outside the
   documented sections and periods, canal command areas, which parcels a canal serves.
4. *Evidence vs plan:* done today: the BD TOPO snapshot, the bounded source search below and the
   measurements. Everything under "Proposal" is a plan.
5. *Next model experiment:* none before the export (12.8).
6. *Still missing from the subject:* satellite semantics (12.10, Earth Engine login),
   explanations of real outputs (CQ10), the scenario (CQ16), the AGROVOC gold set (Assil) and
   OntoAligner; CQ6's command areas (a data gap: request to DDTM 66 or the Chambre
   d'agriculture).

### Sources found (bounded search, 2026-11-06)
- **BD TOPO V3 hydrography** (IGN Géoplateforme WFS; `src/ingest/bdtopo_hydro.py`, snapshot
  2026-11-06): 48,346 reaches and 3,269 watercourses in DEPT_BBOX. Each reach carries the BD Carthage
  code of its watercourse, the code Hub'Eau gives a gauge's river (`code_cours_eau`): the 21
  gauged rivers of dataset v4 are all found, so a gauge meets its reaches by code, never by name.
  2,546 reaches are canals (`nature` = Canal), with names (e.g. "Canal de Perpignan"): CQ6's
  conveyance lines.
- **Official river water bodies** (Sandre WFS `MasseDEau_VRAP2022`, layer
  `MasseDEauRiviere_VRAP2022_FXX`, 193 lines in the box): the sections the sheets below qualify,
  e.g. FRDR224 "La Têt du barrage de Vinca à la Comelade"; all 13 sections the sheets name exist.
- **Groundwater-body characterisation sheets** (Agence de l'eau Rhône-Méditerranée-Corse, SIERM,
  "état des connaissances 2021"), each relation stated "at the scale of the surface water body, at
  low flow":
  - FRDG351 "Alluvions quaternaires du Roussillon" (it lists its BD LISA V3 units: 671AB01–04,
    718BP01–04): Têt Vinça → Comelade *pérenne perdant* (the river loses to the aquifer),
    Comelade → sea *pérenne drainant* (it drains it); Agly Verdouble → Roboul *en équilibre*,
    Roboul → sea *pérenne drainant*; Canterrane and Réart *temporaire drainant*; Tech Lamanère →
    Molas and Molas → Tanyari *en équilibre*, Tanyari → sea *pérenne drainant*; Massane,
    Riberette and the Bolès below Bouleternère: no information. Comments refine the Agly, Réart
    and Tech by town (e.g. the Tech "in equilibrium as far as Elne, then draining").
  - FRDG243 "Multicouche pliocène du Roussillon": Canterrane/Réart upstream *indépendant de la
    nappe*; "the rivers are connected with the Quaternary aquifers overlying the Pliocene".
- **BRGM/RP-71486-FR** (Ladouche & Caballero 2022; Têt between Rodès and Perpignan, differential
  gauging and geochemistry of 11–13 September 2017, sampling points in Lambert-93): the river
  drains the recent alluvium between Rodès (Têt-A) and T6 (Têt-D) (p. 25); groundwater adds about
  +0.4 m³/s per reach down to Le Soler (Têt-I) (Tableau 2, p. 26), +2.1 m³/s from Rodès to Perpignan
  with the unmeasured canal returns (p. 29); from Le Soler to Perpignan a loss of −0.15 m³/s, and
  "the exchange could reverse in this sector, the Têt feeding the Quaternary" (pp. 30, 32); the
  upper Boulès infiltrates entirely in summer (about 20 l/s) into the recent alluvium (p. 14), its
  lower course drains the Quaternary (p. 24); canal losses 1.7 (right bank) and 1.2 m³/s (left)
  into the recent alluvium, 1.9 m³/s into the ancient alluvium (right bank) (p. 29). The report
  calls the recent alluvium 750PP02, a code absent from BD LISA V3 (genealogy table checked): it is
  mapped to 718BP02 "Alluvions récentes de la Têt" by its name, and the mapping is stated.
- **SMNPR**, "Présentation des nappes" (read 2026-10-27): the Têt and its Quaternary aquifer
  infiltrate into the Pliocene upstream, between Bouleternère and Saint-Féliu-d'Amont.
- **Canal command areas: none found** (data.gouv.fr, the préfecture 66 site, the Géoplateforme
  WFS, Sandre). ASA perimeters exist as prefectural orders with map annexes (PDF); data.gouv.fr has
  a test dataset for the ASA of the Castellane (Conflent, upstream), not the plain.
- **The sources disagree on the Têt above the Comelade:** FRDG351 says "losing" (from the EVP Têt,
  BRLi 2011: losses of about 0.5 m³/s over the year, 2 m³/s at low flow), BRGM's September 2017
  campaign measured gains. The case of CQ5's acceptance rule ("two documented opposing directions
  are preserved, not collapsed") occurs in the real data; both are kept, each with its period.

### Measured (dataset v4, 65 wells, 5 km search zones)
- 59 wells have a gauged watercourse within 5 km. For the alluvial wells the river runs on the
  outcrop of their own unit (MILLAS C2-1: 12.0 km of the Têt on 718BP02); for most Pliocene wells it
  runs over the alluvium that covers the Pliocene (MILLAS C2-2: the same 12.0 km over 718BP02); a
  few Pliocene wells have river reaches on Pliocene outcrop (TERRATS: 7.5 km of the Réart). The two
  ancient-alluvium core wells: the Têt is within 5 km but runs on the recent alluvium beside the
  terrace, so the stack rule finds no association; BRGM documents a lateral contribution of the
  ancient alluvium to the Têt below the Corneilla intake.
- Wells that would get a river edge in D (C gives every well its 2 nearest of 5 gauges):

  | gauge pool | association in the 5 km zone | wells (core) |
  |---|---|---|
  | C's 5 full-record gauges (Têt ×2, Agly, Tech ×2) | river on the unit's outcrop | 14 (6) |
  | C's 5 | on the outcrop, or over the unit's cover | 32 (22) |
  | any gauge with ≥ 2/3 of training weeks observed | on the outcrop | 26 (9) |
  | any gauge with ≥ 2/3 | on the outcrop, or over the cover | 49 (26) |

### Proposal
- **Facts** (new `src/kg/rivers.py`, called by `build_kg`): watercourses (BD Carthage code), the
  reaches of gauged watercourses inside the 65 search zones, the official water-body sections
  named by the sheets, the gauges (code, position, river, local-influence class, weekly series
  reference, training coverage), the length of each reach inside each elementary polygon and zone
  (computed in Python, as CQ4's polygon × cell pieces), and the documented statements as
  `lulcw:ExchangeAssertion` records from a curated table (`configs/river_exchange_evidence.csv`:
  source, page, short quote, section, unit, direction, period or state, quantity, hedging).
- **Rules:** a river–unit association per well zone: *on outcrop* (the unit is order 1 under the
  reach), *over cover* (the unit lies under other units, which are listed), or *documented
  lateral* (a source names the unit for a section with reaches in the zone); the statements that
  apply to each association; the candidate gauges with their representativeness; then the river →
  well influences (CQ8).
- **The sign (for Gate 3).** Where river and aquifer are connected, the exchange flux grows with the
  river stage in both directions (q = C (h_river − h_aquifer), the MODFLOW river package: Harbaugh
  2005, doi:10.3133/tm6A16), so the head response to stage is non-decreasing whether the river
  gains or loses. The documented direction is a *state*, recorded with its period; it does not set
  the sign. Proposed: sign-eligible only *on outcrop* or *documented lateral* with a documented
  exchange other than "independent"; *over cover* edges carry no eligible sign (leakage through the
  cover, FRDG243). A gauge's discharge stands for stage near the well only up to the diversions in
  between, so its use as a constraint is settled at Gate 3, as for the recharge proxies.
- **CQ6, bounded:** command areas stay a documented gap (with the data request); facts: canal
  lines (BD TOPO), canal intakes (BNPE, surface water), the documented canal losses and return flows
  (BRGM, FRDG351); answers stay partial, never a local recharge amount.
- **Questions for Assil** (❓ 1 gauge pool, ❓ 2 association types giving D edges, ❓ 3 canal edges):
  asked on 2026-11-06; answers below.

### Decisions (Assil, 2026-11-06, before any CQ5 code; all four as recommended)
1. **Gauge pool of D's river edges: C's 5 full-record gauges** (Têt at Rodès and Perpignan, Agly
   at Estagel, Tech at Le Boulou and Argelès). D and C differ only in which gauge connects to which
   well; wells whose associated river has no pool gauge (the Réart) get no river edge in D, and the
   gap is reported. CQ5 itself still answers for every gauge of dataset v4.
2. **Associations that give D a river edge: on outcrop, over cover, and documented lateral.** An
   *over cover* edge is labelled "via overlying units" and never carries an eligible sign.
   Measured with the pool: 32 wells (22 core) before the documented lateral links.
3. **Canal edges of D: C's plain canal node connects to a well** whose unit has a BD TOPO canal
   crossing its outcrop within 5 km **and** a documented canal-return pathway (FRDG351, BRGM); the
   sign "canal return raises the alluvium head" eligible there, its use settled at Gate 3. Command
   areas stay a documented gap.
4. **The per-regime depth threshold of the well links is confirmed as proposed** (analysis plan
   §14 item 15): eligible thresholds keep ≥ 10 linked pairs with ≥ 104 shared training weeks; ties
   (medians within 0.02) go to the looser threshold; chosen inside each regime's allowed heads.

## 2026-11-06 (continued): CQ5 and CQ6 built: facts, rules, shapes, queries, tests

### Recurring check (CLAUDE.md §7)
Unchanged from the morning's check above (same task): the chain link is water → model (the river
and canal relations of arm D); dated land use still reaches no model graph (no command areas tie a
parcel to a canal); no model experiment before the export.

### What was done
- **Facts** (`src/kg/rivers.py`, called by `src.kg.build_kg`; facts 469,337 triples, +96,031):
  22 watercourses (the dataset's gauged rivers and those the statements name, by BD Carthage code),
  each with its main stem (the longest path of its BD TOPO flow network); the 2,755 reaches that meet
  the 65 reach search zones (1,004 river, 1,751 canal); 8,999 pieces = reach ∩ 5 km zone ∩ elementary
  polygon (14 off the geological map, pieces under 1 m dropped), whose 69 polygons join the graph's;
  the 13 WFD river water bodies the sheets name (Sandre, 2022 reporting) and 5 stretches between
  points located by BRGM, projected on the main stems; the 45 gauges of the dataset with their weekly
  discharge series and observed training weeks, arm C's pool (5) and 390 gauge-zone relations
  (distance to the zone's pieces of the gauge's river, position along its main stem); 4 documents, 32
  passages and exchange statements (`configs/exchange_evidence.csv`, every quote found on its printed
  page by `tests/test_exchange_evidence.py`); the plain's 181 surface intakes behind the canal input
  (126 with a candidate watercourse within 500 m), in one intake group with its weekly series.
- **Ontology 0.6.1** (367 terms; ELK and HermiT consistent, ROBOT without error): the driver group
  `RiverDischargeGroup` ("river stage proxies"); `measuredAt`, the site of the measurement behind a
  statement; `SurfaceWaterIntake` is a `geo:Feature`, no longer an `AbstractionFacility` (the CQ2
  facilities carry unit attributions, the intakes do not); `SummerDemand` includes the canal
  diversion volumes. ROBOT caught a duplicate English label: the group was first called "river
  discharge", as the observable property.
- **Rules** (orders 62-64, after the recharge proxies; the policy selection stays last, at 90): for
  each reach search zone and unit attributed to its well, a river-unit association **on outcrop**
  (41), **over cover** with the covering units listed (54) or **documented lateral** (4: a statement
  about the unit and a section with reach pieces in the zone, where the river runs neither on nor
  over it); 69 statement applications (a river statement applies when it is about the unit and a
  section holding a piece of the association's watercourse in the zone; a canal statement, by its
  unit); **43 river influences** from the pool gauge on the associated watercourse nearest to the
  zone's pieces: 8 non-decreasing and eligible, 10 non-decreasing but ineligible (geometric only, or
  independence stated), 25 over cover with an unknown sign, never eligible; 42 canal-unit
  associations and **5 canal influences** of the intake group where a source documents a return into
  the unit (2 eligible: stated; 3 hedged). Each influence states its driver (`proxyFor RiverStage`
  for discharge), conditions (gauge distance and position, training coverage, canal length on the
  outcrop) and the reason for its eligibility.
- **Shapes**: the facts (watercourses, reaches, pieces, sections, gauges, pool, gauge-zone relations,
  documents, passages, statements, intakes) and the derived records, and whole-graph completeness:
  every association and influence that the facts call for exists, so a missing derivation is a
  violation, never a silent "no river pathway". 47 negative controls in all.
- **Queries** (`tests/cq/`): `cq05_associations`, `cq05_statements`, `cq05_gauges`, `cq05_status`,
  `cq06_chain`, `cq06_status`; `cq08_influences` and `cq08_status` cover the river and canal
  influences (`river`: derived, no_pool_gauge, none_found, unknown; `canal`: derived, not_documented,
  none_found, unknown; each with its reason).
- **Tests**: `test_kg_rules` (fixture wells R1-R6; the associations, canal lengths and gauge choice =
  the GeoPandas oracle on BD TOPO × 5 km discs × BD LISA, independent of `src/kg/rivers.py`);
  `test_cq` (CQ5, CQ6 and CQ8 fixtures: documented, geometric, conflicting, not searched, incomplete
  search, stale or missing rule outputs; data checks for every well, section 17).

### Fixed on the way
- **Scope and staleness.** The rules associate rivers with the units attributed to a zone's well
  only, so the status queries now answer unknown with "not searched" for another unit, instead of
  "rule outputs missing or stale"; `cq08_status` checks its river and canal answers against the facts
  (pieces on or over the unit, a documented exchange in a section of the zone, an association with a
  pool gauge or a return statement, each without the record the rules derive from it): a facts-only
  graph answered none_found before. `cq05_statements` also lists a statement about a section of the
  zone that no association applies; a documented independence makes an association supported, not
  "geometric only".
- **pyoxigraph 0.5 and EXISTS (measured).** An EXISTS evaluates each of its triple patterns in full
  and hash-joins them: two patterns over the reach pieces cost 0.25 s even with the zone written as a
  constant, while the same patterns as a query, or as a sub-select that starts from the parameters,
  run on index lookups (3 ms). The first versions took **43 s** (`cq08_status`) and **21 s**
  (`cq05_statements`) a well, and the 9,000 new `withinExtent` triples slowed the older recharge
  checks of `cq08_status` (0.37 s). The heavy tests are now sub-selects marked `#bind-parameters`,
  where `src.kg.cq.bind` writes the parameters' VALUES clause as it does at the top of the query (in
  any other engine the mark is a comment: same answers, slower). Now 0.01-0.2 s a well.

### Results (release of 2026-11-06, dataset v4, main policy)
- **D's river edges: 35 wells (24 core)**, the 32 (22 core) measured before the decisions plus the
  three ancient-alluvium wells linked by a documented lateral exchange (HIPPO2 and the two PZ at
  10962X, BRGM/RP-71486-FR). An eligible sign for **7 wells (5 core)**: the recent alluvium on the
  outcrop of its unit, the ancient alluvium by documented lateral exchange. Over cover only: 18 wells
  (16 core, mostly Pliocene): an edge without an eligible sign. Gauges used: the Agly at Estagel (18
  influences), the Têt at Rodès (8) and at Perpignan (8), the Tech at Argelès (5) and at Le Boulou (1).
  Confident-only selects 41 of the 43.
- **No pool gauge: 17 wells (4 core: NYLS-1, FE1, ALENYA, MEDALU)**, associated with rivers that C's
  gauges do not measure (the Réart, the Canterrane, the coastal streams): no river edge in D, the gap
  reported with every D vs C result (analysis plan §14 item 16). None found: 7 wells (4 core: F2 and
  three Corbières karst wells).
- **Canal edges: 5 wells (4 core), 2 eligible** (C2-1 and 10915X0395/PZ: stated returns into the
  recent alluvium); 37 wells have canals on their unit's outcrop within 5 km but no documented return
  into it, so no edge.
- **`cq05_status` for the recorded units:** conflicting 4 (the Têt above the Comelade: FRDG351 calls
  the Vinça-Comelade stretch losing, BRGM measured gains in September 2017; C2-1, 10915X0395/PZ and
  the two PZ at 10962X), supported 16, partial 39 (geometric only), unknown 1 (CARRIE, unit outside BD
  LISA). `cq06_status`: partial 42, supported 17, unknown 1.
- **Anchors** (`test_cq`): MILLAS C2-1, 12.0 km of the Têt on 718BP02, conflicting, an eligible edge
  from Rodès and an eligible canal edge; MILLAS C2-2, the same 12.0 km over the alluvium covering the
  Pliocene, an edge with an unknown sign; MEDALU at Terrats, 7.5 km of the Réart on Pliocene outcrop,
  independence stated by FRDG243, no pool gauge.
- **Release of 2026-11-06** (09:32 UTC): facts 469,337 triples, rule outputs 162,997, no violation (the
  8 infos of the wells without an investigation depth); rules 211 s, total 488 s (with the CQ
  fixture tests running alongside).

### What to consider
- **A conflicting direction does not block a sign.** By design the sign is about the stage (the flux
  grows with the river stage whatever its direction), so C2-1's edge is eligible while its statements
  disagree on the direction. A reviewer may ask for the conflict to block it; a Gate 3 point with the
  use of the river signs.
- **Over-cover edges** reach 16 core wells, mostly Pliocene, through the overlying alluvium: they can
  carry information in the graph, never a sign in the constrained responses.
- **Statements that apply nowhere.** SMNPR's "the Têt and its Quaternary aquifer infiltrate into the
  Pliocene between Bouleternère and Saint-Féliu-d'Amont" and BRGM's two Boulès statements (upper
  course infiltrating, lower course draining) delimit no located stretch, so they are listed for the
  zones of their river and never applied. Locating their end points would make C2-2's association
  documented; over cover its sign would still stay unknown (decision of 2026-11-06).
- **CQ6 stays partial by design**: no command area, no local return amount; the 37 not_documented
  wells may be served by canals whose returns no source names.
- **The `#bind-parameters` mark** is a new query convention: a sub-select that starts from the
  parameters must carry it (the docstring of `src/kg/cq.py`).
- **Next:** the export (12.8), its per-well, per-relation inventory bound to this release; then the
  two-well path to a model output (LU-6 can now report CQ5 and CQ6).
- **Checks (2026-11-06):** `test_ontology` passes (0.6.1); `test_kg_rules` passed on the release of
  09:08 UTC (the 09:32 release re-derived the same 162,997 triples after the label fix); the CQ
  fixtures (sections 1-11) and the river data section (17) of `test_cq` pass on the 09:32 release.
  **To redo at the next session:** the full `test_cq`, `test_kg_rules`, `test_kg`, `test_release`
  and `test_exchange_evidence` on the final files (a run was in progress when the session ended;
  two queries then gained a `documentKey` column only).
- **Suite run at the end of the session (on the final files):** `test_cq` (9 min), `test_kg_rules`,
  `test_release`, `test_exchange_evidence` pass; **`test_kg` fails: "AssertionError: a point off dept
  66"**, probably a new gauge or surface-intake point of `src/kg/rivers.py` outside the check's
  département box. To fix first at the next session (decide whether the point or the check is wrong).

## 2026-11-06 (afternoon): the Codex review of the day answered

Review `docs/review_codex_2026-11-06.md` (moved from the root, unchanged); verdicts, checks and what
was done point by point in `docs/review_codex_2026-11-06_response.md`. Assil: "check it out and if
there's something concerning or good adapt it, otherwise continue". Every point held; none was
rejected.

### Recurring check (CLAUDE.md §7)
1. *Chain link advanced:* none new; the water → model link of the morning (D's river and canal
   edges) is corrected: what the sources say about which unit, where and when.
2. *Where dated land use enters:* unchanged (the crop-thirst index, LU-4; CQ7's dated areas); no
   command area ties a parcel to a canal.
3. *Observed / inferred / assumed / unknown:* observed: the passages and their documents; now also
   recorded: each statement's subject (a unit, or an aggregate of units), its method and its
   period; inferred: the localisation of an aggregate statement to the unit on whose outcrop the
   river runs (a separate, labelled inference, never evidence about the unit), the section
   overlaps; assumed: a remote gauge's discharge and the plain's summed canal diversions as proxies
   (now explicit, pending review); unknown: everything off the geological map (no longer a
   negative answer).
4. *Evidence vs plan:* done and tested below; the Gate 3 questions are plans.
5. *Next model experiment:* none before the export (12.8).
6. *Still missing from the subject:* unchanged from the morning (12.10, CQ10, CQ16, the AGROVOC
   gold set, OntoAligner, command areas).

### What was done
- **S1, the failing graph test.** The 45 gauges were written `POINT (x y)` by Shapely, every other
  point `POINT(x y)`; the old regex turned them into NaN and blamed the coordinates. Gauges are now
  written by the graph's `point()` helper. `test_kg` check 7 parses every geometry with Shapely:
  Lambert-93, inside the département box (lines and polygons too, no longer points only), points in
  the form the CQ2 queries parse as text; four fixtures check the checker. 16 BD LISA multipolygons
  are invalid as published: counted, not refused.
- **S2, documents.** `src/ingest/documents.py` writes atomically and saves its index after each
  document; a stored copy without an entry is fetched again and compared, never dated by guess.
  `tests/test_documents.py`.
- **R1, aggregates.** Nineteen of the 32 statements are about an aggregate: FRDG351's table (14
  rows, the body's eight units), the EVP's "aquifères", BRGM's "Quaternary groundwater (poles P1
  and P2)" (water end-members, not units: report p. 23), "formations du Quaternaire", "aquifère
  quaternaire", SMNPR's "nappes quaternaires" and the EVP Agly's "nappe alluviale". The CSV records
  `subject`, `groundwater_body` and `method`; the graph writes `aboutUnit` only for a statement
  about the unit itself and `aggregateMemberUnit` (with `aboutGroundwaterBody` for FRDG351 and
  FRDG243) otherwise. Rules: a documented lateral association needs a statement about the unit
  itself; an aggregate statement is localised to an on-outcrop association when pieces of its
  section run on the unit's outcrop (`localizedStatement`, order 6; canals order 3), documents the
  exchange at the aggregate's scale and makes no sign eligible. `test_exchange_evidence` gate 6
  checks every subject against its sheet's own unit list.
- **Q3, measurements at a site:** applicable only in that site's zone (river and canal rules,
  shapes, the stale checks of CQ5 and CQ8).
- **Q1, Q2, incomplete searches:** reaches off the map turn CQ8's `none_found` (and
  `no_pool_gauge`, when a pool-gauged river is off the map) into `unknown`, and a documented CQ5
  answer into `partial`, with the off-map length.
- **R4, conflicts and periods.** `lulcw:overlapsSection` (lines running together over at least
  500 m within 100 m; 14 pairs, all on the Têt: FRDR224 and FRDR223 do not overlap each other, nor
  do BRGM's adjacent stretches); a conflict needs opposite states for the same or overlapping
  stretches, both dated with overlapping periods (contradiction) or one undated (unresolved);
  otherwise variation. CQ5 and CQ6 take an optional requested period. `evidenceMethod`: 5
  differential gauging, 7 geochemical tracing, 4 water balance, 16 synthesis.
- **R2, constraint decisions.** `lulcw:ConstraintDecision` per mechanism and policy
  (`configs/constraint_decisions.csv`): pumping accepted (CLAUDE.md §3), recharge, river and canal
  pending; `cq08_influences` returns `proxyReview`, `constraintApproval` and `constrained`.
- **R3, alignments.** `RiverReach` closeMatch `HY_FlowPath` instead of every reach ⊑ HY_FlowPath;
  the HY_Features import keeps the source's `skos:broader`; the new ledger
  (`ontology/alignments/ledger.csv`, 25 rows) and `test_ontology` gate 8 (HermiT: 8 required
  subsumptions hold, none of 13 forbidden ones). The ledger's counterexample check found a second
  faulty axiom: `Piezometer ⊑ GW_Well`, but the network's monitoring points include springs
  (Fontestramar, Source de la Tirounère, Source Sainte-Cécile, Source Clots de Rhodes): a close
  match now, and the class definition names the springs.
- **Release identity.** `git_version` hashes the uncommitted changes; the facts summary records the
  hashes of the configuration files and snapshot manifests; `configs/snapshots.json` pins the
  snapshots the graph and its tests read.
- Ontology **0.7.0**; analysis plan §14 item 17 (the decisions and the ❓ for Gate 3).

### Results (release rebuilt 14:28–14:43 local time, dataset v4, main policy)
- Facts 469,450 triples (+113), rule outputs 162,922 (−75), no SHACL violation (the 8 infos of the
  wells without an investigation depth); rules 186 s, validation 413 s.
- **Documented lateral links 4 → 2**: HIPPO2 and 10915X0395/PZ lost their link to the Agly, which
  rested on FRDG351's table alone; the two 10962X PZ keep theirs (BRGM: "the ancient alluvium pole",
  671AB02 itself). **River edges 35 → 34 wells (23 core)**: HIPPO2 had no other.
- **Eligible river signs 7 → 3 wells (2 core)**: MILLAS C2-1 (BRGM: the Têt drains the recent
  alluvium between Rodès and T6), CORBERE and 10962X0075/PZ (BRGM, ancient alluvium). BARQUA (Agly),
  10915X0395/PZ (Têt) and 10972X0094/111111 (Tech) keep their edges but only aggregate statements
  document them (FRDG351's rows, the EVP Têt, BRGM's "Quaternary formations"): ineligible, with
  that reason, until Gate 3 decides whether outcrop localisation suffices.
- Canal edges unchanged (5 wells, 4 core, 2 eligible); 10915X0395/PZ no longer cites BRGM's mixing
  measured at C2-1 and stays eligible on the statements about 718BP02 itself.
- Statements: 41 applications to the unit itself (69 before, aggregates included) and 15
  localisations from an aggregate.
- **CQ5**: conflicting 4 → 2 (C2-1 and 10915X0395/PZ: undated FRDG351 or EVP statements against
  BRGM's 2017 campaign on overlapping stretches, "unresolved"), supported 16 → 15, partial 39 → 42
  (BARQUA and the other wells with 32 m of the Agly off the map), unknown 1. **CQ8 river**: unknown
  6 → 7 (COLLIOURE RIMBAU, 448 m of the Massane off the map; before a "completed" none_found);
  HIPPO2 is now a completed none_found.
- No recharge, river or canal sign is constrained under any policy before Gate 3
  (`cq08_influences.constrained`); pumping signs are, where eligible and selected.

### What to consider
- **Fewer eligible river signs** (3 wells). The physics is unchanged; what changed is that body-level
  wording no longer counts as evidence about a unit. If Gate 3 accepts outcrop localisation, three
  wells come back (BARQUA, 10915X0395/PZ, 111111); a domain reviewer can settle each case by reading
  FRDG351's table with the map.
- **The constraint layer defaults to off.** RQ2's "hard" arm will constrain pumping signs only until
  Gate 3 approves other mechanisms; the analysis plan's soft/hard comparison should say which
  mechanisms each run constrains.
- **The alignment ledger** is the place where a correspondence is argued; a new alignment axiom
  without a ledger row now fails `test_ontology`.
- **Next:** unchanged: the export (12.8) with its per-well, per-relation inventory and the proposed
  path-aggregation rule (analysis plan §14 item 17), then the two-well path.

## 2026-11-06 (continued): 12.8, step 1: the inventory of arm D

### Recurring check (CLAUDE.md §7)
1. *Chain link advanced:* water → model: what D's graph gives each well, before any arm is scored.
2. *Dated land use:* none enters D's graph (no command areas; the crop-thirst index is a feature).
3. *Observed / inferred / assumed / unknown:* the inventory only reads the release; "constrained"
   reflects the constraint decisions (pumping accepted, the others pending).
4. *Evidence vs plan:* done and tested; the HeteroData export itself is still a plan.
5. *Next model experiment:* none before the export and the two-well path.
6. *Missing from the subject:* unchanged.

### What was done
- `src/kg/inventory.py` (`PFE_DATASET=v4 python -m src.kg.inventory [--policy …]`): per well and
  relation (pumping, recharge in the 5 km zone, recharge unit-wide, river, canal, well links) the
  sources D connects, the number of evidence paths, eligible and constrained edges (one edge per
  source; eligible or constrained only if every selected path is, with one sign: the rule proposed
  in analysis plan §14 item 17), nearest distance, cell weights, CQ8's answer and reason where
  there is no edge, the well links under each candidate depth threshold (10, 20, 50 m, none), and
  the distinct sources a depth-2 network reaches through the selected links. Read through the CQ
  queries, so it cannot drift from the CQ answers. Output
  `data/processed/kg/inventory_v4_main.parquet` (390 rows) and `.json` (the release's hashes, the
  policy, the code version, totals).
- `tests/test_inventory.py`: the aggregation rule on synthetic paths, the CQ fixture (W1's pumping
  edges per facility, W7's recharge weights, R1's eligible but unconstrained river and canal edges,
  R8's off-map unknown, symmetric links, monotone reach), and the data totals against independent
  SPARQL counts of the release. Passes.

### Results (main policy, release of 2026-11-06 13:42 UTC; 65 wells, 33 core)

| relation | wells with an edge (core) | without (core) | wells with an eligible edge | constrained edges | wells reaching more sources at depth 2 (no threshold / 50 m) |
|---|---|---|---|---|---|
| pumping (facilities) | 43 (24) | 22 (9) | 40 | 416 | 22 / 13 |
| recharge, 5 km zone | 54 (27) | 11 (6) | 54 | 0 | 13 / 5 |
| recharge, unit-wide (sensitivity) | 59 (32) | 6 (1) | 59 | 0 | 0 / 0 |
| river (pool gauges) | 34 (23) | 31 (10) | 3 | 0 | 4 / 1 |
| canal | 5 (4) | 60 (29) | 2 | 0 | 0 / 0 |
| well links (same unit, 5 km) | 38 (22) | 27 (11) | — | — | pairs within 10 / 20 / 50 m / any: 0 / 2 / 13 / 47 |

- One core well gets no exogenous edge at all: CARRIE (its unit 760AE09 is outside BD LISA).
- Pumping: 434 facility-well edges, 416 eligible (exact unit on both sides), all constrained under
  the main policy's decision; recharge, river and canal edges are eligible in places but none is
  constrained before Gate 3.
- The well links decide much of what a well sees: without a depth threshold 22 wells reach more
  pumping sources through a linked well; with 50 m, 13. The per-regime threshold therefore changes
  D's information, not only its structure, and is reported with each regime (item 15).

### What to consider
- The **D vs C contrast** is a contrast of whole connection policies (item 15): C gives every well its
  nearest cell and two gauges; D leaves 11 wells (6 core) without a local recharge edge and 31 (10
  core) without a river edge. This table is the inventory to report beside it; the coverage-matched
  diagnostic, if wanted, is defined before any score.
- **Next:** the export proper (node and edge tables for C–F from one node inventory, bound to the
  release; the HeteroData adapter where PyG is installed, i.e. on Colab or Kaggle), the per-regime
  depth threshold from each regime's training heads, the equivalence test against pandas, and a
  fixed-weight forward pass compared between the two.
