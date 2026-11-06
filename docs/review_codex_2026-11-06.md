# Codex research and ontology review — 6 November 2026

**Verdict: substantial progress in evidence engineering, but the project is not yet ready to support its main publication claims.** Today's work makes the river/canal part inspectable and testable. The priority now is to correct evidence-scope errors, finish one executable KG-to-model-to-explanation path, and evaluate it under the already strong experimental plan. More ontology terms or more baseline runs alone will not close that gap.

This is a review, not an implementation change. Only this file was created. Severity below means **P1: resolve before freezing/exporting the research graph or enabling constraints; P2: resolve before claiming the affected capability is complete or releasing the reproducible workflow.** Research recommendations are distinguished from reproduced defects.

## Scope and evidence

- Reviewed the four commits dated **2026-11-06**, `deeb294`, `30832cf`, `1f23c2f`, and `c7555f5`, against `173361f2a1a914a6b621257daeab194938278631`: 38 files, 4,105 insertions and 104 deletions. This is the repository evidence for “what Claude did today”; commit authorship alone does not prove who wrote each line.
- Read the project brief, ontology design, competency-question contracts, analysis plan, today's notes, prior review response, alignment tools, saved results and graph release. The repository was initially clean. The review uses these local specifications; no issue-tracker setup is needed for this task.
- Checked the current graph release, dated **2026-11-06 09:32:04 UTC**: its bound hashes match, with **469,337 factual triples** and **163,097 rule-output triples**. A matching release demonstrates artifact consistency, not scientific correctness.
- Used independent read-only standards/spec reviews, as required by the code-review skill. Their findings are kept separate below; the scientific assessment adds source-level checks and analysis.
- Verification used `PFE_DATASET=v4` and disabled Python bytecode writes. Queries and metric checks ran in memory; temporary tool outputs stayed outside the repository. No data rebuild, model training, source edit or report regeneration was performed.

## What today's work actually achieved

The new module combines BD TOPO reaches, Sandre river sections, existing gauges, geological polygons and curated documentary evidence. It distinguishes rivers on a unit's outcrop, rivers above its cover, and proposed documented lateral exchanges. Canal answers explicitly retain the missing command-area link. These distinctions are valuable: a map intersection, an exchange observation, a model input and a causal constraint are different things.

The strongest additions are the source passages and their provenance, explicit exchange states and dates, opposing statements retained together, the shared five-gauge pool for C and D, and tests against geospatial/table computations. I reran the evidence checks: **all 32 quotations were found on their stated pages**, with document checksums, section coordinates, codes and negative controls passing. That is a useful provenance check; it does not establish that each quotation entails the structured assertion derived from it.

The release reports **43 river influences across 35 wells, including 24 core wells**, and **5 canal influences across 5 wells, including 4 core wells**. Eight river influences across seven wells and two canal influences are marked eligible for constraints. Treat these as current implementation counts, subject to the evidence-scope corrections below—not as independently validated hydraulic connections.

Today's commits do **not** demonstrate improved simulation, successful ontology alignment, faithful explanations or causal identification. The graph export and main model experiments remain unfinished; the AGROVOC gold file still has **0 labelled rows out of 198**. CQ6 is an implemented *partial answer*, not a completed intake-to-parcel pathway.

## Standards

### S1 — P1: repair the graph quality gate's WKT parser

`CLAUDE.md` §6.12 requires ontology changes to pass their quality gates. New gauge geometries from `src/kg/rivers.py:236` serialize as `POINT (...)`; `tests/test_kg.py:283` accepts only `POINT(...)`. Valid coordinates become NaNs and trigger the misleading assertion **“a point off dept 66.”**

**Reproduced:** the full graph test fails there. Independently parsing all point literals with Shapely found **2,478 points, 45 rejected by the regex, and zero outside the existing numeric bounds**. The 45 are gauge geometries. This is a test-parser defect, not evidence of misplaced stations.

**Fix:** parse WKT with a geometry library after handling the CRS prefix; retain CRS and coordinate checks. Add fixtures for both whitespace forms and a genuinely invalid/out-of-bounds geometry. Do not widen the box or delete gauges to obtain a passing test.

### S2 — P2: make document ingestion recover from interruption

`CLAUDE.md` §6.1 requires idempotent, cached ingestion. `src/ingest/documents.py:59` writes each file, but line 66 saves the index only after all downloads succeed. If a later request fails, earlier files survive without metadata. On restart, line 52 skips those files and line 64 accesses a missing `log[key]`, causing `KeyError`.

**Fix:** persist each successful download and its metadata safely, and handle cached-but-unindexed files explicitly without fabricating an original retrieval date. Verify recovery after an injected failure between documents. This finding follows directly from the control flow; I did not interrupt real downloads.

**Standards summary: two confirmed findings. The immediate gate failure is S1. No cosmetic code-smell finding justifies distracting from these defects.**

## Spec

### Q1 — P1: CQ8 labels an incomplete geological search as complete

The common CQ contract says an “unsearched or uncovered area must not” produce an empty supported result (`docs/competency_questions.md:81`). However, `tests/cq/cq08_status.rq:143` treats the existence of a search zone as completion; its river result does not examine off-map reach pieces.

**Reproduced on the hash-validated release:** **BSS002MVJS** has off-map river pieces. CQ5 returns `partial`; CQ8 returns `river=none_found` with a reason explicitly calling the search complete. The overall CQ8 answer being `partial` does not repair that false per-mechanism explanation.

**Fix/acceptance:** propagate explicit coverage/completion per mechanism into CQ8. With relevant uncovered pieces, report incomplete/unknown rather than a completed negative. Add this real case and an analogous canal fixture; retain genuine completed-empty searches as negative answers.

### Q2 — P2: CQ5 hides incomplete coverage when some supporting evidence exists

CQ5 requires “partial when … part of the reaches is off the map” (`docs/competency_questions.md:297`). In `tests/cq/cq05_status.rq:75`, the supported-evidence branch precedes the off-map branch.

**Reproduced:** **BSS002MQNK** receives `supported` despite off-map river pieces. Keep its supported individual associations, but report the overall search as partial. Test the combination of a supported association **and** uncovered reaches; testing them separately misses this defect.

### Q3 — P2: a named-well observation is applied to another well

The evidence contract requires “Where and when the assertion applies” (`docs/competency_questions.md:73`). `canalApplicableStatement`, `ontology/rules/lulcw-rules.ttl:1049`, joins only on unit and mechanism, ignoring `measuredAt`.

**Reproduced:** `brgm-c2-1-mixing`, a September 2017 observation at **MILLAS C2-1**, becomes applicable to both C2-1 and **BSS002MREZ / 10915X0395/PZ**. Recording the original location does not prevent this unqualified transfer.

**Fix/acceptance:** distinguish evidence observed at a well from a hypothesis transferred to another location. A different well must not inherit local measurements as local evidence. General unit-level statements may independently support the existing edge; this finding does not imply every affected edge must disappear.

No material unrequested scope expansion was found: the five-gauge pool, cover/lateral distinction and partial canal chain follow the approved amendment. **Temporal/policy functionality remains partial:** CQ5 specifies `U,S,T` and policy, while the query signatures expose `U,S` or `S`. Displaying dates is useful, but is not period-specific evidence selection.

**Spec summary: three confirmed defects, plus the stated temporal/policy limitation. The most consequential contract failure is Q1's false completed-search answer.**

## Ontology alignment and hydrogeological foundations

### R1 — P1: groundwater-body evidence is promoted to exact-unit evidence

This is the most important additional scientific finding. In `configs/exchange_evidence.csv`, the FRDG351 river-section statements list **all eight constituent BD LISA units** as their `units`. `src/kg/rivers.py:446` converts each membership into an `aboutUnit` assertion. The lateral rule at `ontology/rules/lulcw-rules.ttl:823` then interprets it as documentary evidence of exchange with that particular unit.

The source identifies eight units belonging to the groundwater body; its river table characterizes exchanges at groundwater-body/surface-water-body scale under low-flow conditions. Membership of an aggregate does not entail that every constituent individually participates in each exchange. The source also describes downstream merging of some alluvial formations, so a cross-unit connection is possible; it still requires a localized argument. See the [FRDG351 characterization, pp. 1–4](https://www.rhone-mediterranee.eaufrance.fr/sites/sierm/files/underground_waterbody/FRDG351.pdf).

**Observed consequences in the released graph:**

| Well | Assigned unit | Derived lateral association | Applicable evidence |
|---|---|---|---|
| BSS002MREZ / 10915X0395/PZ | `718BP02`, recent Têt alluvium | Agly `Y06-0400` | Only `frdg351-frdr211` |
| BSS002MQGM / HIPPO2 | `671AB01`, ancient Agly alluvium | Agly `Y06-0400` | Only `frdg351-frdr211` |

Both drive river influences from gauge `Y066404001` marked `EligibleConstraint`. Two other lateral associations have additional BRGM evidence. Thus **two of the four current lateral associations rely solely on the aggregate-to-unit promotion**. This does not prove either physical connection false; it establishes that the stored “documented” exact-unit justification is stronger than the cited evidence.

**Fix:** retain the original groundwater-body subject and evidence resolution. Represent any allocation to a BD LISA unit as a separate, reviewed inference with its own rationale, spatial scope and confidence. Body-level evidence alone must not authorize an exact-unit lateral connection or sign. Audit all 32 structured statements for entailment, not just quote occurrence.

**Acceptance:** a synthetic body containing units A and B with an exchange statement about the body cannot automatically generate “documented lateral exchange with B.” Re-evaluate the four real lateral associations and publish the resulting change in counts and eligibility.

### R2 — P1 before hard constraints: a proxy requires its own sign justification

Today's design correctly distinguishes **exchange direction** from **response to river stage**. However, the actual input is **remote gauge discharge**. The RIV formulation uses river stage, riverbed conductance and bed elevation; it does not establish a monotonic relation from a distant discharge series to local groundwater head. The simple linear exchange equation is also conditional on the hydraulic regime. See the [USGS RIV documentation](https://water.usgs.gov/ogw/modflow/MODFLOW-2005-Guide/riv.html).

My assessment: the physical argument can motivate a local stage-response prior under specified conditions. It cannot alone validate a hard derivative constraint on remote discharge. Diversions, regulation and intervening reaches are already acknowledged in the notes, but acknowledging them in prose does not encode their implications for constraint selection.

The canal analogue is equally important. The input sums **181 surface-water intakes across the plain**; a positive local response to additional infiltrating canal water does not establish a universally positive response to an increase in that aggregate. Which intake changes, where the water goes, return fractions and coupled river changes all matter. A partial chain can support an exploratory predictor while remaining insufficient for a hard physical intervention claim.

**Recommendation for Gate 3:** separate `pathwayEvidenceAccepted`, `proxyAdequacyReviewed` and `constraintApproved` in the export policy, or equivalent explicit fields. Default proxy-based river/canal hard constraints to off pending review. Keep unconstrained edges and a declared soft-prior sensitivity where justified. Test physical interventions through the complete preprocessing and model path, as the analysis plan already requires. This is a scientific refinement of the approved plan, not an allegation that Claude ignored that plan.

### R3 — P2: the HY_FlowPath subclass mapping is not sufficiently justified

`ontology/alignments/lulcw-hyf.ttl:31` asserts every `HydrographicReach` is a `HY_FlowPath`, including canal reaches. The local reach is a mapped network segment. HY_Features defines a flowpath as a **realization of a catchment**, connecting that catchment's inflow and outflow. Two endpoints alone do not establish that interpretation. See [OGC HY_Features §7.3.2.8](https://docs.ogc.org/is/14-111r6/14-111r6.html).

The mapping is therefore insufficiently demonstrated for **every instance**, the standard required by `docs/ontology_design.md` §2. This is a semantic review finding, not a detected OWL inconsistency. Missing catchment triples alone are not an OWL contradiction under open-world semantics.

**Fix:** either justify a restricted class of reaches as catchment flowpath realizations, with the appropriate context, or keep the general reach mapping as a documented candidate until that interpretation is established. Preserve verbatim upstream vocabulary statements separately from local axioms. In particular, the local import explicitly translates a source `skos:broader` relation into `rdfs:subClassOf`; that is a local modeling commitment, not merely a copied upstream axiom. SKOS conceptual mappings and OWL class entailments must remain distinct ([W3C SKOS Reference](https://www.w3.org/TR/skos-reference/)).

For the whole ontology network, add a compact alignment ledger: source and target, relation, definition comparison, counterexample considered, source version, reviewer and status. Evaluate useful entailments **and forbidden entailments**. Reasoner consistency is necessary but cannot validate the intended scientific meaning of weakly axiomatized imports.

### R4 — P2: preserve space, time and evidence type through the reasoning

`cq05_status.rq:25` aggregates opposite directions across the entire `(unit, zone)` pair. It does not establish that the claims concern the same river segment and overlapping period. Consequently it can call ordinary spatial variation or seasonal reversal a conflict. Preserve the existing source disagreements, but distinguish **opposing recorded states**, **unresolved scope**, and **contradictory claims under comparable conditions**.

Add requested-period handling to CQ5/CQ6, including an explicit result for undated evidence. A 2017 campaign and a 2021 synthesis can inform a static hypothesis, but should not silently become observations valid throughout every modeled week.

All exchange statements currently receive `ExpertHypothesis` (`src/kg/rivers.py:466`). This conforms to the project's broad definition, but obscures differences between field measurements, geochemical mixing estimates, literature summaries and expert assumptions. Add a method/evidence subtype; keep scientific confidence separate from whether the author used assertive or hedged language. Assertive wording is not evidence calibration.

## What the current results support

I recomputed the following medians directly from `results/v4/*/metrics_per_well.csv`, selecting `split=test_drought`, `variant=all`, `core=True`: **33 wells in every row**. These are existing exploratory baseline results, not gains produced by today's work.

| Simulation method | Median drought NSE | Median skill against training climatology |
|---|---:|---:|
| Climatology | -1.494 | 0.000 |
| Pastas, training heads only, best start | -0.753 | 0.224 |
| Tuned LightGBM | -0.083 | 0.493 |
| Tuned LSTM | 0.124 | 0.567 |
| Distance-graph ST-GNN | 0.055 | 0.551 |
| Adapted Taccari-graph ST-GNN | -0.055 | 0.485 |
| Validation-selected ensemble | 0.143 | 0.512 |

There is useful improvement over climatology, but absolute drought NSE is modest. The graph baselines do not establish an advantage over the LSTM. The rows change more than graph policy, so they cannot isolate the value of knowledge or topology. Compare the future D model against strong neural baselines as well as Pastas; beating a negative-NSE physical baseline alone would be an insufficient main result.

Keep uncertainty and aggregation clear. The baseline report distinguishes the saved aggregate-prediction score from single-seed performance; for example its LSTM single-seed drought NSE summary is **-0.05 ± 0.14**, versus **0.124** for the saved aggregate predictions. Report both rather than presenting ensemble performance as the typical single fit. Median NSE and median skill need not rank methods identically, and a difference of medians is not a median paired improvement.

The land-use experiment is useful negative evidence. `results/v4/land_use_test.csv` reports the main paired NSE contrasts:

- LightGBM: **+0.0159**, 95% interval **[-0.0416, +0.0513]**.
- LSTM: **+0.0013**, 95% interval **[-0.0459, +0.1632]**.

Both intervals include zero. The defensible statement remains **no detectable benefit from this index under these models, settings, wells and drought period**. It does not establish that land use is irrelevant, and it does not establish practical equivalence. The broad LSTM interval leaves meaningful gains possible. The same-machine comparison was a good correction and should become mandatory for the main contrasts.

The statistical foundation has improved since the previous review: exact scored-week digests, spatial cluster inference, a declared multiplicity family, grouped holdouts and explicit disclosure that the drought benchmark influenced development. Preserve those decisions. Do not retune on the drought results until a preferred story emerges. Recovery evidence is still limited by validated coverage, and the existing plan correctly reserves independent checking for genuinely post-freeze observations.

## How to obtain stronger, publishable evidence

### 1. Make the next milestone an executable scientific example

Finish the **two-well vertical slice** already planned: one alluvial well and one Pliocene well, from source records through qualified assertions, selected graph edges, model prediction and driver contributions to a query-backed explanation. Include one missing-path case and one disputed-evidence case.

Acceptance is a reproducible artifact that shows input units, graph release, policies, model/checkpoint identity, prediction, reference condition, contributions, residual and exact evidence citations. The contributions must reconstruct the prediction, but that numerical identity alone must not be called causal recovery. The explanation must distinguish “the model attributes” from “the observation demonstrates.”

### 2. Complete the shared export and audit the actual information reaching each well

The existing contract for C–F is sound: fixed node/feature inventory, backbone, response family, budget, split and seeds; change the connection policy. Implement the promised per-well/per-relation inventory **before scoring**: direct inputs, reachable inputs at the actual message-passing depth, missing sources, weights and signs.

D currently gives river inputs to 24 of 33 core wells, while C's policy supplies two nearby pool gauges per well. Eighteen wells have river associations only over cover. The raw D-versus-C contrast therefore measures the whole connection policy, including restriction of access to inputs. Call it that unless the prespecified matched diagnostic supports a narrower routing claim. Keep the already planned coverage/distance/degree controls; do not add a large uncontrolled grid of new arms.

Export identity should include the graph release, feature schemas, units, relation direction, weights, temporal alignment and constraint policy. Finish the independent pandas equivalence test and fixed-weight forward-pass comparison. Multiple paths between one gauge and well must have a declared aggregation rule so that duplicated associations do not silently amplify a signal.

### 3. Use the small synthetic twin to test whether the scientific tests work

Build it before broad training, as already planned. Include independent and climate-correlated pumping, an omitted driver, nonlinear/delayed responses, wrong unit assignments and multiple generator/noise draws. Keep the truth graph separate from the learner graph.

Acceptance: show at least one case with good predictive accuracy but wrong contributions that the shortcut/faithfulness tests detect, and one correct case they retain. Then measure false alarms and detection across draws. A model recovering its own generating equations is not enough. Pastas coefficients remain a comparator, not causal truth.

### 4. Finish a bounded, defensible alignment experiment

The current **40 dev / 158 evaluation** split, alternative targets, explicit SKOS relations and planned blind second annotation are good foundations. The work is still preparation, not measured alignment performance.

Before annotation, finalize the plant-versus-product-versus-land-use rules, composite/residual codes and abstention policy. Then compare lexical, retrieval and local-LLM matchers under the same input conditions. Add these acceptance criteria:

- Report **candidate recall@k** separately from matching accuracy. A reranker cannot recover a target absent from its candidate set.
- Report **joint target-and-relation correctness**, not only target correctness and relation accuracy conditional on a correct target. Keep strict/alternative-target scoring and no-match errors visible.
- Audit near-duplicate crop labels across dev/eval; report any grouping sensitivity without replacing the frozen split after results are seen.
- Preserve the blind second annotations and adjudication. The selected 30-code subset emphasizes common/difficult codes, so its agreement is not automatically representative of all 198 codes.
- Call this an **RPG-to-AGROVOC concept/code alignment benchmark**. It is not evidence that arbitrary OWL ontology alignment has been solved, and successful crop matching does not validate irrigation status or crop coefficients.

For the schema alignments to GWML2, SWEET and HY_Features, prioritize the entailment ledger and domain review over adding vocabulary names. Count useful, justified correspondences rather than imported terms.

### 5. Strengthen the data where it can change the conclusion

The agricultural chain is weakest at water delivery and pumping attribution. The main pumping policy still leaves irrigation unassigned; parcel demand is not actual irrigation; the canal feature is an aggregate. A bounded request for canal service/perimeter data, a local pumping series or a review of the two example wells is more valuable than adding an unrelated model family.

Evaluate the planned satellite rule against independent irrigation evidence, or explicitly retain it as a heuristic. Crop labels and the demand assumptions used to construct the rule cannot independently validate it. Small alluvial subgroups warrant descriptive cases and uncertainty, not strong subgroup claims. Keep the drinking-water-pressure framing for the main Pliocene analysis until the evidence supports broader agricultural attribution.

### 6. Freeze a reproducible experiment, then complete the planned contrasts

Preserve the existing exploratory/pre-specified/independent-check distinctions in `docs/analysis_plan.md` §11. Use the same machine type or a matched control, five neural seeds, exact paired support and the declared cluster/multiplicity procedure. Report effect sizes, intervals and failure cases, not only whether a p-value crosses a threshold.

`docs/run_inventory_v4.md` lists **38 replayable runs, 18 prediction-only, 4 recomputable and 1 partly replayable**. Prediction-only runs can support rescoring, but not future interventions or frozen-model confirmation. Rerun only the reference models needed for those tasks under new, complete identities.

The graph manifest currently records `30832cf+uncommitted` for facts/rules code. Its content hashes usefully bind the released graph and ontology, but do not fully identify the Python builder or every raw input. For publication, bind the build code/configuration and raw snapshot hashes as well; pin snapshot selection rather than silently choosing the newest directory. Package a small executable example plus retrieval/rebuild instructions for the larger data. Include outstanding namespace, attribution and ontology quality-gate work in the release checklist already required by the project.

## Publication position and order of work

The defensible contribution is a **traceable method for translating uncertain hydrogeological knowledge into graph connections and conditional model constraints, with tests of when those choices help and when explanations fail**. A KG connected to a GNN is not by itself enough novelty: groundwater graph models and modular water KGs already exist, including [Taccari et al. (2024)](https://www.nature.com/articles/s41598-024-75385-2) and [WHOW-KG (2025)](https://www.nature.com/articles/s41597-025-04537-4). Establish the precise difference against the closest studies in the existing literature table; avoid an unverified “first” claim.

| Order | Deliverable | Completion criterion |
|---|---|---|
| 1 | Correct scientific evidence scope and query coverage; repair the WKT gate | R1 and Q1–Q3 have adversarial regression cases; the graph suite passes; changed link/eligibility counts are documented |
| 2 | Bounded domain review and constraint decision | Two wells reviewed; body-to-unit transfers, remote-discharge proxies and aggregate canal inputs have explicit accepted/rejected/unknown decisions |
| 3 | Shared export and two-well executable example | Release-bound graph/model artifacts; per-well inventory; independent table equivalence including a forward pass; prediction and contribution explanation reproduced |
| 4 | Alignment evaluation and small twin | Frozen gold/matcher protocol; measured alignment outcomes; demonstrated shortcut-test detection and false-alarm behavior |
| 5 | Frozen main experiments | Matched C–F comparisons, B–A and constraint comparisons; declared seeds/support/inference; checkpoints retained |
| 6 | Submission artifact and claims audit | Every substantive claim points to an experiment, source or explicit limitation; independent check reported if adequate; no unsupported causal or transfer claim |

The project can become publishable without uniformly winning every metric. A convincing result could show that knowledge improves plausibility or explanation reliability only under sufficiently specific evidence, while weak or overly broad knowledge harms performance. But that conclusion requires the model, controls and falsification experiments to exist. At present, the progress is strongest in building the research infrastructure; the next phase must convert it into measured scientific evidence.

## Verification record and limits

- `tests.test_ontology`: **passed**, including all 13 catalog modules, 367 local terms, ELK, HermiT, the inconsistency negative control and ROBOT report (no ERROR; 18 INFO/WARN rows).
- `tests.test_exchange_evidence`: **passed**, all five checks.
- `tests.test_kg`: **failed**, reproduced at line 284; diagnosed as S1. Its later checks do not run after that assertion, so this review does not claim the whole suite passed.
- Release hash verification: **passed**. Current stored validation reports eight informational missing-depth results and no violation. A fresh full production SHACL rebuild was not run.
- Independent checks: baseline medians and gold-set completion counted directly; point geometries parsed independently; incomplete-search and evidence-application examples queried from the released graph.
- `tests.test_kg_rules`: **passed**, including the fixture graph, all 47 negative controls and the production table/geospatial comparisons. These checks validate the implemented derivations; R1 shows why separate tests of source entailment are also needed.
- `tests.test_cq`: **passed**, all 17 fixture/data checks, including river/canal checks across 65 wells. Q1–Q3 are additional counterexamples beyond the cases those tests currently enforce; a passing suite does not negate them.
- OOPS! remains a separately documented pending gate; I did not submit project content to that external service. No claim here that all ontology/publication gates are complete.
- External checks used OGC, W3C and USGS primary documentation and the FRDG351 source. The BRGM web fetch was unavailable; its local stored document and quotations were available and passed the source checks. This was a targeted review, not an exhaustive systematic literature search or an independent hydrogeological field validation.
