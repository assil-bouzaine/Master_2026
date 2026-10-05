# Step 4: Hub'Eau piezometers (groundwater levels)

**Date:** 2026-10-05 · **Status:** done

## What was done

| Script | What it does |
|---|---|
| `src/ingest/hubeau_piezo.py` | Downloads the station list for dept 66, then the full series of every station. Each station is saved separately. |
| `src/analysis/piezo_profile.py` | Computes per-station statistics, applies the working-set filters, extracts the 2016–2025 series, and draws the map. |
| `src/config.py`, `src/web.py` | Shared paths, and an HTTP session with automatic retries. |

Run them with:

```bash
.venv/Scripts/python -m src.ingest.hubeau_piezo     # ~1.5 min first time, instant afterwards
.venv/Scripts/python -m src.analysis.piezo_profile
```

### Results

| | Rebuild (Oct 2026) | First run (Aug 2026) |
|---|---|---|
| Stations in dept 66 | **101** | 98 |
| ≥ 8 years and active in 2024+ | **43** | 45 |
| … and ≥ 50 obs/year | 43 | n/a |
| … and inside the plain = **working set** | **33** | 34 |
| Pliocene multilayer `671AA00` | 20 (median record 35.6 y) | 20 (median 35 y) |
| Quaternary alluvium (`718BP0x` + `671AB0x`) | 6 | ~7 |
| Corbières karst `681AM00` | 6 | 2 |
| Other (`760AE09`, Aspres) | 1 | n/a |
| Measurements 2016–2025, working set | **115,443** | "~309k" (see below) |

Map: `reports/figures/piezo_stations_record_length.png`.

## Why

- **What a piezometer measures.** A piezometer is a borehole where a sensor
  records the water-table level, usually once a day. Hub'Eau gives two
  values per measurement:
  - `niveau_nappe_eau`: the level as an altitude in metres NGF (above sea
    level). **This is our target variable.** It can be compared between
    stations.
  - `profondeur_nappe`: the depth below the ground surface.
- **Why one file per station.** Last time, a single big download timed out
  and had to restart from zero. Now each station is a separate file, and a
  file is only written once it is complete ("atomic write"). If the power
  cuts at station 60, a rerun picks up at station 61.
- **Why follow `next` instead of counting pages.** The API itself tells us
  the URL of the next page, and HTTP code 206 means "partial content, more
  to come". Following that link is robust if the API changes its paging.
- **Why these filters.**

  | Filter | Reason |
  |---|---|
  | ≥ 8 years of record | Enough history to see several dry and wet years and the seasonal cycle. A deep-learning model needs that variety. |
  | Active in 2024+ | Old, closed stations can't be used to predict the present. |
  | ≥ 50 obs/year | At least weekly data. Coarser series can't capture seasonal dynamics. |
  | Inside the plain | We model one aquifer system (Master's scope). |

- **Why 2016–2025 as the common window.** Every working-set station has data
  in it, and it matches the RPG land-use editions (2016 and 2023) and the
  AlphaEarth embedding years we will use later.

## What to consider

### 1. The "309k measurements" in CLAUDE.md was probably mislabelled

Over 2016–2025, 33 daily stations can produce at most ~120k measurements, so
309k is impossible for that window. The working set's **full** history
(since the 1960s–70s) is **303k**, almost exactly the old figure. The first
run most likely counted the full record and called it "2016–2025". The
correct number for the window is **115k**. **Update CLAUDE.md §8** when you
have a moment.

### 2. The working set is unbalanced across layers

There are 20 stations in the deep Pliocene and only 6 in the shallow
alluvium. A GNN will learn the Pliocene well and the alluvium poorly. Keep
this in mind when reporting errors: report them **per layer**, not just as
one average.

### 3. Corbières karst stations: keep them or not? (question for the supervisor)

The box includes six karst stations at Salses, on the northern edge (four
more than the first run, mainly because their records got longer). Karst
behaves very differently from sands and clays: the water flows through
conduits and reacts within days. Two options:

- **Keep them** as *boundary nodes*. The Corbières karst is known to feed
  the Pliocene laterally near Salses.
- **Drop them**, and work only on the 26 "core" stations (`671AA*`,
  `671AB*`, `718BP*`).

Both subsets are available through the `layer` column. Decide at Gate 2.

### 4. Data quality

- The median share of missing days in the window is only 1.6%.
- Two stations have large gaps: `10915X0316/F3` (Pia) is missing 36% of days
  and `10911X0219/HIPPO2` 28%.
- 19% of window measurements are marked "Non qualifié" (not yet validated by
  BRGM) rather than "Correcte". The share grows over time:

  | Year | Not yet validated |
  |---|---|
  | 2016 | under 1% |
  | 2021 | ~30% |
  | 2025 | **52%** |

  Validation lags behind measurement. We keep these values but flag them.
  Train the model with and without them as a check, and choose the test
  period knowing that recent data are less checked.

### 5. Other points

- **Station-metadata dates are not always reliable.** The station table's
  `date_fin_mesure` and `nb_mesures_piezo` can lag behind the real series.
  All statistics here are computed from the downloaded series, not from the
  metadata.
- **Rerunning the download** with `--refresh` will add the newest days. The
  counts will then move slightly. That is expected; log the new date in
  `data/README.md`.
