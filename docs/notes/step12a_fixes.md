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
  version stays as a sensitivity row. **Decided (Assil, 19:40):** `lgbm_noclim_tuned` is the
  LightGBM row and the only LightGBM ensemble candidate (`docs/analysis_plan.md` §5).
- The WellModel (pumping wells as separate stresses) is no better than the summed 3 km
  stress of `pastas_seasonal_canal` (drought −0.68 vs −0.73). Reported either way.

**Camber CLI:** still "authentication error: failed to get token" at 19:05 (Assil had logged
in to the web app). Assil runs `! camber login` in the Claude Code prompt (if it fails
again: `! camber update`, then `! camber login`).

**Update ~20:00.**
- Camber CLI works again; `stgnn_tuned_{lwo,f25,f50,refit}` copied and rescored, the 19 Camber
  EA-LSTM trials kept as `results/v3/ealstm_tuning_camber/` (record only), log as
  `results/v3/run_v3_camber.log`.
- **Kaggle:** logged in (`assilbouzaine`, 30 GPU-h per week, refresh 2026-10-24). The first
  kernel ran **without a GPU**: the account is not phone-verified, and Kaggle then silently
  gives a CPU session (quota still 0.00 h used). It also showed that a venv on Kaggle's
  Python 3.13 image has no pip and does not see the image's packages. Fixed in `ebbd892`
  (pins in a `PYTHONPATH` folder; the kernel stops at once without a GPU). Waiting for Assil's
  phone verification, then `scripts/kaggle_gpu.py push`.
- **Interim v3 report** (`docs/results_baselines.md`, EA-LSTM and Taccari not run yet):
  ensemble = tuned LSTM + tuned distance ST-GNN (validation 0.68; drought NSE 0.02, skill
  0.55; recovery 0.44). Against Pastas seasonal+canal, clustered bootstrap + Holm: tuned
  LightGBM (no clim), both LSTMs, the tuned distance ST-GNN and the ensemble are
  **significantly better in the drought** (p_holm 0.002–0.04); in the recovery only LightGBM
  is (p_holm 0.001). On v2 no ML baseline was significantly better: Pastas lost drought skill
  on v3 (NSE −0.52 → −0.73) while the networks gained. Unseen wells (R2) hurt every model,
  the LSTM most (drought NSE −1.56), the distance graph least (−0.42); 25–50 % of the
  training period costs little (R3), as on v2. Pastas WellModel: better on the Pliocene
  (drought −0.30 vs −0.49), much worse on the recent alluvium (−6.51, 4 wells).
- **Correction (2026-10-23, Step 12b):** "significantly better" above comes from the
  per-well Wilcoxon test, which treats wells as independent. With the cluster sign-flip test
  of analysis plan v2, the same comparisons give p_holm 0.08–0.23 in the drought (effects
  unchanged and large). Only LightGBM's recovery NSE stays significant (p_holm 0.039).
  "R2 unseen wells" now reads "left-out monitored wells".
- The Gate 2 addendum waits for EA-LSTM and Taccari, so the supervisor gets one v3 update.

**Update ~20:25: Kaggle phone verification does not work from Tunisia (no SMS arrives), so
EA-LSTM moves to the laptop.** Measured on the laptop CPU (4 threads): EA-LSTM 208 weeks ×
hidden 128 **55 s/epoch** (the fused kernel; the old loop took 38 s/epoch on the Camber L4),
Taccari default **163 s/epoch** (≈ 100 h for its 80 runs: needs a GPU). Started
`STEPS="ealstm_tune ealstm_regimes" bash scripts/run_cpu.sh` → `results/v3/cpu_runs6.log`
(20:23, 3 torch threads via `PFE_THREADS`, one core left free). The tuning **resumes the
Camber study** (copied to `results/v3/ealstm_tuning/`; the interrupted trial 19 marked FAIL;
`ealstm_tuning_camber/` stays as the raw record): a restart would cost ~10 h of CPU, and the
19 trials are FP32 runs of the same function (loop on the L4, fused kernel here; tested equal).
Estimate: tuning ~7–8 h (5 trials + 6 re-selection runs + 5 final seeds), regimes ~15 h;
resumable after a power cut (only the current run is lost). Taccari: Kaggle if the
verification works, otherwise Camber after 2026-11-13.

**Update ~21:35: laptop run stopped at Assil's request (end of the session).** The script
was killed first (so it could not start `ealstm_regimes`), then the tuner, during trial 24
(epoch 11); trial 24 was marked FAIL in `results/v3/ealstm_tuning/study.db`. The study now
has **23 complete trials** + 2 failed (19 on Camber, 24 here); the laptop added trials 20–23
(validation 0.48, 0.42, 0.52, 0.58). Best single-seed: trial 18 0.604, trial 12 0.599, trial
23 0.575 (all lookback 208, hidden 128), so these are the re-selection candidates unless the
last trial beats them. A 208/128 trial takes 17–24 min on 3 threads. **Left:** 1 trial + 6
re-selection runs + 5 final seeds ≈ 4 h, then the 4 regimes (40 runs) ≈ 11–15 h. Restart
(it continues where it stopped):
`STEPS="ealstm_tune ealstm_regimes" setsid nohup bash scripts/run_cpu.sh > results/v3/cpu_runs7.log 2>&1 < /dev/null &`.
Nothing else was running: the Camber node was already stopped by the platform, and no
Kaggle kernel was running (the account is still not phone-verified).

**Update 2026-10-23 13:40.** Restarted with the command above (`results/v3/cpu_runs7.log`);
Optuna reopened the existing study (23 complete, 2 failed). Assil confirmed that Kaggle's
phone verification does not work from Tunisia, so **Kaggle is dropped**. Only Taccari still
needs a GPU (≈ 100 h on the laptop). Options without an SMS code, proposed to Assil:
- **Google Colab, free T4** (recommended): a Google account is enough. Google publishes no
  fixed limits; sessions can stop without warning and need the tab open. Results go to
  Google Drive after every run (the Drive permission is Assil's click, each session).
- **Modal:** $30 of compute per month (L4 ≈ $0.80/h, T4 ≈ $0.59/h), run from the laptop
  terminal, keeps running with the laptop off. modal.com/pricing does not say whether a
  payment card is needed.
- **Lightning AI:** up to 30 free credits (≈ 80 h on interruptible GPUs, valid 12 months),
  no card, but it asks for a phone number.
- **Camber** after the allowance renews (2026-11-13): the fallback.
- Not useful: SageMaker Studio Lab also needs an SMS code and caps the GPU at 4 h a day.
Phase 4 (~300 runs of the same network) needs more than the free tiers: ask the supervisor
at Gate 2 whether the lab, the university or a SAVE Water partner has a GPU we can use.

**Update 2026-10-23 14:10: Taccari runs on Google Colab (Assil chose it).** Notebook
`pfe_v3_gpu.ipynb` (Assil's Drive), free T4; the bundle was uploaded in three 7 MB parts (the
Chrome extension uploads at most 10 MB per file) and copied to Drive `pfe_colab/`.
`scripts/colab_run.py` (new) restores earlier results from Drive, installs the pins, runs
`tests/test_taccari.py`, then `taccari tune:taccari regimes:taccari`, copying the results to
Drive every 5 min (Optuna databases through SQLite's backup API). First attempt stopped at the
test: `tests/` had no `__init__.py` and another `tests` package on Colab's path won; fixed
(`tests/__init__.py`). **Taccari default: 10 s per epoch on the T4** (laptop 163 s), so the
~80 runs should take a few GPU-hours. How to resume or bring results back: `docs/gpu_howto.md`,
Colab section (`scripts/colab_pull.py` on the laptop). Laptop: EA-LSTM trial 25 (the 24th
complete) gave 0.484; the re-selection of the top 3 (trials 18, 12, 23) follows.

**Update 2026-10-23 20:50: Taccari finished on Colab; EA-LSTM regimes running.**
- **Colab** (log `run_colab.log` on Drive, read in the Drive preview): `done` at 18:40 UTC,
  131 files on Drive `pfe_colab/results_gpu`; not pulled to the laptop yet. The re-selection
  picked trial 15 (3-seed validation 0.582: lookback 156, hidden 64, dropout 0.229,
  lr 8.2e-4) over trial 12 (best single seed 0.620, 3-seed mean 0.560). Medians over the 33
  core wells as Colab printed them (no skill column until `colab_pull.py` rescores):

  | run | NSE validation | NSE drought | NSE recovery |
  |---|---|---|---|
  | `taccari` | 0.527 | −0.162 | 0.394 |
  | `taccari_tuned` | 0.633 | −0.107 | 0.457 |
  | `taccari_tuned_lwo` | 0.317 | −0.399 | 0.147 |
  | `taccari_tuned_f25` | 0.477 | −0.220 | 0.145 |
  | `taccari_tuned_f50` | 0.492 | −0.072 | 0.208 |
  | `taccari_tuned_refit` | (in sample) | −0.079 | 0.537 |
- **Laptop:** the re-selection picked trial 12 (3-seed validation 0.540) over trial 18
  (0.531) and trial 23 (0.538). `ealstm_tuned` (5 seeds, 17:46): validation 0.489, drought
  NSE −0.264 (skill 0.344), recovery 0.411 (skill 0.479). The regimes started at 17:47; at
  20:45 run 7 of 40 (LWO fold 1, seed 1), ≈ 29 min per full-data run; estimate: all done
  ≈ 09:00–10:00 on 24 Oct.
- **20:58: the EA-LSTM regimes on v3 were stopped (Assil's decision).** v4 redoes them (its
  GPU plan has `regimes:ealstm`). 19 of the 34 missing runs used the v3 leave-wells-out folds,
  which split twin wells 20 m apart (C2-1/C2-2), so their scores would be optimistic by
  design; the other 15 only filled the interim v3 table. The tuning (reused by v4) and the 5
  final seeds were finished. Kept as a record, not reported: `ealstm_tuned_lwo` fold 0
  (5 seeds) and fold 1 seed 0. The v3 report shows the EA-LSTM in R1 only.

**Resume checklist:**
1. ✅ CLI login, then bring back `stgnn_tuned_{lwo,f25,f50,refit}`, `ealstm_tuning` and
   `run_v3.log` (`camber stash cp -r stash://assil0723/pfe_v3_run/results_gpu/v3/<run>
   results/v3/<run>`), rescore with `src.models.evaluate`.
2. **Decided (Assil, 19:40): Kaggle.** Assil makes a phone-verified Kaggle account and runs
   `! .venv/bin/kaggle auth login`; then `.venv/bin/python scripts/kaggle_gpu.py push`
   (EA-LSTM tuning from trial 0 + regimes + Taccari default on one T4, Taccari tuning +
   regimes on the other), `status` / `log`, `pull` (docs/gpu_howto.md, Kaggle section).
   **Changed at 20:25:** the SMS never arrives, so EA-LSTM runs on the laptop (restart command
   in the 21:35 update: do it first). If Kaggle is verified later, push Taccari only:
   `--steps "taccari | tune:taccari regimes:taccari"`; otherwise Camber after 2026-11-13.
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

**Update 2026-10-23 15:25: state when Assil stopped for the day.** Both sweeps are running
unattended. CLAUDE.md §7 ("Running now") has the resume and finish instructions.
- **Colab T4, Taccari.**
  - Default model: 5 seeds; validation 0.527, drought −0.162, recovery 0.394, train
    0.933 (Colab's own scoring, without the skill column). The gap between train and
    validation shows strong overfitting with the default settings.
  - Tuning: 16 of 24 trials done; best trial 12 = 0.620 (lookback 156, hidden 64).
  - About 10 s per epoch.
- **Laptop, EA-LSTM.**
  - The study is complete.
  - Re-selection: trial 18 = 0.531 and trial 12 = 0.540 (3-seed means; their single-seed
    values were 0.604 and 0.599, the lucky-seed effect again). Trial 23 was next.
  - Then come 5 final seeds and the regimes.
- **When both are done:** pull the Colab results (`scripts/colab_pull.py`), then
  ensemble, report, and close this step (CLAUDE.md §7).
