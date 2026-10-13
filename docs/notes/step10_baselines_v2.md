# Step 10: improving the baselines (dataset v2, tuning, ensemble, ablation)

**Date:** 2026-10-13 · **Status:** done

## What was done

| Change | How |
|---|---|
| Versioned data and results | `src/config.py`: `PFE_DATASET` (v1/v2/v2a/v2b) and `PFE_RESULTS`. v1 is untouched in `results/v1/`. |
| Longer history | SAFRAN from 2000; training from **2005** (v1: 2012). BNPE pumping for 2005–2011 back-filled with each ouvrage's 2012–2014 mean (flagged `imputed`). |
| More wells | **65 dept-66 wells** (v1: 47 plain wells). Same 33 core wells for reporting. Training well-weeks 29,847 (v1: 14,013). |
| Pumping scope | The whole département (v1: the plain + 3 km). |
| LSTM tuning | `src/models/tune_lstm.py`, Optuna, 24 trials, **chosen on validation only**. Best: look-back 104 weeks, hidden 128, dropout 0.19, lr 0.0024. |
| Ensemble | `src/models/ensemble.py`: every subset of the simulation models, chosen on validation. Selected: **LightGBM + tuned LSTM**. |
| Ablation | v2a = v1 wells + history from 2005; v2b = all wells + training from 2012. Separates the two v2 changes. |
| Significance | Paired Wilcoxon test on per-well NSE (33 core wells). |

GPU runs (ST-GNN, Chronos-2, LSTM, tuning, ablations) ran on the Camber
L4 node through the Chrome extension; laptop runs: naive, Pastas,
LightGBM. Full table: `docs/results_baselines.md` (v1 vs v2 columns).

## Results (median NSE over 33 core wells)

| Model | Validation v1 → v2 | Test v1 → v2 |
|---|---|---|
| LightGBM (simulation) | 0.54 → 0.49 | **0.03 → 0.20** |
| LSTM (default) | 0.58 → 0.51 | 0.25 → 0.24 |
| **LSTM tuned** (v2) | — → **0.63** | — → 0.24 |
| Distance ST-GNN | 0.58 → 0.46 | 0.26 → 0.24 |
| **Ensemble LightGBM + tuned LSTM** (v2) | — → 0.62 | — → **0.25 (RMSE 0.587 m, the lowest)** |
| Pastas (best variant) | 0.50 → 0.28 | 0.13 → 0.06 |
| LightGBM forecast 12 wk | 0.44 → 0.48 | 0.04 → 0.16 |
| Chronos-2 forecast 4 / 12 wk | unchanged | 0.83 / 0.42 (unchanged) |

**Ablation** (test NSE; validation in brackets):

| Dataset | ST-GNN | LSTM |
|---|---|---|
| v1: plain, from 2012 | 0.27 (0.58) | 0.25 (0.58) |
| v2a: plain, from 2005 | 0.30 (0.55) | 0.34 (0.57) |
| v2b: all wells, from 2012 | 0.35 (0.53) | 0.22 (0.59) |
| v2: both | 0.24 (0.46) | 0.24 (0.51) |

**Significance** (paired Wilcoxon on per-well test NSE vs v1):
- **none of the data changes is significant** (p = 0.24–0.82; each helps
  about half the wells)
- **tuning is significant on validation** (29/33 wells better, p < 0.001)
  but not on test (p = 0.20)
- the ensemble beats v1's best in about 2/3 of wells, not significantly
  (p = 0.11–0.32)

## Why it matters (the honest reading)

1. **More data does not fix the drought.** Seven more years or 32 more
   wells change the drought score by amounts indistinguishable from noise.
   The models are not short of *examples*; they are short of
   *information*.
2. **Tuning and ensembling improve normal years, not the drought.**
   Validation rises to 0.62–0.63 (significant), while the test stays near
   0.25 for every model. That ceiling is the same in every experiment.
3. **The ceiling has a known cause** (Step 9 hydrographs): no input shows
   that summer pumping intensified in the drought, or which aquifer layer
   each borehole draws from. The knowledge graph (Phase 3) targets exactly
   that. This is now the central argument of the paper, backed by
   significance tests.
4. **Pastas suffers from the back-filled pumping:** a physics-style model
   trusts its inputs, and 2005–2011 pumping is only an estimate. For Pastas,
   the v1 calibration (2012+) is the reference.

## Baselines of record (for the paper)

| Task | Reference | Test NSE |
|---|---|---|
| simulation | ensemble LightGBM + tuned LSTM (v2) | 0.25 (RMSE 0.587 m) |
| simulation, hydrology reference | Pastas seasonal + canal (v1) | 0.13 |
| forecast 4 wk | Chronos-2 zero-shot | 0.83 |
| forecast 12 wk | Chronos-2 zero-shot | 0.42 |

## What to consider

- Report validation **and** test, plus the Wilcoxon tests, in the paper.
  Do not cherry-pick the best test row (v2b ST-GNN 0.35 was not selected on
  validation and is not significant).
- **Camber lesson:** folders uploaded from the laptop are read-only for the
  job. Use `PFE_RESULTS=results_abl/<v>` and copy the feature panel in
  (`docs/gpu_howto.md`).
- **Possible next data:** monthly drinking-water production and the aquifer
  layer of each abstraction point. These are expected to move the
  drought score where more data did not.
