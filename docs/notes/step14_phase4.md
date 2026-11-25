# Step 14 — Phase 4: the real-data arms (RQ1, RQ2) and the black box

Run on 2026-11-24, after Gate 3 and the tag `analysis-plan-v2` (pushed to GitHub before the first
fit). Plan: `docs/phase4_runs.md`; contrasts and families: `configs/phase4_contrasts.json`; analysis
plan §10, §14 items 18–24.

## What was run

- **378 response-model fits** (10 starts each) and 51 leave-wells-out assemblies, blocks B1–B8 and
  B2conv, through the dependency-aware queue (`scripts/p4_queue.py`) on two Colab TPU v5e1 runtimes
  (24 vCPUs, AMD EPYC 7B13), one shard each: shard 1 214 commands in 79 min, shard 2 215 in 66 min,
  **no failure**. The first push had failed before any fit (the TPU image's `torch_tpu` plugin; fixed
  by `TORCH_DEVICE_BACKEND_AUTOLOAD=0`, commit 727f84b, numbers unchanged; analysis plan item 24).
- **The black box** (Gate 3 point 21): the tuned Taccari-style ST-GNN on arm D's edges (`taccari_D`) and,
  in the same L4 session, on its distance edges (`taccari_tuned_ctl`), 5 seeds each (46 min).
- **Getting the results back.** A shard is 4.4 GB on Colab, 3.2 GB of it per-start contribution
  files. At 1–2.4 MB/s the full archive did not fit the pull's 30-minute limit; the pulls left the
  contribution files on Colab (`colab_cli pull --exclude 'contrib_seed_*.parquet'`) because the
  replay (`src/models/response.py: replay`, step 15) recomputes them exactly from the saved
  checkpoints, and fetched the contributions of the runs that explanations and test 2 read
  (B2, B2conv, B4 at R1) separately. Compute used: about 9 units (balance 192.8 → see the end).

## Results

(filled in from `docs/results_arms_v4.md`, `docs/results_phase4_overview_v4.md`,
`docs/results_blackbox_v4.md` and `docs/results_seed_disagreement_v4.md`)

### The black box on the knowledge graph's edges (pre-specified)

`taccari_D` vs `taccari_tuned_ctl`, drought log RMSE ratio **+0.011** [−0.029, +0.055], cluster
sign-flip p = 0.81, exact support on 33 core wells: **no detectable effect** of the knowledge graph's
edges on the black box. The machine effect (same model and edges, L4 today vs T4 in October) is
−0.012 [−0.068, +0.003]: as large as the edge effect. Drought NSE −0.01 (D edges) and 0.04
(distance), skill 0.55 and 0.49.

### First look (informal, 2026-11-24 ≈ 21:15 UTC; the pre-specified report `arms_report` comes next)

Computed with `ladder_report.contrast` on the core wells, drought log RMSE ratio, negative = a better. Not
the arms report: no Holm adjustment, no same-arm bands, no classification. Recorded so the reading starts
from what was seen.

| Contrast | Median | 95 % interval | Share of wells a better | Cluster p |
|---|---:|---:|---:|---:|
| D vs C, R1, reconstruction 1 | +0.010 | [−0.127, +0.112] | 0.48 | 0.875 |
| D vs C, R1, reconstruction 2 | +0.074 | [−0.072, +0.133] | 0.36 | 0.295 |
| black box vs hybrid, both on arm D's edges (`taccari_D` vs `p4_B2_D_r1`, descriptive) | +0.044 | [−0.105, +0.160] | 0.42 | 0.707 |
| black box vs hybrid, distance edges (`taccari_tuned_ctl` vs `p4_B2_C_r1`, descriptive) | +0.008 | [−0.303, +0.075] | 0.48 | 1.000 |

Medians over core wells: `p4_B2_D_r1` validation NSE 0.62, drought NSE 0.014, drought skill 0.33, drought RMSE
0.76 m; `p4_B2_C_r1` 0.58, −0.188, 0.53, 0.64 m. D and C help different wells: on the per-well ratio they tie.
The twin predicted this (D/C within ±0.03 in every cell, `docs/results_twin_v4.md`). The interpretable hybrid
is as accurate as the black-box graph network on the same edges. The ladder's rung-2 runs (panel inputs) had a
drought NSE of −0.29; the routed Phase 4 arms reach −0.19 (C) to 0.01 (D).

## State at the stop (2026-11-24 ≈ 21:20 UTC)

- All 174 Phase 4 run folders are in `results/v4` (shard 2 from p4b; shard 1 rerun on p4c and p4d after the
  first shard-1 runtime was reclaimed unpulled). Every Colab session is stopped; balance 165.3 units (192.8 at
  the start of the day: about 27.5 units used, about 10 of them for the lost shard and the download trouble).
- Contribution files: fetched for the B2, B2conv, B4 and B8 runs of shard 1 (`scripts/fetch_contribs.sh`), rebuilt
  by replay for those of shard 2 (`scripts/replay_contribs.py`, checked against the saved predictions to 8.5e-6 m).
- `docs/results_phase4_overview_v4.md`, `docs/results_blackbox_v4.md`, `docs/results_seed_disagreement_v4.md`:
  regenerated with every run. **`arms_report` not yet run** (stopped after 10 min at Assil's end of session; it
  takes longer): first command of the next session.

## Reading (2026-11-25, after `arms_report`; `docs/results_arms_v4.md`, every family complete, 0 pending)

Measure: the per-well drought log(RMSE a / RMSE b) over the 33 core wells (negative favours a), cluster
bootstrap, cluster sign-flip with Holm, same-arm bands; labels as analysis plan v2 §11 (the R1 / reconstruction 1
rows are pre-specified on a previously examined benchmark, the rest robustness or exploratory).

**RQ1, knowledge as facts (B vs A).** R1, all three reconstructions: **no effect of interest** (reconstruction 1:
+0.008, interval [0.002, 0.015], wholly inside ±0.05). The facts do not change accuracy. The controls agree:
the facts replaced by random name tags give the same score (B1c, +0.000), shuffled facts slightly worse
(+0.028, interval includes 0): the facts act like identifiers, as Heudorfer et al. (2024,
doi:10.5194/hess-28-525-2024) found for global models. One robustness cell (R2, reconstruction 3) is worse with
the facts (+0.029, Holm p 0.016) but stays "undecided" (inside the same-arm bands).

**RQ1, knowledge as structure (D vs C).** **Undecided** in every regime and reconstruction: R1 reconstruction 1
+0.010 [−0.127, +0.112], Holm p 0.875. The intervals are wide (≈ ±0.12): the data cannot tell the two graphs
apart in accuracy, as the twin predicted (no knowledge-value cell pays). The f50 regime leans towards D
(−0.070, −0.010, −0.063) and the R2 regime towards C (+0.060, +0.049, +0.023), none detected.

**RQ2, sign constraints.** Hard vs none, R1 reconstruction 1: **no effect of interest** (+0.009 [−0.010, +0.046]):
the ontology's signs cost no accuracy, while the unconstrained model learns wrong-signed responses at many wells
(`docs/rq2_signs_v4.md`, T67, on the saved parameters, core wells × starts, R1: attributed pumping 32.4 / 42.1 /
35.2 % wrong for reconstructions 1 / 2 / 3, unattributed pumping 35–43 %, rain 11–15 %; soft penalty 100 still
20.6–27.9 % but with wrong gains about 100 times smaller; hard 0 %). The review's counts are reproduced exactly. Soft (penalty 100, chosen on validation) vs none: undecided / no effect.
Plausibility comes free: this is the clearest positive result of Phase 4.

**Graph controls (exploratory).** R1: D beats the random graphs in all five draws (−0.089 to −0.154, most
intervals exclude 0) and the complete graph (−0.050); it ties the distance-preserving rewires (E_distance,
−0.020 to +0.012) and is a little better than the degree-preserving ones (−0.000 to −0.059). So the graph's
edges carry information compared with random edges, but not more than spatial proximity. In R2 (held-out
wells) the advantage disappears (D slightly worse than F_random, +0.020 to +0.067).

**B5–B8 (exploratory).** Message passing adds nothing over routing (R1 +0.010). The pump-link policies change
nothing (B6). Unit-wide recharge vs local (B7): −0.002 [−0.012, +0.006], i.e. no per-well median change: the
gain is concentrated on the few weather-blind wells (the review's "0.758 → 0.604 m" compared medians across
wells, not paired wells). Soil drainage (+0.005) and effective rain (+0.010) as the recharge proxy: no gain.
The bounded seasonal residual (B8): small gains (−0.013 for D, −0.023 for B).

**What this means (plain words, for Assil).** Under the plan we wrote before the runs, the knowledge graph does
not make the v4 hybrid more accurate, as facts or as structure, and it does not make it worse; its sign rules
make it physically plausible at no cost. This is a null on accuracy, reported as such. The review's large gains
come from other statistics (medians across wells, single regimes) that our pre-specified measure does not
confirm, which is why v5's design is tested by its own ladder (`docs/analysis_plan_v3.md` §4) and its drought
results are labelled exploratory (§0 there). The independent evidence for "right reasons" stays the twin
(D recovers pumping better than C in 82 % of worlds under converged pooling) and the explanations.

Post-hoc (not part of the plan): the leave-wells-out intercept (`docs/lwo_centring_v4.md`, T61) explains little
of the R2 failure (median offset ≈ 0.3 m; drought NSE does not improve with centring).
