# Step 12a: fixing the evaluation, the data and the baselines (from the review)

**Date:** 2026-10-20 · **Status:** in progress · **Why this step exists:** the
critical review in `docs/feedback.md` found problems that would weaken every later
result (evaluation, pumping inputs, missing regimes, unequal tuning). They are fixed
*before* the ontology phase, because the ontology's value is measured against these
baselines.

## 1. Evaluation (done, commit `5d00bee`)

| Fix | Before | Now | Why it matters |
|---|---|---|---|
| Test sub-periods | one test window May 2022 → Oct 2026 | **drought** May 2022 → Nov 2025, **recovery** Dec 2025 → (`src/config.py`) | the old headline (test NSE 0.25) mixed two regimes; the boundary is fixed from observed SGI, not from model scores |
| KGE | β = mean(sim)/mean(obs) on heads in m NGF | **KGE''** (Tang et al. 2021, doi:10.1175/JCLI-D-21-0067.1): β = (mean(sim) − mean(obs))/sd(obs) | 12 of 33 core wells have a mean head below 5 m NGF: the old β depended on the datum |
| Benchmark-relative skill | none | `skill = 1 − MSE/MSE(climatology)` (simulation), vs anomaly persistence (forecast) | NSE in a sub-period uses that sub-period's mean as benchmark, which already "knows" the drought (Schaefli & Gupta 2007, doi:10.1002/hyp.6825) |
| Statistics | per-well Wilcoxon, ad hoc (not in a script) | `src/analysis/stats.py`: cluster bootstrap over 10 km cells, paired Wilcoxon, Holm | wells are not independent (nested piezometers, neighbours) |
| Analysis plan | none | `docs/analysis_plan.md` | endpoints, periods, regimes, tuning budget and tests fixed before new runs |

**How the drought/recovery boundary was chosen.** The median SGI of the 33 core
wells stays between −0.6 and −1.9 from late 2022 to November 2025 (with a relapse in
Oct–Nov 2025), then turns positive. The rule: the recovery starts on the first month
from which the median SGI stays ≥ −0.5 for three months. Both SGI references (v1:
2012–2019, v2: 2005–2019) give December 2025.

**What the rescoring of v2 showed** (median over 33 core wells):
- In the drought phase every simulation model has a negative NSE (−0.12 to −0.52),
  but the ML models remove 40–51 % of the error of a "normal year".
- After clustering and Holm correction, **no ML baseline is significantly better than
  Pastas in the drought phase** (Holm p ≥ 0.24). The step-10 claims rested on tests
  that treated wells as independent.
- Single LSTM seeds score −0.40 ± 0.19 in the drought, the 5-seed average −0.12:
  averaging seeds helps a lot exactly where it matters.

## 2. Dataset v3 (built)

See `data/README.md` ("BNPE snapshot of 2026-10-20", "VigiEau", "Model-ready dataset
v3") for every number. In short:

1. **BNPE 2024 is published** (a dated snapshot keeps v1/v2 reproducible).
2. **177 rows of 2024 had no usage code**, and 163 of them were the canal intakes.
   Before restoring the usage, 2024 canals looked like 1 Mm³ ("missing"); after, 76.5
   Mm³. Lesson: *check why data look missing before imputing them.*
3. **The 2018 jump of groundwater irrigation is a reporting change** (708 boreholes
   declaring for the first time); they are back-filled to 2012.
4. **Missing declarations in the latest years** are filled by the ratio of the
   ouvrages that declared both years (per source × use × zone).
5. **Years without data (2025–26)** for surface water are decided by the official
   drought orders of the Têt surface-water zones (VigiEau): a year with ≥ 30 days of
   "crise" in April–September is "restricted". Only 2023 (145 days) and 2024 (183
   days) qualify since 2012.
6. **Leak fixed:** the artesian share (a static input) was computed over the whole
   record, test included.
7. **New inputs:** river discharge (Têt, Agly, Tech and the nearest main-stem gauge);
   the canal input now covers the plain only.

**Why not use the restriction orders as a model input?** Groundwater alert zones are
triggered by piezometers of the very aquifers we predict: that would leak the target.
Surface-water zones are triggered by river flow, which the models can already see
through the river inputs. The orders are used only to classify restricted years for
the imputation.

## 3. Baselines (in progress)

| Change | File | Status |
|---|---|---|
| Equal tuning budget: Optuna, 24 trials, validation only, for LightGBM, LSTM, EA-LSTM, distance ST-GNN, Taccari ST-GNN | `lgbm.py --tune`, `tune.py` | code done |
| True EA-LSTM (statics drive the input gate) | `lstm.py --arch ealstm` | code done |
| Regimes: leave-wells-out (5 folds), 25/50 % of the training period, refit on train + validation | `lstm.py`, `stgnn.py`, `regimes.py` | code done |
| Taccari-style graph baseline (weather, river, pumping-field and canal nodes; distance rules; MTGNN-style network) | `taccari.py` | code done |
| Pastas WellModel: every abstraction point within 5 km with a distance-scaled Hantush response | `pastas_baseline.py` (`pastas_wellmodel`) | running |
| Chronos-2: cross-learning across wells, fine-tuning on the training period | `chronos2.py --mode xl / ft` | code done |

## 4. Knowledge-graph pre-check (done; `docs/kg_precheck.md`)

`python -m src.analysis.kg_precheck` asks, before Phase 3, whether the relations the
knowledge graph would encode explain how wells co-vary *beyond distance*. It uses only
training and validation weeks.

- **Raw** correlations of weekly anomalies are ~0.3 at every distance: the plain-wide
  climate signal dominates.
- **After removing that regional signal**, co-variation is local: wells in the **same
  BD LISA entity and within 5 km** keep a median partial correlation of 0.32 (other
  pairs ≈ 0). In the regression: +0.21 (QAP p = 0.048). Wells at **similar screen
  depth** co-vary more (−0.043 per 100 m of depth difference, p = 0.002). Nested
  piezometers co-vary strongly. Similar pumping neighbourhoods add nothing significant
  (p = 0.18).
- The 3-nearest-wells **distance graph joins different entities in 53 %** of its edges.

**Meaning for RQ1.** The knowledge graph has information a distance graph lacks: at
short range it can keep same-unit, similar-depth neighbours and drop the others. The
pumping relation (`pumpsFrom`) is not supported by this check yet; its value must come
from better layer assignment of the boreholes (Phase 3).

**Why a permutation (QAP) test?** Every well appears in many pairs, so pairs are not
independent and ordinary regression p-values would be far too small. QAP permutes the
labels of the wells (e.g. which entity each well belongs to), rebuilds every pair
attribute and refits; the p-value is the share of permutations with an effect at least
as large.

## 5. Where we stopped (2026-10-20, ~10:35) and how to resume

**Results so far on v3 (laptop):** naive floors; LightGBM default (validation 0.51,
drought NSE −0.28, drought skill 0.39) and LightGBM tuned (validation 0.43, drought
−0.36, skill 0.40). Pastas variants were running when the PC was shut down (they
resume per well).

**Finding: single-seed tuning picks lucky seeds.** The best of the 24 LightGBM trials
scored 0.573 on validation with seed 0, but the same configuration averaged over 5
seeds scored only 0.431, below the untuned default (0.509). Each Optuna trial uses one
seed, so the maximum over 24 trials favours a configuration that was lucky once (the
"winner's curse"). **Fix before the GPU sweep:** in `src/models/tune.py` and
`lgbm.tune()`, re-evaluate the 3 best trials with 2 more seeds (validation only) and
keep the best 3-seed mean; record it in `docs/analysis_plan.md` §5 (same rule for every
model, so the budget stays equal).

**Smoke tests (1 seed, 1 epoch, results in a scratch folder):** passed for LSTM,
EA-LSTM, leave-wells-out fold, refit, 25 % data, distance ST-GNN, Taccari, the tuner
(EA-LSTM; Taccari through a fixed small trial) and the regimes driver (5 LSTM folds
assembled and scored). Not finished: Chronos-2 `--mode xl` and `--mode ft` (they will
run first on the GPU; check the log).

**Resume checklist (next session):**
1. Restart the laptop chain (resumable): `nohup bash scripts/run_cpu.sh > results/v3/cpu_runs2.log 2>&1 &`
   with `STEPS="lgbm_tuned pastas wellmodel"` after the tuner fix of item 2.
2. Implement the top-3 × 3-seed re-selection (above), rerun `lgbm --tune 24` (the
   Optuna study is cached; only the selection and the final seeds rerun).
3. Assil: `! camber login` (OAuth in the browser; the CLI token expired on 2026-10-20).
4. `PFE_DATASET=v3 .venv/bin/python scripts/make_gpu_bundle.py`, upload with
   `camber stash cp gpu_bundle.zip stash://assil0723/pfe_v3/`, start the GPU node in the
   web app (Chrome), run `scripts/run_gpu.sh` (v3 section of `docs/gpu_howto.md`),
   **stop the node** at the end.
5. Bring the runs back, `python -m src.models.ensemble`, `python -m
   src.analysis.baseline_report`, update this note, `docs/results_baselines.md`, the Gate
   2 addendum.
6. Then Phase 3 (the knowledge-graph pre-check is done: `docs/kg_precheck.md`).

## What to consider

- The WellModel is slow (minutes per well) and, on a first test, fitted Millas worse
  than the summed 3 km stress. Report it honestly either way.
- Cross-learning in Chronos-2 must batch *wells at the same date*, never dates of one
  well, or later contexts leak into earlier forecasts.
- The Taccari baseline and the future knowledge-graph model share the same network and
  node types; only the edges differ. That is what makes RQ1 a clean test of the edge
  semantics.

## Glossary additions

| Term | Meaning |
|---|---|
| **Sub-period** | A part of the test window scored separately (here: drought, recovery). |
| **Benchmark-relative skill** | 1 − error of the model / error of a simple reference; 0 = no better than the reference. |
| **Cluster bootstrap** | Resampling whole groups (here 10 km cells) instead of single wells, so that wells that move together are not counted as independent evidence. |
| **Holm correction** | Adjusts p-values when many comparisons are made, so "significant" keeps its meaning. |
| **Snapshot** | A dated copy of a download that is never overwritten, so an old dataset can be rebuilt exactly. |
| **Consolidation lag** | Recent years of an administrative database are incomplete because declarations arrive late. |
| **Ratio imputation** | Filling a missing value with last year's value × the change observed in units that reported both years. |
| **EA-LSTM** | Entity-aware LSTM: the static attributes of a site decide how much new input enters the memory. |
| **Leave-wells-out** | Training without some wells and testing on them, to measure generalisation to unmonitored places. |
| **Cross-learning** | A foundation model forecasts several series jointly and shares information between them. |
