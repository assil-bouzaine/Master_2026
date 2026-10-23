# Gate 2: baseline results (one page)

**Project:** LULC-Water ontology and knowledge-guided GNN for groundwater (SAVE Water)
**Author:** Assil Bouzaine · **Date:** 13 October 2026 · **Read with:** the Gate 1 memo

## What was done

I built a weekly dataset for the Roussillon plain and tested standard
models before adding any ontology.
- **Data:** 65 piezometers (33 core wells for reporting), 2005–2026.
- **Inputs:** Météo-France SAFRAN climate, declared pumping (BNPE), river
  flows.
- **The target is the hard part:** the test period is the record drought
  (May 2022 → October 2026), in which 45% of the weeks are in BRGM's
  "très bas" class. Every model was trained up to 2019 and tuned on
  2020–April 2022. **No choice was made on the test period.**

Two tasks:
- **simulation:** the level from weather and pumping only
- **forecast:** 4 or 12 weeks ahead, knowing today's level

## Results (median Nash–Sutcliffe efficiency over the 33 core wells; 1 = perfect)

| Task | Model | Validation | Test (drought) |
|---|---|---|---|
| Simulation | Climatology ("a normal year") | 0.07 | −0.27 |
| Simulation | Pastas (standard groundwater model; calibrated 2012–2019) | 0.50 | 0.13 |
| Simulation | LightGBM | 0.49 | 0.20 |
| Simulation | LSTM, tuned automatically (24 trials, 5 seeds) | **0.63** | 0.24 |
| Simulation | Graph neural network on a distance graph (5 seeds; trained 2012–2019) | 0.58 | 0.26 |
| Simulation | **Ensemble LightGBM + tuned LSTM** | 0.62 | **0.25** (error 0.59 m) |
| Forecast 4 weeks | "As far from normal as today" | 0.78 | 0.77 |
| Forecast 4 weeks | **Chronos-2** (pretrained, no training on our data) | 0.81 | **0.83** |
| Forecast 12 weeks | **Chronos-2** | 0.45 | **0.42** (others ≤ 0.20) |

Figures: `reports/figures/baselines_nse_v2.png` (all models),
`reports/figures/baselines_hydrographs_v2.png` (three wells, test period).

## Three findings

1. **Every model stops near 0.25 in the drought.**
   - I tested more history (from 2005 instead of 2012), more wells (65
     instead of 47), automatic tuning and ensembles.
   - Tuning significantly improves normal years (paired Wilcoxon test, 29
     of 33 wells better, p < 0.001).
   - **None of these changes significantly improves the drought**
     (p = 0.24–0.82).
2. **The models miss the deepening summer drawdowns of the deep Pliocene.**
   - Pliocene wells: test score 0.16 for the best model (karst 0.60,
     alluvium 0.26–0.45).
   - At Sabirou, the real summer level fell to about 20 m while every model
     stays near 22 m.
   - Most likely cause: summer pumping intensified in the drought, and the
     inputs cannot show it.
     - pumping is declared once a year
     - the aquifer layer each borehole pumps from is not recorded
3. **The data support both of your framing options.**
   - **Use conflict:** the Pliocene's summer drop is driven by pumping
     (a flat-pumping assumption forces the standard model to fake it with
     evaporation).
   - **Canal recharge:** adding canal volumes helps the shallow alluvium
     wells only, which fits canal-return recharge.

## What this means for the thesis

*(Correction of 2026-10-23, second review: the next sentence is too strong.
Missing measurements, forcing assumptions such as the reconstructed weekly
pumping, model structure and groundwater memory remain competing explanations;
see `docs/review_codex_response.md`.)*

The bottleneck is **missing knowledge, not data or model size**. That is
precisely what the ontology phase adds: linking each abstraction point to
its aquifer unit, and building the model's graph from these relations
instead of distances. The baselines above are now the bar to beat, with
significance tests. For forecasting, Chronos-2 is the reference; the
thesis's contribution is on simulation and explanation.

## Questions for you

The Gate 1 questions still apply:
- the framing
- the karst wells
- a newer RPG year
- the journal
- the defence date

In addition:
1. Do you agree with focusing the contribution on simulation and
   explanation, with Chronos-2 as the forecasting reference?
2. Could the project obtain **monthly drinking-water production** for the
   Roussillon boreholes (water utilities or the SAGE syndicate)? It is the
   single most useful missing input.
3. May I start the ontology phase (Phase 3) now, in parallel with your
   review?
