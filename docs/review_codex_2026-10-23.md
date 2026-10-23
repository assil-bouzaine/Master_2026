# Independent research review and recommendations

**Project:** LULC-Water / SAVE Water — Roussillon groundwater modelling  
**Review date:** 23 October 2026  
**Status:** Recommendations for consideration, not changes to the approved research plan.

This review examined the original subject, research plans, literature tables, stored
dataset v3 and results, relevant preprocessing and evaluation code, and selected
recent publications. It was a targeted research assessment, not an exhaustive
systematic literature review. The review itself changed no files and ran no
training; this document records its findings at the user's request.

## Overall assessment

I would continue this project, but narrow its claims and tighten the evaluation
before adding more complexity. There is a substantial data and baseline foundation
for a strong Master's thesis. There is not yet evidence that the proposed
ontology-guided approach advances the state of the art: the central contribution
still needs to be implemented and tested.

The main concern is that parts of the narrative are ahead of the evidence,
particularly around causal explanations, pumping effects, and generalisation.

## Where the project stands

| Component | Assessment |
|---|---|
| Data collection and integration | Substantial and useful; several assumptions need stronger validation |
| Baseline experiments | Well developed, with some remaining results awaiting integration |
| Literature review | Good selection of topics; incomplete critical synthesis and some outdated decisions |
| Ontology and knowledge graph | Detailed design, but no implemented ontology artifacts found during the review |
| Proposed hybrid model | Research proposal, not a demonstrated contribution yet |
| Causal and explanation validity | Promising experimental ideas; currently unproven |

The latest [baseline report](docs/results_baselines.md) available during the review
gave the following drought-phase simulation results:

| Model | Median NSE | Median skill over climatology |
|---|---:|---:|
| Pastas, seasonal + canal | −0.73 | 0.20 |
| Tuned LightGBM | −0.12 | 0.47 |
| Tuned LSTM | 0.01 | 0.56 |
| Tuned distance ST-GNN | −0.09 | 0.54 |
| Selected ensemble | 0.02 | 0.55 |

These results mean that the learned models improve substantially on historical
climatology, while drought simulation remains difficult. The tuned graph model has
not established an advantage over the tuned LSTM. The ensemble offers little
additional drought performance.

The ensemble's whole-test NSE of 0.44 should not become the headline for drought
performance: the drought-only value is 0.02, and the Pliocene subgroup remains
negative. Chronos-2's stronger forecasting results concern a different task that
uses previous observed heads.

This is a scientifically useful starting point. It identifies a difficult problem
without establishing its solution.

## What to keep

- **Roussillon as the main study area.** One well-characterised system is
  appropriate for this thesis.
- **Weekly groundwater-level simulation**, with forecasting as a secondary
  comparison.
- **Pastas, LightGBM, LSTM/EA-LSTM and a strong graph baseline.** This is already
  a sufficient baseline family.
- **Knowledge provenance, uncertain relations, competency questions and ontology
  reuse.** These give the semantic component practical value.
- **The separation between knowledge as features, knowledge as graph structure,
  and constraints.** This is essential for understanding where any improvement
  comes from.
- **Drought/recovery reporting, multiple seeds, and spatial uncertainty
  estimates.** Keep these principles while addressing the implementation issues
  below.
- **The decision to reject universal shallow-above-deep head ordering.** Letting
  observations challenge an attractive assumption is good research practice.

## Literature review and state-of-the-art positioning

The literature review needs deeper comparison more urgently than it needs a larger
reading list.

The [comparison table](docs/literature/comparison_table.md) still has important
“to complete” entries for the closest competitors. Meanwhile, the reading list
retains earlier choices—PiShield, semantic loss on discrete states, SGI as a
shortcut test—that the newer plan has superseded.

Prioritise these references:

| Reference | Why it matters to the project's positioning |
|---|---|
| [Wu et al., 2025: Graph Fourier groundwater model](https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2025WR041215) | Already uses hydrogeological units as graph priors, with 473 wells and a fully connected graph control. “Adding geology to a GNN” is insufficient novelty. |
| [Heudorfer et al., 2024](https://hess.copernicus.org/articles/28/525/2024/) | Directly relevant to whether static attributes convey transferable knowledge or help identify individual wells. |
| [Schorpp et al., 2023: Roussillon hydrogeological modelling](https://link.springer.com/article/10.1007/s12665-023-10877-4) | A peer-reviewed study of the actual aquifer, including geological structure, canal recharge and withdrawal uncertainty. This deserves a central place alongside the thesis and conference references already listed. |
| [Chu et al., 2026: hybrid TFN–LSTM](https://www.sciencedirect.com/science/article/pii/S0301479726019341) | Combines transfer-function modelling and neural residual correction. A Pastas-like model plus neural residual is already part of the literature, although its forecasting setup differs from this project's. |
| [2026 Water Research study on interpretable transfer learning](https://www.sciencedirect.com/science/article/pii/S0043135426010006) | Evaluates transfer across 62 wells under limited target-well records and compares learned responses with independent hydrogeological information. Relevant to both generalisation and explanation validation. |

The last two were missing from the current tables at the time of review. Their
assessment here uses the accessible publisher abstracts and descriptions.

For each central paper, record:

- Whether previous heads are inputs.
- Whether forcings are observed or forecast.
- The split strategy and spatial generalisation setting.
- What knowledge is supplied to the model.
- Whether explanations receive independent validation.

Those differences matter more than comparing headline accuracy across unrelated
datasets.

A defensible research question could be:

> When does explicit hydrogeological knowledge improve groundwater simulation and
> explanation reliability under uncertain pumping information?

That question remains worthwhile if a simple model wins some comparisons.

## Priority 1: correct the treatment of observation quality

The review found **71 weekly target records containing measurements explicitly
labelled “Incorrecte”** in the source data. These are historical training-period
records; none were found in the drought-test period.

The [weekly aggregation](src/dataset/build.py) averages them into the target. It
only marks “Non qualifié” as unvalidated, so “Incorrecte” is not properly
distinguished. Furthermore, the [evaluation subset labelled “validated”](src/models/evaluate.py)
allows weeks with up to—but less than—50% unqualified measurements.

Exclude explicitly incorrect measurements before aggregation, define a genuinely
validated-only sensitivity analysis, and report its coverage. This does not prove
the model rankings will change; it does mean the current quality labels are too
strong.

Recent observations also need careful wording: the average unqualified share
across core well-weeks rises to approximately **52% in 2025 and 75% in 2026**.
Unqualified does not mean wrong, but recovery-period conclusions remain
provisional.

## Priority 2: treat pumping as an uncertain reconstructed input

Annual BNPE declarations are valuable. Weekly pumping derived from those
declarations is a modelling assumption.

In the stored v3 data, pumping for **2025–2026 is entirely imputed**. Earlier years
also include backfilling and reporting-break corrections. Seasonal allocation
follows climatic deficit, making it difficult to separate pumping from weather
statistically.

Improved fit after adding pumping does not establish that the model recovered
actual pumping effects. Between-year variation alone does not solve confounding
either.

Prioritise monthly drinking-water production and screened aquifer information
above another model family. Without those data, compare a small set of plausible
pumping reconstructions and show whether conclusions survive them.

The older statement that the bottleneck is definitively “missing knowledge” is
too strong. Missing measurements, incorrect forcing assumptions, model structure
and groundwater memory remain competing explanations.

## Priority 3: tighten what “unseen wells” and “less data” mean

The analysis plan openly uses each held-out well's historical mean and standard
deviation for converting predictions into metres. That supports a conditional
test of dynamics at historically monitored wells; it does not demonstrate
prediction at a completely unmonitored well.

There is an additional issue: [`pct_days_artesian`](src/models/features.py) is
calculated from historical groundwater observations and remains an input for
held-out wells.

Spatial separation is also limited. The fold check found that **8 of the 33 core
wells have another core well in a different fold within 500 metres**; the closest
pair is about 20 metres apart. These tests primarily assess transfer within the
existing monitoring network.

Keep that experiment, label it accurately, and add a grouped split keeping
nested/nearby wells together. For the reduced-data experiments, recompute
observation-derived statistics using only the permitted history. Currently,
shortening the training loss window does not remove all information from earlier
records.

## Priority 4: separate retrospective simulation from operational forecasting

Reconstructed annual pumping totals and full-year seasonal weights can contain
information unavailable at the forecast issue date. River-gap interpolation also
uses subsequent observations.

Those choices may be acceptable for retrospective simulation, but the
“operational” forecasting description needs an explicit information-availability
audit. Shifting the finished feature table backwards does not by itself make every
feature historically available.

The current test period has already informed extensive diagnosis and research
decisions. Preserve those results, but describe their exploratory role honestly.
Freeze the next hypotheses and comparisons before running the ontology models;
use later observations or an additional predefined evaluation for confirmation.

## Priority 5: validate pump-to-aquifer attribution

The 211 BSS-linked points are valuable evidence, but their representativeness
matters. Drinking-water boreholes may be much better documented than irrigation
boreholes.

One statistical distinction is particularly important: finding that **50 of 53
Pliocene points have a false river-connection flag does not establish that a false
flag means Pliocene**. That requires checking all false-flag points and their
possible aquifer classes.

Report attribution coverage by **abstraction volume and use**, as well as point
count. Allow ambiguous and unknown assignments. Evaluate uncertain links through
sensitivity analyses rather than turning every plausible inference into a fixed
edge.

A BD LISA stack describes geological arrangement; it does not automatically
establish hydraulic connectivity. Investigation depth remains an imperfect
substitute for screened depth.

## Priority 6: resolve the limits of constraints and explanations

Testing the hybrid model is worthwhile, but its present design does not yet
justify “hard monotonicity.”

A negative gain can enforce a decreasing response when the remaining construction
satisfies the necessary conditions. If the gain itself depends freely on pumping,
or an unconstrained residual also responds to pumping, the **total prediction can
still increase with pumping**. Bounding the residual's magnitude does not bound
its derivative.

The guarantee must cover the complete input-to-output path. Start with a
constrained response model whose behaviour can be verified, then add complexity
deliberately. The [monotonic-network literature](https://arxiv.org/abs/2205.11775)
is relevant here.

An additive contribution can be an exact explanation of the model's calculation
without being the true physical contribution. Ontology consistency, model
faithfulness and causal correctness are separate properties.

Keep the synthetic experiment, but include cases generated by mechanisms
different from the fitted model, missing drivers and incorrect graph links.
Otherwise, recovering contributions generated by the model's own assumed response
functions is an unusually favourable test. Pastas estimates should be a
comparator, not causal ground truth.

## Strengthen the land-use component at a manageable scale

The original subject explicitly concerns land-use–water interactions. The current
operational core is much closer to climate–pumping–groundwater modelling; RPG and
satellite concepts are mostly planned additions.

Two RPG snapshots can support land-use context and a limited change comparison.
They cannot substantiate detailed annual land-use effects over 2005–2026. Using
2023 land use to represent earlier years would require an explicit retrospective
assumption.

**Agreement with RPG crop labels cannot validate irrigation detection:** crop
type and irrigation status are different variables. Summer greenness plus coarse
soil moisture can indicate probable irrigation, but needs independent irrigation
evidence or should remain a clearly labelled heuristic.

Retain one small satellite-derived concept and test whether it adds useful
information. That would satisfy the subject more convincingly than a large
semantic vocabulary disconnected from the prediction experiments.

## Keep the ontology compact and test its scientific role

Keep provenance, observations, time, units and uncertain attribution. Reuse only
the vocabulary needed for the agreed questions. Relax the proposed requirement
that every piezometer have exactly one known unit and depth: forcing incomplete
or ambiguous evidence into a single answer creates false certainty.

Add one important comparison: a graph built from the **same hydrogeological
information using ordinary tables and rules**. This separates the benefit of
domain information from the benefit of formal semantic representation. The
ontology can contribute reproducibility, traceability and consistency even if an
equivalent numerical graph produces identical predictions.

## Strengthen statistical inference

The cluster bootstrap is a useful start. However, the accompanying Wilcoxon test
still treats wells as independent; Holm adjustment does not correct spatial
dependence. With only **14 spatial clusters** under the existing grid definition,
emphasise effect sizes and cluster-aware uncertainty, and avoid conclusions
resting on borderline p-values.

## What to remove from the main workload or move to an appendix

- Additional baseline families after completing the existing comparisons.
- AlphaEarth/TESSERA experiments unless a specific unresolved question requires
  them.
- A substantial LLM extraction or ontology-alignment benchmark; retain a small
  measured demonstration where the subject requires it.
- Multiple competing explanation systems before the hybrid's contributions are
  validated.
- Claims of predicting use conflicts without observations of allocation, unmet
  demand or conflict outcomes. Competing uses can remain the motivation.
- Quantitative crop-change policy recommendations without validated links from
  crops to pumping and recharge.
- A mandatory second-country demonstration. Make transfer conditional on usable
  data arriving.
- A full decision dashboard. A small interface exposing evidence, uncertainty
  and a few meaningful queries is enough.

## Recommended order of work

1. Correct data-quality handling.
2. Define and freeze the evaluation protocol, including information availability
   and the precise generalisation claims.
3. Complete the critical literature comparison.
4. Validate pump attribution and quantify its uncertainty and coverage.
5. Build a minimal ontology and graph export.
6. Test a simple constrained hybrid through controlled comparisons.

Judge success by whether the project establishes **which knowledge helps, under
what conditions, and with what uncertainty**. That would make a coherent,
defensible thesis and a credible paper contribution. The existing work provides
the foundation; the next stage needs stronger evidence and tighter scope.
