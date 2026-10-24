# Response to the third external review (2026-10-24 night)

The review is `docs/review_codex_2026-10-24.md` (kept unchanged; written by Codex as
`codex.md` at the repository root, moved here on 2026-10-25). This file records what Claude
checked in the code and data, the verdict on each point, and what was changed. Assil approved
the quick fixes on 2026-10-25; the open points in §2 are his to decide.

**Overall verdict.** A careful and accurate review. All 16 of its factual claims that we
checked hold. It found three statements of ours that were wrong (the Pastas calibration
window, "the solver's own criterion", "confirmatory") and one scientific consequence we had
not drawn (the main pump links carry no irrigation volume).

## 1. Point by point

Status: **done** = changed on 2026-10-25; **plan** = written into the plan for a later task;
**open** = decision for Assil (§2).

| § | Point | Checked | Verdict | Status |
|---|---|---|---|---|
| 1 | v3/v4 drought medians; strict subset 27 wells / 3,948 well-weeks (drought), 7 / 296 (recovery) | `results/v*/…/metrics_summary.csv` | correct | no change |
| 3.1 | Tagging the plan cannot make the examined 2022–25 drought unseen; "confirmatory" is too strong | `docs/analysis_plan.md` §11 said "confirmatory" | agree | **done**: §11 and §12 now say "pre-specified comparisons on a previously examined benchmark"; only post-freeze weeks are an independent check, the validated 2025–26 weeks a quality sensitivity check |
| 3.2 | R3: the input standardisation uses every training row, the window applies only to the loss | `lstm.py` `arrays()` (2005–2019 rows), `taccari.py` exogenous scaling | correct; not target leakage | **done**: rule stated in §4 (R3 limits the head history, not the forcing history). We keep this rule instead of Codex's preference (window-only preprocessing): forcings are known for every year, and it needs no GPU re-run |
| 3.2 | R2 reuses `best.json` selected on all core wells | `regimes.py` `base_cmd()` | correct | **done**: R2 called "fixed-configuration transfer" (§4, §12); **plan**: nested selection for the primary D vs C contrast only |
| 3.3 | Pastas sets its initial constant from the whole head series | `pastas/model.py:129` (2.0.0) | correct | **open** (2): make the training-heads-only fit (`--train-obs`, running on Kaggle) the v4 reference |
| 3.3 | The calibration window is 2005–2019, not 2012–2019 | `splits.json` `model_start` = 2005-01-01; `fit_well()` | correct: our note had kept the v1 window | **done**: docstring, CLAUDE.md, step 12b note. 6 of 55 fitted wells changed heads (73 weeks, 71 inside the calibration); 13 of the 43 drought-scored wells with identical heads still moved > 0.05 |
| 3.3 | The best-start score (unweighted noise) is not the solver's objective (noise × weights) | `pastas/solver/objective/misfit.py:47` | correct | **done**: the solver's objective is stored from now (`train_objective`); the best start is chosen by the training-period simulation RMSE, a rule frozen before any multistart result, and agreement with the objective plus fallbacks and failures are reported (`pastas_stability.py`, `tests/test_pastas_starts.py`) |
| 3.4 | Main policy: no irrigation volume gets an accepted unit (plain 2012–2024: 0 confident, 0 probable, 137.3 Mm³ possible, 24.1 unknown) | `pump_unit_attribution_eval.json` | correct, and important | **open** (1); **plan** (12.8): coverage by use × unit × year in every export; unattributed pumping enters every arm as an explicit input, never as zero; C and D get the same forcing inventory |
| 3.4 | Wilson 95 % intervals: flag_true 18/19 [0.754, 0.991]; flag_false 36/39 [0.797, 0.973], raw 32/39 [0.673, 0.910] | recomputed (exact-unit flag_true 12/19: [0.410, 0.809]) | correct | **plan**: report them in the thesis; the flag_false lower bound is just under the 0.80 threshold, a reason never to read point precision as an edge probability |
| 3.4 | The revised reference and the rules share the BD LISA stack | `pump_attribution.py` | agree | already reported both ways (revised and raw record); keep |
| 4 | D vs C must change only the edges; the arm table does not fix the backbone | `docs/feedback.md` §5.1 (A = LSTM, D = main model, C unstated) | correct | **open** (3) for Gate 3: one backbone for C–F, a hybrid without message passing as ablation, a random-ID control, a distance-matched rewiring, several graph draws |
| 4 | Taccari: 6 layers, kernel 3, dilations 1–32 = 127-week receptive field, with a 156-week lookback | `taccari.py`, `taccari_tuning/best.json` | correct | **done**: docstring |
| 5 | Whole-path monotonicity details (kernel signs and normalisation, rolling copies of a driver, residual proxies); small twin early; truth graph different from the graph given to the learner | design | agree | **plan**: Phase 4 design notes |
| 6 | Finish 12.6–12.8 before new vocabulary; equivalence beyond edges plus a fixed-weight forward pass | `analysis_plan.md` §10 said "equal edges give equal predictions" | agree; our sentence overstated it | **done**: §10 rewritten; 12.6–12.8 were already next |
| 6 | 50 KG facilities absent from the dataset | KG summary | correct | already explicit unknowns (0.04 Mm³ in total); reconcile at export (12.8) |
| 6 | The 2023 RPG used as a fixed attribute for 2005–2019 | CQ7 contract | agree | **plan**: dated snapshots for arm B features (CQ7) |
| 7 | Each run is scored on its own weeks; pairing is not enforced | `evaluate.py` `score()` | correct | **done**: `stats.paired()` counts `support_mismatch`, `strict=True` refuses such a pair, the report warns; none in v3 (26 rows) or v4 (8 rows) (`tests/test_stats.py`) |
| 7 | Cluster test: add a cluster-scale/origin sensitivity and leave-one-cluster-out | design | agree | **plan**: Gate 3, prespecified |
| 7 | SGI reference has no 2005 lower bound; Chronos-2 fine-tunes on the 2000–2004 warm-up weeks too | `build.py` `sgi()`; `chronos2.py` `finetune()` (6,579 warm-up well-weeks with a target) | correct; no future information | **done**: documented (§12, docstrings); prior results kept |
| 7 | No model weights are saved | 0 `.pt`/`.ckpt` files under `results/` | correct | **plan**, before Phase 4: weights, preprocessing state, feature schema, graph export, hashes, commit, config, seed, environment |
| 7 | Cached seeds reused without checking the settings; `config.json` overwritten; partial folds assembled | `lstm.py`, `stgnn.py`, `regimes.py` | correct | **done**: run fingerprints, a config guard, exact seed sets per fold (`tests/test_run_cache.py`); legacy seeds are accepted on their folder's settings. LightGBM's cache unchanged (its v4 runs are complete) |
| 8 | Position against Wu WRR on provenance and validity tests, not on "a graph prior"; check its SI before any criticism; read Chu and Jeong | `docs/literature/comparison_table.md` | agree | our row already says "in the main text"; **plan**: check the SI before writing |
| 9 | Order of work (P0 before declaring v4 final and before Phase 4) | — | agree | adopted; 12.6–12.8 stay next |

## 2. Open decisions for Assil

1. **Framing of irrigation.** Under the approved policy (confident + probable), the model's
   pump links are drinking-water links. Proposed: the main story is drinking-water pressure
   on the Pliocene within the agricultural water-use context; claims about farm pumping
   come only from the all-links sensitivity. The policy itself stays.
2. **The Pastas v4 reference.** Proposed: the fit built from training heads only
   (`--train-obs`), whatever its test score, with the start chosen by the frozen rule
   above, and its spread reported. Decide once the Kaggle results are in.
3. **Gate 3.** One backbone for arms C–F (only the edges change), and the cheap controls of
   §4 of the review.
