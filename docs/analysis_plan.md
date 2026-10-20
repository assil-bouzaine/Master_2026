# Analysis plan (written before the runs it governs)

**Version 1 · 2026-10-20** · Status: proposed by Claude, to be confirmed by
Assil (and the supervisor at Gate 3). Every result in the thesis and the paper
follows this plan. A change after results exist must be dated here, with its
reason, and both versions reported.

Why a plan: the same data allow many reasonable analyses. Fixing the endpoints,
periods and tests *before* looking at new results keeps the comparisons honest
and protects the conclusions from being tuned to the results.

## 1. Task and endpoints

- **Main task: simulation.** Weekly head per well from weather, pumping and
  static attributes only; no observed head is ever an input.
- **Primary endpoint:** median over the **33 core wells** of the **NSE in the
  drought phase** of the test period.
- **Co-primary endpoint:** median **skill against the training climatology** in
  the drought phase, `1 − MSE(model) / MSE(climatology)` on the same weeks.
  NSE in a sub-period uses the mean of that sub-period as its benchmark, which
  "knows" how low the levels went; the climatology does not.
- **Secondary:** the same two scores in the recovery phase and on the whole test
  period; KGE'' (Tang et al. 2021, doi:10.1175/JCLI-D-21-0067.1, datum-free) with
  its components r, α and the normalised bias; RMSE and bias in metres; scores
  per aquifer group; the **plain core** subset (26 wells: alluvium + Pliocene,
  without the karst and THUIR); test weeks with validated data only.
- **Forecast task (secondary):** 4 and 12 weeks ahead; reference = anomaly
  persistence; Chronos-2 is the model to beat.

## 2. Periods

| Period | Dates | Rule |
|---|---|---|
| warm-up | forcings from 2000 | inputs only, never scored |
| train | 2005-01-01 → 2019-12-31 | |
| validation | 2020-01-01 → 2022-04-30 | the only period used for any choice |
| test | 2022-05-01 → end of record | never used for any choice |
| test, **drought** | 2022-05-01 → 2025-11-30 | see below |
| test, **recovery** | 2025-12-01 → end | see below |

**Drought/recovery boundary (fixed 2026-10-20, from observed levels only):** the
recovery starts on the first month after the drought trough from which the
median SGI of the 33 core wells stays ≥ −0.5 for three consecutive months. This
gives December 2025 with both the v1 (2012–2019) and the v2 (2005–2019) SGI
references (median SGI −0.29 in Dec 2025, +0.55 in Jan 2026, +1.07 in Feb 2026;
2025 itself stayed between −0.6 and −1.6, with a relapse in Oct–Nov 2025).
Defined in `src/config.py` (`TEST_PERIODS`).

A provisional boundary at 2024-12-31 was used in `docs/feedback.md` before this
rule was fixed; its numbers are superseded by `docs/results_baselines.md`.

## 3. Wells

- **Core set:** the 33 working-set wells (primary). **Plain core:** 26
  (secondary). All usable dept-66 wells may be used for training (masked loss).
- A well is scored in a period only if it has at least 26 observed weeks there.

## 4. Regimes (RQ1)

| Regime | Training data | Scored on |
|---|---|---|
| R1 temporal | all training wells, train period | core wells, test periods |
| R2 **unseen wells** | wells outside fold k (5 folds, stratified by aquifer group, seed 2026, `splits.json`) | the core wells of fold k, test periods; the 5 folds pooled |
| R3 **less data** | the most recent 25 % and 50 % of the training period (start 2016-04-01 and 2012-07-01; end 2019-12-31) | core wells, test periods |

- **Unseen wells, "dynamics" convention:** models predict the standardised
  head z; it is converted to metres with the held-out well's *own*
  training-period mean and standard deviation, which the model never sees. The
  score therefore measures the dynamics (timing and amplitude relative to the
  well's normal range), not the absolute level. Static attributes of the
  held-out well are allowed. Early stopping and selection use the validation
  period of the *training* wells only. Pastas is calibrated per well and has no
  R2 result; the climatology benchmark uses the held-out well's own training
  data, consistent with the convention.
- **R3** keeps the forcing warm-up before the shortened training period. The
  validation and test periods are unchanged.

## 5. Model selection and tuning (equal budget, CLAUDE.md rule 11)

- **One budget for every learned model:** Optuna TPE sampler, seed 2026,
  **24 trials**, objective = median validation NSE over the core wells (one
  seed per trial, early stopping on validation). Search spaces of comparable
  size (4 hyperparameters). Then the best configuration is retrained with
  **5 seeds**.
- **Selection against lucky seeds (added 2026-10-20, before any tuned v3 result
  was used):** the 3 best trials are re-run with seeds 1 and 2 (validation
  only) and the configuration with the best **3-seed mean** is retrained.
  Reason: the maximum of 24 single-seed scores favours a configuration that was
  lucky once (LightGBM v3: best trial 0.573 with seed 0, the same configuration
  averaged 0.431 over 5 seeds, below the untuned default 0.509). Same rule for
  every model (`reselect()` in `src/models/tune.py`), so the budget stays equal
  (24 trials + 6 re-runs).
- Applies to: LightGBM, the global LSTM, EA-LSTM, the distance ST-GNN, the
  Taccari-graph ST-GNN, and later the knowledge-graph models. Pastas variants
  are hypothesis tests chosen on validation, not tuned.
- **Ensembles:** members chosen on validation only; the number of candidate
  subsets is reported.
- **Reported prediction of a neural model:** the mean of its 5 seeds; the mean
  ± sd of the single-seed scores is reported next to it.
- **Refit on train + validation (secondary):** after selection, the chosen
  configuration is retrained on 2005 → April 2022 with the number of epochs
  (boosting rounds) found by early stopping, then scored on the test period.
  Reported as separate rows; the primary rows remain trained on 2005–2019 only.

## 6. Statistics

- Paired, well by well, on the core wells.
- **95 % interval** of the median paired difference by **cluster bootstrap**
  (4,000 resamples of 10 km Lambert-93 grid cells; `src/analysis/stats.py`).
  Wells in the same cell (nested piezometers, neighbours) are resampled
  together.
- **Paired Wilcoxon signed-rank p-value**, **Holm-adjusted** across the
  comparisons of one table (one period × metric).
- **A claim "A is better than B"** requires a Holm-adjusted p < 0.05 **and** a
  bootstrap interval that excludes 0. Otherwise the text says "no significant
  difference", whatever the medians are.

## 7. Inputs that are not allowed

- Observed heads in the simulation task (by definition).
- Any input derived from observed groundwater levels. In particular, drought
  restriction orders for **groundwater** alert zones are triggered by
  piezometers of the same aquifers and are excluded. Restrictions for
  **surface-water** zones (triggered by river flows) are allowed.
- Static attributes computed with data after the training period (for example
  the artesian share is computed on the training period only from dataset v3).
- The imputation flags of pumping are kept in the dataset for analysis but are
  **not** model inputs: they mark eras (2005–2011, 2024+) and would invite a
  time shortcut.

## 8. Claims about drivers (RQ2–RQ4)

- Weekly irrigation and canal volumes are spread with the climatic deficit, so
  within a year they are almost collinear with it (r = 0.92–0.97,
  `docs/feedback.md` §3.1). Until pumping data with independent timing exist,
  effects of pumping are claimed only from between-year and between-well
  variation, and attributions group "summer demand" (deficit + seasonal
  pumping) as one driver.
- No attribution is claimed for weeks whose pumping input is imputed.

## 9. Data versions

- Results of record come from **dataset v3** once it is built (real BNPE 2024,
  harmonised 2018 break, documented canal rule, river inputs). v1 and v2 stay
  frozen for reproducibility, with their results in `results/v1/` and
  `results/v2/`.
- Every results folder records the dataset version, the git commit and the
  configuration.

## 10. Planned comparisons for Phase 4 (to be confirmed at Gate 3)

The arms of `docs/feedback.md` §5.1: (A) baseline inputs, no graph; (B)
knowledge-graph features, no graph; (C) knowledge-graph features + Taccari
distance graph; (D) knowledge-graph features + knowledge-graph graph; (E) D with
the graph rewired (degrees preserved); (F) random and complete graphs. Primary
RQ1 contrasts: D vs C (edge semantics) and B vs A (knowledge as information).
