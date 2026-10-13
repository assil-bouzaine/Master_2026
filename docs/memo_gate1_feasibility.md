# Gate 1 memo: data feasibility and paper plan

**Project:** LULC-Water ontology and knowledge-guided GNN for groundwater
(SAVE Water) · **Author:** Assil Bouzaine · **Date:** 13 October 2026

This memo closes the data-collection stage. It summarises what data exists
for the Roussillon plain, what the data says about the research question, the
plan for the thesis and a journal paper, and five questions I need your
answer on.

---

## 1. Data inventory (all open, all re-downloadable by script)

| Layer | Source | What we have |
|---|---|---|
| Groundwater levels | Hub'Eau *niveaux_nappes* (ADES) | 101 stations in dept 66. **33 in the working set** (≥ 8 years, active in 2024+, ≥ 50 values/year, in the plain). Daily data, records up to 35 years. 115,443 values over 2016–2025. |
| Aquifer structure | BD LISA V3 (Occitanie) | 30 aquifer entities under the plain. The vertical stack under each well. 26 "overlies" relations. |
| Agricultural land use | RPG (IGN), 2016 and 2023 | About 10,200 parcels / 14,000 ha within 3 km of the wells in 2023. Vines 32%, orchards 19%. Stable in hectares since 2016. |
| Water abstraction | BNPE via Hub'Eau *prélèvements* | 3,061 abstraction points. Annual volumes by use and source, 2012–2023. |
| Still to add (next 3 weeks) | Météo-France SAFRAN/SIM2; Hub'Eau *hydrométrie* | Rain, evapotranspiration, soil moisture (8 km grid); discharge of the Têt, Agly, Réart, Tech |

Wells by aquifer:
- 20 in the Pliocene multilayer (`671AA00`)
- 6 in the recent or ancient alluvium
- 6 in the Corbières karst
- 1 unclassified

The numbers match a first exploration done in August 2026 within a few
percent. Every difference is explained in the project notes.

## 2. What the data says

**(a) Irrigation is mostly surface water; groundwater mostly serves drinking water.**

| Plain, 2012–2023 cumulative | Surface water | Groundwater |
|---|---|---|
| Irrigation | 741 Mm³ (84%) | 144 Mm³ (16%) |
| Drinking water | 3 Mm³ (1%) | 475 Mm³ (99%) |
| Canal intakes (Têt/Agly canals) | 1,245 Mm³ | — |

- Groundwater for drinking water is steady at about 39–43 Mm³ per year.
- Groundwater for irrigation appears to rise from about 7 to about 18 Mm³ per
  year after 2018. This is mostly a **reporting change**: many more boreholes
  declare from 2018.

So the simple chain "crops pump the aquifer" from the subject does not
describe this plain well. Two sharper framings follow (question Q1).

**(b) Water does not always flow downward between the layers.**
- I compared the heads of 17 shallow/deep well pairs (≤ 5 km apart, shallow
  aquifer above deep aquifer in BD LISA). The shallow level is above the deep
  level in only **50.5%** of 17,124 pair-weeks.
- Two nested piezometers (same site, different depths) show both cases:
  - **At Millas (Têt valley)**, water goes down 100% of the time.
  - **At Barcarès (Agly)**, the deep Pliocene is under pressure. Water goes
    up about 95% of the time, and the gradient reverses mostly in summer and
    autumn, when pumping is highest.
- Four Pliocene wells are sometimes **artesian** (level above ground).

Consequence: the constraint "water infiltrates downward" proposed in the
subject would be wrong half of the time here. I propose constraints on the
*direction of responses* instead (pumping lowers the level, rain raises it).
These hold everywhere. The seasonal reversal is itself evidence of the
summer abstraction pressure on the Pliocene.

**(c) The test period is ready-made.** The Roussillon reached historic lows in
2022–2024 (BRGM bulletins), and levels recovered in 2025–2026. Our own
series confirm this. The median standardised level of the working-set wells
(reference 2010–2026) was:
- 2023–2024: −0.5 (Pliocene) and −1.1 (alluvium)
- 2026: back to +0.5 and +0.9 Training up to
2019 and testing on May 2022 → 2026 tests the model on a drought it never saw.

## 3. Caveats

- The latest BNPE year (2023) is under-reported (declarations still being
  consolidated).
- Boreholes below the declaration threshold are missing, so groundwater
  irrigation is a **lower bound**.
- The 2018 reporting break means volumes before and after 2018 are not
  directly comparable.
- BNPE volumes are annual. The model runs weekly, so I will spread them with
  monthly use profiles and test how sensitive the results are.
- 19% of 2016–2025 levels are flagged "non qualifié" (not yet validated),
  rising to 52% in 2025. I will report results with and without them.
- The Pliocene is one BD LISA entity but several sand layers. Wells from
  11 m to 235 m deep may monitor different layers. Well depth is kept as
  an input.

## 4. Plan: thesis and one journal paper

**Working title:** *Right for the right reasons? Ontology-derived graphs and
constraints for groundwater-level forecasting in a Mediterranean multilayer
aquifer.*

| | Research question |
|---|---|
| RQ1 | Does a graph built from the LULC-Water knowledge graph forecast weekly levels better than a distance-only graph and strong standard models? Tested on the drought period, on wells held out from training, and with less training data. |
| RQ2 | Do constraints derived from the ontology make predictions more physically plausible and more robust out of distribution? |
| RQ3 | Does the model really use the knowledge, or only satisfy it (a "reasoning shortcut", Marconato et al., NeurIPS 2023)? We scramble the ontology's relations and check whether skill drops. |
| RQ4 | Can explanations be written in ontology terms ("the drop at well X is linked to pumping from the Pliocene unit and to the rainfall deficit") *and* be shown to be faithful to the model? |

**Design choices (changes from the subject, with the reason):**
1. **The ontology generates the model's graph** (by SPARQL query), so the
   ontology is used, not only described.
2. **Response-direction constraints** instead of "water goes down" (see 2b).
3. **Standard models as baselines:**
   - Pastas, the reference groundwater time-series model
   - LSTM networks
   - a recent forecasting foundation model (Chronos-2)
   - a distance-based graph network

   Without these, a hydrology journal will not accept the paper.
4. **SHACL** rules instead of SWRL, for validation and derived concepts.
5. **Land use from the RPG**; satellite embeddings (AlphaEarth) only as
   extra features.
6. **Nitrate, socio-economics, the dashboard and the Spain/Tunisia sites
   become future work**, with an optional small Tunisia demo if time
   allows.

**Timeline** (assuming a defence in June 2027):

| When | What |
|---|---|
| Nov 2026 | Climate and river data, weekly dataset |
| Dec 2026 | Baseline models |
| Dec–Jan | Ontology and knowledge graph |
| Feb 2027 | Knowledge-guided model, tests |
| Mar 2027 | Explanations |
| Apr 2027 | Paper written and submitted |
| May–Jun 2027 | Thesis and defence |

**Target journals:** *Environmental Modelling & Software* (first choice) or
*JGR: Machine Learning and Computation* (AGU, open access).

## 5. Questions for you

1. **Framing.** Which do we commit to?
   - **(A) the use conflict on the Pliocene:** drinking water vs
     agriculture, with the summer gradient reversal as evidence
   - **(B) canal-return infiltration** as a recharge term for the alluvium

   The pipeline supports both. The choice changes the story and the
   explanation case studies.
2. **Karst stations.** Keep the 6 Corbières karst stations, or work on the
   26 plain stations only? Karst behaves very differently: its level is
   15–18 m below the nearby Pliocene.
3. **Land use.** Is RPG 2016 + 2023 enough, or should I add 2024/2025
   (available, new format)?
4. **Publication.** Do you agree with the venue? Does SAVE Water pay
   open-access fees (the project committed to gold open access)? Who should
   be co-authors?
5. **Dates.** What is the defence date, and is there a mid-term deadline
   for the thesis?

Figures and full numbers are in the project notes (`docs/notes/`). I can
send the maps on request.
