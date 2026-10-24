# Reading list: triage of `Articles/` and additions

Written 2026-10-13. Each identifier below was checked: the DOIs resolve on
doi.org and the arXiv IDs open the right title on arxiv.org.

**Updated 2026-10-23** (second external review, `docs/review_codex_response.md`):
- verdicts aligned with the decisions of 2026-10-23: no semantic loss, PiShield
  dropped, SGI accuracy reported but not the shortcut test
- four references added, checked on Crossref (§2, "Added 2026-10-23")
- the paper's claim is now about **simulation**, not forecasting

**Verdicts**
- **CORE**: read in full; it shapes a design choice or an experiment.
  Goes in the paper.
- **CITE**: skim the abstract, method and conclusion; cite it in related
  work or the thesis.
- **DROP**: out of scope for the paper. Keep the PDF only if the thesis
  background needs it.

The rule behind the verdicts: the paper's core claim is about **groundwater
level forecasting with an ontology-derived graph and constraints, tested for
reasoning shortcuts, with ontology-grounded explanations**. Every reference
must support one of those four words: graph, constraints, shortcuts,
explanations. The ontology and data-integration references also count.

---

## 1. Triage of the 28 PDFs in `Articles/`

### Axis A: Ontology alignment

| Paper | Verdict | Why |
|---|---|---|
| OntoAligner (Babaei Giglou et al., ESWC 2025), arXiv:2503.21902 | **CORE** | The tool we use. Read the API and the matcher families (lightweight, retrieval, LLM). |
| LLMs4OM (Babaei Giglou et al., 2024), arXiv:2404.10317 | CITE | It is the LLM matcher inside OntoAligner. Cite it when describing the LLM-based run. |
| Agent-OM (Qiang et al., PVLDB 18(3) 2024), doi:10.14778/3712221.3712222 | CITE | The state of the art in agentic matching. One sentence in related work; too heavy to run. |
| OAEI-LLM-T (Qiang et al., 2025), arXiv:2503.21813 | DROP | A benchmark of LLM hallucinations in matching. Only useful if alignment becomes the main contribution, which it should not. |

### Axis B: Water ontologies and knowledge graphs

| Paper | Verdict | Why |
|---|---|---|
| WHOW-KG | **CORE**, but **replace the PDF** | The folder has the 2023 arXiv preprint (2305.11051). Cite the peer-reviewed version: *Scientific Data* 2025, **doi:10.1038/s41597-025-04537-4**. It is our architecture pattern (a network of ontologies). |
| Baydaroğlu et al., *A Comprehensive Review of Ontologies in the Hydrology and Water Resources Domain* (EarthArXiv preprint) | CITE | Good map of which hydrology ontologies exist. The PDF says "not peer-reviewed". Look for a journal version before citing; otherwise cite it as a preprint. |

### Axis C: Earth observation

| Paper | Verdict | Why |
|---|---|---|
| WorldCereal (Van Tricht et al., *ESSD* 2023), doi:10.5194/essd-15-5491-2023 | CITE | Has a global **active-irrigation** layer. The RPG lacks irrigation, so this matters for the Tunisia transfer, where there is no RPG. |
| Prithvi-EO-2.0 (Szwarcman et al.), arXiv:2412.02732 | DROP | A 30 m HLS foundation model that needs a GPU and fine-tuning. AlphaEarth or TESSERA embeddings do the same job without training. One sentence at most. |
| GEO-Bench-2 (Simumba et al.), arXiv:2511.15658 | DROP | Benchmarks foundation models. We don't benchmark them. |
| *A Comprehensive GeoAI Review* (Boutayeb et al.), arXiv:2412.11643 | DROP | Too generic; no reviewer will expect it. |

### Axis D: Neuro-symbolic learning

| Paper | Verdict | Why |
|---|---|---|
| Marconato et al., *Not All Neuro-Symbolic Concepts Are Created Equal* (NeurIPS 2023), arXiv:2305.19951 | **CORE** | The reasoning-shortcut test is our validity check. Read sections 3–5 carefully. |
| Xu et al., *A Semantic Loss Function…* (ICML 2018), arXiv:1711.11157 | CITE (was CORE until 2026-10-23) | The foundational way to put logic in the loss. Superseded for us: the concepts are now continuous driver contributions, and the constraints are response signs (soft gradient penalties or monotone by construction), not logic over discrete states. Cite it in related work. |
| Xu et al., *Physics-aware Machine Learning…* (2023), arXiv:2310.05227 | **CORE** | Its taxonomy (data-guided / physics-informed / embedded / hybrid) is how we position the method. |
| Logic Tensor Networks (Badreddine et al., *AIJ* 2022), arXiv:2012.13635 | CITE | The fuzzy-logic alternative to the semantic loss. Cite it; don't implement it (the reference code is TensorFlow). |
| Acharya & Song, *Comprehensive Review of Neuro-symbolic AI…* (*AJSE* 2026), doi:10.1007/s13369-025-10887-3 | CITE (optional) | Intro-level survey; one citation for "NeSy for trustworthy AI". |
| van Krieken et al., *On the Independence Assumption…* (ICML 2024), arXiv:2404.08458 | DROP | About probabilistic NeSy over many discrete symbols. Not our setting. |

### Axis E: Spatio-temporal GNNs for water

| Paper | Verdict | Why |
|---|---|---|
| E3 Wu et al., *Forecasting Groundwater Level by Characterizing Multiple Spatial Dependencies…* (*JGR: Machine Learning and Computation* 2025), **doi:10.1029/2024JH000520** | **CORE** | Several adjacency matrices (distance, rainfall response, hydraulic, …) for a T-GCN, North China Plain. |
| Wu, Yao, Guo, Yang, He, Lancia & Zheng, *Graph Fourier deep learning for spatiotemporal and hydrogeological interpretation of groundwater levels in the Yellow River Basin* (*WRR* 61(11), e2025WR041215, 2025), **doi:10.1029/2025WR041215** | **CORE** (added 2026-10-20) | **The closest competitor.** According to its indexed abstract it embeds hydrogeological units as prior information in a graph model of 473 wells; read the full text to confirm. Position our claim against it: a graph and constraints generated from a formal knowledge graph, plus shortcut and faithfulness tests. **Correction:** on 2026-10-13 CLAUDE.md §10 replaced "WRR, graph Fourier, Yellow River" by the JGR:MLC paper, as if the first were a mistake. Both papers exist; this one was missing. |
| E8 Dai et al., *Incorporating Deep Learning Into Hydrogeological Modeling* (*JGR:MLC* 2025), doi:10.1029/2025JH000703 | **CORE** | Names the gaps: interpretability, physics consistency, benchmarks. The paper's introduction cites these gaps. |
| E6 HydroGAT (Sarkar et al., SIGSPATIAL 2025), doi:10.1145/3748636.3764172 | **CORE** | A heterogeneous hydrological graph with attention, the design template for our heterogeneous graph. It works on floods, not groundwater. |
| E4 Chen et al., STGCN-M (*Earth Sci. Informatics* 2025), doi:10.1007/s12145-025-01741-z | CITE, with caution | Reports STGCN RMSE ≈ 0.009 vs LSTM ≈ 0.9, a 100× gap. That points to a normalisation or leakage problem, so don't use it as a benchmark. Cite it only as an example of STGCN on wells. |

(E1, E2, E5 and E7 are missing from the folder. If they were dropped on
purpose, that's fine. Taccari et al. and Bai & Tahmasebi below fill the gap.)

### Axis F: Explainability

| Paper | Verdict | Why |
|---|---|---|
| F1 Clark et al., *XAI for Interpreting Spatiotemporal Groundwater Predictions* (*WRR* 2025), doi:10.1029/2025WR041303 | **CORE** | Groundwater XAI with SHAP. It is the baseline style of explanation that ours must beat in meaning. |
| F3 Azzolin et al., *Perks and Pitfalls of Faithfulness in … GNNs* (2024), arXiv:2406.15156 | **CORE** | Explains why GNN explanations must be checked for faithfulness, and which metric to use. |
| F2 Zounemat-Kermani & Kheimi, *XAI in Hydrology: A Review* (*WRM* 2026), doi:10.1007/s11269-025-04435-9 | CITE | Shows SHAP dominates the field and that XAI is rarely combined with physics, which is our gap. |
| F4 GLGExplainer (Azzolin et al., ICLR 2023), arXiv:2210.07147 | DROP | A global explainer for **graph classification**. Our task is node-level regression. |

### Axis G: Mediterranean domain

| Paper | Verdict | Why |
|---|---|---|
| G1 Costa et al., *Five Decades of Groundwater Change…* (*Sci. Total Environ.* 2025), doi:10.1016/j.scitotenv.2025.180925 | **CORE** | Mediterranean attribution of natural vs human drivers; the domain framing for the paper's introduction. |
| G4 Gargouri-Ellouze et al., Jebel Zaghouan karst (*Water* 2025), doi:10.3390/w17030407 | CITE (optional) | Only for the Tunisia demo and for the SGI drought index. |
| G2 Richa et al., nitrate vulnerability review (*ESPR* 2025), doi:10.1007/s11356-025-36694-9 | DROP | Nitrate, not levels. Future work. |
| G3 Chahid et al., nitrate deep learning (*Sci. Rep.* 2025), doi:10.1038/s41598-025-18996-7 | DROP | Nitrate and tabular data. Future work. |

**Result:** 11 CORE, 9 CITE, 8 DROP (28 papers; the WHOW-KG PDF should be
swapped for the journal version).

---

## 2. Papers and tools to add (all verified)

### Groundwater forecasting: baselines a hydrology reviewer will expect

| Reference | Why it matters |
|---|---|
| Collenteur et al., *Pastas: Open Source Software for the Analysis of Groundwater Time Series*, *Groundwater* 57(6) 2019, **doi:10.1111/gwat.12925** | The standard groundwater baseline: transfer-function noise models with rain, ET and pumping as inputs. Without it, a hydrology reviewer will reject the paper. |
| Wunsch, Liesch & Broda, *Groundwater level forecasting with ANNs: LSTM vs CNN vs NARX*, *HESS* 25 2021, **doi:10.5194/hess-25-1671-2021** | The reference deep-learning baseline for groundwater levels. |
| Heudorfer, Liesch & Broda, *On the challenges of global entity-aware deep learning models for groundwater level prediction*, *HESS* 28 2024, **doi:10.5194/hess-28-525-2024** | **Key paper for our story.** Static well features were used as *identifiers*, not as semantics. That is a shortcut, and our ontology features risk the same thing. It motivates our "semantic ablation" test. (A corrigendum exists; read it too.) |
| Kratzert et al., *Towards learning universal, regional, and local hydrological behaviors…* (EA-LSTM), *HESS* 23 2019, **doi:10.5194/hess-23-5089-2019** | The entity-aware LSTM. It is the global, non-graph baseline. |
| Taccari et al., *Spatial-temporal graph neural networks for groundwater data*, *Sci. Rep.* 14 2024, **doi:10.1038/s41598-024-75385-2** | **Closest analogue to our setting:** a multi-aquifer system with pumping, river and rain nodes in the graph, weekly data, masked loss for gaps. A predefined physical graph beat a learned graph by 25%. Code: github.com/mlttac/GroundwaterFlowGNN. |
| Bai & Tahmasebi, *Graph neural network for groundwater level forecasting*, *J. Hydrol.* 616 2023, **doi:10.1016/j.jhydrol.2022.128792** | First GNN for groundwater levels (adaptive adjacency). Cite it as the origin of the line of work. |
| Ansari et al., *Chronos-2: From Univariate to Universal Forecasting*, 2025, **arXiv:2510.15821** | A time-series foundation model, zero-shot with covariates. It is the modern baseline: if a 120M zero-shot model matches our GNN, we must say so. |
| Bloomfield & Marchant, *Analysis of groundwater drought building on the SPI approach* (SGI), *HESS* 17 2013, **doi:10.5194/hess-17-4769-2013** | The Standardised Groundwater Index. It turns levels into **discrete drought states** (the IPS classes of the BRGM bulletins). SGI accuracy is reported; since 2026-10-23 it is **not** the shortcut test (the concepts are the driver contributions). |

### Graph learning for time series

| Reference | Why |
|---|---|
| Cini et al., *Graph Deep Learning for Time Series Forecasting* (survey), **arXiv:2310.15978** | The best methodological overview, by the authors of the `tsl` library. |
| Cini, Marisca & Alippi, *Filling the G_ap_s* (GRIN, ICLR 2022), **arXiv:2108.00298** | Graph-based imputation. Our series have gaps, and 52% of the 2025 values are "Non qualifié". |
| Hu et al., *Heterogeneous Graph Transformer*, **arXiv:2003.01332** | The heterogeneous message-passing layer (`HGTConv` in PyG) for well / aquifer / abstraction / parcel nodes. |

### Knowledge-guided ML and constraints

| Reference | Why |
|---|---|
| Willard et al., *Integrating Scientific Knowledge with ML for Engineering and Environmental Systems*, *ACM Comput. Surv.* 55(4) 2022, **doi:10.1145/3514228** | The standard survey of knowledge-guided ML. Positioning. |
| Stoian et al., *PiShield: A PyTorch Package for Learning with Requirements*, IJCAI 2024, **doi:10.24963/ijcai.2024/1037** | Enforces linear-inequality constraints on continuous **outputs** by construction. **Dropped as a method on 2026-10-23:** our constraints are on response signs (how the output changes with a driver), not on output values. Cite it as related work. The hard variant is monotone by construction (Runje & Shankaranarayana 2023, arXiv:2205.11775, in the comparison table). |
| Marconato et al., *BEARS Make Neuro-Symbolic Models Aware of their Reasoning Shortcuts* (UAI 2024), **arXiv:2402.12240** | Mitigates reasoning shortcuts with ensembles. Cheap to apply once there is a GPU. |
| Bortolotti et al., *A Neuro-Symbolic Benchmark Suite for Concept Quality and Reasoning Shortcuts* (rsbench, NeurIPS 2024), **arXiv:2406.10368** | Gives the concept-quality metrics to report. |

### Ontology engineering

| Reference | Why |
|---|---|
| Babaei Giglou et al., *LLMs4OL: Large Language Models for Ontology Learning*, **arXiv:2307.16648** | For the subject's "textual extraction" step: getting Mediterranean concepts out of articles. |
| Caufield et al., *SPIRES* (OntoGPT), *Bioinformatics* 2024, **doi:10.1093/bioinformatics/btae104** | A practical tool for zero-shot extraction of triples from text into a given schema. |

### Earth observation (light use only)

| Reference | Why |
|---|---|
| Brown et al., *AlphaEarth Foundations*, **arXiv:2507.22291** | Annual 10 m, 64-d embeddings for 2017–2024 on Google Earth Engine. Already chosen. |
| *TESSERA: Temporal Embeddings of Surface Spectra…* (CVPR 2026), **arXiv:2506.20380** | Open-weights alternative: 128-d embeddings at 10 m from S1 and S2. Use it if Earth Engine access becomes a problem or a reviewer asks for open models. |

### Roussillon domain grounding

| Reference | Why |
|---|---|
| Dall'Alba, *Hydro-geological modeling of the Roussillon aquifer…*, PhD thesis, Univ. Neuchâtel 2023, **doi:10.35662/unine-thesis-3052** | The most detailed recent geological and hydrogeological model of **our** aquifer (Dem'Eaux Roussillon project, BRGM). Read the geology chapter before building the `overlies` edges. |

---

### Added 2026-10-20 (critical review, `docs/feedback.md` §6; each ID opened that day)

| Reference | Why |
|---|---|
| Collenteur et al., *Data-driven modelling of hydraulic-head time series: results and lessons learned from the 2022 Groundwater Time Series Modelling Challenge*, *HESS* 28, 2024, **doi:10.5194/hess-28-5193-2024** | 15 teams, Pastas to deep learning, simulating heads: the benchmark culture hydrology reviewers expect. |
| Chidepudi et al., *Training deep learning models with a multi-station approach and static aquifer attributes for groundwater level simulation*, *HESS* 29, 2025, **doi:10.5194/hess-29-841-2025** | French piezometers, global models with static attributes; models trained on clusters of similar series beat a model trained on all wells. The closest French deep-learning study. |
| Kirschstein & Sun, *The Merit of River Network Topology for Neural Flood Forecasting*, ICML 2024, **arXiv:2405.19836** | A domain graph (river network) gave a GNN no gain: the reason RQ1 needs no-graph, random-graph and Taccari-graph controls. |
| Topp et al., *Stream temperature prediction in a shifting environment: the influence of deep learning architecture*, *WRR* 59, 2023, **doi:10.1029/2022WR033880** | Explainable AI shows whether a graph model's learned spatial relations match physics. A template for RQ3/RQ4. |
| Jia et al., *Physics-guided recurrent graph model for predicting flow and temperature in river networks*, SDM 2021, **doi:10.1137/1.9781611976700.69** | The canonical "domain graph + physics loss" model. |
| Tsai et al., *From calibration to parameter learning*, *Nature Communications* 12, 2021, **doi:10.1038/s41467-021-26107-z** | Differentiable parameter learning: a network predicts the parameters of a process model (option in `docs/feedback.md` §5.5). |
| Shen et al., *Differentiable modelling to unify machine learning and physical models for geosciences*, *Nat. Rev. Earth Environ.* 4, 2023, **doi:10.1038/s43017-023-00450-9** | Positioning of hybrid differentiable models. |
| Brakenhoff et al., *Application of time series analysis to estimate drawdown from multiple well fields*, *Front. Earth Sci.* 10, 2022, **doi:10.3389/feart.2022.907609** | Pastas WellModel: one response scaled by distance for many pumping wells (`pastas_wellmodel`). |
| Ross, Hughes & Doshi-Velez, *Right for the Right Reasons: Training Differentiable Models by Constraining their Explanations*, IJCAI 2017, **doi:10.24963/ijcai.2017/371**, arXiv:1703.03717 | Origin of the phrase in our title and of input-gradient constraints (the soft constraints of RQ2). |
| Koh et al., *Concept Bottleneck Models*, ICML 2020, **arXiv:2007.04612** | What a "concept" is; supports treating driver contributions as concepts (RQ3). |
| Runje & Shankaranarayana, *Constrained Monotonic Neural Networks*, ICML 2023, **arXiv:2205.11775** | Monotone by construction: a hard way to enforce response signs (RQ2). |
| Kratzert et al., *HESS Opinions: Never train a Long Short-Term Memory (LSTM) network on a single basin*, *HESS* 28, 2024, **doi:10.5194/hess-28-4187-2024** | Justifies the global LSTM instead of one LSTM per well. |
| Rangaraj et al., *How Effective are Large Time Series Models in Hydrology? A Study on Water Level Forecasting in Everglades*, 2025, **arXiv:2505.01415** | Chronos best of 17 models for water levels: supports Chronos-2 as the forecasting reference. |
| Holmberg et al., *Knowledge-Graph-Augmented Chronos-2 for HEC-RAS Surrogate Forecasting*, 2026, **arXiv:2609.21381** | A knowledge graph combined with a frozen Chronos-2 in river hydraulics: related work. |
| Schaefli & Gupta, *Do Nash values have value?*, *Hydrol. Processes* 21, 2007, **doi:10.1002/hyp.6825** | Scores only mean something relative to a stated benchmark (our skill scores). |
| Tang, Clark & Papalexiou, *SC-Earth: a station-based serially complete Earth dataset from 1950 to 2019*, *J. Climate* 34, 2021, **doi:10.1175/JCLI-D-21-0067.1** | Source of KGE'' (bias normalised by the observed sd), used because heads near 0 m NGF break the original KGE. |
| Bakker et al., *Scripting MODFLOW model development using Python and FloPy*, *Groundwater* 54, 2016, **doi:10.1111/gwat.12413** | Only if a MODFLOW synthetic twin is built (RQ3). |
| Brodaric et al., *Enabling global exchange of groundwater data: GroundWaterML2 (GWML2)*, *Hydrogeology Journal* 26, 2018, **doi:10.1007/s10040-018-1747-9** | The citable GWML2 reference. No maintained OWL encoding was found: check before Phase 3. |
| Lanini et al., *Groundwater modelling of a complex multilayer coastal aquifer under climate change in the framework of the Dem'Eaux Roussillon project*, AHS 2022 (conference abstract), **HAL hal-03530184** | Two process-based models of our aquifer with shared geometry and pumping locations: domain grounding and a data contact. |

### Added 2026-10-23 (second external review; Crossref records checked that day)

| Reference | Verdict | Why |
|---|---|---|
| Schorpp, Dall'Alba, Renard, Lanini & Caballero, *Hydrogeological modeling of the Roussillon coastal aquifer (France): stochastic inversion and analysis of future stresses*, *Environmental Earth Sciences* 82(9), 201, 2023, **doi:10.1007/s12665-023-10877-4** | **CORE** | The peer-reviewed process-based model of our aquifer (title: stochastic inversion, future stresses). The review says it covers the geological structure, canal recharge and the uncertainty of withdrawals: check while reading. It grounds the domain chapter and the canal-recharge case study. |
| Chu, Ruan & Gong, *A hybrid TFN–LSTM model for groundwater level forecasting in Rhode Island, USA*, *Journal of Environmental Management* 414, 130474, 2026, **doi:10.1016/j.jenvman.2026.130474** | **CORE** (positioning) | A transfer-function-noise model (Pastas) plus an LSTM that forecasts its residuals; 3 wells; SHAP shows past residuals drive the correction (abstract read on PubMed, PMID 42442261, 2026-10-25). Our hybrid is a simulation model with shared, sign-constrained responses and a bounded residual blind to the constrained drivers: position it against this residual-learning design. Full text still to read (split, inputs, pumping). |
| Jeong, Lee, Lee, Mbarki, Kim, Moon, Seo, Park & Jeong, *A physically interpretable transfer learning framework for improved generalization of data-driven groundwater level prediction*, *Water Research* 304, 126321, 2026, **doi:10.1016/j.watres.2026.126321** | **CORE** (positioning) | GRU + 1D convolution pretrained on 62 wells, transferred with 1–3 years of target-well data (leave-one-well-out); the abstract confirms the review: convolution-kernel weights agree with independently estimated residence times, and transfer similarity weights follow residence time and vadose-zone permeability (PubMed, PMID 42361754, read 2026-10-25). The closest precedent for our explanation checks. Full text still to read. |
| Roberts et al., *Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure*, *Ecography* 40(8), 913–929, 2017, **doi:10.1111/ecog.02881** | CITE | Why held-out sites must be blocked in space. Cited for the grouped leave-wells-out folds of dataset v4. |

## 3. Reading order (about 3 weeks, alongside Phase 1)

1. Taccari 2024 → Wu 2025 (E3) → Heudorfer 2024 → Pastas 2019. This is how our
   problem is solved today.
2. Marconato 2023 → Ross 2017 (gradient penalties) → Runje & Shankaranarayana
   2023 (monotone networks). This is how we add knowledge, and how it can fail.
   (Until 2026-10-23 this line read "Xu 2018 (semantic loss) → PiShield".)
3. Clark 2025 (F1) → Azzolin 2024 (F3). This is how we explain the
   predictions, and how we check those explanations.
4. WHOW-KG 2025 → OntoAligner. This is how the knowledge side is built.
5. Dall'Alba 2023 (geology chapter) and Costa 2025. This is what the
   aquifer actually does.

For each paper, fill one row of the comparison table the guide asks for.
Use these columns: authors/year, problem, method, data, results, limits,
and **what we take from it**. Keep the table in
`docs/literature/comparison_table.md`.
