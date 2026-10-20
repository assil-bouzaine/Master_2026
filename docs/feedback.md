# Feedback: critical review of the project so far

**Reviewer:** Claude, acting as an external researcher · **Date:** 2026-10-20 ·
**For:** Assil Bouzaine

**Scope:** everything committed up to `58aaa05` (Step 11):
- the roadmap, reading list, Gate 1 and Gate 2 memos, and step notes 8–10
- the dataset builder and the code of every baseline
- the saved v2 predictions in `results/v2/`

**How I reviewed it**
- I read the documents and the code line by line.
- I re-analysed the saved v2 predictions. No model was retrained. The
  numbers below come from those files (Appendix A).
- I checked the recent literature and data sources online. Every *new*
  reference here has a DOI or arXiv ID that I opened on 2026-10-20
  (Appendix B).
- I pulled the BNPE 2024 volumes once into a scratch folder, not into
  `data/`, to test one hypothesis. The real refresh must go through
  `python -m src.ingest.hubeau_bnpe --refresh` and be logged in
  `data/README.md`.

**What I did not do:** read the PDFs in `Articles/`, re-check the DOIs
already in the reading list, or re-run any model.

> **Update, same day, after the fixes started (see `docs/analysis_plan.md`).**
> 1. **The drought/recovery boundary is now fixed from observed SGI**:
>    the recovery starts in December 2025, not January 2025. 2025 was still a
>    drought year, with a relapse in Oct–Nov 2025. With this boundary:
>    - the ML baselines have skill 0.40–0.51 against climatology in the
>      drought and 0.23–0.57 in the recovery
>    - the hard part is the drought phase, 2025 included, not the recovery
>
>    Points 1–2 below and §2.1–2.3 used the provisional boundary. Their
>    direction holds (negative drought NSE, mostly an offset), but the
>    current numbers are in `docs/results_baselines.md`.
> 2. **Clustered statistics** (10 km cells, Holm correction) show that **no
>    ML baseline is significantly better than Pastas in the drought phase**.
>    The step-10 Wilcoxon tests had treated wells as independent.
> 3. **Restriction orders (§3.5):** only **surface-water** zones may be used.
>    Groundwater-zone orders are triggered by piezometers of the same
>    aquifers, so using them would leak the target.
> 4. **Correction to §3.2.** The 2024 canal intakes are **not** missing. They
>    were published without a usage code: 163 of the 177 such rows are canal
>    intakes.
>    - With the usage restored from each intake's other years, the plain took
>      **76.5 Mm³ in 2024** (2023: 47.3; 2022: 96.0).
>    - The v2 imputation (97 Mm³) therefore overstated 2024 by about 25 %,
>      not by a factor of 100.
>    - The "imputed canal comeback" explanation of the 2024–25 offset is
>      weaker than written below. Dataset v3 uses the real values.
> 5. **The knowledge-graph pre-check (§5.1) was redone properly**
>    (`docs/kg_precheck.md`: regional signal removed, permutation tests).
>    - The early warning was too pessimistic. After removing the plain-wide
>      signal, wells **in the same BD LISA entity and within 5 km** co-vary
>      more (+0.21 partial correlation, QAP p = 0.048), and so do wells at
>      **similar screen depth** (p = 0.002).
>    - Shared pumping neighbourhoods add nothing significant.
>    - The 3-nearest-wells distance graph joins different entities in 53 % of
>      its edges.
>    - So a knowledge-graph graph has real information to add: same-unit,
>      similar-depth neighbours at short range.

---

## 0. The ten points that matter most

1. **"Every model is stuck at NSE 0.25 in the drought" is misleading.**
   - Split the test window in two. In the drought phase itself (May
     2022 → Dec 2024), every model has a **negative** median NSE (−0.19 to
     −0.59). The 0.25 comes from the 2025–26 recovery.
   - Against a "normal year" (climatology), the ML baselines remove about
     **55% of the error in the drought**, but only about **30% in the
     recovery**.
   - The weak spot is the recovery, not the drought. → §2.1–2.2
2. **The drought error is mostly a level offset, not missed summer
   drawdowns.**
   - The offset grows in winter 2024–25: the models expect a recovery that
     does not come.
   - The median summer error in the Pliocene is about 0 m. → §2.3
3. **The pumping inputs are the weather in disguise.**
   - Irrigation and canal volumes were spread over the year with the
     climatic deficit. Within a year they therefore correlate 0.92–0.97
     with that deficit.
   - No model can separate "pumping" from "evaporation" inside a year.
     This undermines RQ2–RQ4 unless it is fixed or handled openly. → §3.1
4. **The test-period inputs are partly invented, and BNPE 2024 is now
   online.**
   - Pumping for 2024–26 is imputed from 2020–22.
   - Real 2024 groundwater drinking-water abstraction is about 8% lower.
     That is the drop BRGM reported in September 2024.
   - The imputed canal volumes "come back" to about 100 Mm³ after the
     reported halving in 2023. This plausibly explains point 2. → §3.2
5. **KGE is computed on heads in m NGF, so it depends on the datum.**
   12 of the 33 core wells have a mean head below 5 m NGF; their KGE is
   meaningless. → §2.4
6. **Two of the three RQ1 regimes have no baseline numbers.**
   - Leave-wells-out and the 25/50% data subsets have not been run.
   - The unseen-well setup is not defined: the z-scores need the well's
     own mean. → §2.6
7. **The "Taccari-style" ST-GNN is not Taccari-style.**
   - Taccari's graph has rain, ET, river and pumping nodes; ours links
     wells to wells only.
   - It also got 0 tuning trials, against 24 for the LSTM. → §4.1, §4.3
8. **Early warning for RQ1: at BD LISA entity level, the knowledge graph
   adds nothing beyond distance.**
   - Two wells in the same entity do not have more correlated anomalies
     than two wells at the same distance in different entities.
   - 31 of the 65 wells sit in one entity (`671AA00`).
   - The knowledge graph must go below the entity (Pliocene layers by depth)
     and know which unit each borehole pumps from. Otherwise the knowledge-graph
     graph collapses into a group label. → §5.1
9. **RQ2 and RQ3 need to be reformulated.**
   - PiShield constrains *outputs*. It cannot express the *sign of a
     response to an input*.
   - SGI classes are computed from the predicted head, so "SGI concept
     accuracy" cannot detect a reasoning shortcut.
   - The concepts should be the **driver contributions** (pumping,
     recharge, canal). The Pastas result "evaporation fakes pumping" is
     the textbook shortcut.
   - A semi-synthetic twin with known contributions makes RQ3 and RQ4
     testable. → §5.2–5.4
10. **Literature: the closest competitor is missing.**
    - Wu et al. 2025 in *WRR* builds a graph model with hydrogeological
      units as prior knowledge.
    - The 2026-10-13 "correction" in CLAUDE.md §10 merged it with a
      different Wu et al. 2025 paper (*JGR: MLC*).
    - Also missing: Collenteur et al. 2024, Chidepudi et al. 2025, and
      Kirschstein & Sun 2024 (river topology did not help a GNN). → §6

**Timing.** You are about 7 weeks ahead of the roadmap (Phase 3 was
planned to start on 7 December). Spend that buffer on points 1–9 before
building the ontology. They decide whether the ontology can show anything
at all.

---

## 1. What is already strong (keep it)

- **Honest selection.** Choices are made on validation only, the test is
  untouched, v1 is frozen, and paired Wilcoxon tests are run. Negative
  results (FlexModel, regional pumping) are kept. Many published papers
  don't do this.
- **Pastas variants used as hypothesis tests.** This is how hydrologists
  think. The finding that "flat pumping makes Pastas fake the summer drop
  with evaporation" is valuable. It is the best example of a reasoning
  shortcut in the project (§5.3).
- **A data check before a constraint.** The head-ordering check (Step 6b)
  killed a wrong rule before it was used. Apply the same discipline to
  every rule (§5.2).
- **Reproducible data work.** Cached, idempotent ingest, the data log and
  one note per step.
- **Chronos-2 as the forecasting reference**, with the honest conclusion
  that forecasting is not where the contribution lies.

---

## 2. Evaluation: the numbers tell a different story

### 2.1 Split the test window

Median over the 33 core wells, v2 runs:

| Model | Validation | Test (all) | Drought, May 2022 → Dec 2024 | Recovery, 2025 → 2026 |
|---|---|---|---|---|
| Climatology | 0.07 | −0.27 | **−1.91** | 0.07 |
| Pastas (seasonal + canal, v2) | 0.28 | 0.06 | **−0.59** | 0.18 |
| LightGBM | 0.49 | 0.20 | **−0.34** | 0.43 |
| LSTM, tuned | 0.63 | 0.24 | **−0.19** | 0.31 |
| Distance ST-GNN | 0.46 | 0.24 | **−0.21** | 0.43 |
| Ensemble LightGBM + LSTM | 0.62 | 0.25 | **−0.27** | 0.39 |

**What it means.**
- In a sub-period, NSE compares the model with *the mean of that
  sub-period*. In the drought, that benchmark already "knows" how low the
  levels went, and every model is worse than it.
- In the recovery, every model beats it.
- The 0.25 headline mixes two very different regimes. This also explains
  why the "validated weeks" scores were negative: validated data are mostly
  the drought years.

**Action (S = under a day):**
- Add the two sub-periods to `src/models/evaluate.py`.
- Fix the boundary from data, before any new run. For example, use the week
  when the median core SGI goes back above −0.5, or a BRGM bulletin.
  2024-12-31 is only my proposal.
- Make the drought phase the primary endpoint.

### 2.2 Use a benchmark that does not know the answer

**Skill relative to climatology** is `1 − MSE(model) / MSE(climatology)`,
per well, then the median. Climatology means "a normal year" from the
training period. Schaefli & Gupta (2007) make the general point: a
squared-error score only means something relative to a stated benchmark.

| Model | Drought | Recovery | Test (all) |
|---|---|---|---|
| Pastas | 0.19 | 0.12 | 0.28 |
| LightGBM | **0.55** | 0.36 | 0.48 |
| LSTM, tuned | 0.54 | 0.27 | 0.47 |
| Distance ST-GNN | 0.46 | 0.28 | 0.40 |
| Ensemble | **0.55** | 0.31 | **0.51** |

**What it means.**
- The ML models remove about half of the "normal year" error during the
  drought. That is a real skill, and the Gate 2 summary undersells it.
- They are relatively worse in the recovery.
- Pastas is weak everywhere, for the reasons in §4.4.

**Action:** report three scores side by side:
- NSE, the convention
- skill relative to climatology
- skill relative to Pastas, the hydrology reference

### 2.3 What the error actually is

The error can be split into an offset, a timing part and an amplitude part.
In the drought phase (median over wells):

| | Ensemble | LSTM | ST-GNN | Pastas |
|---|---|---|---|---|
| Share of the MSE that is a pure offset | **0.42** | 0.32 | 0.40 | 0.43 |
| Offset in training-sd units (validation → drought) | −0.10 → **+0.28** | −0.16 → +0.23 | −0.14 → +0.28 | −0.28 → +0.32 |
| Correlation r (validation → drought) | 0.91 → 0.73 | 0.91 → 0.75 | 0.88 → 0.66 | 0.81 → 0.53 |
| Amplitude ratio α in the drought | 0.93 | 0.98 | 0.89 | 0.99 |

Median ensemble error (prediction − observation, m) for the Pliocene, by
season:

| | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| Jun–Sep | −0.17 | −0.04 | 0.04 | −0.03 | 0.04 |
| Oct–May | −0.07 | 0.04 | 0.06 | **0.18** | **0.17** |

The alluvium shows the same pattern: +0.13 to +0.35 m per year in 2023–25.

**What it means.**
- The amplitude is about right (α ≈ 0.9–1.0).
- The aggregate error is mainly a **positive offset that grows in the
  non-summer months of 2024–25**. The models expect the levels to recover
  after rain, and they don't recover as much.
- The offset flips sign between validation (too low) and the drought (too
  high). That points to a **slowly varying missing driver**, not to
  within-summer pumping intensity.
- The Sabirou hydrograph in the Gate 2 summary is real, but it is not
  representative of the aggregate.

**Candidate causes, each testable:**
1. Imputed canal recharge "coming back" in 2024–26 (§3.2).
2. Multi-year storage depletion that is longer than the 104-week look-back.
3. Lower river infiltration in low-flow years. The models get no river
   input (§3.5).
4. Undeclared groundwater pumping that replaced restricted canal water.
   This is a hypothesis; BNPE cannot test it.

### 2.4 KGE on heads depends on the datum

`evaluate.py:38-42` computes the bias term as β = mean(sim) / mean(obs) on
heads in m NGF.
- At BARQUA (mean head 0.30 m NGF), a +0.1 m bias gives β = 1.33.
- At a well at 140 m NGF, the same bias gives β = 1.0007.
- 12 of the 33 core wells have a mean head below 5 m NGF, so a third of
  the KGE values are dominated by the datum.

**Action (S):** choose one of these:
- compute KGE on z-scores (training mean and sd)
- replace β by (μ_sim − μ_obs) / σ_obs
- drop KGE and report r, α and the bias in metres separately; this is the
  most informative option for this paper

### 2.5 Extrapolation is not the main failure

With v2 (training from 2005):
- Only 3% of test weeks (median per well; mean 12%) fall below a well's
  training minimum. 11 of 33 wells exceed 10%.
- The models predict below that minimum in about 3% of weeks.
- Test NSE is **not** correlated with the out-of-range share (Spearman
  −0.02).

So don't spend time on "LSTMs cannot extrapolate" fixes. The problem is
information (§3), not range.

### 2.6 Missing regimes, and the unseen-well problem

- **Not run yet.** `splits.json` contains 5 leave-wells-out folds, but no
  model reads them. The 25/50% training subsets have not been run either.
  RQ1 promises both regimes.
- **Unseen wells.** Every neural model predicts z and converts it back with
  *the well's own* training mean and sd (`features.py:102-104`,
  `lstm.py:66`). For an unseen well, those are unknown. Decide and state
  one of these:
  - (a) predict only the dynamics (z), scored with the hidden well's
    mean and sd, and call it a "dynamics" score
  - (b) also predict the mean level from statics or knowledge-graph
    attributes; this is harder but more honest

  Follow one convention from the literature (Heudorfer et al. 2024;
  Chidepudi et al. 2025) and cite it.
- **Subsets.** Define the 25/50% subsets *before* running: random blocks
  of years, wells, or both.

### 2.7 Statistics

- **Wells are not independent.** There are nested piezometers, close
  neighbours, and 20 core wells in one entity. Paired Wilcoxon p-values
  are therefore optimistic.
  - Add a block bootstrap by site or aquifer group, with confidence
    intervals for median differences.
  - Apply a Holm correction across comparisons.
  - Report effect sizes.
- **Seeds.** Report the spread of single-seed scores (mean ± sd) next to
  the score of the seed-averaged prediction.
- **Analysis plan.** Write and commit a one-page plan before Phase 4:
  primary endpoint, primary comparisons, tests. Reviewers trust endpoints
  that were declared in advance. It also protects you from tuning the
  story to the results.

---

## 3. Data: the inputs cannot carry the signal you are looking for

### 3.1 Pumping ≈ weather (an identifiability problem)

`build.py:240-259` spreads each annual irrigation and canal volume over the
weeks in proportion to max(ETP − rain, 0), April to October. The seasonal
drinking-water variant is 50% the same shape.

Week-by-week correlation within a year (April–October, each year
normalised, plain average):

| | Climatic deficit | Canal input | Groundwater irrigation |
|---|---|---|---|
| Climatic deficit | 1 | **0.97** | **0.92** |
| Canal input | | 1 | 0.97 |

Inside a year, the pumping inputs carry almost no information beyond the
weather. Only the *annual totals* and *differences between wells* identify
a pumping effect. Groundwater drinking water is nearly flat at 37–45 Mm³
per year, so there is very little of that signal for the Pliocene.

**Consequences for each research question:**
- **RQ2 (counterfactual signs).** Changing pumping while keeping the
  deficit fixed creates inputs never seen in training. The "response" is
  then extrapolation.
- **RQ3 (shortcuts).** Any model can reproduce the summer drop with ETP
  instead of pumping, and Pastas does exactly that. In
  `pastas_seasonal_canal` (v2), the evaporation factor f sits at its bound
  (−2) for 15 of 55 wells, and the median pumping gain is practically zero.
- **RQ4 (explanations).** Within a year, an attribution "the drop is due to
  pumping" versus "due to evaporation" is arbitrary.

**What to do:**
1. Get pumping timing that is **not** a function of the weather: monthly
   production from the utilities or the SAGE syndicate (already asked) and
   drought restriction orders (§3.5).
2. Until then, treat "summer demand" (deficit plus seasonal pumping) as
   **one driver group** in attributions and tests. Claim pumping effects
   only from the variation between years and between wells.
3. Quantify what this costs with the semi-synthetic twin (§5.3): simulate
   pumping with independent timing versus deficit-shaped timing, and
   measure how well each model recovers the true pumping response.

### 3.2 Test-period inputs: imputed, and now replaceable

Hub'Eau now returns **1,846 BNPE rows for dept 66 in 2024**. The cache
from 5 October stops at 2023. Plain volumes (bbox + 0.04°, Mm³):

| | 2022 | 2023 | **2024, BNPE now** | 2024 as imputed in dataset v2 |
|---|---|---|---|---|
| Groundwater, drinking water | 40.4 | 36.5 | **36.6** | 39.8 |
| Groundwater, irrigation | 18.6 | 18.1 | **15.3** | 16.6 |
| Surface, canal intakes | 95.1 | 47.3 | **1.0** (almost surely incomplete) | 96.8 |
| Surface, irrigation | 78.3 | 63.6 | **62.9** | 74.4 |

Groundwater drinking water from the same 158 ouvrages declared in 2022,
2023 and 2024: 37.4 → 34.3 → 34.4 Mm³, a drop of about 8%. This matches
the BRGM bulletin of 16 September 2024: the deep Pliocene was "modérément
bas" *"du fait de la forte diminution de la pression des prélèvements,
engendrant une remontée locale des niveaux"*.

**Consequences:**
- **The Phase 5 case study is mis-dated.** The roadmap's "2025 Pliocene
  recovery due to reduced abstraction" should be the **summer 2024 local
  rise**. It can only be tested if the real 2024 inputs replace the
  imputed ones.
- **The canal input jumps back up.** The dataset feeds the reported 2023
  canal volume (47 Mm³), then imputes 97 Mm³ for 2024 and 131 Mm³ for 2026,
  scaled by the record 2026 deficit. Canal gains are positive, so the
  models are told that canal-return recharge came back. That is a
  plausible part of the offset in §2.3.
- **2023 may be under-reported.** The roadmap and the memo say 2023 is
  under-reported, yet it is used as is, in the middle of the drought test.

**Action (M = 2–5 days):**
- Refresh BNPE and build **dataset v3**.
- For canals in 2024 and later, choose and document a rule (hold at the
  2023 level, or scale with restriction orders). Run a sensitivity with
  2023-held versus the 2020–22 mean; the change in the 2024–25 offset is
  itself a result.
- Give the models an "imputed input" flag, and make no attribution claim
  about imputed weeks.

### 3.3 The 2018 reporting break is inside the training period

Groundwater irrigation jumps from 8.7 to 15.7 Mm³ between 2017 and 2018
because more boreholes declare, not because more water was pumped. The
models see a fake step in an input. Pastas is especially sensitive to
steps.

**Fix, one of:**
- a balanced panel: only ouvrages declared in every year
- a break dummy
- rescale the years before 2018

Then test with Pastas.

### 3.4 v2 silently changed the meaning of "canal"

`canal_series()` sums all surface irrigation and canal intakes in
`pumping_points`, and v2 includes the whole département. As a result:
- the 2019 input is 214 Mm³ in v1 and 299 Mm³ in v2
- the 2016 input is 239 Mm³ in v1 and 388 Mm³ in v2

Mountain canals do not recharge the plain. Restrict the input to the
plain. Better still, restrict it to canals whose command area overlies
each alluvial unit, which is an `irrigates` relation for the knowledge
graph. This also muddies the v1 → v2 comparison.

### 3.5 Signals you already have, or can get, but don't use

| Signal | Status | Why it matters | Effort |
|---|---|---|---|
| **River discharge** (45 gauges) | Already in `dataset_v*/rivers_weekly.parquet`; **no model reads it** | River–aquifer exchange in the alluvium. It also carries Pyrenean snowmelt, which local SAFRAN rain misses | S |
| **Forcing over the recharge zone** | Nearest 8 km cell today | The confined Pliocene is not recharged by rain at the well. Average SAFRAN over the unit's outcrop (BD LISA order 1). This is a feature *derived from the knowledge graph* | S–M |
| **Drought restriction orders** | Open data: data.gouv.fr "Donnée Sécheresse – VigiEau" (one CSV per year, "Arrêtés YYYY") and "Donnée Sécheresse – Propluvia" (older zones) | Weekly timing of irrigation and canal cuts that is *not* a function of the weather pattern. Check the earliest year covered | M |
| **Annual drinking-water production per service and per works** | Open data: data.gouv.fr "Services publics d'eau potable – description et indicateurs de performance" (SISPEA) | Real totals for the test years. Check whether 2024–25 are published | M |
| **Borehole depth for the 92% of BNPE points without a BSS link** | Not done | Match to BRGM BSS (InfoTerre) by position and name, plus rules ("puits" vs "forage", drinking water vs irrigation) with a confidence level. This is the `pumpsFrom` relation | M |
| **Monthly production, pumping by layer, layer geometry** | Not asked of the right people | The Dem'Eaux Roussillon team (BRGM, Lanini et al. 2022) built two process models with shared pumping locations. The ANR AQUIMER project (BRGM, 2025–2029) works on the same aquifer. One e-mail through the supervisor | S |

**The canal-recharge evidence has a confound.** The canal input peaks in
spring and summer, and so do river high flows (snowmelt) and irrigation.
Before claiming canal-return recharge, run two **placebo variants**: replace
the canal series by (a) a seasonal signal with the same shape and (b) river
discharge. If a placebo helps as much, the evidence is for "a spring–summer
signal", not specifically for canals. The "spring rise at Millas when it
hardly rains" fits snowmelt-fed river infiltration as well as canals.

### 3.6 A small leak

`pct_days_artesian` is computed on the **whole record, test included**
(`bdlisa_profile.py:216-222`), then used as a static input
(`features.py:34-35`). Compute it on the training period only. It is also
an identity-like static, which is the Heudorfer et al. (2024) concern.

---

## 4. Baselines: fair overall, but fix these before a paper cites them

### 4.1 The distance ST-GNN is not "Taccari-style"

I checked Taccari et al. (2024) in the open-access version:

| | Taccari et al. 2024 | `src/models/stgnn.py` |
|---|---|---|
| Nodes | wells **plus rain, ET, river-stage and pumping stations** (exogenous nodes) | wells only; forcings are node features |
| Edges | 3 nearest wells, **all pumping stations**, nearest rain and ET station, 2 nearest river points, with weights by edge type | 3 nearest wells |
| Model | MTGNN without graph learning: mix-hop propagation, dilated gated temporal convolutions | GRU + 2 GCN layers |
| Synthetic test | MODFLOW synthetic set for the ablations; the predefined graph beat a learned one (8.13 cm vs 10.90 cm) | none |

**Why it matters.** RQ1 asks whether the *semantics* of the edges help. The
fair competitor is a **Taccari graph**: the same node types as the
knowledge-graph model, with edges from distance rules. Then the only
difference from the knowledge-graph model is how the edges are chosen.

**Action:**
- Rebuild that baseline. The code is public, per the reading list:
  `github.com/mlttac/GroundwaterFlowGNN`.
- Keep the current 3-nearest-neighbour model as an extra row.

### 4.2 Names that don't match the code

- **"EA-LSTM global".** The implemented model appends the statics to every
  input step (`lstm.py:4-11`). That is a global LSTM with static inputs, not
  Kratzert's EA-LSTM, where the statics drive the input gate. Either
  implement EA-LSTM (NeuralHydrology has it) or rename the model.
- **"LSTM per well"** (CLAUDE.md §3) is not implemented. Dropping it is
  defensible: Kratzert et al. (2024, HESS Opinions) show that models trained
  on many basins beat single-basin LSTMs. Say so in the paper rather than
  skipping it silently.

### 4.3 Equal tuning budget (rule 11)

| Model | Tuning budget so far |
|---|---|
| LSTM | 24 Optuna trials |
| ST-GNN | **0** (hidden 64 and lr 1e-3 fixed; no CLI arguments, `stgnn.py:87-97`) |
| LightGBM | 8 configurations |
| Pastas | 6 variants |

Fix one budget for every neural model, including the future
knowledge-graph model: for example 24 trials, a search space of the same
size, and selection on validation. Otherwise a knowledge-graph win can be
dismissed as "more tuning".

### 4.4 Make Pastas the strongest version of itself

- **Pumping.** Today pumping is one 3 km sum with one Hantush response. Use
  `ps.WellModel` with `ps.HantushWellModel` (both in the pinned Pastas
  2.0.0): one response scaled by each pumping point's distance (Brakenhoff
  et al. 2022). Once the knowledge graph has `pumpsFrom`, restrict it to
  points in the well's aquifer unit. This is "giving Pastas the
  knowledge-graph information", which the fairness argument in the Step 9
  note already requires.
- **Rivers.** Add a river stage or discharge stress for the alluvium wells.
- **The 2018 step.** Harmonise it (§3.3).
- **Don't use Pastas gains as "physics truth"** in the counterfactual tests.
  The median pumping gain is about 0, and f is at its bound for 15 of 55
  wells. The gains mirror the confounding of §3.1. Use them as one point
  of comparison; §5.3 gives a better reference.

### 4.5 Chronos-2: two cheap upgrades

- **Fine-tuning.** `Chronos2Pipeline.fit()` exists in the pinned
  chronos-forecasting 2.3.2 (full or LoRA). A fine-tuned Chronos-2 is the
  strongest honest forecasting reference.
- **Cross-learning.** `predict(..., cross_learning=True)` forecasts a batch
  jointly. Today each batch holds the issue weeks of a single well. Try
  contexts grouped by knowledge-graph unit, by distance, and not grouped.
  This needs no training, and it is a small RQ1 result for foundation
  models.
- **Related work.** Holmberg et al. (2026) couple a knowledge graph with a
  frozen Chronos-2 for river hydraulics. Rangaraj et al. (2025) found
  Chronos the best of 17 models for Everglades water levels.

### 4.6 Refit on train + validation, decided in advance

After choosing hyperparameters on validation, refit on 2005 → April 2022
with the same number of epochs, then test. This is standard in time series,
and the models then see the 2020–22 state. Write it in the analysis plan
*before* looking at the result, and report both versions.

---

## 5. Research design: where RQ1–RQ4 break, and how to repair them

### 5.1 RQ1: separate knowledge as *information* from knowledge as *structure*

**The problem.** The knowledge-graph model will receive new information
(layer-aware pumping, recharge zones, land use) *and* a new graph. If it
wins, a reviewer will ask which of the two did it.

**The design.** All arms get the same tuning budget:

| Arm | Inputs | Graph |
|---|---|---|
| A | baseline inputs | none (LSTM) |
| B | features derived from the knowledge graph, given flat | none |
| C | knowledge-graph features | Taccari distance graph (§4.1) |
| **D** | knowledge-graph features | **knowledge-graph graph (main model)** |
| E | knowledge-graph features | knowledge-graph graph, rewired with degrees preserved |
| F | knowledge-graph features | random graph and complete graph |

How to read the comparisons:
- **B vs A** = the value of the knowledge as information.
- **D vs C** = the value of the edge semantics.
- **D vs E and F** = the shortcut control.
- Pastas with points selected through the knowledge graph is "arm B" for
  hydrologists.

Two papers back this design:
- Kirschstein & Sun (ICML 2024) found that the river-network topology gave
  a GNN no gain for discharge. The prior that "a domain graph helps" is not
  safe; this design protects the paper whichever way the result goes.
- Topp et al. (2023) used explainable AI to check whether graph models
  learned physically meaningful spatial relations. That is a template for
  your analysis.

**Early warning: the knowledge-graph pre-check I ran.** I correlated the
weekly anomalies (z minus the training climatology, train + validation
weeks) for 1,669 well pairs with at least 104 common weeks:

| Distance | Same BD LISA entity | Different entity |
|---|---|---|
| 0–5 km | 0.39 | 0.30 |
| 5–10 km | 0.33 | 0.43 |
| 10–20 km | 0.32 | 0.33 |
| 20–40 km | 0.33 | 0.29 |

- A linear fit gives r = 0.54 − 0.075·log(distance in km)
  **− 0.065·[same entity]**, with a standard error of 0.017 on the last
  term.
- Between Pliocene wells (385 pairs), r is about 0.3 whatever the distance:
  0.37, 0.28, 0.29 and 0.33 across the distance bands.
- 31 of the 65 wells are in `671AA00`.

**What it means.** The check is crude: the "different entity" pairs mix
nested piezometers, karst and alluvium. Even so, the signal is clear. At
BD LISA level-3 granularity, membership in a unit says nothing about
co-variation beyond what distance already says. A knowledge-graph graph at
that level is unlikely to beat a distance graph. The Pliocene, where skill
is lowest, is one node for half of the wells.

**Before building the knowledge-graph graph:**
1. **Refine the check.**
   - Use partial correlations after removing the regional (plain-mean)
     anomaly.
   - Pair wells by same entity *and* similar screen depth.
   - Treat nested pairs separately.
   - Add similarity of the pumping neighbourhood: do two wells share the
     same pumped unit?
2. **Add structure below the entity for the Pliocene.**
   - Depth classes from `profondeur_investigation` and borehole logs.
   - The layers of Dall'Alba's (2023) geological model, if they can be
     obtained (Dem'Eaux; Lanini et al. 2022).
3. **Decide early if the result stays null.** If the knowledge-graph
   relations still add nothing to distance, shift the main claim to RQ2–RQ4
   (knowledge as constraints and explanations). That is still publishable,
   and far better than discovering it at Gate 4.

### 5.2 RQ2: constraints that actually encode the ontology

**Problem 1: PiShield cannot express a response sign.**
- PiShield (Stoian et al. 2024) guarantees that every output vector
  satisfies requirements written over the *output variables*, such as
  propositional rules or linear inequalities like y₁ ≤ y₂.
- "Abstraction lowers head" is a relation between outputs for *two
  different inputs*, a sign of ∂h/∂pumping. It cannot be written that way.
  Adding counterfactual outputs only guarantees it at the chosen
  perturbations.
- With head ordering dropped, the only PiShield rule left in the roadmap is
  "weekly change bounds", which does not come from the ontology. The "hard"
  arm would not test the ontology at all.

**The fix: make the hard arm monotone by construction.** Options:
- sign-constrained response functions in an additive model: gain
  = −softplus(·) for `decreasesHead`, +softplus(·) for `increasesHead`
  (§5.5)
- networks that are monotone in selected inputs (e.g. Runje &
  Shankaranarayana, ICML 2023)
- a cheap baseline: LightGBM's built-in `monotone_constraints`

The soft arm, gradient or counterfactual sign penalties, is the method of
Ross et al. (2017), *"Right for the Right Reasons"*. Your title borrows
their phrase, so cite them.

**Problem 2: counterfactual tests on pumping are confounded** (§3.1).
Report sign accuracy for perturbations within the observed range of
year-to-year variation, and on the synthetic twin.

**Problem 3: every concept-level rule needs a data check first**, as head
ordering had. Example rule: "two wells in the same unit are in the same SGI
class, ± 1". The pre-check found a within-Pliocene anomaly correlation of
only about 0.3, so this rule will probably fail. Test it before using it.

### 5.3 RQ3: what is a "concept" in a regression?

**The problem.**
- In Marconato et al., a reasoning shortcut is a model that gets the right
  label through wrong *latent* concepts.
- Here, the SGI classes are computed from the predicted head. If the head
  is right, the SGI is right by construction.
- "SGI concept accuracy" is therefore a discretised regression score and
  cannot reveal a shortcut.

**A reformulation that fits the hydrology:**
- **Concepts** = the contribution of each driver to the head: recharge,
  pumping by unit, canal or river. A Pastas decomposition is exactly this
  (and it works like a concept bottleneck, Koh et al. 2020).
- **Knowledge** = which drivers can affect which well (knowledge-graph
  paths) and with which sign (`lulcw:` polarity).
- **Reasoning shortcut** = the head is fitted with the wrong contributions.
  For example, a summer drawdown explained by ETP instead of pumping. Your
  Step 9 Pastas result (f at its bound to fake pumping) is exactly this.
  Use it as the motivating example in the paper.

**How to measure it:**
1. **A semi-synthetic twin** (about 1 week).
   - Inputs: the real forcings, real wells and abstraction points, and the
     real knowledge graph.
   - Synthetic heads = known response functions per relation + AR noise.
   - Two variants: pumping timing shaped by the deficit (as in the real
     data) and pumping timing independent of it.
   - Concept accuracy is then the error of the recovered contributions,
     measured against the ground truth.
   - Taccari et al. (2024) used a synthetic MODFLOW set for their
     ablations, so there is a precedent. A full MODFLOW/FloPy twin (Bakker
     et al. 2016) is more realistic but takes 2–3 weeks; a Master's does
     not need it.
2. **Ensemble disagreement** (the BEARS idea). Train 5 seeds or models
   with equal head skill. If they disagree on the pumping contribution, the
   concept is not identified, and the model is prone to shortcuts. This is
   cheap: you already train 5 seeds.
3. **Real-world anchors.**
   - The BRGM statement of September 2024 (a local Pliocene rise from
     strongly reduced abstraction), with the real 2024 inputs.
   - The nested piezometer pairs.
4. **Semantic ablation (rewiring) stays, but calibrate its power on the
   twin.** If rewiring does not hurt even on synthetic data where the true
   structure matters, the test cannot detect anything on real data.

### 5.4 RQ4: explanations

- **Use driver groups.** Because of the collinearity (§3.1), per-feature
  attributions between pumping and ETP are arbitrary. Aggregate them over
  driver groups, such as "summer demand".
- **Or use an additive model.** In a model whose contributions are additive
  by construction (§5.5), the decomposition *is* the model, and fidelity is
  exact. Integrated Gradients and GNNExplainer then become a check, not the
  explanation.
- **Fix the case study.** The documented event is the **summer 2024** local
  rise of the deep Pliocene (BRGM bulletin, 16 Sept 2024), not a 2025
  recovery. It is testable only with the real 2024 pumping (§3.2).
- **Add a sign-consistency test.** The entity-existence test for templated
  text is good. Also check that the text says "pumping lowered the level"
  only if that contribution has that sign.

### 5.5 A main model that serves all four RQs (an option for you and the supervisor)

**The idea.**
- The knowledge graph feeds a (heterogeneous) GNN.
- The GNN outputs the **parameters of sign-constrained response functions**.
- The responses are added up by a differentiable superposition: a
  Pastas-like model whose parameters are learned for all wells at once.
- A small, bounded residual network adds what the linear model misses.

```
h_i(t) = d_i + Σ_r  gain_ir · (θ_ir ⊛ x_r)(t)  +  residual_i(t)
```

**How it maps to the plan:**
- **The stresses x_r are routed by knowledge-graph edges:**
  - recharge, averaged over the unit's outcrop
  - pumping from the points that `pumpsFrom` the well's unit, scaled by
    distance
  - canal or river inputs for the alluvium
- **RQ2.** The sign of each gain comes from the `lulcw:` polarity: a hard
  constraint by construction.
- **RQ3 and RQ4.** The contributions are exact and additive. They are the
  concepts, and they give faithful explanations in ontology terms.
- **RQ1, held-out wells.** The parameters are predicted from
  knowledge-graph attributes, so the model applies to unseen wells. This is
  "differentiable parameter learning" (Tsai et al. 2021; Shen et al. 2023).
- **A natural ablation.** Pastas, calibrated per well, has the same
  structure with no knowledge sharing. That gives the paper continuity with
  your baselines.

**Cost and risk.**
- About 2–3 weeks in PyTorch: response functions become causal 1-D
  convolutions with parametric kernels.
- Risk: a linear superposition misses nonlinearity. The bounded,
  regularised residual network covers part of it; compare against the
  black-box HGT.

**What changes.** The graph still comes from the knowledge graph, and a
heterogeneous GNN is still at the core. What changes is what the GNN
outputs. This touches a §3 design decision, so it needs your OK.

---

## 6. Literature review

### 6.1 One correction

There are **two different** Wu et al. 2025 papers:

| Paper | DOI | Status in the repo |
|---|---|---|
| Wu et al., *JGR: Machine Learning and Computation* 2025: several spatial-dependency graphs, T-GCN, North China Plain | 10.1029/2024JH000520 | CORE in the reading list ✔ |
| **Wu, Yao, Guo, Yang, He, Lancia, Zheng**, *Graph Fourier deep learning for spatiotemporal and hydrogeological interpretation of groundwater levels in the Yellow River Basin*, **WRR 61(11), e2025WR041215**, 19 Nov 2025 | **10.1029/2025WR041215** | **missing**: the 2026-10-13 "correction" in CLAUDE.md §10 treated it as a mistake |

According to its indexed abstract, the WRR paper embeds **hydrogeological
units as prior information** in a graph model of 473 wells. That makes it
the closest competitor to "a graph from knowledge". I could not open the
full text (publisher 403), so read it first and position the paper against
it. Restore the original CLAUDE.md §10 line as a second entry.

### 6.2 Add these (all verified on 2026-10-20)

| Reference | ID | Why |
|---|---|---|
| Collenteur et al., *Data-driven modelling of hydraulic-head time series: lessons from the 2022 Groundwater Time Series Modelling Challenge*, HESS 28, 2024 | doi:10.5194/hess-28-5193-2024 | 15 teams, Pastas to deep learning, on head simulation. The benchmark culture a hydrology reviewer will expect |
| Chidepudi et al., *Training deep learning models with a multi-station approach and static aquifer attributes for groundwater level simulation*, HESS 29, 2025 | doi:10.5194/hess-29-841-2025 | French piezometers (BRGM co-authors), global models with statics. Training on clusters with similar spectral properties beat training on all wells. Your closest French deep-learning analogue |
| Wu et al., WRR 2025 (above) | doi:10.1029/2025WR041215 | Hydrogeological units as a graph prior |
| Kirschstein & Sun, *The Merit of River Network Topology for Neural Flood Forecasting*, ICML 2024 | arXiv:2405.19836 | A domain graph gave a GNN no gain. Motivates the arms in §5.1 |
| Topp et al., *Stream temperature prediction in a shifting environment: the influence of deep learning architecture*, WRR 59, 2023 | doi:10.1029/2022WR033880 | Explainable AI shows whether a graph model's learned spatial relations match physics, and that this helps generalisation |
| Jia et al., *Physics-guided recurrent graph model for predicting flow and temperature in river networks*, SDM 2021 | doi:10.1137/1.9781611976700.69 | The canonical "domain graph + physics loss" model |
| Tsai et al., *From calibration to parameter learning*, Nature Communications 12, 2021 | doi:10.1038/s41467-021-26107-z | Differentiable parameter learning (§5.5) |
| Shen et al., *Differentiable modelling to unify machine learning and physical models for geosciences*, Nat. Rev. Earth Environ. 4, 2023 | doi:10.1038/s43017-023-00450-9 | Positioning for §5.5 |
| Brakenhoff et al., *Application of time series analysis to estimate drawdown from multiple well fields*, Front. Earth Sci. 10, 2022 | doi:10.3389/feart.2022.907609 | Pastas with many well fields and distance scaling (§4.4) |
| Ross, Hughes & Doshi-Velez, *Right for the Right Reasons*, IJCAI 2017 | doi:10.24963/ijcai.2017/371 · arXiv:1703.03717 | The origin of your title's phrase, and of input-gradient constraints (§5.2) |
| Koh et al., *Concept Bottleneck Models*, ICML 2020 | arXiv:2007.04612 | What a "concept" is (§5.3) |
| Runje & Shankaranarayana, *Constrained Monotonic Neural Networks*, ICML 2023 | arXiv:2205.11775 | Monotone by construction (§5.2) |
| Kratzert et al., *HESS Opinions: Never train an LSTM on a single basin*, HESS 28, 2024 | doi:10.5194/hess-28-4187-2024 | Justifies dropping the per-well LSTM (§4.2) |
| Rangaraj et al., *How effective are large time series models in hydrology? Everglades water levels*, 2025 | arXiv:2505.01415 | Chronos best of 17 models for water levels |
| Holmberg et al., *Knowledge-Graph-Augmented Chronos-2 for HEC-RAS Surrogate Forecasting*, 2026 | arXiv:2609.21381 | A knowledge graph combined with a time-series foundation model in hydraulics: related work for §4.5 |
| Schaefli & Gupta, *Do Nash values have value?*, Hydrol. Processes 21, 2007 | doi:10.1002/hyp.6825 | Benchmark-relative skill (§2.2) |
| Bakker et al., *Scripting MODFLOW model development using Python and FloPy*, Groundwater 54, 2016 | doi:10.1111/gwat.12413 | Only if a MODFLOW twin is chosen (§5.3) |
| Brodaric et al., *Enabling global exchange of groundwater data: GroundWaterML2*, Hydrogeology Journal 26, 2018 | doi:10.1007/s10040-018-1747-9 | The citable GWML2 reference (§7.2) |

### 6.3 Re-checking the novelty claim

After these papers, here is what already exists:
- GNNs for groundwater: Bai & Tahmasebi 2023, Taccari 2024, Wu 2025a and
  2025b.
- Hydrogeological prior knowledge inside a graph: Wu 2025 in WRR.
- A knowledge graph combined with a foundation model, for river hydraulics:
  Holmberg 2026.
- Evidence that domain graphs do not always help: Kirschstein & Sun 2024.

My searches found **no** groundwater model whose graph is generated from a
formal ontology or knowledge graph, and **no** reasoning-shortcut analysis
in groundwater modelling. The novelty is real but narrower. State it as:
1. a graph *and* constraints generated from explicit causal polarity in a
   knowledge graph
2. a validity test (identifiability and shortcuts) that hydrology papers do
   not run
3. ontology-grounded explanations with measured faithfulness

Do not claim "the first knowledge-informed graph for groundwater".

### 6.4 Trim and complete

- **OntoAligner, LLMs4OL and SPIRES do not answer RQ1–RQ4.**
  - Keep the manual alignments: you need them to build the knowledge graph.
  - Move the matcher benchmark to a thesis chapter or to future work.
  - This saves 2–3 weeks and GPU time.
- **Write `docs/literature/comparison_table.md`.** The guide asks for it,
  and it does not exist yet. Start with the ~12 CORE papers plus Wu 2025
  in WRR.

### 6.5 Domain sources and people

- **The Dem'Eaux Roussillon modelling** (Lanini et al. 2022, AHS conference
  abstract, HAL hal-03530184). Two process-based models of the
  Plio-Quaternary multilayer, with shared reservoir geometry and pumping
  locations.
- **ANR AQUIMER** (ANR-24-CE01-1184, coordinated by BRGM, March 2025 + 48
  months), on the same aquifer, onshore and offshore.

These teams hold what you lack: pumping by layer and the layer geometry.
Ask through the supervisor.

---

## 7. Phase 3: make the ontology serve the model

### 7.1 Competency questions derived from what the model needs

Each question should feed an edge, a feature, a constraint or a template:

| # | Competency question | Used by |
|---|---|---|
| CQ1 | Which aquifer unit, and which depth layer, does well W monitor? | node attributes, §5.1 granularity |
| CQ2 | Which abstraction points pump from the unit or layer of W, at what distance, for which use, and with what confidence? | `pumpsFrom` edges, Pastas WellModel, §5.5 |
| CQ3 | Which units overlie unit U, and is the layer between them semi-permeable? | `overlies` edges |
| CQ4 | Where does unit U outcrop, i.e. what is its recharge zone? | recharge-zone forcing (§3.5) |
| CQ5 | Which river reaches are connected to unit U? | river inputs and edges for the alluvium |
| CQ6 | Which canal command areas overlie unit U? | `irrigates`; canal input restricted to the plain (§3.4) |
| CQ7 | Which land-use classes with high irrigation demand lie in the recharge zone of W? | land-use features (RPG) |
| CQ8 | Which drivers can affect W, and with which polarity? | sign constraints (§5.2), concepts (§5.3) |
| CQ9 | Which restriction orders applied to the zone of W in week t? | restriction input (§3.5) |
| CQ10 | Which entities does an explanation of W at week t mention, and do they exist and connect to W? | template tests (§5.4) |

### 7.2 Reuse, but check GWML2 first

GWML2 is an OGC standard (OGC 16-032r2) defined as a UML and GML schema. I
could not confirm that a maintained OWL or RDF encoding exists. Check in
week 1. If there is none:
- define the few terms you need in the `lulcw:` module
- link them to the GWML2 specification with `rdfs:seeAlso` or
  `skos:closeMatch`, and cite Brodaric et al. 2018

Do not spend weeks converting XML schemas.

### 7.3 Uncertain edges

`pumpsFrom` is uncertain for about 92% of the points.
- Store the provenance (`prov:wasDerivedFrom`: BSS link, depth rule or name
  rule) and a confidence level.
- The main run uses only confident edges; a sensitivity run uses all of
  them.

This is also a natural SHACL check: every `pumpsFrom` must carry a
provenance and a confidence.

### 7.4 Granularity

Add sub-units for the Pliocene (§5.1). Without them, the knowledge-graph
graph cannot tell 31 wells apart.

### 7.5 Scope

- Time-box the knowledge-graph build to **4 weeks**, not 6.
- Write about 5 SHACL shapes and 2–3 SHACL-AF rules, and only ones the
  model uses.
- Everything else is future work.
- Draft the competency questions now. They are cheap, and they tell the
  data work in §3 what to produce.

---

## 8. Engineering and reproducibility

- **`configs/` does not exist.** Runs are configured by CLI defaults, which
  breaks rule 10. Add one YAML per run. Store the config, the git commit,
  the dataset version and the seed in every results folder.
- **`tests/` does not exist.** Add tests for:
  - the metrics, including the KGE fix
  - leakage: SGI, z-scores and `pct_days_artesian` must use the training
    period only
  - the dataset: no imputed week without its flag
- **`uv.lock` is missing** (roadmap §5). The laptop runs torch 2.14.1 CPU
  and Camber runs torch 2.8 cu128. Record the environment in each run.
- **`stgnn.py` imports `LOOKBACK` by value from `lstm.py`.** A call to
  `set_lookback()` would not reach it. Expose the ST-GNN hyperparameters as
  arguments (also needed for §4.3).
- **The ensemble picks the best of 26 subsets on validation.** That is
  fine, but say so in the paper: it is a mild selection effect.
- **Make this review reproducible.** Move the diagnostics into
  `src/analysis/diagnostics.py` (Appendix A).

---

## 9. Paper framing

- **The title says "forecasting".** Your own conclusion is that the
  contribution is simulation and explanation, and that Chronos-2 owns
  forecasting. Suggestion: *Right for the right reasons? Knowledge-graph-derived
  structure and constraints for groundwater-level **simulation** in a
  Mediterranean multilayer aquifer.* Cite Ross et al. (2017) for the phrase.
- **Lead with validity: identifiability and shortcut tests.** No hydrology
  paper does this, and it stays publishable even if the knowledge-graph
  graph does not beat the baselines.
- **Venue.** *Environmental Modelling & Software* fits. If §5.5 is adopted,
  WRR or HESS become realistic too: differentiable hybrid models are an
  active topic there. Decide at Gate 4, as planned.
- **Gate 2 addendum.** If the Gate 2 summary has not been sent yet, fix
  "finding 1" and "finding 2" with §2.1–2.3 before sending it. If it has
  been sent, send a five-line addendum: the drought/recovery split, skill
  relative to climatology, and BNPE 2024 now online.

---

## 10. Suggested order of work (about 9 weeks)

S ≤ 1 day · M = 2–5 days · L = 1–3 weeks.

| Week (from 20 Oct) | Work | Effort | Output |
|---|---|---|---|
| 1 | Evaluation: sub-periods, skill relative to climatology and to Pastas, KGE fix, bias/r/α, block bootstrap; Gate 2 addendum; analysis-plan draft; draft the competency questions | S–M | `evaluate.py` update; `docs/analysis_plan.md`; CQ list |
| 1–2 | **Dataset v3:** BNPE refresh (2024) and a canal rule with sensitivity; 2018 harmonisation; canal input limited to the plain; rivers as inputs; recharge-zone forcing; artesian share on training only | M | `dataset_v3`; a step note |
| 2 | Re-run the baselines on v3. Diagnose the offset: canals held at 2023 vs imputed; river input; canal placebo | M | `results/v3`; a short note |
| 3 | Missing RQ1 regimes for the baselines (leave-wells-out, 25/50%); equal tuning budget; the Taccari-graph baseline | M–L (GPU) | complete RQ1 baseline table |
| 3–4 | Refine the knowledge-graph pre-check (partial correlations, depth classes, pumping neighbourhoods) → decide the graph granularity | S–M | note + figure |
| 4–5 | Semi-synthetic twin; decide the RQ2/RQ3 formulation and §5.5 | M | twin generator; decision memo |
| 5–9 | Phase 3 minimal ontology: competency questions (§7.1), knowledge-graph build, SHACL, SPARQL → HeteroData | L | **Gate 3** |
| ongoing | Literature: comparison table, Wu 2025 (WRR) and the §6.2 additions; one e-mail to the Dem'Eaux / AQUIMER teams through the supervisor | M | `comparison_table.md` |

Phase 3 then still starts before its planned date (7 December).

---

## 11. Decisions for you (and the supervisor)

Each of these touches a design decision in CLAUDE.md §3, so I have changed
nothing.

1. **Primary metric.** NSE in the drought phase, plus skill relative to
   climatology; KGE replaced or fixed (§2).
2. **Dataset v3** with BNPE 2024 and the canal rule, replacing v2 as the
   default (§3.2).
3. **The RQ1 arms** of §5.1, including "knowledge-graph features without the
   graph", and the Taccari graph as *the* graph baseline (§4.1).
4. **The RQ2 hard arm:** monotone by construction instead of PiShield
   (§5.2).
5. **The RQ3 concepts:** driver contributions, plus a semi-synthetic twin;
   SGI accuracy is reported but is not the shortcut test (§5.3).
6. **The main model:** keep the black-box heterogeneous ST-GNN, or adopt the
   knowledge graph → GNN → response-function parameters model of §5.5, with
   the HGT as a comparison.
7. **OntoAligner** moves to the thesis only (§6.4).
8. **Title:** "simulation" instead of "forecasting" (§9).

---

## Appendix A: how the numbers in this review were produced

All numbers come from the saved files of dataset v2 and `results/v2/`. The
only exception is the one-off BNPE 2024 pull. The scripts are in this
session's scratch folder, which is temporary, so ask me to move them into
`src/analysis/diagnostics.py` if you want to keep them:

- `/tmp/claude-1000/-home-mclovin-Projects-Master-2026/5c1502e3-ccf7-4ed4-a349-57f50e9eeb3f/scratchpad/diag.py`:
  sub-period NSE, error decomposition, out-of-range share, KGE datum check
- `/tmp/claude-1000/-home-mclovin-Projects-Master-2026/5c1502e3-ccf7-4ed4-a349-57f50e9eeb3f/scratchpad/diag2.py`:
  plain pumping by year, pumping–deficit correlation
- `/tmp/claude-1000/-home-mclovin-Projects-Master-2026/5c1502e3-ccf7-4ed4-a349-57f50e9eeb3f/scratchpad/bnpe2024.py`:
  BNPE 2024 vs 2019–2023 (Hub'Eau `prelevements/chroniques`,
  `code_departement=66&annee=2024&size=2000`, 1,846 rows, 2026-10-20)
- Inline computations: skill relative to climatology; bias by year and
  season; Pastas parameters; the knowledge-graph pre-check (anomaly
  correlation of well pairs vs distance and BD LISA entity).

**Definitions:**
- **Sub-periods:** drought = 2022-05-01 → 2024-12-31; recovery = 2025-01-01
  → end of record.
- **Plain:** `PLAIN_BBOX` + 0.04°, as in `build.py`.
- **Median rule:** medians over the 33 core wells, each well needing at
  least 26 weeks in the period.

## Appendix B: sources checked online (2026-10-20)

- Wu et al. 2025, WRR: [XJTU record](https://scholar.xjtu.edu.cn/en/publications/graph-fourier-deep-learning-for-spatiotemporal-and-hydrogeologica/) · [AGU](https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2025WR041215)
- Taccari et al. 2024, design details: [PMC11490608](https://pmc.ncbi.nlm.nih.gov/articles/PMC11490608/)
- Collenteur et al. 2024: [HESS](https://hess.copernicus.org/articles/28/5193/2024/)
- Chidepudi et al. 2025: [HESS](https://hess.copernicus.org/articles/29/841/2025/)
- Kirschstein & Sun 2024: [arXiv](https://arxiv.org/abs/2405.19836v1) · [PMLR](https://proceedings.mlr.press/v235/kirschstein24a.html)
- Topp et al. 2023: [USGS](https://pubs.usgs.gov/publication/70250381)
- Jia et al. 2021: [USGS](https://pubs.usgs.gov/publication/70247905)
- Tsai et al. 2021: [PMC8514470](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8514470/)
- Shen et al. 2023: [USGS](https://pubs.usgs.gov/publication/70247088)
- Brakenhoff et al. 2022: [Frontiers](https://www.frontiersin.org/journals/earth-science/articles/10.3389/feart.2022.907609/pdf)
- Ross et al. 2017: [arXiv](https://arxiv.org/abs/1703.03717) · [IJCAI](https://www.ijcai.org/proceedings/2017/371)
- Koh et al. 2020: [PMLR](https://proceedings.mlr.press/v119/koh20a.html)
- Runje & Shankaranarayana 2023: [PMLR](https://proceedings.mlr.press/v202/runje23a.html)
- Kratzert et al. 2024: [HESS](https://hess.copernicus.org/articles/28/4187/2024/)
- Rangaraj et al. 2025: [arXiv](https://arxiv.org/abs/2505.01415)
- Holmberg et al. 2026: [arXiv](https://arxiv.org/abs/2609.21381)
- Schaefli & Gupta 2007: [EPFL Infoscience](https://infoscience.epfl.ch/entities/publication/3488a1d9-c650-40ce-ac69-bec9a3e99d97)
- FloPy (Bakker et al. 2016): [USGS](https://pubs.usgs.gov/publication/70170433)
- GWML2: [OGC 16-032r2](https://docs.ogc.org/is/16-032r2/16-032r2.html) · [Brodaric et al. 2018](https://link.springer.com/article/10.1007/s10040-018-1747-9)
- BRGM bulletin, 16 Sept 2024 (Pliocene, reduced abstraction): [Banque des Territoires / Localtis](https://www.banquedesterritoires.fr/nappes-phreatiques-une-situation-generale-tres-satisfaisante-mais-des-points-noirs-persistants-dans)
- Dem'Eaux Roussillon model (Lanini et al. 2022): [Eau et Biodiversité notice](https://www.documentation.eauetbiodiversite.fr/fr/notice/groundwater-modelling-of-a-complex-multilayer-coastal-aquifer-under-climate-change-in-the-framework-of-the-dem-eaux-roussillon-project-35833)
- ANR AQUIMER: [ANR](https://anr.fr/Projet-ANR-24-CE01-1184)
- VigiEau restriction orders: [data.gouv.fr](https://www.data.gouv.fr/datasets/donnee-secheresse-vigieau) · Propluvia: [data.gouv.fr](https://www.data.gouv.fr/datasets/donnee-secheresse-propluvia/reuses_and_dataservices)
- SISPEA drinking-water indicators: [data.gouv.fr](https://www.data.gouv.fr/datasets/services-publics-deau-potable-description-et-indicateurs-de-performance-2)
