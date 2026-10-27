# LULC-Water competency questions

**Revision:** 2026-10-24. Requirements for Phase 3; 16 stable question IDs.
This revision replaces the 2026-10-23 draft. It preserves the project scope and
priorities, but strengthens the meaning, answer structure and acceptance criteria of
each question. It is a specification, **not a claim that the ontology or its tests
already exist**. Reasons for the changes: [review note](notes/step12c_competency_review.md).

Approval history: the project brief records approval of the six MUST questions
(CQ1, CQ2, CQ3, CQ8, CQ11, CQ12) on 2026-10-24. This revision refines their
requirements and the seven SHOULD/three COULD questions without changing priorities.
**Priority change (Assil, 2026-10-25, after `docs/review_codex_2026-10-25.md`):**
CQ7, CQ10 and CQ15 become MUST, so the MUST set covers the subject's land-use →
water → model → explanation chain (9 MUST, 4 SHOULD, 3 COULD).

## 1. Purpose and scope

The ontology must describe how land use, water abstraction, climate and the
hydrogeological setting relate to weekly groundwater levels in the Roussillon plain.
It must support the model's graph, qualified physical assumptions and explanations,
while allowing an answer to remain uncertain. Its requirements come from the
[subject](../Documents/sujet.docx), the [research decisions](supervisor_questions.md),
and the [analysis plan](analysis_plan.md), rather than just the columns currently
available in the dataset.

Competency questions define what knowledge the ontology must represent and retrieve.
One natural-language question can require several formal queries; a single SPARQL
query per question is not a design constraint. See
[Wiśniewski et al. (2019), DOI: 10.1016/j.websem.2019.100534](https://www.sciencedirect.com/science/article/pii/S1570826819300617).

Three motivating uses guide the questions:

- **Hydrogeologist:** identify which units a well may monitor, what evidence supports
  their connections, and where a head comparison is meaningful.
- **Modeller:** select reproducible graph edges, inputs and conditional sign constraints,
  with traceable inclusion rules and no target leakage.
- **Water manager:** inspect declared abstraction by use, follow an explanation, and
  explore explicitly hypothetical crop-change scenarios with their limitations.

The core remains one aquifer system, groundwater head and its SGI class. Pollution,
water-quality modelling, allocation rights, economic welfare and prediction of use
conflicts remain future work. A Manouba transfer recipe or conditional qualitative
demo remains compatible with the [project decisions](supervisor_questions.md).

## 2. Common answer contract

These requirements apply to **all 16 questions**, including when their data are missing.
The field names below are conceptual requirements, not final RDF property names.

### Inputs, scope and reproducibility

- `W`: monitoring well; `U`: hydrogeological unit; `S`: explicit spatial extent;
  `y`: calendar year; `T`: dated interval; `r`: search radius in metres.
- Every query records its KG/data release, source versions, spatial selection method,
  interval, and rule/policy version. Record an information cutoff when testing what
  was knowable at a past date. A source release date and the date a fact applies are
  different things.
- Use metres for distances, square metres or hectares for areas, cubic metres for
  volumes, and a stated vertical datum for heads. Distances/areas are computed in
  Lambert-93 (EPSG:2154) for this site, with the CRS retained. A depth below ground and
  a head elevation cannot be compared as if they were the same quantity.
- Keep 3 km parcel and 5 km neighbour searches as named, reproducible reference queries.
  They are not universal hydraulic limits. Any tuned distance/depth threshold is frozen
  with the training/validation protocol before test evaluation.

### Evidence and incomplete answers

Every answer row, or the assertion it cites, must expose:

| Element | Required meaning |
|---|---|
| Identity | Stable source identifiers; distinguish a well, a monitoring site, an abstraction facility and an individual intake |
| Validity | Where and when the assertion applies, including geometry/source vintage |
| Evidence kind | Reported observation, derived assertion, literature/expert hypothesis, or model/scenario result |
| Provenance | Source record or document passage; producing procedure/rule and version; retrieval/production date |
| Assessment | Candidate/accepted/rejected/superseded status where relevant; confidence and its basis, at the resolution actually evaluated |
| Coverage | What was examined, what is missing, and whether the result is complete within that declared scope |

An answer has status `supported`, `partial`, `unknown`, `conflicting`, or
`not_applicable`, with a reason. `Supported` means supported by the cited evidence,
not established physical truth. A complete search with no matches may return an empty
supported result; an unsearched or uncovered area must not. Zero volume, no restriction,
no irrigation and no hydraulic connection must never be manufactured from missing data.
This follows OWL's open-world interpretation; explicit completeness checks belong in
the application and SHACL validation. See the
[OWL 2 Primer](https://www.w3.org/TR/owl2-primer/) and
[SHACL Recommendation](https://www.w3.org/TR/shacl/).

Confidence (`confident`, `probable`, `possible`) is separate from answer status,
source quality, and acceptance by a model-export policy. `Unknown` is not a probability.
A rule's empirical precision is not the probability that each individual assertion is
true. Conflicting records and alternatives stay accessible; selecting one for an
experiment must not erase the others.

### Observation and computation boundary

An observation needs a feature of interest, observed property, result and unit,
phenomenon time, method and quality information. Record result-production and source
publication/retrieval times separately when available. SOSA distinguishes phenomenon
time from result time; neither alone establishes availability to the modeller.
[SOSA/SSN (2017 Recommendation)](https://www.w3.org/TR/2017/REC-vocab-ssn-20171019/).

The KG stores entities, qualified relations, annual/dated facts, series references and
selected derived summaries. Weekly arrays remain in parquet. Statistical summaries and
model outputs are computed outside OWL, then exposed through versioned result records
or an explicitly linked application query. SPARQL retrieves evidence and results; OWL
does not estimate recharge, compute a prediction or establish causality. Provenance
connects results to their inputs and producing activities.
[PROV-O](https://www.w3.org/TR/prov-o/).

## 3. Catalogue

**Feeds:** G = graph; F = features; C = model constraints; E = explanations;
V = validation; R = research framing; S = subject objective.
**Priority:** MUST = core requirement; SHOULD = planned supporting capability;
COULD = conditional extension. Priority is independent of data readiness.

“Available” below refers to source tables, not implemented KG queries. Dataset v4 is
the data contract; historical v3 findings remain in the linked step notes.

| ID | Competency question | Feeds | Priority | Current evidence |
|---|---|---|---|---|
| CQ1 | What hydrogeological and monitoring context is known for well W? | G F V | MUST | Well metadata/stacks available; screens incomplete |
| CQ2 | Which abstraction facilities may draw from W's unit, with what evidence and uncertainty? | G F C V R | MUST | Attribution tables available; resolution/conflicts need explicit representation |
| CQ3 | What is the local vertical arrangement of units in S? | G F V | MUST | BD LISA stacks available; aggregate contacts need spatial qualification |
| CQ4 | Which mapped outcrop areas of U can support recharge-related inputs, and how are they covered by weather cells? | F E | SHOULD | Geometry/grid available; weighted intersections to build |
| CQ5 | Which river reaches are associated with U, and what is known about exchange and gauge relevance? | G F C | SHOULD | River/gauge metadata available; hydraulic evidence incomplete |
| CQ6 | Which canal supply areas overlap U, and which intake-to-recharge pathways are supported? | G F C R S | COULD | Intakes available; supply-area and pathway evidence missing |
| CQ7 | What crops/land uses occupy S in year y, and what irrigation-demand estimates are justified? | F E R S | MUST | RPG 2016/2023 available; demand method/mappings to validate |
| CQ8 | Which driver-to-head pathways are admissible for W, and under what conditions may their signs constrain the model? | C G E V | MUST | Inputs partly available; rule/constraint catalogue to build |
| CQ9 | Which restriction events applied to the relevant location, resource and use during T? | E V | COULD | Level histories available; authoritative spatial applicability missing |
| CQ10 | Which evidence and model results support an explanation of W at time t? | E V S | MUST | KG, model-result links and explanation checks to build |
| CQ11 | Which wells are same-unit neighbours of W under a declared distance/depth policy? | G V | MUST | Well metadata available |
| CQ12 | What declared abstraction can be attributed to U in year y by use, and what remains unresolved? | R E F V | MUST | Annual records/attributions available; audited aggregation to build |
| CQ13 | Which well pairs permit meaningful head comparisons, and what do comparable observations show? | E V G | SHOULD | Pair list available; v4/window-specific summaries to compute |
| CQ14 | What is known separately about cover, confinement and pressure conditions at W? | F C E V | SHOULD | Stack/level data available; local confinement evidence incomplete |
| CQ15 | Which parcel-seasons satisfy a documented probable-irrigation rule, with what validation and water-source evidence? | F E S V | MUST | Satellite observations/rule/evaluation to build |
| CQ16 | Under an explicit crop-change scenario, where are modelled effects on U greatest and most robust? | E S V | COULD | Scenario assumptions, supply links and trained model missing |

## 4. Detailed requirements

Two real anchors were checked against local v4 tables on 2026-10-24:
**W1** = `10964X0119/NYLS-1` (Ponteilla), recorded unit `671AA00`, investigation depth
97 m; **W2** = `10906X0039/C2-1` (Millas), recorded unit `718BP02`, investigation depth
9 m. These are source-record examples, not independent validation of the monitored
screen interval. Numerical cases labelled **synthetic** below are proposed test fixtures.

### CQ1 — Monitoring well and hydrogeological context

**Question.** For well W, which hydrogeological unit(s) and WFD groundwater body(ies)
are recorded or inferred as monitored, what depth information supports that assignment,
and what is the mapped local geological stack?

- **Inputs:** W, metadata release and optional validity date. **Outputs:** one qualified
  assignment per candidate unit/body; identifiers, site/location, investigation depth,
  screened interval if documented, depth reference/unit, ordered stack and unresolved
  conflicts. Identify the observation-series reference, variable, vertical datum,
  temporal coverage and quality policy used for the well's head observations.
- **Meaning:** distinguish a physical well, a monitoring site and its observations.
  A WFD management body is not identical to a BD LISA unit; preserve multiple
  memberships. Investigation depth is not screened depth, and map position alone does
  not establish what a borehole monitors.
- **Evidence/readiness:** `dataset_v4/wells.parquet`, `interim/piezo_stations.parquet`,
  BD LISA elementary polygons/stacks and, when obtained, BSS construction logs.
  Well codes absent from the regional geometry extract remain identifiable; report the
  missing geometry instead of dropping the well.
- **Acceptance:** W1 returns the recorded 97 m investigation depth and unit `671AA00`;
  W2 returns `718BP02 > 671AA00` as its local stack. Neither acquires a screen interval
  from that depth. A synthetic conflicting record returns both candidates with their
  sources; missing depth leaves the well in the answer.
- **Ontology needs / dependencies:** monitoring well/site, hydrogeological unit,
  groundwater body, qualified monitoring assignment, depth measurement and series
  reference. Foundation for CQ2–CQ5 and CQ11–CQ14; no dependency on model performance.

### CQ2 — Abstraction-to-unit attribution

**Question.** Within a declared search area around W, which groundwater abstraction
facilities are recorded or inferred to draw from a unit W monitors, at what resolution,
for which dated uses, and with what supporting or conflicting evidence?

- **Inputs:** W, S or r, year/interval, attribution release and confidence-selection
  policy. **Outputs:** facility/intake IDs, candidate unit or unit group, distance,
  dated uses, documented screen/depth information, attribution rank/status, evidence,
  confidence, evaluation scope and inclusion/exclusion reason under the selected policy.
  Report nearby facilities with unknown attribution separately.
- **Meaning:** a BNPE `code_ouvrage` identifies the reporting facility; do not assume a
  one-to-one mapping to physical boreholes or duplicate a facility's volume across its
  intakes. Nearby or vertically overlapping does not mean hydraulically connected.
  Alternatives are competing assignments, not fractions of pumped water. “Confident”
  describes the evidence policy, not certainty about hydraulic influence on W.
- **Evidence/readiness:** `interim/pump_unit_evidence.parquet`,
  `pump_unit_attribution.parquet`, `pump_unit_attribution_eval.json`, BSS/ADES records
  and BD LISA stacks; [attribution implementation](../src/kg/pump_attribution.py).
  The present table's single confidence field does not distinguish group-level from
  exact-unit accuracy. Its `flag_true` evaluation is 18/19 correct at alluvium-group
  level but 12/19 at exact-unit level. Irrigation has no recorded reference boreholes
  in that evaluation. Neither limitation may disappear during RDF conversion.
- **Acceptance:** a synthetic BSS-supported assignment remains linked to its source;
  a deep borehole with a conflicting alluvial record retains both the record and the
  depth-based alternative. Group-only evidence cannot pass an exact-unit confident
  filter. An irrigation candidate cannot inherit drinking-water evaluation confidence.
  Changing policy changes selected edges, not the stored evidence.
- **Ontology needs / dependencies:** qualified unit attribution, facility/intake identity,
  dated water use, method/evaluation and selection policy; CQ1 and CQ3. Main runs use
  confident + probable links, as recorded in the [2026-10-24 decision](supervisor_questions.md);
  confident-only and all-link policies remain sensitivity runs. Each policy preserves
  the resolution and limits of its evidence; inclusion does not upgrade certainty.

### CQ3 — Spatially qualified vertical structure

**Question.** At a location or within S, which units lie directly above/below U, which
are separated by other mapped units, and what is known about those intervening units?

- **Inputs:** U, S/location and BD LISA release. **Outputs:** upper/lower unit, direct
  adjacency versus indirect ordering, intervening sequence, supporting elementary
  polygons, overlap area and the source classification of each unit.
- **Meaning:** this is geological arrangement, not hydraulic connection, flow direction
  or a head inequality. “No intervening mapped unit” does not prove no confining bed
  exists below map resolution. A semi-permeable BD LISA label does not by itself
  describe the hydraulic behaviour of an entire multilayer system.
- **Evidence/readiness:** elementary polygons and `TABLE_PILE_ENTITES_NIV3` in the
  BD LISA GeoPackage. `bdlisa_overlies_plain.csv` is a useful aggregate, but its 26
  pairs do not retain individual spatial witnesses; reconstruct those for the KG.
- **Acceptance:** a synthetic stack `A > B > C` gives direct A–B/B–C and indirect A–C.
  If A overlies B only in S1 and B overlies C only in disjoint S2, the query must not
  infer a local A–C stack. Any minimum-area filter is a query/export parameter and
  leaves the original contact evidence available.
- **Ontology needs / dependencies:** local stratigraphic relation, stack, geometry,
  unit nature and scale; CQ1 identities. Transitive ordering is restricted to a
  compatible spatial context; an unqualified global transitive `above` is insufficient.

### CQ4 — Outcrop coverage and recharge-related forcing

**Question.** Within S, where is U mapped at outcrop, which weather cells cover that
area, and which evidence justifies using those cells to construct a recharge proxy?

- **Inputs:** U, S, geological/grid releases and forcing variable/period.
  **Outputs:** outcrop geometry, cell intersections, intersection areas and weights,
  covered/uncovered area, forcing-series references and recharge interpretation.
- **Meaning:** outcrop is a mapped geological property; it is not proof of actual
  infiltration, effective recharge or a complete contributing area. Recharge may also
  involve lateral inflow, leakage or irrigation return flow. State explicitly whether
  S clips the unit and excludes recharge outside the study boundary.
- **Evidence/readiness:** BD LISA order-1 geometry and SAFRAN grid are available;
  intersections and their provenance remain to be built. Geometric association is
  represented separately from hydraulic interpretation, using
  [GeoSPARQL 1.1](https://docs.ogc.org/is/22-047r1/22-047r1.html).
  *Built 2026-10-27 (increment 1; `tests/cq/cq04_*.rq`):* polygon-cell intersection
  areas for the 65 search zones (5 km) and the forcing extent (the 141 cells), outcrop
  coverages and cell weights derived by rules, and each unit's whole mapped outcrop in the
  BD LISA extract, so that an answer states how much of the unit S holds (`unitShareInS`).
  A negative answer ("no mapped outcrop in S") follows a completed search of the asserted
  pieces; outcrop facts without a derived coverage answer unknown, and facts and rule
  outputs are read only as a validated release (Codex review of 2026-10-26, §1). The
  forcing extent clips 681AF00 (15 % of its outcrop outside the cells) and 681AO00 (9 %):
  partial. For the Pliocene, local outcrop is a weak proxy: rain infiltration alone does
  not recharge the deep aquifers, which are fed by the Têt and its Quaternary aquifer
  upstream, the Corbières karst and the peripheral massifs (SMNPR), and by downward leakage
  from the Quaternary driven by Pliocene pumping (BRGM/RP-71486-FR); analysis plan §14
  item 15.
- **Acceptance:** synthetic outcrop area 100 ha with non-overlapping cell intersections
  of 60 and 40 ha gives weights 0.6 and 0.4. If only 80 ha are covered, return coverage
  0.8; any weights renormalised over covered area are labelled as such. A fully covered
  subsurface unit with no local outcrop returns “no mapped outcrop in S”, not zero
  recharge. Union duplicate/overlapping geometries before area aggregation.
- **Ontology needs / dependencies:** outcrop feature, spatial coverage/weight,
  forcing observation/series and recharge-proxy procedure; CQ1 and CQ3.

### CQ5 — River reaches, aquifer exchange and gauges

**Question.** Which river reaches are associated with U in S, what evidence establishes
or merely suggests hydraulic exchange, and which gauges can represent those reaches
for the requested period?

- **Inputs:** U, S, T and association/evidence policy. **Outputs:** river and reach IDs,
  association type, evidence, exchange direction where known (river-to-aquifer,
  aquifer-to-river, variable or unknown), validity period, gauge location, measured
  variable, series coverage and representativeness limitations.
- **Meaning:** a shared river name, a spatial intersection and a demonstrated hydraulic
  connection are different assertions. A gauge measures discharge/stage at its own
  site, not recharge to the entire unit. Exchange depends on hydraulic conditions and
  may change direction; an alluvial name does not justify a permanent positive sign.
  [USGS groundwater/surface-water exchange guidance](https://ca.water.usgs.gov/sustainable-groundwater-management/interconnected-surface-water-depletion.html).
- **Evidence/readiness:** `dataset_v4/gauges.parquet` and river series are available.
  Names provide candidate associations; reach geometry, hydraulic documentation and
  a gauge-to-reach selection rule still need work.
- **Acceptance:** the Têt name may associate `718BP02` with a river, but cannot alone
  produce a signed recharge constraint. A gauge on the same river but outside the
  relevant reach remains a labelled proxy candidate. Two documented opposing exchange
  directions in different periods are preserved, not collapsed into a timeless sign.
- **Ontology needs / dependencies:** river, reach, gauge, observation, spatial association
  and qualified exchange assertion; CQ1/CQ3, optionally CQ4.

### CQ6 — Canal supply and possible return-flow pathways

**Question.** Which canal command areas overlap U in S, which river intakes supply them,
which parcels are served during T, and what evidence supports conveyance seepage or
irrigation return flow reaching U?

- **Inputs:** U, S, T and pathway policy. **Outputs:** intake → canal → supply area →
  parcel/land-use area links, overlap areas, dated service evidence, candidate receiving
  units, documented/assumed return fractions and provenance. Missing links are explicit.
- **Meaning:** distinguish river diversion, delivery, crop consumption, canal seepage
  and return flow. The intake's location does not locate the receiving fields. Being
  inside a command area means potential service, not proof of irrigation in a given
  year. A diverted cubic metre is not automatically a cubic metre of recharge.
- **Evidence/readiness:** BNPE canal-related records exist; authoritative supply-area
  polygons, service links and local return-flow evidence are not yet available. The
  current plain-wide canal feature is a modelling proxy, not a mapped local pathway.
- **Acceptance:** synthetic areas supplied by two intakes keep distinct supply chains;
  an overlapping parcel is not counted twice without an allocation rule. With only an
  intake record, return a partial chain and no local recharge amount or hard sign.
- **Ontology needs / dependencies:** canal, intake, command area, dated supply relation,
  water-transfer/return-flow hypothesis and quantity; CQ3–CQ5 and CQ7. Retain this CQ
  as a documented data gap if polygons cannot be obtained; do not fabricate coverage.

### CQ7 — Dated land use, crop alignment and irrigation demand

**Question.** In S and RPG year y, which crops and land uses are recorded, over what
area, how are their source codes aligned to shared vocabularies, and what estimate or
category of irrigation requirement is justified for that season and setting?

- **Inputs:** y, S (e.g. W's 3 km buffer or U's outcrop), spatial aggregation policy and
  mapping/demand-rule versions. **Outputs:** parcel-year IDs, original crop codes,
  AGROVOC/HILUCS mappings with mapping relation and evidence, area by class, unmapped
  area, demand value/category with unit, method, assumptions and missing inputs.
- **Meaning:** crop identity, land use, potential irrigation requirement, actual
  irrigation and abstraction source are different facts. Demand depends on climate,
  season, soil and management; a universal high/low classification from crop name alone
  is insufficient. FAO distinguishes crop water requirements from irrigation needs.
  [FAO crop evapotranspiration guidance](https://www.fao.org/4/X0490E/x0490e04.htm).
- **Evidence/readiness:** RPG 2016 and 2023 available; mapping gold set and locally
  applicable demand procedure to build. Preserve the existing centroid-selected,
  whole-parcel area as a named legacy statistic. “Hectares inside S” instead requires
  clipped intersection area. Never present those two quantities as interchangeable.
- **Acceptance:** a synthetic 10 ha parcel intersecting S over 4 ha contributes 4 ha
  to clipped area. Unknown crop codes remain in the denominator as unmapped. A 2023
  observation cannot answer “observed crop in 2020”; any static proxy is labelled and
  subjected to the analysis plan's information-availability policy. Do not infer a
  parcel's crop transition from matching identifiers across years without lineage.
- **Ontology needs / dependencies:** parcel-year observation, crop/use concept,
  versioned alignment and demand estimate; CQ4 only for outcrop-based selection.

### CQ8 — Conditional influences and admissible constraints

**Question.** For W and T, which driver-to-head pathways are supported or hypothesised,
through which entities, and under which assumptions, evidence policy and time scale
may their response signs constrain a model?

- **Inputs:** W, T, model task, evidence/export policy and rule versions.
  **Outputs:** driver variable and unit, ordered path, target, mechanism, source
  assertions, confidence, applicable conditions, spatial/temporal scope, driver group,
  proposed sign and constraint eligibility with reasons. A sign may remain unknown or
  conditional; an absent supported path is not proof of no influence.
- **Meaning:** the sign is a directional response to a specified input change, with
  other stated conditions held fixed; it is not a weekly correlation or a claim of
  measured causality. Pumping from a connected unit can justify a non-increasing head
  response under the stated abstraction convention. River discharge, raw rainfall,
  potential ET and canal diversion are proxies whose signs require their own mechanism
  and conditions. Do not constrain both a net-recharge input and its components as if
  they were independent forcings.
- **Evidence/readiness:** CQ1–CQ7, literature/expert assumptions and the attribution
  tables. Candidate physical mechanisms become qualified `Influence` records, not
  unconditional OWL claims about every instance. Distance is a selection assumption,
  not hydraulic proof. Literature-extracted rules retain passage, scope and review
  status; unreviewed extracted text cannot enable a hard constraint.
- **Acceptance:** a synthetic supported pumping path yields a conditional negative
  response sign; a name-only river link yields no hard sign. A missing/unaccepted
  segment blocks an accepted end-to-end path. Seasonal deficit and reconstructed
  pumping remain grouped as “summer demand” where they cannot be separated, following
  [analysis plan §8](analysis_plan.md#8-claims-about-drivers-rq2rq4).
- **Ontology needs / dependencies:** driver, pathway, mechanism, assumption, influence,
  driver group and constraint specification; CQ1–CQ7 as available. Whole-model
  monotonicity is tested in model code; graph consistency alone cannot guarantee it.

### CQ9 — Dated restriction context

**Question.** Which restriction events were applicable at the location of W, or at a
specified abstraction location serving the case study, during T, for which resource
and use, and on what official spatial and temporal evidence?

- **Inputs:** location/target role, resource type, use, T and source release.
  **Outputs:** zone identifier and geometry version, order/event ID, authority/source,
  effective start/end, level, covered resource/use, exemptions if recorded and coverage.
  Return subintervals if the level changes during a week.
- **Meaning:** distinguish the location of a monitoring well from the location/legal
  scope of a withdrawal. Restriction severity is not an SGI class, compliance record,
  measured reduction in pumping or proof of drought at W. An overlapping order is
  not automatically applicable to every use. “No applicable restriction” requires
  evidence that the relevant records and boundaries are covered.
- **Evidence/readiness:** VigiEau level histories exist; zone polygons and durable
  cross-year identities are missing. Zone-name matching alone cannot establish
  spatial applicability. This CQ supplies explanation context; groundwater-triggered
  restrictions are excluded from model inputs under the analysis plan.
- **Acceptance:** a synthetic order starting midweek yields dated segments, not a
  fabricated whole-week level. Missing geometry returns unknown applicability, not
  level 0. A surface-water order is not relabelled as a groundwater restriction.
- **Ontology needs / dependencies:** restriction event, zone version, resource, use and
  interval; CQ1 location and CQ2 facility location when relevant.

### CQ10 — Evidence-backed model explanations

**Question.** For a model result at W and time t, what head/SGI result, driver
contributions and qualified knowledge paths support each explanation statement, and
which statements must be qualified or withheld?

- **Inputs:** result/run ID, W, t, KG release and explanation policy. **Outputs:** head
  value/unit/datum, SGI value/class with reference period and threshold version,
  contribution value/unit and reference baseline, cited entities/paths, assumptions,
  source quality/imputation flags and a statement-level validation report. Keep the
  simulated head distinct from an observed head.
- **Meaning:** this is retrieval of a model result and its evidence, not prediction
  by the ontology. Distinguish semantic consistency, computational faithfulness and
  physical/causal validity. The first can be checked from the KG; the others need the
  model tests and independent/twin evidence in the analysis plan.
- **Evidence/readiness:** model outputs and KG links are not yet implemented. SGI
  classification must reuse the versioned implementation and its training reference,
  not a newly invented threshold table. Explanation text says “the model attributes…”
  when reporting model contributions.
- **Acceptance:** reject a named non-existent entity, a path excluded by the run's
  policy, a mismatched period, or a wrong SGI boundary classification. Do **not**
  confuse response polarity with contribution sign: reduced pumping can contribute
  positively relative to a baseline even when more pumping lowers head. Contributions
  must reconstruct the model output including baseline/residual within a declared
  tolerance. Imputed-pumping weeks carry no pumping attribution claim; inseparable
  seasonal drivers use the CQ8 group.
- **Ontology needs / dependencies:** model/run/result reference, SGI classification,
  contribution, explanation claim and evidence path; CQ1, CQ8 and any contextual CQs.
  Explanatory validity is queryable, not merely a boolean “all entities exist”.

### CQ11 — Same-unit neighbouring wells

**Question.** Which other wells are within r of W and monitor a common unit under the
selected attribution policy, and what comparable depth information distinguishes them?

- **Inputs:** W, r (reference query: 5,000 m), metadata/evidence policy, optional
  depth-difference threshold and its selection provenance. **Outputs:** unordered well
  pair, shared unit and assignments, projected horizontal distance, investigation-depth
  difference, screen-elevation difference only if known, and edge-selection reason.
- **Meaning:** shared membership in the Pliocene system does not prove the same screened
  horizon or direct hydraulic connection. A small investigation-depth difference is
  a modelling descriptor. Different ground elevations can make identical below-ground
  depths correspond to different absolute elevations.
- **Evidence/readiness:** v4 wells and CQ1 assignments; pre-check motivation in
  [kg_precheck.md](kg_precheck.md). The ontology must not hard-code fixed depth classes.
- **Acceptance:** synthetic wells 4,999 m apart pass the inclusive 5 km reference query;
  5,001 m do not. No self-pairs or duplicate undirected pairs. A missing depth remains
  missing rather than 0; the pair can enter a distance-only policy but cannot satisfy
  a depth-required policy. Candidate-only unit overlap is labelled accordingly.
- **Ontology needs / dependencies:** qualified well link and export policy; CQ1.
  Head correlations can evaluate a graph but cannot define held-out-test edges.

### CQ12 — Annual abstraction accounting by unit and use

**Question.** For U, year y and reporting extent S, how much declared groundwater
abstraction is attributable to U by use under a stated policy, and how much of the
eligible declared total is unresolved, excluded or based on alternative assignments?

- **Inputs:** U, y, S, BNPE release and attribution/allocation policy. **Outputs:**
  totals in m³ by unit/use/confidence, facility counts, coverage denominator,
  unresolved/excluded totals, record-quality flags and alternative-policy results.
  Report imputed or harmonised estimates separately from original declarations.
- **Meaning:** use belongs to a dated volume record, not permanently to a facility.
  The reporting extent selects facilities by an explicit rule; it does not imply all
  abstraction from U occurs inside S. These are declared withdrawals, not necessarily
  all actual abstraction, consumptive use, sustainable yield or evidence of a conflict.
- **Evidence/readiness:** raw annual BNPE records in
  `data/raw/hubeau_bnpe/2026-10-20/chroniques_66.parquet`, attribution tables and
  reconstruction rules in [bnpe_v3.py](../src/dataset/bnpe_v3.py). Annual source records
  anchor the accounting; weekly reconstruction is not an independent observation.
  Preserve source revisions, reporting keys, producer quality and deduplication rules.
- **Acceptance:** synthetic facility P declares 100 m³ and has two alternative unit
  candidates. The combined accounting must never become 200 m³. With no accepted
  assignment, 100 m³ remains unresolved; with an explicit allocation, weights sum to
  at most 1 and the remainder stays unresolved. For each reporting scope/use,
  `eligible declared total = allocated + unresolved + explicitly excluded`, after
  documented source deduplication. Mutually exclusive sensitivity scenarios are not
  summed. Missing declarations are not zero.
- **Ontology needs / dependencies:** annual abstraction observation, dated use,
  attribution/allocation policy and aggregation result; CQ2. Preserve calendar-year
  totals when bridging to week-ending dates across December/January.

### CQ13 — Comparable well pairs and head relationships

**Question.** Which well pairs are documented at one monitoring site or form a spatial
comparison across superposed units, and over T how often is one comparable observed
head above the other, with what coverage and uncertainty?

- **Inputs:** pair or S/r, T, metadata release, datum, quality and temporal-matching
  policy, minimum sample count and near-equality tolerance. **Outputs:** pair type
  (documented nested/same-site or nearby comparison), unit assignments, known screens
  and depths, distance, matched/missing counts, head-difference statistics, fraction
  positive/negative/near-zero and the calculation provenance.
- **Meaning:** a head difference is not automatically a vertical hydraulic gradient.
  A gradient needs comparable heads and the relevant vertical separation of screened
  intervals; investigation depths alone do not supply it. Two wells kilometres apart
  also include horizontal variation. Neither vertical ordering nor one observed
  period establishes a permanent flow direction.
- **Evidence/readiness:** `bdlisa_vertical_pairs.csv` provides candidate pairs and
  historical summaries. Recompute requested summaries using v4 quality-filtered heads
  and the specified window; do not import full-record summaries as training features.
- **Acceptance:** a synthetic matched pair with equal sampling and differences
  `+1, -1, +1, -1` m gives 50% positive, not a head-ordering axiom. Non-overlapping
  time series or incompatible datums yield no comparison statistic. A nearby pair
  is never called nested solely because it passes a distance threshold.
- **Ontology needs / dependencies:** site/pair relation, comparable observation series
  and statistical result; CQ1 and CQ3. Computation occurs outside the reasoner.

### CQ14 — Cover, confinement and pressure state

**Question.** At W and for the relevant period, what evidence describes the monitored
unit's mapped cover, local hydraulic confinement and head relative to ground level,
and which of these properties remains unknown?

- **Inputs:** W, T or training window, geological/metadata release and level-quality
  policy. **Outputs:** stack position and cover, confinement assessment
  (confined/unconfined/semi-confined/unknown) with evidence and locality, head-above-ground
  fraction with denominator/tolerance, datum compatibility and limitations.
- **Meaning:** mapped cover does not establish confinement; BRGM explicitly documents
  covered yet unconfined settings.
  [BRGM/RP-62275-FR, §9.1.1, pp. 57–58](https://rapportage.eaufrance.fr/sites/default/files/DCE/2016/documents/FRN_guide_ME_2013_BRGM.pdf).
  An outcropping multilayer unit may still contain locally confined horizons.
  Artesian pressure means head above the confined aquifer's top; flowing conditions
  require head high enough to reach the outlet/ground surface. Those are distinct.
  [USGS artesian-well explanation](https://www.usgs.gov/water-science-school/science/artesian-water-and-artesian-wells).
- **Evidence/readiness:** stack position and head/ground-elevation data exist. The
  current `pct_days_artesian` field measures head above the assumed ground elevation;
  expose it as a head-above-ground proxy, not a complete confinement diagnosis or
  observation of actual discharge. Local lithology/screens and verified elevation
  reference may be needed. Use the appropriate v4 training-window summary for features.
- **Acceptance:** a synthetic covered unit without hydraulic evidence returns
  `covered; confinement unknown`. W1's order-1 stack cannot type every Pliocene horizon
  as unconfined. A missing/incompatible ground elevation produces unknown exceedance,
  not zero; changing the training window selects/recomputes the matching summary.
- **Ontology needs / dependencies:** local hydrogeological setting, confinement
  assessment and pressure-state summary; CQ1/CQ3/CQ13. No `ConfinedSetting` rule based
  only on stack position, and no unconditional “local rain cannot affect this well”.

### CQ15 — Probable irrigation from remote sensing

**Question.** Which parcel-seasons satisfy a versioned rule for probable irrigation,
which observations and quality checks support the classification, how has it been
validated, and what is separately known about their water supply?

- **Inputs:** parcel set/S, season/year, observation release and rule/threshold version.
  **Outputs:** dated classification (rule-positive/rule-negative/insufficient data),
  NDVI and soil-wetness observations with spatial support, cloud/valid-pixel coverage,
  temporal aggregation, thresholds, uncertainty, validation result and separate
  canal/abstraction-source associations.
- **Meaning:** high summer vegetation activity under dry regional conditions is an
  irrigation hypothesis, not proof. Crop phenology, roots, residual moisture and
  mixed pixels may offer alternative explanations. A negative heuristic result does
  not prove rainfed management. SAFRAN moisture represents a grid cell, not measured
  parcel moisture. Irrigation status belongs to a season/year, not timeless parcel type.
- **Evidence/readiness:** Sentinel-2 observations and the rule are still to build;
  SAFRAN and RPG are available. Validate against independent irrigation observations
  at compatible spatial/temporal resolution. Crop agreement is not irrigation
  validation; a canal perimeter or nearby BNPE point indicates access/plausibility,
  not a parcel-year irrigation label. Commune census totals support aggregate checks,
  not parcel-level precision/recall without labelled parcels.
- **Acceptance:** synthetic high-NDVI/low-wetness values produce a positive result only
  with sufficient quality/coverage. Cloud-contaminated or temporally mismatched inputs
  yield insufficient data. Classification survives an unknown supply source; proximity
  to a pump alone cannot produce `irrigatedBy`. Freeze thresholds without test leakage.
- **Ontology needs / dependencies:** parcel-season observation, quality, derived
  classification, rule execution and validation; CQ7, plus CQ2/CQ6 for supply context.
  The legacy name `ProbablyIrrigatedParcel` must be qualified by season and procedure.

### CQ16 — Explicit crop-change scenarios

**Question.** For a specified crop substitution, area and period, which locations have
sufficient evidence to simulate changes in irrigation demand, abstraction and return
flow affecting U, and how do their modelled head responses rank under stated assumptions?

- **Inputs:** baseline and alternative crop/area/management, S, U, period/horizon,
  climate, water-source shares, demand/return-flow assumptions, model run and uncertainty
  variants. Specify whether ranking is by total effect, effect per hectare, head
  increase at selected wells or another declared metric.
- **Outputs:** eligible and ineligible areas with reasons; baseline/scenario forcing
  changes by source/pathway, head changes at named wells/times, scenario/model IDs,
  uncertainty or sensitivity range, ranking and missing/unsupported assumptions.
- **Meaning:** the ontology identifies relevant entities and assumptions; an external
  calculation/model supplies impacts. A lower crop water requirement does not alone
  determine a groundwater benefit: reduced abstraction and reduced irrigation return
  flow can act in opposite directions. Estimated net effects depend on the water
  source, management and response model. This is a conditional demonstration, not
  an optimal land-use recommendation or a validated real-world intervention effect.
- **Evidence/readiness:** CQ2, CQ4–CQ8, CQ12 and CQ15 where irrigation status is used,
  plus a trained model. Do not require a heuristic irrigation label when independent
  service/irrigation evidence exists. Today this is a schema/test-fixture requirement;
  no numerical ranking is defensible yet.
- **Acceptance:** a synthetic no-change scenario gives zero forcing changes and zero
  deterministic model difference within tolerance. A surface-supplied parcel does not
  automatically reduce groundwater pumping. If source shares are unknown, report
  explicit alternative scenarios or withhold a single ranking. Return-flow effects
  remain separate, and unsupported extrapolations are labelled.
- **Ontology needs / dependencies:** scenario, intervention, baseline, assumption,
  model execution/result and comparison; scenario facts remain distinct from observed
  facts and cannot feed training as observations.

## 5. Coverage of the ontology and research objectives

These are conceptual modules, not a commitment to one file or class per row.
A class/property/axiom must serve a CQ or the shared identity, evidence and validation
requirements; the design is not limited to reusing the present table structure.

| Knowledge module | Questions | Required distinction / project purpose |
|---|---|---|
| Identity and observations | All, especially 1, 10, 12–15 | Physical entity vs source record vs dated observation; units, quality and series access |
| Hydrogeological structure | 1, 3, 4, 11, 13, 14 | Local geology vs monitored interval vs hydraulic conditions; RQ1 graph/features |
| Abstraction and supply | 2, 5, 6, 12 | Candidate connection vs accepted path; withdrawal vs consumption/return flow; Pliocene framing |
| Land use and alignment | 7, 15, 16 | Crop code vs mapped concept vs dated land use vs irrigation; subject SO1 |
| Processes and constraints | 4–8, 14 | Supported mechanisms and explicit assumptions vs universal causal axioms; RQ2 / SO3 |
| Remote-sensing enrichment | 15 | Observations vs heuristic inference vs independent validation; SO2 |
| Results and explanations | 8–10, 12, 13 | Model contribution vs real-world cause; SGI vs legal restriction; RQ3/RQ4 / SO4 |
| Scenario and dashboard | 9, 10, 12, 16 | Observed, inferred and hypothetical results; missing-evidence reporting; SO5 |
| Provenance and transfer | All | Versioned source/method/alignment assertions; reviewed literature rules in CQ8; reusable core with site-specific codes/rules |

No CQ establishes model accuracy or causal correctness by itself. RQ1–RQ4 still require
the experiments in the analysis plan. The KG/pandas edge-equivalence check attributes
accuracy gains to the encoded knowledge and traceability/consistency benefits to its
ontology representation.

## 6. Acceptance and implementation plan

### Test design

For each CQ, create one or more queries in `tests/cq/` after the vocabulary is settled.
Retain IDs CQ1–CQ16; name subqueries by purpose (e.g. CQ2 candidates/policy selection).
Each test records parameters, expected schema/rows, units, numeric tolerance,
source/rule versions and the inference/materialisation regime. Do not leave it unclear
whether a query tests asserted facts, reasoner entailments or SHACL-AF rule outputs.

Use three complementary checks:

1. **Small synthetic fixtures:** hand-check positive answers, missing evidence,
   conflicting evidence and prohibited inferences. The cases above are requirements
   for fixtures, not claims of executed tests.
2. **Data-backed regression:** compute expected results independently from frozen source
   tables/geometries using pandas/GeoPandas. Do not derive the oracle from the same RDF
   exporter or reuse a historical example number without its filters and version.
3. **Semantic and pipeline checks:** reasoner consistency, SHACL integrity and
   query/export equivalence. Time-series summaries and predictions additionally need
   their external calculation checks; agreement between two query engines cannot
   validate a physical hypothesis.

Every CQ's fixture suite must pass, including missing-data cases for conditional
extensions. Report **data-backed** coverage separately: all MUST questions require
working queries and representative real-data checks; each SHOULD/COULD gap is recorded
with missing evidence and implementation status. Returning unknown everywhere is not
completion of the core. CQ16 can pass representation fixtures in Phase 3 while its
numerical demonstration remains in Phase 4/5. Data-dependent omissions are visible
review decisions, never silently dropped questions.

### Work order and remaining decisions

| Order | Work | Completion evidence |
|---|---|---|
| 1 | Identity/observations and qualified geology: CQ1, CQ3, CQ11, CQ14 | Source identities retained; no depth/confinement shortcuts |
| 2 | Pump evidence and accounting: CQ2, CQ12 | Resolution-aware candidates; declared-volume reconciliation and unknown coverage |
| 3 | Forcing and land-use context: CQ4, CQ5, CQ7 | Reproducible spatial weights; dated crop mappings; proxy status explicit |
| 4 | Conditional pathways and explanations: CQ8, CQ10, CQ13 | Path/policy checks; model-result/summary contracts; negative fixtures |
| 5 | Satellite objective: CQ15 | Qualified parcel-season rule plus appropriate independent validation, or explicit heuristic status |
| 6 | Conditional extensions: CQ6, CQ9, CQ16 | Missing-evidence behaviour tested; real answers enabled only when inputs exist |

Before freezing the ontology, record the vocabulary mappings, attribution/export policy,
spatial tolerances and aggregation rules, source snapshots, demand/irrigation methods,
and every outstanding data gap. The approved architecture and main research scope stay
in place; the [ontology design](ontology_design.md) must implement these distinctions.
