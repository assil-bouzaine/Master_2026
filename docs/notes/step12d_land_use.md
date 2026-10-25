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
