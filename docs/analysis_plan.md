# Analysis plan (written before the runs it governs)

**Version 2 · 2026-10-23** (version 1: 2026-10-20, in git) · Status: the
changes of version 2 were decided by Assil on 2026-10-23 after the second
external review (`docs/review_codex_2026-10-23.md`, response in
`docs/review_codex_response.md`); the Phase 4 families (§10) are confirmed at
Gate 3, then the plan is tagged `analysis-plan-v2` in git **before any Phase 4
run** (§11). Every result in the thesis and the paper follows this plan. A
change after results exist must be dated here, with its reason, and both
versions reported (§13 lists the changes of version 2).

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
- **Validated data (v2):** the `strict` variant keeps the test weeks whose every
  value is qualified "Correcte"; its coverage (wells, weeks) is reported next to
  every score. The v1 `validated` variant (less than half "Non qualifié") is
  kept for comparison; the two differ on 0.2–0.3 % of weeks. In the recovery the
  strict subset holds only 7 wells and 296 weeks (all weeks: 32 and 1,362), so
  **recovery-phase conclusions are provisional** until ADES validates 2025–2026
  (re-scored then, §11). Values qualified "Incorrecte" are dropped before the
  weekly mean from dataset v4 on.
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
| R2 **left-out monitored wells** | wells outside fold k (5 folds, stratified by aquifer group, seed 2026, `splits.json`; from v4 wells < 2 km apart share a fold) | the core wells of fold k, test periods; the 5 folds pooled |
| R3 **less data** | the most recent 25 % and 50 % of the training period (start 2016-04-01 and 2012-07-01; end 2019-12-31); from v4 the per-well statistics come from that window only | core wells, test periods |

- **Left-out wells, "dynamics" convention:** models predict the standardised
  head z; it is converted to metres with the held-out well's *own*
  training-period mean and standard deviation, which the model never sees. The
  score therefore measures the dynamics (timing and amplitude relative to the
  well's normal range), not the absolute level. Static attributes of the
  held-out well are allowed, **including its training-period artesian share,
  which is derived from its heads**. R2 is therefore a test of transfer to
  monitored wells left out of training, given their historical head
  statistics; it is never called prediction at an ungauged or unmonitored well.
- **Grouped folds (v2, dataset v4):** wells closer than 2 km (single linkage)
  form one block and blocks are dealt to the folds, balancing the core wells per
  aquifer group (4 Pliocene core wells per fold). In v3, 8 core wells had a core
  well of another fold within 500 m (nested sites of different units), which let
  the twin carry the answer. Spatial grouping follows Roberts et al. 2017
  (doi:10.1111/ecog.02881). The v3 random folds stay in `results/v3/` as the
  comparison. Early stopping and selection use the validation
  period of the *training* wells only. Pastas is calibrated per well and has no
  R2 result; the climatology benchmark uses the held-out well's own training
  data, consistent with the convention.
- **R3** keeps the forcing warm-up before the shortened training period. The
  validation and test periods are unchanged. From v4 the per-well mean, sd,
  climatology and artesian share are computed on the window only
  (`build_panel(train_start=...)`); with 2016–2019 only, the mean of a well
  moves by a median 0.16 m (max 1.82 m). The skill benchmark stays the
  full-period climatology, so every regime is measured with the same yardstick.

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
- **Dataset v4 re-runs (v2):** the baselines keep the configuration selected on
  v3 (v4 changes 71 training weeks of 29,784, the folds and the R3 statistics);
  only the final seeds and the regimes are re-run. The knowledge-graph models
  are tuned on v4 with the same budget.
- **Ensembles:** members chosen on validation only; the number of candidate
  subsets is reported. **Rule fixed 2026-10-20, before the v3 ensemble:** one
  candidate per model family (Pastas, LightGBM, recurrent, graph), the family's
  best run on validation; then every subset of the family winners (11 subsets
  for 4 families) is scored on validation. A search over all v3 runs (2,036
  subsets) would favour runs that are lucky on validation.
- **LightGBM inputs (decided 2026-10-20 by Assil, before the v3 ensemble and
  report):** the LightGBM baseline is the tuned run **without** each well's own
  training climatology as input (`lgbm_noclim_tuned`), so it gets the same
  information as the networks; that input would also leak into the
  unseen-wells regime. The runs with it (`lgbm_sim`, `lgbm_tuned`) are reported
  as sensitivity rows and are not ensemble candidates. On v3 the like-for-like
  run is also the better one on every split (validation 0.56 vs 0.51, drought
  NSE −0.12 vs −0.18).
- **Reported prediction of a neural model:** the mean of its 5 seeds; the mean
  ± sd of the single-seed scores is reported next to it.
- **Refit on train + validation (secondary):** after selection, the chosen
  configuration is retrained on 2005 → April 2022 with the number of epochs
  (boosting rounds) found by early stopping, then scored on the test period.
  Reported as separate rows; the primary rows remain trained on 2005–2019 only.

## 6. Statistics

- Paired, well by well, on the core wells. **Effect sizes come first:** the
  median paired difference and its interval.
- **95 % interval** of the median paired difference by **cluster bootstrap**
  (4,000 resamples of 10 km Lambert-93 grid cells; `src/analysis/stats.py`).
  Wells in the same cell (nested piezometers, neighbours) are resampled
  together. The 33 core wells fall in 14 cells.
- **p-value (v2): cluster sign-flip permutation test.** Under "no difference",
  the paired differences of a cell are as likely to have the opposite sign, so
  signs are flipped cell by cell, never well by well; statistic = the median
  paired difference; exact over the 2^14 sign patterns (smallest two-sided p
  0.0001). **Holm-adjusted** across the comparisons of one family. The per-well
  Wilcoxon p (which treats the wells as independent) is reported for comparison
  only.
- **A claim "A is better than B"** requires a Holm-adjusted cluster p < 0.05
  **and** a bootstrap interval that excludes 0. Otherwise the text gives the
  effect size and says "not significant with 14 clusters", whatever the medians
  are. With 14 clusters a moderate effect cannot reach significance; the text
  says so rather than leaning on borderline p-values.
- **Families:** the baseline report: every model against the hydrology
  reference, per period × metric (as in v1). Phase 4: one family per research
  question on the primary and co-primary endpoints (§10). Families are not
  redefined after results are seen.

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

### 7b. Information availability (added in v2)

**Simulation** is retrospective by definition: it uses the reconstructed
forcings of the whole record. The **forecast** task is a **hindcast with
reconstructed forcings**, not an operational forecast. The observed heads it
uses are causal (known at the issue week), but some inputs are not:

| Input | Available at issue week t−h? | Why |
|---|---|---|
| SAFRAN rain, ETP, effective rain, soil moisture | yes, with the SIM2 publication lag | daily reanalysis |
| Observed head (forecast only) | yes | last value at or before t−h |
| BNPE annual volumes | **no** | published 1–2 years later; 2025–26 imputed from later means |
| Weekly spread of irrigation and canal volumes | **no** | weights normalised by the deficit of the whole year |
| River discharge | mostly | gaps ≤ 8 weeks are interpolated between both ends |
| Static attributes, KG | yes | fixed before the test period |

Results of the forecast task are reported as hindcast skill; an operational
claim would need causal versions of the pumping and river inputs.

## 8. Claims about drivers (RQ2–RQ4)

- Weekly irrigation and canal volumes are spread with the climatic deficit, so
  within a year they are almost collinear with it (r = 0.92–0.97,
  `docs/feedback.md` §3.1). Until pumping data with independent timing exist,
  effects of pumping are claimed only from between-year and between-well
  variation, and attributions group "summer demand" (deficit + seasonal
  pumping) as one driver.
- No attribution is claimed for weeks whose pumping input is imputed.
- **Pumping reconstructions (v2):** the weekly pumping is a reconstruction from
  annual declarations. The main contrasts of §10 are repeated under three
  reconstructions: (1) the current one (irrigation and canals follow the
  year's April–October deficit; drinking water 50 % flat + 50 % seasonal);
  (2) flat drinking water; (3) irrigation following a fixed crop calendar (the
  mean weekly profile of the training years), independent of the year's
  weather. A conclusion is stated only if it holds under all three; otherwise
  the text reports which reconstruction it depends on.
- Pump → unit links carry a confidence measured on the recorded boreholes
  (`src/kg/pump_attribution.py`); conclusions that use them are checked with
  confident links only and with all links.

## 9. Data versions

- Results of record come from **dataset v4** (v2 of this plan): v3 (real BNPE
  2024, harmonised 2018 break, documented canal rule, river inputs) with the
  quality filter, the grouped folds and the R3 window statistics. v1–v3 stay
  frozen for reproducibility, with their results in `results/v1/`–`results/v3/`.
- Every results folder records the dataset version, the git commit and the
  configuration.

## 10. Planned comparisons for Phase 4 (to be confirmed at Gate 3)

The arms of `docs/feedback.md` §5.1: (A) baseline inputs, no graph; (B)
knowledge-graph features, no graph; (C) knowledge-graph features + Taccari
distance graph; (D) knowledge-graph features + knowledge-graph graph; (E) D with
the graph rewired (degrees preserved); (F) random and complete graphs. Primary
RQ1 contrasts: D vs C (edge semantics) and B vs A (knowledge as information).

Added in v2:
- **Families (proposal for Gate 3):** RQ1 = {B vs A, D vs C}; RQ2 = {soft vs
  none, hard vs none}; each on drought NSE and drought skill, Holm within the
  family (4 tests). Everything else is exploratory and labelled so.
- **Equivalence test, not an arm:** the edges exported by SPARQL from the KG
  must equal the edges built by pandas rules from the same tables (a test in
  `tests/`). Equal edges give equal predictions, so accuracy gains are credited
  to the knowledge; the ontology is credited with traceability, consistency
  and reuse (competency questions, SHACL, provenance), not with accuracy.
- **Satellite concept:** arm B is also run without `ProbablyIrrigatedParcel`
  (one ablation row).
- **Pumping robustness:** D vs C and B vs A under the three reconstructions of
  §8.
- **Hard monotonicity, conditions:** a sign holds by construction only if it
  holds on the whole path from the driver to the output. (1) The gain of a
  response may depend on static and KG features, never on the driver it
  constrains. (2) The residual network does not receive the constrained
  drivers (or is itself monotone in them). (3) A test checks the sign of the
  finite difference of the output with respect to each constrained driver on
  random inputs (Runje & Shankaranarayana 2023, arXiv:2205.11775, for monotone
  networks).
- **Semi-synthetic twin (RQ3), harder variants:** besides the response
  functions of the model and the two pumping-timing variants, the synthetic
  heads are also generated with (a) a response shape the model does not have
  (e.g. a delayed, non-linear threshold response), (b) a driver the model does
  not see, (c) wrong KG links (a share of pumps attributed to the wrong unit).
  Recovering contributions generated by the model's own response family would
  be a favourable test. **Pastas gains are a comparator, not causal ground
  truth.**

## 11. Freeze and confirmation (added in v2)

- The test period has informed diagnosis and decisions (for example the 2024–25
  level offset). The baseline results are therefore **exploratory** and
  described so.
- Before any Phase 4 run, this plan is tagged `analysis-plan-v2` in git (after
  Gate 3 confirms §10). The Phase 4 comparisons are then confirmatory.
- **Confirmation check:** at the end of Phase 4 every frozen model is also
  scored on (1) the weeks observed after the freeze date, and (2) the 2025–26
  weeks once ADES has validated them (strict variant). It is short, so it is
  reported as a check of direction and size, not as a new primary endpoint.

## 12. Wording of claims (added in v2)

- "Simulation" for the main task, "hindcast" for the forecast task, "left-out
  monitored wells" for R2.
- An exact additive decomposition explains the model's computation; it is not
  the physical contribution. **Ontology consistency** (entities exist, signs
  agree), **faithfulness** (fidelity+/−) and **causal correctness** (recovery on
  the twin) are three separate properties, each with its own evidence.
- Land use is static context (RPG 2016 and 2023); no annual land-use effect is
  claimed. `ProbablyIrrigatedParcel` is a heuristic unless it is checked against
  independent irrigation evidence; agreement with RPG crops does not validate
  irrigation.
- The use conflict on the Pliocene is the motivation; the thesis does not claim
  to predict conflicts.
- Pumping effects: missing measurements, forcing assumptions, model structure
  and groundwater memory remain competing explanations of the remaining error.

## 13. Changes in version 2 (2026-10-23)

Decided by Assil after the second external review; reasons and checks in
`docs/review_codex_response.md`.
1. §1 strict validated variant and coverage; recovery provisional. Reason: 71
   training weeks contained "Incorrecte" values; the recovery is 75 %
   unqualified.
2. §4 grouped folds; R2 wording; R3 window statistics. Reason: nested wells of
   different units were split across folds; R3 inherited statistics from the
   removed years.
3. §5 v4 re-runs keep the v3-selected configurations.
4. §6 cluster sign-flip test instead of the per-well Wilcoxon. Reason: wells
   are not independent. Effect on the v3 baseline report: the per-well test
   gave p_holm 0.002–0.04 for "ML better than Pastas in the drought", the
   cluster test 0.08–0.23; the effect sizes are unchanged.
5. §7b information availability; the forecast task is a hindcast.
6. §8 three pumping reconstructions.
7. §9 dataset v4 of record.
8. §10 families, equivalence test, satellite ablation, monotonicity conditions,
   harder twin.
9. §11 freeze tag and confirmation check; §12 wording.
