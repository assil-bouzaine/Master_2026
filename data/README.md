# Data log

Every download is logged here: source, endpoint/URL, parameters, retrieval
date, row counts and file sizes. The data itself is gitignored; this file is
the only thing under `data/` that is committed. Anyone with the repo can
rebuild `data/` by running the ingest scripts in `src/ingest/`.

Folder convention:

| Folder | Content | Rule |
|---|---|---|
| `raw/` | untouched downloads | never edit by hand; scripts only add files |
| `interim/` | cleaned / filtered tables | can always be regenerated from `raw/` |
| `processed/` | model-ready datasets | can always be regenerated from `interim/` |

---

## Study-area definition

**Roussillon plain = bounding box, WGS84:**
- **lon 2.55–3.06 °E, lat 42.50–42.88 °N**
- Defined in `src/analysis/piezo_profile.py` as `PLAIN_BBOX`.

How the box was chosen. It was fixed from geography *before* looking at
which stations pass the filters:

| Edge | Coordinate | Where it falls |
|---|---|---|
| West | 2.55 °E | Têt valley entrance near Ille-sur-Têt, where the Pliocene basin pinches out |
| East | 3.06 °E | The coast. Excludes the rocky Côte Vermeille, e.g. Collioure at 3.08 °E |
| South | 42.50 °N | Foot of the Albères range |
| North | 42.88 °N | Salses lagoon / Corbières foothills, the limit with dept 11 (Aude) |

The box also captures six stations in the Corbières karst (BD LISA
`681AM00`) at the plain's northern margin, and one in `760AE09` (Aspres). Each
station keeps a `layer` column, so the "core" subset (Pliocene + alluvium
entities `671AA*`, `671AB*`, `718BP*`, 26 stations) can be selected at any
time. Once BD LISA polygons are available (Step 6b), a polygon-based extent
can replace the box.

---

## Pull log

| Date | Source | Endpoint / URL | Parameters | Output | Rows | Size |
|---|---|---|---|---|---|---|
| 2026-10-05 | Hub'Eau Piézométrie v1 (API 1.4.3) | `https://hubeau.eaufrance.fr/api/v1/niveaux_nappes/stations` | `code_departement=66`, `size=5000` | `raw/hubeau/stations_66.{json,parquet}` | 101 stations | 116 KB json / 26 KB parquet |
| 2026-10-05 | Hub'Eau Piézométrie v1 | `.../niveaux_nappes/chroniques` | `code_bss=<each station>`, `size=5000`, follow `next` | `raw/hubeau/chroniques/<code_bss>.parquet` (`/` → `_`) | 437,023 measurements, 101 files (7 empty) | 8.1 MB |

Script: `python -m src.ingest.hubeau_piezo` (rerun skips cached stations;
`--refresh` re-downloads). Derived tables come from
`python -m src.analysis.piezo_profile`, which writes to `data/interim/`:

| File | Content | Rows |
|---|---|---|
| `piezo_stations` | all stations | 101 |
| `piezo_working_set` | stations passing all filters | 33 |
| `piezo_series_window` | working-set series, 2016–2025 | 115,443 |

### RPG agricultural parcels (Step 5)

| Date | Source | Endpoint / URL | Parameters | Output | Rows | Size |
|---|---|---|---|---|---|---|
| 2026-10-05 | IGN Géoplateforme, Atom listing | `https://data.geopf.fr/telechargement/resource/RPG` | `page=1..35` (1 s pause, else HTTP 429) | (in memory) | 349 resources | n/a |
| 2026-10-05 | IGN Géoplateforme | `.../download/RPG/RPG_2-0__SHP_LAMB93_R76-2016_2016-01-01/<same>.7z` | region R76, edition 2016 | `raw/rpg/<name>.7z` + extracted folder | 1,526,641 parcels in Occitanie | 453 MB 7z / 1.2 GB extracted |
| 2026-10-05 | IGN Géoplateforme | `.../download/RPG/RPG_2-2__SHP_LAMB93_R76_2023-01-01/<same>.7z` | region R76, edition 2023; MD5 verified | `raw/rpg/<name>.7z` + extracted folder | n/a | 395 MB 7z / 827 MB extracted |
| 2026-10-05 | IGN Géoplateforme annexes | `https://data.geopf.fr/annexes/ressources/documentation/` | `REF_CULTURES_GROUPES_CULTURES_2023.csv` (cp1252), `_2024.csv` (utf-8), `REF_CULTURES_2023.csv`, `SE_RPG.pdf` | `raw/rpg/docs/` | 372 crop codes | 1.4 MB |

Notes:
- **No reference table for 2016.** The 2016 table returns 404. The 2023
  table lists every crop code since 2014, with its validity period.
- **Newer editions.** 2024 and 2025 editions exist (GeoPackage, RPG v4.0)
  but are not downloaded.
- **Shapefile structure.** Each edition's shapefile sits three folders deep
  inside the archive (found by recursive glob). Fields: `ID_PARCEL`,
  `SURF_PARC` (ha), `CODE_CULTU`, `CODE_GROUP`, `CULTURE_D1`, `CULTURE_D2`.

Scripts: `python -m src.ingest.rpg` (cached, resumable) and
`python -m src.analysis.rpg_profile`, which writes:

| File | Content | 2016 | 2023 |
|---|---|---|---|
| `interim/rpg_plain_<year>.parquet` | parcels in the plain bbox + 3 km | 27,271 | 32,795 |
| `interim/rpg_3km_<year>.parquet` | parcel centroid within 3 km of a working-set piezometer | 7,914 | 10,222 |
| `interim/rpg_3km_groups.csv` | share and hectares by `CODE_GROUP` | n/a | n/a |

### BNPE water abstraction (Step 6a)

| Date | Source | Endpoint / URL | Parameters | Output | Rows | Size |
|---|---|---|---|---|---|---|
| 2026-10-05 | Hub'Eau Prélèvements v1 (API 1.0.3) | `https://hubeau.eaufrance.fr/api/v1/prelevements/referentiel/points_prelevement` | `code_departement=66`, `size=2000`, follow `next` | `raw/hubeau_bnpe/points_prelevement_66.parquet` | 3,061 points (987 CONT, 2,074 SOUT) | 120 KB |
| 2026-10-05 | Hub'Eau Prélèvements v1 | `.../prelevements/chroniques` | `code_departement=66`, `size=2000` | `raw/hubeau_bnpe/chroniques_66.parquet` | 16,965 ouvrage×year×usage rows, 2012–2023 | 243 KB |

Notes:
- **Page size.** A first attempt with `size=5000` got the connection reset.
  Hub'Eau then refused every request for about 10 minutes. Use `size=2000`.
- **`code_bdlisa`** is null for all 3,061 points; never use it.
- **Facilities vs points.** Each ouvrage has exactly one point, hence one
  water source.
- **Coordinates.** Only the chroniques table has them (`longitude`,
  `latitude`).
- **Unmatched rows.** Two volume rows have an ouvrage absent from the points
  table; they are dropped.

Script: `python -m src.analysis.bnpe_profile` writes
`interim/bnpe_annual.csv` and `interim/bnpe_cumulative.csv`.

### BD LISA V3 aquifer entities (Step 6b)

| Date | Source | Endpoint / URL | Parameters | Output | Rows | Size |
|---|---|---|---|---|---|---|
| 2026-10-05 | BD LISA V3, Occitanie extract (manual download by Assil) | `https://bdlisa.eaufrance.fr` → Téléchargement | GeoPackage, region OCC | `raw/bdlisa/BDLISA_V3_OCC-gpkg.zip` → `BDLISA_V3_OCC-gpkg/BDLISA_V3.gpkg` | 1,475 level-3 polygons; 16,789 elementary polygons; 124,734 stack rows | 169 MB zip |

Notes:
- **Layers used:** `TME` (attributes for all levels), `POLYG_ELEMENTAIRES`
  (`codepoly`), `TABLE_PILE_ENTITES_NIV3` (`CodePoly`, `CodeEH`,
  `OrdRelatif`; 1 = top of the stack). Codes decoded with SANDRE
  nomenclatures (see `src/analysis/bdlisa_profile.py`).
- **Plain extent.** The same `PLAIN_BBOX` as the piezometers; 180 elementary
  polygons intersect it (3,104 km²).
- **Missing entity.** `760AE09` (station CARRIE) is not in the Occitanie
  extract. Its well sits in a `699AD01` (granite) polygon.

Script: `python -m src.analysis.bdlisa_profile` (re-run 2026-10-13) writes:

| File | Content | Rows |
|---|---|---|
| `interim/bdlisa_entities_plain.csv` | level-3 entities under the plain + decoded attributes, outcrop and total area | 30 |
| `interim/bdlisa_overlies_plain.csv` | direct `upper → lower` edges from the stacks, with polygon count and area | 26 |
| `interim/bdlisa_station_stacks.csv` | per working-set well: entity, stack under the well, position, % artesian days | 33 |
| `interim/bdlisa_vertical_pairs.csv` | shallow/deep well pairs ≤ 5 km + weekly head-ordering statistics | 17 |

### SAFRAN / SIM2 climate forcing (Step 8, Phase 1)

| Date | Source | Endpoint / URL | Parameters | Output | Rows | Size |
|---|---|---|---|---|---|---|
| 2026-10-13 | Météo-France SIM2 (SAFRAN-ISBA) daily, data.gouv.fr dataset `6569b27598256cc583c917a7` ("Données changement climatique - SIM quotidienne") | `https://meteofrance.s3.sbg.io.cloud.ovh.net/data/REF_CC/SIM/QUOT_SIM2_<year>.csv.gz` + `QUOT_SIM2_latest.csv.gz` | years 2005–2026; cells with lon 1.65–3.25, lat 42.30–43.00 (`DEPT_BBOX`); variables PRELIQ, PRENEI, T, ETP, EVAP, PE, SWI, DRAINC, RUNC | `raw/safran/sim2_66_<year>.parquet` (+ `.json` with server Last-Modified), `raw/safran/grid_cells_66.parquet` | 141 cells; 1,121,655 cell-days, 2005-01-01 .. 2026-10-12 | ~3.0 GB downloaded (≈ 137 MB per national year file, deleted after filtering); 8.6 MB kept |

Notes:
- **Approved by Assil** (2026-10-13) for the 2005–2026 period, above the 2 GB
  rule.
- **Grid:** 8 km SAFRAN cells; coordinates file
  `coordonnees_grille_safran_lambert-2-etendu.csv` (Lambert II étendu in hm,
  decimal commas).
- **Parameters:** see `raw/safran/sim-quotidienne-parametres-20260331.pdf`.
  - `ETP` = Penman-Monteith FAO-56
  - `PE` = effective rain
  - `DRAINC` = drainage below the root zone (a recharge proxy)
- **Updates:** the current year file is updated monthly. The script
  re-downloads a year only when the server's Last-Modified changes, and
  merges the rolling `latest` file into the current year.

### Hub'Eau hydrometry: river and canal flows (Step 8)

| Date | Source | Endpoint / URL | Parameters | Output | Rows | Size |
|---|---|---|---|---|---|---|
| 2026-10-13 | Hub'Eau Hydrométrie v2 | `https://hubeau.eaufrance.fr/api/v2/hydrometrie/referentiel/stations` | `code_departement=66`, `size=200` | `raw/hubeau_hydro/stations_66.parquet` | 105 stations | 14 KB |
| 2026-10-13 | Hub'Eau Hydrométrie v2 | `.../hydrometrie/obs_elab` | `code_entite=<station>`, `grandeur_hydro_elab=QmnJ` (daily mean flow, L/s), `date_debut_obs_elab=2005-01-01`, `size=5000`, follow `next` | `raw/hubeau_hydro/qmnj/<code_station>.parquet` | 72 stations open since 2005: 45 with data, 27 empty | 3.4 MB |

Notes:
- **Swapped coordinates:** two stations have lon/lat swapped in the
  referential (Y021401101, Y043642201); fixed on ingest.
- **Canals:** 6 canal stations are open since 2005, but only the "canal
  adducteur" (Y030521001) returns data, and only 9 weeks of it. **There is
  effectively no gauged canal flow in Hub'Eau.** The canal signal must come
  from the BNPE canal-intake volumes.
- **Slow API:** about 2,000 records per page at ~1 page/s. The full pull
  took about 40 min.

### Model-ready dataset v1 (Step 8)

Script: `python -m src.dataset.build` (2026-10-13) →
`data/processed/dataset_v1/` (5.6 MB). Loader:
`src.dataset.load.load_arrays()`.

| File | Content | Rows |
|---|---|---|
| `wells.parquet` | 47 plain wells (33 core = working set): attributes, BD LISA group and stack, nearest SAFRAN cell, leave-wells-out fold | 47 |
| `heads_weekly.parquet` | well × week (W-SUN): mean head, days observed, share "Non qualifié", monthly SGI, IPS class | 37,671 |
| `forcing_weekly.parquet` | SAFRAN cell × week (sums: rain, ETP, EVAP, PE, DRAINC, RUNC; means: T, SWI) | 160,176 |
| `gauges.parquet`, `rivers_weekly.parquet` | 45 gauges; weekly mean flow (m³/s) | 37,714 |
| `pumping_points.parquet`, `pumping_weekly.parquet` | 2,046 BNPE ouvrages within ~3 km of the plain box; weekly volumes (m³) by use | 817,595 |
| `splits.json`, `meta.json` | time splits, 5 stratified leave-wells-out folds, parameters | n/a |

**Assumptions** (all flagged and documented in the module docstring):
- **SGI reference:** the training period only.
- **IPS bounds:** standard-normal quantiles at 10/20/40/60/80/90 %, from the
  return periods in the BRGM/DREAL Rhône-Méditerranée bulletin table.
- **Weekly pumping:**
  - irrigation and canal intakes follow the April–October climatic deficit
    max(ETP − rain, 0)
  - other uses are spread uniformly
  - years after 2023 are imputed (mean 2020–2022, missing years count as
    zero, irrigation scaled by that year's deficit)
- **Excluded:** 5 plain stations with no measurement at all.

### BNPE snapshot of 2026-10-20 (Step 12a, dataset v3)

| Date | Source | Endpoint / URL | Parameters | Output | Rows | Size |
|---|---|---|---|---|---|---|
| 2026-10-20 | Hub'Eau Prélèvements v1 (API 1.0.3) | `.../prelevements/referentiel/points_prelevement` | `code_departement=66`, `size=2000`, follow `next` | `raw/hubeau_bnpe/2026-10-20/points_prelevement_66.parquet` | 3,184 points (was 3,061) | 124 KB |
| 2026-10-20 | Hub'Eau Prélèvements v1 | `.../prelevements/chroniques` | `code_departement=66`, `size=2000`, follow `next` | `raw/hubeau_bnpe/2026-10-20/chroniques_66.parquet` | 18,811 rows, 2012–**2024** (2024: 1,846 rows) | 258 KB |

Script: `python -m src.ingest.hubeau_bnpe --snapshot 2026-10-20`. The 2026-10-05 files
stay in the top folder for datasets v1/v2; a snapshot is never overwritten.

Notes (checked before writing any rule; `src/dataset/bnpe_v3.py`):
- **Revisions of 2012–2023 since 2026-10-05 are small**: 1.7 Mm³ of absolute change in
  total for the plain.
- **177 rows of 2024 have no usage code.** 163 of them are surface canal intakes
  (121.7 Mm³ in the département), so 2024 canals looked "missing" until the usage was
  restored from each ouvrage's other years. With it, the plain's canal intakes took
  76.5 Mm³ in 2024 (2023: 47.3; 2022: 96.0).
- **2023 canal drop is real**: the 28 intakes declared in both years took 0.54 × their
  2022 volume; 11 intakes did not declare in 2023.
- **2018 reporting break**: the 2017 → 2018 jump of groundwater irrigation is made
  entirely of 708 boreholes that first declare in 2018/2019; older declarants decline
  slowly.
- 2024 is about 90 % complete for groundwater uses (declared both years: drinking water
  174/191, irrigation 874/981).
- A one-off check pull of 2024 (same endpoint, `annee=2024`, 1,846 rows) was made into a
  scratch folder on the same day before the snapshot; it is superseded by the snapshot.

### VigiEau drought restriction orders (Step 12a)

| Date | Source | Endpoint / URL | Parameters | Output | Rows | Size |
|---|---|---|---|---|---|---|
| 2026-10-20 | data.gouv.fr "Donnée Sécheresse - VigiEau" (dataset `662a5e2cd71b24df5e9a0827`, Etalab 2.0) | resources "Arrêtés 2012" … "Arrêtés 2024" and "Arrêtés" (current) | none (national CSVs) | `raw/vigieau/arretes-<year>.csv`, `raw/vigieau/arretes.csv` | 78 orders for dept 66 (36 zone names, 438 surface / 329 groundwater zone rows) | 20 MB |

Script: `python -m src.ingest.vigieau` (cached) writes
`interim/vigieau_levels_daily_66.parquet`: day × alert zone, level 0–4 (0 none,
1 vigilance, 2 alerte, 3 alerte renforcée, 4 crise), 194,652 rows, 2012-01-01 → 2026-10-20.
When orders overlap, the one that starts last applies.

Notes:
- **Only surface-water zones may be used** (docs/analysis_plan.md §7). Groundwater
  zones ("nappes Roussillon" sectors) are triggered by piezometers of the aquifers we
  predict.
- Têt surface-water zones at **crise**, April–September: **145 days in 2023, 183 days
  (the whole season) in 2024**, 0 days in every other year 2012–2026. Used to classify
  restricted years for the imputation of unpublished surface-water volumes.
- Zone names and codes changed over the years (e.g. `76_66_7` "Têt aval" →
  `76_66_0005`); grouping by name ("Têt") covers all versions.

### Model-ready dataset v3 (Step 12a)

Script: `PFE_DATASET=v3 python -m src.dataset.build` (2026-10-20) →
`data/processed/dataset_v3/` (14 MB). Same wells (65, core 33), periods and folds as v2.

| Change from v2 | Why |
|---|---|
| BNPE snapshot 2026-10-20 (real 2024) and the rules of `src/dataset/bnpe_v3.py` | 2024 was imputed in v2; missing usage codes, the 2018 break and the consolidation lag are now handled explicitly |
| Rules 3–4 estimated per zone (plain / rest of the département) | mountain canals and the plain's Têt intakes are declared and restricted on different schedules |
| Irrigation weights sum to 1 in every complete year; the partial current year uses the observed deficit + the mean deficit of the weeks still to come | v2 scaled imputed totals by the year's climatic deficit (2026 canals were inflated by ~30 %) |
| `pct_days_artesian` from the training period only | v2 used the whole record: F3N4 went from 21.4 % to 0.8 %, its artesian days are in the 2026 recovery (leak through a static) |
| `restrictions_weekly.parquet`: weekly max level per surface-water alert zone | for analysis and explanations; not a model input |
| `pumping_points.zone` (plain / outside) | the canal input of the models is restricted to the plain (v2 took the whole département: 299 instead of 214 Mm³ in 2019) |

Model inputs added at feature level from v3 (`src/models/features.py`): log discharge of
the Têt at Perpignan, the Agly at Estagel, the Tech at Argelès and of the main-stem gauge
nearest to each well (+ 13/52-week means). Gaps ≤ 8 weeks interpolated, longer ones
filled with the gauge's training-period median for that week of year.

Plain volumes after the rules (Mm³/yr): groundwater drinking water 40.2 (2022) → 37.9
(2023) → 38.2 (2024); groundwater irrigation 15.8–19.7 in every year 2012–2026 (no 2018
step); canal intakes 95.1 (2022) → 52.7 (2023) → 84.7 (2024) → 104.0 (2025–26, imputed
as normal years).

### Hub'Eau groundwater-quality stations (Step 12, Phase 3: CQ2)

| Date | Source | Endpoint / URL | Parameters | Output | Rows | Size |
|---|---|---|---|---|---|---|
| 2026-10-23 | Hub'Eau *qualite_nappes* (ADES water points) | `https://hubeau.eaufrance.fr/api/v1/qualite_nappes/stations` | `num_departement=66`, `size=2000` (this endpoint ignores `code_departement`) | `raw/hubeau_qualite/stations_66.json`, `stations_66.parquet` | 1,094 stations (617 boreholes, 370 springs, 71 wells…); 1,046 with a BD LISA entity code | 2.7 MB JSON, 116 kB parquet |

Script: `python -m src.ingest.hubeau_qualite_stations` (cached; `--refresh` to download
again).

Why: BNPE abstraction points carry no aquifer unit, but **211 of the 235** BNPE points
with a BSS code are quality stations with a BD LISA entity (125 also give the
investigation depth). They are the direct evidence for CQ2 (`docs/competency_questions.md`).

Notes:
- `nom_caracteristique_aquifere` (free / confined) is "Inconnu" for 1,062 stations: not
  usable.
- Check on the 211 points against the BNPE flag `nappe_accompagnement` (river-connected
  aquifer):
  - alluvium-coded points are flagged True in 30 of 39 cases
  - Pliocene-coded points are flagged False in 50 of 53 cases
  - points flagged True are alluvium in 30 of 33 cases

  The flag is therefore usable, with a measured error, as "probable" evidence for the
  1,890 groundwater points of the plain (1,067 flagged True, 603 False, 220 empty).

**Correction (2026-10-23, task 12.3):** the counts above mix two directions. "50 of 53
Pliocene-coded points are False" is a recall. As a rule ("False → Pliocene") the flag is
right in only 53 of 112 coded points of the plain; with the BD LISA stack (False **and**
the Pliocene under the point) in 92 % of the 130 distinct recorded boreholes. The plain
counts of the dataset's 1,890 groundwater ouvrages are 882 True, 539 False, 469 empty.
`nom_mode_gisement` (free / confined / semi-confined / artesian) is filled for 571
stations and could serve CQ14. Details: `docs/notes/step12b_review_fixes.md`.

### Model-ready dataset v4 (Step 12b, second review)

| Date | Command | Output | Rows |
|---|---|---|---|
| 2026-10-23 | `PFE_DATASET=v4 python -m src.dataset.build` (log in `results/build_v4.log`) | `data/processed/dataset_v4/` | 65 wells (33 core); heads_weekly 55,141 (v3: 55,204); forcing, rivers, pumping, restrictions byte-identical to v3 |

No new download: v4 is v3 rebuilt from the same caches (piezometer chronicles up to
2026-10-04, BNPE snapshot 2026-10-20). Changes (`docs/analysis_plan.md` v2, §13):

| Change | Effect |
|---|---|
| Values qualified "Incorrecte" or "Qualification non définissable" dropped before the weekly mean | 449 values; 8 model-window weeks changed (≤ 0.11 m), 63 emptied (F3, 2007); SGI changes at F3, CONTE, F1N3 (14 test-period IPS classes at F3) |
| `share_reconstructed` per week (producer-reconstructed values) | 0.6 % of test-period values of the core wells |
| Leave-wells-out folds: wells < 2 km apart in one block (45 blocks), blocks dealt by core wells per aquifer group | closest wells in different folds 2,153 m (v3: 20 m); 4 Pliocene core wells per fold |
| `pct_days_artesian_f25`, `_f50`: artesian share per R3 window | used by `build_panel(train_start=...)` |

Added 2026-10-25 (third review, second pass; decided by Assil on 2026-10-24), no download:

| Date | Command | Output | Rows |
|---|---|---|---|
| 2026-10-25 | `PFE_DATASET=v4 python -m src.dataset.placeholders` (also run by `src.dataset.build` from v4) | `data/processed/dataset_v4/placeholder_weeks.parquet` | 60 well-weeks, one run: 10971X0155/PD5 (CORNEILLA, core, Pliocene), depth 0.00 m on 413 consecutive days, 2022-11-30 → 2024-01-16, qualified "Correcte" |

Rule: a run of ≥ 28 days with a depth to water of exactly 0.00 m (records ≤ 7 days apart) is a
suspect placeholder; its weeks leave every scored variant (`src/models/evaluate.py`). Flowing
wells record negative depths (F 2,011 days, S 3,033, FAITOU 5,208); PD5 never does. Every
other run at depth 0 is at most 7 days long and kept (days at depth 0 in total since 2000:
BSS004PRUN 39, BSS004PRUL 32, BSS004PRUM 17, F3N4 12, all non-core except F3N4; seven other
stations 1–6 days; PD5 itself has 20 more days at 0 outside its long run). None of the
flagged weeks is before the test period, so no model input or training week changes. The
other dataset files are unchanged; all local v4 runs were rescored on 2026-10-25.

Known limit of the weekly pumping (`tests/test_pumping_conservation.py`, 2026-10-25): flat
uses (drinking water, industry, energy) get 7/365.25 of the annual volume per week label, so
a year keeps 52 × 7/365.25 = 0.9966 or 53 × 7/365.25 = 1.0157 of it; the four 53-week years
since 2005 (2006, 2012, 2017, 2023) carry 1.9 % more flat pumping than the others. Seasonal
uses (irrigation, canals) sum exactly to their annual volume. Kept in v4 (every model sees the
same input); annual accounting uses the declared records (the KG), not weekly sums.

### Pump → aquifer unit attribution (Step 12, task 12.3)

| Date | Command | Output | Rows |
|---|---|---|---|
| 2026-10-23 | `PFE_DATASET=v4 python -m src.kg.pump_attribution` | `data/interim/pump_unit_evidence.parquet` (evidence per ouvrage), `pump_unit_attribution.parquet` (candidates), `pump_unit_attribution_eval.json` (precision, coverage) | 2,137 groundwater ouvrages; 2,144 candidates (the 4 depth-checked boreholes appear under 7 ouvrages, each keeping its recorded unit as an alternative) |

Inputs: the dataset's `pumping_points` and `pumping_weekly`, the BNPE points of the
2026-10-20 snapshot, the quality stations above, the BD LISA V3 GeoPackage.

| Date | Command | Output | Rows |
|---|---|---|---|
| 2026-10-25 | `PFE_DATASET=v4 python -m src.kg.pump_coverage` | `data/interim/pump_unit_coverage.csv` (zone × year × imputed × use × unit group × rule × confidence at unit-group and exact-unit resolution → m³), `docs/pump_coverage.md` | plain, declared 2012–2024: 712.0 Mm³; main policy 72.3 % (unit group) / 61.8 % (exact unit); irrigation 0 % |

### Reused vocabularies (Step 12, task 12.4)

| Date | Command | Output | Size |
|---|---|---|---|
| 2026-10-24 | `python -m src.kg.build_imports` (downloads once, then ROBOT MIREOT extracts; log with sha256 in `data/raw/vocab/sources.json`) | `data/raw/vocab/` (sources), `ontology/imports/*_terms.ttl` (extracts, committed) | see below |

| File | Source (content negotiation where marked) | Bytes |
|---|---|---|
| `sosa.ttl` | `https://www.w3.org/ns/sosa/` (text/turtle) | 27,326 |
| `prov-o.ttl` | `https://www.w3.org/ns/prov-o` (text/turtle) | 68,795 |
| `time.ttl` | `https://www.w3.org/2006/time` (text/turtle) | 101,486 |
| `skos.rdf` | `https://www.w3.org/2004/02/skos/core` (application/rdf+xml; redirects to the 2009 SKOS reference) | 28,966 |
| `geo.ttl` | GeoSPARQL 1.1 (`owl:versionIRI <http://www.opengis.net/ont/geosparql/1.1>`) from the `1.1.0-ghpages` tag of github.com/opengeospatial/ogc-geosparql; the OGC server now answers its namespace with a catalogue page | 40,630 |
| `sweet_realmHydro.ttl`, `sweet_matrWater.ttl` | github.com/ESIPFed/sweet, `src/` (CC0) | 12,158; 15,532 |

The GWML2 and HyFO terms have no downloadable source: SAWGraph's Turtle URL returned 404
and its documentation page (https://ontologies.geoconnex.us/sawgraph-water-ontology, read
on 2026-10-24) is the source of the hand-written `ontology/imports/gwml2_hyfo_terms.ttl`.
ROBOT 1.9.11 (`tools/robot.jar`, gitignored) came from the ontodev/robot GitHub release;
its sha256 matched the published digest (53cd275c…).

### Knowledge graph (Step 12, task 12.5)

| Date | Command | Output | Rows |
|---|---|---|---|
| 2026-10-24 | `PFE_DATASET=v4 python -m src.kg.build_kg` (61 s; check: `python -m tests.test_kg`) | `data/processed/kg/lulcw_kg_v4.ttl` (14.5 MB Turtle), `lulcw_kg_v4_summary.json` (counts) | 205,650 triples: 65 piezometers, 47 units, 201 polygons, 2,187 groundwater facilities, 2,280 unit attributions, 12,951 annual declared volumes |

Inputs: dataset v4 (`wells`, `heads_weekly`), `data/interim/piezo_stations.parquet` and
`raw/hubeau/stations_66.parquet`, the BNPE snapshot of 2026-10-20 (points and annual
volumes, groundwater only), the BD LISA V3 GeoPackage, and the task 12.3 tables. No
download. Rebuild it after any of them changes (`tests/test_kg.py` then fails).
