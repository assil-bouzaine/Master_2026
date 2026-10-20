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

## 5c. State at 2026-10-20 ~19:30 — RESUME HERE

**The Camber GPU allowance is used up.** Account Settings → Billing & Usage (Student plan):
GPU usage 99 %, CPU usage 100 % for the period 13 Oct – 13 Nov 2026 (renews 2026-11-13).
The platform stopped the node at 15:22 UTC (16:22 CET) during EA-LSTM trial 19; the
auto-stop watcher logged nothing because the sweep never ended. Steps 10 (2026-10-13) and
~4 h of the v3 sweep consumed the month's allowance.

**On the Stash** (`stash://assil0723/pfe_v3_run/results_gpu/v3/`, log `results_gpu/run_v3.log`):
- finished and already copied to `results/v3/`: `lstm`, `stgnn_distance`, `chronos2`,
  `chronos2_xl`, `chronos2_ft`, `lstm_tuned` + its four regimes, `stgnn_tuned`;
- finished, **not yet copied**: `stgnn_tuned_lwo`, `_f25`, `_f50`, `_refit`;
- `ealstm_tuning`: 19 of 24 trials complete in `study.db` (TorchScript loop version, before
  the fused kernel); best single-seed validation 0.604 (trial 18), 0.599 (trial 12).

**Not run yet:** EA-LSTM (5 trials, re-selection, 5 final seeds, 4 regimes) and Taccari
(default, tuning, regimes): about 56 + 80 training runs. With the fused EA-LSTM (`e09a482`)
and the strided Taccari (`b3a8b74`), roughly 1 h + 5 h on an L4 (estimate: the Taccari
epoch time on a GPU after `b3a8b74` has not been measured). If the runs move to another
GPU, restart the EA-LSTM tuning from trial 0 there, so that all 24 trials share one
implementation and one GPU; keep the Camber study as a record. On Camber after 13 Nov it
can resume (Optuna storage; the interrupted trial 19 stays RUNNING and is ignored).
`tests/test_ealstm.py` now also checks the GPU path (cuDNN, TF32 off during the check):
run it first on any new GPU.

**Laptop chain finished at 16:01** (`results/v3/cpu_runs5.log`), median over 33 core wells:

| Run | val NSE | drought NSE | drought skill | recovery NSE |
|---|---|---|---|---|
| LightGBM tuned, no own-climatology input | 0.56 | −0.12 | 0.47 | 0.58 |
| (LightGBM tuned with `clim_z`, for comparison) | 0.51 | −0.18 | 0.44 | 0.42 |
| LightGBM no-clim, leave-wells-out | 0.30 | −0.75 | 0.24 | 0.26 |
| LightGBM no-clim, 25 % / 50 % training data | 0.56 / 0.59 | −0.26 / −0.32 | 0.34 / 0.50 | 0.35 / 0.48 |
| Pastas WellModel | 0.51 | −0.68 | n/a in the log | −0.03 |

- Re-selection worked as intended again: single-seed best trial 18 (0.583) fell to a
  3-seed mean of 0.528; trial 17 (3-seed 0.541) was kept.
- **Dropping `clim_z` did not cost skill; it improved every split.** So the like-for-like
  LightGBM (no own-climatology input) can be the LightGBM baseline with no loss; the `clim_z`
  version stays as a sensitivity row. Decision still for Assil and the supervisor.
- The WellModel (pumping wells as separate stresses) is no better than the summed 3 km
  stress of `pastas_seasonal_canal` (drought −0.68 vs −0.73). Reported either way.

**Camber CLI:** still "authentication error: failed to get token" at 19:05 (Assil had logged
in to the web app). Assil runs `! camber login` in the Claude Code prompt (if it fails
again: `! camber update`, then `! camber login`).

**Resume checklist:**
1. CLI login, then bring back `stgnn_tuned_{lwo,f25,f50,refit}`, `ealstm_tuning` and
   `run_v3.log` (`camber stash cp -r stash://assil0723/pfe_v3_run/results_gpu/v3/<run>
   results/v3/<run>`), rescore with `src.models.evaluate`.
2. Assil chooses where the remaining GPU runs go (Kaggle, Colab, or Camber after 13 Nov).
3. `python -m src.models.ensemble`, `python -m src.analysis.baseline_report` with what
   exists (EA-LSTM and Taccari marked pending), this note, `docs/results_baselines.md`,
   the Gate 2 addendum.
4. Phase 3 (ontology, CPU only) does not wait for the GPU runs.

## 5b. State at 2026-10-20 ~13:20 (after a PC crash at ~12:52)

**Laptop** (`results/v3/cpu_runs3.log`): naive ✅, LightGBM default ✅, Pastas ✅,
LightGBM re-selection running (resumable, `lgbm_tuned/reselect.json`), then WellModel.
Run only **one heavy job at a time** on the laptop: the crash most likely came from
memory exhaustion (LightGBM + a Chronos-2 fine-tuning test + a Taccari profile at once).

**Pastas on v3** (median over 33 core wells, `pastas_seasonal_canal`): validation NSE
0.45 (v2: 0.28), drought NSE −0.73 (v2: −0.52), drought skill 0.20 (v2: 0.24). Better
calibration, most likely because v3 removed the fake 2018 step in groundwater pumping
inside the calibration period; slightly worse in the drought. Report both.

**Tuner fix applied** (commit `a4a578a`): LightGBM trial 15 = 0.573 with seed 0, 0.439
and 0.410 with seeds 1 and 2 → 3-seed mean 0.474 (winner's curse confirmed).

**GPU sweep on the Camber node** (GPU · Xsmall, started 11:35 UTC, restarted 11:43 UTC):
- The CLI-uploaded `pfe_v3/` folder is read-only on the node (owned by root), so the bundle
  is unzipped into **`~/pfe_v3_run`** (= `stash://assil0723/pfe_v3_run/`), created from
  the node; results in `~/pfe_v3_run/results_gpu/v3/`, log `results_gpu/run_v3.log`.
- Done before the restart: `lstm`, `stgnn_distance` (5 seeds each, ~1 min each).
- New order: `chronos2 chronos2_xl chronos2_ft tune:lstm tune:stgnn regimes:lstm
  regimes:stgnn tune:ealstm regimes:ealstm taccari tune:taccari regimes:taccari`.
- `scripts/gpu_autostop.py` watches the sweep's PID and shuts the node down 10 min after
  it ends (`results_gpu/autostop.log`). Still check that the node shows "Stopped".
- **Taccari took ~45 s/epoch** (full dilated stack over every node and week). Commit
  `b3a8b74` evaluates only the positions the next layer reads (exact, 4.2× on CPU).
  **Upload it before the `taccari` step starts:** `camber stash cp src/models/taccari.py
  stash://assil0723/pfe_v3_run/patch/`, then in a notebook cell
  `cp ~/pfe_v3_run/patch/taccari.py ~/pfe_v3_run/src/models/taccari.py` and compare
  `md5sum` with the laptop copy.
- After the crash the Camber CLI token is invalid: Assil runs `! camber login`; Chrome must
  be open for the extension.

**Update 2026-10-20 ~13:40.** Both speed-ups are on the node (md5 checked): Taccari strided
TCN (`b3a8b74`) and EA-LSTM TorchScript (`a5956a1`, 1.6× on the L4). Finished GPU runs
(lstm, stgnn_distance, chronos2 ×3, lstm/stgnn tuned, lstm regimes) were copied to
`results/v3/` and rescored on the laptop. Interim medians over the 33 core wells:

| Simulation | val NSE | drought NSE | drought skill | recovery NSE |
|---|---|---|---|---|
| Pastas seasonal+canal | 0.45 | −0.73 | 0.20 | −0.04 |
| LightGBM tuned (3-seed re-selection) | 0.51 | −0.18 | 0.44 | 0.42 |
| LSTM default / tuned | 0.54 / 0.66 | −0.07 / +0.01 | 0.56 / 0.56 | 0.28 / 0.46 |
| ST-GNN distance default / tuned | 0.52 / 0.66 | +0.03 / −0.09 | 0.37 / 0.54 | 0.23 / 0.39 |

Forecast, drought NSE (skill vs anomaly persistence): Chronos-2 4 wk 0.78 (0.26) zero-shot,
0.79 (0.27) cross-learning, 0.81 (0.30) fine-tuned; 12 wk 0.37 / 0.40 / 0.35 (0.31–0.33).

**LightGBM's own-climatology input.** `clim_z` (each well's training climatology, computed
from its heads) is LightGBM's dominant feature; the networks never get it, and it would leak
in R2/R3. Commit `60e9872` adds `lgbm --no-clim` (tuned with the same budget) and its
regimes; queued on the laptop after the WellModel (`results/v3/cpu_runs4.log`). Both
LightGBM rows will be reported; which one is "the" LightGBM baseline is for Assil and the
supervisor (the no-clim one is the like-for-like comparison).

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
