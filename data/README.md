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
