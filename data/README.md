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

**Commune history for CQ9 (2026-11-26, night).** `python -m src.ingest.vigieau_communes` (cached):

| Date | Source | URL | Output | Rows | Size |
|---|---|---|---|---|---|
| 2026-11-26 | same dataset, resource "Historique Communes" (one JSON array, 12.1 GB unpacked, streamed from the zip, never unpacked on disk) | `https://static.data.gouv.fr/resources/donnee-secheresse-vigieau/20261126-170419/historique-communes.zip` (SHA-256 `f31955f2879e82c8…`) | `raw/vigieau/2026-11-26/historique-communes.zip`; `interim/vigieau_communes_66.parquet` (commune, name, date, SUP, SOU, AEP levels 0–4) | 1,368,204 = 226 communes × 6,054 days (2010-05-01 → 2026-11-26) | 594,629,369 B |

Every commune of the département is listed every day; a null level (0) is VigiEau's "no restriction of that type". The
first restriction in the département is on 2012-03-28 (the order files start in 2012: before 2012 the absence of a
restriction is not evidenced); drinking-water (AEP) levels exist only from 2024-04-28. Explanation context only (CQ9),
never a model input.

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

### Land-use thread (Step 12d, 2026-10-25)

| Date | Source | Endpoint / URL | Parameters | Output | Rows | Size |
|---|---|---|---|---|---|---|
| 2026-10-25 | Natural Earth admin-0 countries 1:10m (public domain) | `https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip` | `python -m src.ingest.borders`; Spain + Andorra (`ADM0_A3`; `ISO_A3` is -99 for France) intersecting `DEPT_BBOX` | `raw/naturalearth/ne_10m_admin_0_countries.zip` (md5 0bc33f3e…) → `interim/foreign_land_66.parquet` | 2 countries | 4.9 MB |
| 2026-10-25 | DRAAF Occitanie, Agreste Essentiel (RA2020), irrigating-farm typology, dept 66, January 2024 | `https://draaf.occitanie.agriculture.gouv.fr/IMG/pdf/essentiel_typoirri_0124_dep66-pyrenees-orientales_v24c.pdf` | manual read (pdftotext) | `raw/agreste/essentiel_typoirri_0124_dep66-pyrenees-orientales_v24c.pdf` (md5 e23db3cb…) | 10 pages | 0.65 MB |
| 2026-10-25 | DRAAF Occitanie, Agreste Études no 9 (RA2020, Pyrénées-Orientales), July 2022 | `https://draaf.occitanie.agriculture.gouv.fr/IMG/pdf/agreste_etudes_ra20_po_19072022.pdf` | manual read (pdftotext) | `raw/agreste/agreste_etudes_ra20_po_19072022.pdf` (md5 792aae4c…) | 6 pages | 0.74 MB |

Census figures used (dept 66, RA2020): SAU 68,020 ha; vines 19,840 ha (−5,770 ha since
2010), orchards 8,100 ha (+1,150 ha, +16 %), market gardening 1,760 ha. Irrigating farms
by type (typology covering 73 % of the irrigated SAU): specialised fruit 403 farms,
5,268 ha irrigated of 6,715 ha; vegetables 227, 932 of 1,113 ha; vines 91, 839 of
3,107 ha; vegetables + fruit 102, 1,639 of 1,926 ha; fruit + vines 38, 502 of 1,236 ha.
Used to set the main crop-thirst index to the classes usually irrigated (analysis plan
§14 item 13).

RPG editions 2015–2025, clipped to the département extent (`python -m src.ingest.rpg
--years ... --clip dept [--drop-raw]`; `DEPT_BBOX` of `src/ingest/safran.py`, which holds the
3 km zone of every well). Columns are upper-cased (the 2024–25 GeoPackages use lower case
and add `cat_cult_p`, `precision`, `gcp`, `pp`, `bio`, `iae`); `CODE_GROUP` is Int64. Every
crop code keeps its group across the 11 editions (245 codes; `tests/test_crop_demand.py`).

| Date | Source | Endpoint / URL | Parameters | Output | Rows | Size |
|---|---|---|---|---|---|---|
| 2026-10-25 | IGN Géoplateforme | `.../download/RPG/RPG_2-0__SHP_LAMB93_R76-2015_2015-01-01/` (RPG_2-0__SHP_LAMB93_R76-2015_2015-01-01.7z) | R76, edition 2015; no .md5 published (size check); clipped to `DEPT_BBOX` | `interim/rpg_dept_2015.parquet` (raw deleted after the clip) | 74,466 parcels | 448 MB raw / 29.0 MB clip |
| 2026-10-25 | IGN Géoplateforme | `.../download/RPG/RPG_2-0__SHP_LAMB93_R76-2016_2016-01-01/` (RPG_2-0__SHP_LAMB93_R76-2016_2016-01-01.7z) | R76, edition 2016; no .md5 published (size check); clipped to `DEPT_BBOX` | `interim/rpg_dept_2016.parquet` | 74,582 parcels | kept from Step 5 raw / 29.5 MB clip |
| 2026-10-25 | IGN Géoplateforme | `.../download/RPG/RPG_2-0__SHP_LAMB93_R76-2017_2017-01-01/` (RPG_2-0__SHP_LAMB93_R76-2017_2017-01-01.7z) | R76, edition 2017; no .md5 published (size check); clipped to `DEPT_BBOX` | `interim/rpg_dept_2017.parquet` (raw deleted after the clip) | 75,310 parcels | 458 MB raw / 29.6 MB clip |
| 2026-10-25 | IGN Géoplateforme | `.../download/RPG/RPG_2-0__SHP_LAMB93_R76-2018_2018-01-15/` (RPG_2-0__SHP_LAMB93_R76-2018_2018-01-15.7z) | R76, edition 2018; no .md5 published (size check); clipped to `DEPT_BBOX` | `interim/rpg_dept_2018.parquet` (raw deleted after the clip) | 76,527 parcels | 556 MB raw / 32.7 MB clip |
| 2026-10-25 | IGN Géoplateforme | `.../download/RPG/RPG_2-0_SHP_LAMB93_R76-2019/` (RPG_2-0_SHP_LAMB93_R76-2019.7z) | R76, edition 2019; no .md5 published (size check); clipped to `DEPT_BBOX` | `interim/rpg_dept_2019.parquet` (raw deleted after the clip) | 77,502 parcels | 484 MB raw / 31.0 MB clip |
| 2026-10-25 | IGN Géoplateforme | `.../download/RPG/RPG_2-0__SHP_LAMB93_R76_2020-01-01/` (RPG_2-0__SHP_LAMB93_R76_2020-01-01.7z) | R76, edition 2020; no .md5 published (size check); clipped to `DEPT_BBOX` | `interim/rpg_dept_2020.parquet` (raw deleted after the clip) | 79,730 parcels | 497 MB raw / 32.1 MB clip |
| 2026-10-25 | IGN Géoplateforme | `.../download/RPG/RPG_2-0__SHP_LAMB93_R76_2021-01-01/` (RPG_2-0__SHP_LAMB93_R76_2021-01-01.7z) | R76, edition 2021; no .md5 published (size check); clipped to `DEPT_BBOX` | `interim/rpg_dept_2021.parquet` (raw deleted after the clip) | 80,548 parcels | 618 MB raw / 33.1 MB clip |
| 2026-10-25 | IGN Géoplateforme | `.../download/RPG/RPG_2-0__SHP_LAMB93_R76_2022-01-01/` (RPG_2-0__SHP_LAMB93_R76_2022-01-01.7z.001) | R76, edition 2022; MD5 verified; clipped to `DEPT_BBOX` | `interim/rpg_dept_2022.parquet` (raw deleted after the clip) | 81,178 parcels | 394 MB raw / 35.7 MB clip |
| 2026-10-25 | IGN Géoplateforme | `.../download/RPG/RPG_2-2__SHP_LAMB93_R76_2023-01-01/` (RPG_2-2__SHP_LAMB93_R76_2023-01-01.7z) | R76, edition 2023; MD5 verified; clipped to `DEPT_BBOX` | `interim/rpg_dept_2023.parquet` | 83,367 parcels | kept from Step 5 raw / 35.6 MB clip |
| 2026-10-25 | IGN Géoplateforme | `.../download/RPG/RPG_4-0__GPKG_LAMB93_R76_2024-01-01/` (RPG_4-0__GPKG_LAMB93_R76_2024-01-01.7z) | R76, edition 2024; no .md5 published (size check); clipped to `DEPT_BBOX` | `interim/rpg_dept_2024.parquet` (raw deleted after the clip) | 80,136 parcels | 1766 MB raw / 32.9 MB clip |
| 2026-10-25 | IGN Géoplateforme | `.../download/RPG/RPG_4-0__GPKG_LAMB93_R76_2025-01-01/` (RPG_4-0__GPKG_LAMB93_R76_2025-01-01.7z) | R76, edition 2025; no .md5 published (size check); clipped to `DEPT_BBOX` | `interim/rpg_dept_2025.parquet` (raw deleted after the clip) | 80,905 parcels | 1699 MB raw / 32.3 MB clip |

Notes:
- **Volume transferred.** About 10 GB in all on 2026-10-25: a first pass clipped 2015 and
  2017–2021 to the plain only (3.1 GB), which missed the zones of the 15 mountain wells; the
  second pass re-downloaded them for the département extent, and the 2024–25 GeoPackages
  weigh 1.7 GB each, about four times the shapefile editions. Assil had approved about 4–5 GB
  and then about 3 GB on estimates that did not check the sizes; `--plan` now prints them
  before any download. The superseded plain clips of 2015 and 2017–2021
  (`interim/rpg_plain_<year>.parquet`, written that morning) are no longer read.
- **2018** timed out twice (3 MB/s from the server in the afternoon) and was resumed from its
  partial file; **2022** is published as a single part `.7z.001` with an MD5 for that part.
- Derived: `interim/crop_area_3km.parquet` (clipped ha by well × edition × code; 0 ha
  unmapped), `interim/crop_demand_weekly_v4.parquet` (90,805 well-weeks),
  `interim/pumping_weekly_cropcal_v4.parquet` (reconstruction 3, 2,308,950 rows),
  `interim/crop_demand_plain_check.csv`, `interim/rpg_coverage_plain.csv`.

### AGROVOC Core (Step 12, task 12.9, 2026-10-26)

| Date | Source | Endpoint / URL | Parameters | Output | Rows | Size |
|---|---|---|---|---|---|---|
| 2026-10-26 | FAO, AGROVOC Core dump, N-Triples (CC BY 4.0); listed by the FAO data catalogue, dataset "AGROVOC Release" (`data.apps.fao.org/catalog/api/3/action/package_search?fq=organization:agrovoc`) | `https://agrovoc.fao.org/latestAgrovoc/agrovoc_core.nt.zip` | `python -m src.ingest.agrovoc`; release regenerated by FAO on 2026-10-26 (Last-Modified 08:15:49 GMT, VoID `dct:modified` 07:34:13Z); ETag = md5 `dfcebf9f76c73a980b11ddff4ab13116` | `raw/agrovoc/2026-10-26/agrovoc_core.nt.zip`, `void.ttl`, `release.json` | 42,082 concepts (1 deprecated) | 74.4 MB |

- **Moving URL.** FAO serves only its newest release at this URL (older ones on request), so
  the snapshot is kept under its release date and never downloaded again; `--check` compares it
  with the release online by a HEAD request. The gold set and the matchers of 12.9 use this
  snapshot only.
- The zip is read as a stream, never extracted. Labels are SKOS-XL only (`skosxl:prefLabel` /
  `altLabel` → `skosxl:literalForm`; the core dump has no plain `skos:prefLabel`).
- Derived: `interim/agrovoc_labels.parquet` (105,697 French and English labels: 42,082
  preferred in each language, 13,006 English and 8,527 French alternatives),
  `interim/agrovoc_broader.parquet` (42,530 `skos:broader` links between concepts).

### River reaches, water bodies and cited documents (Step 12, CQ5 and CQ6, 2026-11-06)

| Date | Source | Endpoint / URL | Parameters | Output | Rows | Size |
|---|---|---|---|---|---|---|
| 2026-11-06 | IGN, BD TOPO V3 hydrography (Licence Ouverte 2.0) | `https://data.geopf.fr/wfs/ows` (WFS 2.0.0), `BDTOPO_V3:troncon_hydrographique`, `BDTOPO_V3:cours_d_eau` | `python -m src.ingest.bdtopo_hydro`; BBOX = DEPT_BBOX (lon 1.65–3.25, lat 42.30–43.00), `SRSNAME=EPSG:2154`, `COUNT=5000` + `STARTINDEX`, `SORTBY=cleabs` | `raw/bdtopo_hydro/2026-11-06/troncon_hydrographique.parquet`, `cours_d_eau.parquet`, `release.json` | 48,346 reaches; 3,269 watercourses | 23.9 MB; 11.3 MB |
| 2026-11-06 | Sandre, référentiel des masses d'eau, version rapportage 2022 | `https://services.sandre.eaufrance.fr/geo/MasseDEau_VRAP2022` (WFS), `sa:MasseDEauRiviere_VRAP2022_FXX` | `python -m src.ingest.sandre_water_bodies`; same BBOX, `SRSNAME=EPSG:2154`, `OUTPUTFORMAT=GPKG` (GeoJSON is refused for this layer) | `raw/sandre_water_bodies/2026-11-06/masses_eau_riviere_vrap2022.zip`, `.parquet`, `release.json` | 193 river water bodies | 0.5 MB |
| 2026-11-06 | BRGM/RP-71486-FR (Ladouche & Caballero 2022, Dem'Eaux Roussillon #11b); Agence de l'eau RMC (SIERM) groundwater-body sheets FRDG351 and FRDG243, état des connaissances 2021 | `https://infoterre.brgm.fr/rapports/RP-71486-FR.pdf`; `https://www.rhone-mediterranee.eaufrance.fr/sites/sierm/files/underground_waterbody/FRDG351.pdf`, `.../FRDG243.pdf` | `python -m src.ingest.documents` | `raw/documents/<key>.pdf`, `documents.json` (URL, date, size, md5) | 3 documents (50, 8 and 7 pages) | 5.4 MB, 159 KB, 155 KB |

- **Join keys.** A BD TOPO reach carries the BD Carthage code of its watercourse
  (`code_du_cours_d_eau_bdcarthage`, e.g. `Y04-0400` for the Têt), which is Hub'Eau's
  `code_cours_eau` for a gauge: the 21 gauged watercourses of dataset v4 all match (the canal
  adducteur and the Font-Estramar resurgence have code `00000000`). Reach attributes used: `nature`
  (2,546 canals), `persistance`, `reseau_principal_coulant`, `cpx_toponyme_de_cours_d_eau`.
- **Water bodies.** The 13 sections that the FRDG351 and FRDG243 sheets qualify are all present
  (FRDR211, 212, 223, 224, 232A, 232B, 234A, 234B, 235, 237A, 984, 986B, 1012); they carry no BD Carthage
  code, so they meet the BD TOPO reaches by geometry (procedure in `src/kg/rivers.py`).
- **Documents.** Read with `pdftotext -layout`. The statements used are curated in
  `configs/river_exchange_evidence.csv` (printed page, short quote). BRGM's sampling points come
  with Lambert-93 coordinates (annex, Figure A-3); the report's code 750PP02 for the recent alluvium
  is absent from BD LISA V3 and is mapped to 718BP02 by name.
- **Canal command areas: not found** (search of 2026-11-06: data.gouv.fr, the préfecture 66 site,
  the Géoplateforme WFS, Sandre). The ASA perimeters exist as map annexes of prefectural orders
  (PDF); a "test" dataset on data.gouv.fr covers the ASA of the Castellane only (Conflent).

### INSPIRE HILUCS code list (Step 12, land use, 2026-11-16)

| Date | Source | Endpoint / URL | Parameters | Output | Rows | Size |
|---|---|---|---|---|---|---|
| 2026-11-16 | INSPIRE registry (European Commission), code list HILUCSValue (Hierarchical INSPIRE Land Use Classification System), governance level "Legal (EU)" | `https://inspire.ec.europa.eu/codelist/HILUCSValue/HILUCSValue.en.json` | `python -m src.ingest.inspire_hilucs`; SHA-256 `6df58135c36f04541aaac1172e6e293a591efacc6021659c78626c4e9396fa33` | `raw/inspire_hilucs/2026-11-16/HILUCSValue.en.json`, `release.json` | 98 values, all Valid | 295 kB |

- Each value's `id` is its IRI (e.g. `http://inspire.ec.europa.eu/codelist/HILUCSValue/1_1_1_CommercialAgriculturalProduction`).
  Pinned in `configs/snapshots.json`; the crop classes' HILUCS values (`configs/lu_hilucs.csv`) are
  checked against it when the graph is built, and `tests/test_kg.py` checks the local copies in
  `ontology/imports/inspire_terms.ttl` against it.

### OOPS! pitfall scan (quality gate, 2026-11-16)

| Date | Source | Endpoint / URL | Parameters | Output | Rows | Size |
|---|---|---|---|---|---|---|
| 2026-11-16 | OOPS! (OntOlogy Pitfall Scanner), Ontology Engineering Group, UPM | `https://oops.linkeddata.es/rest` (POST) | `python -m src.kg.oops_scan`; content = the merged network (lulcw 0.7.1 + imports, ROBOT merge, owl:imports removed), RDF/XML in a CDATA section; scanning by URL is refused by the service | `raw/oops/2026-11-16/response.xml`, `release.json` (SHA-256 of the content sent) | 5 pitfalls + 1 suggestion | 3,236 triples sent |

- What is sent is public already (the repository is public). The service failed ("unexpected
  error") on the owl:imports of lulcw.ttl (w3id.org IRIs not yet redirected), hence their removal.
- Report and verdicts: `docs/oops_report.md`, `configs/oops_verdicts.csv`.

## Dataset v5 pulls (branch `master_2026_fixes`, `docs/v5_plan.md` R1; from 2026-11-25)

### BRGM borehole database (BSS) points (R1.3, 2026-11-25)

| Date | Source | Endpoint / URL | Parameters | Output | Rows | Size |
|---|---|---|---|---|---|---|
| 2026-11-25 | BRGM, Banque du Sous-Sol, open WFS of the geology geoservice (Etalab Open Licence 2.0); layers found with GetCapabilities, fields with DescribeFeatureType | `https://geoservices.brgm.fr/geologie` (MapServer WFS 2.0.0) | `python -m src.ingest.brgm_bss --folder 2026-11-25-tiled`; `TYPENAMES=ms:BSS_EAU_POINT` and `ms:BSS_TOTAL_SANS_LABEL`; `DEPT_BBOX` (lon 1.65–3.25, lat 42.30–43.00) cut in 0.2° tiles, a tile split in four while it returns the 1000-feature cap; GeoJSON; 1 s between requests; deduplicated on `gid` / `gis` | `raw/brgm_bss/2026-11-25-tiled/bss_eau_point.parquet`, `bss_total_sans_label.parquet`, `release.json` | 6,848 water points (5,557 in dept 66); 12,611 boreholes (9,893 in dept 66) | — |

- **Superseded first pull** (`raw/brgm_bss/2026-11-25/`, kept, not used): it paged with STARTINDEX and no sort
  order; MapServer's order is not stable between requests, so pages overlapped. It held the same number of rows
  but only 5,292 distinct water points and 9,953 distinct boreholes: **1,556 water points and 2,658 boreholes
  (≈ 22 %) were skipped**. Found by worker neon in T62; the tiled pull contains every id of the paged one.
- MapServer answers a tile without features with HTTP 200 and an **empty body** (not an empty collection).
- Water points in dept 66: investigation depth `prof_invest` filled for 73.1 %, BD LISA entities `liste_bdlisa`
  for 41.5 % (20.8 % read "NV3 absent, nom de l'entité NV2 : …"), aquifer condition `mode_gisement` mostly
  "Inconnu" (4,292), "Libre" 470, "Captif" 96. Boreholes in dept 66: depth reached `prof_atteinte` filled for 78.1 %.
- Join to the BNPE groundwater points of dataset v4: 2,137 points, 240 with a BSS code, 237 of them found among
  the water points. `liste_bdlisa` copies ADES verbatim on the recorded boreholes (T62: 130/130), so it is not
  independent evidence there; matching by location is weak because most BSS points with a known code sit at
  their commune's centroid. Measured in `docs/bss_evidence.md` (T62): no irrigation borehole has a recorded
  unit, so no irrigation link can be made "probable" by these data.

### Sentinel-2 spring and summer indices per RPG parcel (R1.4, CQ15, 2026-11-26)

| Date | Source | Endpoint / URL | Parameters | Output | Rows | Size |
|---|---|---|---|---|---|---|
| 2026-11-26 | Copernicus Sentinel-2 level-2A surface reflectance, harmonised (`COPERNICUS/S2_SR_HARMONIZED`), through Google Earth Engine under Assil's Cloud project (`.agents/RESOURCES.md`); parcels from the RPG editions already pulled (`interim/rpg_dept_<year>.parquet`) | Earth Engine API (`earthengine-api` 1.7.53, `ee.data.computeFeatures`) | `PFE_DATASET=v5 python -m src.ingest.gee_s2 --workers 4`; years 2017–2025; parcels intersecting the 65 wells' 3 km zones (`crop_demand.well_buffers`), whole, simplified to 2 m; seasons April–May and July–August; SCL classes 4, 5, 6 kept; per pixel the seasonal median of NDVI (B8, B4) and NDMI (B8, B11) and the count of valid acquisitions; per parcel the mean at 10 m and the valid-pixel count; batches of 800 parcels, 4 in parallel | `raw/gee_s2/2026-11-26/s2_parcels_<year>.parquet` (+ one file per batch, `release.json`); log `results/logs/gee_s2_2026-11-26.log` | 142,282 parcel-years (13,927 in 2017 … 17,989 in 2025); valid summer pixels for all but 1, spring for all but 128 | 23 MB |

- About 8 minutes in all (≈ 3 s per batch). Medians 2017–2019 by RPG group look physical: vines (21)
  NDVI 0.27 in spring, 0.35 in summer; orchards (20) 0.66 → 0.57; fallow (11) 0.52 → 0.31; mountain pastures
  (17) 0.60 → 0.67 (green from altitude, not irrigation: hence the soil-wetness condition of CQ15's rule);
  ≈ 9 valid summer acquisitions per pixel after the cloud mask.
- Observations only: the CQ15 rule (thresholds frozen on training years), its validation against the Agreste
  2020 census and the per-well irrigated share come after (`docs/analysis_plan_v3.md` §1).
- **Derived (CQ15, T76, 2026-11-26):** `PFE_DATASET=v5 python -m src.dataset.irrigation_s2` (36 s) →
  `interim/irrigation_s2_parcels_v5.parquet` (142,282 parcel-years with status positive / negative /
  insufficient_data / not_applicable), `processed/dataset_v5/irrigation_s2_wells.parquet` (65 wells × 9 editions +
  a "train" row: the 2017–2019 mean share of probably irrigated land in the 3 km zone, the static fact of CQ15's
  with/without row) and `processed/dataset_v5/irrigation_s2_rule.json` (frozen threshold NDVI ≥ 0.485 = Otsu on
  2017–2019; quality MIN_PX 4, MIN_OBS 3; dry SWI_JA ≤ 0.5; input hashes). Report `docs/irrigation_s2.md`:
  verdict **heuristic** (2020 vs RA2020: orchards 0.71 in [0.65, 0.91], vines 0.13 above [0.04, 0.07], market
  gardening 0.18 below ≥ 0.53).

### BNPE 2025 availability check (R1.1b, 2026-11-25)

- `https://hubeau.eaufrance.fr/api/v1/prelevements/chroniques?code_departement=66&annee=<y>&size=1`:
  count 1,823 (2023), 1,846 (2024), **0 (2025)**. BNPE 2025 is not published yet: 2025 pumping
  stays imputed in v5 (recheck before the v5 freeze).

### Hub'Eau piezometers and river flows, dated snapshots (R1.1b, 2026-11-25)

| Date | Source | Endpoint / URL | Parameters | Output | Rows | Size |
|---|---|---|---|---|---|---|
| 2026-11-25 | Hub'Eau niveaux_nappes (full re-download, not incremental) | `https://hubeau.eaufrance.fr/api/v1/niveaux_nappes` (`/stations`, `/chroniques`) | `python -m src.ingest.hubeau_piezo --snapshot 2026-11-25` (dept 66, size 5000) | `raw/hubeau/snapshots/2026-11-25/` (stations files, `chroniques/`) | 105 stations (2 empty, 0 failed) | — |
| 2026-11-25 | Hub'Eau hydrometrie v2, daily mean flow QmnJ | `https://hubeau.eaufrance.fr/api/v2/hydrometrie` (`referentiel/stations`, `obs_elab`) | `python -m src.ingest.hubeau_hydro --snapshot 2026-11-25` (from 2005-01-01) | `raw/hubeau_hydro/snapshots/2026-11-25/` (`stations_66.parquet`, `qmnj/`) | 45 series (27 stations empty, 0 failed) | — |

- The default caches (`raw/hubeau/chroniques/`, `raw/hubeau_hydro/qmnj/`) are untouched: dataset v4 was
  built from them and must still rebuild from cold.
- Piezometers, 33 core wells: last date 2026-09-29 → 2026-11-22 (median), 1,861 daily records added, and
  **6,578 records since 2024 re-qualified** by the producer (6,574 now "Correcte"): the 2024–2025 case
  studies lose most of their "not validated" caveat in v5.
- River flows: obs_elab serves QmnJ from 2005 only (the Têt at Perpignan, Y046403001, returns its first
  value on 2005-01-01 even when asked from 1950), so v5's rivers start in 2005 as v4's.
- Canal stations re-checked (docs/v5_plan.md C1): no daily flow in our period, and the monthly QmM series
  stop before 2005 (Y046821001 has 2000-04 … 2004-11; Y046881001, Y005561001, Y047882001, Y046901001,
  Y063404001, Y024511001 none after 2000).

### SAFRAN-SIM2 1990–1999 and the republication of 2023+ (R1.1a, 2026-11-25)

| Date | Source | Endpoint / URL | Parameters | Output | Rows | Size |
|---|---|---|---|---|---|---|
| 2026-11-25 | Météo-France SIM2 daily (data.gouv.fr "SIM quotidienne") | `https://meteofrance.s3.sbg.io.cloud.ovh.net/data/REF_CC/SIM/QUOT_SIM2_<year>.csv.gz` | `python -m src.ingest.safran --start 1990` (dept-66 cells of `DEPT_BBOX`; each national file deleted after filtering) | `raw/safran/sim2_66_1990.parquet` … `_1999.parquet` (new); 2023–2026 re-fetched | 37 years, 1,900,257 cell-days | 14.7 MB on disk (≈ 1.4 GB transferred for 1990–1999, ≈ 0.53 GB for 2023–2026) |

- 1990–1999 national files: ≈ 137–140 MB each, Last-Modified 2026-07-31.
- **2023, 2024, 2025, 2026 were republished** by Météo-France after v4's pull (server copies newer than the
  sidecars), so the ingest replaced them. Measured against v4's saved weekly forcing (same cells and weeks):
  2000–2022 identical; 2023+ total differences 0.01–0.17 % (rain 0.05 %, ETP 0.17 %, PE 0.13 %, DRAINC 0.01 %),
  largest single cell-week |Δrain| 7.6 mm (provisional data replaced by final). v4's processed tables stay the
  record; a cold rebuild of v4 would now differ trivially from 2023 and reach 2026-11-22 instead of 2026-10-11.

### Model-ready dataset v5 (R1.5, built 2026-11-25)

`PFE_DATASET=v5 python -m src.dataset.build` (entry `v5` of `src/dataset/build.py`; log
`results/logs/build_v5_2026-11-25.log`) → `processed/dataset_v5/`. v4's rules and wells, plus weather from
1990, the Hub'Eau snapshots of 2026-11-25, and the canal volume per basin (`canal_basins_weekly.parquet`,
`canal_intakes_basin.parquet`).

| | v4 | v5 |
|---|---|---|
| wells / core / folds | 65 / 33 / 5 | identical (same wells, core flags and folds) |
| weekly heads | 55,141 (from 2000) | 59,868 (from 1990; 59,884 before T69 trimmed the week without weather) |
| forcing cell-weeks | 196,977 (from 2000) | 271,425 (from 1990) |
| last week | 2026-10-04 | 2026-11-22 (= the last weather week, `end_at_forcing`, T69) |
| core test well-weeks | 7,414 | 7,677 |
| core test weeks not validated | 41.5 % | **23.7 %** |
| placeholder weeks masked | 60 (CORNEILLA PD5) | 60 (same) |
| quality filter | — | 437 values dropped; model-window weeks changed 7, emptied 62 |
| last BNPE year | 2024 | 2024 (2025–2026 imputed) |

### Reused vocabularies for the v5 alignments (R2.3, 2026-11-26)

`python -m src.kg.build_imports --only sweet saref envo` (downloads once into `data/raw/vocab/`, logged with SHA-256
in `data/raw/vocab/sources.json`; ROBOT MIREOT extracts in `ontology/imports/`, committed). Licences read at the
source the same day.

| File | Source | Licence | Bytes | SHA-256 (first 16) |
|---|---|---|---|---|
| `saref4watr.ttl` | `https://saref.etsi.org/saref4watr/v2.1.1/saref4watr.ttl` (SAREF4WATR v2.1.1, ETSI) | ETSI BSD-3-Clause | 57,491 | `964044e750d829e1` |
| `envo.owl` | `http://purl.obolibrary.org/obo/envo/releases/2026-10-23/envo.owl` (redirects to the `v2026-10-23` tag of github.com/EnvironmentOntology/envo) | CC0 1.0 | 9,955,495 | `cc070bc1ceca4bf7` |
| `sweet_realmHydroBody.ttl`, `sweet_phenHydro.ttl`, `sweet_humanAgriculture.ttl` | github.com/ESIPFed/sweet, `src/` (master) | CC0 | 15,804; 10,659; 8,091 | `cd8d91fe26f5a1e5`; `160789f8978b4ecc`; `569c79958b14c9b8` |

Checked but not used: SAREF4AGRI v2.1.1 (`https://saref.etsi.org/saref4agri/v2.1.1/saref4agri.ttl`, 21,016 bytes;
v1.1.1 returns 404): its candidate correspondences are rejected in the ledger, and its `Parcel` waits for CQ15's
terms. GEMET and the CORINE Land Cover SKOS vocabulary (both on Eionet, `www.eionet.europa.eu`,
`dd.eionet.europa.eu`) could not be reached from this network on 2026-11-26 (TLS connections time out, IPv4 and
IPv6): retry later.

**GEMET and CORINE from the Internet Archive (2026-11-26, night).** Eionet was still unreachable (DNS resolves to
87.54.7.182; TCP connections time out), so the two files were taken from the Internet Archive's copies of the Eionet
URLs, as raw bytes (`id_` mode), logged in `data/raw/vocab/sources.json` with the original URL and the snapshot time:

| File | Original URL (archive snapshot) | Licence | Bytes | SHA-256 (first 16) |
|---|---|---|---|---|
| `gemet.rdf.gz` | `https://www.eionet.europa.eu/gemet/latest/gemet.rdf.gz` (2026-03-09 18:06:56 UTC); GEMET Concepts version 4.2.3 of 2021-12-06 | CC BY 4.0 (stated in the file) | 7,423,725 | `96002bb7cd1f89bc` |
| `clc_eionet.rdf` | `http://dd.eionet.europa.eu/vocabulary/landcover/clc/rdf` (2022-06-29 05:27:16 UTC); Eionet data dictionary vocabulary "Corine Land Cover", modified 2015-04-23, empty definitions | Eionet terms of use (to check before reuse) | 26,007 | `b6a64d9af98ec057` |

### EuroCrops HCAT3 and its French mapping (R2.3, 2026-11-26)

| Date | Source | Parameters | Output | Rows / bytes |
|---|---|---|---|---|
| 2026-11-26 | github.com/maja601/EuroCrops (CC BY-SA 4.0), raw files at commit `b4331adc3dec584ca0e86f0f2d5c881e53cb3b68` (2026-03-11) | `hcat_core/HCAT3.csv`, `csvs/country_mappings/fr_2018.csv`, `fr_other_years.csv`, `LICENSE` | `raw/eurocrops/2026-11-26/` | HCAT3: 384 classes (10,244 B, SHA-256 `47dcd2fcab18862a…`); fr_2018: 282 RPG codes (31,860 B, `3bad5f442691c7e0…`); fr_other_years: 41 codes (5,951 B, `8dfa01e9ab019570…`) |

The French mapping gives an HCAT3 class for 183 of the 198 crop codes of the well zones (98.6 % of their area; 119
distinct HCAT3 classes, 3 codes `not_known_and_other`); the 15 others are codes added after 2018. It is the EuroCrops
authors' mapping, used as the gold of the RPG → HCAT matching experiment (no labelling needed). Share-alike licence:
it stays a separate resource, not copied into the CC BY 4.0 ontology.

### CORINE Land Cover nomenclature guidelines, agricultural classes (R2.3, 2026-11-27)

The Eionet CLC vocabulary (`clc_eionet.rdf`, above) has labels but empty definitions, and the Copernicus Land
Monitoring Service site (`land.copernicus.eu`) refused or reset every connection on 2026-11-27. The official
"CORINE Land Cover nomenclature guidelines" pages of the eight agricultural classes used by the crop-class mapping
(`configs/lu_clc.csv`) were therefore taken from the Internet Archive's copies, as raw bytes (`id_` mode), into
`data/raw/vocab/clc_guidelines_2025-10-17/` (read only for their definitions; not redistributed):

| File | Original URL `https://land.copernicus.eu/content/corine-land-cover-nomenclature-guidelines/html/<file>` (archive snapshot, UTC) | Bytes | SHA-256 (first 16) |
|---|---|---|---|
| `index-clc-211.html` | 2025-10-17 19:07:55 | 19,763 | `9817be0608a070c0` |
| `index-clc-212.html` | 2025-10-17 19:08:07 | 16,416 | `555a593f79326a39` |
| `index-clc-221.html` | 2025-10-17 19:08:02 | 16,254 | `b3d1b954a409ee1a` |
| `index-clc-222.html` | 2025-10-17 19:07:48 | 20,281 | `628ba1bb280efc5f` |
| `index-clc-223.html` | 2024-05-03 08:56:38 | 15,259 | `1f70d78177489813` |
| `index-clc-231.html` | 2025-10-17 14:32:44 | 25,129 | `8dc7f841a30b2e8a` |
| `index-clc-241.html` | 2025-10-17 19:07:30 | 15,130 | `7b927e31c401aced` |
| `index-clc-242.html` | 2024-09-23 17:22:11 | 17,331 | `6413a22ff786efce` |
