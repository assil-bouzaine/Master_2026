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

### Later the same day: the RQ2 settings, a faster convolution, the pilot pushed again

- **The RQ2 settings are declared and coded** (analysis plan item 19, amendment point 9, written
  before any RQ2 run). *Hard*: the signs are built in, as in every rung so far. *None*: every gain is
  a free number. *Soft*: free gains plus a penalty equal to the share of the well's variance carried
  by contributions with the wrong sign. That is Ross et al.'s "right for the right reasons" penalty
  (arXiv:1703.03717), in the form that suits a model whose response to a sustained change has the
  sign of its gain. It is in the same units as the error, so λ_s = 1 means a wrong-signed
  contribution costs as much as an error of the same size. Its tests check the penalty by hand, check
  that it pulls a wrong gain towards zero, and check that a short training with it leaves fewer wrong
  signs than without it.
- **The convolution is now done by FFT** (`--conv fft`): the same contributions and gradients to
  float precision (largest difference 4e-7), and **12.6 times faster** on the real shapes (23 ms
  instead of 291 ms per training step, one thread). Almost all of the model's time was this
  convolution. The default stays the old one, so the runs of rungs 1–2 keep their numbers. The twin
  and every later run use FFT.
- **The pilot was pushed again** with the fast convolution (Kaggle kernel version 10), so that it
  measures the code the grid will use. The first push (version 9, old convolution) would have needed
  hours for its 3,000-step fits. The new push also gives a first look at RQ2 on the same three worlds
  (none and soft, on arms D and T).

### The pilot's results (pulled 2026-11-16 ≈ 14:00; `docs/results_twin_v4.md`)

Three worlds in the base cell (ε = 0.1, u = 0.3, π = 0.3, ν = 0.25). Three worlds are enough to size the
run and to see that every score works; they are **not** enough for any conclusion. Every number below
is a median over the three worlds.

**Run time (what the pilot was for).** The whole pilot took 18 minutes on Kaggle (9 processes on 4
CPUs). One world costs about 8 CPU-minutes for both protocols when nothing else runs. The grid and the
slices (about 400 worlds) therefore fit in about two Kaggle sessions. By the rule written before the
scores were read (item 19, amendment point 7), both protocols go on every cell and slice.

**A first look at the scores (exploratory):**

| | arm C (distance) | arm D (graph) | arm T (truth) |
|---|---|---|---|
| drought NSE, free | 0.63 | 0.64 | 0.70 |
| error against C (log RMSE ratio) | — | −0.061 | −0.056 |
| pumping recovery error (sd units; 0 = exact), free | 0.23 | 0.24 | 0.18 |
| pumping recovery, pooled λ = 0.1 × 3,000 steps | 0.30 | 0.29 | 0.24 |
| error of the −20 % intervention, free | 0.24 | 0.44 | 0.27 |

- **D is about 6 % more accurate than C, as much as the oracle.** But its pumping share is no closer to
  the truth than C's. D gets the river and canal shares right (0.11 and 0.00 against C's 0.14 and
  0.06), and those are D's by assumption in the base world. So part of D's gain may come from relations
  the dials do not control. Slice G (the truth taking C's routes for them) will measure how much.
- **Early stopping recovers pumping better than converged pooling** (oracle: 0.18 against 0.24) and is
  more accurate. On the real data, too, it was the more accurate protocol. If the grid confirms this,
  stopping early is not just luck near the starting values, and the converged model's stability
  comes at the price of a worse pumping share. (One reason may be the generator itself: its wells
  differ from their group by design, which pooling resists.)
- **D answers the intervention worse than C** (relative error 0.44 against 0.24). D splits pumping
  into its attributed pumps and the rest, each with its own gain, and the cut falls on both. Worth
  watching in the grid.
- **RQ2.** With free signs, 19 % of D's gains (9 % of the oracle's) have the wrong sign. The soft
  penalty at λ_s = 1 barely changes that (17 %), and the hard signs give D its best pumping share and
  the right sign of the intervention in every well (85 % with free signs).
- **No world has "wrong reasons"** (score 6) in this easy cell, as expected.

**Next:** the grid and the slices on Kaggle (both protocols), then the knowledge-value map.

## 2026-11-18: the controls of arms E and F, rung 3, rung 5's groundwork, a citation audit

Assil asked today for a new way of working: Claude leads, and two Codex workers in tmux windows take
the well-specified pieces (GPT-6.2-Sol at high effort for the simple tasks, GPT-6.1-Sol at maximum
effort for the simplest). Claude writes each brief with the design fixed, reviews the code line by
line, re-runs the tests and commits what passes. Every commit made from a worker's code says so.

### Recurring check (CLAUDE.md §7; answered late: the session started without it)

1. *Which link of the chain does this advance?* Knowledge → model. The control graphs make a D vs C
   result readable (meaning of the edges, or only their locality and number?). Rung 3 asks whether the
   graph's facts describe wells well enough to carry responses to wells the model never saw.
2. *Where does dated land use enter?* Still nowhere in these pieces. Set B's facts hold no crop
   information (crop demand stays in arm B's ablation, Gate 3 point 11). The land-use thread waits for
   Assil's AGROVOC gold set and the Earth Engine login.
3. *Observed / inferred / assumed / unknown.* Set A's facts are observed (depth, altitude, stack
   position, artesian share). Set B's are inferred by the graph's rules (attributed pumps, recharge
   cells, river kinds, canal). The control graphs are wrong on purpose (that is their job).
4. *Evidence vs plan.* The controls are built and tested; rung 3 is coded and tested on toy worlds;
   no real-data run exists (it waits for the twin, Gate 3 and the tag). The twin's grid is running on
   Kaggle (kernel version 12).
5. *Does the next experiment resolve an open question?* Yes, two: whether D's gain (if any) is
   semantic or local (E_distance), and whether facts beat name tags on held-out wells (rung 3 against
   the controls of Heudorfer et al. 2024).
6. *Missing from the subject:* unchanged (satellite rule, alignment results, explanations, dashboard).

### What was done

- **The twin's grid, second Kaggle session.** Version 11 ended at its 11-hour budget with 206 of the
  240 grid worlds; the slices had not started. Pulled, and pushed again as version 12 (same steps,
  resumes from the pulled worlds). The bundle carries the **same export as version 11** (release
  12:41 UTC of 2026-11-16, put back in place for the push and restored afterwards), so every world of
  the grid sees identical tables; the code differs from version 11 only by a comment in
  `src/kg/export.py` and the new `src/kg/oops_scan.py`.
- **Control graphs of arms E and F** (`src/kg/controls.py`, `tests/test_controls.py`; plan §14 item 20;
  worker A, two review rounds). E_degree keeps every degree (Maslov–Sneppen swaps), E_distance keeps
  the length of every edge as far as the sources allow (one of the five closest lengths), F_random
  keeps D's number of edges, F_complete links everything. Five draws each, bound to the export by its
  hashes. Review findings fixed: lengths now follow D's own convention (the graph stores points to
  0.1 m, so D's pumping and well-link distances are reproduced to 1e-12 m) and an edge that a control
  happens to keep carries exactly D's attributes. What the controls can and cannot do: E_distance
  keeps pumping lengths within a median 45 m, but rivers (five gauges) move by a median 13 km and
  recharge cells (8 km grid, the near cells are already D's) by 7 km, so it is a locality control
  mainly for pumping. The canal (one source) cannot be rewired.
- **`--arm` accepts the controls** (`E_degree:<draw>` …, `src/models/routing.py`), and a control's
  export hashes enter the run fingerprint.
- **Rung 3** (`src/models/response.py --statics A|B`): parameters = group mean + f(facts) + a pooled
  deviation. A held-out well keeps its deviation at zero, so its responses come from its group and its
  facts only. On a toy world whose gains vary with one fact, the facts carry the responses to the
  held-out wells (NSE 0.98–1.00, against −3.6 and 0.86 with the group mean alone). The fact table
  (`src/models/statics.py`) is worker B's current task.
- **Rung 5's groundwork** (`src/models/message.py`): the neighbours' facts, averaged over the arm's well
  links (GraphSAGE's mean), become extra inputs of rung 3's map. Arm C links every well, arm D 38 of
  65. The per-regime depth threshold of D's links is worker A's current task.
- **Citation audit** (`src/analysis/citation_audit.py` → `docs/literature/citation_audit.md`; worker
  B, one review round). Twelve identifiers cited in the code or docs were missing from the reading list;
  each was resolved on Crossref today and added. One line-wrapped DOI remains in an ontology comment
  (`ontology/lulcw-meta.ttl`), to join at the next ontology release.

### Why

- **Why controls before any real-data arm.** A D vs C difference alone mixes three things: which
  wells get which inputs (meaning), how far the inputs come from (locality) and how many inputs each
  well gets (density). The controls take them apart, and they must exist before the first real
  number so that nobody chooses them after seeing it.
- **Why the fact table is declared now.** Static facts can act as name tags (Heudorfer et al. 2024).
  The table, its training-window rule and the two name-tag controls are fixed before any rung-3 run.

### What to consider

- If the per-regime depth threshold keeps fewer well links than D's 47 pairs, the well-link controls
  of rung 5 must be drawn from the kept links of each regime, not from the full set (to do when
  `--message` is wired into the response model).
- The workers cannot write into `.agents/` (Codex protects it): their reports go to
  `results/_agents/reports/`.

### Later the same day: the workers' tasks T03–T07 (each reviewed, re-tested and committed)

| Task | Worker | What it delivered | Review |
|---|---|---|---|
| T03 | B (GPT-6.1-Sol) | `src/models/statics.py`: fact sets A and B, the training-window rule, standardisation, name tags and shuffled facts | one fix (T03b): the source's altitude −999 for `10915X0395/PZ` is "unknown", not an altitude; it had shifted every well's standardised altitude |
| T04 | A (GPT-6.2-Sol) | `src/models/depth_threshold.py`: the per-regime depth threshold of D's well links | accepted unchanged. **Result:** in every regime (R1, the five folds, both R3 windows) only "no threshold" has the 10 qualifying pairs the rule asks for (50 m: at most 8), so D keeps all 47 pairs; R1 medians 0.517 (50 m) and 0.511 (none) |
| T05 | A | `paper/`: the EMS skeleton (headings and TODO notes only) and `fetch_bib.py` | accepted; Claude anchored the `tools/` ignore rule and fetched the bibliography online: 104/104 entries (one thesis record corrected by hand from its repository page) |
| T06 | B | `--pumping-reconstruction 1/2/3` for every routed arm | accepted: default arrays bit-identical; annual totals of 2,137 facilities conserved to 4e-16 |
| T07 | A | `src/analysis/arms_report.py` + `configs/phase4_contrasts.json`: the reading of Phase 4's contrasts | accepted; its development run on the ladder runs matches the ladder report to 1e-12 |

Claude's own work in the afternoon: rung 5 wired (`--message`; per-regime links, controls drawn
from the links D keeps), `--arm baseline` (the panel's rules as edges, so arms A and B get the
reconstructions), `docs/phase4_runs.md`, Gate 3 points 18–21, the twin map's reading rules (a)–(f) as
code (`twin_report.reading`, tested on hand-made tables only, before the grid could be read), and the
exports of the two pump-link sensitivities (confident-only: D has 134 pumping edges on 26 wells;
all-links: 1,839 on 54; main: 434 on 43).

**What to consider**
- The twin's next Kaggle push must carry the 12:41 export again: it is kept in
  `results/_kaggle_cpu/twin_export_release1241/`. Copy it over `data/processed/kg/export_v4_main/`
  (after moving the 13:54 export aside, outside `data/processed/kg/`), run `kaggle_cpu.py push`, and
  put the 13:54 export back as soon as `results/_kaggle_cpu/dataset/cpu_bundle.zip` is rewritten.
- Block B7 needs two small options before Phase 4: a flag for arm D's unit-wide recharge relation
  (routing already accepts `recharge="recharge_unitwide"`) and soil drainage (DRAINC, in the forcing
  table) as a recharge input.
- The Codex account's five-hour window was about two-thirds used by 13:00 with both workers busy.

## 2026-11-20: an external review checked and fixed; the twin's grid read

Assil started the session in the herdr app (not tmux) and asked for the same way of working: Claude
leads and reviews, two Codex workers take the well-specified pieces. The workers now run as herdr
terminals started by Claude (`hc run --bg`, tabs of the Master_2026 space): cxa = GPT-6.2-Sol at high
effort (moderate tasks), cxb = GPT-6.1-Sol at maximum effort (the simplest). He also asked to check
`astra_review.md`, an external review of commit `0171297` (17 points), and to correct what is useful.

### Recurring check (CLAUDE.md §7)

1. *Which link of the chain does this advance?* Knowledge → model → explanation: the twin says when
   the graph makes the model right for the right reasons, and the review's fixes keep the Phase 4
   reading honest (no incomplete experiment can be read as a result).
2. *Where does dated land use enter?* Nowhere new today (it waits for the AGROVOC gold set and the
   Earth Engine login).
3. *Observed / inferred / assumed / unknown.* The twin's results are synthetic (assumed generators);
   the river gap fix changes an observed input's fill (an assumption) on 8 validation weeks.
4. *Evidence vs plan.* The grid is evidence about the learner under the generators, not about the
   aquifer; no real-data arm exists yet.
5. *Does the next experiment resolve an open question?* Yes: RQ2's three settings on the same worlds
   with the per-well score 5 (kernel version 13), and the slices O and S, where wrong reasons can
   appear.
6. *Missing from the subject:* unchanged (satellite rule, alignment results, explanations, dashboard).

### The review, point by point

Every point was checked against the code before any change; all held.

| Point | What was wrong | Fixed by | Commit |
|---|---|---|---|
| 1 | Score 5 cut the union of all wells' true facilities, not "every true-edge facility of a well" | Claude: per-well cut (one pass), union kept as "plain-wide"; RQ2 also fits hard | `3bad792` |
| 2 | River gaps > 8 weeks partly interpolated toward their far end (8 validation weeks of the Têt leaned on a test observation) | Claude: rule "declared" for every real-data arm; "legacy" kept for the baselines' panels and the twin | `3bad792` |
| 3 | A one-start `predictions.parquet` could be read as a ten-start Phase 4 result | cxa (T12): aggregates rebuilt from exactly seeds 0–9 | `5ab58f1` |
| 4 | A missing test shrank its Holm family | cxa (T12): families kept whole, pending until complete | `5ab58f1` |
| 5 | Score 6 reported as a median of 0/1 flags | Claude: k of n worlds | `3bad792` |
| 6 | Twin verdicts on incomplete grids and on ties | Claude: complete cells only, paired worlds, ties counted, strict majority | `3bad792` |
| 7 | Response predictions decoded with the raw sd (only AIGUAN, not core) | cxb (T11), cxa (T12) | `f2cd482`, `5ab58f1` |
| 8 | Reported lags are a·n, not the implemented weekly kernel's mean | cxb (T13): implemented mean and peak beside BRGM (review's numbers confirmed) | `945b322` |
| 9 | Duplicate predictions counted twice; empty scores crashed | cxb (T09) | `b57b837` |
| 10 | A resumed twin cell accepted worlds of another experiment | Claude: identity check on resume and in the report | `3bad792` |
| 11 | Kaggle runs looked successful after failures | cxa (T10) | `394da63` |
| 12 | A pull could delete the only copy of partial work | cxa (T10): staged pull + cumulative state | `394da63` |
| 13 | The bundle lacked Phase 4 inputs | cxa (T10) | `394da63` |
| 14 | Parallel twin workers lost manifest records | Claude: file lock + atomic replace (the test fails without it: 31 of 40 records kept) | `3bad792` |
| 15 | A first naive run wrote persistence skill as missing | cxb (T09) | `b57b837` |
| 16 | A Chronos-2 smoke run could become the full forecast | cxb (T11) | `f2cd482` |
| 17 | An offline bibliography refresh could empty `refs.bib` | cxb (T09) | `b57b837` |

### The twin: kernel version 12 pulled, version 13 pushed

- Version 12 (pushed 11-18) ended at its budget: **grid complete (240 worlds)**, slices 146 of 160,
  RQ2 not started. Pulled (the previous download kept in `results/_kaggle_cpu/output_v11_backup`).
- The Kaggle wheel dataset was refreshed (33 wheels: T10 added rdflib, pyoxigraph, requests and their
  dependencies, checked on Kaggle) and dry-run on a clean Python 3.13 (install and versions only).
- **Version 13 pushed 2026-11-20 ≈ 12:55 CET**, steps `twin_slices` (the 14 missing slice worlds,
  then `twin_rq2`: hard, none and soft on arms D and T, base cell and 8 slices × 20 worlds), with the
  12:41 export again (swapped in for the bundle, the 13:54 export restored right after). About 8 h.

### The grid's reading (`docs/results_twin_v4.md`, rules fixed before; synthetic heads only)

- **Accuracy barely moves.** D / C (log RMSE ratio, drought, median over 20 worlds) is between
  −0.012 and +0.009 under early stopping and between −0.025 and −0.002 under converged pooling. Even
  the oracle T, which routes exactly the truth, gains only 2–9 %. No cell "pays" (rule a), the
  bracket cells included (rule d): a real-data D vs C accuracy contrast without a detected gain is
  the expected outcome, not a failure of the graph.
- **The graph's value shows in the explanation, and only under converged pooling.** There D recovers
  the true pumping contribution better than C in 82 % of the worlds and in every cell (rule c: right
  reasons); under early stopping it does so in 25 % of the worlds (rule c: "D more accurate for other
  reasons" where D/C < 0).
- **Rule (e) picks early stopping** (lower absolute pumping recovery error of D in 8 of 12 cells,
  +0.03 NSE). Gate 3 point 1 now proposes both, with declared roles: early stopping for the accuracy
  contrasts, converged pooling for the explanation claims.
- **Score 6 never fires:** 0 of 240 worlds have "wrong reasons" (recovery errors 0.1–0.4, the
  threshold is 0.5). Inside the model class there is no positive case for the shortcut tests; slices O
  and S will say whether one appears outside it.
- Slice G (16 worlds so far): when the graph is wrong about recharge, rivers and canals, D loses 5–7 %
  against C: those relations weigh more on accuracy than the pumping routing does.

### Why

The review found real defects, and the most important ones could have changed what we report: the
intervention score measured something other than its definition, and the Phase 4 report could have
classified an incomplete experiment. Fixing them before the twin's grid was read, and before any
Phase 4 run, keeps the plan's "rules first, results second" order intact.

### What to consider

- The twin's scores 4 (lags) compare a·n with a·n: like with like, but not the implemented delay;
  T13 gives the ladder's comparison with BRGM the implemented mean and peak.
- The baselines of record keep the old river fill (8 validation weeks of one gauge): documented in
  §7b and item 21, not re-run.
- `selection.json` now guards Chronos-2 caches: Colab session 2's Chronos folders (still on Drive)
  have none, so a *resumed* Chronos run in those folders stops by design; scoring them is unaffected.
- Codex account: about 70 % of the five-hour window left at 13:00 with both workers busy since 11:30.

### Later the same day: the workers' tasks T08, T13, T15 (each reviewed, re-tested and committed)

| Task | Worker | What it delivered | Review |
|---|---|---|---|
| T08 | A (GPT-6.2-Sol) | Phase 4 steps `p4_B1` … `p4_B7` in `scripts/run_v4_cpu.sh`, locked until `P4_CONFIRMED=1`, dry-run mode | accepted; dry runs repeated: 364 of 366 fits + 51 fold assemblies printed with the declared names (B7 waits for its options) |
| T13 | B (GPT-6.1-Sol) | `response.kernel_moments`, the ladder's comparison with BRGM on implemented delays | accepted; only the lag table of `docs/results_ladder_v4.md` changed |
| T15 | A | `kaggle_cpu.py push --env KEY=VALUE` (how `P4_CONFIRMED` and the `P4_*` settings reach the kernel), the R2 assembler's scale for response seeds | accepted |

Open: T14 (A, running): the two B7 options (`--recharge-relation recharge_unitwide`, `--recharge drainc`);
then B7's two commented commands in `run_v4_cpu.sh` can be enabled.

### End of the session (2026-11-20 ≈ 14:10 CET): T14 and T16, then stop

| Task | Worker | What it delivered | Review |
|---|---|---|---|
| T14 | A (GPT-6.2-Sol) | B7's options: `--recharge-relation recharge_unitwide` (960 edges for 59 wells against 193 for 54) and `--recharge drainc` | accepted; every existing configuration bit-identical (arrays, predictions from the same start, config and schema files). Claude then enabled B7 in the Phase 4 steps and added `P4_RECHARGE` |
| T16 | B (GPT-6.1-Sol) | `scripts/run_tests.py`: every test module in its own process, times and logs in `results/_tests/` | accepted; **42 of 42 modules pass** (23 min) |

Kaggle kernel version 13 (the twin's last session) was still running at the end. Assil asked to stop
after the workers' tasks: nothing new was started.

### Evening session (2026-11-20, 18:00-19:05 CET): the black box on D's edges, paper sections and figures, test 2's threshold

Assil: "continue as the leader of the two Codex workers, spawned here in herdr, not inside tmux".
Claude ran in herdr terminal t8 (space `~`); the workers were relaunched as t9 (`cxa`, GPT-6.2-Sol
high) and t10 (`cxb`, GPT-6.1-Sol max), both `codex --no-daemon`, each a direct child of
herdr-core with no `TMUX` in its environment (checked).

| Task | Worker | What it delivered | Review |
|---|---|---|---|
| T17 | A | `src/models/taccari.py --edges D`: the Taccari ST-GNN on arm D's edges (51 cells, 5 gauges, 178 facilities, 64 per-well unattributed nodes, the canal, well links; 363 nodes vs 208), the export's provenance in the fingerprint; Gate 3 point 21 | accepted; distance graph bit-identical; Claude added a guard (`--edges D` refuses run folders not made with it) and its test |
| T18 | B | `paper/tools/kg_tables.py` → `paper/tables/kg_*.tex` (classes by theme, coverage of arms C and D, 21 macros) | accepted; one label reworded ("triples derived by the rules") |
| T19 | A | `paper/tools/fig_study_area.py` → figure 1 (units typed by `unit_class`, wells, gauges, facilities, canals, rivers, inset) | accepted; river labels moved into the plain in T21 |
| T20 | B | `paper/tools/data_tables.py` → `paper/tables/data_*.tex` (sources, periods, 51 macros) | accepted; "59 % of rows imputed" replaced by which weeks are filled |
| T21 | A | `paper/tools/fig_twin_map.py` → the twin's knowledge-value map (D/C, T/C, right reasons; 2 protocols) | accepted; matrices agree with the morning's reading |
| T22 | B | `paper/tools/fig_influence.py` → one real Influence record with all its 21 triples and both attributions | accepted |
| T23 | A | `paper/tools/fig_periods.py` → observed SGI of the core wells; the recovery rule recomputed: December 2025 | accepted |
| T24 | A | `paper/tables/twin_numbers.tex` (34 macros of section 6.1) | accepted; section 6.1 now uses them |

Claude: paper sections 1 (introduction), 2 (study area and data), 3 (the knowledge graph), 4 (the
models), 5.1 (the twin) and 6.1 (the twin's map) drafted, every claim checked against the notes
(several wordings corrected before each commit); 12 references added (9 by DOI on Crossref, refs.bib
114; W3C/OGC documents, data services and LightGBM by hand in `paper/refs_standards.bib`, each page
opened); bibliography switched on. BD LISA (503 that day), BD TOPO and the RPG are still to cite.
**Test 2's flag threshold fixed before kernel version 13 is pulled** (analysis plan item 22, Gate 3
point 5): τ = the 95 % quantile of the grid's seed disagreement per arm and protocol; the twin
report computes τ and the detection and false-alarm rates (tested on hand-made tables only).
Quick test suite at `2256f83`: 43 of 43 pass (the 4 slow modules skipped).

Correction: the oracle's ceiling is a 2-8 % RMSE reduction (log T/C −0.021 to −0.086, i.e. 2.1-8.3 %),
not "2-9 %" as said in the morning (that rounded the log ratio).
Codex account at 19:00: 41 % of the five-hour window left; no new worker task until kernel
version 13 is pulled.
