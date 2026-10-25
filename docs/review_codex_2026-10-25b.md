# Codex project review — 2026-10-25

**Yes: the project is going in the right direction, and Claude's recent work is useful. The land-use correction brings the implementation closer to the original subject. However, the current land-use branch is unfinished integration work, not yet a validated experiment. Finish and freeze that work before launching its model runs.**

This review covers `Documents/sujet.docx`, the project brief, analysis plan, roadmap, recent review responses, local results and implementation. The code comparison starts at `0411ecc` (the subject-alignment review), includes commit `f03573d`, and includes the existing uncommitted changes. Findings describe the local snapshot reviewed today; ongoing downloads or later rebuilds can change its readiness. No cloud job status was checked and no model was trained.

Only this file was added. The existing edits and generated files were left untouched. Recommendations below are review notes, not changes to the approved design or experimental plan.

## Project state and direction

| Area | Evidence now | Assessment |
|---|---|---|
| Data and evaluation | Dataset v4, grouped spatial evaluation, uncertainty-aware pumping attribution, saved results; pumping and statistics checks pass | A substantial foundation worth preserving |
| Baselines | The interim v4 report gives drought median NSE 0.12 for LSTM, 0.14 for the ensemble, 0.06 for distance ST-GNN and −0.05 for Taccari ST-GNN | Useful benchmarks, but no demonstrated advantage from graph structure yet; these are not results for the planned KG-guided model |
| Ontology and factual KG | The real-data KG test passes: 205,650 triples, 65 piezometers, 2,187 groundwater facilities, 12,951 annual records, with negative controls | Real semantic infrastructure, beyond a diagram or vocabulary list |
| Land use | Crop mapping, clipped areas, calendars, demand features, placebo and reconstruction code exist | Correct direction; local artifacts and tests currently lag behind the latest code |
| Main contribution | SHACL-AF derivation, model export, hybrid constraints and faithful output explanations remain scheduled | This is the next essential connection to deliver |
| Satellite semantics and alignment | Independent irrigation validation and RPG → AGROVOC evaluation remain planned | Keep these visible as outstanding subject objectives |

Sources: `docs/results_baselines_v4.md`, `CLAUDE.md` §7, `docs/notes/step12d_land_use.md`, and the checks below. The original subject asks for land-use knowledge to guide and explain a model. A better groundwater benchmark alone cannot satisfy that requirement. The new land-use thread addresses this directly. Remaining Phase 3 work is expected at this point in the schedule, rather than evidence of failure.

Claude has made several good choices: retaining uncertainty in pump attribution; distinguishing potential demand from measured irrigation; retaining a main index and a wider sensitivity; using fixed baseline settings; documenting the geographical clipping and calendar corrections; and reporting LU-4 as not yet run. Keep that discipline. The weak spot is completion control: prose saying that checks passed needs to identify the exact input/code snapshot to which it applies.

## Current verification: two land-use checks do not pass

Executed with `PFE_DATASET=v4`, the existing `.venv/bin/python`, bytecode writing disabled, and temporary plotting caches outside the repository. These checks did not train models or rebuild saved project artifacts.

| Check | Result |
|---|---|
| `tests.test_kg` | **PASS**, including source-table comparisons and both negative controls |
| `tests.test_stats` | **PASS**, including the cluster-test checks |
| `tests.test_pumping_conservation` | **PASS**: 2,308,950 weekly rows reproduced in memory; declared/annual/weekly accounting checks pass |
| `tests.test_crop_demand` | **FAIL**: synthetic checks pass, then the stored-file check raises `KeyError: demand_main_m3` at line 102 |
| `tests.test_pumping_cropcal` | **FAIL**: the synthetic summer/non-summer weight-ratio assertion at line 49 fails |

The demand parquet still contains the older `demand_irrigable_m3` / `demand_irrigable_placebo_m3` schema. The current code requires `demand_main_m3`, `demand_main_placebo_m3` and `demand_wide_m3`. Rebuild the derived files and panels after completing the source snapshot.

For the crop-calendar test, I independently measured a summer/non-summer ratio of **4.427**, against the test's required value greater than 5. The weights are finite and their annual sums are approximately 1. This failure does **not** establish that the new calendar is physically wrong: the fixture/expectation needs reassessment after changing the included crop classes. Check the scientific invariant before changing either the threshold or implementation; do not tune the formula just to pass the assertion.

`data/interim/pumping_weekly_cropcal_v4.parquet` is absent, so current real-data validation of reconstruction (3) could not be performed. Historical statements in the step note are not verification of the current main-index version.

## Standards

Two consequential findings against the documented reproducibility rules; no stylistic refactoring is a priority.

1. **P1 — Include the actual land-use inputs in run identity and resume checks.** `src/models/features.py:104` reads an additional demand parquet, while `src/models/manifest.py:26` and `:69` hash only the existing dataset file list. Neither the crop-class CSV nor the resolved land-use panel is captured. LightGBM's manifest configuration (`src/models/lgbm.py:156`) also omits the land-use mode; on/placebo/wide share input column names. This leaves the provenance promised by `docs/analysis_plan.md` §9 incomplete.

   More seriously, `src/models/lstm.py:264` fingerprints settings and input names, while `schema_of()` records training statistics. An in-memory check using synthetic demand columns on the existing panel confirmed that changing only 2023-onward values leaves both the fingerprint and schema unchanged. The resume loop at `:365` then accepts old seed predictions while unfinished seeds use the revised inputs. **This is a code-level risk, not evidence that existing results are already mixed.** Record the variant, resolved panel content hash, crop assumptions and source-edition manifest; reject incompatible cached seeds. Bundled panel caches need the same identity even when raw sources are unavailable remotely.

2. **P2 — Include coordinates in the crop-area cache key.** `src/dataset/crop_demand.py:173` records well identifiers but not their coordinates. Correcting a well's location while retaining its identifier can return the old buffer areas, whereas a cold rebuild produces different areas. Include coordinates, CRS and a calculation version. This follows `CLAUDE.md` rule 1: “Nothing is done until it runs from cold.”

**Standards: two findings; the most consequential is potentially mixing predictions produced from different land-use inputs.**

## Spec

Two implementation-readiness gaps against the adopted land-use experiment. The feature paths, fixed tuned settings, main/wide distinction and training-climate reconstruction broadly follow the specification; I found no material scope expansion in this change.

1. **Complete the prescribed comparison report.** `docs/analysis_plan.md:593` specifies models “each with and without the feature” and “cluster sign-flip, Holm over the two models.” The runners produce individual evaluations, but `src/analysis/baseline_report.py:26` lists no land-use runs, and its significance function at `:184` compares models against Pastas. LU-4 needs its own paired contrasts: land-use-on versus the same model without land use, with matched scoring support, the prescribed correction family, and main/placebo/wide rows. Merely adding these runs to the existing significance table would answer a different question.

2. **Gate LU-4 on a completed, rebuilt input snapshot.** The specification uses “clipped area within 3 km in RPG year y” (`docs/analysis_plan.md:576`). At inspection, department clips exist for 2015–2017 and 2019–2024, but not 2018 or 2025. The area cache contains only **2015, 2016, 2017 and 2023**. The saved demand index therefore uses 2017 for 2019–2022 despite newer source clips now being present. No `panel_lu_*.parquet` caches or land-use result folders exist locally. Missing-year substitution is documented and is not itself a bug; this unfinished snapshot must not be presented as the completed annual experiment. The notes correctly anticipate a final rebuild. Make its completion verifiable through an edition/lag inventory, current schemas, generated panels and passing checks before packaging.

**Spec: two readiness gaps; the most consequential is the missing prescribed land-use comparison report.**

## Advice for Claude and Assil

**Make the next milestone a complete vertical path.** For one alluvial well and one Pliocene well, demonstrate dated parcel observations → crop class and assumptions → KG evidence and derived influence → exported model input. In early Phase 4, extend the same example to one model output and its contribution trace before multiplying model variants. This keeps ontology, land use and explanations tied to the thesis objective. Complete the remaining baseline reruns, but avoid adding model families or tools without a specific unanswered question.

**Separate evidence about agricultural geography from evidence about land-use change.** The existing spatial placebo is useful, but the statement at `src/dataset/crop_demand.py:45` that beating it establishes crop-information use rather than a well signature is too strong. One permutation cannot isolate static geography, changing registration coverage and actual crop transitions. The project already documents a registration effect. I recommend considering the step note's fixed-crop-mix sensitivity, using an edition chosen from the training period, before making a claim about annual change. This would be a recorded amendment, not a change silently made by this review. For an initial LU-4 result, “incremental predictive information from the demand index” is an appropriately narrow claim. The cited [Heudorfer et al. study](https://hess.copernicus.org/articles/28/525/2024/) motivates identifier controls; it does not validate this particular permutation design.

**Preserve the distinction between demand, withdrawals and recharge in the KG.** Crop demand does not identify a parcel's water source or actual irrigation volume. Before assigning it a response sign in the hybrid, specify whether it modifies groundwater abstraction, canal-return recharge or another explicitly qualified pathway. Avoid counting the same assumed withdrawal once through reconstructed pumping and again as an independent crop-demand effect. Unknown sources should remain unknown. The simplified demand calculation is reasonable as an index: [FAO-56 chapter 6](https://www.fao.org/4/X0490E/x0490e0b.htm) defines crop evapotranspiration under standard conditions and discusses adjusting coefficients and stages. It does not turn this weekly index into measured irrigation or a validated local water balance.

**Keep conclusions proportional to the evidence.** The interim drought scores leave substantial error, and stronger baseline skill does not establish causal explanations. Keep simulation/hindcast wording, provisional recovery results, model-attributed contributions and the already-examined benchmark limitation. A null land-use or graph result is acceptable if the experiment is complete and the interpretation is honest. The ontology's traceability and consistency can still be demonstrated independently of an accuracy gain.

**Reconcile the working documents at the next normal documentation update.** `docs/analysis_plan.md:493` still describes land use as static RPG 2016/2023 context, while §14 introduces annual demand. `docs/roadmap.md` still contains laptop-training instructions and an outdated statement that Kaggle is unavailable, conflicting with the newer brief. Keep completed evidence, work in progress and future commitments visibly distinct; the original-subject coverage table currently reads more like a delivery plan than a completed-results table.

Recommended order: complete and freeze the land-use source/derived snapshot; resolve the failing checks and provenance gaps; implement the paired report; run the planned LU-4 comparison; continue SHACL rules, CQ tests and graph export toward the two-well demonstration. The foundation is strong enough to proceed without redesigning the project.
