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

## 2026-11-16: the follow-up runs, a correction, and the twin

### Recurring check (CLAUDE.md §7), answered before starting the twin

1. *Which link of the chain does this advance?* Knowledge → model → explanation. The twin is the one
   place where the right answer is known, so it can say whether routing by the knowledge graph helps
   and whether the model's driver shares are right.
2. *Where does dated land use enter?* Not in the twin's base worlds: the canal volume is the only
   agricultural input, as in rungs 1–2. The crop-calendar pumping (reconstruction 3) can become a
   timing variant later.
3. *Observed / inferred / assumed / unknown.* Observed: wells, weeks, weather, facility volumes,
   river and canal series, which weeks have a head. Assumed (the dials): the response shapes, the
   gains, the noise, and which pumps really affect which well.
4. *Evidence vs plan.* The generator and its tests exist and pass. The pilot runs on Kaggle. There is
   no twin result yet.
5. *Does the experiment resolve an open question?* Two. Under which conditions D's routing beats
   C's. And, after today's follow-up results, which fitting protocol gives the right driver shares
   (see below).
6. *Missing from the subject:* unchanged.

### The follow-up runs (pulled today; `docs/results_ladder_v4.md`)

| Model (median over the 33 core wells) | val NSE | drought NSE | drought skill | a well's drought NSE moves between starts by | wells whose pumping share keeps its size |
|---|---|---|---|---|---|
| free, early stopping (10 Nov) | 0.51 | −0.26 | 0.39 | 1.17 | 52 % |
| free, 3,000 steps | 0.48 | −0.43 | 0.26 | 0.70 | 70 % |
| pooled λ = 0.1, early stopping (10 Nov) | 0.52 | −0.63 | 0.35 | 0.44 | 91 % |
| pooled λ = 0.1, 3,000 steps | 0.49 | −0.63 | 0.38 | **0.11** | **100 %** |
| free, permanent + seasonal pumping | 0.51 | −0.31 | 0.34 | 1.11 | 45 % (seasonal part) |
| pooled λ = 0.01, gains in the well's sd | 0.52 | −0.26 | 0.39 | 0.77 | 88 % |
| shared, gains in the well's sd | 0.25 | −0.81 | 0.15 | 0.51 | 61 % |

What it says, in plain words:

1. **Most of the spread between starts came from early stopping.** Early stopping halts training
   when the validation score stops improving, which happened after 140–330 steps, while each start
   was still near its own starting point. Trained for 3,000 steps, the starts agree on the
   predictions and on the recharge response. But in the free mode they still disagree on how strong
   pumping and canal water are. With one set of numbers per well, the data cannot pin those two
   down: this is the equifinality the review found in Pastas, and it is real, not a training artefact.
2. **A correction to the section above.** On 10 Nov I wrote "fitting all wells together helps". Trained
   to the end, the free model is no better than Pastas (log RMSE ratio −0.03, interval −0.18 to +0.23,
   instead of −0.15). What helped was early stopping itself. Stopping early keeps every well's numbers
   close to the common starting values, so it works like a pull towards an average model (a
   *shrinkage*). That is a legitimate way to regularise a model. But it is not the structure, and it
   makes each well's numbers depend on where its start happened to be.
3. **Pooling, trained to the end, pins everything down.** All starts agree on every number, and every
   core well keeps its pumping share. Its accuracy is that of Pastas, behind the early-stopped free model.
4. **So accuracy and stability trade off.** Which one gives the *right* driver shares? On real data
   nobody knows the true effect of pumping, so the real data cannot say. The twin can, because it
   knows the truth. The fitting protocol of the main model is now a Gate 3 point, to be informed by the
   twin (analysis plan §14 item 18, last results paragraph).
5. **Two smaller results.** Splitting pumping into a permanent and a seasonal part (as BRGM did) brings
   no gain. Expressing gains in units of each well's own swing helps pooling (as accurate as free,
   steadier pumping share), but one response per aquifer group stays poor.

### The twin: what was done

`src/models/twin.py` builds a **world**: the real wells, weeks, weather, pumping volumes, rivers, canal
and the real pattern of missing heads, with *invented* heads. Each invented head is the sum of known
responses to recharge, pumping, river and canal, plus slowly varying noise. We choose which pumps truly
affect which well (the *truth graph*). The model never sees it. Then the same model is fitted three
times on the same world, and the only difference between the fits is the routing:

- **C**: the distance rules (every pump within 10 km);
- **D**: the knowledge graph's edges (the pumps attributed to the well's unit within 5 km, plus the
  others as a separate "unattributed" input);
- **T**: the truth's own routing, which the real data never have. It is the ceiling: how much routing
  could help at most.

Because the truth is known, each fit gets more than an accuracy score. We can measure how far its
pumping share is from the true one, whether its response time is right, and whether it predicts
correctly what happens if the true pumps are cut by 20 %.

Two dials say how wrong the graph is: **ε**, the share of its pump links that are false, and **u**,
the share of the true pumping it misses. The map over these dials says where routing by the graph
beats routing by distance. The real data sit near ε ≈ 0.1–0.4, u ≤ 0.66 (analysis plan item 19).

**Design changes made today, before any world existed** (analysis plan item 19, amendment of
2026-11-16):

- **The oracle T was added.** The plan needed a "truth-informed fit" (score 6) but the code had none.
- **ε now moves the truth, not the graph.** The draft replaced some of D's links by wrong ones. That
  was wrong in two ways. First, the numbers that place the real data on the ε axis (36 of 39 links
  right; 63 %) measure *false* links only, while a replacement also *removes a true* link, which the
  u dial already covers. Second, a test showed that the replacement could not reach its own dial
  (0.41 instead of 0.5), because some wells have too few spare pumps nearby. Now D stays exactly the
  exported graph, and the truth drops a share ε of D's links. It also means the model sees exactly
  the tables the real experiment will use.
- **Slice G was added.** The truth takes its recharge, river and canal routes from D, so D is right
  about them *by assumption*. Slice G gives the truth C's routes instead, and the two together
  bracket that assumption.
- **The converged pooled model joins the pilot**, because of the follow-up results above.
- **Smaller points:** π is defined on the contribution variances (and the share of the head it really
  explains is recorded: about 0.2 for π = 0.3, because summer pumping and the dry season move
  together); the noise starts from its steady state; the hidden variation of variant I has mean one.

**Tests** (`tests/test_twin.py`, all pass): the generator and the model compute the same thing for the
same parameters (relative difference 4e-7), so a base world is a world the model *can* fit exactly.
The variance shares, signs and noise ratio are exact. ε is unbiased (0.250 for 0.25 over 30 seeds).
The truths are nested along the dials. Variants S, I, O, G and the independent timing do what they
should. The whole path runs end to end.

Two bugs were found and fixed while writing the generator: it read a column the panel does not have
(the weather cell), and the "independent timing" variant would have silently deleted the volume of
pumps that opened after 2019.

**The pilot is on Kaggle** (`scripts/run_v4_cpu.sh` step `twin_pilot`): 3 worlds in the base cell
(ε = 0.1, u = 0.3, π = 0.3, ν = 0.25), arms C, D, T, three learners (free and pooled λ = 0.01 with
early stopping; pooled λ = 0.1 for 3,000 steps). It measures the run time and gives a first look.
The settings of the grid (12 cells × 20 worlds) are chosen after it, from synthetic heads only.

### Why

- **Why an oracle.** Without it, "D beats C by 3 %" cannot be read: is 3 % most of what routing could
  give, or a small part? T gives that scale in every world.
- **Why the twin before any real-data arm.** On real data a difference between C and D is the end of
  the story. On the twin we know whether the difference comes with right driver shares or wrong ones,
  which is the paper's question ("right for the right reasons").

### What to consider

- In the base cell, 9 core wells get true pumping although the graph attributes them none (u draws it
  from their unattributed pumps). For these wells D can only use its unattributed input.
- The twin's generator shares the model's additive structure, except in variants O and S. A good twin
  score is a statement about these generators, not about the aquifer.
- After the pilot: a report script (`src/analysis/twin_report.py`), then the grid and the slices on
  Kaggle (about 400 worlds; the pilot's timing says how many kernel sessions).
