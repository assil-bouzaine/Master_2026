# Step 8 (Phase 1): climate, rivers, weekly pumping and the model-ready dataset

**Date:** 2026-10-13 · **Status:** done

## What was done

| Script | What it does |
|---|---|
| `src/ingest/safran.py` | Downloads Météo-France SIM2 daily data year by year (2005–2026). Keeps the 141 cells of 8 km over the Pyrénées-Orientales and deletes the national file. |
| `src/ingest/hubeau_hydro.py` | Downloads daily mean flows of every river and canal gauge open since 2005 in dept 66 (45 with data). |
| `src/dataset/build.py` | Builds `data/processed/dataset_v1/`: weekly heads, SGI drought index, weekly forcings, river flows, weekly pumping, splits. |
| `src/dataset/load.py` | The single loader every model uses. Returns aligned arrays: heads `Y (weeks × wells)`, mask `M`, inputs `X (weeks × wells × 15)`, statics `S`, split labels. |

```bash
.venv/bin/python -m src.ingest.safran          # ~25 min the first time
.venv/bin/python -m src.ingest.hubeau_hydro    # ~40 min the first time
.venv/bin/python -m src.dataset.build
.venv/bin/python -m src.dataset.load           # shapes + figure
```

### Results

| | |
|---|---|
| Wells | **47** plain wells (the 33 core wells + 14 more used only for training) |
| Weeks | 1,135 (2005–2026); model window from 2012 |
| Train / validation / test | 2012–2019 / 2020 → Apr 2022 / **May 2022 → Oct 2026** |
| Observed well-weeks | train 14,013 · validation 4,960 · test 9,195 |
| Inputs per well and week | rain, ETP, actual ET, effective rain, drainage, runoff, temperature, soil wetness, plus groundwater and surface abstraction within 3 km, by use (15 in total) |
| Test period IPS classes | **43.5% "très bas"** (expected 10% in normal times) |
| Not validated ("Non qualifié") values | train 1.6% · validation 16.8% · **test 35.1%** |
| Rivers | 45 gauges; **no usable canal flow series** |

Figure: `reports/figures/dataset_v1_series.png` (rain + one well per aquifer type).

## Why

- **Why weekly.** Daily heads are noisy and have many gaps, while monthly
  data would hide the summer pumping cycle (2–4 m in the Pliocene). Weekly
  is the scale at which the processes we want to explain (recharge events,
  pumping seasons) are visible. Taccari et al. 2024 made the same choice.
- **Why climate from 2005 when the model starts in 2012.** Groundwater
  remembers past rain for months or years. Models like Pastas need a
  "warm-up" period of forcing before the first date they predict.
- **Why the SGI and the IPS classes.** The SGI turns a level into "how
  unusual is this for this month at this well". It is a standardised
  number, comparable between a karst well and a Pliocene well. Cutting it
  into BRGM's 7 classes ("très bas" … "très haut") gives us **discrete
  concepts**, which the reasoning-shortcut test needs. They also speak the
  same language as the official drought bulletins.
- **Why the SGI uses only the training years as reference.** If the test
  years helped define what "normal" is, information from the future would
  leak into the inputs.
- **Why the test period is hard.** 43.5% of test well-weeks are "très bas"
  compared with the training years. The model must predict levels it has
  never seen. That is the honest test of whether knowledge helps.
- **Why spread pumping with the water deficit.** The BNPE only gives one
  volume per year. Farmers irrigate when the soil is dry, i.e. when
  evapotranspiration exceeds rain, from April to October. So we distribute
  irrigation and canal volumes in proportion to that weekly deficit.
  Drinking water is spread evenly. It is an assumption, flagged so that
  Phase 2 can test its effect.

## What to consider

- **The test period is 35% unvalidated data.** Report test scores with and
  without "Non qualifié" weeks.
- **Pumping after 2023 is imputed** (BNPE stops in 2023, and 2023 itself is
  under-reported). The 2026 irrigation estimate is high because 2026 had
  the largest April–October water deficit since 2012 (671 mm vs a mean of
  500).
- **No canal flow data.** The "canal-return recharge" framing must rely on
  BNPE canal-intake volumes (annual) and on the shallow wells' behaviour.
  The figure shows something interesting at Millas (Têt alluvium): the
  level jumps every spring, when it hardly rains. That is a candidate
  signature of irrigation-canal water infiltrating. Check it on all
  alluvium wells in Phase 2 before claiming it.
- **Pumping is not yet assigned to an aquifer layer.** BNPE does not say
  whether a borehole taps the alluvium or the Pliocene; only 8% of points
  carry a BSS borehole code that could give the depth. For now the inputs
  are "abstraction within 3 km". Phase 3 links abstraction points to
  aquifer units in the knowledge graph.
- **THUIR (`760AE09`)** is in the core set but outside the BD LISA extract
  ("other" group). The karst and THUIR series are very flashy and will
  dominate errors in metres, so report metrics per aquifer group.

## Glossary additions

See `docs/notes/README.md`: SAFRAN, ETP, effective rain, drainage, SGI, IPS,
warm-up, data leakage.
