# Step 9 (Phase 2): baselines, part 1 (naive and Pastas)

**Date:** 2026-10-13 · **Status:** in progress (naive + Pastas done; LSTM,
Chronos-2, distance ST-GNN to do)

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
