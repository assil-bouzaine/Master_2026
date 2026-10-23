# Competency questions (Phase 3, step 1): draft for review

Draft of 2026-10-23, revised the same day after the project review
(`docs/review_2026-10-23.md` §4.3, which lists the corrections). It is for Assil and then the
supervisor (Gate 3).

The list starts from the ten questions of the critical review (`docs/feedback.md` §7.1),
checks each one against dataset v3, and adds the subject's objectives that were missing
(CQ15, CQ16). Every example answer was computed from the v3 tables on 2026-10-23.

## What competency questions are, and how we use them

A competency question (CQ) is a question the ontology and its knowledge graph must be able to
answer. Together, the CQs are the ontology's requirements (Grüninger & Fox 1995,
doi:10.1007/978-0-387-34847-6_3). We use them in two ways:

1. **Scope.** A class or relation enters the ontology only if a CQ needs it. Everything else is
   future work. This keeps Phase 3 inside its time-box.
2. **Tests.** Each CQ becomes a SPARQL query in `tests/`. Its expected answer is computed
   separately from the parquet tables (an "oracle"), and the test passes when both agree.
   Phase 3 is done when every CQ test passes (`docs/roadmap.md`, Phase 3). Wiśniewski et al.
   2019 (doi:10.1016/j.websem.2019.100534) analyse how CQs are written as SPARQL queries.

Every CQ must feed at least one of these:
- **G**: the model's graph (node and edge types exported by SPARQL → PyG `HeteroData`)
- **F**: a model input or feature
- **C**: a constraint (the sign of a response)
- **E**: the explanations (templates and their checks)
- **V**: validation (SHACL shapes and rules)
- **R**: the research framing (the Pliocene conflict, or canal-return recharge)
- **S**: a subject objective that would otherwise be missing (`Documents/sujet.docx`)

Priorities:
- **MUST**: the model cannot be built without it.
- **SHOULD**: needed for the explanations, the features, the framing or the subject.
- **COULD**: needs data we do not have yet.

"Terms" lists candidate vocabulary. It is confirmed in step 2 (reuse), following the review
(§4.1):
- GWML2 has **no official OWL**. Its class IRIs come from the OWL rendering in SAWGraph's water
  ontology (`gwml2:` = `http://gwml2.org/def/gwml2#`).
- SWEET (`realmHydro`) and HyFO are alignment targets.
- Water uses are ours: WHOW-KG has no abstraction module.

Two example wells are used throughout:
- **W1** = `10964X0119/NYLS-1` (Ponteilla). Pliocene multilayer `671AA00`, investigation depth
  97 m.
- **W2** = `10906X0039/C2-1` (Millas). Recent alluvium of the Têt `718BP02`, investigation
  depth 9 m. It is nested above C2-2.

## Summary

| CQ | Question | Feeds | Priority | Data now |
|---|---|---|---|---|
| CQ1 | Which aquifer unit and groundwater body does well W monitor, at what depth, and what is the local stack? | G F | MUST | yes |
| CQ2 | Which abstraction points pump from the unit of W, at what distance, for which use, with what evidence and confidence? | G F C V R | MUST | partly: needs an attribution step |
| CQ3 | Which units overlie unit U, and what kind of unit lies between them? | G F | MUST | yes |
| CQ4 | Where does unit U outcrop (its direct recharge zone), and which weather cells cover it? | F E | SHOULD | yes |
| CQ5 | Which rivers and gauges are connected to unit U? | G F C | SHOULD | yes (name rule); spatial rule to add |
| CQ6 | Which canal command areas lie over unit U, and which river intake feeds them? | G F C R | COULD | no command-area polygons yet |
| CQ7 | Which land-use classes with high irrigation demand lie near W in year y, and over how many hectares? | F E R | SHOULD | parcels yes; demand rule to source |
| CQ8 | Which drivers can affect the head of W, through which entities, and with which sign? | C G E | MUST | derived from CQ1–CQ6 |
| CQ9 | Which water-restriction level applied around W in week t? | E | COULD | levels yes; zone polygons no |
| CQ10 | Which entities does an explanation of W name, do they exist and connect to W, and does the stated sign match the polarity? | E V | SHOULD | a test on the KG |
| CQ11 | Which wells monitor the same unit within 5 km of W, and at what depth difference? | G | MUST | yes |
| CQ12 | How much water was abstracted from unit U in year y, by use? | R E F | MUST | after CQ2 |
| CQ13 | Which wells sit at the same site or within 5 km at different depths, and how often is the shallow head above the deep one? | E V G | SHOULD | yes |
| CQ14 | Is W in an outcropping (unconfined) or a covered (confined) part of its unit? | F C E | SHOULD | yes |
| CQ15 | Which parcels were probably irrigated in year y, by a rule on satellite data, and do they lie in a canal area or near a groundwater abstraction point? | F E S | SHOULD | rule to build (Earth Engine) |
| CQ16 | Where would a change to a less thirsty crop most change the inputs that reach unit U? | E S | COULD | needs the trained model |

## The questions

### CQ1: unit, groundwater body, depth and stack of a well (MUST)
- **Question.** Which aquifer unit and which WFD groundwater body does well W monitor, at what
  depth, and what is the vertical stack of units at W?
- **Why.** Node type and attributes of every piezometer (G, F). The review found that BD LISA's
  unit alone cannot tell the 31 Pliocene wells apart, so depth is added below the unit.
  - The pre-check supports the **continuous depth difference** (QAP p = 0.002).
  - It does **not** support fixed depth classes (p = 0.52), so depth stays a number.
  - The groundwater body links each well to water management (subject, decision makers).
- **Data.** `wells.parquet`:
  - `code_bdlisa` from Hub'Eau
  - `profondeur_investigation`: the **investigation depth** of the borehole, not the screened
    interval; screens exist only in the BSS logs
  - `stack_str` and `pos_in_stack` (Step 6b)
  - `codes_masse_eau_edl` (in `data/interim/piezo_stations.parquet`)
- **Terms.**
  - `gwml2:GW_Well` (and `gwml2:GW_MonitoringSite`)
  - `gwml2:GW_AquiferUnit`
  - `lulcw:monitors` (sub-property of `hyfo:tapsAquifer`)
  - `lulcw:investigationDepth` (metres)
  - `lulcw:inGroundwaterBody`
  - the BD LISA code and BSS id as identifiers
- **Example.**
  - W1 → `671AA00` "Sables et argiles pliocènes du Roussillon", body `DG243` "Multicouche
    pliocène du Roussillon", 97 m. The Pliocene crops out at W1 (one-unit stack).
  - W2 → `718BP02` "Alluvions récentes de la Têt", 9 m; stack `718BP02 > 671AA00`.
- **Open.** `760AE09` (1 well) is missing from the Occitanie BD LISA extract.

### CQ2: abstraction points that pump from the unit of W (MUST, top priority)
- **Question.** Which abstraction points pump from the unit of W (and from which depth range)?
  At what distance, for which use, and on what evidence and with what confidence?
- **Why.** This is the information every baseline lacks (CLAUDE.md §7, priority).
  - G: pump → unit edges
  - F: pumping input per unit
  - C: the "decreases head" influence
  - V: every link carries its provenance and a confidence (review §7.3)
  - R: drinking water against irrigation on the Pliocene
- **Data.**
  - `pumping_points.parquet`: 3,055 points, of which 2,137 are groundwater and only **240
    have a BSS code**.
  - `pumping_weekly.parquet`: uses irrigation, drinking water, canals, industry, energy.
  - Evidence, from strongest to weakest (sources checked on 2026-10-23, `data/README.md`):
    1. **confident:** the BSS code → the ADES quality station's BD LISA entity. Found for
       **211 points** (`src/ingest/hubeau_qualite_stations.py`), 125 of them with the
       investigation depth.
    2. **probable or possible (measured):** the BNPE flag `nappe_accompagnement`
       (a river-connected aquifer) together with the BD LISA stack at the point.
       Measured on the 130 distinct recorded boreholes (task 12.3, 2026-10-23,
       `src/kg/pump_attribution.py`):
       - True → the alluvial unit at or within 1 km of the point: right group 95 %
         (18 of 19), right entity 63 %.
       - False **and** the Pliocene under the point → Pliocene: 92 % (36 of 39; 82 %
         against the raw record).
       - False alone is not a rule: among the coded points of the plain it means Pliocene
         in only 53 of 112 cases. (The earlier reading "50 of 53 Pliocene points are
         False" was a recall, not a precision.)
       - The recorded boreholes are drinking-water and industry wells only, so
         "probable" holds for those uses; irrigation boreholes stay "possible".
       - In the plain: 882 True, 539 False, 469 empty (groundwater ouvrages of the
         dataset). The Sandre definition of the flag is still to confirm.
    3. **possible:** the BD LISA stack at the point holds a single unit; a dug well
       ("PUITS") with alluvium at the point.
    4. **The record is checked too:** a "recent alluvium" record deeper than 50 m above
       the Pliocene (4 boreholes, 96–130 m) is attributed to the Pliocene, with the
       recorded unit kept as a "possible" alternative.
  - **Coverage** of the plain's declared groundwater volume 2012–2024: confident 27 %,
    probable 45 % (drinking water), possible 21 % (mostly irrigation), unknown 7 %.
- **Terms.**
  - `lulcw:pumpsFrom` (sub-property of `hyfo:tapsAquifer`)
  - `lulcw:hasUse` (our SKOS scheme of the BNPE uses)
  - `prov:wasDerivedFrom` for the evidence
  - `lulcw:confidence` (SKOS: confident / probable / possible)
- **Example (groundwater points within 5 km, volumes 2012–2023 in dataset v3).**
  - W1: 148 points, **4** with a BSS code; 129 irrigation, 10 drinking water, 6 industry,
    3 mixed. Drinking water 17.4 Mm³, irrigation 18.2 Mm³, industry 0.7 Mm³.
  - W2: 130 points, 7 with a BSS code. Drinking water **110.4 Mm³**, irrigation 16.9 Mm³.
    Whether that drinking water comes from the Têt alluvium or from the Pliocene below is
    exactly what CQ2 must answer.
- **Open.**
  - The 211 coded points are mostly drinking-water boreholes, so the flag's accuracy on
    irrigation boreholes may differ. Report it as measured, not assumed.
  - Main runs use confident links only (or confident + probable, decided on the twin); a
    sensitivity run uses all links (review §7.3).

### CQ3: units above unit U (MUST)
- **Question.** Which units overlie unit U, and what kind of unit lies between them: an
  aquifer, an aquifer system or a confining bed?
- **Why.** `overlies` edges (G) and unit attributes (F). The edges carry no sign: the Step 6b
  pair check rejected a head-ordering rule.
- **Data.** `data/interim/bdlisa_overlies_plain.csv` (26 pairs in the plain) and
  `bdlisa_entities_plain.csv` (`nature`, `theme`, `milieu`).
- **Terms.**
  - `lulcw:overlies`: **our own**. GWML2 has no such relation; it models a multilayer as an
    aquifer system of aquifers and confining beds (`gwml2:GW_AquiferSystem`,
    `gwml2:gwAquiferSystemPart`).
  - `lulcw:hasBdlisaNature` (the BD LISA `natureeh` codes as a SKOS scheme)
  - the hydraulic type (`gwml2:GW_Aquifer` / `GW_AquiferSystem`; SWEET `ConfinedAquifer`,
    `UnconfinedAquifer`, `Aquitard`), set by a written mapping rule, not by `natureeh` alone
- **Example.**
  - Nine units overlie `671AA00`:
    - recent alluvium of the Agly, Têt, Réart and Tech (`718BP01`–`04`)
    - ancient alluvium (`671AB01`–`04`)
    - `718BG49`
  - `671AA00` overlies the Corbières karst `681AM00` over 141 km².
  - BD LISA labels `671AA00` a "semi-permeable unit": its level-3 entity is missing and the
    level-2 name is used. Hydraulically it is the plain's main aquifer system.
- **Open.** Drop contacts below a minimum area? Some pairs touch over less than 0.01 km².

### CQ4: outcrop and recharge zone of unit U (SHOULD)
- **Question.** Where does unit U crop out (its direct recharge zone), and which SAFRAN cells
  cover it, with what area share?
- **Why.** A recharge input averaged over the outcrop (F; review §3.5), and explanations such
  as "rain on the Pliocene outcrop" (E).
- **Data.** BD LISA polygons at order 1 (outcrop); the SAFRAN grid.
- **Terms.** GeoSPARQL (`geo:hasGeometry`, `geo:sfIntersects`); `lulcw:outcropOf`.
- **Example.** `671AA00` crops out over 288.9 km² of its 902.3 km² under the plain (32 %).
  Alluvium covers the rest.

### CQ5: rivers connected to unit U (SHOULD)
- **Question.** Which rivers, and which of their gauges, are connected to unit U?
- **Why.**
  - G: river nodes linked to alluvium wells
  - F: the river inputs of dataset v3
  - C: river recharge, only where the exchange direction is documented
- **Data.**
  - BD LISA alluvium units are named after their river.
  - `gauges.parquet`: 45 gauges, of which 8 are on the Têt, 7 on the Tech, 6 on the Agly
    and 3 on the Réart.
  - A river network (HY_Features; BD TOPAGE if needed) for a spatial rule.
- **Terms.** HY_Features river and water body; `lulcw:connectedTo`; `lulcw:rechargesFrom`.
- **Example.** `718BP02` ↔ la Têt, with 8 gauges (e.g. Ille-sur-Têt [T6], Perpignan [Pont
  Sauvy]). Likewise `718BP01` ↔ l'Agly, `718BP03` ↔ le Réart, `718BP04` ↔ le Tech.
- **Open.** Name rule or spatial rule (river line crossing the outcrop)? Gaining or losing
  reaches are not known, so the sign of the exchange may vary.

### CQ6: canal command areas over unit U (COULD)
- **Question.** Which canal command areas lie over unit U, and which river intake feeds them?
- **Why.**
  - G, F: canal input routed only to the units under irrigated land (review §3.4)
  - C: canal return flow raises the alluvium head
  - R: canal-return recharge framing
  - S: the LULC side of the causal chain
- **Data.** BNPE canal intakes (use "canals"). **No command-area polygons yet** (ASA canal
  perimeters: a source still has to be found).
- **Example.** Today the dataset has one plain-wide canal node. Step 9 found that the canal
  input helps the alluvium wells only.

### CQ7: land use with high irrigation demand near W (SHOULD)
- **Question.** Which land-use classes with high irrigation demand lie within 3 km of W (or on
  the outcrop of its unit) in year y, and over how many hectares?
- **Why.** Land-use features (F), explanations (E), framing (R).
- **Data.**
  - RPG 2016 and 2023 parcels (`CODE_GROUP`, centroid rule).
  - An irrigation-demand rule per crop group, which still needs a citable source.
- **Terms.**
  - HILUCS land use and AGROVOC crops
  - `lulcw:irrigationDemand` (SKOS: high / low)
  - the RPG year as the observation time (SOSA, OWL-Time)
  - a SHACL-AF rule deriving `lulcw:HighIrrigationDemandZone`
- **Example (RPG 2023, within 3 km).**
  - W1: 638 parcels, 1,093 ha: vines 485 ha, fodder 112, miscellaneous 109, set-aside 88.
  - W2: 1,101 parcels, 1,219 ha: **orchards 678 ha**, summer pasture and heath 156,
    vines 148, vegetables and flowers 52, olives 41.
- **Open.** About 84 % of the plain's irrigation is surface water (Step 6a). Land use near W
  therefore says more about canal water than about pumping.

### CQ8: drivers of the head of W and their signs (MUST)
- **Question.** Which drivers can affect the head of W, through which entities, and with which
  sign?
- **Why.**
  - C: sign constraints (RQ2)
  - the driver contributions that serve as RQ3's concepts (review §5.3)
  - E: explanations (RQ4)
  - G: edge types
- **Data.** The `lulcw:` causal axioms, applied to the links of CQ1–CQ6.
- **Terms.**
  - **Class level:** "an abstraction decreases the head of the unit it pumps from".
  - **Instance level:** `lulcw:Influence` nodes (W3C n-ary relation pattern) carrying the
    source, the target, the sign, the distance, the confidence and the evidence. They are
    derived by SHACL-AF SPARQL rules, because OWL property chains cannot test a distance.
  - `lulcw:DriverGroup` (e.g. "summer demand").
- **Example.**
  - W2 (Têt alluvium):
    - rain on the outcrop (+)
    - ETP (−)
    - pumping from `718BP02` within d (−)
    - the Têt (+, recharge)
    - canal return flow (+)
  - W1 (Pliocene): rain on the `671AA00` outcrop (+), ETP (−), pumping from `671AA00` at a
    similar depth (−).
  - Within a year, pumping is spread with the climatic deficit (r = 0.92–0.97). Explanations
    therefore name the group "summer demand", not pumping alone (`docs/analysis_plan.md` §8).
- **Open.** The influence distance d (the baselines use 3 km and the Taccari graph 10 km).

### CQ9: restriction level around W in week t (COULD)
- **Question.** Which water-restriction level applied around W in week t?
- **Why.** Context for the explanations only (E), e.g. "restrictions were at 'crise'".
  - **Not a model input.** Groundwater-zone orders would leak the target.
  - The surface-water orders only classify the restricted years for the imputation (step 12a
    note §2; analysis plan).
- **Data.**
  - VigiEau orders: `restrictions_weekly.parquet`, surface-water zones, level 0 none,
    1 vigilance, 2 alerte, 3 alerte renforcée, 4 crise.
  - Zone polygons are **not** in the dataset.
  - Zone names change across years: 21 names.
- **Example.** The "Têt aval" zones reached level 3 in 2022 and level 4 (crise) in 2023, 2024
  and 2025.

### CQ10: checking an explanation against the graph (SHOULD)
- **Question.** Which entities does an explanation of W at week t name? Do they exist, are they
  connected to W, and does the stated sign match the polarity?
- **Why.** The template tests of RQ4 (E, V; review §5.4): entity existence and sign
  consistency.
- **Terms.** The SGI drought classes as a SKOS scheme, with their thresholds (Bloomfield &
  Marchant 2013, doi:10.5194/hess-17-4769-2013), so that templates can name a class ("severe
  drought").
- **Example.** The sentence "In summer 2023, pumping from the Pliocene within 5 km lowered W1"
  passes only if:
  - W1, `671AA00` and the named abstraction points exist in the graph;
  - each named point has a confident `pumpsFrom` link to `671AA00`;
  - the influence has the sign "decreases".

  Because of CQ8's driver group, the template would say "summer demand" unless the claim
  rests on between-year variation.
- This is a test run on the knowledge graph, not a data question.

### CQ11: same-unit neighbours of W (MUST)
- **Question.** Which wells monitor the same unit within 5 km of W, and at what depth
  difference?
- **Why.** Well–well edges (G). The knowledge-graph pre-check (`docs/kg_precheck.md`) found
  that, after removing the regional signal:
  - same unit and ≤ 5 km raises the anomaly correlation (median 0.32 against −0.01;
    QAP p = 0.048)
  - a larger depth difference lowers it (QAP p = 0.002)
- **Data.** `wells.parquet`.
- **Example.**
  - W1 has three same-unit neighbours 2.8 km away: PIEZOMETRE DEM'TER 1, 2 and 3, with
    investigation depths 15, 60 and 111 m. Only DEM'TER 3 (14 m deeper) is at a depth
    similar to W1's.
  - W2 has none in `718BP02`.
- **Open.** The |Δ depth| threshold for a "similar depth" edge, chosen on the training period.
  Fixed depth classes were not supported by the pre-check.

### CQ12: annual abstraction from unit U by use (MUST: the main framing)
- **Question.** How much water was abstracted from unit U in year y, by use?
- **Why.**
  - R: Pliocene, drinking water against agriculture: the subject's "conflits d'usage"
  - E: explanations
  - F: annual totals
- **Data.** Annual BNPE volumes in `pumping_weekly.parquet` (real 2024 snapshot; imputations
  flagged), routed to units by CQ2.
- **Terms.** SOSA observations (an annual volume, with the year as `sosa:phenomenonTime` in
  OWL-Time); uses as in CQ2; `lulcw:imputed` with the imputation rule.
- **Example.** Today only by resource type, not by unit: in the plain over 2012–2023,
  groundwater gave 475 Mm³ of drinking water and 144 Mm³ of irrigation (Step 6a). Per unit
  only after CQ2.

### CQ13: stacked and nested wells (SHOULD)
- **Question.** Which wells sit at the same site, or within 5 km, at different depths in
  superposed units? How often is the shallow head above the deep one?
- **Why.**
  - E: the real-world anchors of RQ3 (nested pairs)
  - V: the evidence behind "no head-ordering rule"
  - G: vertical well pairs
- **Data.** `data/interim/bdlisa_vertical_pairs.csv` (17 pairs, of which 2 are nested).
- **Example (W2, C2-1, 9 m).**
  - Nested with C2-2 (Pliocene, 108.55 m, 20 m away): the shallow head is above the deep one
    in 100 % of the weeks.
  - With BOIS (Pliocene, 60 m, 2.2 km): 0 %.

### CQ14: outcropping or covered (SHOULD)
- **Question.** Is W in an outcropping (unconfined) part of its unit, or a covered (confined)
  one, and is it sometimes artesian?
- **Why.**
  - F: where recharge reaches the well (local rain, or only the outcrop)
  - C: the expected lag and strength of the rain response
  - E: explanations ("a confined well responds to rain on the outcrop, not to local rain")
- **Data.** The stack position (`pos_in_stack`; 1 = the unit crops out at the well) and the
  artesian share (training period only, after the v3 leak fix).
- **Terms.** SWEET `ConfinedAquifer` / `UnconfinedAquifer`; a SHACL-AF rule deriving
  `lulcw:ConfinedSetting`.
- **Example.** W1 is at an outcrop of `671AA00` and never artesian. 4 Pliocene wells are
  sometimes artesian (Step 6b).

### CQ15: parcels probably irrigated, from satellite data (SHOULD; subject SO2)
- **Question.** Which parcels were probably irrigated in year y, by a rule on satellite data,
  and do they lie in a canal command area or near a groundwater abstraction point?
- **Why.**
  - S: the subject's "semantic enrichment of remote sensing". Its own example: NDVI high in
    summer AND soil moisture low → probable irrigation.
  - F, E: an irrigation feature that does not depend on BNPE declarations.
- **Data.** Sentinel-2 summer NDVI per RPG parcel (computed on Google Earth Engine) and the
  SAFRAN soil-wetness index. Check the rule against the RPG crops.
- **Terms.** `lulcw:ProbablyIrrigatedParcel`, derived by a SHACL-AF rule from two observations
  (SOSA); AGROVOC for the crop.
- **Example.** To build: none yet.

### CQ16: where a crop change would matter most (COULD; subject SO5)
- **Question.** Where would a change to a less thirsty crop most change the inputs that reach
  unit U (irrigation return flow, pumping)?
- **Why.** S: the subject's dashboard query. E: a scenario explanation. A demonstration, not a
  result of the paper.
- **Data.** CQ6, CQ7 and CQ15, plus the trained model's response functions. It is feasible
  for the alluvium if the main model has explicit responses (review §3).
- **Example.** To build after Phase 4.

## Left out on purpose (future work)

- Water quality (nitrate), socio-economics, Spain and Tunisia.
- A full geological model of the Pliocene layers, unless the Dem'Eaux layers become available
  (review §5.1). Until then, the investigation depth stands in for them.
- Weekly time series in the graph. Series stay in parquet. The graph holds the structure,
  annual volumes, land use per year, restriction events and derived concepts.

## Data work these questions ask for (before the KG build)

1. **CQ2:** attribute each groundwater abstraction point to a unit (BSS records, depth, name,
   stack), with provenance and a confidence level. The biggest item.
2. **CQ15:** summer NDVI per RPG parcel on Earth Engine, and the irrigation rule with its check
   against the RPG.
3. **CQ7:** an irrigation-demand rule per RPG crop group, with a citable source.
4. **CQ4:** outcrop polygons intersected with the SAFRAN cells (area weights).
5. **CQ6:** find a source for canal command areas, or drop CQ6.
6. **CQ9:** VigiEau zone polygons and a harmonised list of zone names, or drop CQ9.

## Next

1. Assil reviews this list: questions to add or drop, priorities, the open points.
2. Scope and framing decided on 2026-10-23 (`docs/supervisor_questions.md` §1). The
   Pliocene use conflict is the main story, so CQ12 is now MUST.
3. Step 2 (reuse): a term-by-term table following review §4.1 (SAWGraph's GWML2 rendering,
   HyFO, SWEET, HY_Features, SOSA, GeoSPARQL, HILUCS, AGROVOC, PROV-O, SKOS, OWL-Time),
   with `lulcw:` for the rest.
4. Step 3: write each CQ as a SPARQL query in `tests/`, with its oracle computed from the
   parquet tables.
