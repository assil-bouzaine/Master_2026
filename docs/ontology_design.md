# Ontology design (Phase 3, step 3.2): draft

**Status:** draft of 2026-10-23, revised 2026-10-24 to implement the stronger
[competency-question contract](competency_questions.md). This document specifies
requirements; it does not certify their implementation. The reuse targets were
checked at their sources on 2026-10-23 (`docs/review_2026-10-23.md` §4.1). The design follows
CLAUDE.md §3 and serves the competency questions in
`docs/competency_questions.md`.
- "checked" = the IRI was seen in the source on 2026-10-23.
- "to check" = confirm before writing Turtle (CLAUDE.md rule 12).

The 2026-10-24 revision separates reported facts, qualified hypotheses and
model results. In particular, geological cover is not confinement, spatial
association is not hydraulic connection, and confidence is not a calibrated
probability. See the [review note](notes/step12c_competency_review.md).

## 1. Namespaces

| Prefix | Namespace | Role | Status |
|---|---|---|---|
| `lulcw:` | to decide in 3.4: `https://w3id.org/lulcw#` if a w3id redirect is accepted, else a GitHub Pages IRI | our bridging module | ours |
| `lulcwd:` | same base + `data/` | instances of the knowledge graph | ours |
| `gwml2:` | `http://gwml2.org/def/gwml2#` | GWML2 classes, in the OWL rendering of SAWGraph's water ontology v1.0 (`http://purl.org/spatialai/spatial/water-full`) | checked; **licence not stated**: keep local copies of the terms we use, with attribution |
| `hyfo:` | `http://hyfo.spatialai.org/v1/hyfo#` | HyFO | checked (declared in the SAWGraph ontology) |
| SWEET `realmHydro` | `http://sweetontology.net/realmHydro/` | Aquifer, ConfinedAquifer, UnconfinedAquifer, WaterTable, Aquitard | checked (v3.6.0, CC0) |
| SWEET `matrWater` | `http://sweetontology.net/matrWater/` | Groundwater | checked (used by `realmHydro`) |
| `sosa:` | `http://www.w3.org/ns/sosa/` | observations (annual volumes, land use per year, NDVI) | W3C Recommendation |
| `time:` | `http://www.w3.org/2006/time#` | phenomenon time | W3C Recommendation |
| `prov:` | `http://www.w3.org/ns/prov#` | evidence of derived links | W3C Recommendation |
| `skos:` | `http://www.w3.org/2004/02/skos/core#` | code lists, alignments | W3C Recommendation |
| `geo:` | `http://www.opengis.net/ont/geosparql#` | geometry, spatial relations | OGC GeoSPARQL 1.1 |
| `hyf:` | `https://www.opengis.net/def/schema/hy_features/hyf/` | rivers | prefix checked (SAWGraph); **class names to check** in the hyf Turtle |
| HILUCS | `http://inspire.ec.europa.eu/codelist/HILUCSValue` | land use | scheme checked (redirects to EU Vocabularies); **value IRIs to check** |
| `agrovoc:` | `http://aims.fao.org/aos/agrovoc/` | crops | concept IRIs found while building the gold set |

GWML2 itself has no official OWL (OGC 16-032r2 is UML + GML/XML; Brodaric et
al. 2018, doi:10.1007/s10040-018-1747-9). We therefore cite the standard and
use SAWGraph's OWL IRIs.

## 2. Classes

Rules for the relations:
- `rdfs:subClassOf` only where it is true for every instance.
- `skos:closeMatch` for alignments that are not strict. This avoids wrong
  inferences.

| `lulcw:` class | Meaning (source data) | Reuse / alignment | CQ |
|---|---|---|---|
| `Piezometer` | Hub'Eau monitoring well (`code_bss`, `bss_id`) | ⊑ `gwml2:GW_Well`; closeMatch `hyfo:WaterWell` | 1, 11, 13 |
| `AbstractionPoint` | BNPE reporting ouvrage (`code_ouvrage`); distinguish facility from individual intakes/boreholes when the source does | groundwater well subclass only with supporting type evidence; a name is a clue, not proof | 2, 12 |
| `AquiferUnit` | Working name for a BD LISA hydrogeological entity, including non-aquifer units | ⊑ `gwml2:GW_HydrogeoUnit`; do not make every instance a `GW_Aquifer` | 1, 3, 4 |
| `AlluvialAquifer` | recent and ancient alluvium (`718BP0x`, `671AB0x`) | ⊑ `AquiferUnit`, ⊑ `gwml2:GW_Aquifer`; local confinement assessed separately | 3, 5, 14 |
| `MultilayerAquiferSystem` | the Pliocene `671AA00` | ⊑ `AquiferUnit`, ⊑ `gwml2:GW_AquiferSystem` | 3, 14 |
| `KarstAquifer` | Corbières `681AM00` | ⊑ `AquiferUnit`, ⊑ `gwml2:GW_Aquifer`; closeMatch SWEET `Aquifer` | 3 |
| `ConfiningUnit` | BD LISA nature 7 (impermeable) | ⊑ `AquiferUnit`; closeMatch SWEET `Aquitard` (GWML2's confining bed is not a class in the rendering) | 3 |
| `GroundwaterBody` | WFD body (`codes_masse_eau_edl`, e.g. `DG243`) | ours; Sandre URI if it resolves (to check) | 1 |
| `River` / `Gauge` | Hub'Eau hydrometry | `River` ⊑ a `hyf:` water-body class (to check); `Gauge` ⊑ `sosa:Platform` | 5 |
| `WeatherCell` | SAFRAN 8 km cell | ⊑ `geo:Feature` | 4 |
| `Parcel` | RPG parcel | ⊑ `geo:Feature` | 7, 15 |
| `CropType` | RPG `CODE_CULTU` / `CODE_GROUP` as a SKOS scheme | `skos:exactMatch` / `closeMatch` → AGROVOC; broader → HILUCS | 7, 15 |
| `CanalCommandArea` | area served by a canal | ours | 6 |
| `RestrictionZone`, `RestrictionEvent` | VigiEau zone and dated order | ours | 9 |
| `Influence` | qualified mechanism/pathway and conditional response sign (§4.1) | ours; distinguish hypothesis from model constraint | 8, 10 |
| `UnitAttribution` | candidate monitoring or abstraction assignment, with role, evidence and resolution (§4.3) | ours; unknown assignment allowed | 1, 2 |
| `WellLink` | n-ary "wells A and B, same unit, distance, depth difference" | ours | 11, 13 |
| `StratigraphicRelation` | local direct adjacency or ordering, with supporting polygons and source release | ours; no global transitivity across different locations | 3 |
| `HydrogeologicalSetting` | local cover, confinement evidence and pressure-state summaries, kept separate | ours; SWEET confinement types only where supported | 14 |
| Dated assessments | irrigation likelihood, demand category, confinement assessment | observation/result pattern; qualify legacy `ProbablyIrrigatedParcel`, `HighIrrigationDemandZone`, `ConfinedSetting` by time, place, method and evidence | 7, 14, 15 |
| Result and scenario records | model run/result, contribution, explanation claim, scenario assumptions and comparison | reuse observations/provenance where appropriate; final local classes to minimise in 3.4 | 10, 16 |

Alignment notes in this table are requirements to verify, not published
equivalence axioms. SKOS mappings apply to code/concept schemes; they do not
establish OWL class equivalence. Keep the original code, mapping relation,
source/target versions, review status and unmapped concepts queryable (CQ7).

SKOS concept schemes (ours unless stated):
- `WaterUse`: drinking water, irrigation, industry, energy, canals. Align
  with the Sandre usage nomenclature if it has URIs (to check).
- `Confidence`: confident / probable / possible.
- Answer status: supported / partial / unknown / conflicting / not applicable,
  separate from confidence and from a model policy's acceptance decision.
- `Sign`: increases / decreases where justified; retain unknown or conditional
  applicability without manufacturing a signed constraint.
- `DriverGroup`: e.g. `SummerDemand`.
- `SGIClass`: thresholds copied from the code that computes SGI, never
  re-invented.
- `BdlisaNature`, `BdlisaTheme`, `BdlisaMilieu`: the BD LISA codes (CLAUDE.md
  §7b).

## 3. Properties

| `lulcw:` property | Domain → range | Reuse | CQ |
|---|---|---|---|
| `monitors` | Piezometer → AquiferUnit | ⊑ `hyfo:tapsAquifer` only after checking inherited domain/range; qualified assignments are authoritative | 1 |
| `pumpsFrom` | AbstractionPoint → AquiferUnit | check inherited types before using ⊑ `hyfo:tapsAquifer`; policy-scoped projection, confident + probable in main runs (§4.3) | 2 |
| `overlies` | AquiferUnit → AquiferUnit; some mapped direct contact | shortcut backed by `StratigraphicRelation`; indirect ordering derived only within compatible spatial contexts | 3 |
| `inGroundwaterBody` | Piezometer → GroundwaterBody | — | 1 |
| `investigationDepth` | Piezometer → xsd:decimal (m) | Hub'Eau `profondeur_investigation`; **not** the screen depth | 1, 11 |
| `stackPosition` | local unit assignment/setting → xsd:integer (1 = mapped outcrop) | retain stack/source context when a well has several candidates | 14 |
| `outcropOf` | mapped outcrop feature → AquiferUnit | the feature has geometry via `geo:hasGeometry` | 4 |
| `connectedTo` | qualified unit/reach hydraulic association | distinguish name/spatial association from evidence of exchange; include place/time | 5 |
| `hasUse` | dated abstraction observation → WaterUse | facility-level summaries are derived views, not permanent exclusive uses | 2, 12 |
| `confidence` | UnitAttribution / Influence → Confidence | — | 2, 8 |
| `source`, `target`, `sign`, `distanceKm`, `inDriverGroup` | Influence → … | add mechanism, variable, conditions, time scope and policy eligibility | 8 |
| `wellA`, `wellB`, `depthDifferenceM` (and `distanceKm`) | WellLink → … | — | 11, 13 |

Reused properties:
- `prov:wasDerivedFrom` (the evidence)
- `geo:hasGeometry`, `geo:asWKT`, `geo:sfIntersects`
- `sosa:hasFeatureOfInterest`, `sosa:observedProperty`,
  `sosa:hasSimpleResult`, `sosa:phenomenonTime`
- `time:hasBeginning`, `time:hasEnd`, `time:inXSDDate`
- `skos:prefLabel`, `skos:definition`, `skos:closeMatch`, `skos:exactMatch`,
  `skos:broader`

## 4. Patterns

Illustrations only: the values and IRIs are examples, not data.

### 4.1 Causal knowledge: class level plus `Influence` nodes

Class-level mechanism specifications document conditional physical knowledge;
they are not universal OWL statements that every nearby abstraction causes a
measured fall. A response sign refers to an increase in a named input with
specified conditions held fixed. OWL classifies entities; it does not prove
the derivative of a numerical model.

Instance-level `Influence` records cite the full evidence path. A SHACL-AF
rule may propose one using accepted assignments and a distance policy, but
spatial selection alone is not hydraulic evidence. The example below is a
candidate pumping influence. Its confidence alone does not establish all
conditions required for a signed constraint:

```turtle
lulcwd:infl_pt123_wellX a lulcw:Influence ;
    lulcw:source        lulcwd:pt123 ;          # an abstraction point
    lulcw:target        lulcwd:wellX ;          # a piezometer
    lulcw:sign          lulcw:Decreases ;
    lulcw:distanceKm    1.3 ;
    lulcw:inDriverGroup lulcw:SummerDemand ;
    lulcw:confidence    lulcw:Probable ;
    prov:wasDerivedFrom lulcwd:attribution_pt123,
                        lulcwd:monitoring_assignment_wellX ;
    prov:wasGeneratedBy lulcwd:rule_execution_123 .
```

The complete record must also carry the mechanism, variable, applicable
conditions/interval, rule version and eligibility decision from CQ8. The
export (3.8) selects eligible influences under a named policy and turns them
into typed edges with attributes. Unsigned structural edges remain possible.
The model enforces and tests response signs end to end. A response sign is
distinct from a signed contribution relative to a baseline (CQ10).

### 4.2 Time: annual and dated facts as SOSA observations

```turtle
lulcwd:vol_pt123_2023 a sosa:Observation ;
    sosa:hasFeatureOfInterest lulcwd:pt123 ;
    sosa:observedProperty     lulcw:AnnualAbstractedVolume ;   # m³, stated in its definition
    sosa:hasSimpleResult      "1.0E5"^^xsd:double ;
    lulcw:hasUse              lulcwd:drinkingWater ;
    sosa:phenomenonTime [ a time:ProperInterval ;
        time:hasBeginning [ time:inXSDDate "2023-01-01"^^xsd:date ] ;
        time:hasEnd       [ time:inXSDDate "2024-01-01"^^xsd:date ] ] .
```

This project's interval convention is start-inclusive/end-exclusive; OWL-Time
does not impose that application convention. Preserve source interval semantics
when converting. The same pattern serves land use per RPG year and summer NDVI
per parcel. Include source identity, quality, procedure, and available
result-production/publication/retrieval dates in complete records. Neither the
phenomenon year nor `sosa:resultTime` alone proves historical data availability.
Units: either stated in each property's definition, or QUDT (decide in
3.4).

Annual declarations and reconstructed/imputed estimates are distinct records.
CQ12 aggregates deduplicated declarations with an explicit attribution policy;
alternative candidates never duplicate the same declared volume. Weekly arrays
stay in parquet, with versioned series references and derived-summary records
in the KG. Statistical summaries and predictions are computed outside OWL.

### 4.3 Uncertain links: `UnitAttribution` with evidence

A pump → unit link is uncertain for most points (240 of 2,137 groundwater
points have a BSS code). Each candidate link is an `UnitAttribution` node
holding:
- the point and the unit (or no unit: an explicit "unknown")
- the rule: `record`, `record_depth`, `flag_true`, `flag_false`, `dug_well`,
  `single_unit` (`src/kg/pump_attribution.py`, task 12.3)
- its rank (1 = main candidate, 2 = alternative)
- `prov:wasDerivedFrom`
- `lulcw:confidence`, plus assessment resolution (group vs exact entity),
  evaluation sample/use, reference version and raw-record versus revised-record
  agreement. A measured rule precision is not an individual probability.
- validity/source dates and acceptance/conflict status. An explicit unknown
  assignment has no invented target; confidence and answer status are separate.

The existing implementation's threshold is group precision ≥ 0.80 on ≥ 10
recorded boreholes, with use applicability checked separately. It must not be
mistaken for exact-entity validation: the alluvial flag rule has 0.947 group
precision but 0.632 entity precision. The current single confidence column
therefore needs qualification during KG construction (CQ2), not blind copying.

Materialise `lulcw:pumpsFrom` in a named/versioned policy view: confident and
probable links for main runs (Assil's 2026-10-24 decision), confident-only and
all-link policies for sensitivity. Preserve the original records, all alternatives
and their assessment resolution outside that projection. Wider policies select
alternative assignments explicitly; they do not sum a facility's volume once for
every candidate. A monitoring assignment uses the same evidence pattern with a
distinct role and provenance.

Two limits are stated wherever these links are used:
- A BD LISA stack describes the geological arrangement under a point. It
  does not prove a hydraulic connection.
- Investigation depth is not screened depth.

### 4.4 Typing the BD LISA units (a written rule, not `natureeh`)

| BD LISA entity (plain) | `lulcw:` class |
|---|---|
| theme alluvial (`718BP0x`, `718BG49`) and ancient alluvium (`671AB0x`) | `AlluvialAquifer` |
| `671AA00` "Sables et argiles pliocènes du Roussillon" (labelled semi-permeable at level 3) | `MultilayerAquiferSystem` |
| milieu karstic (`681AM00`, `681AN02`, `699AB01`) | `KarstAquifer` |
| nature 7, impermeable (e.g. `679AB00`, `699AD01`) | `ConfiningUnit` |
| other units (fissured basement, folded series) | `AquiferUnit`, with their BD LISA attributes |

These broad geological types do not assign local confinement. For CQ14,
derive mapped cover from stack position; require separate local hydraulic
evidence for confinement. `pct_days_artesian` is a head-above-ground proxy
whose datum and training window must be recorded, not a universal aquifer type.

### 4.5 Spatial and seasonal assertions

Keep spatial witnesses for stratigraphic relations. A contact A–B in one
polygon and B–C in a disjoint polygon cannot entail a local A–C stack. Direct
contact, indirect ordering and hydraulic exchange remain different relations.
Record the CRS, geometry vintage, boundary tolerance, area denominator and
coverage for spatial summaries (CQ3–CQ7).

Irrigation likelihood and demand describe a parcel-season or dated assessment.
Do not give a parcel a timeless irrigation status from one summer's rule.
The same caution applies to local confinement and pressure conditions. For
CQ15, command-area membership and nearby pumps support source plausibility,
not parcel-year irrigation truth. Model/scenario results use distinct records
and never overwrite observed facts (CQ10/CQ16).

## 5. Quality gates (in `tests/`, on every ontology change)

1. All modules load (rdflib), and the imports resolve to local copies.
2. **Reasoner:** ROBOT `reason` (ELK, then HermiT) finds the ontology
   consistent with no unsatisfiable class; ROBOT `report` gives no ERROR.
3. **OOPS!** pitfall scan: no critical pitfall. It is a web service, so the
   ontology is sent to it; ours only.
4. **SHACL:**
   - every `UnitAttribution` has a source, role, evidence and assessment status;
     resolved candidates additionally have a target, confidence and resolution.
     Unknown assignments have an explicit reason, not a fictional unit.
   - every `Influence` has source/target, evidence path, mechanism, applicability
     and rule/policy provenance; a signed constraint additionally has a supported
     sign, variable and conditions. Missing targets cannot become model edges.
   - every piezometer and groundwater pump has at least one
     `UnitAttribution` (possibly "unknown"); several candidates are allowed.
     The investigation depth is optional, and a missing depth is reported.
     (Second review, 2026-10-23: forcing incomplete evidence into one answer
     creates false certainty.)
   - every term has French and English labels and a definition
5. **CQ tests:** fixture contracts for all 16 pass (including unknown/conflict
   cases). All MUST CQs also have representative data-backed regression checks;
   each SHOULD/COULD data gap is reported separately. A query returning unknown
   everywhere does not complete the core. Use one or more queries per CQ and
   declare the inference/rule regime. See the acceptance plan in
   [competency_questions.md](competency_questions.md#6-acceptance-and-implementation-plan).
6. **Alignment:** P/R/F1 recorded for each run against the gold sets.
7. **Equivalence test** (task 12.8): the edge list exported by SPARQL equals
   the one built by pandas rules from the same tables. The ontology is
   credited with traceability, consistency and reuse; accuracy gains belong
   to the knowledge it carries (analysis plan v2, §10).

`ProbablyIrrigatedParcel` (CQ15) is a heuristic unless it is checked against
independent irrigation evidence: agreement with RPG crops does not validate
irrigation (crop type and irrigation status are different variables). Canal
perimeters and nearby abstraction points are also not parcel-year truth labels;
aggregate census data validate only at their compatible aggregation scale.

## 6. Open points (decide in 3.4)

- The namespace: a w3id.org redirect needs a pull request from Assil's
  GitHub account; otherwise GitHub Pages.
- The SAWGraph licence: ask, or keep local copies of the terms with
  attribution.
- The `hyf:` class for rivers; the HILUCS value IRIs; the Sandre URIs (water
  uses, groundwater bodies).
- Units: QUDT or documented datatypes.
- The distance d for pump → well influences, and the |Δ depth| threshold for
  `WellLink` edges: chosen on the training period.
