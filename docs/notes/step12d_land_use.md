# Step 12d: the land-use thread (after the Codex review of 2026-10-25)

## What was done (2026-10-25)
- Checked `docs/review_codex_2026-10-25.md` against the code: no dated land use
  entered the dataset, the baselines or the KG. Verdicts and the working road:
  `docs/review_codex_2026-10-25_response.md`.
- Assil decided: annual RPG 2015–2025; CQ7, CQ10, CQ15 → MUST; a pre-registered
  land-use test (`docs/analysis_plan.md` §14 item 13).
- **LU-1 started.** `src/ingest/rpg.py` now finds every edition name (2019 has no date
  suffix; 2024–25 are GeoPackages), and with `--clip-plain --drop-raw` writes
  `data/interim/rpg_plain_<year>.parquet` and then deletes the raw archive.
- **LU-2 started.** `configs/lu_crop_classes.csv`: 14 harmonised crop classes, each
  with its FAO-56 Kc (Table 12) and stage lengths (Table 11), checked on
  fao.org/4/X0490E/x0490e0b.htm on 2026-10-25, plus an irrigation *assumption*
  (usually / partly / rainfed / none). Every crop code in the plain, 2016 and 2023,
  falls into exactly one class.

## Why
The subject asks how land use and agricultural practices affect water. The
project's chain had a missing first link. In Roussillon most irrigation water comes
from canals, and the farm-borehole links stay "possible". So the agricultural signal
must enter as crop demand (timing and place of farm pumping) and canal return flow,
not through pump → unit links.

## What to consider
- **Codes change; land does not always change.** From 2016 to 2023, peaches (PVT) went
  from 1 to 2,129 ha while "other orchards" (VRG) lost 1,650 ha: peaches got their own
  code. Harmonised, orchards are 9.1 % → 9.4 % of the plain's declared area. Grassland
  grows from 36.6 % to 40.7 % because pastoral land (SPL, SPH) was newly declared, a
  registration effect. Trends are read on harmonised classes and on a stable
  footprint only (LU-1 check).
- **Potential demand is not irrigation.** The Kc index is a crop water requirement
  minus rain. Whether a parcel is irrigated, and from which source, are separate
  facts (CQ7, CQ15).
- **The irrigation assumptions are unverified.** They must be checked against the
  Agreste 2020 census (irrigated area by crop, dept 66) before LU-3 uses them.
- **Nut stages** come from a Utah row (FAO-56 has no Mediterranean walnut row). The
  class covers 0.1 % of the area.
- Before 2015 there is no parcel-level RPG: the 2015 mix is backfilled and flagged
  (RPG v1 2007–2014 has group-level crop shares per anonymous block, an option if the
  backfill matters).

## Recurring check (review §"Recurring check"), 2026-10-25
1. *Chain link advanced:* land use (LU-1, LU-2).
2. *Where dated land use enters:* nowhere yet in the model or the KG. After LU-3:
   the weekly demand feature and pumping reconstruction (3); after 12.6: parcel-year
   observations in the KG.
3. *Observed / inferred / assumed / unknown:* crop codes and areas are observed. The
   classes are inferred by a written mapping. Kc values and irrigation status are
   assumed. The parcel → water source link is unknown.
4. *Evidence vs plan:* class coverage is tested on 2016 and 2023 (0 unmapped
   parcels). Everything else is still a plan.
5. *Next model experiment:* LU-4 answers an open question (does land use carry
   information?), not a new baseline.
6. *Still missing from the subject:* satellite semantics (12.10), explanations of real
   outputs (CQ10), the scenario (CQ16), forecasting (stated as out of scope).
