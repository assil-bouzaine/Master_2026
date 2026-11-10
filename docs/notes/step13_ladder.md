# Step 13: the review of 2026-11-10 and the first rungs of the model ladder

Date: 2026-11-10. Files: `fable_review.md`, `src/models/response.py`, `tests/test_response.py`,
`src/analysis/ladder_report.py`, `scripts/run_v4_cpu.sh` (step `ladder`), analysis plan §14 item 18.

## Recurring check (CLAUDE.md §7, review of 2026-10-25), answered before starting

1. *Which link of the chain does this advance?* Water → model. For the first time a model of the
   project's own kind (signed responses to recharge, pumping and canal water) is fitted, so that the
   knowledge graph has something to route into.
2. *Where does dated land use enter?* It does not enter these two rungs. The canal volume is the only
   agricultural input (surface irrigation and canal intakes of the plain). The crop-demand index can
   be added as a stress later; the land-use test of 2026-10-26 found no detectable gain from it.
3. *Observed / inferred / assumed / unknown.* Observed: heads, weather, annual declared volumes.
   Assumed: the weekly spread of pumping, the 3 km radius, the shape of the response (a Gamma curve),
   the bounds on its time scale. Unknown: which unit each pump draws from (not used in rungs 1–2:
   they use the 3 km sum, like the Pastas reference).
4. *Evidence vs plan.* The model, its tests and its report script exist and run. Its results are on
   Kaggle and not pulled yet. Rungs 3–5, the twin and the explanations are still plans.
5. *Does the experiment resolve an open question?* Yes: whether fitting all wells together, with
   bounded response times and sharing by aquifer group, removes the instability measured in the
   Pastas reference. If it does not, the hybrid needs another design before Phase 4.
6. *Missing from the subject:* unchanged (satellite rule, alignment results, explanations, dashboard).

## What was done

### 1. A review of the whole project (`fable_review.md`)

Written at Assil's request, without changing anything. Its new numbers come from the saved result
tables (the method is in its Appendix A). The four that matter:

- **Training noise.** Train the same model twice with different random seeds and the two results
  differ. Between two-seed averages of the tuned LSTM, the median difference in drought NSE over the
  wells reaches 0.12. The effects measured so far (land use: +0.016 and +0.001) are smaller than
  this, so the data could not have shown them either way.
- **What the test can detect.** With 33 wells in 14 clusters, two models that share a backbone must
  differ by about 0.05–0.10 NSE before the test of record sees it; models as different as our two
  graph baselines, by 0.25–0.5.
- **Two endpoints that are one.** A difference in NSE and a difference in skill are the same
  difference in squared error, divided by two different numbers. They have the same sign in all 33
  wells. Counting them as two tests wastes half of the statistical budget.
- **Why the Pastas reference is unstable.** Refitted from ten starting points, a well keeps its
  recharge response but gets pumping and canal responses that differ tenfold, often with a time
  scale at its 27-year limit. Such a slow response behaves like a free trend: it costs nothing in
  2005–2019 and decides the level in 2022–2025. The reason is the data: weekly pumping is 100 %
  filled in for 2005–2011, so the fit sees eight real annual totals. Hydrologists call this
  *equifinality*: many parameter sets fit equally well (Beven 2006,
  doi:10.1016/j.jhydrol.2005.07.007).

The last point matters most, because the planned main model has the same structure as Pastas.

### 2. Decisions (analysis plan §14 item 18)

Assil: "okay start working and u have the permission to do anything". Read as approving the five
points Claude recommended: the ontology is frozen at 0.7.x; the model is built as a ladder; the
primary measure of a contrast becomes the log of the RMSE ratio; primary arms get 10 seeds and a
"same-arm band"; the twin also carries RQ1–RQ2. The other proposals wait for Gate 3. Assil can still
change any of them before the plan is tagged.

### 3. Rungs 1–2 of the ladder (`src/models/response.py`)

The head of a well, relative to its training mean, is written as

    constant + gain_recharge × (smoothed recharge) − gain_pumping × (smoothed pumping) + gain_canal × (smoothed canal water)

- "Smoothed" means averaged over the past weeks with a weighting curve (a Gamma kernel), because an
  aquifer answers slowly. The curve has two numbers: how fast it reacts and how long it remembers.
- The signs are built in. A gain is written as plus or minus a positive number, so more pumping can
  never raise the simulated head and more rain can never lower it. `tests/test_response.py` checks
  this by nudging each input and looking at the output, for random parameters.
- The three terms add up exactly to the simulation. They are the model's own account of each
  driver's share. That is an account of the model, not proof of what happens in the ground.
- Memory is bounded: the reaction time can be at most one year (two in a sensitivity run), so a
  response cannot turn into a free trend.
- All wells are fitted together, in three ways:
  - **free**: every well has its own numbers, as in Pastas;
  - **pooled**: every well has its own numbers, but they are pulled towards the average of its
    aquifer group, more or less strongly (λ);
  - **shared**: one set of numbers per aquifer group.
- Each run is fitted from 10 different starting points. Their disagreement is one of the results.

### 4. The report (`src/analysis/ladder_report.py`)

Writes `docs/results_ladder_v4.md`: scores; how much each well's drought score, each parameter and
each driver's share change between starting points, beside the same numbers for Pastas; contrasts
with the new measure; and the same-arm band (the difference between two halves of one run's
starting points, which is what noise alone produces).

### 5. Running it

On Kaggle CPU (no training on the laptop): kernel `assilbouzaine/pfe-v4-cpu`, steps `ladder`,
pushed on 2026-11-10: 8 runs × 10 starts. On the laptop only the tests and a 40-step check that the
code runs were executed; those 40-step numbers are not results.

### 6. Housekeeping

- The repository is pushed (it had been 109 commits ahead of GitHub).
- 30 open-access papers were downloaded to `Articles/to_read/`.

## Why

- **Why a ladder.** If the full hybrid is built in one piece and then matches or misses the LSTM,
  nobody can tell which ingredient did it. Each rung adds one thing, so each comparison has one
  explanation.
- **Why start with rungs that need no graph.** They test the riskiest assumption first (is the
  response structure stable at all?) and they could be built in a day from tables that exist.
- **Why bound the memory.** An unbounded slow response is where Pastas lost its footing. A bound is
  an assumption, so it is declared and one run relaxes it.
- **Why the log RMSE ratio.** It reads as a percentage (−0.05 ≈ 5 % less error), it treats a well with
  small swings like a well with large ones, and it has no extreme values. NSE differences ran from
  −2.9 to +2.8 between two neural models.

## What to consider

- **Results are not in yet.** Nothing in this note says the ladder works. When the kernel has
  finished: `scripts/kaggle_cpu.py pull`, then `python -m src.analysis.ladder_report`.
- **What would count as good news:** a drought score at or above the Pastas reference with a much
  smaller change between starting points, and pumping shares that keep their size.
  **Bad news:** stable but poor (the structure is too stiff), or still unstable (sharing by group is
  not enough, and the pumping input itself has to change, review §6.2).
- The bounds (one year, shape up to 3, six years of weights) are Claude's choices, not taken from a
  source. Schorpp et al. 2023 and the Dall'Alba thesis should give physical values; neither is read.
- Sharing gains in metres between wells whose heads swing by centimetres and by metres is crude.
  If "shared" is poor for that reason, sharing in units of each well's own swing is the next variant.
- The aquifer group "other" mixes 19 mountain wells of unrelated units. Pooling them together is
  only a start; the knowledge graph's units are the proper grouping (rung 3).
- These runs use the 3 km pumping sum. Routing by the graph (rung 4) is where the knowledge enters.

## 2026-11-10 (continued): first results of rungs 1–2

Report: `docs/results_ladder_v4.md` (generated). 8 runs × 10 starting points, Kaggle CPU. All of it
is exploratory: the drought period was already examined when the method was designed.

### What the numbers say

| Model (median over the 33 core wells) | validation NSE | drought NSE | drought skill | a well's drought NSE moves between starts by |
|---|---|---|---|---|
| Pastas reference | 0.54 | −0.75 | 0.22 | 1.17 |
| **free** (every well its own numbers) | 0.51 | −0.26 | 0.39 | 1.17 |
| pooled, weak (λ = 0.01; the one chosen on validation) | 0.52 | −0.29 | 0.38 | 0.82 |
| pooled, medium (λ = 0.1) | 0.52 | −0.63 | 0.35 | 0.44 |
| shared (one set of numbers per aquifer group) | 0.11 | −1.52 | 0.07 | 0.27 |
| LSTM, tuned | 0.65 | 0.12 | 0.57 | — |

1. **Fitting all wells together helps.** The free model has about 14 % less error than the Pastas
   reference in the drought (median log RMSE ratio −0.15, interval −0.28 to −0.06). Two halves of
   its own starting points differ by at most 0.07–0.10, so this is more than training noise. The
   structure is the same as Pastas'; what changed is the fitting (all wells at once, the simulation
   error itself as the target, response times bounded at one year).
2. **It is still behind the LSTM**, by about 10 % of error in the median well (the LSTM is better at
   70 % of the wells).
3. **The instability is not cured.** A well's drought score still moves by 1.17 between starting
   points, exactly as in Pastas. Bounding the response times removed the 27-year responses, but the
   *sizes* of the pumping and canal effects still differ between starts (by more than their own
   median). Only 52 % of the wells have a pumping share that keeps its size whatever the start, and
   12 % a canal share.
4. **Sharing steadies the model and costs accuracy.** With medium pooling a well's score moves by
   0.44 and 91 % of the wells have a steady pumping share, but the drought NSE falls to −0.63. One
   set of numbers per aquifer group is steady and poor. The five groups are too mixed, and sharing a
   gain *in metres* between a well that swings by centimetres and one that swings by metres cannot
   work. This was expected (first part of this note) and is the reason for one of the follow-ups.
5. **Compared with BRGM's published model of two of our wells** (Caballero & Ladouche 2015): the
   recharge response at Perpignan has a mean delay of 97 days (63–118 across starts) against their
   89; at Argelès 111 days against their 220, and 173 days when SIM2's effective rainfall is the
   input, as in their model. The pumping comparison I fixed in advance turned out to compare two
   different things (the peak of our response to one week of pumping, 2–5 weeks, with their delay of
   the deepest drawdown after a whole pumping season starts, 75 days), so it shows only that both are
   weeks to months, not years.
6. **Two input choices.** SIM2's effective rainfall as recharge is clearly worse than rain minus a
   fitted share of evapotranspiration (validation 0.45 against 0.51, drought −0.66 against −0.26): a
   fact for the open Gate 3 question about the recharge proxy. Allowing response times up to two
   years is slightly better (drought −0.14), not clearly so.

### A caveat, and the follow-up runs

Training stops when the validation score stops improving. Here that happens early (after 140–330
steps), while the numbers are still close to where each start began. So part of the spread between
starts may be "stopped early at different places", not "several equally good answers". The follow-up
runs (kernel step `ladder2`, pushed the same day; defined in the analysis plan after the results
above were read, and labelled so) separate the two and test two ideas:

- **diagnostic:** the free and the medium-pooled models trained for 3,000 steps with no early stop;
- **permanent + seasonal pumping** (`--pumping split`), the split BRGM used: the part of pumping that
  is the same all year, which only changes between years, and the summer part;
- **sharing in each well's own units** (`--gain-units sd`): gains expressed as a share of the well's
  usual swing, pooled weakly, medium, strongly, and shared.

### What it means for the project

- The main model's core works and is already better than the hydrology reference. That was the first
  thing to find out.
- Its "shares per driver" are **not yet trustworthy** per well: they depend on the starting point.
  Reporting them without that spread would be the "right answer for the wrong reasons" the paper is
  about. Every contribution must be shown with its spread over starts, and the model must be judged
  on both accuracy and stability.
- The LSTM gap (10 %) is the price of the simple structure so far. The next ingredients are meant to
  close it: better grouping from the knowledge graph (rung 3), routing by the graph (rung 4), and a
  small bounded residual.

### Also done on 2026-11-10 (details in `step12_ontology.md`, last section)

- The graph export (`src/kg/export.py`) and its equivalence test.
- `src/models/routing.py`: turns an arm's edges into the weekly input series of each well. Its test
  shows that "baseline" edges reproduce the feature panel exactly, and found a small quirk of the
  baselines: the "3 km" pumping rule uses a 64-sided polygon, so 5 facility–well pairs between
  2,999.3 and 2,999.9 m are left out. Too small to matter; noted, not changed.
- `scripts/kaggle_cpu_run.py`: a kernel's output now holds only the runs it touched, so a pull no
  longer downloads every earlier run again.
