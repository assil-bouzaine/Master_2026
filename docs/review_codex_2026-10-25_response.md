# Response to the Codex subject-alignment review of 2026-10-25

Review: `docs/review_codex_2026-10-25.md` (kept unchanged). Checked by Claude on
2026-10-25 against the code and data; decisions by Assil the same day.

## 1. Verdict

**The review is right, and its main claim holds in the code.** No dated land-use
information enters the dataset, the baselines or the knowledge graph:
`src/models/features.py`, `src/dataset/` and `src/kg/build_kg.py` contain no RPG,
crop or NDVI reference. Only the RPG editions 2016 and 2023 had been downloaded, and
were used for one descriptive profile (`src/analysis/rpg_profile.py`). The
"fixed crop calendar" pumping reconstruction required by `docs/analysis_plan.md` §8
was not implemented.

| Review point | Verdict | Action |
|---|---|---|
| Land use not in the pipeline | Holds (checked above) | Land-use thread LU-1 … LU-6 below |
| RPG → AGROVOC alignment still a plan | Holds (task 12.9 ⬜) | LU-2, first week |
| Satellite rule still a plan | Holds (task 12.10 ⬜) | LU-5; needs Assil's Earth Engine login |
| KG rules, queries and export still plans | Holds (12.6–12.8 ⬜) | Unchanged order; land-use rules added to 12.6 |
| Explanations of actual outputs not yet produced | Holds; the explainer is for readers, not model outputs | CQ10 promoted to MUST; Phase 5 |
| "Prediction of future risks" departs from the subject | Holds | Stated in the thesis scope table (simulation and hindcast, not operational forecasting) |
| 0 % irrigation under the main pump policy does not answer the subject's agricultural question | Holds | See §2: the agricultural path is rebuilt around demand and canals, not farm-borehole links |
| Several subject-critical CQs are SHOULD/COULD | Holds | CQ7, CQ10, CQ15 → MUST (Assil, 2026-10-25) |

## 2. One nuance: where agriculture meets groundwater in Roussillon

In this plain, 84 % of irrigation water is surface water (Têt/Agly canals, Step 6a).
Farm boreholes declare about 144 Mm³ of groundwater over 2012–2023, but their links
to a unit stay "possible". The agricultural pathway that the data can carry is therefore:

1. **Crop demand → timing and spatial pattern of farm pumping** (potential demand from
   dated crops; never presented as metered irrigation)
2. **Canal irrigation → return-flow recharge of the alluvium** (the existing framing B)

Farm-borehole attribution stays a sensitivity (decision of 2026-10-24, unchanged).
Crop demand enters as its own input, which leaves it unaffected by the 0 % link coverage.

## 3. Decisions (Assil, 2026-10-25)

1. **Annual RPG 2015–2025** downloaded, clipped to the plain bbox + 3 km, raw archives
   deleted after clipping (about 4 GB transient).
2. **CQ7, CQ10, CQ15 become MUST** (9 MUST). CQ16 stays COULD.
3. **A pre-registered land-use test in RQ1**, written into `docs/analysis_plan.md` §14
   before any run. The crop-demand feature also defines reconstruction (3) of §8,
   "irrigation following a fixed crop calendar". In Phase 4, crop demand is one
   `lulcw:Influence` type of the hybrid.

## 4. Working road (Phase 3: 26 Oct – 6 Dec 2026)

Each line names the link of the chain *land use → water → model → explanation*
that it advances.

| Week | Ontology / KG (tasks 12.x) | Land-use thread | Chain link |
|---|---|---|---|
| 26 Oct – 1 Nov | Close the v4 re-runs (Kaggle kernel 5, Colab session 2) | **LU-1** annual RPG 2015–2025 clipped; registration-coverage check (stable footprint vs newly declared land). **LU-2** crop table: RPG code → group → AGROVOC candidate → FAO-56 Kc calendar → irrigable class; gold-set draft for 12.9 (Assil validates) | land use |
| 2 – 8 Nov | **12.6** SHACL shapes and SHACL-AF rules (stratigraphy, CQ11 well links, CQ8 influences); land-use rules: parcel-year observations, `HighIrrigationDemandZone` | **LU-3** weekly potential-demand index per well and unit (clipped area × max(0, Kc·ETP − Peff)); reconstruction (3) of §8 built from it | land use → water |
| 9 – 15 Nov | **12.7** CQ tests incl. CQ7 (oracle: pandas on the same clipped tables) | **LU-4** pre-registered ablation on Kaggle CPU: LightGBM and LSTM ± demand feature, with a shuffled-area placebo; null result reported as is | water → model |
| 16 – 22 Nov | **12.8** SPARQL → HeteroData + equivalence test; land-use zone node type and its relations | Demand and canal-return Influence types exported | model structure |
| 23 – 29 Nov | **12.9** OntoAligner P/R/F1 on the RPG gold set (Colab) | **LU-5** Sentinel-2 summer NDVI per parcel (Earth Engine) → `ProbablyIrrigatedParcel`, checked against Agreste census irrigated areas, else labelled a heuristic | land use (observation → concept) |
| 30 Nov – 6 Dec | Buffer; Gate 3 package | **LU-6** one end-to-end example: an alluvium well (canal + crops) and a Pliocene well, from the RPG parcels to the KG path | whole chain (no model yet) |

**Phase 4 (Dec–Jan):** the hybrid gets the crop-demand and canal-return Influence
types; RQ1 reports the land-use row; the twin includes a land-use driver.
**Phase 5 (Feb):** explanation of a real output for the alluvium well (CQ10); one
conditional crop-change scenario (CQ16) with its assumptions and unsupported cases.
**Thesis:** a "subject vs delivered" table (forecasting → hindcast simulation;
pollution, socio-economics, full dashboard as future work).

## 5. The recurring check

Claude answers the review's six questions in the step note before choosing each
substantial task, and links each closed gap to its file and result (CLAUDE.md §7).

## 6. The two external repositories (checked 2026-10-25)

- **Imbad0202/academic-research-skills** (v3.23.2, CC BY-NC 4.0): Claude Code
  skills for writing, simulated peer review and citation checking. It runs no
  experiments. **Not useful before Phase 6**; worth installing in March 2027 for
  its reviewer panel and its citation gate (it matches rule 9) on the manuscript.
- **fabio-rovai/open-ontologies** (v2.1.0, MIT): a Rust MCP server for ontology
  change control, with OWL-RL reasoning that issues Lean-checked certificates.
  **Not adopted.** Our quality gates already use ROBOT with HermiT/ELK, pySHACL and
  pyoxigraph. Its Rust engine validates SHACL constraints (including SPARQL-based
  ones) but does not run SHACL-AF rules; its Python layer runs them by calling pySHACL
  in advanced mode, the library we already use (`python/src/open_ontologies_lite/shacl.py`,
  checked 2026-10-25; an earlier line here said it had no SHACL-AF rules at all). It would
  add a second engine to every gate. Its semantic `plan`/diff could be reconsidered at
  the ontology freeze, if a release needs a change audit.
