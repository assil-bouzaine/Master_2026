# Gate 3: the decisions to take (draft of 2026-11-16)

Gate 3 is the supervisor's review of the knowledge graph and the experiment plan, before the plan is
frozen with a git tag and Phase 4 (the main model and its comparisons) starts. This sheet gathers
every open point of `docs/analysis_plan.md` §14 (items 13–19) and of the step notes in one place.
Each point gives the question, the options, Claude's recommendation with its evidence, and where the
details are. **Twin** marks the points whose answer should wait for the twin's grid (running on Kaggle
since 2026-11-16, read in `docs/results_twin_v4.md` when it is pulled).

Nothing here is decided until Assil decides it. The recommendations are Claude's.

## Summary

| # | Decision | Recommendation | Waits for |
|---|---|---|---|
| 1 | Fitting protocol of the main model: early stopping or training to convergence with pooling | Early stopping, provisionally; converged pooling as a sensitivity | Twin |
| 2 | Rungs 3–5 of the ladder; routing (rung 4) as the primary form of D vs C | Confirm | — |
| 3 | Smallest effect of interest for the primary contrasts | A median RMSE reduction of 5 % (log ratio −0.05), with 10 seeds | — |
| 4 | Permanent + seasonal pumping as the main structure | No: keep it as a sensitivity | — |
| 5 | The twin's design (item 19 and its amendment) | Confirm and freeze with the tag | Twin (pilot done) |
| 6 | RQ2: the weight λ_s of the soft sign penalty on real data | A declared grid {1, 10, 100}, chosen on validation | Twin |
| 7 | Recharge: does "effective rain raises the head" constrain the model? PE or max(PE, 0)? | Yes, with PE as is; max(PE, 0) as a sensitivity | — |
| 8 | Rivers: constrain the sign where eligible (3 wells)? body-level statements? conflicting directions? | Constrain only where eligible; body-level statements stay ineligible; a conflicting direction keeps the sign eligible | — |
| 9 | Canals: eligibility by the source's wording or by its method; constrain? | Method criterion; no hard canal constraint, a soft-prior sensitivity instead | — |
| 10 | Proxy adequacy: gauge discharge for river stage; summed canal diversions for canal return | Gauge discharge adequate with its caveat; canal diversions weak | — |
| 11 | Crop demand as an influence: its pathway and no double counting | Not in Phase 4's main runs (LU-4 found no information); keep in arm B's ablation | — |
| 12 | Export: drop weather cells holding under 0.001 of an outcrop | Drop them | — |
| 13 | Export: one edge per driver and well, eligible only if every path agrees | Confirm (implemented 2026-11-10) | — |
| 14 | Hypothesis families and tests (§10) | RQ1 = {B vs A, D vs C}, RQ2 = {soft vs none, hard vs none}, one test each on the log RMSE ratio | — |
| 15 | Ontology scope: CQ9, 13, 14, 16 | Minimal fixtures or future work; the 7 SHOULD/COULD reviewed by Assil | Assil's CQ review |
| 16 | Reporting: Chronos-2 and the forecast task; Pastas sensitivity rows; a time-reversed test; EuroCrops; text extraction | Thesis only for the first three; text extraction scored on the 32 curated statements; EuroCrops only if time | — |
| 17 | Public repository before the paper | Ask the supervisor and SAVE Water | Supervisor |

## 1. The model

**1. Fitting protocol of the main model (Twin).** On the real data (`docs/results_ladder_v4.md`), the
response model stopped early on the validation score is the more accurate one, but its starts
disagree on the size of the pumping effect; pooled towards the aquifer group and trained to the end,
every start tells the same story, at the accuracy of the Pastas reference. The first look at the twin
(3 worlds) found that early stopping also recovers the true pumping effect better. *Options:* early
stopping (report the spread over starts with every explanation); converged pooling (stable, less
accurate); both, one as the main protocol and one as a sensitivity. *Recommendation:* early stopping,
unless the twin's grid shows that converged pooling recovers the contributions better across the
cells. Details: analysis plan item 18 (follow-up results), item 19 amendment point 7.

**2. Rungs 3–5 and the routing contrast.** The main model is built as a ladder: (1) one response
model for all wells, (2) pooling by aquifer group, (3) parameters predicted from the graph's facts
about each well, (4) inputs routed by the graph's edges (arm D) or by distance (arm C), (5) message
passing between wells. *Recommendation:* confirm, with rung 4 as the primary D vs C contrast (only
the routing changes) and rung 3 as the control "statics already explain it". Item 18.
*Concrete proposal for rung 3 (to confirm or change):* each well's response parameters = its aquifer
group's mean + a small learned function (linear, or one hidden layer of 16 units) of standardised
facts about the well that exist today: from the dataset, investigation depth (log; missing → 0 with a
flag), altitude, the unit's position in the BD LISA stack, the artesian share of the training window;
from the graph's export, the attributed share of the pumping volume within 5 km, the attributed volume
(log), the number of recharge cells, the kind of river edge (on outcrop, over cover, none) and the
canal edge. Per-well deviations stay, penalised as in the pooled mode. Its main test is the
leave-wells-out folds: if the facts predict a held-out well's responses, the graph carries information
about the wells, not only labels (the name-tag control of Heudorfer et al. 2024 is run beside it).

**3. Smallest effect of interest.** The primary measure is the per-well log RMSE ratio in the drought.
Two trainings of one model differ by up to ±0.07 (the same-arm band of 5-seed halves), so a smaller
effect can only be seen with more seeds. *Recommendation:* −0.05 (5 % less error), with the 10 seeds
already approved; a contrast is then "detected", "compatible with no effect larger than the
interval's end", or "undecided". Item 18.

**4. Pumping structure.** BRGM's model splits pumping into a permanent and a seasonal part
(Caballero & Ladouche 2015). The follow-up run found no gain from it (log RMSE ratio +0.025 against
the single pumping input). *Recommendation:* sensitivity only. Item 18.

**5. The twin's design (Twin).** Written before any real-data arm is scored: synthetic heads on the
real wells and inputs, a truth graph apart from the learner's, dials for false links (ε), missed
pumping (u), pumping signal (π), noise (ν), and variants (pumping timing, hidden variation, an omitted
driver, responses the model does not have, the graph wrong on rivers, canals and recharge).
*Recommendation:* confirm and freeze it with the tag; the grid is computed from it. Item 19.

**6. RQ2's soft penalty (Twin).** The soft setting adds λ_s × the share of each well's variance
carried by contributions of the wrong sign. In the twin's pilot, λ_s = 1 barely reduced the wrong
signs (17 % instead of 19 % of the gains). *Recommendation:* for the real data, declare a grid
{1, 10, 100} and choose λ_s on validation; keep λ_s = 1 in the twin as declared. Item 19 point 9.

## 2. The constraints (what the knowledge forces on the model)

Only the pumping sign is approved (abstraction never raises the head). Every other sign is "eligible"
in the graph where its evidence allows, and constrains nothing until it is approved here
(`configs/constraint_decisions.csv`).

**7. Recharge.** SIM2's effective rain (PE) stands in for recharge; the sign "more effective rain does
not lower the head" is eligible on every recharge edge. PE can be negative (a dry week): a linear
response then lowers the head, as Pastas does with rain minus evaporation. *Options:* constrain or
not; PE as is or max(PE, 0). *Recommendation:* constrain, with PE as is (negative in dry weeks, like
the rain minus evaporation of the hydrological reference), max(PE, 0) as a sensitivity. Note: on the real data, PE was a clearly worse
recharge input than rain minus a fitted share of evapotranspiration (validation NSE 0.45 against 0.51),
so the recharge proxy of the main runs should be decided together. Items 15, 18.

**8. Rivers.** The flux between a river and its aquifer grows with the river stage whatever its
direction (Harbaugh 2005, doi:10.3133/tm6A16), so "a higher river does not lower the head" is eligible
where the river runs on the well's own unit or a source documents an exchange with that unit: 3 wells
today (MILLAS C2-1 and two wells at Corbère). *Questions:* (a) constrain those 3? (b) may a statement
about a whole groundwater body, localised by the outcrop, make a sign eligible (BARQUA, 10915X0395/PZ,
10972X0094/111111)? (c) may a conflicting documented direction (the Têt above the Comelade: losing in
one source, gaining in another) leave the sign eligible? *Recommendation:* (a) yes; (b) no, a body-level
sentence is not evidence about each unit; (c) yes, because the sign concerns the stage, not the
direction. Items 16, 17.

**9. Canals.** Canal return is eligible for 2 wells, where a source states a return into the recent
alluvium. *Questions:* eligibility by wording ("stated") or by method (measured or traced); constrain?
*Recommendation:* the method criterion (wording is not calibration; both give the same 2 wells today),
and no hard constraint (the canal input is a plain-wide sum, see 10), with a declared soft-prior
sensitivity. Item 17.

**10. Proxy adequacy.** A sign constrains a model only if its driver is an adequate stand-in for what
the mechanism responds to. *Recommendation:* the pool gauge's weekly discharge is adequate for the river
stage near the well, with the caveat that diversions and regulation lie in between; the plain's
summed canal diversions (181 intakes) are a weak proxy for the water reaching one unit's outcrop.
Item 17.

**11. Crop demand.** The land-use test (LU-4) found no detectable information from the crop-demand
index. *Recommendation:* no crop-demand influence in Phase 4's main runs; it stays in arm B's
ablation, and its pathway (which water source carries it) is stated if it is ever used, so that the
same withdrawal is never counted twice. Item 13.

## 3. The graph export

**12. Tiny cells.** Some weather cells hold under 0.001 of a unit's outcrop. *Recommendation:* drop
them from the export (they carry no information and add edges). Item 15.

**13. Several evidence paths.** When several paths join one driver to one well, the export makes one
edge, lists the paths, never multiplies the input, and marks it eligible only if every path gives the
same eligible sign. *Recommendation:* confirm (implemented and tested, `tests/test_export.py`).
Item 17.

## 4. Statistics

**14. Families and tests.** *Recommendation:* RQ1 = {B vs A, D vs C}, RQ2 = {soft vs none, hard vs
none}, one test each (the cluster sign-flip test on the log RMSE ratio), Holm within each family; every
other contrast exploratory and labelled so. NSE and skill stay in every table as descriptions (their
differences always agree in sign, so testing both wasted half of the budget). §10, item 18.

## 5. Ontology, scope and reporting

**15. Ontology scope.** The ontology is frozen at 0.7.x (0.7.1 since the OOPS! scan of 2026-11-16: no
critical pitfall, `docs/oops_report.md`). *Recommendation:* CQ9, 13, 14 and 16 stay minimal fixtures
or future work; Assil's review of the 7 SHOULD/COULD questions closes the scope
(`docs/competency_questions.md`); the alignment ledger's rows "to review by Assil" are reviewed
(`ontology/alignments/ledger.csv`).

**16. Reporting.** *Recommendation:* Chronos-2 and the forecast task in the thesis only (the paper is
about simulation); the Pastas sensitivity rows (recharge only, capped time scales, start chosen on
validation) as an exploratory appendix, since they were defined after results; a time-reversed second
test only if time allows (thesis); text extraction scored against the 32 curated statements (small and
measured, thesis); EuroCrops as a second alignment benchmark only if time allows. Item 18.

**17. Public repository.** The GitHub repository is public: the code, the notes, the analysis plan
and the reviews can be read by anyone (the data and the articles are not committed). A public,
dated plan is good evidence that the analysis was fixed before the results, but the supervisor and
SAVE Water may have rules on releasing project outputs before publication. *Recommendation:* ask them.

## 6. Facts still missing (not decisions)

- The defence date (it sets the whole schedule; the paper is planned for the end of April 2027).
- The SAVE Water / PRIMA grant number (acknowledgements), D4.1/D3.1, contacts.
- Monthly drinking-water production, and BRGM's monthly Pliocene pumping 1998–2007 (Terrasson et al.
  2014, used by Caballero & Ladouche 2015): monthly volumes would separate pumping from weather inside
  a year, which annual totals cannot (`docs/supervisor_questions.md` §4–6).
- The w3id.org redirect: until it exists, tools that load the ontology fail on its imports (OOPS!
  did, 2026-11-16). The pull request is ready to open from Assil's account: `docs/w3id/README.md`.
- The Earth Engine account (satellite rule, task 12.10).
