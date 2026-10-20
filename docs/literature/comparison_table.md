# Comparison table (state of the art)

The guide asks for one row per paper. Columns: problem, method, data, results, limits,
and **what we take from it**. Started 2026-10-20 from what was verified that day (open
abstracts, open-access full text where noted). Cells marked *to complete* need the
full text; fill them while reading (`reading_list.md` §3 gives the order). Never fill
a cell from memory.

## Groundwater levels with graphs or deep learning

| Paper | Problem | Method | Data | Results | Limits | What we take |
|---|---|---|---|---|---|---|
| Taccari et al. 2024, *Sci. Rep.* 14, doi:10.1038/s41598-024-75385-2 (open access, read) | Forecast heads in a multi-aquifer polder with pumping and rivers | MTGNN without graph learning: gated dilated temporal convolutions + mix-hop on a **predefined** graph; piezometers + exogenous nodes (rain, ET, river stage, pumping); masked loss | Overbetuwe polder (NL), 30 × 10 km, 200 series after filtering; weekly from 2004; synthetic MODFLOW set (188 wells) for ablations | Predefined graph beat a learned graph (8.13 vs 10.90 cm on synthetic data); real data 16.9 cm vs 25.2 cm for MODFLOW | Forecasting with past heads (5-week window); 80/20 split without validation; no geology in the edges; no LSTM comparison on real data | Our graph baseline (`src/models/taccari.py`); synthetic data to test what a model really uses |
| Wu et al. 2025, *JGR: MLC*, doi:10.1029/2024JH000520 | Groundwater-level forecasting | T-GCN with several spatial-dependency adjacency matrices | North China Plain | *to complete* | *to complete* | Several graphs side by side = the idea behind our arms C–F |
| Wu et al. 2025, *WRR* 61(11), doi:10.1029/2025WR041215 | Spatiotemporal and hydrogeological interpretation of groundwater levels | Graph Fourier deep learning; hydrogeological units as prior information (indexed abstract) | Yellow River Basin, 473 wells (indexed abstract) | *to complete* | *to complete* | **Closest competitor**: knowledge in a graph, but not a formal ontology, no shortcut tests |
| Bai & Tahmasebi 2023, *J. Hydrol.* 616, doi:10.1016/j.jhydrol.2022.128792 | First GNN for groundwater levels | Graph WaveNet-style, self-adaptive adjacency | *to complete* | *to complete* | *to complete* | Origin of the line of work |
| Chidepudi et al. 2025, *HESS* 29, doi:10.5194/hess-29-841-2025 | Multi-station deep learning for groundwater-level simulation | LSTM, GRU, BiLSTM; static aquifer attributes; clustering by spectral properties; wavelet features | Northern France | Models trained on clusters of similar series beat a model trained on all wells (abstract) | *to complete* | French setting, static attributes: compare with our arm B; clustering as an alternative to a graph |
| Heudorfer et al. 2024, *HESS* 28, doi:10.5194/hess-28-525-2024 | Do global groundwater models use static features as semantics? | Entity-aware deep learning, feature ablations | *to complete* | Static features act as identifiers, not semantics (reading list) | *to complete* | Our semantic-ablation test (RQ3) |
| Collenteur et al. 2024, *HESS* 28, doi:10.5194/hess-28-5193-2024 | What can data-driven models do for head simulation? | Modelling challenge: 15 teams, many model types | 4 wells (3 Europe, 1 USA), ~15 y of heads + daily weather | *to complete* | 4 wells only | Benchmark culture and metrics hydrologists expect |
| Kratzert et al. 2024, *HESS* 28, doi:10.5194/hess-28-4187-2024 | Single-basin vs multi-basin LSTMs | Opinion paper with experiments; survey of 150 papers (122 single-basin) | *to complete* | LSTMs are best trained on many basins | Rainfall–runoff, not groundwater | One global LSTM for all wells |

## Graphs and knowledge in hydrology (beyond groundwater)

| Paper | Problem | Method | Data | Results | Limits | What we take |
|---|---|---|---|---|---|---|
| Kirschstein & Sun 2024, ICML, arXiv:2405.19836 | Does river-network topology help neural flood forecasting? | GNNs with several adjacency definitions vs no topology | Gauging-station network | No benefit from topology; learned edge weights matched no static definition | Discharge, not groundwater | Controls in RQ1 (no graph, random graph) |
| Topp et al. 2023, *WRR* 59, doi:10.1029/2022WR033880 | Generalisation of graph models under shifted conditions | RGCN vs Graph WaveNet, process-guided; explainable AI | Delaware River Basin stream temperature | Equal skill in-distribution; Graph WaveNet better in 4/5 shifted tests, its learned spatial relations closer to physics | Stream temperature | XAI to check whether the learned structure is physical (RQ3/RQ4) |
| Jia et al. 2021, SDM, doi:10.1137/1.9781611976700.69 | Flow and temperature in river networks | Physics-guided recurrent graph model on the river network | *to complete* | *to complete* | *to complete* | Domain graph + physics loss: the knowledge-guided ancestor of our design |
| Holmberg et al. 2026, arXiv:2609.21381 | Surrogate of a hydraulic model (HEC-RAS) | Frozen Chronos-2 + graph-conditioned retrieval and corrections ("project knowledge") | 4,675 cross-sections, 71 reaches | 14 % lower RMSE than frozen Chronos-2 | Surface hydraulics; graph construction not described in the abstract | Knowledge graph + foundation model is being tried: related work for the forecasting task |
| Rangaraj et al. 2025, arXiv:2505.01415 | Are time-series foundation models useful in hydrology? | 12 task-specific models vs 5 foundation models | Everglades water levels | Chronos best of all | One region | Chronos-2 as the forecasting reference |

## Knowledge-guided learning, constraints, shortcuts

| Paper | Problem | Method | Data | Results | Limits | What we take |
|---|---|---|---|---|---|---|
| Ross et al. 2017, IJCAI, doi:10.24963/ijcai.2017/371 | Models right for the wrong reasons | Penalise input gradients on features annotated as irrelevant | *to complete* | Better generalisation when test conditions differ | Needs annotations | Soft sign constraints (RQ2); the phrase in our title |
| Marconato et al. 2023, NeurIPS, arXiv:2305.19951 | Reasoning shortcuts in neuro-symbolic models | *to complete* | *to complete* | *to complete* | Discrete concepts | RQ3, with driver contributions as concepts |
| Koh et al. 2020, ICML, arXiv:2007.04612 | Interpretable predictions through concepts | Predict concepts, then the label from the concepts | Knee X-rays, birds | Competitive accuracy; concepts can be edited | Concepts must be labelled | Treat driver contributions as a concept layer |
| Runje & Shankaranarayana 2023, ICML, arXiv:2205.11775 | Monotonic neural networks | Constrained weight signs + new activations | *to complete* | *to complete* | *to complete* | Hard monotone constraints for response signs (RQ2) |
| Tsai et al. 2021, *Nat. Commun.* 12, doi:10.1038/s41467-021-26107-z | Calibrating process models at scale | Differentiable parameter learning: a network maps inputs to process-model parameters | Soil moisture, streamflow | Better than regionalisation, or equal with ~12.5 % of the data | *to complete* | Option §5.5 of `docs/feedback.md` |

## Time-series modelling of heads (hydrology baselines)

| Paper | Problem | Method | Data | Results | Limits | What we take |
|---|---|---|---|---|---|---|
| Collenteur et al. 2019, *Groundwater* 57(6), doi:10.1111/gwat.12925 | Open groundwater time-series analysis | Transfer-function noise models (Pastas) | *to complete* | *to complete* | Linear superposition | Hydrology reference baseline |
| Brakenhoff et al. 2022, *Front. Earth Sci.* 10, doi:10.3389/feart.2022.907609 | Drawdown from several well fields | Pastas WellModel: one Hantush response scaled by distance | 250 series, 122 locations, eastern Netherlands | *to complete* | *to complete* | `pastas_wellmodel` |
