# Roadmap: from data foundation to thesis and paper

Written 2026-10-13. **Revised 2026-10-23**, after:
- the critical review (`docs/feedback.md`)
- the project review (`docs/review_2026-10-23.md`)

Assil approved the revision on 2026-10-23. The same day, the supervisor left the
open choices to Assil. The decisions and their reasons are in
`docs/supervisor_questions.md` §1.
Literature verdicts are in [`literature/reading_list.md`](literature/reading_list.md).

**Timing assumption: defence in early June 2027. Not confirmed.** Week
numbers count from 2026-10-13. If the real date differs, slide every phase by
the same amount.

---

## 1. The paper this project produces

**Working title (decided).** *Right for the right reasons?
Ontology-derived graphs and constraints for groundwater-level simulation in a
Mediterranean multilayer aquifer.*

**One-sentence claim.** A model whose graph, sign constraints and explanation
vocabulary come from a LULC-Water knowledge graph simulates weekly groundwater
levels in the Roussillon multilayer aquifer at least as well as strong
hydrological and deep-learning baselines. A semi-synthetic twin and semantic
ablations then show whether it is right for the right reasons.

**Framing (decided).**
- The main story is the use conflict on the Pliocene: drinking water against
  agriculture.
- Canal-return recharge is a secondary case study for the alluvium.

**Research questions**

| RQ | Question | Experiment that answers it |
|---|---|---|
| RQ1 | Does knowledge from the KG help, as information (features) and as structure (graph)? | The six arms below; scored on the drought and recovery phases, leave-wells-out, and 25/50 % of the training data |
| RQ2 | Do ontology-derived sign constraints improve plausibility and out-of-distribution skill? | None / soft (sign penalties, Ross et al. 2017, arXiv:1703.03717) / hard (monotone by construction); violation rate; counterfactual sign accuracy within the observed year-to-year range |
| RQ3 | Does the model use the knowledge, or take shortcuts? | Concepts = driver contributions. Recovery error on a semi-synthetic twin; disagreement across seeds; rewiring (arm E), its power calibrated on the twin. SGI accuracy is reported, not used as the test. |
| RQ4 | Can explanations be stated in ontology terms *and* be faithful? | Driver-group contributions → SPARQL chains → templates; fidelity+/−; entity-existence and sign-consistency tests; the summer 2024 Pliocene rise (BRGM, 16 Sept 2024) |

The RQ1 arms (`docs/analysis_plan.md` §10):
- **A:** baseline inputs, no graph
- **B:** knowledge-graph features, no graph
- **C:** knowledge-graph features + the Taccari distance graph
- **D:** knowledge-graph features + the knowledge-graph graph
- **E:** D with its edges rewired, degrees preserved
- **F:** random and complete graphs

**Why this is publishable.**
- GNNs for groundwater exist: Bai & Tahmasebi 2023, Taccari 2024, Wu 2025
  (JGR: MLC).
- The closest competitor, Wu et al. 2025 (WRR), uses hydrogeological units as
  a prior. None of these uses an ontology or knowledge graph, or tests for
  reasoning shortcuts.
- Dai et al. 2025 list interpretability and physical consistency as open gaps.
- Kirschstein & Sun 2024 found that a domain graph (river topology) did not
  help a GNN. A careful, testable answer is therefore valuable either way.

**What makes it credible to hydrologists.**
- Pastas as a baseline.
- A test period that is the record 2022–2025 drought followed by the recovery.
- An evaluation with clustered statistics and skill against climatology.
- A documented real event (the 2024 Pliocene rise after reduced abstraction)
  that the explanations must recover.

---

## 2. What changed from the subject, and why

The subject (`Documents/sujet.docx`) describes a PhD-sized programme. A
Master's needs **one sharp, testable contribution**, while still covering
every objective of the subject, some in a small, measured version.

| Topic | Subject | Plan | Why |
|---|---|---|---|
| Physical constraint | "Water infiltrates downward" | **Response-sign constraints** from the ontology's causal knowledge: abstraction lowers the head, effective rain raises it, canal return flow raises the alluvium. Hard arm: **monotone by construction**; soft arm: sign penalties. | The data reject the head ordering (shallow above deep in only 50.5 % of pair-weeks). PiShield constrains outputs and cannot express the sign of a response. |
| Reasoning shortcuts | Marconato et al. as is | **Driver contributions** as the concepts, tested on a **semi-synthetic twin**, by seed disagreement and by rewiring | SGI is computed from the predicted head, so SGI accuracy cannot reveal a shortcut. |
| Ontology | A merged meta-ontology (PROMPT, OntoMerge) | A **network** of reused ontologies plus our bridging module `lulcw:` (WHOW-KG pattern), presented as the meta-ontology | Reuse beats re-invention, and every term has a source. |
| Sources to align | SWEET, INSPIRE, AgroPortal, a use-conflict ontology | SWEET; INSPIRE (HILUCS); AGROVOC (via AgroPortal); GWML2 classes via SAWGraph's OWL rendering; HyFO; SOSA/SSN; HY_Features; GeoSPARQL; PROV-O; SKOS; OWL-Time. Use conflict modelled in `lulcw:` (CQ12). | Checked at their sources on 2026-10-23 (`docs/ontology_design.md`). GWML2 has no official OWL; WHOW-KG has no water-use module. |
| Alignment | A research experiment | **RPG crop codes → AGROVOC** gold set + OntoAligner (P/R/F1); smaller gold sets for units and uses | A real, measurable alignment task, sized for a Master's |
| Derivation rules | SWRL | **SHACL-AF** (pySHACL advanced mode), plus SHACL for validation | One technology for validation and rules; SPARQL rules can test distances. |
| Remote sensing | Semantic classification of Sentinel/Landsat | **One derived concept**, `ProbablyIrrigatedParcel` (summer NDVI + soil wetness), by a rule, checked against the RPG. AlphaEarth embeddings stay optional features. | Covers the subject's objective at Master's scale. The RPG already gives the crops. |
| Graph construction | Built by the ontology | **Generated from the KG** by SPARQL → PyG `HeteroData` | The ontology is operational, not decorative. |
| Main model | GNN or Graph Transformer | **(decided)** A hybrid: KG → heterogeneous GNN → parameters of sign-constrained response functions + a small residual. The black-box heterogeneous ST-GNN is the comparison. | Every causal relation of the ontology does a job; concepts and explanations are exact. |
| Baselines | "Distance graph + baseline GNN" | Seasonal naive, Pastas (+ WellModel), LightGBM, LSTM, EA-LSTM, Chronos-2, distance-graph and Taccari-graph ST-GNNs, at equal tuning budget | Hydrology reviewers expect Pastas; ML reviewers expect a foundation model. |
| Time step and window | Daily, 2016–2025 | **Weekly**, 2005–2026; test May 2022 → latest, split into drought and recovery | Weekly cuts noise; the drought is a natural out-of-distribution test. |
| Explanations | GNNExplainer → text | Contributions by driver group → SPARQL chain → templates → **faithfulness** and sign-consistency tests | Unmeasured explanations are not publishable (Azzolin et al. 2024). |
| Dashboard | A module of the SAVE Water dashboard | **Prototype:** the competency-question queries + one map page + one scenario query (CQ16) | Covers the subject's objective; the full dashboard belongs to SAVE Water WP8. |
| Text extraction | Mediterranean concepts from articles | Small, measured version (10–20 papers, local LLM, manual check, precision) | Covers the subject's phase 1 for the thesis. |
| Nitrate, socio-economics, Spain | In scope | **Future work** | Scope. |
| Tunisia / Living Labs | In scope | A qualitative transfer demo to the Manouba aquifer if its data arrive by February; otherwise a "transfer recipe" chapter | Data access decides. |

---

## 3. The method in one picture

```
 Hub'Eau piezo ─┐                         ┌─ SHACL shapes + SHACL-AF rules
 BNPE abstraction│  ingest   ┌──────────┐  │   (Influence links, ProbablyIrrigatedParcel,
 RPG + Sentinel-2├────────►  │ LULC-    │◄─┤    HighIrrigationDemandZone, ConfinedSetting)
 BD LISA         │  + RDF    │ Water KG │  │
 SAFRAN (rain,ET)│           └────┬─────┘  └─ reuse + alignments: GWML2 (SAWGraph OWL) · HyFO ·
 Hub'Eau rivers ─┘                │            SWEET · SOSA/SSN · HY_Features · GeoSPARQL ·
                                  │            HILUCS · AGROVOC · PROV-O · SKOS · OWL-Time
                                  │ SPARQL export (+ rewired / random variants, arms E–F)
                                  ▼
        Heterogeneous graph: Well · AquiferUnit · AbstractionPoint · RiverReach ·
        WeatherCell · LandUseZone   edges: monitors, pumpsFrom, overlies, sameUnitNear,
        connectedTo, irrigates, Influence(sign, distance, confidence)
                                  │
                                  ▼
   Hybrid model: heterogeneous GNN → parameters of sign-constrained response
   functions (one per Influence type) → superposition + bounded residual
   (comparison: black-box HGT/RGCN + temporal convolution / GRU)
                                  │
                                  ├─► weekly head per well ─► SGI drought class
                                  ▼
   Contributions by driver group → SPARQL chain → templates → text
   Validity: semi-synthetic twin · rewiring · seed disagreement · faithfulness
```

---

## 4. Phases

Each phase lists its goal, its tasks, and a **done-when** test. A **gate** is
a meeting or e-mail with the supervisor. Don't freeze a phase's design before
its gate.

### Phase 0: data foundation (weeks 1–2) — ✅ done
Environment on Linux, Step 6b (BD LISA, head-ordering check), Gate 1 memo.
**Gate 1:** answered 2026-10-23 (the choices are left to Assil).

### Phase 1: forcings and the model-ready dataset — ✅ done
SAFRAN SIM2, Hub'Eau hydrometry, weekly pumping with usage profiles, SGI,
splits. Datasets v1 → v2 → **v3** (real BNPE 2024, documented imputation,
river inputs, leak fixed). See `docs/notes/step08_dataset.md` and
`docs/notes/step12a_fixes.md`.

### Phase 2: baselines — ✅ finishing
- Done:
  - naive and climatology
  - Pastas (+ WellModel)
  - LightGBM, LSTM
  - Chronos-2 (3 modes)
  - distance-graph ST-GNN
  - the regimes
  - equal-budget tuning
  - the drought/recovery evaluation (`docs/analysis_plan.md`)
- Running: EA-LSTM (laptop), Taccari-graph ST-GNN (Colab).
- Then: ensemble, report, Gate 2 addendum. **No new baselines after this.**
- **Gate 2:** answered 2026-10-23 (the choices are left to Assil).
- **Second review (2026-10-23, Step 12b):** dataset v4 (quality filter, grouped
  folds, R3 window statistics) and analysis plan v2. Every baseline is re-run on
  v4 with the configuration selected on v3 (laptop: `scripts/run_v4_cpu.sh`;
  Colab: `final:`/`regimes:` steps), then the v4 report. No re-tuning.

### Phase 3: ontology and knowledge graph (26 Oct – 6 Dec, 6 weeks)

Goal: the smallest ontology that answers the competency questions. It must be
correct, documented, tested, and cover the subject's objectives SO1 and SO2.

| # | Task | Done when |
|---|---|---|
| 3.1 | Competency questions (16) with example answers (`docs/competency_questions.md`) | Assil and the supervisor agree on the list |
| 3.2 | Reuse table, term by term, and the modelling patterns (`docs/ontology_design.md`) | every term has a checked source or a `lulcw:` definition |
| 3.3 | **CQ2 data step:** attribute each groundwater abstraction point to a unit, with provenance and confidence | ✅ 2026-10-23 (`src/kg/pump_attribution.py`): rules measured on 130 recorded boreholes, use-aware confidence, coverage by volume and use |
| 3.4 | Write `lulcw:` + imports/alignment axioms in `ontology/` (IRIs, metadata, FR/EN labels, definitions) | the reasoner is consistent; OOPS! shows no critical pitfall |
| 3.5 | KG instantiation from the parquet tables (rdflib → Turtle → pyoxigraph) | rebuilt from cold by one command |
| 3.6 | SHACL shapes + SHACL-AF rules (Influence links, ProbablyIrrigatedParcel, HighIrrigationDemandZone, ConfinedSetting) | validation passes |
| 3.7 | CQ tests: one SPARQL query plus an oracle each (`tests/cq/`) | all pass |
| 3.8 | Export SPARQL → `HeteroData` (+ rewired/random variants for arms E–F) | loads in PyG; node and edge counts reported; the **equivalence test** passes (pandas rules on the same tables give the same edges) |
| 3.9 | Alignment experiment: RPG → AGROVOC gold set; OntoAligner fuzzy, retrieval and LLM matchers (local LLM on Colab) | P/R/F1 table |
| 3.10 | Satellite rule: Sentinel-2 summer NDVI per RPG parcel (Earth Engine) + soil wetness → `ProbablyIrrigatedParcel` | checked against independent irrigation evidence (Agreste census, ASA perimeters, BNPE irrigation points), else labelled a heuristic; agreement with RPG crops alone does not validate irrigation |
| 3.11 | Text extraction, small and measured (thesis) | precision on 10–20 papers |

Tools: Protégé (editing), `rdflib`, `pyoxigraph`, `pyshacl` (advanced mode),
ROBOT (reason, report), OOPS!, `ontoaligner`, `earthengine-api`.
**Gate 3:** ontology review with the supervisor. A
reviewer from SAVE Water (UGE/LASTIG) would be welcome (contact asked). Gate 3
also confirms the Phase 4 families of `docs/analysis_plan.md` §10; the plan is
then tagged `analysis-plan-v2` in git, **before any Phase 4 run**.

### Phase 4: knowledge-guided model and validity tests (7 Dec – 31 Jan)

Goal: answer RQ1–RQ3. This is the core of the paper.

1. **Main model (decided):** the hybrid. A heterogeneous GNN on the KG
   graph outputs the parameters of sign-constrained response functions
   (causal 1-D convolutions with parametric kernels), one per
   `lulcw:Influence` type. The responses are summed, plus a small bounded
   residual network (`docs/feedback.md` §5.5; about 2–3 weeks). Comparison:
   the black-box heterogeneous ST-GNN (HGTConv or RGCNConv + temporal
   convolutions or a GRU).
2. **Arms A–F** (RQ1) at equal tuning budget, 5 seeds, all regimes.
3. **Constraints** (RQ2):
   - none / soft (sign penalties) / hard (monotone by construction)
   - violation rate and counterfactual sign accuracy
4. **Semi-synthetic twin** (RQ3; about 1 week):
   - inputs: the real forcings, wells, pumps and KG
   - synthetic heads from known response functions plus AR noise
   - two variants: pumping timing tied to the deficit, or independent of it
   - harder variants (decided 2026-10-23): a response shape the model does not
     have, a driver it does not see, wrong KG links
   - concept accuracy = the error of the recovered contributions
5. **Shortcut tests:**
   - rewiring and attribute shuffling (power calibrated on the twin)
   - disagreement across seeds
   - counterfactual sign accuracy; the Pastas gains are a comparator, not the
     reference
6. **Robustness (analysis plan v2):** the main contrasts under 3 pumping
   reconstructions; pump links confident only vs all; the monotonicity
   finite-difference test; the satellite-concept ablation.
7. **Confirmation check** at the end: the frozen models scored on the weeks
   observed after the freeze, and on 2025–26 once ADES validates them.

GPU: Colab (free T4), Camber's monthly allowance.
**Gate 4: results frozen.** No new experiments after this point.

### Phase 5: explanations and the dashboard prototype (February)

1. Contributions by driver group ("summer demand" where pumping and the
   deficit cannot be separated). Captum Integrated Gradients and PyG
   GNNExplainer serve the black box, aggregated by node type and relation.
2. Faithfulness: fidelity+/− and deletion curves (Azzolin et al.,
   arXiv:2406.15156).
3. Templates: contribution → SPARQL chain of entities → fixed French/English
   sentences. Tests check that every entity exists and is connected to the
   well, and that the sign matches the polarity. An LLM may rephrase only.
4. **Case studies:**
   - the summer 2024 Pliocene rise after reduced abstraction
   - the 2023 drop
   - an alluvium well (canal)
5. **Dashboard prototype (subject SO5):** the CQ queries on a map page, plus
   the scenario query CQ16.

Done when: 3 case-study figures with their text, a faithfulness table, and
the prototype page.

### Phase 6: paper (March – 25 April)

1. Venue (decided; final check at Gate 4):

   | Venue | Fit | Note |
   |---|---|---|
   | **Environmental Modelling & Software** (Elsevier) | methods + software + environment; ontologies welcome | first choice |
   | **JGR: Machine Learning and Computation** (AGU, open access) | where Wu 2025 and Dai 2025 appeared | strong second |
   | HESS (Copernicus, open access) | hydrology audience | if the hybrid model is adopted |
   | Earth Science Informatics · Computers & Geosciences | safer | fallback |

   The PRIMA proposal commits SAVE Water to gold open access. Who pays the
   fees has been asked. EMS is a hybrid journal, so the paper can appear without a
   fee.
2. Structure:
   - Introduction (gap: Dai 2025, Clark 2025)
   - Study area and data
   - Knowledge graph
   - Model and constraints
   - Experiments (RQ1–4)
   - Discussion (limits, shortcuts found)
   - Conclusion

   About 8,000 words and 8–10 figures.
3. Reproducibility package:
   - code on GitHub
   - a Zenodo DOI for the code and processed data
   - the ontology and the KG in Turtle
   - the exact configs and `uv.lock`
4. Supervisor review, then submit **by the end of April 2027**.

### Phase 7: thesis and defence (26 April – June)

- The thesis reuses the paper, plus the chapters the paper has no room for:
  - the alignment experiment
  - the text extraction
  - the satellite rule
  - the dashboard prototype
- `docs/notes/` already holds most of the Data and Methodology chapters.
- Transfer demo to the Manouba Living Lab (if its data arrive by February): reuse the
  ontology and the model with the data the consortium provides. Qualitative.
- Defence slides.

---

## 5. Compute plan

| Work | Where | Why |
|---|---|---|
| Ingest, KG, SHACL, Pastas, single runs, EA-LSTM sweep | **Laptop** (4 cores, 11 GB) | The graph is tiny (≈ 65–250 nodes × 1,100 weeks). |
| Tuning sweeps, Phase 4 arms, twin experiments | **Google Colab** free T4 (main); **Camber** L4 monthly allowance (renews on the 13th) | Kaggle is unavailable (no verification SMS to Tunisia). |
| LLM matchers (OntoAligner), text extraction | Colab GPU, local open 7–8B model | Reproducible; no paid API |
| Sentinel-2 NDVI per parcel, AlphaEarth (optional) | **Google Earth Engine** (Assil's account) | Server side; only the parcel summaries are downloaded |

Rules:
- Every sweep is resumable (one result file per run, skipped if it exists).
- Results go to persistent storage (Drive, Stash).
- Pin the environment (`uv.lock`) before Phase 4.

---

## 6. Toolbox

| Purpose | Tool |
|---|---|
| Environment | `uv`, Python 3.12 |
| Geodata | `geopandas`, `pyogrio`, `shapely`, `earthengine-api` |
| Groundwater baseline | `pastas` |
| Deep learning | PyTorch, PyTorch Geometric (`HeteroData`, `HGTConv`, `explain`) |
| Foundation-model baseline | `chronos-forecasting` (Chronos-2) |
| Constraints | sign-constrained response functions (custom), sign penalties; LightGBM `monotone_constraints` as a check |
| Explanations | `captum`, PyG `explain` |
| Experiments | YAML configs, Optuna; GPU runners in `scripts/` |
| Semantic web | Protégé, `rdflib`, `pyoxigraph`, `pyshacl` (advanced), ROBOT, OOPS!, `ontoaligner` |
| Writing | Zotero + Better BibTeX, LaTeX (journal template), a script for every figure |

---

## 7. Risks and fallbacks

| Risk | Sign | Fallback |
|---|---|---|
| The jury questions departures from the subject | Defence | Every objective has a small, measured version (§2), and each choice is recorded with its reason (`docs/supervisor_questions.md`). |
| Pumps cannot be tied to layers (CQ2) | Phase 3.3 | Lower since 2026-10-23: 211 points have a BD LISA unit from ADES, and the BNPE river-connection flag is checked on them (alluvium ≈ True, Pliocene ≈ False). Confidence levels; sensitivity on all links; say so. |
| The KG graph does not beat the Taccari graph | Phase 4 | The arms separate information from structure. Lead with RQ2–RQ4 ("right reasons"), which stay publishable either way. |
| Pumping inseparable from weather within a year | Already known | Claims from between-year and between-well variation; "summer demand" group; the twin with independent timing. |
| The hybrid model misses nonlinearity | Phase 4 | Bounded residual network; the black-box HGT as comparison. |
| Ontology work balloons | Phase 3 still open on 6 Dec | Freeze to the MUST competency questions; the rest is future work. |
| A reused vocabulary disappears or has an unclear licence (SAWGraph) | Phase 3.2 | Keep local copies of the terms we use; cite the source; fall back to `lulcw:` terms with `skos:closeMatch`. |
| GPU access (Colab limits, Camber allowance) | Any sweep | Resumable runs; Camber renews monthly; the laptop for small sweeps. |
| Defence date earlier than June | Supervisor's answer | Cut Phase 7 extras (transfer demo, text extraction) first. |
| Data drift (2025: 52 % "Non qualifié") | — | Results with and without unqualified values. |

---

## 8. Weekly routine

- **Monday:** pick this week's tasks from this file and CLAUDE.md §7.
- **Each step:** commit, then write `docs/notes/stepNN_*.md` (what / why /
  what to consider).
- **Every month:** a short progress report to the supervisor (the PFE guide
  asks for this). The first is the e-mail in `docs/supervisor_questions.md` §4.
- **Reading:** 2–3 papers a week from `literature/reading_list.md` until
  Phase 4, one comparison-table row each.
