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
