# Response to the third external review (2026-10-24 night)

The review is `docs/review_codex_2026-10-24.md` (kept unchanged; written by Codex as
`codex.md` at the repository root, moved here on 2026-10-24). This file records what Claude
checked in the code and data, the verdict on each point, and what was changed. Assil approved
the quick fixes on 2026-10-24 and decided the three open points the same night (§2); a second
pass (§3) checked every recommendation against the code again and did the rest that needs no
model training.

**Overall verdict.** A careful and accurate review. All 16 of its factual claims that we
checked hold. It found three statements of ours that were wrong (the Pastas calibration
window, "the solver's own criterion", "confirmatory") and one scientific consequence we had
not drawn (the main pump links carry no irrigation volume).

## 1. Point by point

Status: **done** = changed on 2026-10-24/25; **plan** = written into the plan for a later
task; **decided** = Assil's decision of 2026-10-24 (§2), implemented.

| § | Point | Checked | Verdict | Status |
|---|---|---|---|---|
| 1 | v3/v4 drought medians; strict subset 27 wells / 3,948 well-weeks (drought), 7 / 296 (recovery) | `results/v*/…/metrics_summary.csv` | correct | no change |
| 3.1 | Tagging the plan cannot make the examined 2022–25 drought unseen; "confirmatory" is too strong | `docs/analysis_plan.md` §11 said "confirmatory" | agree | **done**: §11 and §12 now say "pre-specified comparisons on a previously examined benchmark"; only post-freeze weeks are an independent check, the validated 2025–26 weeks a quality sensitivity check |
| 3.2 | R3: the input standardisation uses every training row, the window applies only to the loss | `lstm.py` `arrays()` (2005–2019 rows), `taccari.py` exogenous scaling | correct; not target leakage | **done**: rule stated in §4 (R3 limits the head history, not the forcing history). We keep this rule instead of Codex's preference (window-only preprocessing): forcings are known for every year, and it needs no GPU re-run. Second pass: the information-use table per regime (§4) and `tests/test_regime_boundaries.py` (window statistics, masks, coverage: every core well keeps ≥ 76 weeks in the 25 % window; 4 non-core wells without heads in 2016–2019 leave R3) |
| 3.2 | R2 reuses `best.json` selected on all core wells | `regimes.py` `base_cmd()` | correct | **done**: R2 called "fixed-configuration transfer" (§4, §12); **plan**: nested selection for the primary D vs C contrast only |
| 3.3 | Pastas sets its initial constant from the whole head series | `pastas/model.py:129` (2.0.0) | correct | **decided**: the training-heads-only fit with the frozen best-start rule is the v4 reference, whatever its score (`baseline_report.REFERENCE`, the ensemble's Pastas candidate; v3 unchanged). **Pulled 2026-10-25:** drought median NSE −0.75; over its 10 starts −1.26 to −0.60, a core well's drought NSE moves by a median 1.2; the v4 report shows the spread and the test of record repeated against every start (only the ensemble passes against all 10; step 12b note, last section) |
| 3.3 | The calibration window is 2005–2019, not 2012–2019 | `splits.json` `model_start` = 2005-01-01; `fit_well()` | correct: our note had kept the v1 window | **done**: docstring, CLAUDE.md, step 12b note. 6 of 55 fitted wells changed heads (73 weeks, 71 inside the calibration); 13 of the 43 drought-scored wells with identical heads still moved > 0.05 |
| 3.3 | The best-start score (unweighted noise) is not the solver's objective (noise × weights) | `pastas/solver/objective/misfit.py:47` | correct | **done**: the solver's objective is stored from now (`train_objective`); the best start is chosen by the training-period simulation RMSE, a rule frozen before any multistart result, and agreement with the objective plus fallbacks and failures are reported (`pastas_stability.py`, `tests/test_pastas_starts.py`) |
| 3.4 | Main policy: no irrigation volume gets an accepted unit (plain 2012–2024: 0 confident, 0 probable, 137.3 Mm³ possible, 24.1 unknown) | `pump_unit_attribution_eval.json` | correct, and important | **decided**: drinking-water main story, irrigation claims only from the all-links sensitivity (analysis plan §8, §12). **done**: coverage by use × unit × year (`src/kg/pump_coverage.py`, `docs/pump_coverage.md`): the main policy covers 72.3 % of the declared volume at unit-group resolution but **61.8 % at exact-unit resolution** (56.2 % of the model forcing with imputed years), so the 72 % figure was not the export coverage. **plan** (12.8): the same table in every export; unattributed pumping as an explicit input of every arm |
| 3.4 | Wilson 95 % intervals: flag_true 18/19 [0.754, 0.991]; flag_false 36/39 [0.797, 0.973], raw 32/39 [0.673, 0.910] | recomputed (exact-unit flag_true 12/19: [0.410, 0.809]) | correct | **done**: in `docs/pump_coverage.md`; the flag_false lower bound is just under the 0.80 threshold, a reason never to read point precision as an edge probability |
| 3.4 | The revised reference and the rules share the BD LISA stack | `pump_attribution.py` | agree | already reported both ways (revised and raw record); keep |
| 4 | D vs C must change only the edges; the arm table does not fix the backbone | `docs/feedback.md` §5.1 (A = LSTM, D = main model, C unstated) | correct | **decided**: one backbone for C–F, experiment contract and controls written into analysis plan §10 (hybrid without message passing, random-ID / shuffled statics, distance-matched rewiring, several graph draws, edge overlap) |
| 4 | Taccari: 6 layers, kernel 3, dilations 1–32 = 127-week receptive field, with a 156-week lookback | `taccari.py`, `taccari_tuning/best.json` | correct | **done**: docstring |
| 5 | Whole-path monotonicity details (kernel signs and normalisation, rolling copies of a driver, residual proxies); small twin early; truth graph different from the graph given to the learner | design | agree | **done** as rules in analysis plan §10 (intervention map, kernel signs and normalisation, rolling copies recomputed, residual share reported; twin built before the sweeps with generator draws and a truth graph separate from the learner's) |
| 6 | Finish 12.6–12.8 before new vocabulary; equivalence beyond edges plus a fixed-weight forward pass | `analysis_plan.md` §10 said "equal edges give equal predictions" | agree; our sentence overstated it | **done**: §10 rewritten; 12.6–12.8 were already next |
| 6 | 50 KG facilities absent from the dataset | KG summary | correct | already explicit unknowns (0.04 Mm³ in total); reconcile at export (12.8) |
| 6 | The 2023 RPG used as a fixed attribute for 2005–2019 | CQ7 contract | agree | **plan**: dated snapshots for arm B features (CQ7) |
| 7 | Each run is scored on its own weeks; pairing is not enforced | `evaluate.py` `score()` | correct | **done**: `stats.paired()` counts `support_mismatch`, `strict=True` refuses such a pair, the report warns; none in v3 (26 rows) or v4 (8 rows) (`tests/test_stats.py`) |
| 7 | Cluster test: add a cluster-scale/origin sensitivity and leave-one-cluster-out | design | agree | **done**: `stats.cluster_sensitivity` (5/10/20 km, origin 0 or half a cell, leave-one-cluster-out), fixed in analysis plan §6 before any Phase 4 result, shown in the v4 report; 10 km stays the test of record |
| 7 | SGI reference has no 2005 lower bound; Chronos-2 fine-tunes on the 2000–2004 warm-up weeks too | `build.py` `sgi()`; `chronos2.py` `finetune()` (6,579 warm-up well-weeks with a target) | correct; no future information | **done**: documented (§12, docstrings); prior results kept |
| 7 | No model weights are saved | 0 `.pt`/`.ckpt` files under `results/` | correct | **done** for the runners: `src/models/manifest.py` (weights of the selected epoch, schema, manifest with code and data hashes and environment; LightGBM boosters), `tests/test_checkpoint.py`; Pastas replays from `params.csv` to 1e-11 m (`tests/test_replay.py`). The v4 neural finals made before have no weights: re-run them with weights before the freeze if they enter the post-freeze check. Graph export: 12.8 |
| 7 | Cached seeds reused without checking the settings; `config.json` overwritten; partial folds assembled | `lstm.py`, `stgnn.py`, `regimes.py` | correct | **done**: run fingerprints, a config guard, exact seed sets per fold (`tests/test_run_cache.py`); legacy seeds are accepted on their folder's settings. LightGBM's cache unchanged (its v4 runs are complete) |
| 8 | Position against Wu WRR on provenance and validity tests, not on "a graph prior"; check its SI before any criticism; read Chu and Jeong | `docs/literature/comparison_table.md` | agree | our row already says "in the main text"; **plan**: check the SI before writing |
| 9 | Order of work (P0 before declaring v4 final and before Phase 4) | — | agree | adopted; 12.6–12.8 stay next |
| 4 | Report search spaces, parameter counts, completed/failed trials, time | `results/v3/*_tuning/study.db` | agree (missed in the first pass) | **done**: `src/analysis/tuning_report.py` → `docs/tuning_budget_v3.md`; equal trials, unequal size (Taccari 230 k parameters, LSTM 78 k) |
| 6 | Conservation of declared and reconstructed totals, December/January boundaries | `src/dataset/build.py`, `bnpe_v3.py` | agree (missed in the first pass) | **done**: `tests/test_pumping_conservation.py` (cold rebuild equal; declared → annual exact; seasonal uses exact). Found: flat uses keep 52 or 53 × 7/365.25 of the annual volume, so a 53-week year (2006, 2012, 2017, 2023) carries 1.9 % more drinking-water pumping; kept in v4 (same input for every model), documented |
| 7 | Hydrological error analysis; SGI class with a confusion matrix and class-sensitive score, frozen observed reference | `evaluate.py` had no SGI scoring although CLAUDE.md says SGI accuracy is reported | correct (missed in the first pass) | **done**: `src/analysis/hydro_errors.py` → `docs/results_hydro_<v>.md` (accuracy, within one class, balanced accuracy, weighted kappa, POD/FAR/CSI of low levels, annual-minimum timing and size, lag, trough; hydrographs chosen by rule). v3: the tuned LSTM and the ensemble detect 72–73 % of low-level drought months (FAR 0.17), Pastas 49 %, climatology 1 % |
| 3.1 | Every main result labelled development / confirmation | analysis plan §11 | agree | **done**: three labels in §11 |

## 2. Decisions of Assil (2026-10-24, late evening)

1. **Framing of irrigation: drinking water main.** The main story is drinking-water pressure
   on the Pliocene within the agricultural water-use context; claims about farm pumping come
   only from the all-links sensitivity, labelled provisional. The policy itself stays.
2. **The Pastas v4 reference: training heads only, decided now** (before the Kaggle
   multistart results), whatever its test score, with the start chosen by the frozen rule
   and its spread reported.
3. **Arms C–F: one backbone, adopted now** (analysis plan §10), with the cheap controls of
   §4 of the review.
4. **Suspect placeholders (found in the second pass, §3): rule-based mask.** A run of
   ≥ 28 days at a depth of exactly 0.00 m leaves every scored variant from v4; the v4
   primary table is shown both ways; a note asks the producer to confirm
   (`docs/supervisor_questions.md` §6).

## 3. Second pass (2026-10-25): every recommendation checked against the code

The first pass had left three rows of the review without a row here (tuning budget,
conservation checks, hydrological error analysis); they are now in §1 and done. What else the
second pass found:
- **A data error the review did not see.** Picking representative hydrographs by rule (the
  review's §7) showed CORNEILLA PD5 (core, Pliocene, 153 m) at exactly its station altitude,
  11.77 m NGF, for 59 weeks in the drought: the raw records give a depth of 0.00 m on 413
  consecutive days, qualified "Correcte". Flowing wells (F, S, FAITOU) record negative depths;
  PD5 never does. Masking these weeks moves the v3/v4 core drought medians by +0.01 to +0.10
  NSE depending on the model and Pastas' drought skill by −0.04 / −0.05, so it matters for
  every contrast with Pastas. Decision 4 above; `src/dataset/placeholders.py`.
- **The 72 % coverage figure** (main pump policy) is a unit-group figure; the exact-unit
  coverage a graph export would see is 61.8 % (§1, row 3.4).
- **Pastas is reproducible from its stored parameters** (replay to 1e-11 m across machines):
  the v3/v4 Pastas instability lies in the fitting, not in the simulation.
- **Unequal model sizes** under equal trial budgets (§1, tuning row).
- **Literature.** The abstracts of Chu et al. 2026 (PubMed 42442261) and Jeong et al. 2026
  (PubMed 42361754) were read: Chu is a forecasting residual-learning TFN + LSTM on 3 wells
  (past residuals drive the correction); Jeong already checks learned kernels against
  independently estimated residence times, so that idea is cited as a precedent, not claimed.

Still open after the second pass (tasks of the plan, not decisions): the export coverage and
unattributed-pumping input (12.8), the 50 KG facilities without forcing (12.8), dated RPG
snapshots (CQ7), Wu WRR supplementary protocol before any criticism, the full texts of Chu and
Jeong, an independent audit of a few pump attributions with borehole screen data, and the
weights of the v4 neural finals before the freeze.
