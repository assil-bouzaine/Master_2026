# Gemini Neon Review: Full Forensic Audit, Pan-Mediterranean Recovery Architecture & Step-by-Step Roadmap

**Date:** 2026-11-25 · **Reviewer:** Antigravity (Gemini 4 Neon) · **For:** Assil Bouzaine  
**Snapshot reviewed:** commit `2950148` (`main`, clean working tree), dataset `v4`, ontology `0.8.0` (release `2026-11-21T23:00:58Z`), 174 Phase 4 run folders in `results/v4/`, live Phase 5 explanation code (`src/explain/`), `Documents/sujet.docx`, `Documents/PRIMA 2023 SaveWater description.docx`, `docs/roadmap.md`, `docs/analysis_plan.md`.

> **Audit standards:**
> - Nothing in the codebase was modified except writing this document.
> - Every number marked **[new]** was computed read-only from your saved `v4` Phase 4 runs, checkpoints, ontology files, and live Phase 5 explanation runs on 2026-11-25 (Appendix A).
> - Every external dataset, ontology, API, language model, and software tool proposed in this review was **verified online on 2026-11-25** to be **100% free and openly available** (Section 5). No paid APIs and no blocked consortium emails are required to complete the entire technical roadmap.

---

## 0. Executive Verdict — And the 12 Fixes That Make This Thesis Stand Out

### The Brutally Honest Verdict

You have already built a foundation with **unusually high scientific discipline** for a Master's thesis — cleaner than many published environmental-ML papers in terms of anti-leakage controls, ontology provenance, pre-registration, and statistical rigor. **Keep that discipline.**

**However, four major problems currently prevent the project from reaching its full accuracy, explanatory strength, and `sujet.docx` pan-Mediterranean vision:**

1. **The Phase 4 "Hybrid GNN" isn't a GNN yet — and 6 fixable bugs held its accuracy back.** Your main Phase 4 arm (`p4_B2_D_r1`) is a purely linear, non-neural Pastas-like convolution fed an over-pruned Knowledge Graph that leaves **6 of 33 core wells completely blind to rain** (`-0.911` median NSE; one well hits `-20.71`), fails nonlinear **Corbières Karst** physics (`-1.709` NSE vs LSTM `+0.460`), crashes **Leave-Wells-Out (`R2`)** to `-1.875` NSE due to an uncentered zero-intercept bug (`d_m = 0`), and suffers from **7 years of 100%-fake back-filled pumping (2005–2011)**.
2. **Yet your OWN Phase 4 data already proves the idea works once those bottlenecks are removed:**
   - On your main target aquifer (**Pliocene multilayer**, 20 of 33 core wells), Hybrid D (`p4_B2_D_r1`) **already beats LSTM (`+0.109` vs `+0.044`), ST-GNN (`+0.019`), Taccari-D (`-0.019`), Distance Hybrid C (`-0.115`), and Pastas (`-0.331`)** **[new]**.
   - When trained from **July 2012 (`p4_B2_D_r1_f50`)** — where BNPE pumping is *real* rather than 2005–2011 back-fill — Hybrid D jumps to **`+0.226` overall drought NSE** (beating *every* baseline including LSTM `0.124` and the Baseline Ensemble `0.14`!), hits **`+0.371` NSE on the Pliocene** (cutting RMSE from `0.70 m` to `0.40 m`!), and **beats Distance Arm C by 7% error (`-0.070` log RMSE ratio)** across all three pumping reconstructions **[new]**.
   - On **RQ2 (physical sign constraints)**, unconstrained models learn physically backwards pumping effects **32.4%–42.1%** of the time and backwards river effects **40%** of the time; even a massive soft penalty (`soft100`) still violates **20.6%** while hurting accuracy (`-0.157` NSE). **Hard ontology constraints cut violations to `0.0%` at zero accuracy cost** **[new]**.
3. **Both flagship Phase 5 case studies currently get `withheld` by your own explanation script:**
   - At `MILLAS C2-1` (where BRGM measured 45.4% canal recharge), leaving the canal unconstrained with a plain-wide 181-intake sum caused a **50/50 sign split** across starts (`-0.098 ± 0.527 m`), forcing `report.py` to withhold the canal explanation **[new]**.
   - On `NYLS-1` (summer 2024 vs summer 2023), blunt pooling (`λ = 0.1`) + 2005–2011 fake pumping shrunk the pumping difference down to **`-0.008 m`**, forcing `report.py` to withhold it too **[new]**.
4. **The ontology is currently "France-locked" — not yet pan-Mediterranean:**
   - **49 of 296 classes/properties in `ontology/lulcw.ttl` hard-code French agencies/databases** (`bdlisaCode`, `bnpeCode`, `bssCode`, `rpgEdition`, `safranGridXHm`, `bdCarthageCode`, `bdtopoId`, `wfdCode`) **[new]**.
   - Key Mediterranean concepts required by [sujet.docx](file:///home/mclovin/Projects/Master_2026/Documents/sujet.docx) and PRIMA SAVE Water (Tunisia, Morocco, Algeria, Egypt, Spain, Greece, Italy) — *greenhouses, drip vs. flood return-flow paradox, coastal seawater intrusion/salinisation, ephemeral wadis/oueds, treated wastewater reuse, managed aquifer recharge, unmetered wells, olive-to-horticulture shifts, pastoralism-agriculture conflicts* — are missing, because **paper-based concept extraction**, **AGROVOC/non-EU alignments**, **Sentinel-2 semantic rules (`SO2`)**, and the **GIS dashboard (`SO5 / CQ16`)** haven't been built yet.

### The Winning Strategy: Keep France for Full ML Training + Make Ontology & Satellite Transfer Truly Pan-Mediterranean

**Was choosing Roussillon (France) for ML training & testing a good call?**  
**YES — 100%.** Training and rigorously testing a neuro-symbolic groundwater model requires 20+ years of weekly piezometry, gridded climate, 3D geology, river/canal gauges, crop maps, and pumping volumes — plus an extreme drought and published BRGM physical benchmarks. No South-Mediterranean basin exposes all of that via free open APIs. Trying to run a full second ML benchmark in another country would stall the thesis for months.

**The optimal Master's architecture (zero email dependency, 100% free open resources):**
1. **Full Quantitative ML, Twin & XAI Benchmark → Roussillon, France (`dataset_v5` + `Hybrid-GNN v2`)**, benchmarked transparently beside your frozen `v4 / Hybrid v1` milestone.
2. **Pan-Mediterranean Meta-Ontology (`lulcw` v1.0) → 2-Layer Design:** Country-agnostic **Mediterranean Core** + thin **Country Adapter Profiles** (`lulcw-fr-profile.ttl`, `lulcw-tn-profile.ttl`), aligned to multilingual/global vocabularies (**AGROVOC**, **CORINE SKOS**, **SAREF4WATR/AGRI**, **ENVO**, **GEMET**, deeper **SWEET**, **GWML2/HyFO**, **INSPIRE**) and enriched by **2-Track Paper Extraction** (20–30 pan-Mediterranean open-access papers + your 32 BRGM quotes).
3. **Zero-Email South-Mediterranean Transfer Proof → Manouba, Tunisia (SAVE Water Living Lab):** Using **100% free global satellite & climate data** (`Sentinel-2` NDVI+NDMI, `ESA WorldCover`, `ERA5-Land` on Google Earth Engine + published Manouba hydrogeology), instantiate `lulcw-tn-profile.ttl`, run the exact same **SHACL-AF `ProbablyIrrigatedParcel` rule (`CQ15`)** and **SPARQL queries**, measure the exact **France → Tunisia Ontology Reuse %**, and display Manouba beside Roussillon in the **Interactive GIS Dashboard**!

### Summary of the 12 Core Improvements (and WHY Each One Matters)

| # | Improvement / Addition | Layer | **WHY We Need It** | Expected Impact |
|---|---|---|---|---|
| **1** | **Imputed-era pumping reliability weighting** (2005–2011 weather-only, 2012–2019 full pumping) | Data / Training | 2005–2011 is 100% fake constant pumping, attenuating pumping gains & hiding D's win over C (`f50` already proved `+0.226` NSE, `+0.371` Pliocene, `-7%` D vs C!). | 🔥🔥🔥 Accuracy + Attribution + D vs C |
| **2** | **Auto-centered stresses + `--gain-units sd` + strong `delta` penalty** | Model | Fixes the LWO `d_m = 0` bug (`|d_m|` averages `1.04 m` on trained wells → `-1.875` crash on unseen wells!) and stops `delta` from starving the KG encoder. | 🔥🔥🔥 Rescues R2 Transfer & B vs A |
| **3** | **Nonlinear Monotone Soil-Moisture Bucket (`FlexModel`) + Double-Gamma (`amax = 104 wk`)** | Model | Linear `rain - f·ETP` crashes on Karst (`-1.71` NSE, `+1.46 m` bias) and multi-year drought; `DRAINC` alone jumps `r` `0.746 → 0.829` & doubles Pliocene NSE! Stays 100% monotone! | 🔥🔥🔥 Closes/beats LSTM while keeping 0% violations |
| **4** | **Two-Channel KG Recharge (`overlies` vertical leakage + regional outcrop)** | KG / Rules | 6 of 33 core wells have ZERO weather edges in Arm D (`-0.911` median NSE; `10912X0024/F` = `-20.71`); unit-wide recharge alone cuts overall RMSE `0.758 → 0.604 m`! | 🔥🔥🔥 Eliminates weather-blind wells using multilayer KG |
| **5** | **Basin-split canals (Têt/Agly/Tech) + real gauged canal flows + hard sign on measured return (`718BP02`)** | Data / KG | Plain-wide 181-intake sum + unconstrained sign causes 50/50 sign split at `C2-1`, forcing explanations to **withhold** Case Study 3! Gauged canals also break `r = 0.96` weather collinearity. | 🔥🔥 Fixes Recent Alluvium & Case Study 3 |
| **6** | **Real Heterogeneous GNN Parameter Encoder (`PyG HeteroConv / GATv2`) + Split Regularization** | Model | Unifies KG facts (`B1`), KG routing (`B2`), message passing (`B5`), and stability (`B2conv`) into **one accurate, stable neuro-symbolic GNN** matching `sujet.docx`. | 🔥🔥 One unified model (no B2 vs B2conv split!) |
| **7** | **Free Open Data Upgrades (`dataset_v5`)**: SAFRAN 1990 warm-up, Hub'Eau refresh (2024–25 validation + BNPE 2025 check), BRGM InfoTerre WFS BSS depths, optional nitrate layer | Data | Eliminates 5-year warm-up padding, lifts *"0% validated weeks"* caveat in 2024 case studies, improves CQ2 pump-depth attribution, and adds nitrate risk context for `sujet.docx`. | 🔥🔥 Cleaner data & stronger explanations |
| **8** | **2-Layer Pan-Mediterranean Ontology (`lulcw` v1.0) + Persisted Oxigraph Store + pyLODE docs** | Ontology / KG | Removes the 49 France-locked terms from core, prunes 23 unused terms, cuts monolithic `lulcw.ttl` into clean WHOW-KG modules, and speeds SPARQL **50× (`30s → <50ms`)** for live dashboard use. | 🔥🔥 True Mediterranean reusability + fast queries |
| **9** | **Expanded Pan-Mediterranean Alignments (`SO1`)**: AGROVOC + EuroCrops HCAT + SAREF4WATR/AGRI + CORINE SKOS + ENVO + GEMET + deeper SWEET | Ontology | RPG is France-only & HILUCS is EU-only; adding multilingual FAO/ETSI/OBO vocabularies makes the ontology work across North & South Mediterranean + delivers real P/R/F1 alignment tables. | 🔥🔥 Fulfils `sujet.docx` SO1 for the whole Med |
| **10** | **2-Track Paper Extraction (`sujet.docx` Phase 1)**: 20–30 pan-Med open-access papers (TBox) + 32 BRGM quotes (ABox) via local `Qwen2.5-7B-Instruct` | NLP / KG | Populates literature-backed Mediterranean causal axioms (*greenhouses, drip paradox, salinisation, MAR, conflicts*) with DOI provenance AND delivers a rigorous P/R/F1 extraction benchmark. | 🔥🔥 Fulfils `sujet.docx` Phase 1 scientifically |
| **11** | **Sentinel-2 NDVI + NDMI `ProbablyIrrigatedParcel` (`SO2 / CQ15`) + Zero-Email Manouba Transfer Proof** | EO / Transfer | Delivers `sujet.docx` SO2 on Roussillon (validated by 2022→2023 canal cut) AND proves live France → Tunisia transfer on Manouba using 100% free GEE satellite data! | 🔥🔥🔥 Fulfils SO2 + proves North-South transfer! |
| **12** | **Full XAI Benchmark (`SO4 / CQ10`) + Interactive 4-Tab GIS Dashboard (`SO5 / CQ16`)** | XAI / App | Compares Hybrid-GNN v2 vs Black-Box XAI (Captum IG + GNNExplainer, Fidelity+/−, Adebayo sanity check) and delivers the interactive map + "what-if crop/pumping mitigation" tool from `sujet.docx`. | 🔥🔥🔥 Complete end-to-end thesis showstopper |

---

## 1. Audit Against `Documents/sujet.docx` & PRIMA SAVE Water

Your subject ([Documents/sujet.docx](file:///home/mclovin/Projects/Master_2026/Documents/sujet.docx)) and the PRIMA SAVE Water proposal ([PRIMA 2023 SaveWater description.docx](file:///home/mclovin/Projects/Master_2026/Documents/PRIMA%202023%20SaveWater%20description.docx)) ask for a **Mediterranean-wide neuro-symbolic pipeline** linking North & South Mediterranean partners (Tunisia, Morocco, Algeria, Egypt, Spain, France, Italy, Greece):

```
Heterogeneous Data (Sentinel-2, Wells, Pumping, Rivers, Canals, Crops, Literature)
        │                                                    │
        ▼                                                    ▼
[Phase 1] Pan-Med Meta-Ontology (OWL)  ◄── Align SWEET/INSPIRE/AGROVOC/SAREF/ENVO + Paper Extraction
        │
        ▼
[Phase 2] Semantic Remote Sensing (SHACL-AF rules → ProbablyIrrigatedParcel, functional water zones)
        │
        ▼
[Phase 3] Spatio-Temporal KG ──► Neuro-Symbolic GNN + Physical Constraints (monotone by construction)
        │
        ▼
[Phase 4] Risk Predictions (Head + SGI) ──► Retro-Traceable Causal Explanations (Hybrid + Black-Box XAI)
                                                         │
                                                         ▼
                                      [SO5] Decision-Support GIS Dashboard ("What-If" Mitigation CQ16)
```

### Honest Gap Matrix: Current Repository vs `sujet.docx`

| `sujet.docx` Objective | Exists Today (`2026-11-25`) | Grade | Specific Gap to Close |
|---|---|---|---|
| **Meta-ontology LULC-Water (OWL, Mediterranean)** | `ontology/lulcw.ttl` v0.8.0 (413 terms, FR/EN, HermiT consistent, OOPS! clean, 11/16 CQs) | **B+** | Monolithic 150 KB file; **49 terms France-locked**; 23 unused terms; missing Mediterranean mechanisms (`salinisation`, `drip`, `greenhouse`, `MAR`, `wadis`), `CQ10` (`0.9.0`), `CQ15`, HTML docs. |
| **SO1: Align domain ontologies** | GWML2/HyFO, SWEET (4 classes), HY_Features, INSPIRE + entailment ledger. | **C+** | `lu_agrovoc_gold.csv` is **0/198**; OntoAligner never run; no non-EU/North-African land-cover or sensor/risk alignments (AGROVOC, SAREF4WATR/AGRI, CORINE, ENVO, GEMET). |
| **Phase 1: Text extraction from articles** | 32 hand-curated BRGM/SDAGE quotes (`configs/exchange_evidence.csv`). | **D** | Zero automated extraction run; no pan-Mediterranean papers mined for causal TBox axioms. |
| **SO2: Semantic remote sensing rules** | Only tabular RPG crop areas + FAO-56 `Kc` index (`LU-4` null). | **F** | Zero Sentinel-2/1 imagery pulled; no `ProbablyIrrigatedParcel` rule (`CQ15`). |
| **SO3: Ontology structures & constrains DL/GNN** | SPARQL → `edges_D` export; linear `ResponseModel` with hard monotone signs; `taccari_D` black box. | **C+** | Hard signs are a huge win (`0%` vs `32–42%` violations!), **but** hybrid has no real GNN, leaves 6 core wells weather-blind, fails Karst (`-1.71`), crashes LWO (`-1.875`). |
| **SO4: Actionable explanations + XAI** | `src/explain/` (exact contributions + KG chains + FR/EN templates). | **B−** | Both flagship case studies (`C2-1` canal, `NYLS-1` 2024 vs 2023) get **withheld**; no black-box GNNExplainer/IG comparison, no Fidelity+/− comparison, no Adebayo sanity check, no CQ10 RDF graph. |
| **SO5: GIS Dashboard + scenario queries (`CQ16`)** | `docs/explainer/index.html` (static project story). | **D** | Not an interactive GIS map, no live SPARQL query runner, no `CQ16` "what-if crop/pumping mitigation" simulator. |
| **North–South Mediterranean transfer** | Roussillon only; Manouba blocked on private emails. | **D** | No live South-Mediterranean demonstration yet (easily unlocked with zero emails via GEE Sentinel-2 + WorldCover + ERA5-Land!). |

---

## 2. Deep Forensic Audit: What Went Good & What Went Wrong

### 2.1 Data Layer Forensics

1. **The 2005–2011 Fake Pumping Trap (`f50` Proof)** **[new]:**
   - In `dataset_v4/pumping_weekly.parquet`, real BNPE volumes begin in **2012**: years **2005–2011 are 100% imputed** (`66.91 Mm³/yr` groundwater constant every year), **2012–2022** are `0–2%` imputed, **2023–2024** are `8%` imputed, and **2025–2026** are **100% imputed**.
   - **Direct impact measured on Phase 4:** Training on 2005–2019 (`R1`) dilutes pumping weights because 47% of training years have invented flat pumping. Training on **2012-07 → 2019 (`f50`, real BNPE)** causes Hybrid D to jump from **`+0.014` → `+0.226` core drought NSE** (beating *every* baseline including `lstm_tuned` `+0.124` and `Ensemble` `+0.14`!), jump from **`+0.109` → `+0.371` on Pliocene** (RMSE `0.697 → 0.404 m`!), and **beat Distance Arm C by 7% error (`-0.070` log RMSE ratio)** across all three reconstructions (`r1`: `+0.226` vs `-0.085`; `r2`: `+0.174` vs `-0.056`; `r3`: `+0.080` vs `-0.138`, `70%` wells better!).
2. **Plain-Wide Canal Sum Discards River-Basin Physics:**
   - `src/dataset/pumping.py:canal_series()` lumps all **181 surface canal intakes** across the entire Roussillon plain into one time series spread by climatic deficit (`r = 0.96` with summer heat).
   - Meanwhile, `pumping_points.parquet` already has exact intake coordinates (allowing instant **Têt / Agly / Tech** basin splits!), AND `src/ingest/hubeau_hydro.py` already downloads **real daily gauged canal flows (`is_canal=True`)** that were never wired into the canal profile!
3. **Irrigation Attribution Bottleneck (`0%` in Main Policy):**
   - Plain groundwater BNPE (`1,890` points): drinking water = `282` points (`135` BSS, `129` recorded unit, `522.6 Mm³`, **98%** group / **83.7%** exact attributed); irrigation = `1,485` points (`8` BSS, `0` recorded unit, `161.4 Mm³`, **0%** attributed).
   - Only `hubeau_qualite/stations` was queried for borehole metadata — BRGM's open **InfoTerre WFS BSS** layer (which publishes borehole `profondeur_totale` across France) has not yet been queried to enrich depths.
4. **Short Climate Warm-Up & Statistical Power:**
   - `dataset_v4` starts forcing in `2000` (5-year warm-up < 6-year kernel `312` weeks!), even though `src/ingest/safran.py` already supports `--start 1990` (15-year warm-up!).
   - With `33` core wells in `14` spatial clusters (10 km cells), statistical power is tight; testing adjacent **Aude (`dept 11`)** wells on the shared Corbières/Agly units can check whether cluster count grows cleanly to ~18–22 (keeping the 33 Roussillon core wells as a primary backward-compatible slice).

---

### 2.2 Ontology & Knowledge Graph Forensics

1. **49 France-Locked Terms in Core `lulcw.ttl`** **[new]:**
   - `bdlisaCode`, `bdlisaNatureCode`, `bdlisaThemeCode`, `bdlisaMediumCode`, `bnpeCode`, `bssCode`, `bssId`, `rpgEdition`, `rpgGroupCode`, `safranGridXHm`, `safranGridYHm`, `bdCarthageCode`, `bdtopoId`, `wfdCode`, plus 35 class/property definitions naming French agencies. This makes the core ontology look Roussillon-specific rather than pan-Mediterranean.
2. **Monolithic File + Unused Terms:**
   - Single `150 KB` `ontology/lulcw.ttl` declaring **413 terms** (`86` classes, `109` object properties, `101` datatype properties, `24` concept schemes, `93` individuals): **23 terms are completely unused** anywhere, and **56** appear only in axioms/shapes (`docs/ontology_term_usage.md`).
3. **The "Over-Pruning Trap" Starved the Model of Weather & Leakage** **[new]:**
   - **6 of 33 core wells** (`BAR3`, `BAR4`, `TOR3`, `F3N4`, `10912X0024/F`, `CARRIE`) receive **ZERO recharge edges** in Arm D (because their confined unit doesn't outcrop within 5 km!). Median drought NSE on these 6 wells = **`-0.911`** (`10912X0024/F` = **`-20.71`**, `TOR3` = `-6.35`, `CARRIE` = `-2.38`) vs **`+0.062`** in Arm C and **`+0.385`** in LSTM!
   - Switching to unit-wide outcrop (`p4_B7_D_unitwide_r1`) immediately drops overall RMSE from **`0.758 m` → `0.604 m`** (beating LSTM's `0.753 m`!) and improves `10912X0024/F` from `-20.71 → -3.26`!
   - `lulcw:overlies` is derived in the KG with polygon witnesses, yet **never routed as a vertical-leakage recharge pathway** for covered aquifers!
4. **Slow In-Memory Turtle Reload (~25–30s per Query):**
   - Every CLI run of `src/kg/cq.py` or `src/explain/report.py` re-parses ~470k Turtle triples from scratch. Persisting a disk-backed `pyoxigraph.Store(path)` drops SPARQL latency from **~30 seconds → < 50 ms**.

---

### 2.3 Model Architecture & Phase 4 Forensics **[new]**

#### Per-Aquifer Drought Performance Across Key Runs (33 Core Wells) **[new]**

| Run | Core NSE | Core RMSE | Core `r` | Pliocene (20) | Recent Alluv. (4) | Ancient Alluv. (2) | Karst (6) |
|---|---:|---:|---:|---:|---:|---:|---:|
| `lstm_tuned` | `+0.124` | `0.753 m` | `0.825` | `+0.044` | **`+0.214`** | `-0.272` | `+0.460` |
| `stgnn_tuned` | `+0.055` | **`0.547 m`** | **`0.871`** | `+0.019` | `+0.019` | `-0.157` | **`+0.562`** |
| `taccari_D` (black box, KG edges) | `-0.006` | `0.595 m` | — | `-0.019` | **`+0.257`** | `-0.809` | `+0.301` |
| `pastas` reference | `-0.753` | `0.743 m` | — | `-0.331` | `-0.678` | `-1.757` | `-2.538` |
| `p4_B2_C_r1` (Hybrid, distance) | `-0.188` | `0.638 m` | `0.774` | `-0.115` | `-0.130` | `-0.048` | `-1.291` |
| **`p4_B2_D_r1` (Hybrid, KG)** | `+0.014` | `0.758 m` | `0.746` | **`+0.109`** | `-0.428` | `+0.239` | **`-1.709`** |
| `p4_B2conv_D_r1` (converged) | `-0.248` | `0.748 m` | — | `-0.160` | `-0.475` | `-0.068` | `-1.855` |
| `p4_B8_D_r1` (+ seasonal resid.) | `+0.033` | `0.745 m` | — | `+0.137` | `-0.267` | `+0.145` | `-1.731` |
| `p4_B7_D_unitwide_r1` | `-0.010` | **`0.604 m`** | — | `-0.020` | `-0.355` | `+0.240` | `-1.504` |
| **`p4_B7_D_drainage_r1` (DRAINC)** | `+0.019` | `0.683 m` | **`0.829`** | **`+0.223`** | `-0.556` | `-0.281` | `-1.250` |
| **`p4_B2_D_r1_f50` (2012–2019!)** | **`+0.226`** | `0.616 m` | `0.771` | **`+0.371`** | `-0.245` | **`+0.357`** | `-1.686` |
| `p4_B2_D_r1_lwo` (Leave-wells-out) | **`-1.875`** | `1.025 m` | `0.492` | `-1.466` | `-2.968` | `-0.042` | `-6.048` |

#### The 4 Model Bugs Discovered + 2 Proven Wins **[new]**
1. **BUG — LWO (`R2`) Zero-Intercept + `delta` Starvation + Metre Pooling:**
   - Stresses in `src/models/response.py` are uncentered, so convolutions carry a 1–6 m offset. In `p4_B2_D_r1_lwo/fold_0`, the 51 trained wells learn `mean |d_m| = 1.044 m` (up to `-6.20 m`), while all **13 held-out wells stay frozen at `d_m = 0.000 m`**! Simply centering held-out predictions on their training-period mean (zero retraining, zero leakage) rescues `p4_B2_D_r1_lwo` `valNSE` from **`-0.316 → +0.046`** and cuts drought RMSE **22% (`1.109 → 0.866 m`)**!
   - In `p4_B1_B_r1_lwo/fold_0`, `RMS(delta) = 1.2555` (max `17.57`) vs `RMS(static_map(Z)) = 0.7261`, and `gain_scale = 1.0` (raw metres instead of `sd`): per-well `delta_i` absorbs well differences during training, starving the KG encoder for unseen wells!
2. **BUG — Linear Recharge Fails Karst & Drought:**
   - Karst (`-1.709` NSE, `+1.463 m` bias, `r = 0.570`) requires nonlinear soil-moisture / epikarst saturation. Simply feeding Météo-France's nonlinear `DRAINC` (`p4_B7_D_drainage_r1`) jumps overall `r` from `0.746 → 0.829` (matching LSTM!) and doubles Pliocene NSE (`+0.109 → +0.223`)!
3. **BUG — Disconnected Rungs (No True GNN):**
   - `B1` had KG facts without KG routing; `B2` had KG routing without KG facts or any neural network; `B5` used only a 1-hop static linear matrix; `B8` showed even a tiny 4-number seasonal residual improves **70%** of core wells (median residual variance share only `6.2%`).
4. **BUG — Blunt Single-`λ` Trade-Off (`B2` vs `B2conv`):**
   - Early stopping (`B2`) gives better NSE (`+0.014`) but unstable starts (D wins only 25% of twin worlds on pumping); converged pooling (`B2conv`, blunt `λ = 0.1` on all params) wins 82% of twin worlds but over-shrinks gains and drops NSE to `-0.248`.
5. **WIN — RQ2 (`B4`) Physical Sign Constraints:**
   - Unconstrained (`none`) violates signs on **32.4% / 42.1% / 35.2%** of attributed pumping (`r1/r2/r3`), **35.5%–43.3%** of unattributed pumping, **35–40%** of constrained rivers, and **10.9%–15.2%** of rain. Even `soft100` still leaves **20.6%** pumping violations and crashes drought NSE to `-0.157`. **Hard constraints achieve `0.0%` violations everywhere at equal/better accuracy!**
6. **WIN — B3 Semantic Ablation:**
   - Arm D beats `F_random` by **9%–15% RMSE** (`-0.089` to `-0.154`), beats `F_complete` by **5%** (`-0.050`), and beats `E_degree` in **5/5 draws** (`-0.000` to `-0.059`), tying `E_distance` in R1 due to the 2005–2011 fake pumping and 6 weather-blind wells.

---

### 2.4 Live Phase 5 Explanation Forensics **[new]**

Running `src/explain/report.py` on `p4_B2conv_D_r1` (with `r2`, `r3` siblings):
- **`NYLS-1` Summer 2024 vs Avg Year:** Sim `51.22` vs Obs `50.45 m` (SGI `-1.94` exact!). Credits Recharge `-2.09 m`, Attributed pumping **`+0.07 m`** (right sign for 2024 pumping cut, 100% agree, lists top 5 real BNPE boreholes!), Unattributed pumping `-0.31 m` (5× larger than attributed!). *Caveat:* `0/18` observed weeks validated.
- **`NYLS-1` Summer 2024 vs Summer 2023:** Attributed pumping = **`-0.008 ± 0.005 m` → WITHHELD** (over-shrunk by blunt `λ = 0.1` + 2005–2011 fake pumping; reconstructions disagree).
- **`MILLAS C2-1` (Alluvium) Summer 2023 vs Avg Year:** Sim `103.21` vs Obs `102.09 m` (`+1.12 m` too high). River `-0.61 m` (accepted), Recharge `-0.16 m` (accepted), **Canal diversions = `-0.098 ± 0.527 m` (50% sign agreement!) → WITHHELD** because canal was unconstrained and fed the plain-wide 181-intake sum!

---

## 3. Evaluating Your Current Plan: What to KEEP vs What to CHANGE

| Element of Current Plan (`docs/roadmap.md`, `docs/analysis_plan.md`) | Action | Why |
|---|---|---|
| Simulation (no past head) vs Chronos-2 hindcast separation | ✅ **KEEP** | Scientifically superior to persistence-dominated groundwater GNN papers. |
| Drought/recovery split + Skill vs Climatology + KGE'' + SGI/IPS + per-group tables | ✅ **KEEP** | Gold-standard hydrological evaluation. |
| Log RMSE ratio + Cluster sign-flip test + 10 seeds + Same-arm bands + Exact paired support + Fingerprints | ✅ **KEEP** | Eliminates seed noise and false positives. |
| 3 pumping reconstructions + explicit unattributed pumping + semi-synthetic twin | ✅ **KEEP & UPGRADE** | Protects against collinearity and tests "right reasons" rigorously. |
| Keep frozen `v4 / Phase 4 v1` (`analysis-plan-v2`) completely untouched | ✅ **KEEP** | Never erase pre-registered results; compare `v5 / Hybrid-GNN v2` transparently beside `v4`. |
| Hard monotone constraints by construction | ✅ **KEEP & EXTEND** | Your strongest empirical win (`0%` vs `32–42%` violations); extend to `FlexModel` & measured canals. |
| Single France-locked monolithic `lulcw.ttl` + on-the-fly Turtle parsing | 🔄 **UPGRADE** | Split into **Pan-Mediterranean Core + thin Country Profiles**, add Med alignments & persisted Oxigraph store. |
| Zero weather edges for confined wells & no `overlies` routing | 🔄 **UPGRADE** | Route `overlies` vertical leakage + regional outcrop as explicit ontology-derived indirect recharge. |
| Linear `rain - f·ETP` + uncentered stresses + metre pooling + blunt `λ` + no real GNN | 🔄 **UPGRADE** | Replace with **Hybrid-GNN v2** (centered, `sd` gains, monotone `FlexModel`, PyG `HeteroGNN`, 2012+ pumping weighting, split reg). |
| Plain-wide 181-intake canal sum + unconstrained canal | 🔄 **UPGRADE** | Basin-split canals (Têt/Agly/Tech) + gauged canal flows (`hubeau_hydro`) + hard `≥ 0` sign where measured. |
| Text extraction limited to 32 French quotes; Manouba waiting on emails | 🔄 **UPGRADE** | **2-Track Paper Extraction** (20–30 pan-Med papers + 32 BRGM quotes) + **Zero-Email Manouba GEE Transfer Proof**. |

---

## 4. Detailed Fix Blueprint (Every Layer, Every "Why")

### 4.1 Data Layer (`dataset_v5` — Roussillon + Free Satellite Manouba)

1. **Extend SAFRAN-SIM2 back to 1990 (`--start 1990`):**
   - *Why:* Eliminates artificial constant padding in the first years of training and supports multi-year (`amax = 104` wk / 6–10 yr) groundwater memory.
2. **Refresh Hub'Eau Piezometry + Check BNPE 2025:**
   - *Why:* Captures newly ADES-validated 2024–2025 observations (removing the *"0% validated weeks"* caveat in 2024 explanations) and checks whether 2025 BNPE declarations are online (eliminating 100% imputation in the 2025 drought year).
3. **Basin-Split Canals (Têt / Agly / Tech) + Real Gauged Canal Profiles:**
   - *Why:* Each alluvium well receives its *own* river basin's canal diversions, shaped by real daily gauged canal flows (`is_canal=True` already in `data/raw/hubeau_hydro/`) instead of the climate deficit (`r = 0.96`), breaking collinearity and fixing `C2-1`.
4. **BRGM InfoTerre WFS BSS Borehole Depth Enrichment:**
   - *Why:* Programmatically retrieves `profondeur_totale` and `bss_id` for nearby boreholes to improve CQ2 pump-to-layer attribution (especially irrigation & alluvium) without waiting on private data. *(Note: multi-level screen intervals/`crépines` are rarely exposed in WFS; total depth is the clean, scalable free signal, and missing screens remain honestly flagged as unknown.)*
5. **Google Earth Engine Satellite Pull (`SO2 / CQ15`) — Roussillon AND Manouba (Tunisia):**
   - *Why:* Fulfils `sujet.docx` SO2 on Roussillon (`COPERNICUS/S2_SR_HARMONIZED` summer NDVI + NDMI within-crop-class anomalies, validated independently via the **2022→2023 46% canal-cut difference-in-differences** + Agreste census) AND simultaneously pulls **Manouba (Tunisia)** `Sentinel-2` NDVI/NDMI + `ESA/WorldCover/v200` + `ECMWF/ERA5_LAND/DAILY_AGGR` so we can prove South-Mediterranean transfer with **zero emails**!
6. **Optional Free Additions (Evaluated at Step 3):**
   - **Nitrate Context Layer (`hubeau/qualite_nappes/analyses`, `code_parametre=1340`):** Stored as annual SOSA observations in the KG & GIS dashboard (`> 50 mg/L` WFD threshold) so the thesis/dashboard links agricultural pressure to *both* water quantity and nitrate vulnerability without over-scoping the neural target.
   - **Adjacent Aude (`dept 11`) Piezometers:** Quick feasibility check on whether Corbières/Agly wells just north of dept 66 expand spatial cluster power from 14 → ~18–22 clusters (always reporting the 33 Roussillon core wells separately for clean `v4` comparison).

---

### 4.2 Pan-Mediterranean Meta-Ontology & KG (`lulcw` v1.0)

1. **2-Layer Modular Architecture (True WHOW-KG Pattern — Eliminates France-Lock!):**
   - **Layer 1 — Pan-Mediterranean Core (100% Country-Agnostic, 7 small modules):**
     - `ontology/modules/lulcw-core.ttl` — `MonitoringPoint`/`Piezometer`, `MonitoringStation`, `HydrogeologicalUnit`, `AlluvialAquifer`, `MultilayerAquiferSystem`, `KarstAquifer`, `ConfiningUnit`, `StratigraphicRelation` (`overlies`), `UnitAttribution`, `Provenance`, `Confidence`, `AnswerStatus` (generic `dcterms:identifier` & `skos:notation`, zero French agency codes!).
     - `ontology/modules/lulcw-hydro.ttl` — `AbstractionFacility`, `Watercourse`, `RiverReach`, `CanalSystem`, `Gauge`, `WaterUse`, `ConfinementAssessment` (`CQ14`), `WaterQualityObservation` (Nitrate/Salinity/EC), `EphemeralStream` (Wadi/Oued), `ManagedAquiferRecharge`.
     - `ontology/modules/lulcw-lulc.ttl` — `LandParcel`, `LandUseClass`, `CropType`, `IrrigationPractice` (drip, flood/canal, greenhouse, rainfed), `IrrigationDemandObservation` (`CQ7`).
     - `ontology/modules/lulcw-eo.ttl` — `SpectralIndexObservation` (NDVI, NDMI), `ProbablyIrrigatedParcel` SHACL-AF rule (`CQ15`, `SO2`).
     - `ontology/modules/lulcw-med-causal.ttl` — **Literature-extracted Pan-Mediterranean causal axioms** (with paper DOIs!) covering olive-to-greenhouse shifts, drip return-flow paradox, coastal salinisation, unmetered pumping, MAR/wastewater reuse, and `WaterUseConflict`.
     - `ontology/modules/lulcw-causal.ttl` — `Influence`, `IndirectRechargeInfluence` (`OverlyingLeakageInfluence`, `RegionalOutcropInfluence`), `DriverGroup`, `ExportPolicy`, `ConstraintDecision` (`CQ8`).
     - `ontology/modules/lulcw-xai.ttl` — `ModelRun`, `SimulatedHead`, `DriverContribution`, `ExplanationStatement`, `MitigationScenario` (`CQ10`, `CQ16`).
   - **Layer 2 — Thin Country Adapter Profiles:**
     - `ontology/profiles/lulcw-fr-profile.ttl` — French sub-properties (`bdlisaCode`, `bnpeCode`, `bssCode`, `rpgEdition`, `safranGridXHm`, `bdCarthageCode`, `wfdCode`, all `rdfs:subPropertyOf skos:notation` or `dcterms:identifier`).
     - `ontology/profiles/lulcw-tn-profile.ttl` — Tunisian Manouba profile (DGRE/CRDA/SONEDE/MSE-UMA identifiers, `ESA WorldCover` classes, Manouba phreatic aquifer & Oued Medjerda/Ellil context).
   - *Why:* Solves the #1 jury challenge (*"Why is a Mediterranean meta-ontology hard-coded to France?"*) and lets you report a real, quantified **France → Tunisia Ontology Reuse %**!
2. **Expanded Pan-Mediterranean Alignments (`SO1`):**
   - Keep existing verified alignments: **GWML2/HyFO**, **HY_Features**, **INSPIRE** (hydrogeology + HILUCS), **SOSA/SSN**, **GeoSPARQL**, **PROV-O**, **OWL-Time**, **SKOS**.
   - Add 4 pan-Mediterranean open alignments (MIREOT + entailment ledger checked by HermiT):
     - **AGROVOC (FAO, CC BY 4.0):** Multilingual (EN/FR/AR/ES/IT/EL) crops & irrigation practices — main **OntoAligner** benchmark (`RPG → AGROVOC`, accelerated by EuroCrops English/botanical names + 30-code blind subset!).
     - **EuroCrops HCAT (CC BY-SA 4.0):** Expert-curated French RPG → HCAT gold standard (immediate, unbiased second alignment benchmark for OntoAligner!).
     - **CORINE Land Cover SKOS (`w3.org/2015/03/corine#`) + ESA WorldCover legend:** Bridges EU land-cover standards with global 10m satellite land cover usable across Tunisia/Morocco/Egypt!
     - **SAREF4WATR & SAREF4AGRI (ETSI, BSD-3-Clause):** Models smart water IoT sensors (like MSE-UMA Manouba!), consumption, water quality (`Nitrate`, `Salinity`), and agricultural parcels cleanly alongside SOSA/SSN.
     - **Deeper SWEET (CC0) + ENVO (CC0) + GEMET (CC BY 4.0):** Standardized Mediterranean hazards & concepts (*Drought*, *SaltwaterIntrusion*, *Wadi/EphemeralStream*, *Greenhouse*, *NitratePollution*, *Overexploitation*, *WaterUseConflict*).
3. **2-Track Paper Extraction (`sujet.docx` Phase 1) via Local `Qwen2.5-7B-Instruct` (Apache 2.0 on Colab):**
   - **Track 1 — Pan-Mediterranean TBox Enrichment:** Query **OpenAlex API** (free, CC0) for 20–30 open-access papers across North & South Mediterranean aquifers (Tunisia, Morocco, Spain, France, Greece, Italy, Egypt). Run structured JSON extraction to mine `(LandUse/Practice) --[relation + polarity]--> (WaterRisk)` axioms; you manually validate each candidate (report Precision & Acceptance Rate) and commit approved DOI-cited axioms to `lulcw-med-causal.ttl`.
   - **Track 2 — Quantitative ABox Extraction Benchmark:** Run the same model over BRGM/SIERM documents and score exact/relaxed P/R/F1 against your **32 curated statements** in `configs/exchange_evidence.csv`.
4. **KG Routing Upgrades & Persisted Oxigraph Store:**
   - Add SHACL-AF rules deriving **`OverlyingLeakageInfluence`** (via `lulcw:overlies` local polygon witness) and **`RegionalOutcropInfluence`** so **0 of 33 core wells are weather-blind** in Arm D.
   - Add basin-matched **`CanalReturnInfluence`** (hard `≥ 0` sign where BRGM measured/traced, e.g., `718BP02 / C2-1`; soft prior elsewhere).
   - Persist the released KG into a disk-backed **`pyoxigraph.Store(path)`** (`< 50 ms` SPARQL queries, 50× faster than re-parsing Turtle!) and generate HTML documentation with **pyLODE**.

---

### 4.3 Neuro-Symbolic Model Reboot: **Hybrid-GNN v2**

```
            LULC-Water KG v1.0 (SPARQL → PyG HeteroData, equivalence-tested)
                                        │
                                        ▼
 ┌───────────────────────────────────────────────────────────────────────────────┐
 │ 1. HETEROGENEOUS GNN PARAMETER ENCODER (PyG HeteroConv / GATv2Conv)           │
 │    Nodes: Well · AquiferUnit · Facility · WeatherCell · Gauge · BasinCanal    │
 │    Edges: monitors · overlies · sameUnitNear · pumpsFrom · recharges · canal  │
 │    Reads ONLY static KG facts (depth, CQ14 confinement, stack, pump share,    │
 │    Sentinel-2 irrigated share, river/canal type) — NEVER dynamic stresses!    │
 │    Outputs per well (in well-SD units!):                                      │
 │      • FlexModel soil bucket params (S_max, k_evap, gamma, karst bypass beta) │
 │      • Fast + slow double-Gamma kernels (amax = 104 weeks, K = 312–416 wk)    │
 │      • Hard-signed gains G_r (±softplus → 0.0% physical sign violations!)     │
 │    Split Regularization: strong unit shrinkage on (a, n, S_max), weak on G_r  │
 └──────────────────────────────────────┬────────────────────────────────────────┘
                                        │
                                        ▼
 ┌───────────────────────────────────────────────────────────────────────────────┐
 │ 2. DIFFERENTIABLE MONOTONE PHYSICS LAYER (Exact Additive Attribution!)        │
 │    • Smooth monotone root-zone bucket: rain, ETP ─► S(t) ─► R_nl(t) [∂/∂P≥0] │
 │    • Causal FFT convolutions:                                                 │
 │        + G_rch_loc  * (k_fast/slow * R_nl_local)       [≥ 0]                  │
 │        + G_rch_ind  * (k_slow      * R_nl_over/reg)    [≥ 0]                  │
 │        - G_pump_att * (k_pump      * P_attributed)     [≤ 0] (2012+ masked!)  │
 │        - G_pump_un  * (k_pump      * P_unattributed)   [≤ 0] (2012+ masked!)  │
 │        + G_river    * (k_riv       * Q_river)          [≥ 0 where eligible]   │
 │        + G_canal    * (k_can       * Q_canal_basin)    [≥ 0 where measured]   │
 │    • Auto-centered anomaly (kills LWO d_m = 0 bug!):                          │
 │        ŷ_i(t) = Σ_r [ c_ir(t) − mean_{train_forcing}(c_ir) ]                  │
 │    • Optional row: Bounded Monotone Residual (positive-weight MLP, ≤ 0.20 sd) │
 └──────────────────────────────────────┬────────────────────────────────────────┘
                                        │
                     ┌──────────────────┴──────────────────┐
                     ▼                                     ▼
          Weekly Head & SGI Class               Exact Additive Attribution
      (0% violations, strong R1 & R2!)        (One unified model — no B2conv!)
```

**Why every upgrade is necessary:**
- **Auto-centering + `--gain-units sd` + 2-stage GNN training** (Stage A: fit `HeteroGNN` with `delta = 0` so the GNN *must* learn from KG facts & unit/neighbor messages; Stage B: small regularized `delta_G` refinement on training wells) → rescues LWO (`R2`) from `-1.875` and makes `B vs A` & `D vs C` transfer genuinely informative!
- **Differentiable Monotone `FlexModel` + Double-Gamma (`amax = 104 wk`)** → captures soil-moisture saturation, dry-soil ET cutoff, and karst conduit flashiness (fixing Karst `-1.71` NSE and `+1.46 m` bias!) while keeping `∂head / ∂rain ≥ 0` by mathematical construction!
- **Imputed-Era Pumping Reliability Masking** → learns climate/recharge across full `2005–2019` (15 years, `1990–2004` warm-up!) while detaching/masking pumping gradients on `2005–2011` (100%-fake pumping) so only real BNPE years (`2012–2019`) calibrate pumping gains — unlocking the `f50` `+0.226` / `+0.371` gain without losing 7 years of weather!
- **Split Regularization + Cosine Annealing to Convergence** → pools physical kernel parameters strongly by `AquiferUnit` while letting `sd`-scaled gains vary per well, converging cleanly in **one unified model** (no more awkward accuracy-model vs explanation-model split!).
- **Fair Black-Box Competitor:** Upgrade the black-box graph baseline to a true **PyG `HeteroConv` (`GATv2Conv`/`RGCNConv`) + Gated TCN/GRU** on the exact same `v5` KG, beside `lstm_tuned`, `stgnn_tuned`, `Pastas`, and `Chronos-2`.

---

### 4.4 Explanations (`SO4 / CQ10`) & Interactive GIS Dashboard (`SO5 / CQ16`)

- **Explanations & XAI (`SO4 / CQ10`):**
  - Materialise every run, simulated head, SGI class, driver contribution, cited KG influence, and FR/EN sentence into `lulcw-xai` RDF validated by all 6 SHACL negative-control shapes.
  - Re-run the **3 flagship case studies** (`NYLS-1` summer 2024 Pliocene rise vs avg & vs 2023; 2023 drought drop in Pliocene + Karst; `MILLAS C2-1` Têt canal cut) + median/worst rule-selected wells.
  - Run **Captum Integrated Gradients** and **PyG GNNExplainer** on the black-box `Hetero-STGNN` → quantitative **Fidelity+ / Fidelity− / Deletion Curves** (Hybrid-GNN v2 vs Black Box) + **Adebayo Randomisation Sanity Check** (trained D vs shuffled weights vs rewired E).
  - Add **counterfactual mitigation explanations** directly answering `sujet.docx` (*"Cutting pumping at boreholes X/Y by 15% raises NYLS-1 by +Δh m"*).
- **Interactive 4-Tab GIS Dashboard (`SO5 / CQ16` — Streamlit + Folium/PyDeck + Plotly + Persisted Oxigraph + Offline HTML Backup):**
  1. **Hydrogeological Knowledge Map (Roussillon + Manouba Switcher):** Interactive aquifer/well map, SGI drought alert colors, BD LISA stack & CQ14 confinement popup, Sentinel-2 `ProbablyIrrigatedParcel` polygons (`CQ15`), optional nitrate (`NO3-`) status layer.
  2. **Causal Explanation Explorer (`CQ10`):** Hydrograph + stacked exact driver contributions + FR/EN rule-checked explanation + instant (`<50 ms`) SPARQL provenance table.
  3. **Semantic Intelligence Query Console (`CQ1–CQ15`):** Natural-language query cards executing live SPARQL on BOTH Roussillon (`lulcw-fr-profile`) and Manouba (`lulcw-tn-profile`).
  4. **What-If Mitigation Simulator (`CQ16`):** Interactive sliders for crop transition (switching thirsty orchards/vegetables to lower-`Kc` crops / drip irrigation), pumping cuts, and canal flows → live Hybrid-GNN v2 replay showing on the map **where changes raise aquifer X the most**, with seed-spread uncertainty & caveats displayed honestly!

---

## 5. Verified 100% Free & Open Resource Registry

Every resource below was verified on **2026-11-25**. Total out-of-pocket cost = **€0** (using your existing Google Colab Pro balance of **165.3 units** + free Google Earth Engine research account + free open APIs/packages).

| Category | Resource | Verified Access / URI / Endpoint | Licence & Cost | Role in Project |
|---|---|---|---|---|
| **French Open Water Data** | **Hub'Eau** (`niveaux_nappes`, `prelevements`, `hydrometrie`, `qualite_nappes`) | `https://hubeau.eaufrance.fr/api/` | Etalab Open Licence 2.0 · **Free** | Piezometers, BNPE pumping, river & canal (`is_canal=True`) gauges, stations & optional nitrate (`1340`) |
| **French Borehole Depths** | **BRGM InfoTerre OGC WFS (BSS)** | `https://infoterre.brgm.fr/` (OGC WFS) | Etalab Open Licence 2.0 · **Free** | Borehole total depths (`profondeur_totale`) & `bss_id` spatial enrichment for CQ2 |
| **French Climate & Soil** | **Météo-France SIM2 (SAFRAN-ISBA)** | `data.gouv.fr` / OVH S3 (`safran.py --start 1990`) | Etalab Open Licence 2.0 · **Free** | Daily rain, ETP, EVAP, PE, DRAINC, SWI, T back to 1958 (pull `1990–2026`) |
| **French Crops & Geology** | **IGN RPG (2015–2025), BD TOPO, BD LISA v3** | `data.geopf.fr` / `bdlisa.eaufrance.fr` | Etalab Open Licence 2.0 · **Free** | Parcels, hydrographic network, 3D aquifer stacks (already cached!) |
| **Satellite & Global Data (Roussillon + Manouba!)** | **Google Earth Engine** (`COPERNICUS/S2_SR_HARMONIZED`, `ESA/WorldCover/v200`, `ECMWF/ERA5_LAND/DAILY_AGGR`, optional `COPERNICUS/S1_GRD`) | `earthengine.google.com` | **Free** for non-commercial research/education | Sentinel-2 NDVI+NDMI (`CQ15`) on Roussillon & Manouba + global land cover & ERA5-Land climate for zero-email Manouba KG! |
| **Pan-Med Ontologies (New + Existing)** | **AGROVOC** (`aims.fao.org/aos/agrovoc/`), **SAREF4WATR** (`saref.etsi.org/saref4watr/`), **SAREF4AGRI** (`saref.etsi.org/saref4agri/`), **CORINE SKOS** (`w3.org/2015/03/corine#`), **ENVO** (OBO), **GEMET** (EEA), **SWEET** (ESIP), **INSPIRE**, **GWML2/HyFO**, **HY_Features**, **W3C SOSA/PROV/TIME/SKOS/GeoSPARQL** | Official RDF/OWL/Turtle endpoints (cached locally via MIREOT) | CC BY 4.0 / BSD-3-Clause / CC0 · **Free** | Pan-Mediterranean interoperability across North & South Med (`SO1`) |
| **Crop Alignment Benchmark** | **EuroCrops HCAT** (`csvs/country_mappings`) | `https://github.com/maja601/EuroCrops` | **CC BY-SA 4.0 · Free** | Expert French RPG → HCAT gold standard + English/botanical aid for AGROVOC |
| **Open-Access Literature** | **OpenAlex API** (+ HAL, Copernicus HESS, MDPI OA) | `https://api.openalex.org/` (`pyalex`) | **CC0 metadata · Free** (no paid key) | Discover & retrieve 20–30 open-access pan-Mediterranean papers for Track 1 extraction |
| **Local Open LLM** | **`Qwen/Qwen2.5-7B-Instruct`** (HuggingFace) | `huggingface.co/Qwen/Qwen2.5-7B-Instruct` | **Apache 2.0 · Free** | Runs on Colab T4/L4 for OntoAligner LLM matcher + 2-Track Paper Extraction (zero API cost!) |
| **KG & Semantic Tools** | `rdflib`, `pyoxigraph` (RocksDB disk store), `pyshacl`, ROBOT (HermiT/ELK), OOPS!, **`pyLODE`**, `ontoaligner` | PyPI / GitHub | BSD / MIT / Apache 2.0 · **Free** | Modular OWL reasoning, validation, `<50 ms` SPARQL, HTML ontology docs, alignment |
| **ML, XAI & Dashboard** | PyTorch, **PyTorch Geometric (`HeteroData`, `HeteroConv`, `GATv2Conv`, `GNNExplainer`)**, **Captum** (Integrated Gradients), `pastas`, `chronos-forecasting`, **Streamlit**, **Folium / PyDeck**, **Plotly** | PyPI | BSD / MIT / Apache 2.0 · **Free** | Hybrid-GNN v2, black-box Hetero-STGNN, XAI faithfulness, 4-tab GIS dashboard |

---

## 6. Strictly Ordered, Gate-Checked Master Roadmap *(Excluding Paper Writing)*

> **How to use this roadmap:** Never jump to the next phase until **every checkbox in the current phase's Exit Gate passes**. That guarantees every upstream file, hash, ontology release, and model tensor stays 100% clean, reproducible, and bug-free.  
> **Two pacing options:** Follow all steps `R0 → R7` (**Track A — Full Reboot, ~7–9 weeks, ~55–75 Colab units**). If your defence date turns out to be very early, skip only items marked *(Optional)* and keep `dataset_v4` for Roussillon while applying the R3 model fixes (**Track B, ~4 weeks**).

---

### Phase R0 — Lock & Close Milestone 1 (`v4 / Hybrid v1`) · *2 days · Laptop only*
**Why first:** Preserves your entire pre-registered `analysis-plan-v2` work cleanly before any `v5` changes begin, giving a rock-solid before/after baseline.

- **Step 0.1:** Run `PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m src.analysis.arms_report` → generates `docs/results_arms_v4.md`.
- **Step 0.2:** Generate Phase 4 v1 summary figures (`T58`) and record the complete RQ1/RQ2 reading in `docs/notes/step14_phase4.md`.
- **Step 0.3:** Commit and create git tag **`phase4-v1-frozen`**.
- **✅ Gate R0 (Must Pass Before R1):** `docs/results_arms_v4.md` exists with 0 pending primary contrasts, `results/v4/` is frozen untouched, git tag `phase4-v1-frozen` pushed.

---

### Phase R1 — Free Open Data Upgrade (`dataset_v5`) & Satellite Pull (Roussillon + Manouba) · *1.5–2 weeks · Laptop + GEE*
**Pre-requisite:** Gate R0 passed + Assil's free Google Earth Engine research account activated.  
**Why before Ontology & Modeling:** Every downstream KG rule (`CQ15`, basin canals, BSS depths) and ML tensor (`1990` warm-up, validated 2024–25 heads) depends on a locked, hashed `dataset_v5`.

- **Step 1.1 — Climate & Hydro-Data Refresh:**
  - Pull SAFRAN `1990–1999` (`python -m src.ingest.safran --start 1990`) for a 15-year real warm-up.
  - Pull fresh dated snapshots of Hub'Eau `niveaux_nappes` (newly validated 2024–25 weeks!) and `prelevements` (check if BNPE 2025 is published!).
  - *(Optional)* Pull Hub'Eau `qualite_nappes/analyses` (`code_parametre=1340`, `NO3-`) for dept-66 nitrate context; check adjacent Aude (`dept 11`) piezometers on shared Corbières/Agly units.
- **Step 1.2 — Basin-Split Canals & Gauged Canal Flows:**
  - Spatially assign all 181 plain surface canal intakes (`pumping_points.parquet`) to **Têt / Agly / Tech** basins using BD TOPO / Sandre polygons.
  - Audit & assemble real weekly canal-gauge series from `data/raw/hubeau_hydro/qmnj/` (`is_canal=True`) as an observed within-year canal timing profile (independent of `ETP - rain`!).
- **Step 1.3 — BRGM InfoTerre WFS BSS Borehole Depth Enrichment:**
  - Query BRGM's open InfoTerre WFS BSS layer for `dept 66` boreholes (`profondeur_totale`, `bss_id`), spatially match to BNPE groundwater points (exact BSS + conservative proximity check), and re-run `src/kg/pump_attribution.py` measuring exact coverage & precision gains.
- **Step 1.4 — Google Earth Engine Pull (Roussillon + Manouba, Tunisia):**
  - **Roussillon:** Export per-RPG-parcel summer (Jun–Aug, 2017–2025) `COPERNICUS/S2_SR_HARMONIZED` NDVI & NDMI medians; compute within-crop-class, within-cell anomalies; validate independently with the **2022→2023 canal-cut diff-in-diff** + Agreste census.
  - **Manouba (Tunisia):** Export `COPERNICUS/S2_SR_HARMONIZED` summer NDVI & NDMI (2017–2025) + `ESA/WorldCover/v200` cropland polygons + `ECMWF/ERA5_LAND/DAILY_AGGR` precipitation/temperature/PET for the Manouba phreatic aquifer bbox.
- **Step 1.5 — Build & Audit `dataset_v5`:**
  - Add `"v5"` to `src/dataset/build.py` (`forcing_start: 1990-01-01`, refreshed validated heads, basin-split canals, enriched BSS attribution, Sentinel-2 parcel summaries, optional nitrate table), log every pull in `data/README.md`.
- **✅ Gate R1 (Must Pass Before R2):**
  - Cold-start rebuild of `dataset_v5` reproduces identical hashes;
  - `test_pumping_conservation.py`, `test_regime_boundaries.py`, and placeholder mask tests 100% pass;
  - Basin-canal series & gauged-canal correlation with climatic deficit reported;
  - Sentinel-2 2022→2023 canal-cut validation statistics logged (or heuristic status explicitly documented).

---

### Phase R2 — Pan-Mediterranean Meta-Ontology (`lulcw` v1.0), Alignments (`SO1`) & 2-Track Paper Extraction · *1.5–2 weeks · Laptop + ~10 Colab GPU units*
**Pre-requisite:** Gate R1 passed.  
**Why before Hybrid-GNN v2:** The upgraded KG (`overlies` leakage, regional outcrop, basin canals, `CQ15`, `CQ10`) generates the exact `HeteroData` graph tensors that Hybrid-GNN v2 trains on!

- **Step 2.1 — 2-Track Paper Extraction (`sujet.docx` Phase 1):**
  - Query **OpenAlex API** (free) to assemble 20–30 open-access pan-Mediterranean LULC-Water papers (Tunisia, Morocco, Spain, France, Greece, Italy, Egypt).
  - Run local **`Qwen/Qwen2.5-7B-Instruct`** on Colab (structured JSON output):
    - **Track 1 (TBox):** Extract Mediterranean causal triples `(Driver/Practice) --[relation, polarity]--> (WaterRisk)` with DOI & verbatim quote; Assil reviews & accepts/rejects → record Precision & Acceptance Rate.
    - **Track 2 (ABox Benchmark):** Run on BRGM/SIERM texts and score exact/relaxed P/R/F1 against the **32 statements** in `configs/exchange_evidence.csv`.
- **Step 2.2 — Refactor `lulcw` v1.0 Into 2 Layers (Mediterranean Core + Country Profiles):**
  - Split `lulcw.ttl` into the **7 country-agnostic Core modules** (`core`, `hydro`, `lulc`, `eo`, `med-causal`, `causal`, `xai`) + **2 thin adapter profiles** (`lulcw-fr-profile.ttl`, `lulcw-tn-profile.ttl`).
  - Prune the 23 unused terms; populate `lulcw-med-causal.ttl` with the validated Track-1 axioms (DOI-cited); complete `CQ10`, `CQ15`, `CQ16` terms & shapes.
  - Add SHACL-AF rules for **`OverlyingLeakageInfluence`** (via `lulcw:overlies`), **`RegionalOutcropInfluence`**, **basin-split `CanalReturnInfluence`** (hard `≥ 0` on measured `718BP02`), and **`ProbablyIrrigatedParcel` (`CQ15`)**.
- **Step 2.3 — Expanded Pan-Mediterranean Alignments (`SO1`):**
  - Add MIREOT imports, alignment files, and HermiT-tested ledger rows for **SAREF4WATR**, **SAREF4AGRI**, **CORINE SKOS**, **ENVO**, **GEMET**, and deeper **SWEET**.
  - Download **EuroCrops HCAT** French mapping CSV (`CC BY-SA 4.0`) + finalize Assil's **AGROVOC gold set** (`lu_agrovoc_gold.csv`, accelerated by HCAT English/botanical labels, preserving the 30-code blind subset!).
  - Run **OntoAligner** (lexical + dense retrieval + `Qwen2.5-7B-Instruct` on Colab) on BOTH **RPG → HCAT** and **RPG → AGROVOC** → unweighted & local-area-weighted P/R/F1 tables.
- **Step 2.4 — Instantiate Both KGs (`Roussillon v5` + `Manouba tn`) in Persisted Oxigraph + Export `HeteroData`:**
  - Build Roussillon `v5` KG + Manouba `tn` KG (Sentinel-2 + WorldCover + ERA5-Land + published Manouba aquifer facts) into disk-backed **`pyoxigraph.Store`**.
  - Compute the exact **France → Tunisia Ontology Reuse %** (classes, properties, SHACL rules reused unchanged).
  - Run `src/kg/export.py` (`v5` Arms `C`, `D`, `E`, `F` + equivalence test) and generate HTML ontology docs via **`pyLODE`**.
- **✅ Gate R2 (Must Pass Before R3):**
  - ROBOT HermiT consistency = **0 errors**, OOPS! = **0 critical pitfalls**, entailment ledger **100% pass**;
  - SHACL validation = **0 violations** on BOTH Roussillon `v5` and Manouba `tn` KGs;
  - All **16 CQ test suites** pass (including `CQ10`, `CQ15`, `CQ16`), Oxigraph queries execute in **`< 1 s`**;
  - Export equivalence test passes, AND **`0 / 33` core wells are weather-blind in Arm D**;
  - SO1 alignment P/R/F1 tables & 2-Track extraction P/R/F1 tables generated and committed.

---

### Phase R3 — Pre-Register `analysis-plan-v3`, Build **Hybrid-GNN v2** & Verify on Twin v2 · *2 weeks · Colab L4/v5e1 (~20–25 units)*
**Pre-requisite:** Gate R2 passed.  
**Why Twin before Real Data:** Proves that **one unified Hybrid-GNN v2** actually fixes the LWO bug, nonlinear karst dynamics, and accuracy-vs-stability trade-off on known synthetic truth *before* touching real `v5` drought scores!

- **Step 3.1 — Pre-Register & Tag `analysis-plan-v3`:**
  - Document the exact `v5` ablation ladder, Hybrid-GNN v2 architecture, `2012+` pumping reliability rule, and upgraded black-box competitor; commit & tag **`analysis-plan-v3`**.
- **Step 3.2 — Implement Hybrid-GNN v2 (`src/models/hybrid_gnn.py`) & Upgraded Black-Box (`Hetero-STGNN`):**
  - Build: auto-centered anomalies, `--gain-units sd`, differentiable monotone **`FlexModel` root-zone bucket**, fast+slow double-Gamma (`amax = 104` wk), two-channel KG recharge (`local` + `overlying/regional`), basin-split canals, **PyG `HeteroConv/GATv2` parameter encoder** (with 2-stage `delta=0 → regularized delta` transfer training), `2005–2011` imputed-pumping gradient masking, split regularization (`λ_kernel > λ_gain`), and CosineAnnealingLR convergence + optional bounded monotone residual row.
  - Build upgraded black-box **PyG `Hetero-STGNN`** (`HeteroConv` + Gated TCN/GRU) reading the exact same `v5` `HeteroData` graph.
- **Step 3.3 — Run Upgraded Semi-Synthetic Twin v2:**
  - Extend `src/models/twin.py` with nonlinear soil-moisture recharge, overlying leakage, basin canals, and 2005–2011 imputed pumping; test Hybrid-GNN v2 on synthetic worlds (`R1` and `R2 LWO`).
- **✅ Gate R3 (Must Pass Before R4):**
  - Finite-difference monotonicity unit test = **`0.0%` sign violations** across random parameters & stresses (including through `FlexModel` and bounded monotone residual!);
  - Exact checkpoint replay matches forward pass to `< 1e-5 m`;
  - LWO unit test proves `mean_{train}(pred) = mu_i` on held-out wells with zero head leakage;
  - Twin v2 confirms unified Hybrid-GNN v2 recovers pumping better than Arm C (>80% worlds) with tight seed agreement AND strong LWO transfer!

---

### Phase R4 — Run `v5` Real-Data Benchmarks, Ablation Ladder & Contrasts · *1–1.5 weeks · Colab L4/v5e1 (~25–35 units)*
**Pre-requisite:** Gate R3 passed.  
**Why ordered as an ablation ladder:** Shows reviewers *exactly* how much each individual fix contributed from `v4 Hybrid v1` → `v5 Hybrid-GNN v2`!

- **Step 4.1 — Reference Baselines on `dataset_v5`:**
  - Re-run Pastas reference, `lstm_tuned`, `stgnn_tuned`, upgraded black-box **`Hetero-STGNN` (distance vs KG edges)**, and `Chronos-2` on `dataset_v5` (same machine per contrast!).
- **Step 4.2 — Hybrid-GNN v2 Controlled Ablation Ladder (Colab):**
  - Run step-by-step ladder (`10 seeds` each, same runtime):
    1. `v1` linear baseline on `v5` →
    2. `+ LWO auto-centering & gain-units sd` →
    3. `+ overlying/regional KG recharge & basin canals` →
    4. `+ monotone FlexModel & double-Gamma (amax=104)` →
    5. `+ 2012+ pumping reliability weighting & split regularization` →
    6. `+ PyG HeteroGNN parameter encoder` (**Main Hybrid-GNN v2**) →
    7. `+ bounded monotone residual` (sensitivity row).
- **Step 4.3 — Full RQ1 / RQ2 / Robustness Matrix on Hybrid-GNN v2:**
  - Arms `A, B, C, D, E_degree, E_distance, F_random, F_complete` across `R1`, `R2 (LWO)`, `R3 (f25, f50)`, and `Refit`;
  - `RQ2` (`none / soft / hard`) with real-data violation rates;
  - 3 pumping reconstructions (`r1, r2, r3`) + pump-link policies (`confident-only / main / all-links`) + **`CQ15` `ProbablyIrrigatedParcel` ablation**.
- **Step 4.4 — Official Scoring & `v4` vs `v5` Comparison Report:**
  - Run `PFE_DATASET=v5 .venv/bin/python -m src.analysis.arms_report` → `docs/results_arms_v5.md` + per-aquifer-group before/after table (`v4 Hybrid v1` vs `v5 Hybrid-GNN v2`) + figures.
- **✅ Gate R4 (Must Pass Before R5):**
  - `10/10` seeds complete for every primary arm; `0` support mismatches; same-arm bands computed;
  - `0.0%` sign violations verified on every hard-constrained run;
  - Every checkpoint replayable (`replay_contribs` passes `< 1e-5 m`).

---

### Phase R5 — Full Explanations, Black-Box XAI Benchmark & Sanity Checks (`SO4 / CQ10`) · *1 week · Laptop + ~10 Colab GPU units*
**Pre-requisite:** Gate R4 passed.  
**Why here:** Explanations must run on the final, replay-verified Hybrid-GNN v2 and black-box `Hetero-STGNN` checkpoints.

- **Step 5.1 — Materialise `lulcw-xai` RDF Result Graph (`CQ10`):**
  - Build `src/explain/result_graph.py` exporting `ModelRun`, `SimulatedHead`, `DriverContribution`, `ExplanationStatement`, and cited `Influence` paths into Oxigraph; run all 6 CQ10 SHACL negative-control tests.
- **Step 5.2 — Audited FR/EN Case Studies & Counterfactual Mitigations:**
  - Generate FR/EN reports for the **3 flagship case studies** (`NYLS-1` summer 2024 Pliocene rise vs avg & vs 2023; 2023 extreme drought drop in Pliocene + Karst; `MILLAS C2-1` Têt canal cut) + median/worst rule-selected wells.
  - Generate quantitative **what-if mitigation explanations** (e.g., `-15%` Pliocene drinking-water cut, `2022` Têt canal restoration, crop-shift demand cut) with 10-seed uncertainty ranges.
- **Step 5.3 — Black-Box XAI Comparison & Adebayo Sanity Check:**
  - Run **Captum Integrated Gradients** and **PyG GNNExplainer** on `Hetero-STGNN` (Colab GPU), aggregated by KG node type & relation.
  - Compute **Fidelity+ / Fidelity− / Deletion Curves** comparing Hybrid-GNN v2 (exact!) vs Black-Box XAI.
  - Run **Adebayo Randomisation Sanity Check**: prove explanations change substantially when comparing trained Arm D vs weight-shuffled Arm D vs rewired Arm E.
- **✅ Gate R5 (Must Pass Before R6):**
  - CQ10 SHACL = **0 violations**;
  - Flagship `NYLS-1` & `C2-1` case studies reflect physically valid, sign-consistent mechanisms (not broken withholds!);
  - Quantitative Fidelity+/− table & Adebayo sanity-check plot committed.

---

### Phase R6 — Interactive GIS Decision-Support Dashboard (`SO5 / CQ16`, Roussillon + Manouba) · *1 week · Laptop*
**Pre-requisite:** Gate R5 passed (persisted Oxigraph store + CQ10 RDF + Hybrid-GNN v2 replay all verified).

- **Step 6.1 — Build 4-Tab Interactive Streamlit GIS Prototype (`src/dashboard/app.py`):**
  - **Tab 1:** Interactive Map (Roussillon + Manouba site switcher; wells, SGI alert colors, BD LISA stack & CQ14 confinement, Sentinel-2 `ProbablyIrrigatedParcel`, optional nitrate overlay).
  - **Tab 2:** Causal Explanation Explorer (`CQ10` hydrograph, stacked contributions, FR/EN explanation, live `<50 ms` SPARQL provenance).
  - **Tab 3:** Semantic Intelligence Queries (`CQ1–CQ15` live SPARQL cards on both Roussillon and Manouba).
  - **Tab 4:** What-If Mitigation Simulator (`CQ16` — interactive crop-transition, pumping-cut & canal-flow sliders driving live Hybrid-GNN v2 replay & spatial impact map!).
- **Step 6.2 — Offline Defence Backup & Explainer Refresh:**
  - Export a zero-server static HTML/Leaflet snapshot of key maps, case studies, and scenarios; update `docs/explainer/index.html` with the `v4 → v5` story.
- **✅ Gate R6 (Must Pass Before R7):**
  - All 4 tabs run smoothly locally (`< 1 s` SPARQL latency, live `CQ16` scenario updates reproducible);
  - Offline HTML backup opens cleanly with network disabled.

---

### Phase R7 — Final Technical Lock & Independent Post-Freeze Confirmation · *3–4 days · Laptop*
**Pre-requisite:** Gate R6 passed.

- **Step 7.1 — Independent Post-Freeze Check:** Pull the newest Hub'Eau ADES observations recorded *after* `dataset_v5` was frozen and score frozen `v4` & `v5` checkpoints on those genuinely unseen weeks.
- **Step 7.2 — Master Quality Gate & Reproducibility Package:**
  - Run unified test runner (`scripts/run_tests.py`: all pytest modules, monotonicity tests, ROBOT HermiT, OOPS!, SHACL on Roussillon + Manouba, all 16 CQs, equivalence test, checkpoint replay).
  - *(Conditional)* If private Manouba piezometer CSVs arrive by this point, drop them into `lulcw-tn-profile.ttl` for an added qualitative time-series transfer demo.
  - Lock `uv.lock`, `configs/exp/*.yaml`, `pyLODE` HTML ontology docs, and tag **`thesis-technical-freeze`**.
- **✅ Gate R7 (Final Technical Sign-Off):** 100% green test suite from cold start, clean git tag, all artefacts ready for thesis & *Environmental Modelling & Software* paper writing.

---

## 7. Appendix A — Read-Only Forensic Audit Record (2026-11-25)

All **[new]** figures were computed read-only from `commit 2950148` (`PFE_DATASET=v4`) without modifying code or results:

1. **Per-group & paired Phase 4 diagnostics:** `results/v4/<run>/metrics_per_well.csv` (`split == 'test_drought'`, `variant == 'all'`, `task == 'simulation'`, `core == True`, 33 core wells) joined with `dataset_v4/wells.parquet` and `export_v4_main/edges_D.parquet`.
2. **RQ2 (`B4`) violation rates:** Concatenated `params_seed_0..9.csv` across `p4_B4_D_*` on the 33 core wells; counted wrong-signed gains for `recharge`, `pumping`, `pumping_unattributed`, and `river_constrained`.
3. **LWO (`R2`) intercept & `delta` audit:** `p4_B2_D_r1_lwo/fold_0/params_seed_0.csv` (`mean |d_m| = 1.044 m` on 51 trained wells, `0.000 m` on all 13 held-out wells); `p4_B1_B_r1_lwo/fold_0/seed_0.pt` (`RMS(delta) = 1.2555` vs `RMS(static_map(Z)) = 0.7261`, `gain_scale = 1.0`); post-hoc training-mean centering rescored via `src.models.evaluate.score`.
4. **B8 residual share:** `p4_B8_{B,C,D}_r1/contrib_seed_0.parquet` (`2022-05-01..2025-11-30`), `Var(residual) / Var(total sim)` = `0.062` median (`0.308` max) for `p4_B8_D_r1`.
5. **Live Phase 5 reports:** `src.explain.report` on `p4_B2conv_D_r1` (`--sibling p4_B2conv_D_r2 p4_B2conv_D_r3`) for `10964X0119/NYLS-1` (`2024-06-01:2024-09-30` vs avg year & vs `2023-06-01:2023-09-30`) and `10906X0039/C2-1` (`2023-06-01:2023-09-30`).
6. **Ontology France-lock audit:** Parsed `ontology/lulcw.ttl` (`rdflib`): 86 classes, 210 properties; **49 terms** reference French agency schemas (`bdlisa`, `bnpe`, `bss`, `rpg`, `safran`, `sandre`, `ades`, `bdtopo`, `carthage`, `wfd`); `configs/lu_agrovoc_gold.csv` = `0 / 198` filled; `docs/ontology_term_usage.md` = `413` total terms, `23` unused.
7. **Free-resource verification (2026-11-25):** Confirmed open licences and active endpoints for SAREF4WATR & SAREF4AGRI (ETSI BSD-3-Clause), CORINE SKOS (`http://www.w3.org/2015/03/corine#`), ENVO (CC0), GEMET (CC BY 4.0), EuroCrops HCAT (`github.com/maja601/EuroCrops`, CC BY-SA 4.0), Google Earth Engine non-commercial research collections (`COPERNICUS/S2_SR_HARMONIZED`, `ESA/WorldCover/v200`, `ECMWF/ERA5_LAND/DAILY_AGGR`), OpenAlex API (CC0), `Qwen/Qwen2.5-7B-Instruct` (Apache 2.0), `pyLODE` (BSD), and BRGM InfoTerre WFS / Hub'Eau (Etalab 2.0).
