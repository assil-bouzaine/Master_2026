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
