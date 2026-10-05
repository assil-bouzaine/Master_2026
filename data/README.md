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
