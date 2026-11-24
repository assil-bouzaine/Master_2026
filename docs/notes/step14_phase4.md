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

## Reading

(to write after the arms report)
