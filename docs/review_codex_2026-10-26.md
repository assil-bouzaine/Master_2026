**Research review — 26 October 2026**

**My assessment: the project is progressing well and is worth continuing with its present research direction. Claude has made substantial, verifiable progress and has responded constructively to the earlier reviews. There are still improvements to make before the main modelling experiments. The strongest current achievement is the research infrastructure and its explicit treatment of uncertainty; the proposed benefit of ontology-guided modelling remains to be demonstrated.**

This review concerns the local snapshot at commit `013c1c7b02e060a11067e79cfd6b55bf5f055c0b`, including the existing, uncommitted CQ4 work. I read the original subject in `Documents/sujet.docx`, the project brief, analysis plan, previous review responses, recent commits, relevant implementation and tests, and locally available results. I also checked primary external sources for the methodological and hydrogeological points cited below. I did not inspect the remote Colab results, train models, rebuild datasets or regenerate the graph. Existing project files were left untouched; this review is the only added project file.

**What Claude has accomplished deserves credit.** The previous gap between the land-use subject and the implemented pipeline has narrowed considerably. Annual RPG editions now feed dated crop areas, demand indices, a controlled model comparison, and the knowledge graph. The same-machine controls and the frozen-area comparison are useful experimental safeguards. The null result was retained and discussed rather than hidden. The response to the earlier provenance finding is implemented for land-use inputs, with content identities and rejection of incompatible cached runs.

The knowledge graph now has executable questions, provenance, uncertainty states and independent source-table checks. The handling of alternative pump assignments without counting their volumes twice is particularly valuable. The two-well example is a meaningful demonstration of evidence retrieval, although it is not yet an explanation of a model prediction. Keeping observed facts, assumptions, rule-derived assertions and unknowns distinguishable is a strength to preserve.

| Component | Assessment at this snapshot |
|---|---|
| Data foundation and baseline evaluation | Substantial and usable; v4 consolidation remains incomplete locally. |
| Land-use experiment, LU-4 | Completed locally; main numerical results reproduced during this review. |
| Ontology and factual KG | Substantial implementation; ontology and factual-data checks pass. |
| Derived graph and competency queries | Existing fixtures pass; current saved facts and derived outputs are inconsistent during the unfinished CQ4 increment. |
| RPG–AGROVOC alignment | Snapshot, candidates and annotation tools exist; the gold CSV has 198 rows and zero completed relation labels. No evaluated alignment result yet. |
| KG export and main hybrid model | Designed, not implemented as the completed research pipeline. |
| Satellite semantics, faithful prediction explanations and scenario demonstration | Still outstanding subject deliverables, with appropriate limitations already specified. |

The local baseline report also gives an appropriately demanding starting point: drought median NSE is approximately 0.12 for the LSTM, 0.06 for the distance graph model, −0.05 for Taccari and 0.14 for the ensemble. Those are useful results in a difficult simulation task, but they leave substantial error. The poorer grouped leave-well-out results should remain prominent. Neither statistical superiority over the Pastas reference nor a plausible graph establishes reliable hydrogeological explanations. See [the v4 baseline report](/home/mclovin/Projects/Master_2026/docs/results_baselines_v4.md).

**Independent checks performed.** With `PFE_DATASET=v4`, bytecode writes disabled, temporary caches directed to `/tmp`, and a Python guard against project writes, I ran these existing modules:

- Passed: `tests.test_stats`, `tests.test_folds`, `tests.test_pumping_conservation`, `tests.test_crop_demand`, `tests.test_pumping_cropcal`, `tests.test_land_use_inputs`, `tests.test_run_cache`, `tests.test_regime_boundaries`, `tests.test_kg`, and `tests.test_ontology`.
- `test_ontology` included ELK, HermiT, the deliberate inconsistency control and the ROBOT report. It reported 254 local terms and no ROBOT errors; 13 information/warning rows remain, which is not equivalent to an error.
- `tests.test_kg_rules` passed its existing fixtures and 16 negative controls, then failed the real-data stratigraphic-relation comparison. `tests.test_cq` passed its seven fixture groups, then failed the real-data CQ3 comparison for unit `671AA00`. These failures are consistent with the stale rule outputs explicitly recorded in `CLAUDE.md`; they are not evidence that previously completed snapshots failed their checks.

I independently rescored the saved LU-4 main predictions using the repository's evaluation code, recomputed the paired comparisons, and matched the saved effect sizes, intervals and cluster p-values. Each on/none pair uses exactly the same 5,992 scored well-week keys across 33 core wells. The dataset hashes recorded in the four main on/none run manifests match the current files they cover. This verifies the reported calculations and recorded dependencies; it is not a cold reproduction of training or an independent implementation of every statistic.

| Main contrast: on versus same-machine none | Median paired ΔNSE | 95% cluster-bootstrap interval | Holm-adjusted p |
|---|---:|---:|---:|
| LightGBM | +0.015919 | [−0.041644, +0.051254] | 1.00 |
| LSTM | +0.001311 | [−0.045913, +0.163209] | 1.00 |

The recommendations below address concrete remaining issues. Priorities indicate when to resolve them, not a judgement that the entire project is defective.

**1. High priority before consuming the graph: reject mismatched graph releases and distinguish missing derivation from negative evidence.**

The factual graph contains 373,259 triples, while the saved rules summary says its inputs contained 356,377 triples. [The graph loader](/home/mclovin/Projects/Master_2026/src/kg/cq.py:93) combines the two files without checking their compatibility. Rebuilding the rules is already Claude's documented next step. The additional recommendation is to make this mismatch impossible to consume silently in a report or model export.

There is a concrete consequence beyond failing tests. For MILLAS C2-1 (`10906X0039/C2-1`), its unit `718BP02` and its 5 km search zone, the current `cq04_status` query returns `supported` with the reason “no mapped outcrop in S”. Yet the same loaded store contains five order-1 polygon-intersection pieces for that unit and extent, totalling approximately **27.08 km²**. The coverage query is empty because the new coverage derivation has not run. [The status query](/home/mclovin/Projects/Master_2026/tests/cq/cq04_status.rq:22) interprets the absent derived value as absent mapped outcrop.

Recommended resolution: record hashes of the factual graph, rules, ontology and relevant parameters in the derivation manifest; require a completed, compatible derivation before queries or export use it. Make an absent coverage record yield an incomplete/unknown status when the prerequisite calculation is missing. A genuine “no mapped outcrop” answer should follow a completed search, not merely a missing triple. Publish a graph release only after its facts, derivations and validation agree.

Acceptance should include an intentionally stale facts/rules combination and a graph with positive intersection facts but no derived coverage. Both should refuse a supported negative answer. Complete the planned CQ4 fixtures and spatial oracle before treating this increment as finished. This is a safeguard for the project's central promise that missing evidence remains visible.

**2. High priority before new primary comparisons: compare scored dates, not just their counts.**

[`stats.paired()`](/home/mclovin/Projects/Master_2026/src/analysis/stats.py:103) checks whether `n_weeks` differs between runs. Equal counts do not establish identical observations. I reproduced the gap in memory: for six wells, remove the first scored week from one prediction set and the last from the other. The two sets then differ by 12 well-week keys, but `strict=True` accepts the comparison and reports `support_mismatch = 0`.

This does **not** invalidate the existing main LU-4 comparisons: their exact date sets match, as checked above. It leaves future comparisons exposed when models have different availability, warm-up periods or missing predictions.

Recommended resolution: check the actual `(well, week, task, horizon)` keys after observation-quality and placeholder filtering. Store a support hash per evaluated group or score both predictions on an explicitly defined common support. For a primary contrast, reject unequal support unless the analysis plan specifies the intersection policy in advance. Also report wells excluded by the existing minimum-coverage rule. Add the equal-count/different-date counterexample to the existing statistical checks.

**3. High priority before freezing Phase 4: specify what the revised D-versus-C contrast can establish.**

The decision to derive D's weather, river and canal links from the KG is coherent with the project's objective. I am not recommending that it be silently reversed. However, [the new export contract](/home/mclovin/Projects/Master_2026/docs/analysis_plan.md:650) explicitly allows D to have no relation where the evidence is missing. Five Pliocene wells lose the direct weather connection under the chosen local-outcrop rule. Canal relations may remain incomplete.

A common node inventory does not by itself guarantee equivalent information availability at each target. The experiment remains a valid comparison of **two complete connection policies**. Its effect can combine hydrogeological routing, sparsity and evidence coverage. Reporting missing-edge percentages describes that difference; it does not establish which component caused an accuracy change.

Before running the arms, produce a per-well, per-relation inventory of direct connections, source coverage, weights and the information actually reachable through the implemented message-passing layers. Include any weather or river features supplied directly at well nodes: absent source-node edges do not necessarily mean absent information.

Use the already planned degree- and distance-matched controls to test semantic routing while preserving relation-specific availability. If an additional coverage-matched diagnostic is needed, define it before seeing scores and keep it clearly distinct from the approved main D arm. A subset analysis must use a coverage rule based on metadata, never on which wells favour D. Phrase D-versus-C conclusions as the benefit or cost of the specified KG connection policy unless the controls support the narrower semantic explanation.

**4. High priority before selecting graph thresholds: close the new information-use ambiguity in R2 and R3.**

[The new depth rule](/home/mclovin/Projects/Master_2026/docs/analysis_plan.md:671) chooses among 10, 20, 50 metres and no threshold using correlations of training-period head anomalies. That is a target-informed graph-selection step. The older regime table says graph construction uses positions and static attributes, never heads. The two statements now need reconciliation.

There is no evidence of test-period leakage from this rule, and it is not yet implemented as a completed experiment. The concern is prospective: applying one threshold learned from all wells and the full history would use held-out wells' historical dynamics in R2 and head history outside the shortened window in R3. The existing monitored-well convention permits specified historical statistics; it should not silently expand to arbitrary target-informed graph selection.

Recommended resolution: choose the threshold using only allowed training wells and head years for each regime. Include this choice inside the planned nested D-versus-C procedure for R2. If a globally selected threshold is retained as a fixed-development sensitivity, explicitly identify that extra information use. Record the qualifying pairs, shared observation counts, missing-depth exclusions, tie rule and selected threshold. A threshold supported by very few pairs should not win by an unspecified accident of small-sample correlation.

Preserve the present spatial grouping. Structured cross-validation should reflect the intended prediction setting; it is not interchangeable with random partitioning. This is the relevant principle from [Roberts et al. (2017), doi:10.1111/ecog.02881](https://onlinelibrary.wiley.com/doi/full/10.1111/ecog.02881). The fold-specific graph-selection recommendation above is my application of that principle to this project's new rule.

**5. Resolve the physical interpretation of recharge edges before giving them hard constraints.**

The 5 km outcrop calculation is a reproducible spatial proxy. Its radius was borrowed from the pumping search radius; that does not establish it as a recharge contributing area. The current CQ4 contract correctly says that outcrop is not proof of effective recharge and that no local outcrop is not zero recharge. Those qualifications need to survive the transition from query answer to `Influence` and model constraint.

This matters in Roussillon. The local groundwater authority describes Pliocene recharge through upstream Têt/Quaternary infiltration and peripheral formations, including the Corbières karst. Local outcrop alone therefore cannot represent the complete supply system. [Syndicat Mixte des Nappes du Roussillon](https://nappes-roussillon.fr/en-pratique/fonctionnement-des-nappes/). The BRGM Dem'Eaux study documents summer canal-related recharge in the Quaternary and downward leakage towards the Pliocene in the Têt sector. [Ladouche and Caballero, BRGM/RP-71486-FR, January 2022](https://www.brgm.fr/sites/default/files/documents/2022-07/reference-demeaux-roussillon-p11b.pdf).

My recommendation is to keep the approved local extent as a declared approximation and retain the planned unit-wide sensitivity. Explicitly state which pathways each represents and omits. Distinguish effective rainfall and soil drainage from actual aquifer recharge; do not add correlated proxy components as independent water inputs without a water-balance rationale. “Exact BD LISA unit” should also retain its cartographic meaning: for a multilayer system it does not identify a common screened horizon or establish hydraulic connectivity.

Before broad model sweeps, obtain a bounded domain review of the two worked examples and their proposed recharge, abstraction and canal pathways. Check the interpretation of quantities and units, not just their geometry. This is a targeted scientific review, not a reason to replace the pipeline with a full groundwater simulator.

**6. Define the alignment evaluation before the gold set and matcher choices become mutually dependent.**

The AGROVOC snapshot and annotation tooling are useful preparation. The current protocol in [agrovoc_gold.py](/home/mclovin/Projects/Master_2026/src/kg/agrovoc_gold.py:8) starts from lexical candidates and asks for one best concept and relation per code. It already warns against limiting the gold set to those candidates. Strengthen that safeguard while all 198 reference relations are still unfilled.

Recommended additions are modest: a written decision rule for plant versus harvested product versus land-use concept; treatment of mixed categories, ambiguous matches and genuine no-match cases; and separate scoring of target identification and relation correctness. Decide how alternative acceptable targets are handled instead of resolving them after a matcher is penalised. Report per-code results; any area-weighted result should be secondary, with its denominator defined, because success on common crops can hide failure on rare codes.

Have a second person independently annotate a manageable subset, including ambiguous and no-match cases, preferably without candidate rankings. Record disagreement and adjudication; if only one annotator is available, disclose that limitation. Reserve development examples for prompt/threshold selection and leave the evaluation subset untouched. The full validated mapping can still be used in the final KG after evaluation.

Do not collapse broad, narrow and close matches into exact equivalence to improve a headline score. Their semantics differ, and `skos:exactMatch` is transitive whereas `skos:closeMatch` is not. [W3C SKOS Reference, section 10](https://www.w3.org/TR/skos-reference/#mapping). Alignment to an agricultural concept also does not independently validate the project's irrigation assumptions or Kc values.

**7. Preserve the land-use null result, with consistent wording and a bounded next step.**

The detailed step note already interprets the uncertainty responsibly: the LSTM interval still includes a median gain around 0.16 NSE. Keep that qualification in summaries. “No detectable improvement from this demand index under these models, settings, wells and drought period” is more accurate than “land use adds no information.” Fixed settings tuned without the new feature test the adopted addition protocol, not every possible land-use model.

The result does not establish equivalence, demonstrate that agricultural practices have no groundwater effect, or validate a causal pathway. The two alluvium groups have only four and two core wells, respectively. Their limited evidence should not be promoted into a strong regional null. A difference between the median model scores is also not the median of paired well differences; Claude correctly distinguishes these in the step note.

I would not launch repeated feature redesigns to rescue a positive result. Carry the result into the thesis and proceed with the already planned pathway-specific work, especially canal return flow and the crop-calendar reconstruction. For future equivalence claims, define a scientifically meaningful negligible-effect margin prospectively rather than interpreting a large p-value as proof of no effect.

Retain the random-identifier and shuffled-static controls already in the plan. Heudorfer et al. found that random static identifiers could perform similarly to environmental features in their groundwater models, making apparent use of static information an insufficient explanation of generalisation. That supports the need for controls, not a conclusion about this project's particular index. [Heudorfer et al. (2024), doi:10.5194/hess-28-525-2024](https://hess.copernicus.org/articles/28/525/2024/).

**8. Finish reproducibility at the level of an executable release, including the remaining input dependencies.**

The land-use manifests and saved weights are an improvement I verified. The main historical v4 folders for LSTM, distance ST-GNN, Taccari and EA-LSTM nevertheless have seed predictions but no local `seed_*.pt`, `schema.json` or `manifest.json`. Thus saving checkpoints in newer code has not retroactively made these runs replayable. Their tables can be rescored; their fitted networks cannot currently be re-executed locally for a new period or intervention.

There is also a specific remaining manifest omission: [`DATASET_FILES`](/home/mclovin/Projects/Master_2026/src/models/manifest.py:26) excludes `rivers_weekly.parquet` and `gauges.parquet`, although [feature construction](/home/mclovin/Projects/Master_2026/src/models/features.py:70) reads them. A manifest matching its recorded files is therefore not yet proof that all model inputs match.

Before Phase 4, inventory runs as predictions-only or replayable; include every consumed data dependency and the resolved graph/panel identity in new run manifests and cache-compatibility checks. Bind graph exports to ontology, rule, policy and feature versions as well as model code. Do not invent retrospective provenance. Recover old checkpoints if they exist remotely; otherwise rerun only selected models actually needed for the independent future-period check or intervention comparisons, under a new recorded run identity.

Complete the existing v4 work before adding model families. Chronos-2 variants and Taccari regime results described as completed on Drive are absent locally; their existence and completeness remain unverified by this review. Consolidate those artifacts, verify their provenance and regenerate one final baseline record. Keep the older exploratory results available and clearly labelled.

**9. Protect the central thesis deliverable by making the next milestone executable and small.**

The next milestone should extend the existing two-well example through **source observations → KG derivation → exported tensors → a model output → a faithful contribution explanation**. That will test the central integration claim sooner than completing every possible ontology extension. Finish CQ4; conduct a bounded evidence search for CQ5/CQ6; preserve documented gaps where support is missing; then implement the export and its independent equivalence check. Do not invent canal service areas to complete a diagram.

Keep the satellite component within the original subject: one seasonal semantic rule with explicit quality coverage and an honest evaluation is sufficient at this stage. The existing CQ15 specification correctly distinguishes aggregate census checks from parcel-level validation. Implement that contract; there is no need to expand it into an unrelated remote-sensing modelling programme.

Build the small, difficult synthetic twin before the broad sweeps, as already planned. Its first useful outcome is a demonstrated case where accurate heads coexist with incorrect contributions and the diagnostic detects the problem. An explanation that merely names a valid KG path is not evidence that the fitted model used it. Preserve the separate tests for consistency, model faithfulness and physical interpretation.

At Gate 3, freeze the exact features for A/B, graph-selection rules, allowed information per regime, machine/software parity for each contrast, statistical families and completion criteria. Include the proposed clarifications above as dated amendments, without retrospectively relabelling exploratory results. The existing distinction between a pre-specified comparison on an examined benchmark and an independent future-period check is scientifically appropriate.

For publication, concentrate the main story on when qualified hydrogeological knowledge helps simulation and whether the resulting explanations withstand tests. Ontology alignment and satellite semantics can support that story and the thesis objectives without each becoming a separate major research programme. A mixed or negative accuracy result can still support a useful paper if the controlled comparisons and explanation diagnostics are convincing; publication is not established by the current infrastructure alone.

My recommended order is: complete a consistent CQ4 graph release and its missing-evidence safeguards; strengthen exact-support evaluation; settle graph coverage and regime-specific threshold rules; finish the export and two-well executable path; then run the small twin and frozen primary contrasts. Complete the gold-set protocol and outstanding baseline consolidation alongside that sequence. The project needs these focused improvements and completion of its central experiment, not a wholesale redesign.
