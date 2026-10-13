# Step 9 (Phase 2): baselines

**Date:** 2026-10-13 · **Status:**
- done: all baselines (naive, Pastas, LightGBM, LSTM, distance ST-GNN,
  Chronos-2)
- ST-GNN and Chronos-2 ran on the Camber GPU (NVIDIA L4), 2026-10-13

Full table: `docs/results_baselines.md`. Figures:
`reports/figures/baselines_nse.png`,
`reports/figures/baselines_hydrographs.png`.

## What was done

| Script | What it does |
|---|---|
| `src/models/evaluate.py` | One scoring module for every model. NSE, KGE, RMSE and bias per well and split; medians over the 33 core wells, overall and per aquifer group; test scores on all weeks and on validated weeks only. |
| `src/models/naive.py` | The floors: climatology (simulation), persistence and anomaly persistence (forecast, 4 and 12 weeks). |
| `src/models/pastas_baseline.py` | Pastas transfer-function noise models, one per well, calibrated 2012–2019, then simulated to 2026 without seeing any observed level. 5 variants to test our assumptions. |

```bash
.venv/bin/python -m src.models.naive
.venv/bin/python -m src.models.pastas_baseline     # ~2 min per variant on 4 cores
.venv/bin/python -m src.models.evaluate --compare
```

### Two tasks

- **Simulation:** predict the level from weather and pumping only; the
  model never sees observed levels after training. This is the main task:
  it works for wells never seen (leave-wells-out), and it is where "did the
  model learn the physics?" can be tested.
- **Forecast:** predict *h* = 4 or 12 weeks ahead, knowing levels up to
  today. This is the operational use.

### Results (median over the 33 core wells)

| Task | Model | Train NSE | Validation NSE | Test NSE (drought) | Test RMSE |
|---|---|---|---|---|---|
| simulation | climatology (floor) | 0.42 | 0.12 | −0.25 | 0.71 m |
| simulation | Pastas (flat pumping) | 0.54 | 0.19 | −0.06 | 0.76 m |
| simulation | Pastas + canal | 0.55 | 0.41 | 0.03 | 0.73 m |
| simulation | Pastas + seasonal drinking water | 0.51 | 0.37 | 0.04 | 0.69 m |
| simulation | **Pastas + seasonal + canal (reference)** | **0.57** | **0.51** | **0.13** | **0.68 m** |
| simulation | Pastas + regional pumping | 0.57 | 0.33 | −0.04 | 0.71 m |
| forecast 4 wk | persistence | 0.58 | 0.59 | 0.63 | 0.35 m |
| forecast 4 wk | **anomaly persistence** | 0.80 | 0.78 | **0.78** | 0.32 m |
| forecast 12 wk | anomaly persistence | 0.45 | 0.29 | 0.11 | 0.61 m |

**Reference baselines from now on:**
- simulation: `pastas_seasonal_canal`
- forecast: `naive_anomaly_persist`

## Why

- **Why the floors matter.** A model that cannot beat "a normal year"
  (climatology) or "same anomaly as today" (anomaly persistence) has learned
  nothing useful. Anomaly persistence at 4 weeks (NSE 0.78) is a hard floor:
  groundwater changes slowly.
- **Why Pastas.** It is the hydrologists' standard tool. Each stress (rain,
  pumping) gets a response curve. Because each curve has a physical
  meaning, the fitted parameters double as a **physics reference** for
  later tests (e.g. "how much does the level drop per Mm³ pumped?").
- **Why the drought test is so hard.** The test period has 43.5% "très
  bas" weeks, which is outside the training range. Every model so far
  performs much worse on test than on validation.

### What the Pastas variants taught us about the aquifer

1. **The flat drinking-water assumption is wrong.** With flat pumping, half
   of the Pliocene wells push the evaporation factor to its bound (f = −2):
   the model uses evaporation to fake the summer drop that pumping should
   explain. Seasonal drinking water (50% following summer demand) helps
   (validation 0.19 → 0.37). This supports the "use conflict on the
   Pliocene" framing: the summer drop is pumping.
2. **The canal input helps exactly where it should.** It raises training
   NSE in the alluvium (median +0.09 to +0.12) and at Millas C2-1 (0.34 →
   0.53), and does nothing for the karst (exactly 0.00). That is early,
   independent evidence for canal-return recharge. The two framings are
   complementary, not exclusive.
3. **Plain-wide pumping does not help.** A single total for the whole plain
   makes the karst worse and the test score drops. Wells feel pumping
   selectively, through *their* aquifer unit. That is the argument for a
   graph built from the knowledge graph (well → aquifer unit → abstraction
   points), rather than distance radii or all-to-all connections.

## What to consider

- **Pastas is still weak** (test 0.13). Half the Pliocene wells still hit
  the evaporation bound. The pumping inputs are the weak point: annual
  totals, unknown aquifer layer, 3 km radius. Linking abstraction points to
  aquifer units (Phase 3) should help every model, not only ours. Keep the
  comparison fair: give Pastas the same improved inputs.
- **Possible extra Pastas variant:** nonlinear recharge (`ps.rch.FlexModel`)
  for the semi-arid climate. Verify the reference (Collenteur et al. 2021,
  HESS) before citing it.
- **Results to report per aquifer group:** the karst and THUIR have RMSE of
  4–8 m and dominate any average in metres.
- **Compute:** Pastas runs in about 2 minutes per variant on this laptop. A
  test LSTM: 20 training steps in 2.4 s on CPU (torch 2.14.1 CPU).


---

## Part 2: machine-learning baselines (2026-10-13)

| Script | What it does |
|---|---|
| `src/models/features.py` | One feature table for all ML models: weather averaged over 1 month to 2 years, seasonal pumping, canals, season, well attributes, training-only climatology. |
| `src/models/lgbm.py` | LightGBM. Configuration and target chosen on validation only. Every well weighs the same. The forecast learns a correction to anomaly persistence. |
| `src/models/lstm.py` | Global LSTM over the last 104 weeks plus well attributes; 5 seeds, averaged. |
| `src/models/chronos2.py` | Chronos-2 zero-shot, rolling forecasts with past covariates. |
| `src/models/stgnn.py` | GRU + 2 graph-convolution layers on a 3-nearest-wells distance graph (Taccari-style); 5 seeds. |
| `src/analysis/baseline_report.py` | Table + figures from all runs. |

### Results (median over 33 core wells)

| Task | Model | Validation NSE | Test NSE (drought) |
|---|---|---|---|
| simulation | climatology | 0.12 | −0.25 |
| simulation | Pastas (best variant) | 0.50 | 0.13 |
| simulation | LightGBM | 0.54 | 0.03 |
| simulation | **LSTM, 5 seeds** | **0.58** | **0.25** |
| forecast 4 wk | anomaly persistence | 0.78 | 0.78 |
| forecast 4 wk | LightGBM | 0.78 | 0.77 |
| forecast 12 wk | anomaly persistence | 0.29 | 0.11 |
| forecast 12 wk | LightGBM | **0.44** | 0.04 |

### What we learned

1. **Trees cannot extrapolate.** LightGBM's level forecasts collapsed in the
   drought (below the training range). Predicting a *correction* to a good
   naive forecast fixed it.
2. **Weighting matters.** A pooled loss is dominated by the flashy karst
   wells. Weighting every well equally made LightGBM match the 4-week floor.
3. **Averaging seeds helps most in the drought.** Single LSTMs reach
   validation 0.42–0.60; the 5-seed mean has the best test score.
4. **At 4 weeks, anomaly persistence is close to unbeatable.** Groundwater
   is slow. The value of models is at longer horizons and in simulation.
5. **The key finding** (hydrographs): **every model gets the timing right
   but misses how deep summer drawdowns became in the drought.** At
   Sabirou (Pliocene) the observed level falls to 19.5–20 m while all
   models stop near 22 m; at Millas, 2022–24 lows are 1–1.5 m below every
   model. The pumping inputs (annual totals, assumed profiles, imputed after
   2023) cannot show that pumping intensified in hot, dry summers. Missing
   information, not a missing algorithm.
6. **Negative results kept:**
   - nonlinear recharge (FlexModel) made Pastas worse
   - one plain-wide pumping series made Pastas worse
   - dropping identity-like statics did not help LightGBM

### How to improve (ordered by expected gain)

**A. Data: the biggest lever** (finding 5)
1. **Monthly drinking-water production** from the water utilities or the
   SAGE nappes plio-quaternaires syndicate, to replace the assumed profile.
   Ask through the supervisor.
2. **Link each abstraction point to its aquifer layer** (BSS borehole
   depth; drinking-water boreholes vs shallow wells). This is Phase 3
   knowledge-graph work, and it will help every model, including Pastas.
3. **Drought restriction orders** (irrigation bans) as an input; check the
   VigiEau/Propluvia open data first.
4. **Train from 2005 instead of 2012:** heads and weather exist; pumping
   would be held at its 2012–2014 level. Seven more years, including dry
   ones.
5. **Use all 101 dept-66 stations for training** the global models
   (evaluate on the core set).

**B. Models**
1. Tune the LSTM with Optuna on a GPU, selecting on validation only:
   lookback 156/208 weeks (the Pliocene has a long memory), hidden size,
   dropout.
2. Average across model families (LSTM + LightGBM + Pastas); often the best
   single baseline.
3. Robustness: a second test window (rolling origin) and per-well paired
   tests (Wilcoxon) between models, so claims are statistically supported.

**C. Tools worth adding**
- Optuna (tuning)
- Weights & Biases or MLflow (run tracking)
- NeuralHydrology (EA-LSTM family by config)
- Nixtla NeuralForecast or Darts (N-HiTS, TFT, TiDE in a few lines)
- AutoGluon-TimeSeries (an automatic ensemble including Chronos-2: a strong
  "AutoML" reference)
- PyTorch Geometric (heterogeneous graphs, Phase 4)
- Captum (attributions, Phase 5)


---

## Part 3: GPU runs on Camber (2026-10-13)

The distance-graph ST-GNN (5 seeds) and Chronos-2 ran on Assil's Camber
XSMALL GPU node (NVIDIA L4, 23 GB, torch 2.8 cu128) through
`scripts/run_gpu.sh`. The results were downloaded with the Camber CLI and
scored locally with the same `evaluate.py`; local scores reproduce the GPU
scores exactly. Logs: `results/camber_gpu_run*.log`.

| Task | Model | Validation NSE | Test NSE | Test RMSE |
|---|---|---|---|---|
| simulation | **distance-graph ST-GNN, 5 seeds** | 0.58 | **0.26** | **0.58 m** |
| simulation | LSTM, 5 seeds | 0.58 | 0.25 | 0.65 m |
| forecast 4 wk | **Chronos-2 zero-shot** | 0.80 | **0.83** | **0.26 m** |
| forecast 12 wk | **Chronos-2 zero-shot** | 0.45 | **0.42** | **0.45 m** |

**What it means**
- **The distance graph helps a little in simulation.** It has the lowest
  error of all simulation models (0.58 m vs 0.65 m for the LSTM). By aquifer,
  test NSE is 0.42 karst, 0.37 recent alluvium, 0.25 ancient alluvium, and
  only **0.07 Pliocene**: the deep drinking-water wells remain the hard
  part. This is the bar for the knowledge-graph graph (RQ1).
- **Chronos-2 is the forecasting reference.** Zero-shot, with no training
  on our data, it beats every other forecaster, and at 12 weeks it reaches
  0.42 where everything else is near 0. Any forecasting claim in the paper
  must be made against Chronos-2.
- **The paper's story is clearer:**
  - for *forecasting*, pretrained foundation models are already strong
  - for *simulation and explanation* (what drives the level; unseen wells;
    the drought), no model captures the Pliocene drawdowns
  - knowledge (layer-aware pumping, the aquifer graph) is the missing piece

**Lessons from running on Camber** (also in `docs/gpu_howto.md`)
- CLI batch jobs (`camber job create`) are blocked on the free tier; the
  interactive JupyterLab GPU node works.
- Start background runs with `setsid nohup … < /dev/null &`. A plain
  `nohup … &` died when the notebook cell ended.
- Never `pkill -f <pattern>` from a shell whose own command line contains
  the pattern: it kills itself. Use PIDs or `grep "[p]attern"`.
- Stash does not sync a log file while it is being written; check progress
  on the node, or wait for result files.
- Camber's image has a torchaudio that does not match its torch;
  `run_gpu.sh` shadows it with the matching version inside the venv.
