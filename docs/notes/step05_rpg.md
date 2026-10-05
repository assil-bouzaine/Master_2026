# Step 5: RPG agricultural parcels

**Date:** 2026-10-05 · **Status:** done

## What was done

| Script | What it does |
|---|---|
| `src/ingest/rpg.py` | Lists all RPG editions from IGN, picks Occitanie (R76) 2016 and 2023, downloads the `.7z` archives, verifies them and extracts them. Also fetches IGN's official crop-code tables. |
| `src/analysis/rpg_profile.py` | Cuts the parcels to the plain. Keeps the parcels whose centre is within 3 km of a working-set piezometer. Computes the statistics and draws the chart. |

```bash
.venv/Scripts/python -m src.ingest.rpg            # ~5 min first time (850 MB)
.venv/Scripts/python -m src.analysis.rpg_profile  # ~30 s first time, faster after
```

### Results: parcels within 3 km of the 33 working-set piezometers

| | 2016 | 2023 | First run |
|---|---|---|---|
| Parcels | 7,914 | **10,222** | ~11,000 |
| Declared area | 11,697 ha | **14,021 ha** | ~15,800 ha |
| Median parcel | 0.74 ha | 0.74 ha | 0.75 ha |
| Vines (share / ha) | 38.1% / 4,455 ha | **32.2% / 4,511 ha** | ~33% |
| Orchards | 19.2% / 2,251 ha | 19.2% / 2,699 ha | ~18% |
| Olives | 2.4% / 285 ha | 2.3% / 321 ha | ~2% |

Chart (hectares by crop group, both years): `reports/figures/rpg_3km_groups.png`.
Full table: `data/interim/rpg_3km_groups.csv`.

The 2023 numbers are a little below the first run (10.2k vs 11k parcels).
That is expected: we have 33 piezometers instead of 34, so the 3 km zone is
slightly smaller. The first run's exact zone rule is also unknown (centroid
or intersection).

## Why

- **What the RPG is.** Every year, farmers who ask for EU subsidies (the
  CAP) draw their parcels and declare the crop. IGN publishes an anonymised
  version. It is the most detailed open land-use map of French farmland: the
  crop of every parcel, every year.
- **Why within 3 km of the piezometers.** The water table under a well is
  influenced by what happens on the land around it: irrigation, infiltration
  under crops, pumping. A 3 km circle is a simple first proxy for "the area
  that influences this well". In the GNN, these zones will become the land
  use attached to each piezometer node.
- **Why centroids.** A parcel crossing the 3 km line is counted once, with
  its full area, if its centre is inside. Without this rule, overlapping
  circles around nearby wells would count the same parcel twice.
- **Why compare at `CODE_GROUP` level.** The detailed crop codes
  (`CODE_CULTU`) change almost every year as the administration adds codes
  (IGN added 18 in 2017 and 20 in 2018). At that level, a change can just be
  a renamed code. Groups (vines, orchards, cereals…) are stable.
- **Why we download the official code table.** `CODE_GROUP` is just a
  number. The meaning (21 = vines) comes from IGN's reference table,
  `REF_CULTURES_GROUPES_CULTURES_2023.csv`, not from memory. That makes the
  labels citable in the thesis.

## What to consider

### 1. Shares lie when the total changes; always look at hectares

The vine share drops from 38% to 32%, which looks like vineyards
disappearing. In hectares, vines are **stable** (4,455 → 4,511 ha). The
total declared area grew by about 2,300 ha:

| Group | Change 2016 → 2023 |
|---|---|
| Pasture / scrubland (`Estives et landes`) | +822 ha |
| Permanent grassland | +529 ha |
| Orchards | +448 ha |
| Fallow | +220 ha |
| "Other cereals" | −312 ha |

That growth pushes the vine share down. This is a classic trap. The chart and
the CSV now show hectares next to shares.

### 2. A large part of the "change" is in the register, not on the ground

About 4,200 ha of 2023 parcels sit where **no parcel at all** was declared in
2016, including 968 ha of vines. Vineyards don't appear from nothing in seven
years. More likely, more land was *declared*:

- more farms applying for aid;
- rule changes, such as the 2023 CAP reform, which might have brought pasture
  and landes into the register.

This is a hypothesis, not yet verified. For the thesis:

- The RPG measures declared farmland, not total land cover. Non-subsidised
  parcels (some vineyards, hobby farms, abandoned land) are missing.
- Comparing two RPG years mixes real land-use change with changes in who
  declares.
- This is one reason the project plans to use **AlphaEarth satellite
  embeddings** (Phase 2). Satellites see every pixel, declared or not.

### 3. Conclusion to carry forward

Land use around the wells is **stable for the main crops**: vines about
4,500 ha, olives about 300 ha, vegetables about 600 ha. Orchards grew by
about 20%. The landscape is dominated by vines (~1/3) and orchards (~1/5).
These are perennial crops. Step 6a's water-abstraction data will show how
much irrigation water they get and whether it comes from canals (surface
water) or boreholes (groundwater).

### 4. Practical notes

- **The IGN listing is rate-limited.** Requests that are too fast get
  "429 Too Many Requests", so the script pauses 1 s between pages.
- **The 2016 edition name has a different pattern**
  (`R76-2016_2016-01-01` vs `R76_2023-01-01`). The regex accepts both. If
  IGN renames again, the script stops and prints the available names.
- **Newer editions.** 2024 and 2025 are now available, in GeoPackage format,
  RPG v4.0. If the supervisor wants a more recent year, add `--years 2024`;
  the script may need a small change for GeoPackage.
- **Text encoding.** The 2023 reference CSV is in Windows-1252, not UTF-8.
  Read it with `encoding="cp1252"`, or the accents turn into `�`.
- **Disk space.** The extracted shapefiles take 2 GB, but we only use about
  20 MB of GeoParquet in `data/interim/`. You can delete the extracted
  folders later; the `.7z` archives are enough to recreate them.
