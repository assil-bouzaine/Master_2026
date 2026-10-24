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
