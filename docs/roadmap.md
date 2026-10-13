# Roadmap: from data foundation to thesis and paper

Written 2026-10-13. It replaces the step list in CLAUDE.md §9.
Literature verdicts are in [`literature/reading_list.md`](literature/reading_list.md).

**Timing assumption: defence in early June 2027.** That leaves about
34 weeks from today, and the week numbers below count from 2026-10-13. If
the real date is different, slide every phase by the same amount.

---

## 1. The paper this project produces

**Working title.** *Right for the right reasons? Ontology-derived graphs
and constraints for groundwater-level forecasting in a Mediterranean
multilayer aquifer.*

**One-sentence claim.** A forecaster whose graph and constraints come from
a LULC-Water knowledge graph forecasts groundwater levels in the Roussillon
plain at least as well as strong hydrological and deep-learning baselines.
It does better in the cases that matter: drought, little training data,
wells it has never seen. We also show, with explicit reasoning-shortcut
tests, whether it uses the knowledge or only satisfies it.

**Research questions**

| RQ | Question | Experiment that answers it |
|---|---|---|
| RQ1 | Does a graph built from the knowledge graph beat a distance-only graph and non-graph baselines? | Model comparison on 3 test regimes: drought period, held-out wells, reduced data |
| RQ2 | Do ontology-derived constraints improve physical plausibility and skill out of distribution? | Soft vs hard vs no constraints; violation rate; counterfactual sign tests |
| RQ3 | Does the model use the semantics, or does it take shortcuts? | Semantic ablation (rewired / shuffled ontology), concept accuracy on drought states (SGI) |
| RQ4 | Can explanations be stated in ontology terms *and* be faithful? | Attribution → ontology templates; fidelity metrics; check against documented events |

**Why this is publishable.** Searches in October 2026 found GNNs for
groundwater: Bai & Tahmasebi 2023, Taccari 2024, Wu 2025. They found
neither an ontology or knowledge graph driving one nor a reasoning-shortcut
analysis in hydrology. Dai et al. 2025 list interpretability and physical
consistency as open gaps. The combination is new. Each component alone is
not, so the paper must be honest and rigorous about baselines.

**What makes it credible to hydrologists.** Two things: Pastas as a
baseline, and a test period that is the record 2022–2024 drought followed
by the 2025–2026 recovery. BRGM reported historic minima in the Roussillon
in 2024. It also reported that the deep Pliocene recovered partly because
abstraction fell. That recovery is a real-world event the explanations
must be able to recover.

---

## 2. What changes compared with the original plan

The subject document (`Documents/sujet.docx`) describes a PhD-sized
programme. A Master's paper needs **one sharp, testable contribution**.

| Topic | Original plan | Recommendation | Why |
|---|---|---|---|
| Physical constraint | "Water infiltrates downward" (head ordering shallow ≥ deep) | **Check it on data first.** Default to *response-sign* constraints from ontology causal links: abstraction lowers head, effective rain raises head, canal irrigation raises alluvium head. Add concept-level rules on drought states. | The Pliocene is heavily pumped. The vertical gradient can reverse with season and place, so a wrong hard rule makes the model worse. Sign constraints hold everywhere and can be tested by counterfactuals. |
| Reasoning-shortcut test | Marconato et al. as is | Adapt it to regression. (a) Concepts = SGI drought states per well and week; measure concept accuracy. (b) **Semantic ablation**: rewire the ontology edges or shuffle attributes. If skill does not drop, the model ignores the semantics (cf. Heudorfer 2024). | Marconato's framework assumes discrete concepts. Ours are continuous levels. |
| Baselines | "Distance graph + baseline GNN" | Add **seasonal naive, Pastas, LSTM / EA-LSTM, Chronos-2 zero-shot, Taccari-style ST-GNN** | Reviewers in hydrology reject deep-learning papers without Pastas. Reviewers in ML reject them without a foundation-model baseline. |
| Time step and window | Daily, 2016–2025 | **Weekly**, extended to **2026**. Push the start back to about 2010 if forcing and abstraction data allow. Test set = **May 2022 → 2026**. | Weekly cuts noise and gaps (as in Taccari). The drought and recovery give a natural out-of-distribution test. |
| Graph construction | Hand-built | **Generated from the knowledge graph** by SPARQL → PyG `HeteroData` | This makes the ontology operational, not decorative. It is the neuro-symbolic link reviewers look for. |
| Land use | AlphaEarth embeddings as a phase | RPG is the primary land-use source in France (exact crops). AlphaEarth is a **feature source** only, with TESSERA as the open backup. WorldCereal irrigation goes in if useful. | The RPG already gives crop types. Earth observation matters for irrigation and for the Tunisia transfer. |
| Ontology alignment | A research experiment | A **supporting** contribution: a small manual gold set (~50 mappings), with OntoAligner (fuzzy, retrieval, LLM) evaluated against it | It is easy to lose 2 months here. The paper needs alignments that are correct and reported, not a new matcher. |
| Derivation rules | SWRL (subject) → SHACL (CLAUDE.md) | SHACL for validation plus **SHACL-AF rules** for derivations (pySHACL supports both) | Keeps one technology. It can express the subject's example (NDVI high in summer AND soil moisture low → irrigation likely). |
| Explanations | GNNExplainer → templates | Integrated Gradients and GNNExplainer at **node-type level**, then ontology templates, then **faithfulness metrics** (fidelity+/−) | Unmeasured explanations are not publishable (Azzolin 2024). |
| Nitrate, dashboard, socio-economics, Spain, Tunisia | In scope | **Future work.** One optional small transfer demo for Tunisia at the end. | Scope. |

**Status (2026-10-13):** Assil adopted all of these, and they are now the
design decisions in CLAUDE.md §3. The Step 7 memo presents them to the
supervisor together with the open questions (framing, karst stations,
venue).

---

## 3. The method in one picture

```
 Hub'Eau piezo ─┐                          ┌─ SHACL shapes + SHACL-AF rules
 BNPE abstraction│   ingest    ┌─────────┐  │
 RPG / AlphaEarth├──────────►  │ LULC-   │◄─┤  GWML2 · HY_Features · SOSA/SSN ·
 BD LISA         │   + RDF     │ Water KG│  │  GeoSPARQL · HILUCS · AGROVOC
 SAFRAN (rain,ET)│             └────┬────┘  └─ alignments (OntoAligner + manual)
 Hub'Eau rivers ─┘                  │ SPARQL export
                                    ▼
             Heterogeneous graph: Well · AquiferUnit · AbstractionPoint ·
             RiverReach · LandUseZone   edges: monitors, overlies, pumpsFrom,
             near, drains, irrigates
                                    │
                                    ▼
      ST-GNN (HGT/RGCN + temporal conv/GRU) ──► weekly head forecast per well
           + soft constraints (counterfactual sign penalties)       │
           + hard constraints (PiShield linear inequalities)        ├─► SGI drought state
                                    │                               │
                                    ▼                               ▼
            Attributions (IG / GNNExplainer) → ontology templates → text
            Validity: semantic ablation · concept accuracy · faithfulness
```

---

## 4. Phases

Each phase lists its goal, its tasks, the tools, and a **done-when** test.
A **gate** is a meeting or e-mail with the supervisor. Don't start the next
phase until the gate has been passed.

### Phase 0: Finish the data foundation (weeks 1–2, 13–26 Oct)

Goal: close the rebuild (CLAUDE.md §7), from cold on the new Linux machine.

1. **Environment on Linux.** `uv venv --python 3.12 .venv`, then
   `uv pip install -r requirements.txt`. The Windows pins can stay. Rerun
   steps 4–6a from cold: the scripts must skip downloads that are already
   cached. Update the header of `requirements.txt`.
2. **Step 6b BD LISA:** as specified in CLAUDE.md §7. **Add one check:**
   for the vertical well pairs, compute how often the head in the shallow
   well is above the head in the deep one (by season). That one number
   decides the constraint design.
3. **Step 7 memo.** Add a "paper plan" section with the RQs above, the
   decisions table from §2, and the venue choice.
4. Add `Articles/` to `.gitignore`. Publisher PDFs must not go to GitHub.

Done when: 6b note committed; memo sent. **Gate 1** answers: framing
(use conflict vs canal recharge), karst stations, design changes, venue,
real defence date.

### Phase 1: Forcings and the model-ready dataset (weeks 3–5, 27 Oct–16 Nov)

Goal: one frozen, versioned dataset that every model reads.

| Task | Source and tool |
|---|---|
| Rain, ETP, effective rain, soil-moisture index per well (nearest 8 km cell) | Météo-France **SIM2 / SAFRAN** daily on data.gouv.fr ("Données changement climatique – SIM quotidienne"). Log the URL in `data/README.md`. |
| River discharge Têt, Agly, Réart, Tech | Hub'Eau **hydrometrie** API (same pattern as the piezometer ingest) |
| Weekly pumping per aquifer unit | BNPE annual volumes spread by **usage-specific monthly profiles**: drinking water peaks in summer (tourism), irrigation runs Apr–Sep. Document the assumption and keep a sensitivity flag. |
| Piezometer series extended to Oct 2026 | Re-run the ingest; the cache makes it incremental |
| Weekly resampling, gap mask, quality flags | pandas; keep "Non qualifié" as a flag, not dropped |
| SGI per well | Bloomfield & Marchant 2013 (normal-score transform per calendar month) |
| Splits | Train ≤ 2019 · validation 2020–21 · **test May 2022 → 2026**. Plus 5-fold **leave-wells-out** for unseen wells. |

Deliverable: `data/processed/dataset_v1/` (parquet) + `docs/notes/step08_dataset.md`.
Done when: a single loader returns X, y, mask and splits, and a plot shows
each series with its forcings.

### Phase 2: Baselines (weeks 6–9, 17 Nov–14 Dec)

Goal: know how hard the problem is before any knowledge is added.

| Model | Tool | Notes |
|---|---|---|
| Seasonal naive / persistence | numpy | the floor |
| **Pastas** (rain + ET + pumping response functions), per well | `pastas` | the hydrology reference; its response-function gains also serve later as "physics truth" for the counterfactual tests |
| LSTM per well, EA-LSTM global | PyTorch | Wunsch 2021, Kratzert 2019 |
| **Chronos-2** zero-shot with covariates | `chronos-forecasting` | runs on CPU (120M parameters) |
| ST-GNN on a distance graph (Taccari-style, predefined graph) | PyG + `torch-spatiotemporal` (tsl) | the homogeneous-graph baseline |

Metrics: NSE, KGE, RMSE, with **separate scores for the drought period**,
held-out wells, and 25/50/100% of the training data. Use 5 seeds for the
neural models.

Tooling from here on: config files (YAML/Hydra), MLflow or Weights &
Biases for run tracking, and `scripts/run_sweep.py` resumable per run.
Each run writes its result file; reruns skip finished runs.

Done when: a results table and a figure exist. **Gate 2:** the target is
confirmed as weekly groundwater level, plus the SGI state. If no model
beats Pastas, the paper becomes "where does knowledge help?" and the
low-data and unseen-well regimes become the headline.

### Phase 3: Ontology and knowledge graph (weeks 8–13, 7 Dec–17 Jan; overlaps Phase 2)

Goal: the smallest ontology that answers the questions the model and the
explanations need. **Time-box: 6 weeks.**

1. **Competency questions** (10–15). Examples: *Which aquifer units does
   well W monitor?* *Which units overlie unit U, and is the separating
   layer semi-permeable?* *Which abstraction points pump from U, for which
   usage?* *Which land-use classes with high irrigation demand lie within
   3 km of W?*
2. **Reuse:** GWML2 (wells, aquifer units, `overlies`), SOSA/SSN
   (observations), HY_Features (rivers), GeoSPARQL 1.1 (geometry),
   HILUCS + AGROVOC (land use, crops), WHOW-KG patterns (water use). Write
   only the **bridging module** `lulcw:` with the causal relations and
   their polarity: `lulcw:decreasesHead`, `lulcw:increasesHead`,
   `lulcw:rechargesFrom`.
3. **Alignment:** a manual gold set of about 50 mappings (RPG `CODE_GROUP`
   → AGROVOC/HILUCS, BD LISA → GWML2, BNPE usage → WHOW). Then run
   OntoAligner's fuzzy, retrieval and LLM matchers and report P/R/F1. The
   LLM runs on a local open model on the GPU credits, so they are
   reproducible and need no paid API.
4. **Knowledge graph instantiation** from the parquet files: `rdflib` →
   Turtle, loaded into `pyoxigraph`.
5. **SHACL shapes** (pySHACL) for validation, plus 3–5 **SHACL-AF rules**
   that derive concepts (e.g. `HighIrrigationDemandZone`).
6. **Export:** SPARQL → PyG `HeteroData`. This is the only way the model
   gets its graph.
7. Optional, for the subject's "textual extraction": extract
   Mediterranean concepts from 10–20 papers with OntoGPT/SPIRES or an
   LLMs4OL-style prompt, then validate them by hand.

Tools: Protégé (editing), `rdflib`, `pyoxigraph`, `pyshacl`,
`ontoaligner`, ROBOT (optional, for releases).
Done when: all competency questions are answered by SPARQL queries in
`tests/`, SHACL validation passes, and the HeteroData export loads.
**Gate 3:** ontology review with the supervisor.

### Phase 4: Knowledge-guided model and validity tests (weeks 14–19, 18 Jan–28 Feb)

Goal: answer RQ1–RQ3. This is the core of the paper.

1. **Heterogeneous ST-GNN:** `HGTConv` or `RGCNConv` (PyG) for space,
   with gated temporal convolutions or a GRU for time. Node features:
   forcings, pumping, RPG shares, AlphaEarth embeddings (averaged per
   zone and year, through Earth Engine `earthengine-api`).
2. **Soft constraints:** during training, perturb pumping and rain inputs
   and penalise responses with the wrong sign (counterfactual penalty).
   Add a semantic loss on the predicted SGI states with the concept rules.
3. **Hard constraints:** PiShield linear inequalities, only for the rules
   the data supports (e.g. weekly change bounds, plus the head ordering if
   the Phase 0 check holds).
4. **Ablation grid:** graph type {none, distance, KG} × constraints
   {none, soft, hard} × data {25, 50, 100%} × 5 seeds, on 3 test regimes.
   That is about 300 short runs, which is where the GPU credits go.
5. **Shortcut tests:**
   - Semantic ablation: rewire the KG edges with degrees preserved, and
     shuffle node-type attributes.
   - SGI concept accuracy versus constraint satisfaction.
   - Counterfactual sign accuracy, with Pastas gains as the reference.
   - Optional: BEARS ensembles for concept confidence.

Done when: the main results table and the ablation figure are frozen.
**Gate 4: no new experiments after this point**, only analysis.

### Phase 5: Ontology-grounded explanations (weeks 20–22, 1–21 Mar)

1. Attributions with Captum Integrated Gradients and the PyG `explain`
   module (GNNExplainer), aggregated by **node type and relation**
   (e.g. "pumping from 671AA00", "rain deficit", "canal irrigation in
   718BP").
2. Faithfulness: fidelity+/− and the deletion curve (Azzolin 2024).
3. Templates: attribution → SPARQL query on the KG for the chain of
   entities → fixed French/English sentence templates. An LLM may rephrase
   only; it never adds facts. Add a test that every entity named in the
   text exists in the KG.
4. **Case studies:** the 2023 drop at a Pliocene well, the 2025 Pliocene
   recovery (does the explanation say "reduced abstraction"?), and one
   alluvium well (does canal irrigation appear?).

Done when: 3 case-study figures with their text, and a faithfulness table.

### Phase 6: Paper (weeks 23–27, 22 Mar–25 Apr)

1. Choose the venue at Gate 1 and confirm it at Gate 4:

   | Venue | Fit | Note |
   |---|---|---|
   | **Environmental Modelling & Software** (Elsevier) | Best overall: methods + software + environment, and ontologies are welcome | first choice |
   | **JGR: Machine Learning and Computation** (AGU, open access) | Where Wu 2025 and Dai 2025 appeared | strong second |
   | HESS (Copernicus, open access, open review) | Hydrology audience; Pastas comparison is a must | ambitious |
   | Earth Science Informatics · Computers & Geosciences | Safer | fallback |
   | Workshop (Climate Change AI at ICLR/NeurIPS; NeSy) | Fast feedback, short paper | optional; check deadlines |

   The PRIMA proposal commits SAVE Water to gold open access. Ask whether
   the project pays the publication fees.
2. Structure: Introduction (gap: Dai 2025, Clark 2025) → Study area and
   data → Knowledge graph → Model and constraints → Experiments (RQ1–4) →
   Discussion (limits, shortcuts found) → Conclusion. Target about 8,000
   words and 8–10 figures.
3. Reproducibility package: code on GitHub, a Zenodo DOI for the code and
   processed data, the knowledge graph in Turtle, and the exact configs.
   (Raw data stays at its public sources; the ingest scripts fetch it.)
4. Supervisor review, then submit **by the end of April 2027**.

Done when: submitted. The submission confirmation is the deliverable.

### Phase 7: Thesis and defence (weeks 28–34, 26 Apr–mid June)

- The thesis reuses the paper plus `docs/notes/` (Data and Methodology
  chapters are already half written there).
- Optional, if ahead of schedule: a Tunisia transfer demo. Reuse the
  ontology and model with AlphaEarth and WorldCereal instead of the RPG,
  and show how the ontology adapts. A qualitative demo only.
- Defence slides. Answer the reviews when they arrive (usually after the
  defence).

---

## 5. Compute plan

| Work | Where | Why |
|---|---|---|
| Ingest, knowledge graph, SHACL, Pastas, single model runs, debugging | **Laptop** (4 cores, 11 GB, CPU) | The graph is tiny (33–101 nodes × ~900 weeks). One run takes minutes. |
| Ablation sweep (~300 runs), Optuna tuning, BEARS ensembles | **GPU credits** (student pack / Kaggle / Colab) | Parallel runs, not big models |
| LLM matcher for OntoAligner, LLMs4OL/SPIRES extraction, explanation polishing | **GPU**, local open 7–8B model (vLLM or Ollama) | Reproducible, free, citable model version |
| AlphaEarth embeddings | **Google Earth Engine** (free for research) | Server side; nothing to download but the zone averages |
| TESSERA (only if needed) | GPU | Open weights |

Rules: every sweep is resumable (one result file per run, skipped if it
exists). Pin the code with `uv.lock` so the laptop and the cloud run the
same thing. Save checkpoints to persistent storage, not to the instance
disk.

---

## 6. Toolbox

| Purpose | Tool |
|---|---|
| Environment | `uv`, Python 3.12 |
| Geodata | `geopandas`, `pyogrio`, `shapely`, `earthengine-api` (+ `xee` optional) |
| Groundwater baseline | `pastas` |
| Deep learning | PyTorch, PyTorch Geometric (`HeteroData`, `HGTConv`, `explain`), `torch-spatiotemporal` (tsl) |
| Foundation-model baseline | `chronos-forecasting` (Chronos-2) |
| Constraints | custom penalties, `pishield` |
| Explanations | `captum`, PyG `explain` |
| Experiments | Hydra/YAML configs, Optuna, MLflow or W&B |
| Semantic web | Protégé, `rdflib`, `pyoxigraph`, `pyshacl`, `ontoaligner`, ROBOT |
| Writing | Zotero + Better BibTeX, LaTeX (journal template), a `figures/` script for every figure |

---

## 7. Risks and fallbacks

| Risk | Sign | Fallback |
|---|---|---|
| The knowledge-graph model doesn't beat Pastas or the distance graph | Gate 2 / Phase 4 | Lead with the regimes where it does help (low data, unseen wells, drought). A clear negative result plus a shortcut analysis is still publishable. |
| Annual pumping is too coarse | Pastas shows weak pumping response | Monthly profiles + sensitivity; say so in the limitations |
| Ontology work balloons | Phase 3 still open at week 13 | Freeze to the competency questions the model needs; the rest is future work |
| 33 wells is too few | High variance across seeds | Train on all 101 stations in dept 66 with a masked loss; evaluate on the 26–33 core wells |
| Head ordering between layers isn't stable | Phase 0 pair check | Drop the hard ordering rule; keep sign and concept constraints |
| Data drift (2025: 52% "Non qualifié") | — | Report results with and without unqualified values |

---

## 8. Weekly routine

- **Monday:** pick this week's tasks from this file.
- **Each step:** commit, then write `docs/notes/stepNN_*.md`
  (what / why / what to consider).
- **Every month:** a short progress report to the supervisor (the guide asks
  for this).
- **Reading:** 2–3 papers a week from `literature/reading_list.md` until
  Phase 4, one comparison-table row each.
