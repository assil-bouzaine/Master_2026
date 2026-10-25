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
  | Graph | positions and static attributes, never heads | the same; held-out wells stay as nodes (transductive) | the same | the same |
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
- Land use is static context (RPG 2016 and 2023); no annual land-use effect is
  claimed. `ProbablyIrrigatedParcel` is a heuristic unless it is checked against
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

## 14. Amendments before the tag (2026-10-24/25)

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
