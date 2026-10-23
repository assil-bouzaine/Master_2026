# Ontology design (Phase 3, step 3.2): draft

**Status:** draft of 2026-10-23. The reuse targets were checked at their
sources the same day (`docs/review_2026-10-23.md` §4.1). The design follows
CLAUDE.md §3 and serves the competency questions in
`docs/competency_questions.md`.
- "checked" = the IRI was seen in the source on 2026-10-23.
- "to check" = confirm before writing Turtle (CLAUDE.md rule 12).

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
| `AbstractionPoint` | BNPE ouvrage (`code_ouvrage`) | groundwater points ⊑ `hyfo:WaterWell` when the name says FORAGE/PUITS; surface intakes: ours | 2, 12 |
| `AquiferUnit` | BD LISA level-3 entity in the plain | ⊑ `gwml2:GW_HydrogeoUnit` | 1, 3, 4 |
| `AlluvialAquifer` | recent and ancient alluvium (`718BP0x`, `671AB0x`) | ⊑ `AquiferUnit`, ⊑ `gwml2:GW_Aquifer`; closeMatch SWEET `UnconfinedAquifer` | 3, 5, 14 |
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
| `Influence` | n-ary causal link (§4.1) | ours | 8, 10 |
| `UnitAttribution` | n-ary "point P pumps from unit U" with its evidence (§4.3) | ours | 2 |
| `WellLink` | n-ary "wells A and B, same unit, distance, depth difference" | ours | 11, 13 |
| Derived by SHACL-AF | `ProbablyIrrigatedParcel`, `HighIrrigationDemandZone`, `ConfinedSetting` | ours | 15, 7, 14 |

SKOS concept schemes (ours unless stated):
- `WaterUse`: drinking water, irrigation, industry, energy, canals. Align
  with the Sandre usage nomenclature if it has URIs (to check).
- `Confidence`: confident / probable / possible.
- `Sign`: increases / decreases.
- `DriverGroup`: e.g. `SummerDemand`.
- `SGIClass`: thresholds copied from the code that computes SGI, never
  re-invented.
- `BdlisaNature`, `BdlisaTheme`, `BdlisaMilieu`: the BD LISA codes (CLAUDE.md
  §7b).

## 3. Properties

| `lulcw:` property | Domain → range | Reuse | CQ |
|---|---|---|---|
| `monitors` | Piezometer → AquiferUnit | ⊑ `hyfo:tapsAquifer` | 1 |
| `pumpsFrom` | AbstractionPoint → AquiferUnit | ⊑ `hyfo:tapsAquifer`; materialised only for confident attributions (§4.3) | 2 |
| `overlies` | AquiferUnit → AquiferUnit; direct contact in a BD LISA stack | ⊑ `lulcw:above` (transitive) | 3 |
| `inGroundwaterBody` | Piezometer → GroundwaterBody | — | 1 |
| `investigationDepth` | Piezometer → xsd:decimal (m) | Hub'Eau `profondeur_investigation`; **not** the screen depth | 1, 11 |
| `stackPosition` | Piezometer → xsd:integer (1 = outcrop) | — | 14 |
| `outcropOf` | geometry → AquiferUnit | with `geo:hasGeometry` | 4 |
| `connectedTo` | AquiferUnit ↔ River | — | 5 |
| `hasUse` | AbstractionPoint → WaterUse | — | 2, 12 |
| `confidence` | UnitAttribution / Influence → Confidence | — | 2, 8 |
| `source`, `target`, `sign`, `distanceKm`, `inDriverGroup` | Influence → … | — | 8 |
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

Class level, for documentation and the reasoner: an abstraction decreases
the head of the unit it pumps from. Instance level, derived by a SHACL-AF
SPARQL rule (same unit, distance ≤ d, confidence carried over):

```turtle
lulcwd:infl_pt123_wellX a lulcw:Influence ;
    lulcw:source        lulcwd:pt123 ;          # an abstraction point
    lulcw:target        lulcwd:wellX ;          # a piezometer
    lulcw:sign          lulcw:Decreases ;
    lulcw:distanceKm    1.3 ;
    lulcw:inDriverGroup lulcw:SummerDemand ;
    lulcw:confidence    lulcw:Probable ;
    prov:wasDerivedFrom lulcwd:rule_pumping_same_unit .
```

The export (3.8) turns each `Influence` into a typed edge with attributes.
The sign fixes the sign of the response function in the hybrid model.

### 4.2 Time: annual and dated facts as SOSA observations

```turtle
lulcwd:vol_pt123_2023 a sosa:Observation ;
    sosa:hasFeatureOfInterest lulcwd:pt123 ;
    sosa:observedProperty     lulcw:AnnualAbstractedVolume ;   # m³, stated in its definition
    sosa:hasSimpleResult      "1.0E5"^^xsd:double ;
    sosa:phenomenonTime [ a time:ProperInterval ;
        time:hasBeginning [ time:inXSDDate "2023-01-01"^^xsd:date ] ;
        time:hasEnd       [ time:inXSDDate "2023-12-31"^^xsd:date ] ] .
```

The same pattern serves land use per RPG year and summer NDVI per parcel.
Units: either stated in each property's definition, or QUDT (decide in
3.4).

### 4.3 Uncertain links: `UnitAttribution` with evidence

A pump → unit link is uncertain for most points (240 of 2,137 groundwater
points have a BSS code). Each candidate link is an `UnitAttribution` node
holding:
- the point and the unit
- the method: BSS record, depth rule, name rule, or stack
- `prov:wasDerivedFrom`
- `lulcw:confidence`

A rule then materialises `lulcw:pumpsFrom` for confident links only. That
keeps the simple queries simple and the main runs clean. The sensitivity
run uses every attribution.

### 4.4 Typing the BD LISA units (a written rule, not `natureeh`)

| BD LISA entity (plain) | `lulcw:` class |
|---|---|
| theme alluvial (`718BP0x`, `718BG49`) and ancient alluvium (`671AB0x`) | `AlluvialAquifer` |
| `671AA00` "Sables et argiles pliocènes du Roussillon" (labelled semi-permeable at level 3) | `MultilayerAquiferSystem` |
| milieu karstic (`681AM00`, `681AN02`, `699AB01`) | `KarstAquifer` |
| nature 7, impermeable (e.g. `679AB00`, `699AD01`) | `ConfiningUnit` |
| other units (fissured basement, folded series) | `AquiferUnit`, with their BD LISA attributes |

## 5. Quality gates (in `tests/`, on every ontology change)

1. All modules load (rdflib), and the imports resolve to local copies.
2. **Reasoner:** ROBOT `reason` (ELK, then HermiT) finds the ontology
   consistent with no unsatisfiable class; ROBOT `report` gives no ERROR.
3. **OOPS!** pitfall scan: no critical pitfall. It is a web service, so the
   ontology is sent to it; ours only.
4. **SHACL:**
   - every `UnitAttribution` and `Influence` has a source, a target, a
     confidence and `prov:wasDerivedFrom`
   - every piezometer has exactly one unit and one investigation depth
   - every term has French and English labels and a definition
5. **CQ tests:** all 16 (or the agreed subset) pass against their oracles.
6. **Alignment:** P/R/F1 recorded for each run against the gold sets.

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
