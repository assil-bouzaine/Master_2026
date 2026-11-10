# Analysis plan (written before the runs it governs)

**Version 2 · 2026-10-23, amended 2026-10-24/25 before the tag** (version 1:
2026-10-20, in git) · Status: the changes of version 2 were decided by Assil on
2026-10-23 after the second external review (`docs/review_codex_2026-10-23.md`,
response in `docs/review_codex_response.md`); the amendments of 2026-10-24/25
follow the third review (`docs/review_codex_2026-10-24.md`, response in
`docs/review_codex_2026-10-24_response.md`) and Assil's decisions of 2026-10-24
(§14). The Phase 4 families (§10) are confirmed at Gate 3, then the plan is
tagged `analysis-plan-v2` in git **before any Phase 4 run** (§11). Every result
in the thesis and the paper follows this plan. A change after results exist must
be dated here, with its reason, and both versions reported (§13 lists the changes
of version 2, §14 the amendments before the tag).

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
- **Suspect placeholders (from v4, amendment of 2026-10-24):** the weeks of a run
  of ≥ 28 days with a depth to water of exactly 0.00 m leave every scored
  variant (`src/dataset/placeholders.py`). It flags one case: CORNEILLA PD5
  (core, Pliocene), 413 days from 30 Nov 2022 to 16 Jan 2024 (60 weeks), all
  qualified "Correcte" by the producer, while flowing wells record negative
  depths and PD5 never does. The rule was written after the test period was
  seen, so the v4 primary table is also shown without it (`all_unmasked`). No
  flagged week falls in training or validation: no model is re-trained.
- **Drought class and hydrological errors (secondary, added 2026-10-24):** the
  simulated SGI class (monthly means over the observed weeks, the well's observed
  SGI reference up to 2019, BRGM IPS classes) is scored by exact and
  within-one-class accuracy, balanced accuracy, quadratic weighted kappa, and the
  probability of detection, false-alarm ratio and critical success index of low
  levels (SGI below the 20 % quantile); plus the timing and size of each year's
  minimum, the anomaly lag and the trough (`src/analysis/hydro_errors.py`,
  `docs/results_hydro_<version>.md`). Representative hydrographs are chosen by a
  stated rule (per aquifer group, the core well with the median drought NSE
  averaged over all runs), never by hand. A head is not water availability: no
  claim about availability, sustainable yield or conflicts follows from these
  scores.
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
- **What each regime may use (table added 2026-10-25; checked by
  `tests/test_regime_boundaries.py`).** "Head history" = observed heads of the
  wells trained on; forcings and static attributes are known for every year.

  | Information | R1 temporal | R2 left-out monitored wells | R3 less data (25 / 50 %) | Refit |
  |---|---|---|---|---|
  | Loss | training wells × train weeks with a head | wells outside fold k × train weeks | training wells × weeks from the window start (2016-04-01 / 2012-07-01) | train + validation weeks |
  | Early stopping | validation weeks of the core wells trained on | validation weeks of the core wells outside fold k | validation weeks (unchanged) | none: the epochs of the R1 seed |
  | Hyperparameters | selected on the validation weeks of all core wells | the same configuration (fixed-configuration transfer) | the same configuration | the same |
  | Input standardisation (neural), river-gap fills, exogenous node scaling | all training rows 2005–2019 | the same, held-out wells included (their forcings are known) | the same: the whole training period of the wells kept | as R1 |
  | Head statistics: mean, sd, climatology of z, artesian share | per well, 2005–2019 | per well, 2005–2019, held-out wells included ("dynamics" convention) | per well, the window only; a well without heads in the window leaves the regime (2016–2019: 4 non-core wells) | as R1 |
  | Graph | positions and static attributes; the one exception, the depth threshold of D's well links, uses the head anomalies this regime allows (§14 item 15) | the same; held-out wells stay as nodes (transductive), the threshold chosen without them | the same; the threshold chosen on the window's heads | as R1 |
  | Pumping reconstruction | annual declarations of every year, by the BNPE rules (allowed for simulation, §7b) | the same | the same | the same |
  | SGI reference | observed monthly means up to 2019 | the same | the same (not limited to the window) | the same |
  | Skill benchmark | training climatology 2005–2019 | the held-out well's own | the full-period climatology (same yardstick) | as R1 |

  Coverage of the windows (v4): every core well keeps at least 76 observed weeks
  in the 25 % window (HIPPO2: 76, the only one under two years) and 178 in the
  50 % window.
- **Reading of the table (stated 2026-10-25, third review §3.2).**
  - R3 reduces the *head history*, not the forcing history: the losses and the
    head-derived statistics (mean, sd, climatology, artesian share) use the
    window only (early stopping keeps the unchanged validation weeks; corrected
    2026-10-25: an earlier wording put early stopping in the window too), while
    the input standardisation of the neural models keeps the whole training
    period (forcings and static attributes are known for every year). The hyperparameters are those selected on the full
    training period, so R3 is a controlled reduction of fitting data, not a
    whole model development with 25 % of the history; and a shorter, more recent
    window changes both the amount *and the recency* of the training data.
  - R2 reuses the configuration selected on the validation weeks of *all* core
    wells (`<model>_tuning/best.json`): the held-out wells take no part in
    gradient updates or early stopping, but they did inform that selection. R2 is
    therefore a **fixed-configuration transfer** test. A nested check (selection
    on the other folds only) is planned for the primary D vs C contrast only.

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
- **Hydrology reference from v4 (decided by Assil on 2026-10-24, before any
  multistart result was seen):** the Pastas seasonal + canal model built from the
  *training heads only* (`--train-obs`; the default construction sets the initial
  constant from the whole series, test years included), each well's start chosen
  by the frozen rule of `src/analysis/pastas_stability.py` (lowest
  training-period simulation RMSE), whatever its test score. Its spread over the
  starts is reported with it. The full-series fits stay as historical rows and
  leave the ensemble's candidates.
- **Budget reporting (added 2026-10-24):** besides equal trial counts, the
  search spaces, completed and failed trials, recorded trial time, re-selection
  runs and the trainable parameters of each selection are reported
  (`docs/tuning_budget_v3.md`). The sizes differ (LSTM 78 k, EA-LSTM 57 k,
  distance ST-GNN 92 k, Taccari ST-GNN 230 k parameters): equal trials are not an
  equal capacity, and the text says so.
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
- **Paired support (added 2026-10-25):** both runs of a contrast must be scored on
  the same well-weeks; `stats.paired()` counts the wells where they differ
  (`support_mismatch`), and the primary contrasts use `strict=True`, which
  refuses such a pair.
- **Sensitivity of the cluster inference (fixed 2026-10-24, before any Phase 4
  result):** the interval and p_cluster are also given for grids of 5, 10 and
  20 km with the origin at 0 or shifted by half a cell, and the median difference
  with each 10 km cluster left out (`stats.cluster_sensitivity`). The 10 km grid
  at origin 0 stays the test of record; the sensitivity is shown next to it and
  never used to choose a grid. A coarse grid caps the attainable p (6 clusters:
  2/2⁶ = 0.031). The exact sign-flip test is exact under sign symmetry given the
  clustering; resampling the wells measures variation across this network
  *during one observed drought*, not over many droughts.
- **Sources of uncertainty are reported separately:** optimiser seeds (training
  variability), the three pumping reconstructions (§8), the pump-link policies
  (§8) and, in Phase 4, graph randomisation draws (§10). Seed spread is not
  observation, forcing or attribution uncertainty. A prediction interval, if one
  is added, is checked for empirical coverage on separate periods, without a
  calibration claim under the drought's distribution shift.

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
| RPG crop areas (crop-demand feature) | **no** | edition y holds the declarations of campaign y and is published afterwards (the 2025 edition was online in October 2026); 2005–2014 backfilled with 2015 |

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
  (2) flat drinking water; (3) irrigation following a fixed crop calendar,
  independent of the year's weather: each facility's annual volume is spread by
  the FAO-56 Kc calendar of the dated RPG crop mix around it, with the
  training-years' mean climate (§14 item 13; before 2026-10-25 this read "the
  mean weekly profile of the training years"). A conclusion is stated only if it holds under all three; otherwise
  the text reports which reconstruction it depends on.
- Pump → unit links carry a confidence measured on the recorded boreholes
  (`src/kg/pump_attribution.py`); conclusions that use them are checked with
  confident links only and with all links.
- **Coverage of the links (added 2026-10-24; `src/kg/pump_coverage.py`,
  `docs/pump_coverage.md`).** Under the main policy (confident + probable,
  decided 2026-10-24) the plain's declared groundwater volume 2012–2024 is 72.3 %
  attributed at unit-group resolution but 61.8 % at exact-unit resolution (the KG
  keeps flag_true links "probable" for the alluvium group only); counting the
  imputed years the model sees, 65.8 % and 56.2 %. Drinking water: 98.0 % /
  83.7 %. **Irrigation: 0 %** at both resolutions (85 % "possible", 15 %
  unknown). Every exported dataset reports this coverage by use × unit × year.
- **Unattributed pumping is an input, never zero (added 2026-10-24).** In every
  arm, the volume outside the policy (possible and unknown links) enters as a
  separate, explicitly labelled forcing (e.g. unattributed groundwater pumping
  within the well's radius), so all arms see the same forcing inventory and C and
  D differ only in edges (§10). An excluded volume is never read as "no effect".
- **What the pumping evidence supports (decided by Assil on 2026-10-24):** the
  main story is **drinking-water pressure on the Pliocene**, within the
  agricultural water-use context; the use conflict stays the motivation. Any
  claim about farm (irrigation) pumping comes only from the all-links sensitivity
  and is labelled provisional; the policy itself is unchanged and uncertain links
  are never upgraded to make the story work. The precision of a rule (e.g.
  flag_false 36/39, Wilson 95 % [0.80, 0.97]) is not the probability of one link.

## 9. Data versions

- Results of record come from **dataset v4** (v2 of this plan): v3 (real BNPE
  2024, harmonised 2018 break, documented canal rule, river inputs) with the
  quality filter, the grouped folds and the R3 window statistics. v1–v3 stay
  frozen for reproducibility, with their results in `results/v1/`–`results/v3/`.
- Every results folder records the dataset version, the git commit and the
  configuration. From 2026-10-24 (third review §7) the neural and LightGBM runs
  also save their fitted models (`seed_<k>.pt`, `model_seed_<k>.txt`) with a
  `schema.json` (inputs and their standardisation) and a `manifest.json` (hash of
  the code that ran, dataset file hashes, configuration, seeds, package and device
  versions; `src/models/manifest.py`). Pastas is replayed from its `params.csv`
  (`tests/test_replay.py`). The neural v4 finals saved before that date have no
  weights: they are re-run with weights before the freeze if they are to enter
  the post-freeze check (§11).

## 10. Planned comparisons for Phase 4 (to be confirmed at Gate 3)

The arms of `docs/feedback.md` §5.1: (A) baseline inputs, no graph; (B)
knowledge-graph features, no graph; (C) knowledge-graph features + Taccari
distance graph; (D) knowledge-graph features + knowledge-graph graph; (E) D with
the graph rewired (degrees preserved); (F) random and complete graphs. Primary
RQ1 contrasts: D vs C (edge semantics) and B vs A (knowledge as information).

**Experiment contract (decided by Assil on 2026-10-24, third review §4):** each
primary contrast changes one factor.

| Question | Held fixed | Changed |
|---|---|---|
| B vs A: does knowledge help as information? | backbone, fitting protocol, forcing inventory | the declared KG-derived features |
| D vs C: do semantic edges help? | node inventory, feature tensors, backbone, response functions, parameter budget, constraint setting, split and seed schedule | the edge-generation rule only |
| soft / hard vs none: do signs help? | graph, inputs, training population, response family | the constraint mechanism and its declared tuning parameters |
| hybrid vs black box | graph and available information | the architecture (read as an architecture comparison) |

- **Arms C–F share one backbone:** the main hybrid (§3 of CLAUDE.md). C uses the
  Taccari distance-rule edges, D the KG edges, E and F rewired / random /
  complete edges, all on the same node inventory and features. The Taccari ST-GNN
  baseline stays a baseline: comparing it with the hybrid changes architecture,
  temporal representation, constraints and graph at once.
- **Controls (fixed before any real-data result):** (1) the hybrid without
  message passing (a parameter-prediction model from static attributes only), to
  test whether shared response functions and statics already explain a gain;
  (2) a random-ID / shuffled-static control (Heudorfer et al. 2024,
  doi:10.5194/hess-28-525-2024: static features can act as identifiers); (3) a
  distance-matched rewiring next to the degree-preserving one, so a semantic gain
  is not a locality gain. Rewiring preserves relation types, edge directions,
  source/target type compatibility and degrees; several graph draws are run, the
  variation over draws is reported apart from the variation over seeds, and the
  edge overlap with the original graph is reported to show the randomisation
  changed the graph.
- **Nested selection** (selection on the other folds only) for the primary D vs
  C contrast in R2 (§4).

Added in v2:
- **Families (proposal for Gate 3):** RQ1 = {B vs A, D vs C}; RQ2 = {soft vs
  none, hard vs none}; each on drought NSE and drought skill, Holm within the
  family (4 tests). Everything else is exploratory and labelled so.
- **Equivalence test, not an arm:** the edges exported by SPARQL from the KG
  must equal the edges built by pandas rules from the same tables (a test in
  `tests/`). Accuracy gains are credited to the knowledge; the ontology is
  credited with traceability, consistency and reuse (competency questions,
  SHACL, provenance), not with accuracy. Equal edges are necessary, not
  sufficient, for equal predictions (third review, 2026-10-25): the test also
  compares node identity and order, relation directions, features and units,
  edge weights, masks, time alignment and constraint eligibility, and a forward
  pass with fixed weights must agree within a tolerance. The pandas side derives
  everything from the source tables, never from the graph's answers.
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
  networks). Added 2026-10-24 (third review §5.1): (4) the map from a physical
  intervention to the head is stated in full: raw volume or recharge, its derived
  and rolling features, scaling, graph processing, response kernel, gain,
  residual and inverse target transform; (5) a positive response uses a causal
  kernel with non-negative weights, a decrease a fixed negative gain; kernels are
  normalised so gain and kernel amplitude cannot trade scale, and kernel shape
  parameters never depend on the intervened driver; (6) an intervention changes
  the raw driver and *recomputes* its rolling copies (changing one precomputed
  feature is not a coherent intervention), and the residual network sees none of
  them nor their close proxies; (7) impulses, sustained changes, lags and
  boundary cases are tested with the training preprocessing; (8) the residual's
  share of the drought variance and its correlation with the constrained drivers
  are reported: a residual that carries most of the drought weakens the
  mechanistic reading even when the decomposition is exact.
- **Semi-synthetic twin (RQ3), harder variants:** besides the response
  functions of the model and the two pumping-timing variants, the synthetic
  heads are also generated with (a) a response shape the model does not have
  (e.g. a delayed, non-linear threshold response), (b) a driver the model does
  not see, (c) wrong KG links (a share of pumps attributed to the wrong unit).
  Recovering contributions generated by the model's own response family would
  be a favourable test. **Pastas gains are a comparator, not causal ground
  truth.** Added 2026-10-24 (third review §5.2): a small twin is built *before*
  the broad sweeps, to show the tests have power. It uses several generator
  parameter draws and noise levels (not only training seeds on one synthetic
  world), independent and climate-correlated pumping, an omitted driver,
  delayed / non-linear responses, wrong links and different shares of imputed
  pumping. The truth comes from a separate graph, and the graph given to the
  learner is corrupted from it (corrupting both together would not test wrong
  knowledge). Scores: prediction error, contribution-recovery error, response
  sign, response timescale and the error of controlled intervention responses;
  the explanation tests' detection and false-alarm rates are calibrated on these
  cases. Success criterion: at least one case of accurate heads with wrong driver
  contributions is detected. The twin validates behaviour under stated
  generators, not causal correctness in the real aquifer.

## 11. Freeze and confirmation (added in v2)

- The test period has informed diagnosis and decisions (for example the 2024–25
  level offset). The baseline results are therefore **exploratory** and
  described so.
- Before any Phase 4 run, this plan is tagged `analysis-plan-v2` in git (after
  Gate 3 confirms §10). The Phase 4 comparisons are then **pre-specified**:
  fixed before the Phase 4 runs, but on a benchmark (the 2022–25 drought) that
  was examined while the method was designed. The tag cannot make those
  observations unseen, so they are not called confirmatory (corrected
  2026-10-25, third review §3.1). Amendments after the tag are recorded, dated,
  without rewriting the story.
- **Confirmation check:** at the end of Phase 4 every frozen model is also
  scored on (1) the weeks observed after the freeze date: the only independent
  temporal check, scored with the saved frozen models and never used to select
  them; and (2) the 2025–26 weeks once ADES has validated them (strict
  variant): already examined, so a data-quality sensitivity check, not an
  independent test. Both are short, so they are reported as checks of direction
  and size, not as new primary endpoints.
- **Labels (added 2026-10-25):** every reported result carries one of
  *exploratory (development benchmark)* — all baseline results; *pre-specified,
  previously examined benchmark* — the Phase 4 contrasts of §10 on the 2022–25
  drought; *independent check* — the post-freeze weeks scored with saved frozen
  models. New post-freeze weeks may be too short or hydrologically different to
  test the drought claim; the text says so instead of calling them a
  confirmation.

## 12. Wording of claims (added in v2)

- "Simulation" for the main task, "hindcast" for the forecast task, "left-out
  monitored wells" and "fixed-configuration transfer" for R2; "pre-specified
  comparisons on a previously examined benchmark" for the Phase 4 results on
  the 2022–25 drought (§11).
- The SGI reference of each well is every monthly mean up to the end of the
  training period (2019), including the years before 2005 for long records
  (`src/dataset/build.py`, `sgi()`); it is not limited to the 2005–2019 training
  window. Chronos-2 fine-tuning likewise uses every week up to 2019, the
  2000–2004 warm-up years included. Neither uses information after 2019.
- An exact additive decomposition explains the model's computation; it is not
  the physical contribution. **Ontology consistency** (entities exist, signs
  agree), **faithfulness** (fidelity+/−) and **causal correctness** (recovery on
  the twin) are three separate properties, each with its own evidence.
- Land use enters as an annual crop-demand index (RPG 2015–2025, §14 item 13); no
  causal effect of land-use change is claimed. The claims each land-use contrast may
  support are fixed in §14 item 13 (before 2026-10-25 this read "static context (RPG 2016
  and 2023)"). `ProbablyIrrigatedParcel` is a heuristic unless it is checked against
  independent irrigation evidence; agreement with RPG crops does not validate
  irrigation.
- The use conflict on the Pliocene is the motivation; the thesis does not claim
  to predict conflicts.
- Pumping effects: missing measurements, forcing assumptions, model structure
  and groundwater memory remain competing explanations of the remaining error.
- "Model-attributed contribution" unless independent evidence supports a
  stronger reading; between-year and between-well pumping variation is more
  informative than the imposed within-year profile but can still be confounded.
- Main story (decided 2026-10-24): drinking-water pressure on the Pliocene; farm
  pumping effects only from the all-links sensitivity, labelled provisional (§8).
- Every explanation states its reference condition, units, period, data-quality
  status (strict / unqualified / masked weeks), evidence policy and unresolved
  pathways. Fidelity uses plausible driver-group interventions (not zeroed
  standardised inputs or deleted nodes), on a fixed sample of ordinary cases and
  failures besides the three case studies. The summer 2024 rise was used while
  designing the method: it is a case study, not an independent causal validation.
  Three outcomes are kept apart: faithfulness to the model, validity of the cited
  KG path, agreement with independent physical evidence.
- The Taccari-graph ST-GNN is "an adaptation of Taccari et al. 2024 to the simulation
  task": their study forecasts from a 5-week window of past heads, ours sees no head.
- Positioning: Jeong et al. 2026 (Water Res., doi:10.1016/j.watres.2026.126321)
  already compare learned responses with independently estimated residence
  times; the thesis does not claim that idea as new (`docs/literature/`).

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

## 14. Amendments before the tag (2026-10-24 to 2026-11-10)

After the third review (`docs/review_codex_2026-10-24.md`); verdicts and checks in
`docs/review_codex_2026-10-24_response.md`. Items 1–4 and 9–11 were decided by Assil
on 2026-10-24; the others make the plan say what the code already does or add
reporting. No result of Phase 4 exists; baseline results are exploratory (§11).
1. §1 suspect-placeholder mask from v4 (found after the test period was seen; both
   versions shown). Effect on the v4 core drought medians: NSE +0.01 to +0.10 by
   model, Pastas skill −0.05.
2. §5 hydrology reference from v4 = training-heads-only Pastas, frozen best-start rule.
3. §8 main story = drinking-water pressure; irrigation claims only from the all-links
   sensitivity; unattributed pumping as an explicit input in every arm.
4. §10 experiment contract: C–F share one backbone; controls fixed in advance.
5. §1 secondary drought-class and hydrological-error endpoints; hydrographs by rule.
6. §4 information-use table per regime, with its test.
7. §5 budget reporting (search spaces, trials, time, parameters).
8. §6 paired support (strict for primary contrasts), cluster sensitivity, separate
   uncertainty sources.
9. §9 fitted models and manifests saved; Pastas replay.
10. §10 monotonicity path, kernel and intervention rules; twin built early with
    generator draws and a truth graph separate from the learner's graph.
11. §11 result labels; §12 wording (attributed contributions, explanation fields,
    case studies, positioning).
12. §5 reporting, added 2026-10-25 **after** the multistart results were seen: besides
    the spread of the reference over its 10 starts, the v4 report repeats the drought-NSE
    test of record with each training-heads-only start as the reference (same models,
    Holm per start). A sensitivity table only: the reference and the test of record are
    unchanged.
13. **Land use (decided by Assil on 2026-10-25, after `docs/review_codex_2026-10-25.md`;
    written before any land-use run).** The subject's land-use pathway is tested, not
    assumed.
    - *Feature:* weekly potential irrigation demand per well, the sum over the crop
      classes assumed usually irrigated (`configs/lu_crop_classes.csv`: orchards,
      vegetables, artichokes, maize, citrus) of
      (clipped area within 3 km in RPG year y) × max(0, Kc(class, date) × ETP − rain),
      weekly sums on the well's SAFRAN cell, Kc on calendar dates from the FAO-56 stage
      tables (`src/dataset/crop_demand.py`). It is a potential requirement, never
      presented as metered irrigation (CQ7). Years before 2015 (no parcel-level RPG)
      carry the 2015 crop mix, flagged as a static backfill (§7b). *Wording fixed on
      2026-10-25, before any land-use run: "Kc(crop, month)" and "effective rain" became
      Kc on calendar dates and rain, as implemented; SIM2's effective rain is a water
      surplus, not the rain available to a crop.*
    - *Main index and sensitivity (decided by Assil on 2026-10-25, before any land-use
      run):* the classes assumed partly irrigated (vines, olives, nuts, fodder) are left
      out of the main index and added in a sensitivity row ("wide"). Reason: in the 2020
      agricultural census of dept 66, farms irrigating mainly vines irrigate 839 ha and
      fruit-and-vine farms 502 ha, against 19,840 ha of vines (about 4–7 %), while the
      specialised fruit and vegetable farms irrigate 78 % and 84 % of their land
      (`data/raw/agreste/`, DRAAF Occitanie, Agreste Essentiel, January 2024). Counting
      every vineyard would let mostly unirrigated vines dominate the index. The wide row
      is reported next to the main one, with the same seeds and settings.
    - *Test (RQ1, exploratory on the v4 baselines):* the tuned LightGBM without its
      own climatology and the tuned LSTM, each with and without the feature, v3
      settings, 5 seeds for the LSTM; a placebo with the crop areas permuted across
      wells (a derangement: each well keeps its weather and gets another well's crop
      areas). Heudorfer et al. 2024 (doi:10.5194/hess-28-525-2024), who found static
      features acting as identifiers, motivate such a control; they do not validate this
      particular design. Endpoint: drought-phase median NSE and skill on
      the core wells, cluster sign-flip, Holm over the two models; per aquifer group
      as secondary; the wide row and the placebo are reported with the same endpoint,
      not counted in the Holm family. A null or negative result is reported as is.
    - *Frozen variant (decided by Assil on 2026-10-25, before any land-use run, after the
      second Codex review of that day):* the main index with the crop areas of the 2019
      RPG edition (the last one inside the training period) in every year. Reported with
      the same endpoint, outside the Holm family: frozen vs without, and on vs frozen.
    - *What each result may claim.* A positive main contrast supports "incremental
      predictive information from the demand index", not an effect of land-use change. A
      gain over the placebo shows information tied to the well's own crop areas, but does
      not separate static agricultural geography, registration changes and actual crop
      change. Only a gain of the dated index over the frozen one supports a statement
      about the change of crop areas over the years, and even then registration changes
      remain part of it (`src/analysis/rpg_coverage.py`).
    - *Same-machine control (added by Claude on 2026-10-25, before any land-use run
      returned; which contrast is primary is Assil's decision, to be taken before the
      land-use results are scored):* the LSTM run without the feature (`lstm_tuned`) was
      trained on a Colab GPU, the land-use runs on Kaggle CPUs, so "on vs without" also
      compares two machines, whose arithmetic sends training along different paths. The
      land-use job therefore also re-trains each model without the feature
      (`<run>_lu_none`, same inputs, settings and seeds as `<run>`). Reported: none vs
      without (the machine effect; for LightGBM, whose run without the feature also ran on
      Kaggle, a reproducibility check) and on vs none (the same-machine contrast).
      **Decided by Assil on 2026-10-26, before the land-use runs were pulled or scored:
      the main contrast is on vs none** (strict paired support, Holm over the two models).
      On vs without (the wording written first) and none vs without (the machine effect)
      are reported outside the Holm family. The placebo, wide and frozen runs were also
      trained in the land-use job, so they are compared with none for the same reason; the
      per-group rows repeat on vs none. Disclosed: to check that the kernel had ended,
      Claude read the end of its log, which printed one summary, the LSTM frozen run
      (drought median NSE 0.006, skill 0.524); no on, none or without result had been seen.
    - *Run identity.* Land-use runs record the variant and a content hash of their
      land-use inputs (with the index file, the crop-class table and the RPG editions);
      the LSTM puts the hash into its fingerprint, so cached seeds made from other
      land-use inputs stop the run (`tests/test_land_use_inputs.py`).
    - *Phase 4:* crop demand and canal return are `lulcw:Influence` types of the
      hybrid; arm B reports with and without them. Before crop demand gets a response
      sign, its pathway is specified (groundwater abstraction by attributed facilities,
      canal-return recharge, or another qualified pathway) and unknown water sources stay
      unknown; it must not count the same assumed withdrawal twice, once through the
      reconstructed pumping (under reconstruction 3 irrigation already follows the crop
      calendar) and again as an independent demand effect (second Codex review of
      2026-10-25). To be settled at Gate 3.
    - *Reconstruction (3) of §8* uses the same Kc calendar and crop mix.
14. **The graph export of arms C–F (task 12.8; decided by Assil on 2026-10-26, before the
    export or any arm exists; proposal in `docs/notes/step12_ontology.md`, 12.8).**
    - *Abstraction nodes:* one node per facility, in every arm. C keeps its distance rule
      (facilities within 10 km, weight exp(−d / 5 km)) applied to facilities instead of 5 km
      fields: a field would mix facilities that the KG attributes to different units.
    - *Node inventory:* the same in C–F. For weather cells, river gauges or reaches and canal
      nodes it is the union of the nodes that the distance rule or the KG rule connects to a
      well; only the edges differ (the contract above).
    - *D's edges all come from the KG:* well ↔ well (same unit within 5 km, depth rule below),
      pump → well (influences selected by the policy, §3), and weather cell, river and canal →
      well from CQ4, CQ5 and CQ6, which are therefore built before the export (Assil preferred
      this to the proposal of keeping C's distance rules for these three relations as shared,
      non-semantic edges). Where the KG holds no documented link for a well, D has none:
      never a distance fallback. The share of wells without each relation is reported
      beside every D vs C result, since D then also differs from C in which exogenous
      inputs reach a well. If an input is missing (CQ6 has no supply-area polygons yet), the
      relation follows what the evidence supports, as the CQ contract states, and the gap is
      reported.
    - *Weather edges of D (CQ4; decided by Assil on 2026-10-26, before any CQ4 code):* the
      cells covering the outcrop of the well's unit inside a 5 km disc around the well (the
      radius of the pumping influences), weighted by intersection area and renormalised over
      the covered area; a well whose unit has no mapped outcrop within 5 km has no weather
      edge in D. Sensitivity: the unit-wide extent (all of the unit's outcrop in the forcing
      cells, the same weights for every well of a unit). Measured before the decision: 54 of
      the 59 wells with a mapped unit outcrop get edges; 5 Pliocene wells do not.
    - *Depth rule of the well links:* the |Δ depth| threshold is the one, among {10 m, 20 m,
      50 m, none}, that maximises the median training-period (to 2019) correlation of weekly
      head anomalies (head minus the well's training mean for that week of the year) of the
      linked pairs; frozen before any arm runs. Pairs without an
      investigation depth enter only the "none" variant (CQ11).
15. **After the Codex review of 2026-10-26 (`docs/review_codex_2026-10-26.md`; verdicts in
    `docs/review_codex_2026-10-26_response.md`). Written on 2026-10-27, before the export or
    any arm exists. Assil asked Claude to adopt the suggestions it judged sound; the points
    that refine one of his decisions are marked "to confirm by Assil before the export".**
    - *Exact paired support (§6, done).* Every scored group stores a digest of its exact
      scored weeks (`support`, `src/models/evaluate.py`); `stats.paired` compares digests,
      counts wells scored in one run only, and in strict mode (primary contrasts) refuses
      different weeks, one-sided wells and tables without digests. Equal counts on different
      weeks had passed before (`tests/test_stats.py` keeps the counterexample). All v4 tables
      were rescored on 2026-10-27: no v4 contrast against the reference had a difference the
      counts missed, and the LU-4 main contrasts pass the exact check with unchanged numbers.
    - *What D vs C can establish (items 4 and 14, §10, §12).* D and C are two complete
      connection policies: a D vs C effect can combine hydrogeological routing, sparsity and
      evidence coverage (5 Pliocene wells have no weather edge in D; canal relations may stay
      incomplete). Before any arm runs, the 12.8 export writes a per-well, per-relation
      inventory: direct connections, source coverage, weights, the inputs reachable within the
      message-passing depth, and any input given directly at a well node. A D vs C result is
      worded as the benefit or cost of the KG connection policy; a semantic-routing reading
      needs the degree- and distance-matched controls (E, F). A coverage-matched diagnostic,
      if wanted, is defined before any score and kept apart from the main arm; a subset of
      wells is chosen by metadata, never by which wells favour D.
    - *Depth threshold per regime (item 14; to confirm by Assil before the export).* The
      threshold is chosen from head anomalies, so it is target information and must stay
      inside each regime's allowed heads (the table of §4 is amended): R1 and the refit, the
      training wells to 2019; R2, for each fold k, only the wells outside fold k (within the
      nested D vs C selection already planned for R2); R3, only the window's head weeks. Of
      the 47 same-unit pairs within 5 km, 0 differ by at most 10 m, 2 by at most 20 m and 13
      by at most 50 m (42 have both depths), so a maximum of medians would compare 2 pairs
      with 47. Proposed: a threshold is eligible only if it keeps at least 10 linked pairs,
      each with at least 104 shared training weeks; ties (medians within 0.02) go to the
      looser threshold; recorded per regime and fold: candidates, qualifying pairs, shared
      weeks, missing-depth exclusions, the medians and the choice. A threshold chosen once on
      all wells and the full training period may appear only as a fixed-development
      sensitivity, labelled as using the held-out wells' (R2) or out-of-window (R3) heads.
      Spatially structured validation follows the intended prediction setting (Roberts et al.
      2017, doi:10.1111/ecog.02881); applying it to graph selection is ours.
    - *Recharge edges (item 14 weather edges; CQ4).* The 5 km local outcrop rule stays as the
      approved, declared approximation, with the unit-wide sensitivity; what each represents
      and omits is stated with every result. The local rule represents diffuse recharge on the
      outcrop of the well's own unit near the well; it omits lateral inflow from distant
      outcrops (partly in the unit-wide variant), inflow from the Corbières karst and the
      peripheral massifs, infiltration of the Têt and its Quaternary aquifer upstream
      (Bouleternère to Saint-Féliu-d'Amont), downward leakage from the Quaternary, canal
      return flow (CQ6) and river infiltration (CQ5). For the Pliocene these omitted pathways
      are the main ones: rain infiltration alone does not recharge the deep aquifers
      (Syndicat Mixte des Nappes du Roussillon, "Présentation des nappes",
      https://nappes-roussillon.fr/en-pratique/fonctionnement-des-nappes/, read 2026-10-27);
      in the Têt sector, downward leakage from the Quaternary to the Pliocene follows Pliocene
      pumping and was about 8–10 % of the water brought by the canals in September 2017,
      while 60–70 % of the canal water returned to the Têt upstream of Perpignan (Ladouche &
      Caballero 2022, BRGM/RP-71486-FR, Dem'Eaux Roussillon production #11b, read
      2026-10-27). The unit-wide extent (the forcing cells) also clips two units: 15 % of the
      mapped outcrop of 681AF00 and 9 % of 681AO00 lie outside the cells, and CQ4 answers
      "partial" there.
    - *One recharge proxy per influence.* SIM2's effective rain (PE) equals rain minus actual
      evapotranspiration (EVAP) within 0.13 % over 2006–2025 in every cell of the dataset, and
      it is close to drainage plus runoff (median cell: PE 183 mm/yr, DRAINC + RUNC 178): soil
      drainage is part of the same surplus. A recharge influence therefore uses one of them
      (PE in the main runs, matching "effective rain raises the head" of the design; DRAINC as
      a sensitivity), named a recharge proxy, never both as independent water inputs; to settle
      at Gate 3 together with the sign constraint. *In the graph since 2026-10-27 (CQ4 increment
      2):* one `lulcw:Influence` per weather cell and well attribution, in the 5 km search zone and
      in the unit-wide extent, with PE as its driver (`lulcw:proxyFor lulcw:GroundwaterRecharge`),
      the non-decreasing sign marked eligible and the omitted pathways listed
      (`lulcw:omitsPathway`); a shape refuses two proxies of one surplus on one path. No recharge
      constraint is applied before Gate 3 confirms this item.
    - *Cartographic meaning of "exact unit".* An exact-unit attribution (CQ2, CQ8) means the
      same mapped BD LISA entity; it does not establish a common screened horizon or a
      hydraulic connection, which matters in the Pliocene multilayer.
    - *Confirmed by Assil on 2026-11-06, before the export:* the per-regime depth threshold as
      proposed above (minimum support, tie rule, records).
    - *Bounded domain review before the broad sweeps.* The two LU-6 wells (MILLAS C2-1, the
      alluvium; PONTEILLA NYLS-1, the Pliocene) and their recharge, abstraction and canal
      pathways go to the supervisor or a hydrogeologist (SMNPR, BRGM) for a targeted check of
      quantities and units, not only geometry; not a replacement of the pipeline by a
      groundwater simulator.
    - *Land-use result wording (item 13).* Summaries say "no detectable improvement from this
      demand index under these models, settings, wells and drought period" (the LSTM interval
      still reaches a median gain of about +0.16 NSE), never "land use adds no information";
      the two alluvium groups (4 and 2 core wells) carry no regional claim. A future
      equivalence claim needs a negligible-effect margin fixed in advance.
    - *Alignment evaluation (12.9), protocol fixed before the gold set is filled:* see the
      12.9 section of `docs/notes/step12_ontology.md` and `src/kg/agrovoc_gold.py`.
    - *Reproducibility.* New run manifests hash every dataset file a run reads (rivers,
      gauges and pumping points were missing) and the raw SAFRAN grid; a base panel cache is
      refused when its dataset files changed; `docs/run_inventory_v4.md` lists which runs are
      replayable (38), recomputable (4) or predictions only (18, plus the EA-LSTM folds, 1 of
      5 with checkpoints). Old manifests are not completed after the fact; a model needed for
      the confirmation check or an intervention is rerun under a new run identity. The 12.8
      export will bind to the graph release (`src/kg/release.py`) and the policy, feature and
      code versions.
    - *Order of the next steps (Codex §9, agreed):* a consistent CQ4 release with its
      missing-evidence safeguards (done 2026-10-27); exact support (done); the D coverage
      inventory and the per-regime threshold rule; the export and the two-well executable path
      (source observations → KG derivation → tensors → a model output → a contribution
      explanation); the small, difficult twin; then the frozen primary contrasts. CQ5 and CQ6
      get a bounded evidence search and keep documented gaps; no canal service area is
      invented to complete a diagram.
16. **River and canal edges of arm D (CQ5, CQ6; decided by Assil on 2026-11-06, before any CQ5
    code; sources and measurements in `docs/notes/step12_ontology.md`, 2026-11-06).**
    - *Gauge pool:* the 5 full-record gauges of C (Têt at Rodès and Perpignan, Agly at Estagel,
      Tech at Le Boulou and Argelès). D connects a well to the pool gauge on a watercourse the
      graph associates with the well's unit in its 5 km zone; a well whose associated river has
      no pool gauge (the Réart) has no river edge in D, reported with every D vs C result.
    - *Associations giving an edge:* the river runs on the outcrop of the well's unit, or over the
      units that cover it ("via overlying units"), or a source documents an exchange between that
      unit and a section with reaches in the zone ("documented lateral"). Measured before the
      decision: 32 wells (22 core) with the pool, before the documented lateral links.
    - *Sign:* where connected, the exchange flux grows with the river stage whatever its
      direction (q = C (h_river − h_aquifer), the MODFLOW river package, Harbaugh 2005,
      doi:10.3133/tm6A16), so a non-decreasing head response to discharge is eligible only on
      outcrop or documented lateral with a documented exchange that is not "independent"; over
      cover, never. Documented directions are states kept with their period (the sources disagree
      on the Têt above the Comelade); the use of the sign as a constraint is settled at Gate 3.
    - *Canal edges:* no command-area map exists for the plain. C's plain canal node connects to a
      well whose unit has a BD TOPO canal crossing its outcrop within 5 km and a documented
      canal-return pathway into that unit (FRDG351, BRGM/RP-71486-FR); the sign "canal return
      raises the alluvium head" is eligible there, settled at Gate 3. The command areas stay a
      documented gap.
    - *In the graph since 2026-11-06 (release of 09:32 UTC; step note, "CQ5 and CQ6 built"):*
      river edges for 35 wells (24 core): the 32 measured above plus three ancient-alluvium wells
      linked by a documented lateral exchange; an eligible sign for 7 (5 core), over cover only
      18 (16 core); associated rivers without a pool gauge for 17 wells (4 core), none found for 7
      (4 core). Canal edges for 5 wells (4 core), 2 eligible (stated returns into the recent
      alluvium). The export (12.8) reads them from the graph.
    - *Corrected the same afternoon (item 17; release rebuilt 14:28–14:43):* two of the four
      documented lateral links rested on FRDG351's body-level table alone and are gone (HIPPO2,
      10915X0395/PZ on the Agly): river edges for **34 wells (23 core)**; an eligible sign for **3
      wells (2 core: MILLAS C2-1, CORBERE; and 10962X0075/PZ)**, each on a BRGM statement about the
      unit itself; BARQUA, 10915X0395/PZ (Têt) and 10972X0094/111111 keep their edges, documented
      only for an aggregate (❓ item 17). Over cover only, the gauge gaps and the canal edges are
      unchanged.
17. **After the Codex review of 2026-11-06 (`docs/review_codex_2026-11-06.md`; verdicts and checks in
    `docs/review_codex_2026-11-06_response.md`): evidence scope, incomplete searches and constraint
    decisions. Points marked ❓ are for Assil at Gate 3; the rest makes the graph say what its
    sources say.**
    - *Subject of a statement (R1):* a statement is about a unit itself, or about an aggregate (a
      groundwater body of several units, or a group the source names: "the Quaternary
      formations"). Membership never stands for evidence about each member: an aggregate
      statement makes no documented lateral association and no eligible sign. On outcrop it is
      localised to the unit in contact with the river (a separate, stated inference, kept for
      CQ5 and the explanations). Item 16's "documented lateral" therefore reads "an exchange
      documented for the unit itself". ❓ May a body-level statement localised by the outcrop make
      a river sign eligible? It concerns BARQUA (Agly), 10915X0395/PZ (Têt) and 10972X0094/111111
      (Tech), whose only sources are FRDG351's table, the EVP Têt and BRGM's "Quaternary
      formations".
    - *Measurements at a site (Q3):* a statement measured at a well (BRGM's mixing proportions at
      MILLAS C2-1) applies only in that well's zone.
    - *Constraint decisions (R2):* a sign constrains a model only when three layers accept it: the
      influence's eligibility (its pathway evidence, derived by the rules), the proxy review (is
      the driver an adequate stand-in for what the mechanism responds to) and the approval. The
      graph records the last two per mechanism and export policy (`lulcw:ConstraintDecision`, from
      `configs/constraint_decisions.csv`): pumping accepted (CLAUDE.md §3); recharge, river and
      canal pending, so none of their signs constrains a model before Gate 3 (default off).
      ❓ Proxy adequacy of (a) a pool gauge's weekly discharge for the river stage near the well
      (diversions, regulation and intervening reaches in between; a gauge downstream of the zone
      is a proxy, not a cause), (b) the plain's summed canal diversions (181 intakes) for the water
      reaching one unit's outcrop, (c) effective rainfall for recharge (item 15); and, where hard
      constraints stay off, whether a declared soft-prior sensitivity is run.
    - *Conflicts and periods (R4):* opposite states conflict only for the same or overlapping
      stretches (`lulcw:overlapsSection`: lines running together over at least 500 m), when both
      are dated with overlapping periods (a contradiction under comparable conditions) or one is
      undated (comparability unresolved); opposite states for different stretches or disjoint
      periods are variation. CQ5 and CQ6 take an optional requested period, report undated
      evidence as such, and an influence states that its evidence serves as one static hypothesis
      for every modelled week.
    - *Evidence method (R4):* each statement records how its finding was obtained (differential
      gauging, geochemical tracing, water balance, or a synthesis that does not say), separate from
      its hedging. ❓ The canal eligibility rule uses the source's wording ("stated"); a method
      criterion (measured or traced) could replace it, since wording is not calibration. Both give
      the same eligible canal edges today.
    - *Incomplete searches (Q1, Q2):* reaches off the geological map make a negative CQ8 answer
      (none_found, no_pool_gauge) unknown and a documented CQ5 answer partial.
    - *Alignments (R3):* `HydrographicReach ⊑ HY_FlowPath` withdrawn (river reaches: a close
      match; canal reaches realise no catchment); HY_River's `skos:broader` kept as the source
      states it; `Piezometer ⊑ GW_Well` withdrawn as well, found by the ledger's counterexample
      check (some monitoring points are springs: a close match). The ledger
      (`ontology/alignments/ledger.csv`) lists every correspondence, the rejected ones included,
      with the required and forbidden entailments HermiT checks (test_ontology gate 8).
    - *Release identity:* code versions carry the hash of uncommitted changes, the facts summary
      the hashes of the configuration and snapshot manifests, and the raw snapshots are pinned
      (`configs/snapshots.json`).
    - *Export (12.8), proposed, ❓ to confirm before scoring:* when several evidence paths join one
      driver to one well for one relation (two candidate units, or two associations), the export
      makes one edge, lists the paths, never multiplies the input, and gives the edge an eligible
      sign only if every selected path gives that same eligible sign (pumping already counts each
      facility once per well, item 14). The per-well, per-relation inventory comes before any arm
      is scored, and the raw D vs C contrast is reported as a contrast of whole connection policies
      (item 15).
    - *Alignment benchmark (12.9):* candidate recall@k is reported apart from matching accuracy;
      joint target-and-relation correctness beside target accuracy and relation accuracy; strict
      and alternative-target scores and no-match errors visible; near-duplicate crop labels across
      the development and evaluation codes are audited and reported without changing the frozen
      split; the blind second annotations and their adjudication are kept, and the 30-code
      subset's agreement is not generalised to all 198 codes; the result is named an
      "RPG-to-AGROVOC concept and code alignment benchmark".
18. **After the review of 2026-11-10 (`fable_review.md`; read-only checks on the saved v4 tables, its
    Appendix A). Assil, the same day, after Claude listed five recommended decisions and proposed to
    leave the others for Gate 3: "okay start working and u have the permission to do anything". Claude
    reads this as the approval of the five points below (Claude's reading; Assil may still change any
    of them before the tag). No Phase 4 result exists; everything here is fixed before the first ladder
    run is scored.**
    - *Why.* (a) The same tuned model trained on other seeds moves the median paired drought ΔNSE
      by up to 0.12 (two seeds per side; about 0.03 typical and 0.08 at worst for five per side, by
      extrapolation), which is larger than the effects measured so far (land use +0.016 and +0.001,
      machine −0.032). (b) With 14 clusters, a uniform gain must reach about 0.05–0.10 NSE to be
      detected between two arms of one backbone, and 0.25–0.5 if the arms differ as much as today's
      two graph models. (c) ΔNSE and Δskill have the same sign in every well (the same MSE
      difference under two scalings). (d) In the Pastas multistart the recharge parameters are stable
      across starts while the pumping and canal responses are not (time scales differing tenfold, at
      the 27-year bound), and a well's training NSE says little about its drought NSE (rank
      correlation across starts 0.19): the superposition structure is not identified per well.
    - *Primary effect measure of the Phase 4 contrasts (§1, §6, §10).* For each contrast, the
      per-well **log(RMSE_a / RMSE_b) in the drought phase** on the same well-weeks (negative: a is
      better): median, cluster-bootstrap interval, cluster sign-flip test. Median NSE, skill, KGE''
      and RMSE of each model stay in every table as descriptions. The Holm families of §10 become
      RQ1 = {B vs A, D vs C} and RQ2 = {soft vs none, hard vs none}, one test each (two per
      family instead of four). The baseline report keeps its NSE and skill tests (exploratory,
      already published in the notes). ❓ Gate 3: the smallest effect of interest (proposed: a
      median RMSE reduction of 5 %, log ratio −0.05), so that a contrast is reported as detected,
      compatible with no effect larger than the interval's end, or undecided.
    - *Seed controls (§6).* The primary arms use **10 seeds**. Each primary contrast is shown with
      its **same-arm band**: the distribution of the contrast statistic between random disjoint
      5-seed means of one arm (both arms, pooled). A difference inside the band is reported as
      not distinguishable from training noise, whatever its p-value. The arms of a contrast are
      trained on one machine type.
    - *Model ladder (§10; refines the experiment contract of 2026-10-24, does not replace arms A–F).*
      The hybrid is built in rungs, each adding one ingredient: (1) the response superposition for
      all wells together, per-well parameters, signs by construction, bounded kernels
      (`src/models/response.py`, mode free); (2) partial pooling towards the aquifer group (mode
      pooled, penalty λ), with one response per group as the other end (mode shared);
      (3) parameters predicted from static and KG features, no message passing (control 1 of §10);
      (4) stresses routed by the KG edges or by the distance rule on the same model: **the primary
      form of D vs C**; (5) message passing over the well links, secondary. Each rung with and
      without the bounded residual once it exists. ❓ Gate 3 confirms rungs 3–5 and the routing
      contrast as primary.
    - *Rungs 1–2, protocol (fixed 2026-11-10, before any run).* Inputs of the Pastas reference
      (weather of the well's cell, seasonal drinking-water pumping within 3 km, plain canal volume),
      weekly. Gamma kernels on 312 weeks, scale a in (0.5, 52) weeks, shape n in (0.5, 3), gains
      signed by softplus, evaporation factor in (0, 1.5); loss = mean over wells of MSE / sd² on
      training weeks; Adam, learning rate 0.05, at most 4,000 steps, early stopping on the median
      validation NSE of the core wells (checked every 20 steps, patience 15 checks); 10 starts
      (seeds 0–9; starting values drawn around the defaults, sd 0.5 on the unconstrained scale).
      Runs: free, shared, pooled with λ in {0.01, 0.1, 1, 10}; the pooled run reported is the one
      with the best validation median NSE of its 10-start mean. Two sensitivity runs of the free
      mode: a up to 104 weeks on 520 weeks; SIM2 effective rainfall instead of rain − f·ETP.
      Reported for every run and for the Pastas multistart beside it: drought and validation scores
      of the mean prediction and of the single starts; **stability across starts**: per core well,
      the range of the drought NSE; per parameter, (max − min) / |median|; per stress, the sd across
      starts of the mean contribution over the drought phase, in units of the well's training sd.
      Label: exploratory (development benchmark), like every baseline result.
    - *Added 2026-11-10 after the runs were launched and before any of their results was read
      (Caballero & Ladouche 2015, doi:10.5194/hessd-12-10109-2015, read that day).* BRGM's transfer
      model of two of our core wells finds impulse responses of 520 days (10972X0137/PONT, Argelès)
      and 300 days (10908X0263/FIGUER, Perpignan), mean transit times of 220 and 89 days, the
      maximum response to seasonal pumping 75 days after it starts. The bounds of the rungs (scale
      up to 52 weeks, weights over 312 weeks) are therefore wider than any published response of this
      aquifer; that paper is their source. **Independent comparator, fixed now:** at those two wells
      the ladder report gives, per start, the mean lag of the learned recharge response beside 220
      and 89 days, and the week of the largest weight of the pumping response beside 75 days. It is a
      comparison with a published model that used measured monthly pumping (1998–2007), not with a
      measurement. **Sensitivity defined now (❓ Gate 3 decides whether it becomes the main
      structure, `fable_review.md` §6.2):** pumping split as in that paper into a *permanent* part
      (per well and calendar year, the mean weekly pumping of January–March and October–December:
      constant within a year) and a *seasonal* part (the rest, not below 0), each with its own
      response and a non-positive gain; run in the free mode and in the pooled mode with the λ
      chosen above (`--pumping split`).
    - *First results of rungs 1–2 (2026-11-10, `docs/results_ladder_v4.md`; exploratory) and the
      follow-ups they led to, defined after those results were read and labelled so.* Read: the free
      mode is better than the Pastas reference in the drought (median log RMSE ratio −0.15, interval
      [−0.28, −0.06], outside its same-arm band of ±0.07) and worse than the tuned LSTM (+0.10); a
      well's drought NSE still moves by a median 1.17 between starts, as in Pastas; pooling towards
      the five aquifer groups steadies it (0.44 at λ = 0.1) and costs accuracy; one response per
      group is poor (validation 0.11). Early stopping ends most starts after 140–330 steps, so the
      spread over starts may partly be "stopped near the starting values". **Follow-up runs**
      (step `ladder2`, 10 starts each; none replaces a run above): (a) *diagnostic:* free and
      pooled λ = 0.1 trained for a fixed 3,000 steps without early stopping: if the spread over
      starts stays, it is several optima; if it shrinks, it was the stopping; (b) the permanent +
      seasonal pumping sensitivity defined above, free and pooled λ = 0.01; (c) *sharing in each
      well's own units:* gains in units of the well's training sd (`--gain-units sd`), pooled with
      λ in {0.01, 0.1, 1} and shared, because the heads of one group swing by centimetres at some
      wells and metres at others. Reported in the same tables, in their own block.
    - *The twin's role (§10).* Besides RQ3, the twin carries RQ1–RQ2 with power: C against D, and
      constraints off / soft / hard, over many synthetic worlds that vary the between-year pumping
      signal against the noise, the share of wrong pump links given to the learner and the share of
      unattributed pumping; the real data are placed on that map. The dials and the grid are
      written here before any real-data arm is scored (to add with the twin's design).
    - *Ontology.* Feature-frozen at 0.7.x: only what the export (12.8) needs, the INSPIRE alignment
      file and defect fixes. CQ9, 13, 14, 16 stay minimal fixtures or future work (to state at Gate 3).
    - *Left for Gate 3 (not approved):* the pumping structure of `fable_review.md` §6.2, the Pastas
      sensitivity rows (recharge only, capped time scales, start chosen on validation: post hoc),
      EuroCrops as a second alignment benchmark, text extraction scored against the 32 curated
      statements, Chronos-2 and the forecast task in the thesis only, a time-reversed second test.
