# Step 12d: the land-use thread (after the Codex review of 2026-10-25)

## What was done (2026-10-25)
- Checked `docs/review_codex_2026-10-25.md` against the code: no dated land use
  entered the dataset, the baselines or the KG. Verdicts and the working road:
  `docs/review_codex_2026-10-25_response.md`.
- Assil decided: annual RPG 2015–2025; CQ7, CQ10, CQ15 → MUST; a pre-registered
  land-use test (`docs/analysis_plan.md` §14 item 13). In the afternoon: the RPG is
  clipped to the whole département (the plain clip missed 15 wells, see Corrections).
- **LU-1** `src/ingest/rpg.py --clip dept --drop-raw` → `data/interim/rpg_dept_<year>.parquet`
  (parcels inside `DEPT_BBOX` of `src/ingest/safran.py`, the extent of the weather data,
  which holds every well's 3 km zone). Each edition's own feed gives its file names
  (2022 is a `.7z.001` part), parts are joined, MD5 checked per file when published, and a
  failed year no longer stops the others. Registration check: `src/analysis/rpg_coverage.py`.
- **LU-2** `configs/lu_crop_classes.csv`: 14 harmonised crop classes with their FAO-56 Kc
  (Table 12) and stage lengths (Table 11), read on fao.org/4/X0490E/x0490e0b.htm on
  2026-10-25; rows without an FAO-56 stage row (alfalfa, pasture, Mediterranean walnut)
  say so. Each class carries an irrigation *assumption* (usually / partly / rainfed / none).
- **LU-3** `src/dataset/crop_demand.py` (the crop-thirst index), its check against declared
  irrigation `src/analysis/crop_demand_check.py`, pumping reconstruction (3)
  `src/dataset/pumping_cropcal.py`, the figure `src/analysis/crop_demand_figure.py`.
- **LU-4, code and inputs only** (no model trained on the laptop): `build_panel(land_use=
  "on" | "placebo" | "wide")` in `src/models/features.py` (own cache files, each adding
  `crop_demand` and its 4/13/52-week means, the other 69 columns unchanged; the default
  panel rebuilt from scratch is identical to the cached v4 panel, 90,740 × 69); `--land-use`
  in `lgbm.py`, `lstm.py`, `tune.py`; steps `lu:lgbm` and `lu:lstm` in
  `scripts/run_v4_cpu.sh`; scoring as pre-registered in `src/analysis/land_use_test.py`
  (written before any run). The runs go to Kaggle once kernel 5 is pulled.
- Foreign land: `src/ingest/borders.py` (Natural Earth 1:10m, Spain + Andorra). No well's
  3 km zone reaches it (nearest: Valcebollère, 3.9 km); kept as a guard.

## Why
The subject asks how land use and agricultural practices affect water. The project's
chain had a missing first link. In Roussillon most irrigation water comes from canals, and
the farm-borehole links stay "possible". So the agricultural signal enters as crop demand
(timing and place of farm water use) and canal return flow, not through pump → unit links.

## How the crop thirst is computed
- For each well and week: sum over crop classes of clipped area within 3 km × max(0, Kc ×
  ETP − rain) × 10 (m³). ETP is SIM2's FAO-56 Penman-Monteith reference, which is what Kc
  is defined against; rain is liquid + solid; both weekly sums on the well's SAFRAN cell.
- Kc on calendar dates: each season starts on day 1 of its planting month every year;
  perennials keep Kc_ini off season, annual crops have Kc = 0. Weekly Kc = mean of the 7
  days of the week (Monday–Sunday, labelled by the Sunday, as the forcing).
- Main index `demand_main_m3` = classes assumed usually irrigated (orchards, vegetables,
  artichokes, maize, citrus); `demand_wide_m3` adds the partly irrigated classes (vines,
  olives, nuts, fodder) as a sensitivity. Decided by Assil on 2026-10-25, before any run,
  from the 2020 census (next section). The parts are stored separately.
- **Why rain and not SIM2's PE:** PE is the water surplus after the soil fills (drainage +
  runoff), near zero all summer. Soil storage is ignored: an index of the timing and size
  of demand, not a field water balance.
- Each calendar year uses its own RPG edition; before 2015 the 2015 mix (`rpg_backfill`);
  `rpg_lag_years` = year − edition used.
- Placebo: each well's own weather with another well's crop areas (a seeded derangement).

## Checks and findings
- `tests/test_crop_demand.py`: CQ7 acceptance (10 ha parcel, 4 ha inside → 4 ha), unknown
  codes kept as "unmapped", Kc at the FAO-56 stage days on the same dates in leap and
  common years, the last day of a season, winter crops across the new year, a zone in Spain
  is foreign, reproducible derangement; on the real output: every crop code keeps its RPG
  group in all 11 editions (245 codes, so classes by group are valid every year), no
  negative value, no unmapped area, summer ≫ winter, and the placebo recomputed
  independently for three wells.
- `tests/test_pumping_cropcal.py`: the climatology ignores post-training weather, weights
  sum to 1 per year, fallback flagged; on the real tables: the moved weights of
  reconstruction (1) reproduce the v4 weekly table (largest relative spread 4e-16), annual
  volumes of complete years kept (only the unfinished 2026 differs, +2.64 Mm³: each method
  gives the weeks so far its own share of the year), other uses unchanged.
  `tests/test_pumping_conservation.py` still passes. One synthetic check (summer weights
  ≥ 5 × the other months) failed once the main classes became orchards and vegetables only:
  the monthly shape was inspected first (0 % December–February, peak June–July, 62 % in
  summer; ratio 4.8, because orchards also need water in spring and September), then the
  arbitrary threshold was replaced by "winter < 1 %, summer > 50 %".
- **Reconstruction (3) on the real tables:** mean within-year correlation between the
  plain's weekly irrigation and the climatic deficit (April–October) 0.96 under (1), 0.61
  under (3); both keep the normal seasonal cycle, (3) drops the year's own weather. 33 of
  75 SAFRAN cells have no main-class crop and take the département mix: 2.3 % of the
  irrigation volume, 28 of 1,877 facilities, none in the plain.
- **Size check** (plain box, as BNPE; 2015–2025): the main classes cover 4,500–5,500 ha and
  their thirst is 29–41 Mm³ a year, against 66–82 Mm³ of declared irrigation (2015–2023),
  a ratio of 0.4–0.6 every year; the wide classes cover about 20,000 ha, and with every
  vineyard fully watered the thirst (92–126 Mm³) would exceed the declared irrigation. The
  declared surface irrigation is almost the same every year (flat-rate declarations), so
  only the size can be compared, not the year-to-year changes.
- **Registration vs real change** (plain, 2015 → 2025): the declared area grows from
  33,820 to 39,848 ha, and every year 1,400–3,300 ha appear and 1,400–2,700 ha disappear.
  Orchards +876 ha net, of which +86 ha by conversion on land declared both years and
  +1,419 ha on newly declared land; grassland +4,674 ha, of which +5,956 ha newly declared;
  vines −2,038 ha net, −2,134 ha by conversion, 1,339 ha of it from 2024 to 2025, when
  1,637 ha of 2024 vineyard (stable footprint) became fallow (644 ha) or temporarily
  non-eligible land (909 ha), consistent with uprooting, not with a new vine code. So part
  of any area trend in the index comes from declarations. (The 2015 → 2023 figures of the
  morning, on fewer editions, are superseded.)
- Mountain wells: their zones are mostly summer pasture (rainfed), Collioure and the
  Tirounère spring have 210 and 343 ha of vines.
- **Census check of the irrigation assumptions** (RA2020, dept 66; `data/README.md`,
  "Land-use thread"). Farms specialised in fruit irrigate 78 % of their land (5,268 ha),
  in vegetables 84 % (932 ha); farms irrigating mainly vines irrigate 839 ha, fruit-and-vine
  farms 502 ha, against 19,840 ha of vines: about 4–7 % of the vines. So "usually" holds
  for orchards and vegetables, and vines are far below what counting all their area
  implies. The census also confirms the real changes: vines −5,770 ha and orchards
  +1,150 ha (+16 %) between 2010 and 2020, so part of the orchard area on newly declared
  land is real planting, which the RPG alone cannot separate from registration.

## Second Codex review of 2026-10-25 (answered the same afternoon)
`docs/review_codex_2026-10-25b.md`, verdicts in `docs/review_codex_2026-10-25b_response.md`.
It read the work at 13:09, half built: its two failing tests and missing files were true
then and were resolved by the full rebuild. Three findings held and were fixed:
- **Run identity (P1).** A resumed LSTM could have mixed seeds from different land-use
  inputs: the fingerprint hashed settings and input names, not values. Each land-use
  panel now has an identity record (`<panel>.json`) with a content hash of its land-use
  columns, checked on every use and put into the LSTM fingerprint and both manifests.
- **Cache key (P2).** The crop-area cache now keys on the well coordinates, the CRS, the
  buffer and a calculation version.
- **The placebo claim was too strong.** One permutation cannot separate crop geography,
  registration and real change. Assil added the **frozen** variant (2019 crop areas in
  every year) before any run; the claim of each contrast is fixed in the plan.
- **A regression of mine, found while fixing P1:** the `--land-use` option put
  `land_use: None` into every LSTM fingerprint, so a Kaggle kernel resuming EA-LSTM folds
  begun with older code would have stopped. An unset option is now left out (tested).
- `tests/test_land_use_inputs.py` checks the snapshot before packaging: editions and lags,
  schema, the four panels against the current index and their records.

## Corrections made on 2026-10-25 (afternoon), after re-checking the morning's work
- **15 wells outside the clip.** The first clip (plain bbox + 3 km) did not hold the 3 km
  zones of the 15 mountain wells (group "other", not core): their index was a false 0.
  Redone on the département extent with Assil's approval (6 editions downloaded again).
- **Stale cache.** The area cache stored crop *classes*, so an edit of the class table
  would have been ignored silently. It now stores crop codes and rebuilds when its inputs
  change; the land-use panel cache does the same.
- **One day off in leap years.** Kc was indexed by day of year; now by calendar date.
- **Sunflower stages** were taken from the small-grains row; FAO-56 has a Mediterranean
  sunflower row (25/35/45/25 days), now used.
- **Wording.** The analysis plan said "Kc(crop, month)" and "effective rain"; the
  implementation uses Kc on calendar dates and rain (fixed before any land-use run).
  "90–100 Mm³ a year" was a sum over 65 overlapping zones, not a plain total; the size
  check above replaces it. Grassland growth was called registration before it was shown;
  it now is. The response to the review said open-ontologies has no SHACL-AF rules: its
  Python layer runs them through pySHACL, which we already use.
- **2022 and the download loop.** 2022 is published as a `.7z.001` part, which the first
  script could not find, and one failed year stopped the later ones.
- **Download volume.** About 10 GB were transferred in all, against the ~4–5 GB and then
  ~3 GB announced when Assil approved: the sizes had not been checked, and the 2024–25
  GeoPackages weigh 1.7 GB each. `--plan` now prints the sizes before any download.

## What to consider
- Potential demand is not irrigation: whether a parcel is irrigated, and from which
  source, are separate facts (CQ7, CQ15). The census numbers are by farm type, not by
  crop; a crop-level table (irrigated area by crop, dept 66) would sharpen them if Agreste
  publishes one.
- Because part of the area trend is registration, a sensitivity with one fixed crop mix
  for all years would separate dated land use from declaration coverage. It is not in the
  pre-registered test; adding it is Assil's decision.
- Reconstruction (3) re-spreads irrigation only, as the plan words it; canal intakes keep
  the deficit timing. Whether canals should follow the crop calendar too is open (Gate 3).
- Before 2015 there is no parcel-level RPG (RPG v1 2007–2014 has group-level shares per
  anonymous block, an option if the backfill matters).

## LU-4 results (2026-10-26): no detectable information from the crop-thirst index

### What was done
- Kaggle kernel 6 (pushed 17:25 UTC on 2026-10-25, ended 22:31 UTC, exit 0, about 5 h): the
  10 runs (LightGBM and LSTM × on, placebo, wide, frozen, none), pulled and rescored on the
  laptop on 2026-10-26 (`scripts/kaggle_cpu.py pull`).
- **Before the pull**, Assil chose the main contrast: on vs none, the control re-trained in the
  same job (commit `1840070`, analysis plan §14 item 13, `src/analysis/land_use_test.py`).
  Placebo, wide and frozen are compared with none for the same reason. Disclosed in the plan:
  one log line had been seen before the decision (the LSTM frozen summary).
- **Checks before scoring:** each land-use run records the content hash of its panel (on
  `bd74f90d…`, placebo `b966f9d3…`, wide `002a84e4…`, frozen `75aeab21…`, equal to the panel
  records); the LSTM land-use runs have 23 inputs with `crop_demand`, the none run the 22 of
  `lstm_tuned`; the LightGBM none run reproduces `lgbm_noclim_tuned` of kernel version 2
  (largest prediction difference 4.4e-16).
- Scored as pre-registered: `PFE_DATASET=v4 python -m src.analysis.land_use_test` →
  `results/v4/land_use_test.csv`.

### Results (drought phase, 33 core wells)
Median of the per-well differences, cluster-bootstrap 95 % interval, cluster sign-flip p over
the 14 clusters; Holm over the two models for the main rows only. Positive = the first run is
better.

| Model | Contrast | ΔNSE [95 % CI] | p | Δskill [95 % CI] | p |
|---|---|---|---|---|---|
| LightGBM | **on vs none (main)** | +0.016 [−0.042, 0.051] | 0.71 (Holm 1.0) | +0.003 [−0.023, 0.024] | 1.0 (Holm 1.0) |
| LSTM | **on vs none (main)** | +0.001 [−0.046, 0.163] | 1.0 (Holm 1.0) | +0.001 [−0.021, 0.030] | 1.0 (Holm 1.0) |
| LightGBM | placebo vs none | −0.011 [−0.063, 0.019] | 0.68 | −0.004 [−0.017, 0.010] | 0.84 |
| LightGBM | on vs placebo | −0.014 [−0.059, 0.028] | 0.84 | −0.008 [−0.030, 0.033] | 0.51 |
| LightGBM | wide vs none | +0.009 [−0.062, 0.067] | 1.0 | +0.002 [−0.030, 0.027] | 1.0 |
| LightGBM | frozen vs none | +0.015 [−0.034, 0.058] | 0.38 | +0.010 [−0.011, 0.017] | 0.34 |
| LightGBM | on vs frozen | −0.030 [−0.080, 0.000] | 0.094 | −0.012 [−0.040, 0.000] | 0.031 |
| LSTM | placebo vs none | +0.043 [−0.092, 0.122] | 0.63 | +0.022 [−0.032, 0.070] | 0.63 |
| LSTM | on vs placebo | +0.023 [−0.106, 0.105] | 0.72 | +0.026 [−0.064, 0.036] | 0.76 |
| LSTM | wide vs none | +0.034 [−0.023, 0.159] | 0.062 | +0.014 [−0.006, 0.042] | 0.092 |
| LSTM | frozen vs none | +0.025 [−0.070, 0.073] | 0.74 | +0.004 [−0.019, 0.045] | 0.86 |
| LSTM | on vs frozen | +0.046 [−0.030, 0.191] | 0.29 | +0.016 [−0.016, 0.051] | 0.31 |
| LightGBM | none vs without (reproducibility) | 0.000 | 1.0 | 0.000 | 1.0 |
| LSTM | none vs without (machine effect) | −0.032 [−0.097, 0.006] | 0.22 | −0.018 [−0.041, 0.003] | 0.36 |
| LSTM | on vs without (first wording) | +0.064 [−0.046, 0.112] | 0.15 | +0.019 [−0.037, 0.024] | 0.62 |

- Medians of the per-well drought NSE, for reading: LSTM none 0.090, on 0.017, without (Colab)
  0.124; LightGBM none = without −0.083, on −0.093. A difference of medians is not the median of
  the paired differences: for the LSTM the wells near the median move both ways (on is better
  on 17 of 33 wells).
- **Robustness** (`stats.cluster_sensitivity`, main rows): p 0.63–1.0 under the other cluster
  grids; leaving out any one cluster moves the median difference by at most 0.02.
- Per aquifer group (secondary): Pliocene (20 wells) LightGBM −0.013, LSTM −0.026; karst (6
  wells) LSTM +0.159 [0.021, 0.239], p 0.25, too few clusters to mean anything; the alluvium
  groups (4 and 2 core wells) are too small for the test.

### Reading, as pre-registered
- **No evidence that the crop-thirst index adds predictive information** to the drought-phase
  simulation of the core wells, in either model, and nothing from the placebo, wide or frozen
  rows. The dated index does no better than the 2019 areas frozen (LightGBM slightly worse,
  outside the family), so nothing here supports a statement about crop-area change.
- **How large a gain is excluded:** the intervals exclude median gains above about 0.05 NSE for
  LightGBM; for the LSTM the upper bound is 0.16, so a moderate LSTM gain is not excluded.
- **The machine effect is as large as the effects tested.** The same LSTM configuration trained
  on a Kaggle CPU scores a median 0.032 NSE below its Colab GPU run. Had on vs without stayed the
  main contrast, the LSTM would have shown +0.064, mostly a machine difference. The same-machine
  control (added before any result) prevented that misreading.
- **Hypotheses for the null, not tested:** the index is the climatic deficit, already an input,
  scaled by crop areas that change little within a well; 20 of the 33 core wells are in the
  Pliocene, where heads follow drinking-water pumping, and 84 % of the plain's declared
  irrigation water is surface water (mostly the Têt and Agly canals, Step 6a); the reconstructed
  irrigation pumping already follows the deficit (within-year r = 0.96).
- **For the subject's chain:** land use → model is now tested. As a direct feature on the core
  wells it adds nothing detectable. The agricultural pathway stays open where the data can carry
  it: canal return flow to the alluvium (framing B, CQ6) and the crop-calendar pumping
  reconstruction (3) of the sensitivity runs. The thesis and the paper report this null as a
  result.

### What to consider
- **Phase 4: one machine type per contrast.** Arms that are compared are trained on the same
  machine type, or the contrast carries a same-machine control. To be written into the plan's
  §10 contract at Gate 3 (Assil's decision).
- The alluvium wells, where crops and canals should matter most, are too few among the core
  wells for a group test; the 26 plain wells (secondary report) or a model trained for the
  alluvium could say more, but either would be a new, exploratory analysis.
- Crop demand as a `lulcw:Influence` type of the hybrid still needs its pathway settled at Gate 3
  (§14 item 13); this result is no reason to give it a sign constraint.

## Recurring check (review §"Recurring check"), 2026-10-25
1. *Chain link advanced:* land use → water (LU-1 to LU-3) and the model input (LU-4 code).
2. *Where dated land use enters:* the weekly crop-thirst index per well, pumping
   reconstruction (3) and, once run, the land-use panels of the pre-registered test. Not
   yet in the KG (12.6).
3. *Observed / inferred / assumed / unknown:* crop codes and areas are observed; classes
   are inferred by a written mapping; Kc values and irrigation status are assumed; the
   parcel → water source link is unknown.
4. *Evidence vs plan:* index, reconstruction (3) and checks implemented and tested; the
   model test is coded, not run.
5. *Next model experiment:* LU-4 answers an open question (does land use carry
   information?), not a new baseline.
6. *Still missing from the subject:* land use in the KG (12.6), satellite semantics
   (12.10), explanations of real outputs (CQ10), the scenario (CQ16), forecasting (stated
   as out of scope).

## LU-6, first version (2026-10-26): the chain answered from the graph
- `src/analysis/lu6_example.py` → `docs/lu6_example.md` (generated): for an alluvium well (MILLAS
  C2-1, 718BP02) and a Pliocene well (PONTEILLA NYLS-1, 671AA00), every statement is the answer of
  a stored CQ query of 12.7, with its status: the well and its unit (CQ1, CQ3); the dated crops of
  its 3 km zone 2015–2025 with their potential demand and category (CQ7); the facilities that may
  draw from its unit, their attribution, the influences and how many the main policy accepts (CQ2,
  CQ8); the 2024 accounting of the plain by unit and use (CQ12); the LU-4 result; and what the graph
  cannot say yet.
- What the two cases show: around C2-1, orchards (usually irrigated) dominate and the zone is
  "high" demand every year, yet the main policy accepts only 7 of the 48 pumping paths (2 of them signed),
  because most alluvium boreholes rest on the "possible" exact-entity evidence; around NYLS-1,
  vines dominate (mostly partly irrigated or rainfed classes) and the main policy accepts 9 of the
  103 paths, those of the 2 confident and 7 probable candidates, all with the sign.
  In 2024 all 16.8 Mm³ of the plain's declared irrigation stays unresolved, against 23.1 Mm³ of
  drinking water placed in the Pliocene: the agricultural pathway cannot be carried by the
  borehole links, as stated in the review response §2.
- Not yet in the example: the satellite irrigation rule (CQ15, LU-5), the canal return flow (CQ6),
  an explanation of a model output (CQ10). The final LU-6 (Gate 3) adds them where they exist.
- A bug caught while writing it: IRIs passed to the CQ runner as plain strings became literals and
  matched nothing (zero accepted paths, an empty CQ12 table). `src.kg.cq.term` now refuses a plain
  string.
