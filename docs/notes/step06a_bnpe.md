# Step 6a: BNPE water abstraction

**Date:** 2026-10-05 · **Status:** done

## What was done

| Script | What it does |
|---|---|
| `src/ingest/hubeau_bnpe.py` | Downloads the abstraction points (3,061) and the annual volumes (16,965 rows, 2012–2023) for dept 66 from Hub'Eau. |
| `src/analysis/bnpe_profile.py` | Joins volumes to points to get the water source. Keeps the facilities inside the plain (same box as the piezometers). Sums by use × source and draws the annual chart. |

```bash
.venv/Scripts/python -m src.ingest.hubeau_bnpe
.venv/Scripts/python -m src.analysis.bnpe_profile
```

### Results: plain, cumulative 2012–2023 (Mm³)

| Use | Surface water | Groundwater | Groundwater share | First run (surface / ground) |
|---|---|---|---|---|
| Irrigation | **741** | **144** | 16% | 811 / 144 |
| Drinking water | **3** | **475** | 99% | 20 / 483 |
| Canal intakes ("CANAUX") | 1,245 | 15 | 1% | not reported |
| Industry | 1 | 9 | n/a | n/a |
| Hydropower (turbined) | 192 | 0 | n/a | n/a |

- **Irrigation is 84% surface water** (93% if canal intakes are counted as
  irrigation).
- **Drinking water is 99% groundwater.**

Chart: `reports/figures/bnpe_plain_annual.png`.

## Why

- **What the BNPE is.** Anyone abstracting more than a threshold volume
  pays a fee to the Water Agency (here the Agence de l'Eau Rhône Méditerranée
  Corse, AERMC). To pay it, they declare their annual volume. The BNPE
  collects these declarations: who takes how much water, from where, and for
  what.
- **Why the source matters for the thesis.** The subject document's causal
  story is "crops → irrigation pumping → water table falls". That story only
  holds if irrigation water comes from the aquifer. Here it mostly doesn't.
- **Why classify by `code_type_milieu`.** Each point is labelled CONT
  (continental surface water: river, canal, reservoir) or SOUT (souterrain,
  i.e. groundwater). The `code_bdlisa` field would tell us *which* aquifer,
  but it is empty for every single point. The first run used it and got a
  false "0% groundwater".
- **Why volumes and sources are joined.** Volumes are attached to the
  *facility* (`code_ouvrage`); the water source is attached to the *point*. We
  checked that every facility has exactly one point, so the join is
  unambiguous. The script stops if that ever changes.
- **Why hydropower is set aside.** Water through a turbine goes straight
  back to the river. It is not consumed and has nothing to do with the
  aquifer.

## What to consider

### 1. The key finding: the plain's two water systems are almost separate

| | Irrigation | Drinking water |
|---|---|---|
| Main source | Rivers, through historic gravity canals fed by intakes on the Têt, Tech, Agly and the Villeneuve-de-la-Raho reservoir | The aquifer (mostly the deep Pliocene, Step 4) |

This matters for the project framing (memo, Step 7). The simple "crops pump
groundwater" chain is weak here. Two sharper framings, both for the
supervisor to choose between:

- **Use conflict on the Pliocene aquifer.** Drinking water depends almost
  entirely on it, and groundwater irrigation is growing beside it. The
  groundwater share of irrigation rises from about 10% (2012–2017) to about
  23% (2021–2022).
- **Canal-return recharge.** Canals and gravity irrigation leak water into
  the shallow alluvium, which recharges the aquifer. In that case less canal
  water (a falling trend since 2017) would mean *less recharge*, and land use
  acts on groundwater through infiltration rather than pumping.

### 2. Groundwater irrigation "doubling" in 2018 is mostly paperwork

The number of boreholes declaring groundwater irrigation jumps from about 370
to about 950 in 2018 (bottom panel of the chart). Volume rises at the same
time (7 → 16 Mm³/yr). Real pumping does not triple in one year. More likely
the declaration or collection rules changed in 2018, but this is not yet
verified. **Treat 2012–2017 and 2018–2023 groundwater irrigation as two
different regimes.** Never fit a trend across the break.

### 3. Caveats for the memo

- **The most recent year (2023) is under-reported.** Declarations take
  months to consolidate. Canal intake falls from 74 to 36 Mm³ and surface
  irrigation from 62 to 48 Mm³. Part of that may be real (2022–2023 were
  very dry years in the Pyrénées-Orientales), part is missing declarations;
  we can't separate the two yet. Rerun the download in a year and compare.
- **Small boreholes are missing.** Abstractions below the declaration
  threshold (domestic and small farm wells, which are numerous in the
  Roussillon) are not in the BNPE. **Groundwater irrigation is a lower
  bound.**
- **Canal intakes are not irrigation volumes.** "CANAUX" is what enters the
  canal at the river intake. Part returns to rivers, part leaks into the
  ground, part reaches the fields. That is why we report it separately and
  give the 84% / 93% range.
- **Canal intakes are falling** (≈130 → ≈75 Mm³/yr, 2017 → 2022). Possible
  reasons are drought restrictions, canal modernisation, or reporting
  changes. This is worth one question to the supervisor or the local
  irrigation syndicate, because it feeds the recharge framing directly.

### 4. Differences with the first run

- **Irrigation from surface water:** 741 vs 811 Mm³.
- **Drinking water from surface water:** 3 vs 20 Mm³.
- **The groundwater numbers almost match:** 144 = 144 and 475 vs 483.

The first run's exact plain extent was not recorded. The most likely cause
is a slightly larger area: intakes and reservoirs on the plain's edge fall
in or out depending on where the line is drawn. The conclusions
(≈85% surface irrigation, ≈99% groundwater drinking water) are unchanged.

### 5. Practical lesson: be gentle with Hub'Eau

Asking for 5,000 rows per page got the connection cut, and then Hub'Eau
refused everything from this computer for about 10 minutes. The script now
asks for 2,000 rows. If it happens again: stop, wait 10–15 minutes and
rerun. The cache means nothing already downloaded is lost.
