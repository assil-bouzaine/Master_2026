# v5 Bugs & Gaps to Fix Before Colab Runs / `analysis-plan-v3` Tag

**Audited commit:** `720fb40` on branch `master_2026_fixes` (2026-11-26)  
**Scope:** Concrete bugs and design gaps found in yesterday's v5 work (`T58`–`T70`). Fix items 1–4 before running Hybrid-GNN v2 on Colab or tagging `analysis-plan-v3`.

---

## 1. Critical Bug — Pre-2012 Fake Pumping Leaks Gradients Into Pumping Parameters

- **Where:** `src/models/hybrid_gnn.py` (`HybridGNN.training_forward`, lines 597–618)
- **What is wrong:**
  - On pre-2012 weeks (`y_pre`), pumping channels are detached before computing `m_pre`, so loss restricted to `< 2012` has exact `0.0` pumping gradient (which is the only case `tests/test_hybrid_gnn.py` checked).
  - **However, on post-2012 weeks (`y_rel`), `m_full = self.centres_from_current(c, obs_train_mask)` averages `c_pump` across all observed training weeks (2005–2019) *without* detaching the pre-2012 slice inside `m_full`.**
  - Because `y_rel[t] = ... + (c_pump[t] - m_full)`, the post-2012 loss still differentiates directly through the invented 2005–2011 pumping values inside `m_full`.
- **Verified evidence (PyTorch autograd check):**
  - Holding 2012–2019 pumping fixed and taking loss **only on 2012–2019 weeks**, changing *only* pre-2012 pumping from `1.0` to `100.0` shifts `grad(gain_pumping)` from **`+0.035692` to `+44.081341`** (`Δ = +44.046`).
- **Fix:**
  - Either detach the pre-2012 time slice of pumping channels *before* computing `m_full` (so `m_full` differentiates only through `>= 2012` pumping weeks), or compute pumping channels' training centre over reliable (`>= 2012`) observed training weeks only (and match that rule in `estimate_centres`).
  - Add a unit test in `tests/test_hybrid_gnn.py` verifying that perturbing *only* pre-2012 pumping does not change post-2012 pumping gradients.

---

## 2. Important Gap — `export_v5_main` Is Missing Graph Nodes/Edges Promised in `analysis_plan_v3.md`

- **Where:** `src/kg/export.py` vs `docs/analysis_plan_v3.md` §3.5 (lines 90–92) and `src/models/hetero_graph.py`
- **What is wrong:**
  - `analysis_plan_v3.md` §3.5 states that `HeteroEncoder` operates over `(well, aquifer unit, facility, weather cell, gauge, basin canal)` with relations `(monitors, overlies, same-unit-near, pumping, recharge channels, river, canal)`.
  - In `data/processed/kg/export_v5_main/nodes.parquet` and `edges_D.parquet` today, only 5 node types exist: `facility (2,077)`, `weather_cell (75)`, `well (65)`, `gauge (5)`, and **1** `canal` node (`canal-intakes:plain`).
  - **Missing from the export:** `aquifer_unit` nodes, `monitors` edges, `overlies` edges, and per-basin `canal` nodes (`canal:Tet`, `canal:Agly`, etc.).
  - While `hybrid_gnn.py` routes per-basin canal *time series* into the physics layer, `HeteroEncoder` still sees a single plain canal node (constant feature `0.0`) and cannot pass messages across aquifer units or `overlies` stratigraphy.
- **Fix:**
  - Either extend `src/kg/export.py` (and `tests/test_export.py`) to export `aquifer_unit`, `monitors`, `overlies`, and basin-level `canal` nodes/edges before R3/R4 runs, **or** update `docs/analysis_plan_v3.md` §3.5 honestly if those node/edge types are intentionally deferred.

---

## 3. Important Gap — Control Graphs (`E` / `F`) Omit `recharge_leakage` (and `recharge_unitwide`)

- **Where:** `src/kg/controls.py` (`REL_ID`, line 54)
- **What is wrong:**
  - `REL_ID = {"pumping": 0, "recharge": 1, "river": 2, "canal": 3, "well_link": 4}` skips `recharge_leakage` and `recharge_unitwide`.
  - In `export_v5_main`, Arm D gets **181 local + 765 regional + 105 leakage** recharge edges, whereas Arms `E_degree`, `E_distance`, `F_random`, and `F_complete` get **0** leakage and **0** regional recharge edges.
  - Any D vs E/F comparison in Hybrid-GNN v2 would be structurally unfair until controls rewire every recharge channel that D uses. (Also noted by worker `neon` in `results/_agents/reports/T65.md` #4.)
- **Fix:**
  - Add `recharge_leakage` (and `recharge_unitwide` if active in Hybrid-GNN v2's Arm D) to `src/kg/controls.py` and `tests/test_controls.py`, then rebuild v5 `controls/`.

---

## 4. Design Gap — No Stage A → Stage B Two-Stage Warm-Start in `hybrid_gnn.py`

- **Where:** `src/models/hybrid_gnn.py` (`train_seed`, lines 1062–1130)
- **What is wrong:**
  - The 2-stage design fits **Stage A (`delta = 0`) first** so the GNN encoder is forced to learn parameter variation from static facts and graph structure, then refines trained wells in **Stage B** with regularized `delta`.
  - Currently `--stage A` and `--stage B` train independently from scratch. In `--stage B`, per-well `delta` is unlocked from epoch 0 alongside a zero-initialized `HeteroEncoder.head` (with `lam_delta = 0.1` equal to `lam_shape = 0.1`), risking the same `delta`-starvation failure seen in v4 LWO (`p4_B1_B_r1_lwo`).
- **Fix:**
  - Support initializing Stage B from a trained Stage A checkpoint (`--init-from` / warm-start), or run a Stage-A warm-up phase (`delta` frozen at `0`) inside Stage B before unfreezing `delta`.

---

## 5. Minor Code, Test & Doc Cleanups

1. **Unify `n_slow >= 1.0` in `src/models/kernels.py` (lines 56–57):** `kernels.raw_to_kernel_params()` still bounds `n_slow` at `N_MIN = 0.5` (which T64 showed loses ~22 weeks of mean lag at 104 wk under `K = 416`), forcing `hybrid_gnn.py` to keep a duplicate `raw_to_kernel_params_v2()` (lines 213–231). Move `N_SLOW_MIN = 1.0` into `kernels.py` and remove the duplicate.
2. **Stale statuses in `docs/v5_plan.md`:** Update R0.2 (`T58`), R1.3 (`T62`), R1.5 (`T68/T69`), and R3.2 (`T64/T66/T70`) from `🔄` to reflect completed commits.
3. **Stale prose in `docs/bss_evidence.md` (line 5):** Still says the raw WFS snapshot contains STARTINDEX paging duplicates even though it was re-run on the clean tiled snapshot (`6,848 rows for 6,848 unique`).
4. **Stale prose about vertical leakage:** `tests/cq/cq08_status.rq` (lines 71–72) and `ontology/lulcw.ttl` (`lulcw:VerticalLeakage`, around line 443) still state that vertical leakage is not yet derived as an influence.
5. **EU-only `wfdCode` in `src/kg/country_terms.py`:** `wfd` was outside T59's France-only token list, so `wfdCode` (EU Water Framework Directive, citing `FRDR224`) did not appear in the 16 name matches. Review whether `wfdCode` belongs in an EU/France profile rather than the pan-Mediterranean core during R2.2.
