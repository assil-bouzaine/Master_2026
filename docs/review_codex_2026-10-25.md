# Codex review — Keep the LULC-Water project aligned with its subject

**Date:** 25 October 2026  
**Author:** Codex  
**Purpose:** Assil requested a recurring reminder for Claude about the project's big picture, especially the land-use ideas that have received too little implementation attention.  
**Basis:** `Documents/sujet.docx`, the current project plans and relevant local code. Snapshot: `01930b4` plus the existing working-tree changes. This is a subject-alignment review, not a new audit of model scores. No models or tests were run for it.

**Claude: revisit this file at the start of a project session, before changing priorities, and before declaring a phase complete.** Read it alongside the original subject and the latest user instructions. The findings below describe 25 October 2026; later progress should be checked against concrete files and results. A planned task or a written response does not by itself close a gap.

**The big picture**

The subject is about understanding **how land use and agricultural practices interact with water resources**, representing that knowledge through aligned ontologies, and using it to guide deep learning and explain water risks in the Mediterranean.

Keep this chain visible throughout the project:

> Dated land use and agricultural practices → water demand and supported hydrological pathways → an ontology-guided model → groundwater conditions and drought risk → an explanation a decision-maker can understand.

These arrows represent relationships to document and test. They do not establish causality merely because they appear in an ontology.

The current groundwater dataset, baselines and knowledge graph are valuable foundations. **The project remains broadly aligned, but its implementation has shifted toward groundwater, pumping and model comparisons. The land-use-to-water connection is still underdeveloped.**

Several ideas have already been restored to the written plan. Calling them completely forgotten would be inaccurate. The concern is that they remain planned or secondary while the hydrological work keeps growing.

**What the original subject still requires us to keep in view**

| Original idea | Evidence and position today | Reminder for the next work |
|---|---|---|
| Land use, crops and agricultural practices affect water | RPG 2016/2023 ingestion and profiling exist. The shared baseline feature builder uses weather, pumping, rivers and well attributes; it does not yet integrate dated crop information. | Make land use an explicit, traceable part of the semantic and modelling pipeline. A crop chart alone does not demonstrate its role in the model. |
| Alignment across land and water vocabularies | Groundwater ontology modules and alignments exist. RPG-to-AGROVOC alignment is still task 12.9; CQ7 specifies dated crop mappings and demand estimates. | Complete a small land-use alignment example and show what it enables downstream. |
| Semantic enrichment of satellite observations | The probable-irrigation concept is specified in CQ15; the satellite implementation remains task 12.10. | Demonstrate the observation-to-concept rule with dates, evidence and uncertainty. Report heuristic status if independent validation is unavailable. |
| Ontology-guided deep learning | The factual KG exists. Rules, queries and model export remain tasks 12.6–12.8; the main hybrid model remains planned. | Demonstrate how a named semantic relation changes model inputs, graph structure or an applicable constraint. |
| Explanations grounded in the ontology | CQ10 and the explanation phase are specified. The educational project explainer is already present. | Produce explanations of actual model outputs, with evidence paths and faithfulness checks. Explaining the project to a reader is a different deliverable. |
| Prediction of future water risks | The main contribution now focuses on simulation. Forecast baselines use reconstructed inputs and are described as hindcasts. | Make this departure from the subject explicit. A simulation result alone does not establish advance warning of future risk. |
| Decision support and mitigation scenarios | CQ16 describes a crop-change scenario, but it is conditional and lacks the required model and supporting links. | Keep one modest scenario/query demonstration in view, with assumptions and unsupported cases clearly reported. |

Sources: [project brief and task status](../CLAUDE.md), [roadmap](roadmap.md), [competency questions](competency_questions.md), [RPG work](notes/step05_rpg.md), [baseline features](../src/models/features.py), [KG builder](../src/kg/build_kg.py), and [project explainer](explainer/README.md).

**The most consequential gap: agriculture and irrigation**

The [pump-coverage report](pump_coverage.md) records **0% accepted irrigation volume under the main confident-plus-probable attribution policy** in the plain's declared-year accounting. This means the accepted pump-to-unit links currently cannot substantiate the agricultural pathway. It does not mean irrigation is absent, or that its volume should become zero in the model.

The [24 October review response](review_codex_2026-10-24_response.md) records a decision to centre the main pumping story on drinking water and restrict irrigation claims to the all-links sensitivity. That is a reasonable response to the available attribution evidence. However, **a drinking-water result does not establish the land-use and agricultural contribution requested by the subject.** Including uncertain irrigation links in a sensitivity run does not validate those links.

Keep the evidence threshold honest while building a small agricultural example. If its water source or aquifer connection cannot be established, preserve that uncertainty and report the incomplete connection. Do not silently replace the subject's agricultural question with the better-measured drinking-water question.

**A manageable way to return the implementation to the subject**

Aim for one complete, inspectable example within the existing Roussillon scope:

1. Select a small area with dated crop observations. Separate actual land-use evidence from changes in RPG registration coverage; two inventories do not automatically prove parcel transitions.
2. Map the crop codes to shared concepts and document a locally justified demand estimate or category. Keep crop identity, potential irrigation need, actual irrigation and water source distinct.
3. Add the planned satellite-derived irrigation assessment where usable observations exist. Crop agreement alone does not validate irrigation. Preserve its time period and confidence.
4. Represent the supported links to demand, abstraction or recharge in the KG. Record missing links explicitly. Proximity to a pump does not prove that it supplies a parcel.
5. Carry the land-use information into the model and evaluate its contribution through a controlled comparison. A carefully measured null result is acceptable; an unused land-use label is not evidence of integration.
6. Explain an actual output through the relevant entities and model contributions. Where evidence allows, demonstrate a conditional crop-change scenario. Reduced demand need not translate directly into greater recharge; water sources and return flows matter.

This builds on CQ7, CQ8, CQ10, CQ15 and CQ16. Complete the necessary KG rules and export, while ensuring that finishing the six current MUST questions is not mistaken for completing every central objective of the subject. Several subject-critical capabilities currently sit under SHOULD or COULD priorities.

**Keep the scope realistic and the claims precise**

One Mediterranean aquifer, groundwater level and drought are a reasonable Master's scope. Pollution, socioeconomic vulnerability, full use-conflict modelling and a production GIS dashboard can remain declared future work. Those reductions should stay visible in the thesis's comparison with the original subject.

The current hybrid architecture, ontology network and SHACL-based rules can serve the original idea. This reminder does not require reverting those choices or adding model families. The priority is to complete the connection between land use, semantic knowledge, the model and explanations.

Keep the narrower paper question in service of the thesis subject. Stronger groundwater benchmarks help, but they cannot substitute for its land-use component. Describe simulation, retrospective forecasting and operational future prediction accurately. Where an original objective is reduced or deferred, say so rather than claiming that every objective is already covered.

**Recurring check for Claude**

Before choosing the next substantial task, answer these questions briefly in the work notes:

- Which part of the original land-use → water → model → explanation chain does this task advance?
- Where does real, dated land-use information enter the current system, and what uses it?
- Which relevant relationships are observed, inferred, assumed or still unknown?
- What implementation and evaluation evidence exists, and what remains only a plan?
- Does the next model experiment resolve an open project question, or merely expand the baseline comparison?
- What remains missing from the original subject, including satellite semantics, explanations and decision support?

Revisit the dated findings as the work progresses and link each closed gap to its implementation and evidence. If land use repeatedly disappears from the answers, refocus the next work on that connection.

**Codex's recommendation:** preserve the existing foundation and bring land use into the working contribution. The next convincing milestone is one demonstrated land-use-to-water example that the ontology guides and the model can explain.
