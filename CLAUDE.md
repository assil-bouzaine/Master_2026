# CLAUDE.md — SAVE Water / LULC-Water PFE

Read this file at the start of every session. It is the project brief, the
rules, and the current task.

---

## 1. The project in one paragraph

Master's PFE (projet de fin d'études) by Assil Bouzaine, Master in Data Science
and Information Retrieval, ISAMM (Université de la Manouba). It contributes to
the SAVE Water project (PRIMA 2023). Goal: forecast groundwater levels in a
Mediterranean multilayer aquifer with a spatio-temporal graph neural network
whose **graph and constraints come from a LULC-Water knowledge graph**. Test
whether the model uses that knowledge or takes shortcuts. Explain its
predictions in ontology terms.

Scope is a **Master's, not a PhD**: one aquifer system (Roussillon plain) and
one target variable (weekly groundwater level, plus its derived drought state),
built end to end. Nitrate, socio-economics, the dashboard, Spain and Tunisia
are future work (one optional Tunisia demo at the very end).

### End goal: a peer-reviewed paper as well as the thesis

- **Working title:** *Right for the right reasons? Ontology-derived graphs and
  constraints for groundwater-level forecasting in a Mediterranean multilayer
  aquifer.*
- **Research questions:**

  | RQ | Question | Experiment that answers it |
  |---|---|---|
  | RQ1 | Does a graph built from the knowledge graph beat a distance-only graph and strong non-graph baselines? | Model comparison on 3 regimes: drought test period, held-out wells, reduced training data |
  | RQ2 | Do ontology-derived constraints improve physical plausibility and out-of-distribution skill? | None / soft / hard constraints; violation rate; counterfactual sign tests |
  | RQ3 | Does the model use the semantics or take shortcuts? | Semantic ablation (rewired or shuffled knowledge graph); concept accuracy on SGI drought states |
  | RQ4 | Can explanations be stated in ontology terms *and* be faithful? | Attributions → ontology templates; fidelity metrics; documented events |

- **Venue** (confirm with the supervisor): first choice *Environmental
  Modelling & Software*; second *JGR: Machine Learning and Computation*;
  fallback *Earth Science Informatics* or *Computers & Geosciences*.
- **Authorship:** Assil first author, supervisors as co-authors. Acknowledge
  SAVE Water / PRIMA.
- **Target:** submitted by the end of April 2027, assuming a June 2027 defence.
  Check the real date at Gate 1.
- **Plan:** `docs/roadmap.md` (phases, tools, risks).
- **Literature:** `docs/literature/reading_list.md` (verdicts, verified IDs).

---

## 2. Study sites

| Role | Site | Notes |
|---|---|---|
| Primary | **Plaine du Roussillon**, Pyrénées-Orientales (dept 66), France | Chosen for open data on every layer |
| Secondary | Campo de Cartagena / Segura, Spain | Generalisation; later |
| Demo | Cap Bon or Kairouan, Tunisia | Transfer demonstration only; later. **Likely to change** to a SAVE Water Living Lab (Manouba or Charf El Akab): see `docs/savewater_consortium_notes.md`, on hold until Assil contacts the consortium |

---

## 3. Design decisions

Adopted on 2026-10-13. Assil approved the researcher's recommendations; the
reasons are in `docs/roadmap.md` §2. Do not change them without asking
Assil. Items marked **(supervisor)** go in the Gate 1 memo for confirmation.

**Knowledge side**
- **Ontology architecture:** a network of small ontologies linked by alignment
  axioms (WHOW-KG pattern, *Scientific Data* 2025,
  doi:10.1038/s41597-025-04537-4), not one merged file.
- **Reuse:** GWML2 (wells, aquifer units, `overlies`), SOSA/SSN
  (observations), HY_Features (rivers), GeoSPARQL 1.1 (geometry), HILUCS +
  AGROVOC (land use, crops), WHOW-KG (water use). Write only a **bridging
  module** `lulcw:` holding the causal relations with their polarity
  (`lulcw:decreasesHead`, `lulcw:increasesHead`, `lulcw:rechargesFrom`, …).
- **Scope of the ontology:** driven by 10–15 competency questions that the
  model and the explanations need. Time-box: 6 weeks.
- **Alignment:** a small manual gold set (~50 mappings), then OntoAligner
  (fuzzy, retrieval, LLM matchers) evaluated against it with P/R/F1. A
  supporting contribution, not the main one. LLM matchers run on a local open
  model (GPU credits), never a paid API.
- **Rules and validation:** SHACL for validation and **SHACL-AF rules** for
  derived concepts (pySHACL). No SWRL.
- **The graph the model sees is generated from the knowledge graph** by SPARQL →
  PyG `HeteroData`. Never hand-code edges in model code.

**Data and target**
- **Time step: weekly.** Keep daily data in `interim/`.
- **Window:** extended to the latest available date (2026). Push the start
  back to about 2010 if forcings and abstraction allow; the minimum is
  2016–2026.
- **Splits:**
  - train ≤ 2019, validation 2020–2021
  - **test May 2022 → latest** (record drought, then the recovery)
  - plus 5-fold **leave-wells-out**
  - plus 25/50/100% training-data subsets
- **Target:** groundwater level (m NGF) per well, plus its **SGI** drought
  class (Bloomfield & Marchant 2013, doi:10.5194/hess-17-4769-2013) as the
  discrete concept layer.
- **Training wells:** use all usable dept-66 stations with a masked loss; report
  on the core working set. Karst stations: **(supervisor)**.
- **Land use:** RPG is the primary source in France. Earth observation is a
  **feature source only**: AlphaEarth annual embeddings (Google Earth Engine,
  arXiv:2507.22291), with TESSERA (arXiv:2506.20380) as the open backup.
  WorldCereal irrigation layer if useful. No Sentinel classifier, no Prithvi.

**Model and constraints**
- **Baselines (mandatory):**
  - seasonal naive
  - **Pastas** (doi:10.1111/gwat.12925)
  - LSTM per well
  - EA-LSTM global
  - **Chronos-2** zero-shot (arXiv:2510.15821)
  - a distance-graph ST-GNN, Taccari-style (doi:10.1038/s41598-024-75385-2)
- **Main model:** heterogeneous ST-GNN (HGT/RGCN in space, gated temporal
  convolutions or a GRU in time) on the knowledge-graph-derived graph.
- **Constraints come from ontology causal links, as response signs:**
  - abstraction lowers head
  - effective rain raises head
  - canal irrigation raises alluvium head
- **Applying the constraints:**
  - *soft:* counterfactual penalties in the loss, plus a semantic loss on
    SGI states
  - *hard:* PiShield linear inequalities (doi:10.24963/ijcai.2024/1037),
    only for rules the data supports
- **No head-ordering rule ("water flows down") unless the Step 6b pair check
  shows the shallow head is consistently above the deep head.**

**Validity and explanations**
- **Reasoning shortcuts** (Marconato et al., arXiv:2305.19951) are tested in
  three ways:
  - **semantic ablation**: rewire the knowledge-graph edges with degrees
    preserved, and shuffle attributes. If skill does not drop, the model
    ignores the semantics (cf. Heudorfer et al. 2024,
    doi:10.5194/hess-28-525-2024).
  - SGI concept accuracy versus constraint satisfaction
  - counterfactual sign accuracy, with Pastas response gains as the reference
- **Explanations:**
  1. Integrated Gradients and GNNExplainer, aggregated by node type and
     relation
  2. SPARQL on the knowledge graph for the chain of entities
  3. **templated text**
  4. faithfulness metrics (fidelity+/−; Azzolin et al., arXiv:2406.15156)

  An LLM may polish fluency only and never invents content. A test checks
  that every entity named in the text exists in the knowledge graph.

**Research framing (supervisor):** use conflict on the Pliocene (drinking
water vs agriculture) or canal-return recharge. Both are expressible as
ontology causal links, so the pipeline does not wait for this answer.

---

## 4. Environment

**Current machine (since October 2026): Arch Linux**
- 4 cores, 11 GB RAM, no NVIDIA GPU; shell zsh
- Venv: `.venv`, Python 3.12, created with
  `uv venv --python 3.12 .venv`. Install with
  `uv pip install --python .venv/bin/python -r requirements.txt`.
- Run scripts as `.venv/bin/python -m src.<pkg>.<module>`. Set
  `PYTHONIOENCODING=utf-8`.
- Cold-start check passed on 2026-10-13: Steps 4–6a re-ran from the cache
  with identical numbers.
- Use `pathlib` for every path. Pin dependencies in `requirements.txt`.
- Use `py7zr` for `.7z` and `pyogrio` for geodata
  (`pyogrio.list_layers()` to inspect a GeoPackage or FileGDB).

**Compute plan** (`docs/roadmap.md` §5)
- The laptop CPU is enough for the data work, the knowledge graph, Pastas and
  single model runs. The graph is tiny: about 33–101 nodes × about 900
  weeks.
- The GPU credits (GitHub Student Pack, Kaggle, Colab) go to:
  - the ablation sweep (~300 runs)
  - Optuna tuning
  - BEARS ensembles
  - local open LLMs (vLLM/Ollama) for alignment and text extraction
- AlphaEarth runs server-side on Google Earth Engine.
- Every sweep is resumable: one result file per run, skipped if it exists.
  Checkpoints go to persistent storage.

**API lessons (still valid)**
- **Hub'Eau prélèvements:** `size=5000` got the connection reset, and then
  hubeau.eaufrance.fr refused the machine for about 10 minutes. Use
  `size=2000`. `niveaux_nappes` accepts 5000.
- **IGN Géoplateforme:** the `/resource/RPG` listing is paginated (35 pages)
  and returns 429 if requests come too fast; pause 1 s per page. Crop
  code → group tables:
  `https://data.geopf.fr/annexes/ressources/documentation/`.
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
src/analysis/    profiling, joins, figures
src/dataset/     model-ready dataset builder (weekly tensors, masks, splits)
src/kg/          ontology modules, KG instantiation, SHACL, SPARQL → HeteroData
src/models/      baselines and the knowledge-guided ST-GNN
src/explain/     attributions, faithfulness, templates
configs/         one YAML per experiment
ontology/        lulcw bridging module (.ttl), alignments, SHACL shapes
tests/           competency-question queries, unit tests
data/raw/        untouched downloads             (gitignored)
data/interim/    cleaned / filtered tables       (gitignored)
data/processed/  model-ready datasets            (gitignored)
data/README.md   data log — committed
results/         run outputs, one folder per run (gitignored)
docs/            roadmap, memos, notes
docs/literature/ reading list, comparison table
paper/           LaTeX manuscript (from Phase 6)
reports/figures/ maps and plots, each made by a script
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
    - metrics include NSE, KGE and RMSE, with separate scores for the drought
      period
    - every figure is produced by a script, never by hand
11. **Honest baselines.** Tune baselines with the same budget as our model.
    If a baseline wins, report it.

---

## 7. CURRENT TASK: Step 11 (Gate 2) and Step 12 (Phase 3 ontology)

Assil chose option **B** on 2026-10-13: make the baselines as strong as
possible before Gate 2 and the ontology phase. Work through the steps
below in order and track them with a task list. **GPU work runs on Assil's
Camber node through the Claude-in-Chrome extension** (see §4 and
`docs/gpu_howto.md`).

### ▶ Where we are (read this first in a new session)

- **2026-10-20, Step 12a (fixes from the critical review `docs/feedback.md`):**
  - **Evaluation changed** (`docs/analysis_plan.md`, the reference for every new
    result): test split into **drought** (May 2022 → Nov 2025) and **recovery** (Dec
    2025 →); primary endpoint = drought-phase median NSE + skill vs climatology;
    KGE'' (datum-free); clustered bootstrap + Holm. With clustered tests no v2 ML
    baseline is significantly better than Pastas in the drought.
  - **Dataset v3** is the new default for runs (`PFE_DATASET=v3`): real BNPE 2024
    (dated snapshot), documented imputation rules (`src/dataset/bnpe_v3.py`), VigiEau
    surface-water orders (analysis only), river inputs, artesian-share leak fixed.
  - **New baselines code:** LightGBM `--tune`, EA-LSTM, `tune.py` (equal budget),
    `regimes.py` (leave-wells-out, 25/50 %, refit), `taccari.py` (Taccari graph),
    Pastas WellModel, Chronos-2 cross-learning / fine-tuning.
  - **Knowledge-graph pre-check done** (`docs/kg_precheck.md`): same BD LISA entity +
    within 5 km and similar screen depth explain co-variation beyond distance (QAP
    p = 0.048 and 0.002); the 3-NN distance graph crosses entities in 53 % of edges.
  - **Stopped 2026-10-20 ~10:35 (PC shut down).** Laptop: naive, LightGBM default and
    tuned on v3 done; Pastas variants were running (resume per well). Smoke tests of all
    new GPU code passed except Chronos-2 `xl`/`ft` (not finished).
  - **Found at the end:** single-seed Optuna trials pick lucky seeds (LightGBM: best
    trial 0.573 on validation, same config over 5 seeds 0.431 < default 0.509).
  - **2026-10-20 ~19:30 — RESUME FROM `docs/notes/step12a_fixes.md` §5c.** The Camber GPU
    allowance is used up until 2026-11-13 (node stopped by the platform during EA-LSTM
    tuning, 19/24 trials saved). Laptop chain done (LightGBM without `clim_z` is better on
    every split; WellModel ≈ Pastas). Assil chose **Kaggle** for EA-LSTM + Taccari
    (`scripts/kaggle_gpu.py`, `docs/gpu_howto.md` Kaggle section) and the LightGBM row
    without `clim_z`. Waiting for Assil: Kaggle account + `! .venv/bin/kaggle auth login`,
    and `! camber login` (to bring back the distance ST-GNN regimes from the Stash).
  - 2026-10-20 ~13:20 — older state in `docs/notes/step12a_fixes.md` §5b (then:
    GPU sweep running on the Camber node in `~/pfe_v3_run` with an auto-stop watcher;
    Taccari speed-up `b3a8b74` must be uploaded before its step; laptop chain running;
    after the PC crash the Camber CLI needs `! camber login`). Older checklist below.
  - **Earlier checklist — `docs/notes/step12a_fixes.md` §5:**
    1. fix the tuner (re-evaluate the top 3 trials with 2 more seeds, keep the best
       3-seed mean; `tune.py` + `lgbm.tune()`; note it in `docs/analysis_plan.md` §5)
    2. restart the laptop runs: `STEPS="lgbm_tuned pastas wellmodel" nohup bash scripts/run_cpu.sh > results/v3/cpu_runs2.log 2>&1 &`
    3. Assil runs `! camber login` (OAuth; never click the consent for him)
    4. bundle + upload + GPU sweep on Camber via Chrome (`docs/gpu_howto.md`, v3
       section), **stop the node** when done
    5. ensemble, `baseline_report`, notes, Gate 2 addendum; then Phase 3.
    Design decisions still open: `docs/feedback.md` §11.

- **Data:** all layers are built.
  - piezometers, RPG, BNPE, BD LISA, SAFRAN climate, rivers
  - weekly dataset v1 (`data/processed/dataset_v1/`, 47 wells, 2012–2026)
- **Gate 1 memo** written (`docs/memo_gate1_feasibility.md`). Waiting for
  the supervisor. Consortium questions are parked in
  `docs/savewater_consortium_notes.md`.
- **Phase 2 baselines done on v1** (`docs/results_baselines.md`; median
  test NSE over 33 core wells, test = May 2022–2026 drought):

  | Task | Best baseline | Test NSE |
  |---|---|---|
  | simulation | distance-graph ST-GNN (5 seeds) | 0.26 (RMSE 0.58 m) |
  | simulation | LSTM 0.25 · Pastas 0.13 · LightGBM 0.03 · climatology −0.25 | |
  | forecast 4 wk | Chronos-2 zero-shot | 0.83 (anomaly-persistence floor 0.78) |
  | forecast 12 wk | Chronos-2 zero-shot | 0.42 (floor 0.11) |

- **Step 10 done (dataset v2, tuning, ensemble, ablation; see
  `docs/notes/step10_baselines_v2.md`):**
  - more data (2005 start, 65 wells) does **not** significantly change
    drought skill (Wilcoxon p = 0.24–0.82)
  - LSTM tuning improves validation significantly (0.63, p < 0.001) but not
    the test
  - **every model is stuck near test NSE 0.25**, so the bottleneck is
    missing information, not data
  - baselines of record:
    - simulation: ensemble LightGBM + tuned LSTM, test 0.25 / RMSE 0.587 m
    - hydrology reference: Pastas v1, 0.13
    - forecast: Chronos-2, 0.83 at 4 wk and 0.42 at 12 wk
  - default dataset is now **v2** (`PFE_DATASET`); v1 results are in
    `results/v1/`
- **Key findings so far:**
  - no head-ordering rule (the vertical gradient flips)
  - flat drinking-water pumping is wrong; seasonal is better
  - canal recharge helps the alluvium only
  - plain-wide pumping does not help, so the graph must be selective by
    aquifer unit
  - **every model misses the deepening Pliocene summer drawdowns in the
    drought** (Pliocene test NSE 0.07)

### ▶ STATUS

| Step | Status | Note |
|---|---|---|
| 1 Repo and environment | ✅ done | `docs/notes/step01_environment.md` |
| 4 Hub'Eau piezometers | ✅ done | `docs/notes/step04_piezometers.md` |
| 5 RPG parcels | ✅ done | `docs/notes/step05_rpg.md` |
| 6a BNPE abstraction | ✅ done | `docs/notes/step06a_bnpe.md` |
| 6b BD LISA | ✅ done | `docs/notes/step06b_bdlisa.md` |
| 7 Gate 1 memo | ✅ written; waiting for the supervisor | `docs/memo_gate1_feasibility.md` |
| 8 Phase 1: dataset v1 | ✅ done | `docs/notes/step08_dataset.md` |
| 9 Phase 2: baselines on v1 | ✅ done | `docs/notes/step09_baselines.md` |
| 10 Improve baselines (dataset v2) | ✅ done (tuning, ensemble, ablation, Wilcoxon) | `docs/notes/step10_baselines_v2.md` |
| **11 Gate 2: results to the supervisor** | **✅ summary written; Assil sends it with the Gate 1 memo — waiting for answers** | `docs/summary_gate2_results.md` + `docs/memo_gate1_feasibility.md` |
| **12a Fixes from the critical review** | **🔄 in progress — START HERE** (evaluation ✅, analysis plan ✅, dataset v3 ✅, laptop baselines v3 ✅, GPU sweep partly done: EA-LSTM + Taccari wait for a GPU) | `docs/feedback.md`, `docs/analysis_plan.md`, `docs/notes/step12a_fixes.md` |
| **12 Phase 3: ontology + knowledge graph** | ⬜ after 12a (the knowledge-graph pre-check in `docs/feedback.md` §5.1 comes first) | `docs/roadmap.md` §4 Phase 3 |

### Step 10: improve the baselines (spec)

**Rule:** v1 stays untouched for reproducibility. Everything new goes to
**dataset v2** and **`results/v2/`**. The validation and test periods and
the 33 core wells are identical, so v1 and v2 are directly comparable.

1. **Versioned paths.**
   - `src/config.py` gets `DATASET` (env var `PFE_DATASET`, default `v2`),
     `DATASET_DIR = data/processed/dataset_<v>/` and
     `RESULTS_DIR = results/<v>/`.
   - Every module reads these; nothing hard-codes `dataset_v1`.
   - Move the existing v1 runs to `results/v1/`.
2. **SAFRAN 2000–2004:** `python -m src.ingest.safran --start 2000`
   (resumable; about 0.7 GB downloaded, under the 2 GB rule). Gives warm-up
   for training from 2005.
3. **Dataset v2** (`python -m src.dataset.build --version v2`):
   - training starts **2005-01-01** (v1: 2012); forcings from 2000
   - **all usable dept-66 stations** for training (v1: plain only);
     `core` = the same 33 wells for reporting
   - pumping points: the **whole département** (v1: the plain + 3 km)
   - BNPE starts in 2012: years 2005–2011 are filled with each ouvrage's
     2012–2014 mean and flagged `imputed`
   - splits: train 2005–2019 · validation 2020-01 → 2022-04 · test
     2022-05 → latest (same as v1)
4. **Re-run on v2:**
   - on the laptop: naive, Pastas (`pastas_seasonal_canal` + `pastas`),
     LightGBM
   - on the Camber GPU: LSTM, distance ST-GNN, Chronos-2
5. **LSTM tuning on the GPU** (`src/models/tune_lstm.py`, Optuna):
   - search over lookback 104/156/208 weeks, hidden 64/128, dropout,
     learning rate
   - **select on the validation median NSE only**
   - retrain the best configuration with 5 seeds
6. **Ensemble** (`src/models/ensemble.py`): the mean of the best simulation
   models, with members chosen on validation.
7. **Report:**
   - `src/analysis/baseline_report.py` with a v1 vs v2 comparison table
   - note `docs/notes/step10_baselines_v2.md`
   - commit

**Done when:** the v2 table exists for every baseline. Each change
(2005 start, all stations, tuning, ensemble) is reported against v1, honestly,
including changes that did not help.

### Step 11: Gate 2 (summary written 2026-10-13)

`docs/summary_gate2_results.md` (one page) goes with the Gate 1 memo. It
asks three new questions:
1. Focus the contribution on simulation and explanation, with Chronos-2
   as the forecasting reference?
2. Can the project obtain monthly drinking-water production for the
   Roussillon boreholes?
3. May Phase 3 start now?

**When the answers arrive:** record them here, then update §1 (venue),
§2 (demo site), §3 (framing, karst) and `docs/roadmap.md`.

### Step 12: Phase 3, ontology and knowledge graph

As in `docs/roadmap.md` Phase 3:
1. competency questions
2. reuse GWML2 / SOSA / HY_Features / GeoSPARQL / HILUCS / AGROVOC /
   WHOW-KG
3. the `lulcw:` bridging module
4. alignments (manual gold set + OntoAligner)
5. SHACL
6. SPARQL → PyG `HeteroData`

**Priority from the baselines:** link every abstraction point to its aquifer
unit (BSS depth, usage), because that is the information all models lack.

---

## 7b. Completed steps (details kept for re-runs)

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
  unit.
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

**Next actions**
1. `src/analysis/bdlisa_profile.py`: print the columns and a sample row of
   each layer used before writing logic against it.
2. Join the 33 working-set stations
   (`data/interim/piezo_working_set.parquet`, column `code_bdlisa`) to the
   entities. Report which are missing from the Occitanie extract (first run:
   `760AE09`).
3. Vertical order of the plain's entities (shallow → deep) and the superposed
   pairs from `TABLE_PILE_ENTITES_NIV3`. These become the `overlies` edges.
   Save them as a table in `data/interim/` for the knowledge graph.
4. Vertical well pairs within 5 km in superposed entities (first run: 13).
   **For each pair, report how often the shallow head is above the deep
   head, overall and by season.** That decides whether a head-ordering rule
   is allowed (§3).
5. Write the figure, the data log entry, `docs/notes/step06b_bdlisa.md` and
   the progress table, then commit.

### ✅ Step 7: Gate 1 memo

Write `docs/memo_gate1_feasibility.md`. Keep it short and plain; Assil may
translate it to French. It covers:
- the data inventory and counts
- the surface vs groundwater finding and what it implies
- caveats:
  - the latest BNPE year is under-reported
  - small boreholes are missing, so groundwater irrigation is a lower bound
  - the 2018 reporting break
  - the rising share of "Non qualifié" values
- **the paper plan:** title, RQ1–4, venue
- **the design changes in §3**, with one line of why each
- **questions for the supervisor:**
  - framing: use conflict on the Pliocene, or canal-return recharge
  - keep or drop the 6 karst stations (core = 26)
  - a newer RPG year (2024/2025, GeoPackage v4.0)
  - venue and publication fees (SAVE Water committed to gold open access)
  - the real defence date

Context for the framing question: irrigation in the plain is about 84%
surface water (the historic Têt/Agly canals), while drinking water is 99%
groundwater. This contradicts the subject's "crops pump groundwater" chain.

### ✅ Step 8: Phase 1, forcings and the weekly dataset

1. **SAFRAN / SIM2** (Météo-France, data.gouv.fr, "Données changement
   climatique – SIM quotidienne").
   - Variables: rain, ETP, effective rain, soil-moisture index, on the 8 km
     grid.
   - Keep only the cells covering dept 66.
   - Check the file sizes first: ask before downloading more than 2 GB.
2. **Hub'Eau hydrometrie:** daily discharge for the Têt, Agly, Réart and
   Tech.
3. **Monthly pumping per aquifer unit:** BNPE annual volumes × usage profiles
   (assumption documented, plus a sensitivity flag).
4. **Piezometer series extended to the latest date:** re-run the ingest; the
   cache makes it incremental, but re-fetch stations whose end date is
   recent.
5. **Weekly resampling, gap masks, quality flags, SGI, splits** →
   `data/processed/dataset_v1/`.

### Rebuild results so far (compare with section 8)

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
  - 2,046 abstraction ouvrages, spread weekly; 2024+ imputed.
  - Pastas 2.0.0 installed and pinned.
- Open questions for the supervisor: see Step 7 above.

### ✅ Step 9: Phase 2, baselines on v1

1. Seasonal-naive and persistence floors.
2. **Pastas** per well:
   - inputs: rain, ETP and the weekly pumping near the well
   - warm-up from 2005
   - calibrate on train, report validation and test
   - save the response-function gains: they are the "physics reference"
     for the counterfactual tests in Phase 4
3. LSTM per well and global EA-LSTM (PyTorch; install the CPU wheel and pin
   it).
4. **Chronos-2** zero-shot with covariates.
5. Distance-graph ST-GNN (Taccari-style).

**Metrics:**
- NSE, KGE, RMSE per well and per aquifer group
- on test, with and without "Non qualifié" weeks
- on the leave-wells-out folds
- with 25/50/100% of the training data
- 5 seeds for the neural models

Also check the spring-rise signature (canal recharge?) on all alluvium
wells.

**Final baseline references (2026-10-13), median over 33 core wells:**
- simulation: distance-graph ST-GNN, test NSE 0.26 / RMSE 0.58 m (LSTM 0.25,
  Pastas 0.13)
- forecast 4 wk: Chronos-2 zero-shot, test NSE 0.83
- forecast 12 wk: Chronos-2 zero-shot, test NSE 0.42
- Pliocene wells: test NSE 0.07 for the best simulation model

GPU work runs on Assil's Camber XSMALL GPU node (JupyterLab; CLI jobs are
blocked on the free tier). **Always STOP the node when a GPU run ends**
(1.5 credits/h while on; the node was stopped on 2026-10-13 after step 10). See `docs/gpu_howto.md`; Stash path
`stash://assil0723/pfe/`.

**Done so far (2026-10-13):**
- `src/models/evaluate.py` (shared scoring), `naive.py`,
  `pastas_baseline.py` (5 variants).
- **Reference baselines:**
  - simulation `pastas_seasonal_canal`: median core NSE train 0.57 / val
    0.51 / **test 0.13**
  - forecast 4 wk `naive_anomaly_persist`: **test NSE 0.78**
- Findings:
  - flat drinking-water pumping makes Pastas fake the summer drop with
    evaporation
  - a canal-recharge input helps the alluvium only
  - plain-wide pumping does not help, so the graph must be selective by
    aquifer unit
- torch 2.14.1 CPU installed (`--extra-index-url
  https://download.pytorch.org/whl/cpu`).
- Neural sweeps (5 seeds × variants) go to GPU credits (Colab/Kaggle);
  development and single runs stay on the laptop.

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
  makes a monotonic-drainage constraint viable. The rebuild must check the
  head ordering on these pairs before any such rule is used (§3).

---

## 9. Roadmap

Follow **`docs/roadmap.md`**. It replaces the old step list 8–29.

| Phase | Weeks | Content |
|---|---|---|
| 0 | 1–2 | Finish 6b + Step 7 memo, recreate the env on Linux. **Gate 1** |
| 1 | 3–5 | Forcings (SAFRAN SIM2, river flows, monthly pumping), weekly dataset, splits |
| 2 | 6–9 | Baselines: naive, Pastas, LSTM/EA-LSTM, Chronos-2, distance ST-GNN. **Gate 2** |
| 3 | 8–13 | Competency questions, ontology reuse + bridging module, alignment, KG, SHACL, SPARQL → HeteroData. **Gate 3** |
| 4 | 14–19 | Heterogeneous ST-GNN, soft and hard constraints, ablations, shortcut tests. **Gate 4** (results frozen) |
| 5 | 20–22 | Attributions → ontology templates; faithfulness; case studies |
| 6 | 23–27 | Paper, submitted by end of April 2027 |
| 7 | 28–34 | Thesis, defence; optional Tunisia demo |

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
  River Basin. **The closest competitor.** *(2026-10-20: the 2026-10-13
  "correction" merged two different Wu 2025 papers; both exist.)*
- Taccari et al., *Scientific Reports* 2024 (doi:10.1038/s41598-024-75385-2)
  — ST-GNN for a multi-aquifer system with pumping, river and rain nodes.
  The closest setting to ours.
- Heudorfer et al., *HESS* 2024 (doi:10.5194/hess-28-525-2024) — global
  groundwater models use static features as IDs, not semantics. Motivates
  our semantic-ablation test.
- Collenteur et al., *Groundwater* 2019 (doi:10.1111/gwat.12925) — Pastas,
  the mandatory hydrological baseline.
- Marconato et al., NeurIPS 2023 (arXiv 2305.19951) — reasoning shortcuts.
- OntoAligner, ESWC 2025 (arXiv 2503.21902) — ontology alignment toolkit.
- WHOW-KG, *Scientific Data* 2025 (doi:10.1038/s41597-025-04537-4) —
  network-of-ontologies pattern for water. (The PDF in `Articles/` is the
  2023 preprint.)
- Clark et al., *WRR* 2025 (doi:10.1029/2025WR041303) — XAI for
  spatio-temporal groundwater predictions.
- Dai et al., *JGR: Machine Learning and Computation* 2025
  (doi:10.1029/2025JH000703) — deep learning in hydrogeology. Names the three
  gaps this project addresses.
