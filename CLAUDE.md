# CLAUDE.md — SAVE Water / LULC-Water PFE

Read this file at the start of every session. It is the project brief, the
rules, and the current task.

---

## 1. The project in one paragraph

Master's PFE (projet de fin d'études) by Assil Bouzaine, Master in Data Science
and Information Retrieval, ISAMM (Université de la Manouba), within the SAVE
Water project (PRIMA). The subject (`Documents/sujet.docx`) asks for a
**LULC-Water ontology**, built by aligning existing ontologies, that
**structures, constrains and explains** a deep-learning model of water risk
in the Mediterranean. Our instance of it:
- simulate weekly groundwater levels in the Roussillon multilayer aquifer
- with a model whose graph and sign constraints come from the LULC-Water
  knowledge graph
- test whether the model uses that knowledge or takes shortcuts
- explain its predictions in ontology terms

Scope is a **Master's, not a PhD**: one aquifer system (Roussillon plain) and
one target (weekly groundwater level, plus its SGI drought class), built end to
end. Every objective of the subject is covered, some in a small, measured
version (§1b). Future work: nitrate, socio-economics, the full dashboard,
Spain. One qualitative transfer demo to the Manouba Living Lab at the end, if
its data arrive by February.

### 1a. End goal: a peer-reviewed paper as well as the thesis

- **Working title (decided 2026-10-23):** *Right for the right reasons?
  Ontology-derived graphs and constraints for groundwater-level simulation in
  a Mediterranean multilayer aquifer.* "Simulation", because Chronos-2 is the
  forecasting reference; the phrase is from Ross et al. 2017 (arXiv:1703.03717).
- **Umbrella question (decided 2026-10-23, after the second review):** *When
  does explicit hydrogeological knowledge improve groundwater simulation and
  explanation reliability under uncertain pumping information?* RQ1–4 answer
  it; the title is unchanged. The ontology is credited with traceability,
  consistency and reuse; accuracy gains are credited to the knowledge it
  carries (an equivalence test shows that plain tables with the same rules give
  the same edges).
- **Research questions:**

  | RQ | Question | Experiment that answers it |
  |---|---|---|
  | RQ1 | Does knowledge from the KG improve simulation, as **information** (features) and as **structure** (graph)? | Arms A–F (`docs/analysis_plan.md` §10), described below the table; scored on the drought and recovery phases, leave-wells-out, and 25/50 % of the training data |
  | RQ2 | Do ontology-derived sign constraints improve plausibility and out-of-distribution skill? | None / soft (sign penalties) / hard (monotone by construction); violation rate; counterfactual sign accuracy within the observed year-to-year range |
  | RQ3 | Does the model use the knowledge, or take shortcuts? | Concepts = driver contributions. Recovery error on a semi-synthetic twin, including mechanisms the model cannot fit; disagreement across seeds; rewiring (arm E), its power calibrated on the twin. SGI accuracy is reported, not used as the shortcut test. |
  | RQ4 | Can explanations be stated in ontology terms *and* be faithful? | Driver-group contributions → SPARQL chains → templates; fidelity+/−; entity-existence and sign-consistency tests; documented events (summer 2024 Pliocene rise) |

  The RQ1 arms:
  - **A:** baseline inputs, no graph
  - **B:** knowledge-graph features, no graph
  - **C:** knowledge-graph features + the Taccari distance graph
  - **D:** knowledge-graph features + the knowledge-graph graph (the main model)
  - **E:** D with its edges rewired, degrees preserved
  - **F:** random and complete graphs

  C–F share one backbone, the hybrid: only the edges change (decided 2026-10-24;
  controls and the full experiment contract in `docs/analysis_plan.md` §10).

- **Venue (decided 2026-10-23; final check at Gate 4):**
  - first choice: *Environmental Modelling & Software*, a hybrid journal, so
    the paper can be published without an open-access fee
  - second: *JGR: Machine Learning and Computation* (fully open access, with a
    fee)
  - HESS if the hybrid model is strong
  - fallback: *Earth Science Informatics* or *Computers & Geosciences*
- **Authorship:** Assil first author, supervisors as co-authors. Acknowledge
  SAVE Water / PRIMA with the grant number (to obtain before submission).
- **Target:** submitted by the end of April 2027, assuming a June 2027 defence.
  **The real defence date is still unknown.**
- **Plan:** `docs/roadmap.md` (phases, tools, risks; revised 2026-10-23).
- **Literature:** `docs/literature/reading_list.md` (verdicts, verified IDs).
- **Project review of 2026-10-23:** `docs/review_2026-10-23.md` (why the plan
  changed).

### 1b. How each objective of the subject is covered

| Subject (`Documents/sujet.docx`) | Covered by | Status on 2026-10-25 (✅ done · 🔄 in progress · ⬜ not started) |
|---|---|---|
| LULC-Water meta-ontology in OWL | A network of reused ontologies plus our bridging module `lulcw:` (the WHOW-KG pattern), presented as the meta-ontology | 🔄 `lulcw:` 0.5.0: the MUST CQs' modules, the land-use module (CQ7) and the recharge-related forcing (CQ4, recharge proxies), with SHACL shapes and SHACL-AF rules (12.6), local copies of the reused terms, quality gates pass; SHOULD/COULD modules to add |
| SO1: fuse and align existing ontologies (SWEET, INSPIRE, AgroPortal) | Reuse and alignment axioms (§3); the RPG → AGROVOC alignment experiment (gold set + OntoAligner, P/R/F1) | 🔄 alignments to GWML2/HyFO and SWEET done; crop classes (LU-2) done; AGROVOC experiment 🔄 (12.9: snapshot, candidates and gold template on 2026-10-26; Assil's gold set next) |
| SO2: semantic enrichment of remote sensing (rules) | One derived concept, `lulcw:ProbablyIrrigatedParcel`: Sentinel-2 summer NDVI + soil wetness, by a SHACL-AF rule (CQ15); checked against independent irrigation evidence, otherwise labelled a heuristic; one ablation row tests whether it adds information | ⬜ (12.10, needs the Earth Engine login); the census evidence on irrigated crops is in hand |
| SO3: the ontology structures and constrains the model | Graph exported from the KG (SPARQL → HeteroData); response-sign constraints from the causal axioms | 🔄 factual KG built (12.5); rules derive the model's links and their sign eligibility, and dated land use (crop classes, class areas, high-demand categories), shapes validate them (12.6, 2026-10-25); recharge proxies (weather cell → well over the outcrop of its unit, with the pathways they omit) on 2026-10-27; export and constraints ⬜ (12.7–12.8, Phase 4); the land-use test (LU-4) found no detectable improvement from the demand index on 2026-10-26 (these models, settings, wells and drought period) |
| SO4: explanations along the causal chain | Contributions → SPARQL chains → templates, with faithfulness tests | ⬜ (Phase 5) |
| SO5: dashboard "semantic intelligence" queries | The competency-question queries plus one map page; one scenario query (CQ16) | ⬜ (12.7, Phase 5) |
| Phase 1 of the subject: text extraction from articles | Small, measured version: 10–20 papers, local LLM, manual check, precision (thesis) | ⬜ (12.11) |
| Risks: drought / pollution / use conflicts | Drought (head + SGI); use conflict as a framing and CQ12; pollution is future work | 🔄 drought scored in the baselines (head, SGI classes); CQ12 specified; pollution future work |

---

## 2. Study sites

| Role | Site | Notes |
|---|---|---|
| Primary | **Plaine du Roussillon**, Pyrénées-Orientales (dept 66), France | The method-development site: open data on every layer, 35-year records. Not a SAVE Water Living Lab. |
| Transfer demo (decided 2026-10-23) | The **Manouba phreatic aquifer** (Tunisia, MSE-UMA sensors); fallback Charf El Akab (Morocco) | Qualitative, and only if its data arrive by end of February; otherwise a "transfer recipe" chapter. See `docs/savewater_consortium_notes.md`. |
| Future work | Campo de Cartagena / Segura, Spain | Not in this thesis |

---

## 3. Design decisions

Adopted on 2026-10-13. **Revised on 2026-10-23**, after the critical review
(`docs/feedback.md`) and the project review (`docs/review_2026-10-23.md`);
Assil approved the revision the same day. Do not change them without asking
Assil. On 2026-10-23 the supervisor left the open choices to Assil ("do what is best
for the project"). The decisions and their reasons are in
`docs/supervisor_questions.md` §1.

**Knowledge side**
- **Architecture:** a network of small ontologies linked by alignment
  axioms, not one merged file. This is the WHOW-KG pattern (*Scientific
  Data* 2025, doi:10.1038/s41597-025-04537-4); the thesis presents it as the
  LULC-Water meta-ontology.
- **Reuse.** Each vocabulary was checked at its source on 2026-10-23; the
  term table is in `docs/ontology_design.md`.
  - **Groundwater:**
    - GWML2 has **no official OWL** (only UML + GML/XML; Brodaric et al.
      2018, doi:10.1007/s10040-018-1747-9). Use the GWML2 classes as
      rendered in OWL in SAWGraph's water ontology (`gwml2:` =
      `http://gwml2.org/def/gwml2#`: GW_Well, GW_MonitoringSite,
      GW_AquiferUnit, GW_Aquifer, GW_AquiferSystem; licence to confirm).
    - HyFO: `hyfo:tapsAquifer`.
  - **SWEET** (ESIP, CC0) is an alignment target and is named in the subject:
    - `realmHydro`: Aquifer, ConfinedAquifer, UnconfinedAquifer, Aquitard
    - `matrWater`: Groundwater
  - **Observations, time, provenance, code lists, geometry:** SOSA/SSN,
    OWL-Time, PROV-O, SKOS, GeoSPARQL 1.1.
  - **Rivers:** HY_Features.
  - **Land use and crops:** INSPIRE HILUCS (SKOS) and AGROVOC.
  - **WHOW-KG** is the architecture pattern only: it has no water-abstraction
    module.
- **The bridging module `lulcw:`** holds only what the reused vocabularies
  lack:
  - `lulcw:monitors` and `lulcw:pumpsFrom` (sub-properties of
    `hyfo:tapsAquifer`)
  - `lulcw:overlies`: ours; GWML2 has no such relation
  - the water uses (a SKOS scheme of the BNPE uses)
  - the driver groups (e.g. "summer demand")
  - the causal knowledge, at two levels:
    - class-level mechanism specifications, such as a non-increasing head
      response to increased abstraction from a connected unit under stated
      conditions; qualified model constraints, not proof of observed causality
    - instance-level **`lulcw:Influence`** nodes, following the W3C n-ary
      relation pattern. Each carries its source, target, sign, distance,
      confidence and evidence, and is derived by SHACL-AF SPARQL rules
      (OWL property chains cannot test a distance).
- **Modelling rules** (review §4.2):
  - Aquifer types come from a written mapping rule, not from BD LISA
    `natureeh`:
    - alluvium → alluvial aquifer; assess local confinement separately (CQ14)
    - Pliocene multilayer → aquifer system
    - karst → aquifer
    - impermeable units → confining bed
  - **Depth = investigation depth** (`profondeur_investigation`), not the
    screen depth. No fixed depth classes. "Similar depth" edges use a
    |Δ depth| threshold chosen on the training period.
  - Every derived link carries `prov:wasDerivedFrom` and `lulcw:confidence`.
    **Main runs use confident + probable links** (decided by Assil on
    2026-10-24: 72 % of the plain's declared groundwater volume, against 27 %
    for confident only); sensitivity runs use confident links only, and all
    links (`docs/notes/step12b_review_fixes.md`). Confidence levels are measured,
    not assumed: pump → unit rules get "probable" only for the uses their
    precision was measured on (`src/kg/pump_attribution.py`). The 72 % is at
    unit-group resolution: at exact-unit resolution it is 61.8 %, and
    irrigation gets 0 % at both (`docs/pump_coverage.md`). Pumping outside the
    policy enters every arm as an explicit "unattributed" input, never as zero.
  - Incomplete evidence stays incomplete: a piezometer or pump may have an
    "unknown" or several candidate units; SHACL does not force exactly one.
  - Annual and dated facts are SOSA observations with `sosa:phenomenonTime`
    (OWL-Time). Weekly series stay in parquet.
  - IRIs and metadata:
    - a persistent namespace: w3id.org/lulcw if the redirect is accepted,
      else GitHub Pages
    - `owl:versionIRI` and dcterms metadata
    - licence CC BY 4.0
    - French and English labels, and a `skos:definition` for every term
- **Scope:** driven by the competency questions
  (`docs/competency_questions.md`; 16, Assil reviewing). Time-box: Phase 3 =
  6 weeks, of which the KG build ≤ 4 weeks.
  - **CQ review, 2026-10-24:** all 16 now specify inputs, outputs, evidence,
    uncertainty and acceptance cases (`docs/notes/step12c_competency_review.md`).
    Use the revised contracts and `docs/ontology_design.md` for implementation:
    spatially qualified stacks; separate cover/confinement; resolution-aware pump
    evidence; dated irrigation assessments; annual accounting without duplicating
    alternative assignments. These refine the approved architecture and scope.
- **Alignment (subject SO1).**
  - Manual gold sets:
    - **RPG crop codes → AGROVOC**: the main experiment
    - BD LISA unit types → GWML2 / SWEET
    - BNPE uses → our scheme / Sandre
  - Then OntoAligner (fuzzy, retrieval and LLM matchers) scored with P/R/F1.
    The LLMs run locally on Colab, never through a paid API.
  - Reported in a thesis chapter, and in the paper as a supporting result if
    space allows.
- **Rules and validation:** SHACL shapes and SHACL-AF rules (pySHACL in
  advanced mode: TripleRule, SPARQLRule). No SWRL: SPARQL rules can test
  distances, and SHACL covers both validation and rules.
- **Satellite data (subject SO2):**
  - `lulcw:ProbablyIrrigatedParcel` = Sentinel-2 summer NDVI per RPG parcel
    (Earth Engine) + SAFRAN soil wetness, by a SHACL-AF rule. Agreement with
    RPG crops does not validate irrigation (crop ≠ irrigation status): check it
    against independent evidence (candidates: Agreste census irrigated areas,
    ASA/canal perimeters, BNPE irrigation points), else label it a heuristic.
  - AlphaEarth embeddings (arXiv:2507.22291) and TESSERA (arXiv:2506.20380):
    not planned unless a research question needs them (decided 2026-10-23).
    No Sentinel classifier, no Prithvi.
- **Quality gates** (in `tests/`, run on every ontology change):
  - reasoner consistency (ROBOT with HermiT or ELK)
  - OOPS! pitfall scan
  - SHACL conformance
  - every CQ test
  - the alignment P/R/F1
- **The graph the model sees is generated from the knowledge graph** by SPARQL →
  PyG `HeteroData`. Never hand-code edges in model code. A test checks that
  pandas rules on the same tables give the same edge list (the equivalence
  test, `docs/analysis_plan.md` §10).

**Data and target**
- **Time step: weekly.** Keep daily data in `interim/`.
- **Dataset v4** (decided 2026-10-23) is the dataset of record: v3 (65 wells,
  33 core, training from 2005, BNPE with its documented imputation rules)
  without the values qualified "Incorrecte", with grouped leave-wells-out
  folds and per-window statistics for the less-data regimes. Built
  (`data/processed/dataset_v4`); the baselines are re-run on it with the
  settings tuned on v3. Until those re-runs exist, v3 is the report of
  record. Set `PFE_DATASET` explicitly in every command: the code default
  (`src/config.py`) is still v2.
- **Suspect placeholders are masked when scoring** (decided 2026-10-24): from
  v4, the weeks of a run of ≥ 28 days with a depth of exactly 0.00 m leave every
  scored variant (`src/dataset/placeholders.py` →
  `<dataset>/placeholder_weeks.parquet`). One case: CORNEILLA PD5, Dec 2022 –
  Jan 2024, 60 weeks, qualified "Correcte". The v4 report also shows the
  primary endpoints without the mask (`all_unmasked`); a note to the producer
  is in `docs/supervisor_questions.md` §6.
- **Splits** (`docs/analysis_plan.md`):
  - train ≤ 2019, validation 2020-01 → 2022-04
  - test May 2022 → latest, scored as **drought** (May 2022 → Nov 2025) and
    **recovery** (Dec 2025 →)
  - plus 5-fold **leave-wells-out** (from v4, wells < 2 km apart share a
    fold; held-out wells keep their training-period head statistics, so this
    is transfer to monitored wells, never to ungauged ones), 25/50 % training
    data (statistics from that window only), and a refit on train + validation
- **Primary endpoint:** drought-phase median NSE and skill against
  climatology; KGE'' (datum-free). Effect sizes first, with a cluster-bootstrap
  interval; p-values from a **cluster sign-flip test** over the 14 spatial
  clusters, Holm-adjusted (decided 2026-10-23; the per-well Wilcoxon is shown
  for comparison only). Recovery-phase results are provisional: only 7 wells
  have ≥ 26 fully validated weeks there.
- **Forecast task = hindcast** with reconstructed forcings (annual pumping
  totals and their weekly spread use information after the issue week).
- **Target:** groundwater level (m NGF) per well, plus its **SGI** drought
  class (Bloomfield & Marchant 2013, doi:10.5194/hess-17-4769-2013).
- **Training wells:** all usable dept-66 stations with a masked loss; report
  on the 33 core wells (primary) and the 26 plain wells (secondary), always
  per aquifer group. The 6 karst stations are kept (decided 2026-10-23): the
  karst lies under the Pliocene in the BD LISA stack.
- **Land use:** the RPG, plus the satellite rule above.
- **Never a model input:**
  - **restriction orders.** Groundwater-zone orders are triggered by the very
    piezometers we predict. Surface-water orders are used only to classify
    the restricted years for the imputation.
  - anything computed on the test period
- **Pumping identifiability.** Within a year, pumping is spread with the
  climatic deficit (r = 0.92–0.97). So:
  - effects of pumping are claimed only from between-year and between-well
    variation
  - attributions group "summer demand" (`docs/analysis_plan.md` §8)
  - the main contrasts are repeated under 3 pumping reconstructions (current;
    flat drinking water; irrigation from a fixed crop calendar, independent
    of the year's weather); a conclusion must hold under all three (decided
    2026-10-23)

**Model and constraints**
- **Baselines** (done on v3; no more are added):
  - seasonal naive and climatology
  - **Pastas** (doi:10.1111/gwat.12925), plus WellModel
  - LightGBM (tuned, without the well's own climatology)
  - LSTM and EA-LSTM
  - **Chronos-2** (arXiv:2510.15821): zero-shot, cross-learning and
    fine-tuned. It is the forecasting reference.
  - the distance-graph ST-GNN (GRU, 3-NN graph)
  - the Taccari-graph ST-GNN (doi:10.1038/s41598-024-75385-2)
  - Equal tuning budget: 24 Optuna trials, then re-selection over 3 seeds.
    Budgets and model sizes are reported (`docs/tuning_budget_v3.md`).
  - **Hydrology reference from v4** (decided 2026-10-24, before its results):
    Pastas seasonal + canal built from the **training heads only**
    (`--train-obs`), the start of each well chosen by the frozen
    training-RMSE rule (`src/analysis/pastas_stability.py` writes
    `pastas_seasonal_canal_trainobs_beststart`), whatever its test score. The
    full-series fits stay as historical rows.
- **Main model (decided 2026-10-23): the hybrid** (`docs/feedback.md` §5.5).
  - The KG feeds a heterogeneous GNN.
  - The GNN outputs the parameters of **sign-constrained response
    functions**, one per `lulcw:Influence` type.
  - The responses are summed (a differentiable, Pastas-like superposition),
    plus a small bounded residual network.
  - Comparison: the black-box heterogeneous ST-GNN (HGT/RGCN + temporal
    convolutions or a GRU) on the same graph.
- **Constraints = response signs from the ontology:**
  - abstraction lowers the head
  - effective rain raises it
  - canal return flow raises the alluvium head
  - river recharge, only where documented
- **Applying them:**
  - *soft:* gradient or counterfactual sign penalties (Ross et al. 2017)
  - *hard:* **monotone by construction**: sign-constrained gains, e.g.
    −softplus(·) for a decreasing influence. LightGBM `monotone_constraints`
    serve as a cheap check. The sign must hold on the whole path: the gain
    depends on static/KG features, never on the driver it constrains, and the
    residual network does not see the constrained drivers; a finite-difference
    test checks it (`docs/analysis_plan.md` §10).
  - PiShield is dropped: it constrains outputs, not response signs.
- **No head-ordering rule.** In the Step 6b pair check, the shallow head is
  above the deep one in only 50.5 % of pair-weeks.

**Validity and explanations**
- **Reasoning shortcuts** (Marconato et al., arXiv:2305.19951). The concepts
  are the **driver contributions**. Four tests:
  1. A **semi-synthetic twin**:
     - inputs: the real forcings, wells, pumps and KG
     - synthetic heads from known response functions plus AR noise
     - two variants: pumping timing tied to the deficit, or independent of it
     - harder variants (decided 2026-10-23): a response shape the model does
       not have, a driver the model does not see, wrong KG links
     - concept accuracy = the error of the recovered contributions
  2. Disagreement of the contributions across seeds (the BEARS idea).
  3. **Semantic ablation:** rewire the KG edges with degrees preserved and
     shuffle the attributes (cf. Heudorfer et al. 2024,
     doi:10.5194/hess-28-525-2024). Its power is calibrated on the twin.
  4. Counterfactual sign accuracy within the observed year-to-year range;
     the Pastas gains are a comparator, not causal ground truth.

  Ontology consistency, faithfulness and causal correctness are three
  separate properties, each with its own evidence.

  SGI accuracy is reported, but it is not the shortcut test.
- **Explanations:**
  1. contributions per driver group: exact with the hybrid; for the black
     box, Integrated Gradients and GNNExplainer aggregated by node type and
     relation
  2. SPARQL on the KG for the chain of entities
  3. **templated text**, in French and English
  4. faithfulness (fidelity+/−; Azzolin et al., arXiv:2406.15156)
  5. tests: every named entity exists and is connected to the well, and the
     stated sign matches the polarity

  An LLM may polish fluency only and never invents content.
- **Case studies:**
  - the summer 2024 local Pliocene rise after reduced abstraction (BRGM
    bulletin, 16 Sept 2024)
  - the 2023 drop
  - an alluvium well (canal)

**Research framing (decided 2026-10-23):**
- **(A) the use conflict on the Pliocene** (drinking water against agriculture)
  is the main story: 20 of the 33 core wells, the CQ2 evidence, the 2024 BRGM
  event. **Refined 2026-10-24 (Assil):** no irrigation volume passes the main
  pump policy, so the model's claims are about **drinking-water pressure** on
  the Pliocene within the agricultural context; farm-pumping effects come only
  from the all-links sensitivity, labelled provisional.
- **(B) canal-return recharge** is a secondary case study for the alluvium. It
  keeps the land-use side of the subject visible.

Both are `lulcw:` causal knowledge.

---

## 4. Environment

**Current machine (since October 2026): Arch Linux**
- 4 cores, 11 GB RAM, no NVIDIA GPU; shell zsh
- The battery holds 12 % of its design charge: keep it plugged in during long
  runs.
- Venv: `.venv`, Python 3.12, created with
  `uv venv --python 3.12 .venv`. Install with
  `uv pip install --python .venv/bin/python -r requirements.txt`.
- Run scripts as `.venv/bin/python -m src.<pkg>.<module>`. Set
  `PYTHONIOENCODING=utf-8`.
- Cold-start check passed on 2026-10-13: Steps 4–6a re-ran from the cache
  with identical numbers.
- Use `pathlib` for every path. Pin dependencies in `requirements.txt`.
  Install the ontology tools when they are first used, then pin them:
  `rdflib`, `pyoxigraph`, `pyshacl`, `ontoaligner`; ROBOT (Java) for the
  reasoner and report.
- Use `py7zr` for `.7z` and `pyogrio` for geodata
  (`pyogrio.list_layers()` to inspect a GeoPackage or FileGDB).

**Compute plan** (`docs/roadmap.md` §5; how-to in `docs/gpu_howto.md`)
- **Laptop CPU:** the data work, the knowledge graph, scoring and reports.
  **No model training on the laptop** (Assil, 2026-10-24): CPU fits (LightGBM,
  Pastas) go to Kaggle, GPU fits to Colab. The graph is tiny: about 65–250
  nodes × about 1,100 weeks.
- **Kaggle, CPU only** (since 2026-10-24): without phone verification there
  is no GPU and **no internet**, but kernels run in the background (4 CPUs,
  32 GB, Python 3.13, 12 h). The pinned packages come as offline wheels from
  the private dataset `pfe-wheels-cp313`; `scripts/kaggle_cpu.py`
  (`docs/gpu_howto.md`, "Kaggle CPU").
- **GPU:**
  - **Google Colab, free T4** (main GPU since 2026-10-23).
    `scripts/colab_run.py` saves results to Drive every 5 min. Assil clicks
    the Drive permission at each session.
  - **Camber** XSMALL L4: a monthly allowance that renews on the 13th; used
    up until 2026-11-13. **Always STOP the node.**
  - **No Kaggle GPU:** its phone-verification SMS does not reach Tunisian
    numbers (Kaggle CPU works, see above).
  - Lightning AI and Modal are untested backups.
- **The GPU goes to:**
  - tuning sweeps
  - the Phase 4 runs (arms, constraints, twin)
  - local open LLMs (alignment, text extraction)
- **Google Earth Engine:** Sentinel-2 NDVI per parcel, and the optional
  AlphaEarth features. It needs Assil's Earth Engine account; the login is
  his.
- Every sweep is resumable: one result file per run, skipped if it exists.
  Checkpoints go to persistent storage (Drive, the Camber Stash).

**API lessons (still valid)**
- **Hub'Eau prélèvements:** `size=5000` got the connection reset, and then
  hubeau.eaufrance.fr refused the machine for about 10 minutes. Use
  `size=2000`. `niveaux_nappes` accepts 5000.
- **IGN Géoplateforme:** the `/resource/RPG` listing is paginated (35 pages)
  and returns 429 if requests come too fast; pause 1 s per page. Crop
  code → group tables:
  `https://data.geopf.fr/annexes/ressources/documentation/`.
- **Chrome extension:** uploads at most 10 MB per file, so split bigger files.
  It cannot reach file inputs inside Colab cell outputs. Never type long text
  into a notebook cell.
- **Shared modules:**
  - `src/config.py`: paths, CRS, window
  - `src/web.py`: retrying `requests` session
  - `src/ingest/hubeau_piezo.fetch_all()`: follows Hub'Eau `next` links

**Old Windows laptop (legacy, only if work moves back there)**
- Windows Smart App Control blocks brand-new wheels. Hence the pins: pandas
  2.2.3, pyarrow 18.1.0, numpy 2.2.6, pyogrio 0.10.0.
- Never `pip install --upgrade` blindly there, and don't suggest turning
  Smart App Control off.

**Learning notes.** Assil wants one note per step in
`docs/notes/stepNN_<topic>.md` (what was done / why / what to consider), plus
the progress table and glossary in `docs/notes/README.md`. Write it before
reporting a step as done.

---

## 5. Repository layout

```
src/ingest/      one script per source, runnable as python -m src.ingest.<name>
src/analysis/    profiling, joins, figures, reports
src/dataset/     model-ready dataset builder (weekly tensors, masks, splits)
src/kg/          KG instantiation, SHACL runs, SPARQL → HeteroData export
src/models/      baselines and the knowledge-guided model
src/explain/     attributions, faithfulness, templates
scripts/         CPU/GPU sweep runners (run_cpu.sh, run_gpu.sh, colab_run.py, colab_pull.py)
configs/         one YAML per experiment (to add before Phase 4; runs already store config.json)
ontology/        lulcw module (.ttl), alignments/, shapes/ (SHACL), rules/ (SHACL-AF), catalog
tests/           unit tests, competency-question queries (tests/cq/), ontology quality gates
data/raw/        untouched downloads             (gitignored)
data/interim/    cleaned / filtered tables       (gitignored)
data/processed/  model-ready datasets            (gitignored)
data/README.md   data log — committed
results/         run outputs, one folder per run (gitignored)
docs/            roadmap, analysis plan, reviews, memos, CQs, ontology design, notes
docs/literature/ reading list, comparison table
paper/           LaTeX manuscript (from Phase 6)
reports/figures/ maps and plots, each made by a script
Documents/       the subject, the SAVE Water proposal, the PFE guide
Articles/        publisher PDFs (gitignored: never push them)
notebooks/       exploration only; anything that matters moves into src/
```

---

## 6. Working rules

1. **Nothing is done until it runs from cold.**
   - Every script must be idempotent and cache what it downloads.
   - If a file already exists with a sensible size, skip re-downloading it.
2. **Log every pull** in `data/README.md`:
   - source and endpoint or URL
   - parameters
   - retrieval date
   - row counts and file sizes
3. **Never commit data.** Commit code after each step works, with a clear
   message.
4. **Don't guess column names.** Print the columns and a sample row from every
   new API or file before writing logic against it.
5. **Don't force the old numbers.**
   - Section 8 lists the counts from the first run.
   - If a new count differs, report the difference and explain why (for
     example, new data since August 2026).
   - Never tune filters just to hit the old number.
6. **Explain in plain language.** After each step, give Assil 3–6 sentences:
   - what was done
   - what the numbers mean for the project
   - what comes next

   He is learning the domain, so explain the *why*, not only the *what*.
7. **Ask before** deleting files, downloading more than 2 GB, or touching a
   design decision in section 3.
8. **Manual steps:** when a download needs a browser, stop and tell Assil
   exactly what to click and where to save the file. Then continue.
9. **Citations:**
   - Never invent a reference.
   - Every paper cited in code comments or docs needs a DOI or arXiv ID that
     you have checked.
10. **Experiments are paper-grade from the first run:**
    - every run comes from a config file
    - 5 seeds for neural models
    - results written to `results/<run_id>/`
    - metrics include NSE, skill against climatology, KGE'' and RMSE, with
      separate scores for the drought and recovery phases
    - every figure is produced by a script, never by hand
11. **Honest baselines.** Tune baselines with the same budget as our model.
    If a baseline wins, report it.
12. **Ontology work:**
    - Check every reused term at its source, and record the date.
    - Never write an IRI you have not seen resolve or listed in the source.
    - Ontology changes pass the quality gates (§3) before they are committed.

---

## 7. CURRENT TASK: finish Step 12a (GPU runs), then Phase 3 (Step 12)

### ▶ Where we are (read this first in a new session)

**2026-10-23, 16:30: second external review (codex) adopted.** Review in
`docs/review_codex_2026-10-23.md`; Claude checked every number in it against
the data (all confirmed). Assil decided the same day:
- **Dataset v4** = v3 without the 71 "Incorrecte" weeks, with a strict
  "validated" flag, leave-wells-out folds that keep wells < 2 km apart
  together, and the 25/50 % regimes recomputing their statistics on their own
  window. All baselines are re-run on v4 with the settings tuned on v3. The v3
  runs in progress **finish as planned** (tonight), except the EA-LSTM
  regimes: stopped at 20:58 (see "State" below).
- **Analysis plan v2:** cluster-level sign-flip test instead of the per-well
  Wilcoxon; a harder twin (wrong response shape, missing driver, wrong links;
  Pastas gains a comparator, not the reference); main contrasts under 3
  pumping reconstructions; plan tagged in git before Phase 4, then a
  confirmation check on weeks observed after the freeze.
- **Framing:** umbrella question above RQ1–4; the ontology is credited with
  traceability, consistency and reuse, and a test shows that plain tables with
  the same rules give the same edges.
- **Done the same evening (Step 12b, `docs/notes/step12b_review_fixes.md`;
  verdict per point in `docs/review_codex_response.md`):**
  - dataset v4 built
  - evaluation `strict` variant
  - cluster sign-flip test
  - R3 window statistics
  - analysis plan v2
  - task 12.3, the pump → unit attribution
  - the v4 re-run scripts
  - tests: `test_stats`, `test_folds`, `test_pump_attribution`
- **Until the v3 report is final, every code change must leave v3 behaviour
  identical** (gate it on v4). No sweep has been running since 20:58, so
  `scripts/run_cpu.sh` may be edited again.
- **Decided by Assil on 2026-10-24:** main runs with confident + probable
  pump links (72 % of the plain's declared volume) instead of confident only
  (27 %); confident only and all links are sensitivity runs (§3).

**2026-10-25: subject-alignment review (Codex) adopted.** `docs/review_codex_2026-10-25.md`;
verdicts and the working road in `docs/review_codex_2026-10-25_response.md`. Checked:
no dated land use entered the dataset, the baselines or the KG. **Read both files at
the start of every session, and answer the review's six "recurring check" questions in
the step note before choosing a substantial task.** Decided by Assil the same day:
(1) annual RPG 2015–2025, clipped to the département extent (`DEPT_BBOX`, so every well's 3 km zone is covered), raw archives deleted after clipping;
(2) CQ7, CQ10, CQ15 → MUST (9 MUST); (3) a pre-registered land-use test in RQ1
(potential crop demand, FAO-56 Kc; LightGBM and LSTM ± feature + shuffled placebo;
`docs/analysis_plan.md` §14 item 13), which also defines pumping reconstruction (3).
Then (4), before any run: the main index counts only the classes usually irrigated
(orchards, vegetables, artichokes, maize, citrus); vines, olives, nuts and fodder only in
the "wide" sensitivity row, because the 2020 census irrigates about 4–7 % of the vines.
(5) After the second Codex review of the day (`docs/review_codex_2026-10-25b.md`, answered
in `docs/review_codex_2026-10-25b_response.md`), still before any run: a "frozen" variant
(the 2019 crop areas in every year) separates crop geography from change over the years;
a positive main result is worded "incremental predictive information from the demand
index"; land-use runs carry a content hash of their inputs.
The agricultural path the data can carry: crop demand → farm-pumping timing, and canal
irrigation → alluvium return flow; farm-borehole links stay a sensitivity.

**Plain-words guide for Assil (2026-10-23):** `docs/explainer/index.html` (open it in a
browser; offline). It covers every step, the four data versions, the decisions and the next
phases, with charts from our data (`src/analysis/explainer_data.py` → `data.js`). **Keep it
current:** when a step finishes or a decision is taken, update its chapter and re-run
`.venv/bin/python -m src.analysis.explainer_data`.

Read `docs/review_2026-10-23.md` for why the plan changed earlier today.
- Assil approved the revised plan (this file, `docs/roadmap.md`).
- **The supervisor answered (2026-10-23): "do what is best for the project".**
  Assil's decisions and their reasons are in `docs/supervisor_questions.md` §1.
  - Still to obtain (facts, §3 there): the defence date, SAVE Water D4.1/D3.1,
    contacts, publication details, monthly drinking-water production.
  - The e-mails are ready in §4–5 there; Assil sends them.

**2026-10-27: Codex review of 2026-10-26 answered** (`docs/review_codex_2026-10-26.md`, verdicts
in `docs/review_codex_2026-10-26_response.md`; Assil: "if u think they are good ideas approve
them and continue coding"). All 9 points hold; done: graph releases (`src/kg/release.py`: facts,
rule outputs, rules, shapes and ontology bound by SHA-256, written only after a clean validation,
checked by every reader), CQ4 negative answers only after a completed search, exact paired support
(`support` digests in every v4 metrics table; no hidden mismatch found; LU-4 unchanged), complete
run manifests and panel-cache records, `docs/run_inventory_v4.md`, the gold-set protocol (40 dev /
158 eval codes, a 30-code second-annotator subset, alternatives). Written as dated amendments,
some **to confirm by Assil before the export** (analysis plan §14 item 15): the per-regime depth
threshold with minimum support (only 0 / 2 / 13 of 47 pairs within 10 / 20 / 50 m), one recharge
proxy per influence (PE main, DRAINC sensitivity: DRAINC is part of PE), the D vs C wording and
inventory, the recharge pathways the 5 km rule omits (SMNPR and BRGM/RP-71486-FR read: the
Pliocene is fed mainly by the Têt and its alluvium upstream, the Corbières karst, the border
massifs and pumping-driven leakage from the Quaternary), a bounded domain review of the two LU-6
wells.

**State at 2026-10-27 (CQ4 increment 1 done).** The CQ4 rules of 2026-10-26 never finished:
rdflib re-sorts a pattern block when it evaluates it, so a constant (`layerOrder 1`) or a lone
class pattern jumps ahead and crosses every piece with every layer and coverage; fixed (FILTER on
a variable; no class pattern where the domain implies it), the whole derivation ≈ 5 min. Unit-wide
clipping found and reported: 681AF00 (15 % of its outcrop outside the cells) and 681AO00 (9 %) are
partial in the forcing extent (`lulcw:mappedOutcropAreaM2`, ontology 0.4.0, 255 terms). Release of
2026-10-27: facts 373,306 triples, 317 outcrop coverages (47 forcing extent, 270 in the 65 search
zones), 1,134 cell weights, stratigraphy 150 direct + 16 indirect (the added outcrop polygons
bring their stacks), no violation; `test_ontology`, `test_kg`, `test_kg_rules` (25 negative
controls, GeoPandas oracle), `test_cq` (CQ4 fixtures and data, MILLAS 27.08 km²),
`test_release`, `test_stats` pass. Colab session 2 results (Taccari regimes, Chronos-2
zero-shot + cross-learning) are still on Drive, **not yet pulled**; `chronos2_ft` not run.

**CQ4 increment 2 done (2026-10-27 evening; step note, last section).** Recharge proxies are
`lulcw:Influence` records (ontology 0.5.0, 262 terms): one per weather cell over the outcrop of
the exact unit a well is attributed to, in its 5 km search zone (main: 193 for 54 wells) and in
the forcing extent (unit-wide sensitivity: 960 for 59 wells); driver the cell's weekly effective
rainfall (`proxyFor GroundwaterRecharge`; soil drainage only as a replacing sensitivity, a shape
refuses both on one path), sign non-decreasing, eligible, **its use as a constraint and the proxy
choice settled at Gate 3** (analysis plan §14 item 15); each names its omitted pathways
(`omitsPathway`: lateral inflow, vertical leakage, river exchange, canal return flow). No local
proxy for the 5 Pliocene wells without Pliocene outcrop within 5 km (`cq08_status` recharge
"none_found", a completed search) and CARRIE (760AE09 outside BD LISA: "unknown"). Path selection
moved to rule order 90. CQ8 stays partial until CQ5/CQ6.

**Resume here:** (1) CQ5 and CQ6 (bounded search for river reaches and canal command areas;
gaps stay documented); (2) 12.8: the export with the per-well, per-relation inventory, bound to
the graph release, and the per-regime depth threshold once Assil confirms it; (3) the two-well
executable path (LU-6 → tensors → a model output → its contribution explanation), then the small
twin. Writing SHACL-AF rules: no constant or one-variable class pattern ahead of the pattern that
binds its subject (rdflib re-sorts by unbound terms; comment in the rules file). Writing CQ
queries (pyoxigraph 0.5): an OPTIONAL block is evaluated on its own in the written order, so it
starts from its most selective pattern; never GROUP BY over EXISTS flags (they run once per row).
**Assil:** retry the Drive download of the six folders (look at Chrome's download bubble), then
`scripts/colab_pull.py <zip> --version v4` and the v4 reports (they now show exact support);
`chronos2_ft` at the next GPU session (new T4 runtime, mount Drive, `!pip uninstall -y -q
datasets`, `%env PFE_DATASET=v4`, `%env STEPS=chronos2_ft`, the run cell); confirm or change the
proposals of analysis plan §14 item 15; the AGROVOC gold set: write the plant/product/land-use
rule first (`src/kg/agrovoc_gold.py` docstring), then `check`; `blind` makes the second
annotator's sheet; ask the supervisor (or SMNPR/BRGM) for the bounded review of the two LU-6
wells.
- **Assil's go (2026-10-24):** "u can use kaggle and colab to train", and no
  model is trained on the laptop any more. This lifts the hold of 2026-10-23
  evening ("keep only v3 running").
- **Kaggle CPU ✅ done** (kernel `assilbouzaine/pfe-v4-cpu` v2, 14:43–15:20
  UTC, 36 min on 4 CPUs; pulled and rescored 2026-10-24): naive, LightGBM
  (`lgbm_sim`, `lgbm_fc`, `lgbm_noclim_tuned` + `_lwo/_f25/_f50`), Pastas,
  `pastas_seasonal_canal`, `pastas_wellmodel` in `results/v4`. The naive rows
  equal the laptop's v4 rows of 2026-10-23 (environment check passed). Scores:
  the v4 report.
- **Colab T4, session 1 ended at 17:13 UTC** (started 15:10 UTC in
  `pfe_v3_gpu.ipynb`). There was no error and no closing log line. At 18:40 UTC
  Colab refused a new GPU "due to usage limits", so the stop was either the
  quota or the idle timeout (92 min after the last interaction, 15:41); we cannot
  tell which. Done and saved on Drive (`pfe_colab/results_gpu/v4`):
  - the finals of LSTM, distance ST-GNN and Taccari
  - the regimes of LSTM and ST-GNN
  - Taccari left-out wells: fold 0, and fold 1 seeds 0–2

  Pulled to the laptop and scored on 2026-10-25 (Drive `pfe_colab/results_gpu/v4`
  → Download → `scripts/colab_pull.py`); Taccari's partial folds stay on Drive
  until every fold exists. Left: `regimes:ealstm` (Kaggle), the rest of
  `regimes:taccari` (32 seed-runs, ≈ 3 h) and Chronos-2 ×3 (Colab).

  The v4 bundle is on Drive as `pfe_colab/gpu_bundle.zip`; the v3 one is kept as
  `gpu_bundle_v3.zip`. Run line:
  `!unzip -oq /content/drive/MyDrive/pfe_colab/gpu_bundle.zip -d /content/pfe && PFE_DATASET=v4 python /content/pfe/scripts/colab_run.py`.
  `V4_STEPS`: the finals of LSTM, distance ST-GNN, Taccari, EA-LSTM, then
  their regimes, then Chronos-2 (≈ 6–8 T4-hours, 2–3 sessions).
  **EA-LSTM was dropped in session 1:** `tests/test_ealstm.py` failed on the
  GPU because it took gradients in eval mode, which cuDNN refuses ("cudnn RNN
  backward can only be called in training mode"); a test bug, not a model
  bug (training runs in train mode). Fixed 2026-10-24 (train mode, dropout 0;
  CPU half passes). **Session 2:** Drive `pfe_colab/gpu_bundle.zip` (md5
  18c1256e…, copied 15:41 UTC on 2026-10-24 through the Colab Terminal) is older
  code; the laptop's `gpu_bundle.zip` was rebuilt on 2026-10-25 (md5 97b2cf45…,
  38.3 MB; new runs save their weights): upload it first (Files panel in 7 MB
  parts, then `cat` + `cp` to Drive in the Terminal; parts that hang are
  re-sent, and a `change` event on `#file-tree-upload-input` starts a stalled
  one). In a new runtime: mount Drive (Assil), then the same run line;
  finished runs are restored from Drive and skipped. **Session 2, when Colab
  gives a GPU again** (EA-LSTM moved to Kaggle): put
  `STEPS="chronos2 chronos2_xl chronos2_ft regimes:taccari"` before `python` in
  the run line (≈ 3.5 T4-hours). Touch the tab at least hourly. Pull with
  `scripts/colab_pull.py` (Drive folder `pfe_colab/results_gpu` → Download).
- **Kaggle CPU, kernel version 4 ✅** (21:11–08:11 UTC, stopped cleanly at its
  11 h budget; pulled and rescored 2026-10-25): the Pastas multistart (2 × 10
  starts), EA-LSTM's final (torch 2.11.0+cpu, `tests/test_ealstm.py` passed) and
  its left-out-well folds 0–3. (Version 3 never started: ERROR, empty log, 16 s
  after a new bundle version; `push` now waits and re-pushes once,
  `docs/gpu_howto.md`.) **Kernel version 5** (pushed 10:04 UTC on 2026-10-25,
  `--steps "regimes:ealstm"`, resumes from the pulled output): fold 4, R3 50 %,
  R3 25 % and the refit, about 6 h. Then `scripts/kaggle_cpu.py pull` (it
  rescores) and the two reports again.
- **v4 results so far** (interim, `docs/results_baselines_v4.md`,
  `docs/results_hydro_v4.md`; step 12b note, last section). The v3 report stays
  as Step 12a's record.
  - **The Pastas reference depends on its starting values** (measured
    2026-10-25): over 10 starts its drought median NSE spans −1.26 to −0.60
    (training heads only) and −1.24 to −0.51 (full series); a core well's
    drought NSE moves by a median 1.2–1.4 between starts. The frozen rule gives
    **−0.75, the reference of record**. The v3 → v4 move of the old reference
    (−0.73 → −0.51) lies inside this spread.
  - Drought NSE / skill: ensemble (Pastas reference + LSTM + distance ST-GNN)
    0.14 / 0.51, LSTM 0.12 / 0.57, distance ST-GNN 0.06 / 0.55, Taccari −0.05 /
    0.49, LightGBM −0.08 / 0.49, EA-LSTM −0.16 / 0.37.
  - Cluster test against the reference: ensemble p_holm 0.020 (NSE) / 0.005
    (skill), distance ST-GNN skill 0.009; the others 0.07–1. Taccari's v3 pass
    (0.013) is not repeated. Repeated against each of the 10 starts: every
    tuned model keeps a large median gain (+0.30 to +1.60 NSE), but only the
    ensemble passes against all 10 (single models 2–4 of 10).
  - Left-out wells (v4 folds keep twin wells together): LightGBM −0.58, LSTM
    −0.94, distance ST-GNN −0.98: the v3 "graph models lose least" came from
    split twins.
  - When the last runs arrive: pull, regenerate `baseline_report` and
    `hydro_errors` (the ensemble's candidates are final), then switch the
    explainer's scores chart to v4.
- **Third review (Codex, 2026-10-24 night):** `docs/review_codex_2026-10-24.md`;
  every factual claim checked, verdicts and status in
  `docs/review_codex_2026-10-24_response.md`. Quick fixes done 2026-10-24;
  **second pass done 2026-10-25** (every recommendation checked against the
  code; step 12b note, last section; analysis plan §14). **Decided by Assil on
  2026-10-24:** (1) main story = drinking-water pressure (irrigation gets 0 % of
  the main pump links; farm effects only from the all-links sensitivity); (2)
  the v4 Pastas reference = training heads only, frozen best-start rule; (3)
  arms C–F share one backbone, with the review's controls; (4) suspect
  placeholder weeks masked (CORNEILLA PD5, depth 0.00 m for 413 days).
  Done in the second pass: `docs/pump_coverage.md` (main policy 61.8 % at
  exact-unit resolution), `docs/results_hydro_<v>.md` (SGI drought classes),
  saved models + manifests, `tests/test_replay.py`, `tests/test_pumping_conservation.py`,
  `tests/test_regime_boundaries.py`, `docs/tuning_budget_v3.md`,
  `stats.cluster_sensitivity`. All local v4 runs rescored with the mask.
- **Left from 2026-10-23:** Assil disconnects the old Colab runtime if it is
  still on, and sends the v3 results in the next monthly report to the
  supervisor. The v3 EA-LSTM regimes stopped at 20:58 are a record only
  (`results/v3/ealstm_tuned_lwo/`, step-12a note §5d).

**Assil's to-do (no model needed)**
1. Send the two e-mails in `docs/supervisor_questions.md`:
   - §4 to the supervisor (decisions + the defence date)
   - §5 data request: monthly drinking-water production
2. Review the 10 SHOULD/COULD competency questions
   (`docs/competency_questions.md`; the 6 MUST were approved on 2026-10-24):
   add, drop, priorities, and the open points listed there.
3. Later, for task 12.10: an Earth Engine account (sign-in is his).
4. Send the note about CORNEILLA PD5 to its producer (SMNPR):
   `docs/supervisor_questions.md` §6 (French text ready).
5. The AGROVOC gold set (task 12.9): fill `configs/lu_agrovoc_gold.csv` (one relation and
   concept per code, most area first; protocol in `src/kg/agrovoc_gold.py` and the step note,
   12.9). First decide the plant-or-product rule (grapevines / Prunus persica vs peaches).
   `python -m src.kg.agrovoc_gold search "<words>"` finds concepts; `check` validates.

**Next for Claude, while the models run or after:**
0. **Land-use thread first** (road: `docs/review_codex_2026-10-25_response.md` §4).
   LU-1, LU-3 (per well) and **LU-4 done**. LU-4 (2026-10-26): main contrast on vs none,
   chosen by Assil before the pull (commit `1840070`); **no detectable improvement** from the
   demand index under these models, settings, wells and drought period: drought median ΔNSE
   +0.016 (LightGBM) and +0.001 (LSTM; interval up to +0.16), p_holm 1.0; placebo, wide and
   frozen show none either; the LSTM's
   machine effect (Kaggle CPU vs Colab GPU) is −0.032, as large as the effects tested (step 12d
   note). Next on the thread: Assil's AGROVOC gold set, then OntoAligner (12.9), LU-6 (end-to-end example),
   LU-5 when Assil has the Earth Engine login. To propose at Gate 3: one machine type per
   Phase 4 contrast (or a same-machine control).
1. ✅ Step 12a done (2026-10-23 evening). 🔄 The v4 re-runs: Kaggle kernel 4
   and Colab session 1 pulled on 2026-10-25, reference run, replay, ensemble and
   the interim reports done (see State). Kaggle kernel 5 pulled on 2026-10-25 (every EA-LSTM
   regime in `results/v4`). Colab session 2 ended on 2026-10-26 (see State): left are
   `chronos2_ft` (next GPU session) and the pull of the six new folders
   (`scripts/colab_pull.py <zip> --version v4`); then
   `PFE_DATASET=v4` `src.analysis.baseline_report` and `src.analysis.hydro_errors`,
   and the explainer's scores chart on v4.
2. Literature, from the second review:
   - the positioning matrix in `docs/literature/comparison_table.md`: past heads
     as input? forcings? split? knowledge supplied? explanation validated?
   - fill the open-access rows (Heudorfer 2024, Wu 2025 JGR-MLC if open)
3. ✅ Task 12.4, version 0.1.0 (2026-10-24; step note §12.4). ✅ Task 12.5
   (2026-10-24 evening; step note §12.5): `src/kg/build_kg.py` →
   `data/processed/kg/lulcw_kg_v4.ttl`, checked by `tests/test_kg.py`. 🔄 Task 12.6
   (2026-10-25; step note §12.6): `PFE_DATASET=v4 python -m src.kg.apply_rules` (after
   `build_kg`) runs `ontology/rules/lulcw-rules.ttl` and validates with
   `ontology/shapes/lulcw-shapes.ttl` → `lulcw_kg_v4_rules.ttl` (derived links, kept apart
   from the facts) and `lulcw_kg_v4_shacl.ttl`; `python -m tests.test_kg_rules`; ontology
   0.3.0; land use inside the graph done the same evening (step note §12.6, continued).
   ✅ Validation speed-up (2026-10-26, step note "12.6 fix"): 26 min → 134 s (the slow
   class-area check became a SHACL Core constraint plus one whole-graph key query), and the
   files now store doubles exactly (`build_kg.ExactTurtle`: rdflib's 7 digits had made 2,068
   stored class areas fail their own sum shape). **12.7: 7 of 9 MUST CQs done** (`tests/cq/`, step note §12.7; left CQ10, CQ15 with their inputs, SHOULD/COULD fixtures; parameters bound by a VALUES clause at the
   top of WHERE; in pyoxigraph 0.5 write all triple patterns before any BIND/UNION and count
   with OPTIONALs rather than EXISTS joins, both were orders of magnitude slower), then 12.8 (export + equivalence test against pandas; take each
   facility's volume once per well, since an influence is stored per evidence path).

**Phase 3 (Step 12):** the task list is below. Freeze the ontology design after
Assil's review of the competency questions.

### ▶ STATUS

| Step | Status | Note |
|---|---|---|
| 1 Repo and environment | ✅ done | `docs/notes/step01_environment.md` |
| 4 Hub'Eau piezometers | ✅ done | `docs/notes/step04_piezometers.md` |
| 5 RPG parcels | ✅ done | `docs/notes/step05_rpg.md` |
| 6a BNPE abstraction | ✅ done | `docs/notes/step06a_bnpe.md` |
| 6b BD LISA | ✅ done | `docs/notes/step06b_bdlisa.md` |
| 7 Gate 1 memo | ✅ answered 2026-10-23: the choices are left to Assil | `docs/memo_gate1_feasibility.md`, `docs/supervisor_questions.md` |
| 8 Phase 1: dataset v1 | ✅ done | `docs/notes/step08_dataset.md` |
| 9 Phase 2: baselines on v1 | ✅ done | `docs/notes/step09_baselines.md` |
| 10 Baselines on dataset v2 | ✅ done | `docs/notes/step10_baselines_v2.md` |
| 11 Gate 2 summary | ✅ answered 2026-10-23: the choices are left to Assil (decisions in `docs/supervisor_questions.md`) | `docs/summary_gate2_results.md` |
| **12a Fixes from the critical review** | **✅ 2026-10-23:** evaluation, analysis plan, dataset v3, all v3 baselines (EA-LSTM regimes on v4 only), final v3 report | `docs/feedback.md`, `docs/analysis_plan.md`, `docs/notes/step12a_fixes.md` |
| **12b Fixes from the second review** | **✅ 2026-10-23** (code, dataset v4, analysis plan v2, tests); 🔄 the baseline re-runs on v4 started 2026-10-24 (Kaggle CPU + Colab T4); first results pulled 2026-10-25 (interim `docs/results_baselines_v4.md`); EA-LSTM regimes on Kaggle, Chronos-2 and Taccari regimes wait for Colab session 2; third review checked and done (two passes, 2026-10-24/25) | `docs/review_codex_2026-10-23.md`, `docs/review_codex_response.md`, `docs/notes/step12b_review_fixes.md` |
| **12 Phase 3: ontology + KG** | **🔄 started 2026-10-23.** 12.1 drafted, 12.2 started, 12.3–12.5 done, 12.6 done for links and land use (2026-10-25), 12.7: 7 MUST CQs (2026-10-26) and CQ4 with graph releases and recharge proxies (2026-10-27) | `docs/review_2026-10-23.md`, `docs/competency_questions.md`, `docs/ontology_design.md`, `docs/notes/step12_ontology.md` |

### Step 12: Phase 3 tasks, in order

| # | Task | Status |
|---|---|---|
| 12.1 | Competency questions (16) with example answers | ✅ drafted; the 6 MUST (CQ1, 2, 3, 8, 11, 12) approved by Assil on 2026-10-24, so 12.4 starts with them; CQ7, CQ10, CQ15 promoted to MUST on 2026-10-25; the 4 SHOULD / 3 COULD are still under his review |
| 12.2 | Reuse table, term by term, and the modelling patterns (`docs/ontology_design.md`) | 🔄 started |
| 12.3 | **CQ2 data step:** attribute each groundwater abstraction point to a unit, with provenance and confidence | ✅ 2026-10-23: `src/kg/pump_attribution.py` → `data/interim/pump_unit_attribution.parquet`. Rules measured on 130 recorded boreholes (flag True → alluvium 95 %; flag False + Pliocene under the point → Pliocene 92 %; False alone 53/112). The record is depth-checked. "Probable" only for the uses that were measured. Plain volume 2012–24: confident 27 %, probable 45 %, possible 21 %, unknown 7 % |
| 12.4 | Ontology module `lulcw:` + imports/alignments in `ontology/`; IRIs and metadata; the quality gates in `tests/` | ✅ 0.1.0 on 2026-10-24 for the 6 MUST CQs: 191 terms (FR/EN labels, definitions), local copies of the reused terms (`src/kg/build_imports.py`), alignments to GWML2/HyFO and SWEET, `python -m tests.test_ontology` (ELK + HermiT consistent, negative control, ROBOT report). SHOULD/COULD modules, the w3id redirect and OOPS! still to do |
| 12.5 | KG instantiation from the parquet tables (rdflib → Turtle → pyoxigraph) | ✅ 2026-10-24: `src/kg/build_kg.py` (61 s) → `data/processed/kg/lulcw_kg_v4.ttl`, 205,650 triples: 65 piezometers (station, head series, groundwater body, polygon; 60 recorded monitoring units, 5 explicit unknowns), 47 units typed by the written rule, 201 BD LISA polygons with stacks, 2,187 groundwater facilities with the 12.3 attributions (resolution-aware: flag_true = alluvium group probable, exact entity possible), 12,951 annual declared volumes (SOSA, with acquisition mode), provenance and 3 export policies. Facts only: derived links come from the 12.6 rules. `tests/test_kg.py`: 8 checks against pandas oracles + 2 negative controls. Ontology 0.1.1 (`EnergyUse`, `geo:hasMetricArea`) |
| 12.6 | SHACL shapes and SHACL-AF rules: Influence links, `ProbablyIrrigatedParcel`, `HighIrrigationDemandZone`, `ConfinedSetting` | 🔄 2026-10-25, links part done: `ontology/rules/lulcw-rules.ttl` (SHACL-AF, pySHACL) and `ontology/shapes/lulcw-shapes.ttl` (SHACL), run by `src/kg/apply_rules.py`: 95 direct contacts + 13 indirect orderings, each witnessed by its polygon (plain = Step 6b's 26 edges), 47 same-unit well links ≤ 5 km, 1,848 pump → well influences (1,830 exact-unit: non-increasing sign, eligible; 18 group-level: sign unknown, not eligible), policy selections (a path is selected only if both its attributions are); shapes: no violation (8 notes: wells without an investigation depth); rules 65 s, validation 51 s. `tests/test_kg_rules.py`: CQ3/CQ8/CQ11/CQ2 fixtures, 9 negative controls, pandas oracles. Ontology 0.2.0 (`admitsConfidence`, `searchRadiusM`). Land-use part done the same evening: ontology 0.3.0 (land-use module, 39 terms), `src/kg/landuse.py` (198 crop codes, 14 classes + unmapped with FAO-56 parameters, 65 zones, 13,684 clipped areas, 1,430 calendar-year demand estimates; graph 356,377 triples), rules: crop class of every code (198 mapped, none unmapped), 5,465 class areas, 715 dated demand categories (248 high; threshold 597,028 m³ = upper tercile of 2015–2019); no violation; tests: CQ7 fixtures, 13 negative controls, pandas oracles pass. 2026-10-26: validation 26 min → 134 s (rules 121 s), doubles stored exactly, 16 negative controls, stored-file sum check. 2026-10-27: CQ4 coverages and cell weights (order 60), recharge-proxy influences (order 61), path selection last (order 90); 32 negative controls. Left: `ProbablyIrrigatedParcel` with 12.10; `ConfinedSetting` with CQ14 |
| 12.7 | CQ tests: one SPARQL query plus an oracle per CQ (`tests/cq/`) | 🔄 2026-10-26: 7 of the 9 MUST CQs done: CQ1, 2, 3, 7, 8, 11, 12 (`tests/cq/*.rq` with a status query each, `tests/test_cq.py`: fixtures incl. conflicting/unknown/missing cases and the 100 m³ facility never counted twice; data against the source tables; main policy 2012–24 = 61.8 % exact / 72.3 % with groups, as `docs/pump_coverage.md`; CQ8's 1,848 influences = CQ2's candidates; ≈ 3 min). Left: CQ10 (needs model outputs), CQ15 (needs 12.10), fixture contracts of the 7 SHOULD/COULD. CQ4 (SHOULD, needed by 12.8) done 2026-10-27: four queries, fixtures, a GeoPandas oracle, negative answers only after a completed search, clipping reported; the same evening CQ8 got the recharge proxies (`cq08_influences` both mechanisms, `cq08_status` with the recharge search) |
| 12.8 | Export SPARQL → `HeteroData` (arms C, D, E, F use the same export) | ⬜ design decided by Assil on 2026-10-26 (analysis plan §14 item 14): one node per facility; depth threshold by training correlation; D's weather, river and canal edges from the KG, so **CQ4, CQ5, CQ6 come first** (CQ6 may stay a documented gap: no supply-area polygons yet). CQ4 extent: 5 km disc (Assil, 2026-10-26); CQ4 done 2026-10-27 (coverages and weights, then the recharge-proxy influences: D's weather edges, local and unit-wide); CQ5 and CQ6 next. Codex review of 2026-10-26: per-well, per-relation inventory before any arm, per-regime depth threshold, export bound to the graph release (analysis plan §14 item 15) |
| 12.9 | Alignment experiment: RPG → AGROVOC gold set + OntoAligner (P/R/F1) | 🔄 2026-10-26: AGROVOC Core snapshot of 2026-10-26 (`src/ingest/agrovoc.py`, 74.4 MB, 42,082 concepts); candidates for the 198 codes (`src/kg/agrovoc_candidates.py` → `configs/lu_agrovoc_candidates.csv`: homonyms through AGROVOC's qualifiers and a crop/land tie-break; 64 exact, 131 overlap, 3 none); gold template and tools (`src/kg/agrovoc_gold.py`). Next: Assil's gold set, then OntoAligner on Colab, then the alignments into the graph (CQ7 turns supported) |
| 12.10 | Satellite rule: Sentinel-2 summer NDVI per parcel on Earth Engine (needs Assil's Earth Engine login) | ⬜ |
| 12.11 | Text extraction, small and measured (thesis) | ⬜ |
| LU-1 | Annual RPG 2015–2025 clipped to the département extent (`src.ingest.rpg --clip dept --drop-raw`; first clipped to the plain, which missed the 15 mountain wells, so redone on 2026-10-25 with Assil's approval); registration-coverage check | ✅ 2026-10-25: 11 editions (74–83 k parcels each), crop groups stable over 245 codes; `src/analysis/rpg_coverage.py`: orchards +876 ha 2015–25, only +86 by conversion; vines −2,134 ha by conversion (1,339 in 2024–25). About 10 GB transferred, more than announced: `--plan` now prints sizes first |
| LU-2 | Crop table: RPG code → group → AGROVOC candidate → FAO-56 Kc calendar → irrigable class (feeds 12.9's gold set) | 🔄 2026-10-25: `configs/lu_crop_classes.csv` (14 classes, FAO-56 Kc and stages, 0 unmapped parcels); irrigation assumptions to check against the Agreste 2020 census; AGROVOC candidates done 2026-10-26 (12.9) |
| LU-3 | Weekly potential-demand index per well and unit (clipped area); pumping reconstruction (3) | ✅ per well 2026-10-25: `src/dataset/crop_demand.py` (main = usually irrigated classes, wide sensitivity, placebo), `src/dataset/pumping_cropcal.py` (within-year r with the deficit 0.96 → 0.61), size check 0.4–0.6 of declared irrigation; tests pass. Per unit: with 12.6 |
| LU-4 | Pre-registered land-use ablation on Kaggle CPU (§14 item 13) | ✅ 2026-10-26: Kaggle kernel 6 (10 runs), main contrast on vs none (Assil, before the pull); **no detectable improvement** for either model (drought median ΔNSE +0.016 / +0.001, p_holm 1.0; LSTM interval up to +0.16; not an equivalence claim), placebo, wide and frozen none either; LSTM machine effect −0.032; hashes and the LightGBM reproducibility checked before scoring; `results/v4/land_use_test.csv`, step 12d note |
| LU-5 | = 12.10, validated against Agreste irrigated areas, else a heuristic | ⬜ |
| LU-6 | End-to-end example (alluvium + Pliocene well): RPG parcels → KG path → Gate 3 | 🔄 2026-10-26: first version `docs/lu6_example.md` (generated by `src/analysis/lu6_example.py` from the CQ queries): MILLAS C2-1 and PONTEILLA NYLS-1, crops 2015–25, demand, pumping paths and policy acceptance, 2024 accounting, LU-4; missing: CQ15, CQ6, CQ10 |
| Gate 3 | Ontology review with the supervisor | ⬜ |

Then Phase 4: the main-model decision, the twin, the arms (`docs/roadmap.md`).

---

## 7b. Completed steps (details kept for re-runs)

### ✅ Steps 10–11 and 12a (summary)
- **Step 10** (`docs/notes/step10_baselines_v2.md`):
  - dataset v2 (from 2005, all dept-66 stations)
  - LSTM tuning, the ensemble, the ablation
  - v1 results are in `results/v1/`
- **Step 11:** the Gate 2 summary (`docs/summary_gate2_results.md`).
- **Step 12a** (`docs/notes/step12a_fixes.md`):
  - the drought/recovery evaluation (`docs/analysis_plan.md`)
  - dataset v3
  - LightGBM without its own climatology (the LightGBM baseline of record)
  - Pastas WellModel
  - the equal-budget tuner with re-selection
  - the regimes
  - the knowledge-graph pre-check (`docs/kg_precheck.md`)
  - the interim v3 report (`docs/results_baselines.md`)
  - Kaggle runner (unused) and Colab runner (in use)
- **Key findings so far:**
  - no head-ordering rule (the vertical gradient flips)
  - seasonal drinking-water pumping beats flat
  - canal recharge helps the alluvium only
  - plain-wide pumping does not help, so the graph must be selective by unit
  - on v3, the ML baselines improve on Pastas in the drought by a large
    effect (median ΔNSE +0.4 to +1.0, most cluster-bootstrap intervals
    exclude 0), but **not significantly with the cluster-level test** (p_holm
    0.07–0.33; the per-well Wilcoxon gives ≤ 0.03). One exception: the tuned
    Taccari ST-GNN on drought skill (p_holm 0.013), not repeated on v4 (0.359).
    The
    remaining error is mostly a level offset in 2024–25. These results are
    exploratory: the test period informed the diagnosis
  - the last two v3 baselines (2026-10-23) beat neither the tuned LSTM nor
    the tuned distance graph: EA-LSTM drought skill 0.34, Taccari tuned 0.55
    (LSTM tuned 0.56). On left-out wells the graph models lose the least
    (drought NSE −0.40/−0.42 against LightGBM −0.75 and LSTM −1.56); the v3
    folds split twin wells, and on the v4 folds it does not hold (distance
    ST-GNN −0.98, LightGBM −0.58)
  - same unit within 5 km and a small depth difference carry co-variation
    beyond distance

### ✅ Step 6b: BD LISA V3 aquifer entities

**Done so far**
- Assil downloaded `data/raw/bdlisa/BDLISA_V3_OCC-gpkg.zip` (GeoPackage,
  169 MB).
- `src/ingest/bdlisa.py` unzips it to
  `data/raw/bdlisa/BDLISA_V3_OCC-gpkg/BDLISA_V3.gpkg` and lists the layers.

**Confirmed by the official description** (`Descriptif_donnees_BDLISA_V3.pdf`):
- `milieueh`: 1 porous, 2 fissured, 3 karstic, 4–10 mixed porosity,
  11 fractured (SANDRE nomenclature 353).
- `themeeh`: 1 alluvial, 2 sedimentary, 3 basement, 4 intensely folded,
  5 volcanic.
- `natureeh` (level 3): 5 aquifer unit, 6 semi-permeable unit, 7 impermeable
  unit. It describes the BD LISA entity, **not** its hydraulic type in the
  ontology: `671AA00`, the main aquifer, is labelled semi-permeable (§3).
- Order 1 = outcropping (the layer at the surface).
- `TABLE_GENEALOGIE` is a version changelog, not a hierarchy. Use `incluseh`
  for the hierarchy.

**Layers**

| Layer | Fields | Rows |
|---|---|---|
| `ENTITES_NIVEAU3_ORDRES` | `CodeEH`, `ordreabseh`, `ordrereleh`, `incluseh`, `milieueh`, … | 1,475 |
| `ENTITES_NIVEAU3_EXTENSION` | n/a | 568 |
| `POLYG_ELEMENTAIRES` | `codepoly` | 16,789 |
| `TABLE_PILE_ENTITES_NIV3` | `CodePoly`, `CodeEH`, `OrdRelatif` | 124,734 |
| `TME` | `codeeh`, `libelleeh`, `ordreabseh`, `niveaueh`, `incluseh`, `natureeh`, `themeeh`, `milieueh`, … | 842 |
| `TABLE_LITHOLOGIE_NIV3` | `CodeEH`, `CdLitho`, `LbLitho`, `LithoPrinc` | 900 |

Outputs used by the KG: `data/interim/bdlisa_entities_plain.csv`,
`bdlisa_overlies_plain.csv`, `bdlisa_station_stacks.csv`,
`bdlisa_vertical_pairs.csv`.

### ✅ Step 7: Gate 1 memo

`docs/memo_gate1_feasibility.md`. Its questions are now in
`docs/supervisor_questions.md`. Context for the framing question: irrigation
in the plain is about 84 % surface water (the historic Têt/Agly canals),
while drinking water is 99 % groundwater. This contradicts the subject's
"crops pump groundwater" chain.

### ✅ Step 8: Phase 1, forcings and the weekly dataset

1. **SAFRAN / SIM2** (Météo-France, data.gouv.fr, "Données changement
   climatique – SIM quotidienne"): rain, ETP, effective rain, soil-moisture
   index on the 8 km grid, cells covering dept 66.
2. **Hub'Eau hydrometrie:** daily discharge for the Têt, Agly, Réart and
   Tech.
3. **Weekly pumping:** BNPE annual volumes × usage profiles (assumption
   documented, plus a sensitivity flag).
4. **Piezometer series** extended to the latest date (incremental cache).
5. **Weekly resampling, gap masks, quality flags, SGI, splits** →
   `data/processed/dataset_v1/` (then v2, v3).

### Rebuild results (compare with section 8)

- **Piezometers.**
  - 101 stations; 43 with ≥ 8 y record and active in 2024+; **33 in the
    working set**.
  - By layer: 20 `671AA00` Pliocene (median record 35.6 y); 6 alluvium
    (`718BP01-03`, `671AB01-02`); **6** Corbières karst `681AM00`; 1
    `760AE09`.
  - 115,443 measurements over 2016–2025.
  - Plain = bbox lon 2.55–3.06, lat 42.50–42.88 (`PLAIN_BBOX` in
    `src/analysis/piezo_profile.py`, documented in `data/README.md`).
  - 19% of window values are "Non qualifié", rising to 52% in 2025.
- **RPG within 3 km** (parcel centroid rule).
  - 2023: 10,222 parcels, 14,021 ha, median 0.74 ha; vines 32% (4,511 ha),
    orchards 19%, olives 2.3%.
  - 2016: 7,914 parcels, 11,697 ha.
  - Vines are stable in hectares. The share drop is a denominator effect:
    ~2,300 ha of newly *declared* land (pasture/landes, grassland,
    orchards). Always compare hectares, not just shares.
- **BNPE, plain 2012–2023 (Mm³).**
  - Irrigation: 741 surface / 144 groundwater → 84% surface (93% if
    canal intakes count).
  - Drinking water: 3 / 475 → 99% groundwater.
  - Canal intakes ("CANAUX"): 1,245 Mm³, reported separately.
  - 2018 reporting break: boreholes declaring groundwater irrigation jump
    from 370 to 950.
  - 2023 under-reported; canal intakes falling since 2017.
- **BD LISA (Step 6b).**
  - 32/33 station entities found (`760AE09` missing).
  - 9 overlies pairs between station entities (= first run); 26 in the
    whole plain.
  - **17 vertical well pairs** ≤ 5 km (first run 13; the stack is now
    followed transitively).
  - **Head ordering: shallow above deep in only 50.5% of 17,124
    pair-weeks.** Nested C2-1/C2-2 (Têt) is downward 100%; nested BARQUA/F
    (Agly) is upward 94.5%, with seasonal flips under summer pumping.
  - 4 Pliocene wells are sometimes artesian.
  - ⇒ **no head-ordering rule**. `overlies` edges carry no sign.
- **Phase 1 dataset v1** (`data/processed/dataset_v1`, loader `src.dataset.load.load_arrays()`).
  - 47 wells (33 core), 1,135 weeks (2005–2026, model window from 2012).
  - Observed well-weeks: train 14,013 / validation 4,960 / test 9,195.
  - The test period is 43.5% IPS "très bas" and 35% not validated.
  - 141 SAFRAN cells.
  - 45 river gauges. **No usable canal flow series** (only 9 weeks of
    one canal), so the canal signal = BNPE canal-intake volumes.
  - 2,046 abstraction ouvrages, spread weekly; 2024+ imputed (v1; v3 uses
    the real 2024).
  - Pastas 2.0.0 installed and pinned.

### ✅ Step 9: Phase 2, baselines on v1

- Seasonal-naive and persistence floors; **Pastas** per well (rain, ETP and
  the weekly pumping near the well; warm-up from 2005; response-function gains
  saved as the "physics reference" for the counterfactual tests); LSTM per
  well and global EA-LSTM; **Chronos-2** zero-shot with covariates;
  distance-graph ST-GNN.
- Metrics: NSE, KGE, RMSE per well and per aquifer group; with and without
  "Non qualifié" weeks; 5 seeds for the neural models.
- **v1 references (2026-10-13), median over 33 core wells:**
  - simulation: distance-graph ST-GNN, test NSE 0.26 / RMSE 0.58 m (LSTM 0.25,
    Pastas 0.13)
  - forecast 4 wk: Chronos-2 zero-shot, 0.83; 12 wk: 0.42
- torch 2.14.1 CPU installed (`--extra-index-url
  https://download.pytorch.org/whl/cpu`).
- Findings:
  - flat drinking-water pumping makes Pastas fake the summer drop with
    evaporation
  - a canal-recharge input helps the alluvium only
  - plain-wide pumping does not help

### Specs of finished steps (kept for re-runs; the scripts implement them)

- **Hub'Eau piezometers** (`niveaux_nappes`):
  - `/stations?code_departement=66`, then `/chroniques` per `code_bss`
  - HTTP 206 means more pages: follow the `next` URL, never increment pages
    yourself
  - cache one parquet per station in `data/raw/hubeau/chroniques/`
  - working set: ≥ 8 y of record, reporting in 2024+, ≥ 50 measurements per
    year, inside `PLAIN_BBOX`
- **RPG:**
  - `https://data.geopf.fr/telechargement/resource/RPG` returns Atom XML;
    regex the names `RPG_..._R76_YYYY-01-01`, then
    `/download/RPG/{name}/{name}.7z`
  - archives may extract flat, so glob recursively
  - compare years at `CODE_GROUP` level and in hectares
- **BNPE** (`prelevements`): classify by `code_type_milieu`
  (CONT = surface, SOUT = groundwater). **Never use `code_bdlisa`**: it is
  always null.

---

## 8. Reference numbers from the first run (August 2026)

Use these to sanity-check the rebuild, not as targets.

**Hub'Eau piezometers:**
- 98 stations in dept 66; 45 with ≥8 years of record and active in 2024+.
- **34 in the working set.** The layers are unbalanced:
  - about 26 deep, in the Pliocene multilayer (BD LISA `671AA00` dominates with
    20 stations; median record 35 years)
  - about 7 shallow, in the Quaternary alluvium
  - 2 in the Corbières karst
- About 309k measurements over 2016–2025. **Correction (rebuild):** this
  was mislabelled. 33 daily stations give at most ~120k values in 10 years.
  The working set's *full* history is 303k; the 2016–2025 window is 115k.

**RPG parcels:**
- About 11,000 parcels and 15,800 ha within 3 km; median parcel 0.75 ha.
- Vines ~33% of area, orchards ~18%, olives ~2%.
- Land use stable 2016 → 2023 at group level.

**BNPE abstraction** (plain, cumulative, Mm³):

| Usage | From surface water | From groundwater |
|---|---|---|
| Irrigation | 811 | 144 |
| Drinking water | 20 | 483 |

**BD LISA:**
- 8 of 9 station entities found; `760AE09` is missing from the Occitanie
  extract.
- Vertical order, shallow to deep:
  1. recent alluvium Têt/Agly/Réart (`718BP01-03`)
  2. ancient alluvium (`671AB01-02`)
  3. Pliocene sands-clays multilayer (`671AA00`, 906 km²)
  4. Corbières limestone (`681AM00`)
  5. Côte Vermeille gneiss (`699AA01`)
- 9 distinct superposed entity pairs across 33 polygons.
- **13 vertical well pairs within 5 km.** The first run concluded that this
  makes a monotonic-drainage constraint viable. The rebuild checked the head
  ordering on these pairs and rejected it (§3).

---

## 9. Roadmap

Follow **`docs/roadmap.md`** (revised 2026-10-23). Weeks count from
2026-10-13; slide everything if the defence date differs from early June 2027.

| Phase | When | Content |
|---|---|---|
| 0–1 | ✅ done | Data foundation, dataset v1 → v3. **Gate 1** (answered 2026-10-23) |
| 2 | ✅ finishing | Baselines; EA-LSTM and Taccari running. **Gate 2** (answered 2026-10-23) |
| 3 | 26 Oct – 6 Dec | CQs, reuse, `lulcw:`, CQ2 data step, KG, SHACL(-AF), CQ tests, HeteroData; alignment experiment; satellite rule. **Gate 3** |
| 4 | 7 Dec – 31 Jan | Main model (hybrid) + black-box comparison, arms A–F, soft/hard constraints, semi-synthetic twin, shortcut tests. **Gate 4** (results frozen) |
| 5 | Feb | Explanations, faithfulness, case studies; dashboard prototype (CQ queries + map + scenario) |
| 6 | Mar – 25 Apr | Paper, submitted by the end of April 2027 |
| 7 | 26 Apr – June | Thesis (incl. alignment and text extraction chapters), transfer demo, defence |

---

## 10. Literature anchors

Verdicts on every PDF in `Articles/` and verified additions:
`docs/literature/reading_list.md`. Papers to keep in mind when writing
code or docs:
- Wu et al., *JGR: Machine Learning and Computation* 2025
  (doi:10.1029/2024JH000520) — T-GCN with several spatial-dependency
  graphs for groundwater levels, North China Plain.
- Wu et al., *WRR* 61(11) 2025 (doi:10.1029/2025WR041215) — graph Fourier
  deep learning with hydrogeological units as prior information, Yellow
  River Basin. **The closest competitor.** *(Two different Wu 2025 papers;
  both exist.)*
- Taccari et al., *Scientific Reports* 2024 (doi:10.1038/s41598-024-75385-2)
  — ST-GNN for a multi-aquifer system with pumping, river and rain nodes.
  The closest setting to ours.
- Heudorfer et al., *HESS* 2024 (doi:10.5194/hess-28-525-2024) — global
  groundwater models use static features as IDs, not semantics. Motivates
  our semantic-ablation test.
- Kirschstein & Sun, ICML 2024 (arXiv:2405.19836) — river topology gave a GNN
  no gain for discharge: "a domain graph helps" is not a safe prior.
- Collenteur et al., *Groundwater* 2019 (doi:10.1111/gwat.12925) — Pastas,
  the mandatory hydrological baseline.
- Marconato et al., NeurIPS 2023 (arXiv:2305.19951) — reasoning shortcuts.
- Ross et al., IJCAI 2017 (arXiv:1703.03717) — "Right for the right
  reasons": gradient penalties; the source of our title and soft constraints.
- OntoAligner, ESWC 2025 (arXiv:2503.21902) — ontology alignment toolkit.
- WHOW-KG, *Scientific Data* 2025 (doi:10.1038/s41597-025-04537-4) —
  network-of-ontologies pattern for water. (The PDF in `Articles/` is the
  2023 preprint.)
- Brodaric et al., *Hydrogeology Journal* 2018
  (doi:10.1007/s10040-018-1747-9) — GWML2, the groundwater data standard.
- Tripathi & Babaie, *Computers & Geosciences* 2008
  (doi:10.1016/j.cageo.2007.08.009) — a hydrogeology ontology built on SWEET.
- Grüninger & Fox 1995 (doi:10.1007/978-0-387-34847-6_3) — competency
  questions; Wiśniewski et al., *J. Web Semantics* 2019
  (doi:10.1016/j.websem.2019.100534) — CQs written as SPARQL.
- Clark et al., *WRR* 2025 (doi:10.1029/2025WR041303) — XAI for
  spatio-temporal groundwater predictions.
- Dai et al., *JGR: Machine Learning and Computation* 2025
  (doi:10.1029/2025JH000703) — deep learning in hydrogeology. Names the three
  gaps this project addresses.
