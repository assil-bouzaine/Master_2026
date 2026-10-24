# Comparison table (state of the art)

The guide asks for one row per paper. Columns: problem, method, data, results, limits,
and **what we take from it**. Started 2026-10-20 from what was verified that day (open
abstracts, open-access full text where noted). Cells marked *to complete* need the
full text; fill them while reading (`reading_list.md` §3 gives the order). Never fill
a cell from memory.

## Positioning matrix (added 2026-10-23, second review)

Headline accuracies of unrelated datasets are not comparable. What separates the closest
studies from ours is how they are set up. "to read" = not yet checked in the paper
(never filled from memory). Heudorfer 2024 was checked on its open HESS page
(2026-10-23).

| Study | Past heads as input? | Forcings | Split / spatial test | Knowledge supplied to the model | Explanations checked against independent information? |
|---|---|---|---|---|---|
| **This thesis** | **No** (simulation); forecasting is a secondary hindcast | SAFRAN reanalysis; pumping **reconstructed** from annual BNPE declarations; river discharge | Temporal (drought / recovery), grouped leave-wells-out (wells < 2 km together), 25/50 % data | KG: units, stacks, pump → unit links with measured confidence, signed `Influence` nodes; equivalence test against plain tables | Semi-synthetic twin (incl. mechanisms the model cannot fit), faithfulness, entity and sign tests, documented events (2024 BRGM bulletin) |
| Taccari et al. 2024 (full text read 2026-10-24, Europe PMC PMC11490608) | Yes: 5-week window; trained 6–8 weeks ahead, shown up to 100 weeks; exogenous inputs given as observed values at inference (a hindcast, like ours) | Observed rain, ET, river stage, pumping as exogenous nodes | Chronological: 80 % train from 2004; the 10 % validation and 10 % test were merged into one 20 % test from April 2018 (a separate test was judged unrepresentative); **no held-out wells** on real data (connectivity ablations on synthetic MODFLOW data only) | Predefined graph (no geology in the edges) | **No**: skill compared with MODFLOW (RMSE 16.9 vs 25.2 cm); no explanation analysis |
| Wu, Yao, Guo, Yang, He, Lancia & Zheng 2025, *WRR* (gold open access; full text read 2026-10-24) | **Yes**: heads and forcings over the previous 6 steps of 5 days; forecasts the next 5 steps (up to 25 days) | Precipitation, temperature, evapotranspiration, NDVI | 473 wells, Yellow River Basin, 5-day heads 2018–2021; chronological 70/30 train/test (no separate validation in the main text; repeated multi-split robustness in the SI); **no held-out wells** | Static edges from hydrogeological units + dynamic graph generation, Fourier layers and graph attention. Control GFN-FC (fully connected graph, confirmed): R² 0.85 vs 0.90 at 5 days (ST-LSTM 0.84, XGBoost 0.80, LSTM 0.78); no random or rewired-graph control | **No**: responses per unit interpreted, not checked against independent information. Code public (github.com/xjtu-gwdg/GraphFourierNet) |
| Wu, Mei, Shao, Xu & Peng 2025, *JGR: MLC* (gold open access; full text read 2026-10-24) | **Yes** (forecasting from the historical series); lookback to read | Daily rainfall (CHIRPS) builds a rainfall-similarity graph; model inputs to read | 15 shallow wells, 5-day heads Jan 2018–Mar 2022; chronological 72/28 train/test with 5 time-ordered validation folds inside training; heads **smoothed by a 30-step moving average** before modelling; **no held-out wells** | Five predefined graphs (distance, rainfall similarity, hydraulic gradient, head-variation similarity, sub-basin) combined in a T-GCN whose adjacency is optimised during training; the composite beats distance only, but LSTM is better at some wells | **No**: learned adjacencies explained after the fact (similar environmental characteristics) |
| Heudorfer et al. 2024 | **No**: meteorological inputs only | Precipitation, temperature (+ annual sinusoid), relative humidity | Train ≤ 2007, validation 2008–11, test 2012–15; out-of-sample = 10-fold CV over wells; 10 seeds | 18 environmental features + 9 features computed from each well's own head series (to 2011); random-integer controls | No: permutation importance only; static features act as identifiers (the random controls did as well) |
| Chu, Ruan & Gong 2026 (abstract read 2026-10-25, PubMed PMID 42442261) | **Yes**, in effect: an LSTM learns the residuals of a TFN (Pastas) model and forecasts corrections; SHAP: *past TFN residuals* drive the correction (residual persistence) | Precipitation, potential evapotranspiration (TFN); daily heads | 3 monitoring wells, Rhode Island; split to read in the full text | None beyond the TFN structure (no pumping, no graph, no sign constraints stated) | No: SHAP of the residual network only |
| Jeong et al. 2026 (abstract read 2026-10-25, PubMed PMID 42361754) | To read (GRU + 1D convolution from precipitation; target-well data used for transfer) | Precipitation (abstract: "precipitation–GL response patterns") | 62 wells, South Korea; **leave-one-well-out** with 1, 2 or 3 years of target-well data for transfer learning; extrapolation beyond the training range | Pretrained backbone across wells; no hydrogeological graph or constraint | **Yes**: convolution-kernel weights agree with *independently estimated residence times*; transfer similarity weights follow residence time and vadose-zone permeability |

Note: Heudorfer et al. also give held-out wells features computed from their own head
history, as our R2 convention does (mean, sd, artesian share). Both are transfer between
monitored wells, not prediction at ungauged sites.

**Positioning (from the matrix, to confirm when the full texts are read):** the closest
graph studies (Taccari 2024, both Wu 2025) forecast with past heads. With past heads,
persistence carries much of the skill, so it is hard to tell whether the graph knowledge
is used. We simulate from forcings and reconstructed pumping only, so the drivers and the
knowledge must carry the prediction, and we test whether they do (twin, rewiring,
signs). The second difference is the source of the graph: a formal KG with provenance
and measured confidence. Wu WRR embeds units as priors in a graph that is partly
generated dynamically. The third is the checks of the explanations.

Hybrids (abstracts read on PubMed, 2026-10-25): Chu et al. 2026 correct a Pastas TFN with
an LSTM forecasting its residuals, and SHAP shows past residuals drive the correction: a
forecasting design that leans on persistence, which our simulation hybrid avoids (no past
heads or residuals; a bounded residual blind to the constrained drivers). Jeong et al. 2026
already compare learned kernels with independently estimated residence times: cite it as
the precedent for checking learned responses, and do not claim that idea as new; our
contribution is the formal, uncertain knowledge behind the responses and the tests of
whether it is used.

## Groundwater levels with graphs or deep learning

| Paper | Problem | Method | Data | Results | Limits | What we take |
|---|---|---|---|---|---|---|
| Taccari et al. 2024, *Sci. Rep.* 14, doi:10.1038/s41598-024-75385-2 (open access, read) | Forecast heads in a multi-aquifer polder with pumping and rivers | MTGNN without graph learning: gated dilated temporal convolutions + mix-hop on a **predefined** graph; piezometers + exogenous nodes (rain, ET, river stage, pumping); masked loss | Overbetuwe polder (NL), 30 × 10 km, 200 series after filtering; weekly from 2004; synthetic MODFLOW set (188 wells) for ablations | Predefined graph beat a learned graph (8.13 vs 10.90 cm on synthetic data); real data 16.9 cm vs 25.2 cm for MODFLOW | Forecasting with past heads (5-week window); 80/20 split without validation; no geology in the edges; no LSTM comparison on real data | Our graph baseline (`src/models/taccari.py`); synthetic data to test what a model really uses |
| Wu et al. 2025, *JGR: MLC*, doi:10.1029/2024JH000520 (full text read 2026-10-24) | Groundwater-level forecasting | T-GCN with several spatial-dependency adjacency matrices | Haihe River Basin, North China Plain: 15 shallow wells, 5-day heads, 2018–2022 | Composite graph better than distance only; not always better than LSTM at individual wells | 15 wells over 4 years; target smoothed (30-step moving average); no held-out wells; post-hoc interpretation | Several graphs side by side = the idea behind our arms C–F |
| Wu et al. 2025, *WRR* 61(11), doi:10.1029/2025WR041215 (full text read 2026-10-24) | Spatiotemporal and hydrogeological interpretation of groundwater levels | Graph Fourier deep learning; hydrogeological units as prior information | Yellow River Basin, 473 wells, 5-day heads 2018–2021 | R² 0.90 (5 days) to 0.67 (25 days); beats the fully connected control, ST-LSTM, XGBoost and LSTM | Forecasting with past heads, leads ≤ 25 days; chronological 70/30 without a separate validation set; no spatial hold-out; no random-graph control; interpretations not checked independently | **Closest competitor**: knowledge in a graph, but not a formal ontology, no shortcut tests |
| Bai & Tahmasebi 2023, *J. Hydrol.* 616, doi:10.1016/j.jhydrol.2022.128792 | First GNN for groundwater levels | Graph WaveNet-style, self-adaptive adjacency | *to complete* | *to complete* | *to complete* | Origin of the line of work |
| Chidepudi et al. 2025, *HESS* 29, doi:10.5194/hess-29-841-2025 | Multi-station deep learning for groundwater-level simulation | LSTM, GRU, BiLSTM; static aquifer attributes; clustering by spectral properties; wavelet features | Northern France | Models trained on clusters of similar series beat a model trained on all wells (abstract) | *to complete* | French setting, static attributes: compare with our arm B; clustering as an alternative to a graph |
| Heudorfer et al. 2024, *HESS* 28, doi:10.5194/hess-28-525-2024 (open access, abstract and method read 2026-10-23) | Do global groundwater models use static features as semantics? | Entity-aware deep learning with environmental and time-series static features; random-integer controls | 108 weekly series, uppermost unconfined aquifer, Germany | In-sample NSE > 0.8, out-of-sample < 0.7; all variants alike, random integers included: the features act as identifiers | Permutation importance only, rankings unstable; no independent check | Our semantic-ablation test (RQ3); the random-ID control idea |
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

## Added 2026-10-23 (second review; Crossref records checked, full texts to read)

| Paper | Problem | Method | Data | Results | Limits | What we take |
|---|---|---|---|---|---|---|
| Schorpp et al. 2023, *Env. Earth Sci.* 82:201, doi:10.1007/s12665-023-10877-4 | Process-based model of the Roussillon coastal aquifer | Stochastic inversion; analysis of future stresses (title) | Roussillon | *to complete* | *to complete* | Domain grounding for our aquifer; canal recharge and withdrawal uncertainty according to the review |
| Chu et al. 2026, *J. Environ. Manage.* 414:130474, doi:10.1016/j.jenvman.2026.130474 (abstract, PubMed PMID 42442261, read 2026-10-25) | Groundwater-level forecasting, Rhode Island | Residual learning: TFN (precipitation, PET) baseline + LSTM forecasting its residuals; SHAP | Daily heads, 3 wells | Hybrid better than TFN and LSTM alone, most at wells with complex behaviour; degrades more slowly with lead time; past residuals dominate the correction | Forecasting with past residuals (persistence), 3 wells; full text to read for split, inputs and pumping | Our hybrid differs on purpose: simulation (no past heads or residuals), response parameters shared across wells and given by the KG-fed GNN, sign constraints, a residual that is bounded and blind to the constrained drivers. Their SHAP result is the risk our bounded residual guards against |
| Jeong et al. 2026, *Water Res.* 304:126321, doi:10.1016/j.watres.2026.126321 (abstract, PubMed PMID 42361754, read 2026-10-25) | Groundwater-level prediction with short records at new wells | GRU + 1D convolution, pretrained on 62 wells, transfer learning | South Korea, 62 wells; leave-one-well-out with 1–3 years of target data | Transfer with 1 year beats a GRU with 3 years; stable beyond the training range; kernel weights match independently estimated residence times | No pumping or geology in the model (abstract); full text to read | The closest precedent for checking learned responses against independent hydrogeological information (our RQ3/RQ4); its leave-one-well-out with target data is transfer to monitored wells, like our R2/R3 |
| Roberts et al. 2017, *Ecography* 40(8):913–929, doi:10.1111/ecog.02881 (abstract read 2026-10-23) | Cross-validation with structured data | Blocked (spatial, temporal, hierarchical) cross-validation | *to complete* | Block cross-validation is "nearly universally more appropriate" than random when predicting to new data; block wherever dependence exists | Blocking must be chosen with care: it can force extrapolation and overestimate error | The grouped folds of dataset v4 (moderate 2 km blocks, not whole regions) |

## Time-series modelling of heads (hydrology baselines)

| Paper | Problem | Method | Data | Results | Limits | What we take |
|---|---|---|---|---|---|---|
| Collenteur et al. 2019, *Groundwater* 57(6), doi:10.1111/gwat.12925 | Open groundwater time-series analysis | Transfer-function noise models (Pastas) | *to complete* | *to complete* | Linear superposition | Hydrology reference baseline |
| Brakenhoff et al. 2022, *Front. Earth Sci.* 10, doi:10.3389/feart.2022.907609 | Drawdown from several well fields | Pastas WellModel: one Hantush response scaled by distance | 250 series, 122 locations, eastern Netherlands | *to complete* | *to complete* | `pastas_wellmodel` |
