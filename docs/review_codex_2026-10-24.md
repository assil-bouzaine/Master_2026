# Independent research review — 24 October 2026

**Project:** SAVE Water / LULC-Water, Roussillon groundwater modelling  
**Author:** Codex, reviewing the work from a research-methodology and ML perspective  
**Reviewed snapshot:** `e9326e0`  
**Scope:** assessment and recommendations only. This document does not change or approve changes to the decisions in `CLAUDE.md`.

I read the project brief, the original subject in `Documents/sujet.docx`, the analysis plan, roadmap, previous reviews and responses, decision notes, competency questions, ontology design, literature matrix, and the relevant dataset, modelling, evaluation, graph-building and test code. I checked local dataset metadata, cached feature panels, attribution evaluations and saved v3/v4 metrics using read-only calculations. I also checked selected research sources online. I did not retrain models, rebuild data, run the ontology gates, or inspect the remote Colab/Kaggle outputs. Statements about work still on those services are therefore distinguished from locally verified results. Only this file was created.

**Overall assessment:** this is a substantial Master's research foundation with a plausible publication path. The strongest work is the explicit handling of data limitations, the baseline coverage, and the increasingly careful knowledge representation. The central scientific contribution remains untested: the repository does not yet demonstrate that ontology-derived structure improves prediction, explanation reliability, or physical plausibility. The next quality improvement should come from completing a controlled experiment and validating its assumptions. Adding more model families would have much less value.

The most consequential outstanding issues are:

1. Historical test results have already influenced the research design; freezing the plan now cannot make those observations unseen again.
2. The reduced-data and held-out-well experiments still have information-use details that need tightening or more precise claims.
3. The Pastas reference needs a clean training-only construction and a correctly specified multistart selection criterion.
4. The accepted pump-link policy covers drinking water well, but currently accepts no irrigation volume in the plain's attribution accounting.
5. Graph semantics, architecture, forcing coverage and sign constraints must be isolated experimentally.
6. Reusable model checkpoints and complete run manifests are needed before the proposed future-data confirmation can work.

## 1. Where the project actually stands

| Component | Evidence present now | Research interpretation |
|---|---|---|
| Dataset | v4 exists: 65 wells, 33 core wells, observations through 2026-10-04; incorrect observations removed, grouped spatial folds, quality flags | A useful, documented regional dataset; forcing reconstruction and recent observation quality remain limitations |
| Baselines | Substantial v3 results; v4 CPU results saved locally; neural v4 results are described in `CLAUDE.md` but their final prediction files are not in the local run folders | Baseline development is advanced, but the complete v4 comparison is not yet available for this review |
| Evaluation | Drought/recovery scores, climatology-relative skill, datum-free KGE, cluster inference, strict-quality subset | Much stronger than a single random split and one average score; some protocol and implementation gaps remain |
| Ontology | `ontology/lulcw.ttl` version 0.1.1, imports, alignments, quality-gate code and documented checks | A real implementation with careful semantics; ontology consistency is not evidence that the hydrogeological assumptions are correct |
| Instantiated KG | Saved summary reports 205,650 triples, 65 piezometers, 47 hydrogeological units across their classes, 2,187 abstraction facilities and 12,951 annual records | The factual integration layer exists; triple count is an engineering statistic, not a scientific outcome |
| Model-facing KG | SHACL/rule execution, complete CQ acceptance, export and independent export-equivalence testing remain scheduled as tasks 12.6–12.8 | The bridge from knowledge representation to numerical modelling is still incomplete |
| Main research model | Hybrid response-function model and black-box comparison are specified | Their predictive and explanatory benefits are hypotheses |
| Explanations, twin and land use | Stronger written contracts; numerical twin, explanation evaluation and satellite experiment remain planned | These are major unfinished parts of the contribution and of the original subject |

For a concrete view, these are **saved local drought-phase medians over the 33 core wells**, not newly fitted results:

| Simulation run | v3 NSE | v4 NSE | v4 skill against climatology |
|---|---:|---:|---:|
| Climatology | -1.494 | -1.494 | 0.000 |
| Pastas, seasonal + canal | -0.728 | -0.513 | 0.215 |
| Pastas WellModel | -0.679 | -0.675 | 0.134 |
| LightGBM, tuned, no own-climatology input | -0.122 | -0.095 | 0.492 |
| Same LightGBM, held-out monitored wells | -0.752 | -0.910 | 0.281 |
| Same LightGBM, most recent 25% training window | -0.255 | -0.345 | 0.468 |

Sources: `results/v3/<run>/metrics_summary.csv` and `results/v4/<run>/metrics_summary.csv`. The last two rows are different regimes, so they should not be ranked as equivalent training setups. Changes between versions can involve data, folds, preprocessing and execution environment; the table does not isolate any one cause.

The tuned v3 LSTM has drought NSE **0.008** and climatology skill **0.560**. That is a meaningful improvement over the historical seasonal benchmark, while substantial drought error remains. Negative NSE and positive climatology skill can coexist because their reference predictions differ. Avoid describing the remaining gap as proof that missing ontology knowledge is the bottleneck.

The v4 strict subset contains **27 wells / 3,948 well-weeks** in the drought, compared with **33 / 6,052** using all available weeks. Recovery has only **7 / 296** strict observations, compared with **32 / 1,362** overall. These are different evaluation populations, not simply more and less accurate versions of the same sample.

## 2. Choices worth keeping

- **One aquifer system and one main prediction target.** The scope is appropriate if the remaining work is prioritised. Keep transfer to Manouba conditional and small.
- **Simulation as the primary task.** Separating it from hindcasting makes the intended contribution clearer. Describe the inputs precisely: no lagged head sequence in simulation, but historical head-derived summaries such as artesian share are still used.
- **Strong simple and hydrological comparators.** Climatology, Pastas, LightGBM and the existing neural/graph baselines already provide ample coverage. Keep unfavourable results.
- **The response-function hybrid as a working hypothesis.** It connects the hydrological baseline to parameter sharing and an inspectable decomposition. It still needs to earn its complexity experimentally.
- **The revised ontology distinctions.** Investigation depth versus screen depth, stratigraphic arrangement versus hydraulic connectivity, group-level versus entity-level attribution, unknown versus zero, and declaration versus reconstruction are all valuable.
- **Giving the ontology credit for traceability and consistency.** The decision to compare exported knowledge with equivalent table-based rules is scientifically sound. Numerical gains should be attributed to the information and inductive assumptions supplied to the model.
- **Restraining the satellite and LLM components.** A small evaluated alignment task and one carefully qualified satellite concept fit the thesis better than several additional foundation models.

## 3. Highest-priority recommendations

### 3.1 Preserve an honest boundary between development and confirmation

**Finding:** `docs/analysis_plan.md` §11 acknowledges that the test period informed decisions, then says the Phase 4 comparisons become confirmatory after tagging the plan. The tag is useful, but does not restore independence from the same historical drought data. The architecture, forcing assumptions, case studies and evaluation boundary have all been discussed in light of those observations.

**Recommendation:** retain the historical drought as the principal development benchmark and describe Phase 4 results on it as *comparisons specified before the Phase 4 runs, on a previously examined benchmark*. Reserve independent confirmation for genuinely new observations or an external dataset excluded from development. Revalidation of previously examined 2025–2026 observations is a valuable quality sensitivity check; it is not an independent temporal test.

Before the next substantive model run, freeze the exact contrasts, graph policies, reconstructions, seeds, evaluation population and interpretation rules. Record amendments without changing the story retrospectively. New post-freeze observations may be too short or hydrologically different to validate the historical drought claim; report that limitation instead of overstating confirmation.

**Completion criterion:** every main result has an explicit development/confirmation label, and the future-data check uses saved frozen models without selecting them on those new observations.

### 3.2 Complete the information-use contract for R2 and R3

**Confirmed R3 implementation gap:** `src/models/lstm.py:113` computes input means and standard deviations from every row labelled `train`. The shorter `train_start` mask is constructed later, after `arrays(P)`. `stgnn.py` shares that function, and `taccari.py:140` separately derives exogenous-node scaling from all `train` columns. The v4 repair correctly restricts target mean, target standard deviation, climatology and artesian share, but does not restrict these input scalers.

The saved `panel_f25.parquet` makes the distinction concrete: the full training population has **50,895 panel rows**, whereas the allowed recent window has **12,740**. Mean temperature is approximately **14.172 versus 14.920**, and mean `pump_gw` is **29.021 versus 30.051** in the panel's units. This is not test-target leakage, but it means the implementation needs a more precise definition of “25% data”.

There are two defensible protocols: less observed head history while retaining historical forcings and their distribution, or less data for all fitted preprocessing. Choose explicitly. My preference is to fit learned preprocessing on the permitted training population, while keeping earlier forcings only as declared warm-up. Apply the same rule to river-gap climatologies, feature construction, node scaling and all architectures. Record which wells lack sufficient target history in each shortened window.

**R2 selection issue:** `src/models/regimes.py:33` reuses `best.json` selected by `src/models/tune.py` on the full set of core validation wells. Holding a fold out of gradient updates and early stopping does not remove its influence from that earlier hyperparameter selection. LightGBM uses the same general selection-transfer strategy. The existing R2 is therefore a fixed-configuration transfer diagnostic, with configuration selection informed by all monitored sites.

For a stronger spatial-generalisation claim, use outer held-out site groups with selection restricted to the remaining groups, or an independently fixed configuration. A limited nested check for the primary C-versus-D contrast would be more useful than nesting every exploratory baseline. State that the graph remains transductive when held-out nodes and their known covariates are present during training; a completely new node arriving after training is a separate experiment. Grouped folds remain the correct direction for dependent spatial data. [Roberts et al., 2017, DOI: 10.1111/ecog.02881](https://nsojournals.onlinelibrary.wiley.com/doi/10.1111/ecog.02881)

R3 also reuses the full-history-selected configuration. This is reasonable as a controlled reduction of fitting data, but it does not represent an entire model-development process conducted with only 25% of the history. Shorter, more recent windows also change climate and pumping regimes: their comparison measures amount **and recency** of training data.

**Completion criterion:** a table specifies, for each regime, which wells and dates may inform losses, selection, scaling, imputation, graph construction and historical head summaries. Checks should verify those boundaries.

### 3.3 Make the Pastas reference clean and stable before relying on it

The saved seasonal-plus-canal reference changes from **-0.728 to -0.513 drought NSE** between v3 and v4. My read-only comparison confirms that **13 of the 43 drought-scored wells with identical head series** change by more than 0.05 NSE. This supports investigating solver and environment sensitivity; it does not yet establish the cause.

Three details deserve attention:

- **Training-only construction:** the ordinary runner supplies the full observation series to `ps.Model`. The installed Pastas 2.0.0 source initialises its constant from that series' mean (`pastas/model.py:129`). Thus held-out observations affect initialisation even though the fit objective is time-restricted. The existing `--train-obs` experiment is useful, but training-only observation construction should be the methodological requirement for the future reference, independent of whether its test score improves.
- **The documented calibration window is stale:** `fit_well()` uses `splits['model_start']`, which is **2005-01-01** for v3/v4. All **55** saved v4 fitted-well training counts match the 2005–2019 window; only 15 match a 2012–2019 count. Consequently, the statement that pre-2010 changes are outside calibration is incorrect. The 47 figure refers to drought-scored wells, not all fitted wells. This correction does not explain changes at wells with identical observations.
- **The multistart ranking criterion needs checking:** `pastas_baseline.py:181` stores the sum of squared unweighted noise, and `pastas_stability.py:43` selects the minimum. The installed solver's objective multiplies noise by its noise weights before optimisation (`pastas/solver/objective/misfit.py`). With gaps and varying noise parameters, these objectives need not rank starts identically. Record the actual solver objective or explicitly choose and justify another training-only criterion. Do not label the current quantity “the solver's own criterion” without verifying equivalence.

Freeze the reference-selection procedure before examining the multistart test ranking. Report convergence failures, simplified-response fallbacks, parameter bounds and per-well score spread. Compare repeated fits on the same environment and a small matched set across environments; do not attribute every v3-to-v4 difference to hardware. Preserve the old rows as historical results.

**Completion criterion:** the reference uses no held-out observations in construction or selection, its chosen-start rule matches the stated objective, and the remaining numerical variability is quantified.

### 3.4 Reconcile the pumping evidence with the scientific story

**Important new interpretation of existing results:** `data/interim/pump_unit_attribution_eval.json` reports the following plain-wide declared-volume accounting for irrigation: **0 confident, 0 probable, 137.30 Mm³ possible, 24.14 Mm³ unknown**. This is the saved 2012–2024 attribution accounting, not a claim that those volumes are independent measurements of actual pumping.

Under the approved confident-plus-probable policy, this accounting provides **no accepted irrigation-to-unit volume**. The headline 72% coverage is dominated by drinking water. A model driven only by these accepted abstraction links cannot then be interpreted as having established the relative groundwater effects of drinking-water and irrigation abstraction. This is a consequence of missing evidence, not an argument for upgrading uncertain links to make the story work.

Keep the approved confidence policy, but report coverage by **use × unit × year**, including unresolved and excluded volume. Specify how unassigned pumping enters each arm: it may remain an unresolved shared forcing or a separately labelled sensitivity assumption; it must not silently become zero. If C sees irrigation forcing that D loses through policy filtering, D-versus-C mixes information coverage with edge semantics. The comparison needs a common forcing inventory and a declared policy for uncertain pathways.

Treat the current data-supported main story as drinking-water pressure within a broader agricultural water-use context. Keep irrigation mechanisms provisional until the all-link sensitivity or better independent evidence supports them. The 72% figure also predates the KG's group/entity resolution split; verify actual model-export coverage rather than carrying that percentage forward automatically.

**The validation sample is useful but small and partly adjudicated.** The alluvial rule is right at group level on **18/19** recorded boreholes; the Pliocene rule on **36/39** after depth-based revision, versus **32/39** against the raw records. Approximate 95% Wilson intervals are **[0.754, 0.991]**, **[0.797, 0.973]**, and **[0.673, 0.910]**, respectively. These intervals assume independent boreholes and do not address selection bias or spatial dependence. They illustrate why point precision must not become an individual-edge probability.

The revised reference labels and the rules share geological assumptions, particularly the stack. Report agreement with raw and revised records separately, retain disagreements, and seek a small independent audit using borehole/screen information. Test geographically separated sites where feasible. The lack of irrigation reference boreholes is a domain-coverage limitation, not something a high drinking-water precision fixes.

**Completion criterion:** accepted, ambiguous and missing pumping are visible in every exported dataset, and every sector-specific claim has evidence at the sector and spatial resolution being claimed.

## 4. Design the main experiment so its result has one interpretation

The A–F structure is sensible, but there is a design tension to resolve before coding. `src/models/taccari.py` describes a fixed temporal-convolution/mix-hop architecture for comparing distance and KG edges. `CLAUDE.md` makes a GNN-to-response-function hybrid the main model. Comparing the existing Taccari network with a new hybrid would change architecture, temporal representation, constraints and graph together.

Use an explicit experiment contract:

| Question | Hold fixed | Change |
|---|---|---|
| B versus A: does additional knowledge help as information? | Backbone, fitting protocol, common forcing coverage | Declared knowledge-derived features |
| D versus C: do semantic edges help? | Node inventory, feature tensors, backbone, response functions, parameter budget, constraint setting, split and seed schedule | Edge-generation rule |
| Hard/soft versus none: do signs help? | Graph, inputs, training population, response family | Constraint mechanism and its declared tuning parameters |
| Hybrid versus black box | Graph and available information | Model architecture; interpret this as an architecture comparison |

A small parameter-prediction model without message passing is a valuable ablation of the proposed hybrid. It tests whether shared response functions and static attributes already explain the gain. This is an ablation of the chosen method, not a request to add another broad baseline search.

For rewiring, preserve relation types, edge directions, source/target type compatibility and degrees. Add a distance-matched null where practicable: otherwise an apparent semantic benefit may simply be a locality benefit. Use several graph draws, report graph-randomisation variation separately from optimiser-seed variation, and verify that the randomisation materially changes the graph. Choose the null designs before examining real-data improvements.

Coordinates, group codes and historical artesian share can identify stations. A shuffled-static or random-ID control can test whether apparent knowledge use is station memorisation. Heudorfer et al. found that random static identifiers could perform comparably to meaningful static features in their groundwater setting; that motivates a control, not a prediction of what will happen here. [Heudorfer et al., 2024, DOI: 10.5194/hess-28-525-2024](https://hess.copernicus.org/articles/28/525/2024/)

Equal Optuna trial counts are a good starting rule, but also report search spaces, parameter counts, completed/failed trials, training time and the total selection procedure. A six-layer, kernel-three Taccari temporal stack has a nominal 127-step receptive field before considering its rolling-summary inputs; a configured 156-week window does not by itself imply 156 weeks of raw temporal memory. Describe effective memory and temporal aggregation, rather than treating all lookback settings as equivalent information access.

## 5. Make physical plausibility and explanations testable

### 5.1 A sign-constrained gain is only part of the guarantee

The adopted whole-path monotonicity conditions are a strong start. Specify the complete map from a physically meaningful intervention to the final head prediction: raw volume or recharge, derived/rolling features, scaling, graph processing, response kernel, gain, residual and inverse target transformation.

Use causal kernels with non-negative weights for a positive response, and a fixed negative gain for a pumping decrease response. Kernel shape parameters must not acquire an unconstrained dependence on the intervened driver either. Normalise kernels so that gain and kernel amplitude cannot arbitrarily trade scale. Test impulses, sustained changes, lagged responses and boundary cases with preprocessing fixed from training.

Changing one precomputed pumping feature while leaving its rolling copies unchanged is not a coherent physical intervention. Likewise, excluding a raw driver from a residual does not exclude its deterministic copies or close proxies. Report residual magnitude and its associations with the constrained drivers. A residual that accounts for most drought variability weakens the mechanistic interpretation even if the total decomposition sums exactly.

Keep CQ8's distinction between effective recharge and proxies. A river-discharge series is not automatically a local river-stage boundary, and canal diversion is not measured return-flow recharge. A model can enforce a specified conditional sign without establishing the net effect of a water-management policy.

### 5.2 Test identifiability, not just reconstruction accuracy

The harder semi-synthetic twin is one of the strongest parts of the plan. Build a small version before the expensive main sweeps, so it can reveal whether the intended explanation tests have any power.

Use multiple generator parameter draws and noise levels, not only different training seeds on one synthetic world. Include independent versus climate-correlated pumping, omitted drivers, delayed/nonlinear responses, wrong links, and different proportions of imputed pumping. Generate truth from a separate graph, then corrupt the graph given to the learner; corrupting both together would fail to test erroneous knowledge.

Score prediction error, contribution-recovery error, response sign, response timescale and error in controlled intervention responses. A convincing stress case is good head prediction accompanied by incorrect driver contributions: the method should detect or acknowledge that ambiguity. Calibrate the explanation tests' false alarms and detection rates on these cases. The twin validates behaviour under specified generators; it cannot establish causal correctness in the real aquifer.

For real data, between-year and between-well pumping variation is more informative than the imposed within-year climate profile, but remains potentially confounded. Use “model-attributed contribution” unless independent evidence supports a stronger interpretation. Independent monthly production or screened-depth information for a few representative sites may be more valuable than another neural architecture.

### 5.3 Evaluate explanation reliability separately from fluency

Report three separate outcomes: numerical faithfulness to the model, validity of the cited KG path, and agreement with independent physical evidence. Exact additive contributions establish the first only for the stated decomposition and baseline.

For every explanation, include the reference condition, units, period, data-quality status, evidence policy and any unresolved pathways. Evaluate deletion/fidelity with plausible driver-group interventions; deleting nodes or setting standardised inputs to zero can otherwise create unrealistic cases. Use a fixed sample of ordinary cases and failures in addition to the three selected events. A groundwater rebound already used to design the method is a case study, not an independent causal validation.

## 6. Complete the ontology's scientific role and the land-use requirement

Finish tasks 12.6–12.8 before broadening the vocabulary. The most persuasive deliverable is one complete path: source records → qualified assertions → rules → query → numerical export → prediction → evidence-backed explanation.

The existing CQ and negative-control work should remain. Add meaningful failure cases: absent depth, contradictory assignments, only group-level evidence, spatial contacts in different polygons, missing declarations, uncertain sign, and alternative candidates that must not duplicate volume. These cases test whether the formalism prevents plausible scientific mistakes.

Extend the planned export-equivalence check beyond an unordered edge list. Compare node identity/order, relation direction, features, units, weights, confidence policies, masks, time alignment and constraint eligibility. Then a fixed-weight forward pass should agree within tolerance. Identical edges alone do not imply identical predictions when other tensors differ. The table implementation must derive results independently from source tables, rather than consume the materialised KG answers.

The KG includes **50 facilities absent from the model-ready pumping-point table**, according to its saved summary. Reconcile those inventories at export and state whether each extra facility has usable forcing, is excluded, or remains unresolved. Conservation of declared totals and reconstructed annual totals should be checked at their respective layers, including December/January weekly boundaries. Do not interpret agreement with a source table as validation of the source's physical accuracy.

Measure the ontology's value through answer coverage, provenance completeness, detected violations, explicit unknowns, export reproducibility and a small documented reuse/change example. Large triple counts or a reasoner's consistency result do not substitute for those outcomes. External hydrogeological review of a small, stratified sample of assignments and influence paths would add evidence the software tests cannot supply.

**Land use remains a real gap relative to the subject.** The groundwater and pumping work is much further along than the crop/remote-sensing chain. Preserve a minimum complete demonstration: dated RPG concept → reviewed AGROVOC/HILUCS mapping → qualified demand or irrigation assessment → relevant pathway → model-feature ablation → explanation. A null predictive result is acceptable if represented and evaluated honestly.

Use only independent parcel-season labels for parcel-level irrigation precision/recall. Commune census aggregates support aggregate checks; canal access and nearby pumps support plausibility. This distinction is already well stated in the revised CQ15 and should survive implementation. Separate alignment-rule development from a held-out gold set, report unmapped/ambiguous codes and agreement between reviewers, and compare any LLM matcher with simple lexical/retrieval matching.

Treat the 2023 RPG snapshot as explicitly dated retrospective context. Using it as a fixed attribute for the 2005–2019 period would not represent land use known or observed throughout that training period. Crop-change scenarios should expose assumptions about demand, source allocation and return flow; until those are supported, their outputs remain conditional model scenarios.

## 7. Evaluation, uncertainty and reproducibility

**Use paired support.** `evaluate.py` drops missing predictions separately for each run; the statistical comparison then pairs per-well scores. For each main contrast, ensure both models were scored on exactly the same well-weeks, and report omissions. The currently inspected v4 simulation rows share 6,052 core drought well-weeks, but the implementation does not enforce this invariant generally. Compare quality variants on a common subset as well as showing their full available populations.

**Keep cluster inference, but describe its limits.** The exact sign-flip enumeration is exact conditional on a sign-symmetry/exchangeability assumption and the chosen clustering. A fixed 10 km grid does not guarantee independent errors between adjacent cells. Retain the frozen primary test; add a small prespecified cluster-scale/origin sensitivity and leave-one-cluster-out influence analysis. Do not choose the clustering that yields significance. Spatial resampling estimates variation across this monitoring network conditional on the observed event; it does not turn one regional drought into many independent droughts.

**Separate uncertainty sources.** Five optimiser seeds measure training variability. They do not measure observational error, uncertain forcing volumes/timing, uncertain pump attribution, or response-family uncertainty. Present seed spread, reconstruction sensitivity and graph-policy sensitivity separately. If prediction intervals are added, assess empirical coverage and width on temporally separated evaluation periods and avoid claiming guaranteed calibration during a distribution shift. The groundwater modelling challenge provides a useful benchmark for treating uncertainty as an evaluated output. [Collenteur et al., 2024, DOI: 10.5194/hess-28-5193-2024](https://hess.copernicus.org/articles/28/5193/2024/)

**Add a compact hydrological error analysis.** Keep the agreed primary endpoints, but show bias, anomaly timing, amplitude, drought minimum/recovery timing and representative hydrographs, selected by a stated rule. Since the subject includes drought risk, evaluate the predicted SGI class with a confusion matrix and class-sensitive score; transform predictions using the frozen observed-reference distribution. Head RMSE alone is not a drought-class validation. Do not equate head change with water availability, sustainable yield or economic conflict without additional evidence.

**Resolve two temporal-definition discrepancies before reporting derived drought claims.** `src/dataset/build.py:195` uses all available monthly observations up to 2019 for SGI, without the stated 2005 lower bound; 27 core wells have pre-2005 observations in the v4 file. `src/models/chronos2.py:83` similarly supplies all panel rows up to the end date for fine-tuning, including warm-up years, despite the stated 2005–2019 training interval. The SGI issue is not future leakage, but its reference period must match the claim. For Chronos, distinguish allowable context from target dates contributing to training, and inspect the library sampling behaviour. Quantify the consequences and retain a documented sensitivity rather than silently rewriting prior results.

**Save models, not only predictions.** `lstm.py:230` saves prediction arrays and best-epoch metadata; the shared graph runner uses the same mechanism. The best network weights exist in memory during fitting but are not saved by these paths. The inspected v3 tree contains no `.pt`, `.pth` or `.ckpt` files. Stored predictions can reproduce a results table, but cannot generate explanations, interventions or predictions on future observations from those exact networks.

Before Phase 4, save the fitted model, preprocessing state, node/feature schema, graph export, dataset/source hashes, code commit, resolved configuration, seed, environment and selection history together. Pin the Chronos checkpoint revision and save its fitting configuration. Record Python, BLAS, torch/CUDA and solver versions where execution varies; the pinned CPU packages and ontology tool checks already provide a useful starting point.

**Make resumption validate identity and completeness.** Neural runners currently skip a seed when its file exists, overwrite `config.json`, and aggregate matching seed files. `assemble_lwo()` rejects an empty fold but accepts a partially completed one. A changed configuration can therefore inherit stale outputs, and a partially completed fold can look like a finished ensemble. Require matching run fingerprints and the exact expected seed set before a result is marked final. Include per-key prediction coverage and explicit failure status. A small cold rebuild and inference-replay check is more valuable than a large set of superficial unit tests.

## 8. Positioning the paper

The strongest prospective contribution is an auditable link between uncertain hydrogeological evidence, model assumptions, and measured explanation reliability. It should not rest on a claim that a groundwater GNN or hydrogeological graph prior is new.

Wu et al. already incorporate hydrogeological units into a groundwater graph model, alongside learned connections and explanatory analyses. Position this project's formal provenance, uncertainty treatment and validity experiments against that work. The publisher text also describes a validation/tuning protocol; the local matrix's wording about no separate validation should distinguish the lack of an explicit partition in the main description from an assertion that no validation occurred. Check the supplementary protocol before making a criticism. [Wu et al., 2025, DOI: 10.1029/2025WR041215](https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2025WR041215)

Domain topology need not improve prediction. A careful negative result can be informative if the experiment controls information, architecture and uncertainty, and establishes that the test could detect a benefit. [Kirschstein and Sun, 2024, arXiv:2405.19836](https://proceedings.mlr.press/v235/kirschstein24a.html)

Two already-listed papers remain important reading before finalising the hybrid novelty claim: **Chu et al.**, *A hybrid TFN–LSTM model for groundwater level forecasting in Rhode Island, USA* (DOI: 10.1016/j.jenvman.2026.130474), whose bibliographic record is confirmed by the [Pastas publication list](https://pastas.readthedocs.io/stable/about/publications.html), and **Jeong et al.**, *A physically interpretable transfer learning framework for improved generalization of data-driven groundwater level prediction* (DOI: 10.1016/j.watres.2026.126321), whose record is confirmed in [PubMed](https://pubmed.ncbi.nlm.nih.gov/42361754/). I did not obtain and assess their full methods here; their titles alone are not enough to assert what they omit.

Describe the Taccari baseline as an adaptation to the simulation task, since its input contract differs from a forecasting study with past heads. Keep a short claim–evidence–limitation table while writing: every novelty and effectiveness claim should identify the experiment or source that supports it. Draft the data and methods sections now, when definitions can still reveal omissions cheaply.

## 9. Recommended order of work

These are recommendations for subsequent work, not actions performed in this review. Existing remote runs can remain useful historical evidence; their existence does not require declaring their protocol final.

| Priority | Work | Concrete completion evidence |
|---|---|---|
| **P0: before declaring v4 final** | Consolidate available outputs; audit Pastas construction, objective and stability; distinguish fitted/scored populations; resolve incomplete-seed handling | One internally consistent v4 results manifest, with provisional rows clearly marked |
| **P0: before Phase 4 training** | Freeze the information-use contract, comparable C/D architecture, forcing inventory, graph policies and claim labels; save complete checkpoints/manifests | A reviewer can identify the single changed factor in each primary contrast and reproduce inference |
| **P0: before pumping interpretation** | Report accepted/unresolved volume by use and unit; define treatment of irrigation and group-only assignments | No excluded irrigation volume is interpreted as no irrigation effect |
| **P1: next implementation focus** | Finish the MUST CQ rules, tests and numerical export; exercise one complete provenance-to-prediction path | Independent table/graph export equivalence, conservation checks and informative failure cases |
| **P1: before broad sweeps** | Implement a minimal hybrid and a small twin; test signs, memory and attribution recovery | The system detects at least one case of accurate prediction with wrong driver attribution |
| **P1: main experiments** | Run the primary information, edge and constraint contrasts; repeat the essential contrasts across the three agreed pumping reconstructions | Paired effect sizes, cluster uncertainty and conclusion stability, with failures retained |
| **P2: thesis completeness** | Finish one dated land-use/irrigation chain, the bounded alignment/text-extraction work, and a small explanation interface | Evidence for the original subject's objectives without expanding the core modelling scope |
| **P2: independent checks** | Obtain domain review and better pumping/screen evidence; evaluate frozen models on genuinely new observations when available | Clearly separated empirical confirmation, sensitivity checks and illustrative cases |

Keep the full combination of architectures, graphs, constraints, regimes, reconstructions and evidence policies under control. Start with the primary contrasts and use the broader arms to answer specific unresolved questions. Estimate the run budget before launching; extra breadth should not displace complete checkpoints, a clean comparator or the twin.

**Research judgement:** the project is ready to move from infrastructure and baselines into its core scientific tests. Publication quality will depend on showing exactly what the knowledge contributes, where uncertainty prevents an explanation, and whether those conclusions survive honest controls. The existing work supports that direction; it does not yet support a claim that the knowledge-guided model works.
