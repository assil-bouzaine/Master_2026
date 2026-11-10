# Fable review of the SAVE Water / LULC-Water PFE

**Date:** 2026-11-10 · **Reviewer:** Claude (Fable 5.2), acting as an outside researcher ·
**Snapshot:** commit `f874f26`, working tree clean, dataset v4, graph release of 2026-11-06 13:42 UTC.

Nothing in the repository was changed; this file is the only thing written. Where I ran
something, it was read-only, on saved result tables (Appendix A). Numbers marked **[new]** come
from those runs; everything else is quoted from the project's own files.

Earlier reviews (`docs/feedback.md`, `docs/review_2026-10-23.md`, the six Codex reviews) already
cover evidence scope, leakage, fold design, paired support and wording, and their points were
adopted. I do not repeat them. This review looks at what they did not: where the effort is going,
whether the planned experiments can decide anything, what the baseline data say about the main
model before it is built, and what would raise the value of the final result.

---

## 0. The verdict, and the ten actions that matter most

**Verdict.** The data foundation, the evaluation protocol and the knowledge graph are of unusually
high quality for a Master's project. The risk is no longer correctness. It is that the project has
spent its care on the knowledge side while the part the paper is judged on (the main model, the
twin, the explanations) does not exist yet, and that the central real-data contrast (D vs C) is
unlikely to be decidable with 33 wells, 14 clusters and one drought. Both problems can be fixed
in November, at low cost, if the order of work changes now.

| # | Action | Why | Cost |
|---|---|---|---|
| 1 | **Push the repository and back up `results/` and `data/`.** `main` is **109 commits ahead** of `origin/main` (115 commits in total). The whole project since mid-October exists on one laptop whose battery holds 12 %. | One disk failure ends the thesis. | 10 min |
| 2 | **Send the two e-mails** (`docs/supervisor_questions.md` §4–5): the defence date, and monthly drinking-water production. Ready since 2026-10-23 and still on the to-do list of 2026-11-06. | The date sets every deadline; the production series is the only data that can break the pumping–weather confounding (§5.1). | 15 min |
| 3 | **Build the model before finishing the graph.** Start a "ladder" of small models (§6.1) this week; its first three rungs need only tables that already exist, not the export. | Zero lines of the main model, twin or explanation code exist, 26 days before Phase 3 ends. | 1 week for rungs 1–3 |
| 4 | **Design for equifinality.** The Pastas multistart shows that per-well pumping and canal responses are not identified: they fit training equally and diverge by more than 1 NSE in the drought (§4.1). The hybrid has the same structure. | Otherwise the hybrid's "exact contributions" will be exact but arbitrary. | design choice |
| 5 | **Make the twin the main experiment for RQ1–RQ2**, not only the tool for RQ3: a map of *when* the KG graph and the signs help, over many synthetic worlds (§6.3). | Real data give one noisy point; the twin gives as much power as needed and answers the umbrella question's "when". | 1–2 weeks, already planned in part |
| 6 | **Measure the noise floor in every contrast** with an A/A run (the same arm trained twice on different seeds), and use 10 seeds for the primary arms (§3.1). | Seed noise alone moves the median paired ΔNSE by up to 0.12 between two-seed means **[new]**; the effects measured so far (+0.001 to +0.016) are far inside it. | cheap: the graph is tiny |
| 7 | **One primary effect measure** before the tag: the per-well log RMSE ratio. ΔNSE and Δskill have the same sign in 33 of 33 wells **[new]**: they are one test counted twice (§3.3). | Halves the Holm family, removes the −16 … +3 tails. | plan amendment |
| 8 | **Freeze the ontology now** (0.7.x), except what the export needs; add the two cheap things a jury will ask for: INSPIRE alignments (none exist yet) and the OOPS! scan (§7). | The module now defines 81 classes and 197 properties; more review rounds on evidence scope will not change a model result. | 1–2 days |
| 9 | **Unblock SO1 with an external gold standard**: the EuroCrops HCAT mapping of the French RPG codes (§8.1). The AGROVOC gold set has 0 of 198 rows after two weeks. | An expert-made mapping is stronger evidence than one annotator's labels, and it exists today. | 2–3 days |
| 10 | **Start `paper/` now**: study area, data, KG and evaluation sections can be written today, and the comparison table still has about 25 "to complete" cells (§10). | Submission is planned for end of April; writing exposes gaps while they can still be fixed. | 2–3 h a week |

---

## 1. What is strong (keep it)

- **Simulation instead of forecasting.** No observed head is an input, so persistence cannot carry
  the score. This is the right setting for asking whether knowledge is used, and it separates the
  project from Taccari 2024 and both Wu 2025 papers (the positioning matrix says so correctly).
- **The evaluation protocol**: drought/recovery split fixed from observed SGI, skill against
  climatology, KGE'', grouped leave-wells-out folds, exact paired support, cluster-level
  inference, results labelled exploratory when the test period informed them.
- **Honesty about what the data cannot say**: irrigation gets 0 % of the main pump links and the
  story was changed to drinking-water pressure; the land-use test was pre-registered and its null
  result reported; river signs fell from 7 wells to 3 when the evidence scope was corrected.
- **The graph as an auditable artefact**: releases bound by hashes, rule outputs apart from facts,
  59 negative controls, an alignment ledger with forbidden entailments, quotes checked on their
  pages. Few published KG papers do this.
- **The decision record.** Every choice has a date, an owner and a reason.

---

## 2. Where the effort goes, and the schedule

**What exists (lines, from the repository):**

| Part | Code and tests | State |
|---|---|---|
| Knowledge graph, rules, shapes, CQ queries, their tests | about 13,500 lines; `step12_ontology.md` alone is 119 KB | ontology 0.7.0, 469,450 fact triples |
| Baselines, evaluation, statistics, their tests | about 4,700 lines | done on v4 except Chronos-2 and two regime sets |
| **Main model (hybrid), black-box comparison** | **0** | not started |
| **Semi-synthetic twin** | **0** | not started |
| **Explanations** (`src/explain/` does not exist) | **0** | not started |
| HeteroData export | inventory only (`src/kg/inventory.py`) | step 1 of 12.8 |
| Experiment configs (`configs/*.yaml`, rule 10) | none | "to add before Phase 4" |

**What is left in Phase 3 (ends 6 December, 26 days):** the export and its equivalence test; the
AGROVOC gold set (Assil, 0 of 198) and OntoAligner; the satellite rule (needs the Earth Engine
account); text extraction; CQ10 and CQ15 (two of the nine MUST questions, both waiting for inputs
that do not exist); the four remaining SHOULD/COULD contracts (CQ9, 13, 14, 16); OOPS!; the w3id
redirect; Gate 3. Then
Phase 4 has eight weeks, across the winter break, for the hybrid, the black box, arms A–F in
three regimes, three constraint settings, three pumping reconstructions, the twin and the
shortcut tests.

**My reading.** The knowledge side has reached the point of diminishing returns for the paper.
Compare the effort with what finally reaches a model (`inventory_v4_main.json`):

| Relation | Wells with an edge (core) | Eligible sign | Approved constraint |
|---|---|---|---|
| pumping | 43 (24) | 416 edges | 416 |
| recharge proxy, 5 km | 54 (27) | 193 | 0 (pending Gate 3) |
| river | 34 (23) | **3 wells** | 0 |
| canal | 5 (4) | **2 wells** | 0 |
| irrigation pumping | 0 % of the main policy | — | — |

The whole of 2026-11-06 (build in the morning, review response in the afternoon) went into river
and canal evidence that decides the sign eligibility of five wells. That work is correct and it is
a result in itself (§7, point 5), but another round of it cannot move any model score. Eight
reviews in under three weeks have each cost up to a day of response; all of them were about the
knowledge side or the baselines, because nothing else exists to review.

**Recommendations.**
1. Declare the ontology **feature-frozen** at 0.7.x. Allowed changes: what the export (12.8)
   needs, the INSPIRE alignment file, defect fixes. CQ9, 13, 14 and 16 become thesis-only minimal
   fixtures or stated future work; say so at Gate 3 instead of carrying them.
2. Bring the model forward (§6.1). The "two-well executable path" in the resume list is the right
   idea; make it the first thing built, with a deliberately crude export if necessary, and refine
   the export afterwards.
3. Pause further review rounds of the knowledge graph until a model has run end to end. Use the
   next review on the model and the twin.
4. Reduce Gate 3 to three decisions (the ladder and primary contrast, the primary effect measure
   and the twin's role, the scope freeze). About ten open points are listed for Gate 3
   (PE or max(PE, 0), cells under 0.001 of an outcrop, wording or method for canal eligibility,
   …). With five wells concerned, settle them by one default rule: **a sign that is not clearly
   supported stays off**, and move on.

---

## 3. Evaluation and statistics: can the planned contrasts decide anything?

### 3.1 The seed noise floor **[new]**

The cluster sign-flip test takes each arm's 5-seed mean prediction as a fixed quantity. It
measures variation over wells, not over training runs. To see how large training noise is, I
compared a model with itself: the mean of two seeds against the mean of two other seeds of the
same tuned run, scored exactly as a contrast would be (drought NSE, 33 core wells).

| Same model, different seeds | median paired ΔNSE, mean of \|·\| (max) | difference of the two table medians, mean of \|·\| (max) | comparisons with p_cluster < 0.05 |
|---|---|---|---|
| LSTM tuned, 1 seed vs 1 seed | 0.116 (0.207) | 0.184 (0.331) | 0 of 10 |
| LSTM tuned, 2 seeds vs 2 seeds | 0.046 (0.124) | 0.110 (0.319) | 2 of 15 |
| Distance ST-GNN, 2 vs 2 | 0.021 (0.059) | 0.053 (0.122) | 0 of 15 |
| Taccari ST-GNN, 2 vs 2 | 0.040 (0.106) | 0.060 (0.144) | 1 of 15 |

If seeds are independent, a 5-vs-5 comparison has about 0.63 of the 2-vs-2 noise: a typical
median paired ΔNSE of about **0.03 (LSTM), 0.013 (ST-GNN), 0.025 (Taccari)**, and up to about
0.08 in a bad draw. (This scaling is my extrapolation; the 2-vs-2 comparisons share seeds, so the
15 are not independent.)

What follows:
- The land-use effects (+0.016 and +0.001) and the machine effect (−0.032) are all inside the
  seed noise. "No detectable improvement" is the correct wording; the data could not have shown a
  small effect either way.
- The ranking of the neural baselines in the main table (LSTM 0.12, distance ST-GNN 0.06,
  Taccari −0.05) is within what seed sets alone produce for the difference of medians (up to 0.3
  with two seeds per side). The paper should not rank them.
- Three of 45 A/A comparisons reach p < 0.05. That is close to the nominal rate, so the test is
  not broken, but a single p < 0.05 for D vs C would not distinguish an edge effect from a seed
  draw.

**Recommendations.**
1. **A/A control in every primary contrast:** train arm C twice (10 seeds, two disjoint 5-seed
   means) and report its contrast beside D vs C. Better: with 10 seeds per arm, build the null
   band from many random 5-vs-5 splits inside each arm; D vs C is credible only outside it.
2. **10 seeds for C and D** in the primary contrast. The graph has 65–250 nodes; this is minutes
   of T4 time.
3. Keep "one machine type per contrast" (already proposed for Gate 3). The −0.032 machine effect
   is the same phenomenon.
4. Cite Bouthillier et al. 2021 (arXiv:2103.03098) for the practice of accounting for seed and
   data-split variance in benchmark comparisons.

### 3.2 Minimum detectable effect **[new]**

I took real vectors of per-well paired differences, centred them, added a uniform shift δ and
searched for the smallest δ that the test of record would call a difference (p_cluster below the
threshold and the bootstrap interval above 0). A uniform shift is the most favourable shape an
effect can have, so these are lower bounds.

| Per-well dispersion taken from | ΔNSE: p < 0.05 / p < 0.0125 | Δskill | −log RMSE ratio |
|---|---|---|---|
| LSTM with vs without one feature (5-seed means) | 0.05 / 0.07 | 0.03 / 0.05 | 0.03 / 0.06 |
| LightGBM with vs without one feature | 0.11 / 0.24 | 0.10 / 0.11 | 0.07 / 0.08 |
| Distance ST-GNN vs Taccari ST-GNN | 0.25 / 0.48 | 0.09 / 0.10 | 0.18 / 0.20 |
| Distance ST-GNN vs LSTM | 0.04 / 0.05 | 0.04 / 0.05 | 0.05 / 0.06 |

(p < 0.0125 is the Holm threshold for the smallest of four p-values, the family proposed in the
analysis plan §10.)

**Reading.** For two arms that share a backbone, the design can detect a median gain of about
0.05–0.10 NSE at best, which is the size of the seed noise of §3.1. If D and C behave as
differently as two graph models do today, the detectable gain is 0.25–0.5 NSE. A gain that large
from changing edges alone would be surprising: Kirschstein & Sun (arXiv:2405.19836) found none,
and in D the edges with approved signs are the pumping edges only.

**So the most likely real-data outcome of D vs C is "not significant with 14 clusters", with an
interval too wide to claim equivalence.** That is the least useful result a paper can have, and
the plan should be built so that it is not the headline (§6.3, §10).

**Recommendations.**
1. Put this table (recomputed on the final arms' A/A runs) in the analysis plan before the tag,
   as the stated sensitivity of the design. A reviewer will respect a design that says what it
   can detect.
2. Fix a **smallest effect of interest** before the runs, for example a 5 % median RMSE reduction
   (log ratio 0.05), and report each contrast as "detected", "compatible with no effect larger
   than X" (upper end of the interval) or "undecided". Lakens 2017
   (doi:10.1177/1948550617697177) is the standard reference for this reasoning; the analysis plan
   §14 item 15 already asks for a margin fixed in advance.
3. Report the 56 wells scored in the drought (not only the 33 core) as a secondary row: more
   clusters, at the price of shorter records.

### 3.3 One primary effect measure **[new]**

On the same weeks, ΔNSE = (MSE_b − MSE_a) / Var(obs) and Δskill = (MSE_b − MSE_a) /
MSE(climatology). The numerator is the same; only the per-well scaling differs. In the LSTM vs
ST-GNN contrast the two differences have the same sign in 33 of 33 wells (Spearman 0.88). The
"primary" and "co-primary" endpoints are therefore one question asked twice, and Holm over four
tests (two contrasts × two metrics) pays for two tests that carry no new information.

The NSE scaling also gives a few wells extreme weight: per-well ΔNSE between two neural models
ranges from −2.94 to +2.76, because a well with little variance in the drought divides by a small
number (the one "other" well scores −16 for the reference). The log RMSE ratio of the same
contrast ranges from −0.50 to +0.41, is symmetric, and reads directly as a percentage.

**Recommendation.** Before the tag, make the primary effect measure of every Phase 4 contrast the
**per-well log(RMSE_a / RMSE_b)** in the drought phase (median, cluster interval, cluster
sign-flip test). Keep median NSE and skill in every table as descriptions of each model. The Holm
family of RQ1 becomes two tests instead of four. This is an amendment of a kind the plan allows
(no Phase 4 result exists), and it should be dated as such.

### 3.4 Smaller points

- The percentile bootstrap of a median over 14 clusters of sizes 5, 4, 4, 4, 3, 2, 2, 2, 2, 1,
  1, 1, 1, 1 is approximate; say so once. The sign-flip test is the solid part.
- The trough and annual-minimum errors (`docs/results_hydro_v4.md`) deserve a pre-specified
  place in Phase 4. Today the Pastas reference has the *best* annual-minimum error (−0.02 m) and
  trough error (0.08 m) of all models while having the worst NSE; the networks stay 0.06–0.12 m
  too high at the annual minimum. A superposition model can go below what it has seen; the
  networks tend not to. That is the hybrid's most plausible advantage, and a drought-depth
  endpoint is where it would show. (Check it across the ten starts first: with the instability
  of §4.1 it may be partly luck.)

---

## 4. Baselines

### 4.1 Why the Pastas reference is unstable, and what it predicts for the hybrid **[new]**

The v4 report shows that a core well's drought NSE moves by a median 1.2 between starting
values. I looked at where the instability sits (10 training-heads-only starts, 33 core wells):

| Parameter | Spread across starts, per well: (max − min) / \|median\|, median over wells | Range of fitted values |
|---|---|---|
| recharge: gain A, shape n, scale a, evaporation factor f | 0.25, 0.06, 0.35, 0.46 | sensible |
| **pumping: gain A, scale a, shape b** | **1.16, 10.85, 5.02** | a up to 10,000 days (its bound), b from 1e-6 to 25 |
| **canal: gain A, scale a** | **1.25, 1.46** | a up to 10,000 days (its bound) |
| constant | 0.09 | |
| noise α | 0.36 | up to 4,999 (its bound) |

- The recharge response is identified. The **pumping and canal responses are not**: the same well
  gets pumping time scales that differ tenfold between starts, often at the 27-year bound.
- Across starts, a well's training NSE varies by a median **0.097**, its drought NSE by 1.17.
  Within a well, the rank correlation between training NSE and drought NSE across starts is
  **0.19**, and between validation NSE and drought NSE **0.13**. Fit quality in-sample says
  almost nothing about behaviour in the drought.
- The best start per well by hindsight still gives only −0.23.

**Why.** The pumping input is 100 % imputed (a constant backfill) for 2005–2011, so the 2005–2019
calibration sees eight years of real annual totals, and inside a year the weekly shape follows
the climatic deficit by construction. A three-parameter response plus a gain per well cannot be
identified from eight annual numbers. A response with a time scale of many years then behaves as
a free slow trend: it costs nothing in training and decides the level in 2022–2025. This is
equifinality in the classical sense (Beven 2006, doi:10.1016/j.jhydrol.2005.07.007). It also
matches the earlier diagnosis in `docs/feedback.md` §2.3 that the remaining error is a slowly
growing offset.

**Consequences.**
1. *For the reference.* It is weaker and more arbitrary than a hydrologist would accept, and a
   reviewer can say the comparison flatters the networks. Three inexpensive sensitivity rows
   would protect the paper (Pastas variants are "hypothesis tests", so this does not break the
   no-new-baseline rule):
   - a **recharge-only** Pastas (the part that is identified) as the transparent floor;
   - pumping and canal time scales **capped** at a physically argued value (the response of a
     piezometer to a well a few kilometres away is not 27 years; take the bound from Schorpp et
     al. 2023 or the Dall'Alba thesis, both still unread);
   - the start chosen by **validation** NSE, the same information the networks' early stopping
     uses. I computed it: drought median **−0.51** instead of −0.75. I did this after seeing the
     test results, so it can only be shown as a post-hoc sensitivity, never replace the frozen
     rule.
   Zaadnoordijk et al. 2018 (doi:10.1111/gwat.12819) describe acceptance checks for automated
   transfer-function models at national scale; one sentence on which checks the reference passes
   would help.
2. *For the hybrid, and this is the important one.* The main model is "a differentiable,
   Pastas-like superposition". With per-well response parameters it will inherit exactly this
   non-identifiability: accurate heads, contributions that change with the seed. The plan's seed
   disagreement test (RQ3, test 2) will detect it; the design should prevent it:
   - share parameters across wells (partial pooling by unit, §6.1), which is the real argument
     for a model that learns all wells at once;
   - bound kernel time scales and state the bounds with their source;
   - give pumping a structure that matches what the data contain (§6.2);
   - report, for every contribution, its spread over seeds next to its value, and make "share of
     wells whose pumping contribution keeps its size across seeds" a headline number of RQ3.
3. *As a finding.* "In-sample fit does not predict drought skill; per-well pumping responses are
   not identifiable from annual declarations" is a clean, quantified statement that motivates
   the whole paper. Use it in the introduction instead of only "ML beats Pastas".

### 4.2 The other baselines

- **Static inputs act as identifiers.** The LSTM, EA-LSTM and ST-GNNs receive x, y, altitude,
  depth and artesian share, a unique combination per well. On left-out wells they collapse (LSTM
  0.12 → −0.94, ST-GNN 0.06 → −0.98), which is consistent with what Heudorfer et al. 2024
  describe, though not proof of it. The random-ID
  control is planned for Phase 4; running it now on the tuned LSTM (statics replaced by random
  numbers, and statics removed) is one Kaggle job and tells in advance whether arm B (knowledge
  as features) has any room to help. It is a diagnostic of an existing baseline, not a new one.
- **Memory.** The tuned look-backs are 104 weeks (LSTM), 156 (both graph models) and 208
  (EA-LSTM), and LightGBM's longest window is 104 weeks. The diagnosis of `feedback.md` §2.3
  (cause 2: storage depletion longer than the look-back) was only tested through these choices.
  SAFRAN starts in 1958, so three- to five-year accumulated effective rainfall or deficit costs
  nothing to compute. For Phase 4 this is a design requirement rather than a baseline change:
  the hybrid's recharge kernel needs a warm-up longer than its longest time scale (extend the
  forcing warm-up from 2000 to 1990). Chidepudi et al. 2023 (doi:10.1016/j.scitotenv.2022.161035)
  and Baulon et al. 2022 (doi:10.5194/hess-26-2829-2022) show for French aquifers that
  multi-annual variability is the hard part of head simulation; both belong in the related work.
- **Ensemble means against single fits.** The network rows are 5-seed means (LSTM 0.12; single
  seeds −0.05 ± 0.14), Pastas is one fit. Already disclosed in the table; say in the text that
  part of the gap to Pastas is the averaging.
- **Chronos-2.** It is a forecasting reference with past heads; the paper is about simulation.
  `chronos2_ft` on v4 is still not run and the session-2 results are still on Drive. Suggestion:
  keep the forecast task for the thesis, give it one supplementary table in the paper, and stop
  spending GPU sessions on it.
- **Pending runs.** The Taccari regimes and the v4 Chronos rows leave the baseline report
  "interim" three weeks after it started. Pull what exists, regenerate the two reports once, and
  close Phase 2 formally, or drop the missing rows with a sentence.

---

## 5. Data

1. **Pumping is the weak input, and only new data fix it.** Share of the weekly pumping volume
   that is imputed, by year (`pumping_weekly.parquet`, v4) **[new]**: 2005–2011 **100 %**,
   2012–2022 0–2 %, 2023–2024 8 %, 2025–2026 **100 %**. So the model learns the effect of pumping
   from eight annual totals, and the last year of the drought phase and the whole recovery have
   no real pumping at all. Three reconstructions test robustness to the *within-year* shape; no
   reconstruction can add between-year information.
   - The request for monthly drinking-water production (e-mail §5) is the most valuable action
     open in the project. Even one operator and five years would let the twin be calibrated on
     real within-year timing and would give RQ2 one honest identification case.
   - Check BNPE for the 2025 declarations before the results freeze (the 2024 ones were
     available by the pull of 2026-10-20).
2. **The test is one event.** All conclusions are about one network in one drought (the plan says
   so). A second check may exist inside the training period: if the SGI shows a marked dry spell
   in 2005–2008 (the Catalan drought of 2007–2008 suggests it; I did not check the series), a
   time-reversed split (train 2009–2021, score 2005–2008) for the final C and D only would give
   a second drought, with the caveat that pumping is backfilled there. Optional; decide at
   Gate 3, before any Phase 4 result.
3. **Recovery phase:** 7 core wells have strictly validated weeks. Keep it out of every claim, as
   planned, and do not spend analysis on it until ADES validates 2025–2026.
4. **CORNEILLA PD5:** the note to SMNPR (§6 of the questions file) is also unsent. It is two
   minutes, and a producer's answer turns a post-hoc mask into a documented correction.

---

## 6. The main model and the Phase 4 design

### 6.1 Build a ladder, not one model

The plan compares the hybrid with a black box and runs arms A–F on the hybrid. If the hybrid
then matches or misses the LSTM, nobody can say which ingredient did it: differentiable training,
sign constraints, parameter sharing, KG features, KG routing, or message passing. A ladder in
which each rung adds one ingredient answers that, and its first rungs can run this week:

| Rung | Model | Adds | Needs |
|---|---|---|---|
| 0 | Pastas per well (exists) | — | — |
| 1 | The same superposition in PyTorch: per-well free parameters, sign-constrained gains, all wells trained together, several starts | differentiable training; does it remove the start dependence? | the panel only |
| 2 | Rung 1 with **partial pooling**: each parameter = its unit-group mean + a shrunk well deviation | sharing by hydrogeological unit, the simplest use of the KG | group labels |
| 3 | Parameters predicted from static and KG features, no message passing (= the plan's control 1) | knowledge as features (arm B) | feature table |
| 4 | Stresses **routed** by KG edges against routed by distance, on rung 2 or 3 | routing: which pumps, cells and gauges feed which well | the export |
| 5 | Message passing over well links (the full hybrid) | graph learning | the export |
| each | with and without the bounded residual | what the linear part misses | — |

Why this is better than the current plan:
- **Rungs 1–2 are the test of §4.1.** If joint training with pooling gives stable contributions
  and a better drought score than Pastas, that is already a result. If it does not, the hybrid
  needs rethinking in November, not in January.
- **The cleanest D vs C is at rung 4, without a GNN.** Routing changes which inputs reach a well;
  that is the part of the graph with a hydrogeological meaning and approved signs. Message
  passing over 47 well links in a model with no head inputs can only smooth parameters between
  neighbours. Making routing the primary contrast and message passing a secondary one removes
  moving parts and noise from the test that §3.2 shows is already short of power.
- **Partial pooling is the statistician's baseline for "sharing knowledge".** A GNN that maps the
  static features of 65 wells to response parameters has 65 training examples of that mapping.
  A hierarchical model with one mean per unit does the same job with a handful of parameters.
  If rung 2 equals rung 5, the honest conclusion is that the *grouping* carries the gain, and
  the paper is simpler and more convincing for it.
- The nearest family in the literature is differentiable, regionalised process models (Tsai et
  al. 2021, already listed; Feng et al. 2022, doi:10.1029/2022WR032404). Position the hybrid
  there, and MC-LSTM (Hoedt et al. 2021, arXiv:2101.05186) as the hydrology precedent for a
  physical property enforced by construction.

Training stays off the laptop (Kaggle CPU is enough for rungs 1–3).

### 6.2 Give pumping the structure the data support

The weekly pumping series is an annual total multiplied by a shape copied from the weather. The
model is then asked to separate two inputs that are the same curve within a year, and the
project handles this by restricting claims and grouping "summer demand". The model itself can
embody that restriction:

- **between-year pumping:** the facility's annual total as a smooth annual-resolution series
  (anomaly from its training mean), through a slow kernel, with the "abstraction lowers the head"
  sign. Only between-year and between-well variation can move it, which is exactly the variation
  the plan allows claims on;
- **within-year demand:** one "summer demand" response driven by the climatic deficit, scaled by
  the well's connected annual volume. No sign claim about pumping timing is made from it.

The three reconstructions remain as sensitivity. The gain is that the pumping contribution is
identified by construction from the only information that exists, instead of being identified
only in the text. To decide at Gate 3; it refines, and does not replace, the approved design.

### 6.3 Make the twin the main experimental engine

Today the twin serves RQ3 (can the tests detect wrong reasons?). It can do more, and it is the
only place where the project has statistical power:

- Generate many synthetic worlds on the real wells, forcings and graph, varying three dials:
  **(a)** how strong the between-year pumping signal is relative to noise, **(b)** the share of
  pump links that are wrong in the graph given to the learner, **(c)** how much of the pumping
  is unattributed.
- In each world run C and D (and constraints off/soft/hard). Plot the gain of D over C, and of
  the constraints, over the dials: a **knowledge-value map**. With 50–100 worlds per cell the
  intervals are narrow.
- Place the real data on the map: 62 % of volume attributed at exact-unit resolution, the
  measured rule precisions (36/39, 0.63 at entity level for the alluvial flag), eight informative
  years. The paper can then say "*in conditions like Roussillon's, a KG graph is expected to
  change the drought RMSE by x %, and to matter only if pumping information improves beyond y*".

That statement answers the umbrella question (*when* does explicit knowledge help under uncertain
pumping information) whatever the single real-data contrast shows, and it turns a probable null
into a result with an explanation. Shapoori et al. 2015 (doi:10.1007/s10040-015-1269-7) is a
direct precedent to read and cite: a synthetic study of decomposing heads into meteorological and
pumping components with transfer-function models.

Keep what the plan already requires (a truth graph separate from the learner's graph, generator
families the model does not contain, several noise levels). Add one rule: the twin's dials and
grid are written into the analysis plan before any real-data arm is scored.

### 6.4 Other design points

- **Recharge proxy.** With the monotone constraint pending, choose between PE and DRAINC by
  validation fit on the outcrop wells and declare it; do not carry both through Phase 4.
- **The residual.** Report its share of drought variance (planned). Add a rule fixed in advance:
  if the residual carries more than a stated share, the "exact contributions" claim is weakened
  for that well and the explanation template must say so.
- **Arms and regimes.** A–F × three regimes × three constraint settings × three reconstructions ×
  5–10 seeds is several hundred trainings. Write the run matrix now and mark the cells that are
  primary (C, D, A/A, in R1), secondary (R2 nested, constraints) and optional. Otherwise January
  is spent launching runs.

---

## 7. Ontology and knowledge graph

1. **Size against the stated design.** CLAUDE.md §3 says the bridging module "holds only what the
   reused vocabularies lack". `lulcw.ttl` now defines **81 classes, 101 object properties, 96
   datatype properties and 22 concept schemes** **[new count]**, in one file. A reviewer of an
   ontology paper will ask for the reuse ratio and for the justification of each new term.
   - Run a **term-usage audit**: for each `lulcw:` term, is it used by a CQ query, a rule, a
     shape or the builder? Terms used by none are candidates for removal; the table "CQ → terms
     it needs" is also the traceability evidence the methodology asks for.
   - Present the module as **sub-modules** (core and attribution, evidence and provenance, land
     use, forcing, rivers and canals, export policy), each with its own IRI and version. That is
     what the WHOW-KG pattern the thesis claims actually looks like.
   - Name the engineering methodology. The work already follows requirements → implementation →
     evaluation with CQs; LOT (Poveda-Villalón et al. 2022, doi:10.1016/j.engappai.2022.104755)
     is the framework to cite for it.
2. **INSPIRE is missing.** The subject names SWEET, INSPIRE and AgroPortal. A search of
   `ontology/` and `src/kg/` finds no INSPIRE or HILUCS term. The INSPIRE feature-concept
   register has resolvable concepts for exactly the project's classes; these resolved on
   2026-11-10 (a made-up name returns 404): `featureconcept/Aquifer`, `AquiferSystem`,
   `Aquitard`, `HydrogeologicalUnit`, `GroundWaterBody`, `ActiveWell` under
   `https://inspire.ec.europa.eu/`, and the HILUCS value
   `codelist/HILUCSValue/1_1_1_CommercialAgriculturalProduction`. One alignment file with
   `skos:closeMatch` links, plus ledger rows, closes a visible gap in SO1 in half a day. Compare
   definitions before choosing the relation, as the ledger requires.
3. **Gates still open:** OOPS! has never been run; the w3id redirect has not been requested (the
   pull request needs Assil's GitHub account and takes days to be merged, so start it now); the
   SAWGraph licence question is unanswered since 2026-10-23 (one e-mail to its authors).
4. **Show what the ontology is worth.** The plan credits the ontology with traceability,
   consistency and reuse, not accuracy, and the equivalence test will show that plain tables give
   the same edges. Then those three qualities need evidence of their own:
   - *consistency:* a table of real defects the semantic layer caught (the spring typed as a
     drilled well, body-level evidence promoted to a unit, the off-map "completed" search, the
     double-counted class areas). They are scattered in the notes; collected, they are a result;
   - *traceability:* for one explanation, the full chain from sentence to source page;
   - *reuse:* in the Manouba transfer (or the "recipe" chapter), count the terms, rules and
     shapes reused unchanged against those that had to change.
5. **The evidence funnel is a figure.** Declared knowledge → attributed → edge → eligible sign →
   approved constraint, by mechanism (the table in §2). It is the most original output of
   Phase 3 and belongs in the paper's main text.
6. **Documentation and release.** Generate HTML documentation of the ontology (WIDOCO or pyLODE),
   and deposit ontology and graph on Zenodo with the paper. KnowWhereGraph (Janowicz et al. 2022,
   doi:10.1002/aaai.12043) is the reference geo-knowledge-graph to position against, besides
   WHOW-KG and SAWGraph.

---

## 8. The subject's other objectives

### 8.1 Alignment experiment (SO1)

- **The gold set is the bottleneck**, and a single annotator who is not an agronomist is its weak
  point (the protocol's 30-code second annotation helps only a little).
- **Use EuroCrops.** Schneider et al. 2023 (doi:10.1038/s41597-023-02517-0) harmonised national
  crop declarations across the EU, the French RPG included, into one taxonomy (HCAT) with
  published mapping tables. That gives a second alignment task, RPG code → HCAT, whose gold
  standard was made by others. Matchers can be scored on it immediately, and the HCAT names (in
  English, with botanical structure) make the AGROVOC gold set faster and more consistent to
  write. Check first that the French table covers the 198 codes and note its RPG year.
- **Guard against anchoring.** The gold template is filled from candidates produced by a lexical
  matcher. Labels chosen from a lexical matcher's shortlist favour lexical matchers. For the
  30-code blind subset, have the annotator search AGROVOC freely before seeing candidates, and
  report how often the free choice was outside the shortlist.
- **Weight by area.** Many of the 198 national codes hardly occur in the Pyrénées-Orientales.
  Report scores unweighted and weighted by local area.
- The two small gold sets (BD LISA types, BNPE uses) have a few dozen terms: present them as
  reviewed alignments in the ledger, not as experiments with P/R/F1.

### 8.2 Satellite rule (SO2)

- **Absolute summer NDVI will mostly rediscover the crop type.** Orchards and vines are green in
  summer whether irrigated or not. Use a **within-class anomaly**: a parcel's summer index
  relative to parcels of the same crop class in the same weather cell. Add a moisture-sensitive
  index (NDMI, from the SWIR band) beside NDVI.
- **An independent check exists in the data: 2023.** Canal intakes fell to 0.54 of their 2022
  volume under the surface-water orders. Parcels whose summer greenness dropped in 2023 relative
  to same-class parcels outside canal reach are, plausibly, the irrigated ones. A
  difference-in-differences on 2022–2023 is a validation that needs no labels. Use it to
  *validate* the rule only, never to *define* the concept: 2023 is in the test period, and a
  concept built from it would carry test-period and restriction information into arm B.
- Radar-based irrigation mapping in a neighbouring region (Bazzi et al. 2019,
  doi:10.3390/rs11151836, Catalonia, Sentinel-1) is the state of the art to cite and the reason
  to call an NDVI rule a heuristic.
- **Expectation.** LU-4 found no detectable gain from the demand index; one more land-use feature
  will very probably show none either. The rule's role is to cover SO2 and to demonstrate
  observation → concept → graph. Time-box it to one week. The Earth Engine registration is
  Assil's and can take days: do it now.

### 8.3 Text extraction (12.11)

The planned version (10–20 papers, Mediterranean concepts, precision) is disconnected from the
rest. A better version is already half built: `configs/exchange_evidence.csv` holds 32
hand-curated statements (river section, unit or aggregate, direction, period, method) with their
quotes and pages. That is a **gold set for extraction**. Task: a local LLM extracts such
statements from the same BRGM and SDAGE documents; score precision and recall against the 32, and
record the errors that matter (an aggregate read as a unit, a missing date). It measures what the
subject asks, feeds the graph, and reuses two days of careful work.

### 8.4 Explanations (RQ4, Phase 5)

- Add a **randomisation sanity check** (Adebayo et al. 2018, arXiv:1810.03292): the explanation
  of a model with shuffled weights, or of the rewired arm E, must differ from the real one. A
  template that produces the same fluent sentence for both is not explaining the model.
- Ask one hydrogeologist (SMNPR or BRGM, the contacts already sought for the two-well review) to
  rate ten explanations for plausibility. Small, and it is the kind of evidence *Environmental
  Modelling & Software* values.

---

## 9. Literature and state of the art

1. **The comparison table is behind.** About 25 cells are "to complete" and several core papers
   are known from abstracts only (Chu 2026, Jeong 2026, Schorpp 2023; Marconato 2023's method
   cell is empty although RQ3 rests on it). The roadmap's "2–3 papers a week" has not happened
   since the table was started. Schorpp et al. 2023 and the Dall'Alba thesis are the priority:
   they hold the time scales and recharge shares that §4.1 and §6 need.
2. **Missing references, all checked at Crossref or arXiv on 2026-11-10** (title and authors
   confirmed; read each before citing its content):

   | Reference | Why it is needed |
   |---|---|
   | Caballero & Ladouche 2015, *HESS Discussions*, doi:10.5194/hessd-12-10109-2015, "Impact of climate change on groundwater in a confined Mediterranean aquifer" | By the BRGM authors of the Dem'Eaux reports the graph already cites; from its title, a modelling study of a confined Mediterranean aquifer. Check whether it is the Roussillon Pliocene and, if so, it is the closest prior head model of our system. A discussion paper: cite as such. |
   | von Rueden et al. 2021, *IEEE TKDE*, doi:10.1109/TKDE.2021.3079836 | The taxonomy of informed machine learning: knowledge source, representation (knowledge graphs are one) and where it enters the pipeline. The cleanest way to position "graph + constraints + explanations from a KG". |
   | Karpatne et al. 2017, *IEEE TKDE*, doi:10.1109/TKDE.2017.2720168 | Theory-guided data science; the origin of the knowledge-guided line in the geosciences. |
   | Nearing et al. 2021, *WRR*, doi:10.1029/2020WR028091 | The role of hydrological knowledge when ML is strong; frames RQ1 honestly. |
   | Feng et al. 2022, *WRR*, doi:10.1029/2022WR032404 | Differentiable regionalised process models: the family the hybrid belongs to. |
   | Hoedt et al. 2021, arXiv:2101.05186 | A physical property enforced by construction in a hydrological network. |
   | Wunsch et al. 2022, *Nat. Commun.*, doi:10.1038/s41467-022-28770-2 | Head simulation from meteorological inputs only, at scale. |
   | Chidepudi et al. 2023, *STOTEN*, doi:10.1016/j.scitotenv.2022.161035; Baulon et al. 2022, *HESS*, doi:10.5194/hess-26-2829-2022 | Multi-annual variability in French groundwater levels and how deep models handle it. |
   | Shapoori et al. 2015, *Hydrogeology J.*, doi:10.1007/s10040-015-1269-7 | Synthetic test of separating pumping from climate in heads: precedent for the twin. |
   | Beven 2006, *J. Hydrol.*, doi:10.1016/j.jhydrol.2005.07.007 | Equifinality: the name of what §4.1 measures. |
   | Zaadnoordijk et al. 2018, *Groundwater*, doi:10.1111/gwat.12819 | Acceptance checks for automated transfer-function models. |
   | Bouthillier et al. 2021, arXiv:2103.03098; Lakens 2017, doi:10.1177/1948550617697177 | Variance in ML comparisons; smallest effect of interest and equivalence. |
   | Schneider et al. 2023, *Sci. Data*, doi:10.1038/s41597-023-02517-0; Bazzi et al. 2019, *Remote Sens.*, doi:10.3390/rs11151836 | EuroCrops (SO1); irrigation mapping (SO2). |
   | Poveda-Villalón et al. 2022, doi:10.1016/j.engappai.2022.104755; Janowicz et al. 2022, doi:10.1002/aaai.12043; Adebayo et al. 2018, arXiv:1810.03292 | Ontology methodology; reference geo-KG; sanity checks for explanations. |

3. **Not re-checked by me.** The 2026 entries of the reading list (Chu, Jeong, Holmberg
   arXiv:2609.21381) are newer than my training data. The list says they were verified on
   2026-10-23/25; I did not repeat that.
4. **The novelty claim, stated carefully.** What is new is not "a graph helps" (unproven, and
   contested) nor "explanations checked against independent information" (Jeong 2026). It is the
   combination: constraints and routing derived from an evidence-qualified KG, with a test of
   when they help and an audit of how much declared knowledge survives. Write the introduction
   around that.

---

## 10. The paper and the final result

1. **Change the one-sentence claim.** The roadmap says the model "simulates … at least as well as
   strong hydrological and deep-learning baselines". Nothing guarantees that: a linear
   superposition may lose to the LSTM on NSE. Write the claim as a question with pre-stated
   outcomes, and decide now what the paper says in each case:

   | Outcome | What the paper leads with |
   |---|---|
   | D better than C beyond the A/A band | Routing by evidence-qualified knowledge helps; the twin map shows where |
   | No detectable difference (most likely) | The twin map: in conditions like Roussillon's the expected gain is below x %; the evidence funnel shows why (little knowledge survives); constraints and explanations are judged on plausibility and stability, not accuracy |
   | Hybrid below the LSTM on RMSE | The price of interpretability, measured; the drought-depth endpoint and seed stability as the compensating evidence |

2. **Results the paper can already count on**, whatever Phase 4 gives: the equifinality result
   (§4.1), the evidence funnel (§7), the pre-registered land-use null, the left-out-wells collapse
   of the networks, the noise-floor analysis (§3.1). Together they are an honest account of what
   uncertain knowledge can and cannot do for groundwater simulation, which is the umbrella
   question.
3. **Venue.** *Environmental Modelling & Software* fits and values reusable software: plan the
   package (one command from raw tables to the graph to the tensors) as a deliverable. The KG by
   itself could later make a short resource paper; not before the thesis.
4. **Write now.** Create `paper/` with the journal template, the figure list (study area and
   stack; evidence funnel; ladder results; knowledge-value map; drought hydrographs with
   contributions; seed stability of contributions; one explanation with its chain) and draft
   study area, data, KG and evaluation. These sections do not depend on Phase 4.

---

## 11. Engineering and project hygiene

1. **Backups (action 1).** Besides pushing: `results/` (1.7 GB) and `data/` (4 GB) are
   git-ignored and live only on the laptop, apart from what happens to remain on Kaggle and
   Drive. A weekly copy of `results/`, `data/processed/` and `data/interim/` to Drive is enough.
2. **`PFE_DATASET` defaults to v2.** Every command must set it, and a forgotten variable silently
   scores another dataset. Make the code refuse to run without it (or default to v4) before
   Phase 4.
3. **Configs and environment.** Rule 10 says every run comes from a config file; `configs/` has
   no experiment YAML yet. Three environments are in play (laptop Python 3.12, Kaggle 3.13
   wheels, Colab's own torch) and the measured machine effect is as large as the effects tested.
   Write the Phase 4 run matrix as config files and pin one environment per contrast.
4. **One command for all gates.** The suites are run one by one (`python -m tests.test_…`). A
   single script that runs every gate and writes the outcome into the release record would make
   "the gates pass" checkable.
5. **CLAUDE.md is carrying the project history.** Section 7 is several hundred lines of dated
   state. Move the history to the notes and keep "Resume here" to one screen; long state files
   drift and contradict themselves (the status table still says the baseline re-runs "wait for
   Colab session 2", which ended on 2026-10-26).

---

## 12. Proposed order of work (to 6 December)

| Week | Assil | Claude |
|---|---|---|
| 10–16 Nov | push and back up; send the three e-mails; register for Earth Engine; request the w3id redirect; pull the Drive results | rungs 1–2 of the ladder on Kaggle CPU; a crude export for two wells; analysis-plan amendments (§3) drafted for approval |
| 17–23 Nov | review the amendments; label 40 development codes with EuroCrops' help | the export proper with its equivalence test; rung 3; the small twin with its dials; INSPIRE alignment, OOPS!, term-usage audit |
| 24–30 Nov | finish the gold set (evaluation codes); Gate 3 material to the supervisor | rung 4 (routing C vs D) on the twin first; OntoAligner on both gold sets; `paper/` skeleton and the data, KG and evaluation drafts |
| 1–6 Dec | Gate 3: ladder, primary measure and twin, scope freeze; tag the plan | satellite rule (one week, time-boxed) or text extraction against the 32 statements, whichever input is ready |

Phase 4 then starts with a model that already runs, a twin that already has power, and a tagged
plan that says what it can detect.

---

## 13. Decisions for Assil

1. Ontology feature freeze at 0.7.x, with CQ9, 13, 14, 16 as minimal fixtures or future work?
2. The model ladder (§6.1), with routing (rung 4) as the primary D vs C contrast and message
   passing as secondary? This refines the experiment contract of 2026-10-24.
3. The primary effect measure: per-well log RMSE ratio, NSE and skill kept as descriptions (§3.3)?
4. The twin as the main engine for RQ1–RQ2, with its dials written into the plan first (§6.3)?
5. A/A controls and 10 seeds for the primary arms (§3.1)?
6. The pumping structure of §6.2 (between-year series + grouped summer demand)?
7. Pastas sensitivity rows (recharge-only, capped time scales, validation-chosen start), shown as
   post-hoc (§4.1)?
8. EuroCrops as a second alignment benchmark, and text extraction scored against the 32 curated
   statements (§8.1, §8.3)?
9. Chronos-2 and the forecast task to the thesis and a supplementary table only (§4.2)?
10. A time-reversed second test (2005–2008) for the final C and D (§5)?

---

## Appendix A. How the new numbers were produced

All read-only, with `PFE_DATASET=v4`, bytecode writing disabled, on 2026-11-10. The two scripts
were kept outside the repository and are not part of it; each check is small enough to rebuild
from this description.

- **Seed noise floor (§3.1).** For `lstm_tuned`, `stgnn_tuned`, `taccari_tuned` in `results/v4`:
  mean of the z predictions of a seed subset from `seed_<k>.parquet`, converted to metres with
  `mu` and `sd` of `results/v4/_cache/panel.parquet`, scored by `src.models.evaluate.score`,
  compared by `src.analysis.stats.paired` (drought, NSE, core wells). All 10 pairs of single
  seeds; all 15 pairs of disjoint two-seed subsets.
- **Minimum detectable effect (§3.2).** Per-well paired differences from the saved
  `metrics_per_well.csv` of the named runs, minus their median, plus δ in steps of 0.01;
  `stats._groups`, `stats.sign_flip_p`, `stats._boot_ci` unchanged; smallest δ with p below the
  threshold and the interval's lower end above 0.
- **Metric redundancy (§3.3).** `lstm_tuned` against `stgnn_tuned`, drought, core wells: signs
  and Spearman correlation of ΔNSE, Δskill and the log RMSE ratio.
- **Pastas (§4.1).** `params.csv` and `metrics_per_well.csv` of
  `pastas_seasonal_canal_trainobs_start0…9`, core wells. Selecting each well's start by training
  NSE reproduces the report's −0.75, which checks the method.
- **Imputed share of pumping (§5).** `imputation != ""` volume over total volume, by year, in
  `data/processed/dataset_v4/pumping_weekly.parquet`.
- **Ontology counts (§7).** `ontology/lulcw.ttl` parsed with rdflib; subjects in the `lulcw#`
  namespace by `rdf:type`.
- **Repository state.** `git status -sb` (ahead 109), `git log` (115 commits), `du` on the data
  and results folders.

**Not done:** no model was trained, no test suite was run, no result of the project was
regenerated, and none of the project's earlier numbers was re-derived beyond the −0.75 above.
The twin, ladder and EuroCrops proposals are untested ideas, sized from experience, not from a
prototype.

## Appendix B. External checks (2026-11-10)

- Crossref records (title, authors, journal, year) for every DOI in §9.2 and in the text; arXiv
  records for 2103.03098, 1810.03292, 2101.05186.
- INSPIRE register: the seven IRIs of §7.2 returned HTTP 200 and the `Aquifer` concept its JSON
  record; a made-up concept name returned 404.
- Not checked: the content of the papers (I verified that they exist and what they are called);
  the coverage of the EuroCrops French mapping; anything behind a login.
