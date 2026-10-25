# Step 12b: fixes from the second external review (2026-10-23)

The review is `docs/review_codex_2026-10-23.md`; the point-by-point response, with every
number checked, is `docs/review_codex_response.md`. Assil's decisions of the same day are
in CLAUDE.md §7.

## What was done

1. **Checked the review against the data and the code.** All of its numbers were right:
   - 71 training weeks with "Incorrecte" values
   - 52 % / 75 % unqualified data in 2025 / 2026
   - 2025–26 pumping fully imputed
   - 8 core wells with a cross-fold neighbour < 500 m
   - the artesian share used for held-out wells
   - 14 spatial clusters
2. **Dataset v4** (`PFE_DATASET=v4 python -m src.dataset.build`, built 2026-10-23,
   `data/processed/dataset_v4`). It is v3 plus:
   - **Quality filter.** 449 values qualified "Incorrecte" (or "non définissable") are
     dropped before the weekly mean: 8 model-window weeks change, 63 disappear (the 347
     days of F3 in 2007). Forcings, rivers, pumping and restrictions are byte-identical to
     v3.
   - **Reconstructed values.** The share of producer-reconstructed values is stored per
     week (`share_reconstructed`; 0.6 % of test values).
   - **Grouped folds.** Wells < 2 km apart are linked into blocks (45 blocks) and blocks
     are dealt to the 5 folds. The deal balances the core wells of each aquifer group
     first: 4 Pliocene core wells per fold, 12–15 wells per fold. The closest wells in
     different folds are now 2,153 m apart; in v3 they were 20 m apart (C2-1/C2-2).
   - **R3 windows.** Artesian shares are stored for each R3 window
     (`pct_days_artesian_f25/_f50`).
3. **Evaluation.**
   - A `strict` variant: test weeks whose every value is "Correcte".
   - Its coverage (`n_weeks`) appears in every summary.
4. **Statistics.** A cluster sign-flip permutation test (`src/analysis/stats.py`):
   - Signs are flipped cell by cell, over the 14 cells of 10 km; the statistic is the
     median paired difference; it is exact over 2^14 patterns.
   - Holm is now applied to it.
   - Tested against a brute-force reference in `tests/test_stats.py`.
5. **Regime R3 (less data).** From v4, `build_panel(train_start=...)` computes each well's
   mean, sd, climatology and artesian share on the window only. It is used by the LSTM,
   the ST-GNNs and LightGBM.
6. **The forecast task is renamed a hindcast.**
   - The weekly pumping spreads an annual total with weights normalised over the whole
     year, which needs information after the issue week.
   - Docstring and analysis plan corrected; audit table in `docs/analysis_plan.md` §7b.
7. **Task 12.3: pump → unit attribution** (`src/kg/pump_attribution.py`); results below.
8. **Analysis plan v2** (`docs/analysis_plan.md`; §13 lists the changes), and CLAUDE.md
   updated (umbrella question, §3 decisions, corrected findings).
9. **v4 re-run machinery** (the selection made on v3 is reused, no new tuning):
   - `scripts/v4_from_v3.py` copies the `best.json` files.
   - `scripts/run_v4_cpu.sh` runs the laptop baselines.
   - `lgbm.py --final-only` trains LightGBM's 5 seeds without a new search.
   - `run_gpu.sh` has a new `final:<model>` step.
   - `colab_run.py`, `make_gpu_bundle.py` and `colab_pull.py` handle `PFE_DATASET=v4`.
10. **Tests (run with `python -m tests.<name>`):**
    - `test_stats`
    - `test_folds` (synthetic blocks, plus the invariants of the built v4)
    - `test_pump_attribution`

## Results worth remembering

**The significance claim changes.** On the v3 report, the per-well Wilcoxon test said "ML
better than Pastas in the drought" with p_holm 0.002–0.04. The cluster test on the same
numbers gives p_holm 0.08–0.23.
- The effects are large: median ΔNSE +0.6 to +1.0, and most cluster-bootstrap intervals
  exclude 0.
- With 14 clusters, they are not significant at 5 %.
- The family of tests is not redefined to rescue significance: that would be p-hacking.
  The thesis gives effect sizes first.

**Validated data are thin at the end.** The strict variant keeps, for the LSTM:
- drought phase: 27 wells and 3,948 weeks (all weeks: 33 wells, 6,052 weeks)
- recovery phase: **7 wells and 296 weeks** (all weeks: 32 wells, 1,362 weeks)

So recovery-phase conclusions are provisional. Re-score when ADES validates 2025–26.

**R3 was inheriting information.** With 2016–2019 only, a well's mean moves by a median
0.16 m (max 1.82 m) and its sd by a median 13 % (range 0.35–1.15 × the full-period sd).

### Pump → unit attribution (task 12.3, CQ2)

The evidence for each groundwater ouvrage:
- **record:** the BD LISA unit of the ADES quality station with the same BSS code, plus
  its investigation depth
- **flag:** the BNPE flag `nappe_accompagnement` (the aquifer is connected to a river)
- **stack:** the BD LISA stack under the point
- **name:** dug well ("puits") or "profond"

Results on the 130 distinct recorded boreholes:

| Rule (record not used) | Fires on | Right group | Right entity | Finds (recall) |
|---|---|---|---|---|
| flag True → the alluvial unit at or within 1 km of the point | 19 | **0.95** | 0.63 | 0.86 of the alluvium boreholes |
| flag False **and** Pliocene under the point → Pliocene | 39 | **0.92** (0.82 against the raw record) | 0.92 | 0.90 of the Pliocene boreholes |

- **False alone is not enough.** Among the coded points of the plain, a False flag means
  Pliocene in only 53 of 112 cases: it also covers karst and other units. The stack is
  what makes the rule work. The previous note read "50 of 53 Pliocene points are False",
  the wrong direction for a rule (the review's point).
- **The record is not perfect either.** 4 boreholes recorded as recent alluvium are deeper
  than 50 m (96–130 m), above the Pliocene. One is named "forage dans nappe profonde".
  - Alluvium boreholes confirmed by both record and flag are 6–23 m deep; alluvium
    piezometers 9–12 m.
  - These 4 are attributed to the Pliocene ("probable"), with the recorded unit kept as
    a "possible" alternative.
- **The recorded unit is often not under the point.** This happens for 30 % of recorded
  boreholes, with a median distance of 819 m: coordinates and polygons are approximate,
  hence the 1 km tolerance.
- **No recorded borehole is an irrigation borehole** (114 drinking water, 16 industry).
  - "Probable" is therefore given only for the uses where the precision was measured.
  - Irrigation boreholes attributed by the same rules stay "possible".

Coverage of the plain's declared groundwater volume, 2012–2024 (main candidate per
ouvrage):

| Confidence | Ouvrages | Volume (Mm³) | Share of volume | Mostly |
|---|---|---|---|---|
| confident (record) | 124 | 194 | 27 % | drinking water |
| probable (measured rule, same use) | 121 | 321 | 45 % | drinking water |
| possible | 1,338 | 149 | 21 % | irrigation (137 Mm³) |
| unknown | 307 | 48 | 7 % | irrigation, canals |

98 % of the drinking-water volume is confident or probable. By unit (all confidences):
- Pliocene: ≈ 370 Mm³, about half of the plain's groundwater abstraction
- recent alluvium: ≈ 185 Mm³
- ancient alluvium: ≈ 91 Mm³

## Why

- **Data quality.** A value the producer itself marks "incorrect" must not become a
  target. The strict variant shows how much of each conclusion rests on checked data.
- **Folds.** If a nested twin 20 m away is in the training set, a "left-out" well is
  hardly left out. Grouping turns the test into transfer between monitoring sites.
- **Cluster test.** Wells in the same area share weather, pumping and the aquifer, so
  their errors move together. Counting 33 wells as 33 independent votes exaggerates the
  evidence. Flipping signs cluster by cluster keeps that dependence.
- **Attribution.** The pump → unit links are the knowledge every baseline lacked (Gate 2).
  An overconfident link would put wrong edges into the graph and wrong explanations into
  the text. Measuring each rule, use by use, keeps the confidence honest. The model can
  then be run with confident links only, or with all of them.

## What to consider

- **Decision for Assil (CLAUDE.md §3).** Main runs with **confident + probable** pump
  links instead of confident only. Confident only would keep only 27 % of the plain's
  declared volume, while the probable links (drinking water, rule precision 0.92–0.95)
  add 45 %. The sensitivity runs would then be confident only, and all links.
- **The entity of an alluvial pump is uncertain** (63 % right): Têt vs Réart alluvium near
  their junctions. Edges should use the group, plus distance, where the entity is unsure.
- **The re-runs on v4 are still to do:**
  - CPU: `scripts/run_v4_cpu.sh`, after the v3 sweep.
  - GPU: Colab with `final:` and `regimes:` steps.
  - Then the v4 report. The v3 report stays as the record of Step 12a.
- **Independent irrigation evidence for task 12.10:**
  - Agreement with RPG crops does not validate irrigation.
  - Lead (searched 2026-10-23): the SDES publication "L'irrigation des surfaces agricoles:
    évolution entre 2010 et 2020" (agricultural census 2020) has downloadable data,
    including commune-level shares of irrigated vineyards, our main crop.
    https://www.statistiques.developpement-durable.gouv.fr/lirrigation-des-surfaces-agricoles-evolution-entre-2010-et-2020
    "Irrigated" there means watered at least once in the year, "irrigable" means
    equipped: choose the variable accordingly.
  - Other candidates: the ASA perimeters, the BNPE irrigation points.
- **To read (paywalled, via the university):**
  - Chu et al. 2026 (hybrid TFN–LSTM, doi:10.1016/j.jenvman.2026.130474)
  - Jeong et al. 2026 (physically interpretable transfer learning,
    doi:10.1016/j.watres.2026.126321; the review describes 62 wells, not checked yet)
  - Schorpp et al. 2023 (Roussillon model, doi:10.1007/s12665-023-10877-4)

## 2026-10-24: the v4 re-runs start, off the laptop

**What was done.**
- Assil gave the go for the v4 re-runs, with a new rule: no model is trained on the laptop.
  CPU fits go to Kaggle, GPU fits to Colab; the laptop only copies the selections, makes the
  bundles, pulls and scores.
- A probe kernel measured what Kaggle gives an account without phone verification: Python
  3.13, 4 CPUs, 32 GB RAM, no GPU and **no internet** (`pip install` cannot reach PyPI).
  Pastas is not installed, and numpy, pandas and LightGBM are at other versions than ours.
- So the 28 pinned packages that the CPU baselines import are uploaded once as wheels (a
  private Kaggle dataset) and installed offline in the kernel, which stops if any version
  differs from `requirements.txt` (`scripts/kaggle_cpu.py`, `scripts/kaggle_cpu_run.py`).
  A local dry run on a clean Python 3.13, without computing anything, found one missing
  package (`tqdm`, needed by Pastas) before the real push.
- The Kaggle kernel runs naive, LightGBM (5 seeds, regimes), Pastas and WellModel on v4.
- `scripts/v4_from_v3.py` copied the Taccari selection (trial 15, best 3-seed mean 0.582).
- Colab: with `PFE_DATASET=v4`, `colab_run.py` now runs the finals of every neural baseline
  first, then the regimes, then Chronos-2, and it checks the EA-LSTM cuDNN path first.

**Why.**
- Same numbers wherever the code runs: the pinned versions, not Kaggle's, compute every v4
  row. The `naive` rows, recomputed on Kaggle, must equal the laptop's of 2026-10-23.
- Finals first: they make the main v4 table, so a Colab session that stops early still
  leaves the most useful part. `refit` needs the final run anyway (its epoch count).
- Chronos-2 is re-run too: v4 changes 73 well-weeks, all in 2000–2009 (none in the test
  period), and Chronos-2's long context and its fine-tuning see those years.

**What to consider.**
- Kaggle gives no live log through the API; the log and the results arrive when the kernel
  ends (`kaggle_cpu.py status`, then `pull`).
- Free Colab can refuse a GPU or stop a session; everything is resumable from Drive.

## 2026-10-24 evening: Colab out of GPU quota; EA-LSTM and a Pastas check go to Kaggle

**What was done.**
- Colab session 1 (15:10–17:13 UTC) finished the finals of LSTM, distance ST-GNN and
  Taccari, the regimes of LSTM and ST-GNN, and 8 of Taccari's 25 left-out-well runs; all
  are on Drive. It stopped without an error. At 18:40 UTC Colab refused a new GPU "due to
  usage limits", so the cause was the idle timeout or the quota; we cannot tell which.
- The rest is split by what each machine does best:
  - Kaggle CPU (kernel version 3, pushed 18:52 UTC): the Pastas stability check, then
    EA-LSTM's final and regimes.
  - Colab, when the quota is back: Chronos-2 ×3, then the rest of Taccari's regimes.
- **Pastas stability check.** The v4 refit on Kaggle moved the reference's drought median
  NSE from −0.73 to −0.51. Only 4 of its 47 drought-scored wells (6 of the 55 fitted) have
  changed heads, all before 2010 but inside its 2005–2019 calibration (corrected
  2026-10-25: "outside its 2012–2019 calibration" was the v1 window), yet 13 of the 43
  wells with identical heads changed by more than 0.05, and most wells' parameters moved. The check refits every well from 10 starting
  points (start 0 = Pastas' defaults), and once more with training-period heads only.
  `tests/test_pastas_starts.py` checks the drawn starting values without solving a model.

**Why.**
- Pastas is the reference of every significance test. If its own score moves by 0.2
  between two computers, a model "beating Pastas" by 0.2 means little. We need its
  spread, like the seed spread of the neural models.
- By default Pastas starts its constant at the mean of the whole head series, test period
  included. That is not an input, but with a poorly determined optimum the starting point
  can steer the fit. The `--train-obs` runs measure whether it matters.
- EA-LSTM was tuned and run on a CPU for v3 (the laptop), so its v4 runs on Kaggle's CPU
  stay comparable, and they save the scarce GPU hours for Taccari and Chronos-2.

**What to consider.**
- The EA-LSTM steps use the torch of Kaggle's image (it is not among the pinned wheels);
  they run only if `tests/test_ealstm.py` passes there, and the log records the version.
- EA-LSTM on 4 CPUs: about 2 h for the final and about 17 h for the regimes, so one more
  push after this one (each push resumes from the last pulled output).
- The GPU bundle on Drive predates one guard in `colab_run.py` (an empty step list now
  becomes "none"); the next Colab steps (Chronos-2, Taccari) never reach that case.
- What becomes the v4 reference (the record, the best of the starts, or training-only
  heads) is decided with Assil once the spread is known.

## 2026-10-25: third review (Codex) and the quick fixes

**What was done.**
- Codex reviewed the project as a research methodologist (`docs/review_codex_2026-10-24.md`).
  Claude checked its factual claims in the code and the data; all 16 hold. Verdicts and
  status per point: `docs/review_codex_2026-10-24_response.md`.
- **Wrong statements corrected.**
  - Pastas calibrates on **2005–2019**, not 2012–2019 (that was the v1 window). The heads
    that changed between v3 and v4 are therefore inside its calibration. The puzzle stays:
    13 of the 43 drought-scored wells with *identical* heads still moved by more than 0.05.
  - The "best start" was picked with the unweighted noise, but Pastas minimises the noise
    times its weights. The best start is now chosen by the RMSE of the simulated head on
    the training weeks, a rule fixed before any multistart result; new runs also store the
    solver's own objective.
  - The analysis plan called the Phase 4 results "confirmatory". They are
    **pre-specified**, on a drought we already looked at; only weeks observed after the
    freeze are a truly independent check.
  - "Equal edges give equal predictions" was too strong: the export test (12.8) will also
    compare nodes, features, weights and masks, and run the model with fixed weights.
- **Rules written down.** R3 (less data) shortens the head history, not the weather
  history; R2 (left-out wells) reuses settings chosen with all wells ("fixed-configuration
  transfer"); the SGI reference uses every month up to 2019; Chronos-2 fine-tunes on the
  2000–2004 warm-up weeks too; Taccari's memory is 127 weeks, not its 156-week window.
- **Two checks added.**
  - A cached seed is reused only if it was made with the same settings (a fingerprint in
    each seed and in `config.json`); a left-out-wells fold is assembled only with all its
    seeds (`tests/test_run_cache.py`).
  - Two compared models must be scored on the same weeks: `stats.paired()` counts wells
    scored on different numbers of weeks (none in the v3 or v4 tables today) and refuses
    them in strict mode (`tests/test_stats.py`).

**Why.**
- Pastas is the yardstick of every significance test, so how its fits are made and chosen
  must be clean and written down before its results are seen.
- A result reused from a different setting, or a comparison on different weeks, would be
  silently wrong; a check that stops the run costs nothing.
- Calling a result "confirmatory" when its test data shaped the method would not survive
  peer review; saying exactly what was fixed and when does.

**What to consider.**
- **The biggest point is scientific, not technical:** with the approved pump policy, no
  irrigation volume gets an accepted layer (0 confident, 0 probable, 137 Mm³ possible). The
  model's pump links are drinking-water links, so the paper can speak about drinking-water
  pressure, and about farm pumping only through the all-links sensitivity. Assil decides
  the framing (CLAUDE.md, State).
- Still to do before Phase 4: save model weights with a run manifest (none are saved
  today), fix one backbone for arms C–F, and decide how unattributed pumping enters every
  arm.

## 2026-10-25: third review, second pass (every recommendation checked against the code)

**What was done.** Assil asked to check each recommendation of `codex.md` (now
`docs/review_codex_2026-10-24.md`) against the code, judge it, and do the good ones. The first
pass had done the quick fixes; this pass found three recommendations without any answer and
did everything that needs no model training (status per point in
`docs/review_codex_2026-10-24_response.md` §1 and §3).
- **Assil decided (2026-10-24, late evening):** the main story is drinking-water pressure on
  the Pliocene (farm pumping only from the all-links sensitivity); the v4 Pastas reference is
  the fit built from training heads only, decided before its results; arms C–F share one
  backbone, with the review's controls; suspect placeholder values are masked by a rule.
- **A data error.** CORNEILLA PD5, a core Pliocene well, reports a depth of exactly 0.00 m on
  413 consecutive days (Nov 2022 – Jan 2024), qualified "Correcte". Its head is then the
  altitude of its benchmark, 11.77 m, a year above its neighbours. Wells that really flow
  record negative depths; PD5 never does. Rule: a run of ≥ 28 days at depth 0 leaves every
  scored variant from v4 (`src/dataset/placeholders.py`); the v4 report also shows the scores
  without it. Effect on the core drought medians: +0.01 to +0.10 NSE by model, Pastas skill
  −0.05. A note to the producer is in `docs/supervisor_questions.md` §6.
- **Pumping coverage, done properly** (`docs/pump_coverage.md`). The "72 %" of the main pump
  policy is the unit-group figure; at exact-unit resolution it is 61.8 % of the declared
  volume, and 56.2 % of what the model sees once imputed years are counted. Drinking water
  98.0 / 83.7 %; irrigation 0 %.
- **Drought classes** (`docs/results_hydro_<v>.md`). The brief says SGI accuracy is reported,
  but nothing computed it. Now: simulated SGI with the observed reference, IPS class scores,
  confusion matrices, timing and size of the annual minima; hydrographs chosen by a rule.
  On v3 the tuned LSTM and the ensemble detect 72–73 % of low-level drought months with 17 %
  false alarms; Pastas 49 %; climatology 1 %.
- **Reproducibility.** Neural and LightGBM runs now save their fitted models and a manifest
  (`src/models/manifest.py`); Pastas is replayed from its stored parameters to 1e-11 m
  (`tests/test_replay.py`); the weekly pumping is checked layer by layer
  (`tests/test_pumping_conservation.py`); what each regime may use is a table (analysis plan
  §4) with a test (`tests/test_regime_boundaries.py`).
- **Reporting.** Tuning budget (`docs/tuning_budget_v3.md`), cluster-test sensitivity over
  grids and leave-one-cluster-out (`stats.cluster_sensitivity`), the analysis-plan amendments
  (§14), and the abstracts of Chu et al. 2026 and Jeong et al. 2026 (PubMed).

**Why.**
- The PD5 weeks are not a measurement. Leaving them in would score every model against a
  number nobody measured, in the drought the paper is about. Writing the rule *after* seeing
  the test period is allowed only if the result is shown both ways: that is what the
  `all_unmasked` variant is for.
- A coverage figure has to be computed at the resolution the model will use. Graph edges go
  to exact units, where the alluvium rule is only 63 % precise.
- Saving the fitted models is what makes the promised check on new weeks possible: a stored
  prediction cannot be extended into 2027.
- Deciding the Pastas reference before its results are seen protects it from looking chosen.

**What to consider.**
- **The pumping forcing has a small calendar artefact:** flat uses (drinking water, industry)
  get 7/365.25 of the annual volume per week label, so a year with 53 week labels (2006,
  2012, 2017, 2023) carries 1.9 % more of them. Every model sees the same input, so it is
  kept in v4; any annual accounting must use the declared layer (the KG), not weekly sums.
- **Equal trials are not equal capacity:** the Taccari ST-GNN has 230 k parameters, the LSTM
  78 k. Say it next to the results.
- **The cluster test depends on the grid:** LightGBM vs the full-series Pastas has p 0.014
  on the 10 km grid but 0.002–0.125 across the other grids (a 20 km grid has 6 clusters and
  cannot go below p = 0.031). The 10 km grid stays the test of record.
- **Before the freeze:** the v4 neural finals have no saved weights (they ran before this
  change); re-run them with weights if they are to enter the check on new weeks. The
  Colab bundle on Drive is the older code: rebuild it before the next GPU session if the new
  runs should save weights.
- **Next:** pull the Kaggle output (EA-LSTM, Pastas multistart) and run
  `src.analysis.pastas_stability`, which writes the reference run
  `pastas_seasonal_canal_trainobs_beststart`; then the v4 report
  (`docs/results_baselines_v4.md`), `hydro_errors` on v4, and 12.6.

## 2026-10-25 morning: the first v4 results (Kaggle kernel 4 and Colab session 1 pulled)

**What was done.**
- **Kaggle kernel version 4** ran 21:11–08:11 UTC and stopped cleanly at its 11 h budget:
  the Pastas multistart (2 × 10 starts, 38 min), EA-LSTM's final (5 seeds, 2 h 33 min;
  torch 2.11.0+cpu, `tests/test_ealstm.py` passed), and EA-LSTM's left-out-well folds 0–3
  (20 of 25 seed-runs). Pulled and rescored with the mask (`scripts/kaggle_cpu.py pull`; the
  previous output is kept in `results/_kaggle_cpu/output_kernel_v2_backup`).
- **Kernel version 5**, pushed 10:04 UTC with `--steps "regimes:ealstm"`, finishes fold 4,
  R3 50 %, R3 25 % and the refit (about 6 h). It resumes from the pulled output: the folds
  done before run fingerprints existed pass the folder check because the current code gives
  them the same 22 inputs (checked on the laptop, without training).
- **Colab session 1 pulled** from Drive (`pfe_colab/results_gpu/v4` → Download →
  `scripts/colab_pull.py`): finals and regimes of the LSTM and the distance ST-GNN, Taccari's
  final. Taccari's left-out wells (fold 0, fold 1 seeds 0–2) stay on Drive until every fold
  exists. The `*_tuning/best.json` on Drive are identical to the laptop's.
- `src.analysis.pastas_stability` wrote the reference run
  `pastas_seasonal_canal_trainobs_beststart`; `tests/test_replay.py` rebuilds it from its
  parameters to 5e-12 m on three core wells.
- **Ensemble** (rule of 2026-10-20, validation only): Pastas reference + LSTM + distance
  ST-GNN (validation median NSE 0.692; 11 subsets of 4 family winners).
- **Interim v4 report** `docs/results_baselines_v4.md` and `docs/results_hydro_v4.md`
  (Chronos-2 ×3, EA-LSTM's and Taccari's regimes still missing). `baseline_report` now says
  which rows v4 does not re-run by design (the untuned defaults and the tuned LightGBM with its
  own climatology, analysis plan §5), which regimes are still running, and reports the
  reference's spread over its starts with the test of record repeated against each start
  (analysis plan §14.12, added after these results). The v3 report is unchanged (checked:
  only the v4 column of its cross-version table would move, so it was not regenerated).
- **GPU bundle rebuilt** from the current code (`gpu_bundle.zip`, 38.3 MB, md5 97b2cf45…):
  new Colab runs save their weights. Not on Drive yet; it goes up at the start of session 2.

**Results worth remembering** (33 core wells, drought phase; interim and exploratory, §11).
- **The Pastas reference depends on its starting values.** On the same machine, start 0
  reproduces the run of record exactly; over 10 starts, the median drought NSE spans −1.24 to
  −0.51 (full series) and −1.26 to −0.60 (training heads only). Per core well the drought NSE
  moves by a median 1.4 (full) / 1.2 (training heads) between starts, for 31–32 of 33 wells by
  more than 0.1. No well fell back to simplified responses or failed. The frozen rule gives
  −0.80 (full) and **−0.75 (training heads only: the v4 reference)**, worse than the default
  start (−0.51): the best training fit is not the best drought simulation. The v3 → v4 move of
  the full-series fit (−0.73 → −0.51) lies inside this spread, so it says nothing about the
  data change. The solver's objective was not stored by these runs (pushed before it was
  added), so its agreement with the chosen start is not known.
- **Scores (drought NSE / skill):** ensemble 0.14 / 0.51, LSTM 0.12 / 0.57, distance ST-GNN
  0.06 / 0.55, Taccari −0.05 / 0.49, LightGBM −0.08 / 0.49, EA-LSTM −0.16 / 0.37, Pastas
  reference −0.75 / 0.22, climatology −1.49 / 0.
- **Cluster test against the reference (p_holm, drought NSE / skill):** ensemble 0.020 / 0.005;
  distance ST-GNN 0.079 / 0.009; LightGBM 0.079 / 0.070; LSTM 0.164 / 0.295; Taccari 0.164 /
  0.359; EA-LSTM 1 / 0.232. Taccari's v3 pass (drought skill, p_holm 0.013) is not repeated on
  v4.
- **Against each of the 10 training-heads-only starts:** every tuned learning model beats Pastas by
  a large median margin whatever the start (+0.30 to +1.60 NSE), but a single model passes
  the cluster test for only 2–4 starts of 10; the ensemble passes for all 10 (p_holm
  0.010–0.039).
- **Drought classes:** the ensemble detects 75 % of the low months with 18 % false alarms,
  the LSTM 71 / 16 %, the distance ST-GNN 71 / 19 %, the Pastas reference 62 / 27 %, the
  full-series Pastas 50 / 27 %, climatology 1 %. The reference has the lower NSE but the
  better drought classes of the two Pastas fits: NSE and class scores can disagree.
- **Left-out wells (v4 folds keep wells < 2 km apart together):** LightGBM −0.58 (−0.91
  without the mask: PD5 moves from below the median to above it, where two neighbouring
  wells are 0.33 apart), LSTM −0.94, distance ST-GNN −0.98. On v3 the
  graph models lost least (−0.42 / −0.40 against LightGBM −0.75); on the v4 folds they do
  not, so the v3 advantage came from twin wells split across folds. **Less data** costs
  little: 25 % of the training years gives LSTM 0.13, ST-GNN 0.21, LightGBM −0.34.

**Why.**
- The reference is what every significance test is measured against. If its own drought
  score moves by 0.7 with the starting point, a single model "beating Pastas" is partly a
  statement about where Pastas started. Showing the test against every start is the honest
  answer; changing the reference now that we know which start would help would not be.
- The rule was frozen before the multistart ran, and it happens to give a weaker reference
  (−0.75) than the default start (−0.51). That is exactly why it was frozen first: the
  reference must not look chosen, in either direction.
- The interim report is written now so that the numbers exist in a generated file, not only
  in a log; it is regenerated when the last runs arrive.

**What to consider.**
- **Pastas's drought behaviour is not identified by the 2005–2019 heads**: many parameter
  sets fit the training years about equally well and extrapolate differently into the
  drought. For the paper, describe the reference as "the hydrological model, with its
  spread", and lean on the ensemble result and the effect sizes, not on single-model p-values.
- The mask moves LightGBM's left-out-well median by 0.33: amendment §14.1 quoted its effect
  on the main runs only (+0.01 to +0.10). Both versions stay in the report.
- **Still to run:** EA-LSTM's regimes (Kaggle, kernel 5), then Colab session 2 (Chronos-2 ×3
  and Taccari's regimes, about 3.5 T4-hours: Assil clicks the Drive permission). Then pull,
  rebuild the ensemble only if its candidates changed (they are final now), regenerate both
  reports, and update the explainer's scores to v4.
