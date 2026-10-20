"""BNPE annual volumes for dataset v3: completed, harmonised and imputed by documented rules.

    from src.dataset.bnpe_v3 import harmonise, restricted_years
    annual = harmonise(load_bnpe("2026-10-20"), restricted_years(), 2003, 2026)

Every rule comes from a check on the data (docs/notes/step12a_dataset_v3.md):

1. Missing usage. 177 rows of 2024 have no usage code; they take the usage the same
   ouvrage declares in other years (dropped if it never declares one).
2. 2018 reporting break. The 2017 -> 2018 jump of groundwater irrigation (8.7 -> 15.7
   Mm3 in the plain) is entirely made of ouvrages declaring for the first time in 2018
   or 2019 (708 of 1,517). These boreholes are back-filled from the first BNPE year to
   the year before their first declaration with the mean of their first three declared
   years.                                                                  [break2018]
3. Consolidation lag. In the last two published years, an ouvrage that declared the
   year before but not this year gets last year's volume x R, where R is the volume
   ratio of the ouvrages of the same source x usage that really declared both years
   (at least MIN_PANEL of them).                                            [gap_ratio]
   If R cannot be estimated (surface canal intakes in 2024: 1 of 39 declared), that
   source x usage x year is treated as unpublished (rule 4).
4. Unpublished years (after the last published year, or rule 3 impossible):
   - surface water: decided by the drought orders of the Têt surface-water alert zones
     (VigiEau; triggered by river flow, so no groundwater information leaks in). A
     year with at least CRISE_DAYS days at 'crise' between April and September is a
     restricted year and takes each ouvrage's volume of the last published restricted
     year (2023: canal intakes of the ouvrages that declared both years fell to 0.54 x
     2022). Other years take the mean of the last three published normal years.
                                                         [restricted | recent_normal]
   - groundwater: mean of the last three published years (after rule 3). [recent_mean]
   Means count a year without declaration as zero, as in v2 (one-off declarers must
   not inflate the fill).
5. Years before the first BNPE year (2012): each ouvrage's mean of the first three
   years, as in v2.                                                         [backfill]
"""
import numpy as np
import pandas as pd

from src.config import DEPARTEMENT, INTERIM

MIN_PANEL = 5
CRISE_DAYS = 30


def restricted_years(dept=DEPARTEMENT):
    """Years whose Têt surface-water zones spent >= CRISE_DAYS days at 'crise' in Apr-Sep."""
    lv = pd.read_parquet(INTERIM / f"vigieau_levels_daily_{dept}.parquet")
    s = lv[(lv["type"] == "SUP") & lv["zone"].str.contains("Têt") & lv["day"].dt.month.between(4, 9)]
    crise = (s.groupby("day")["level"].max() >= 4)
    days = crise.groupby(crise.index.year).sum()
    return {int(y) for y, n in days.items() if n >= CRISE_DAYS}, {int(y) for y in days.index}


def _mean_zero(vol, years):
    years = [y for y in years if y in vol.columns]
    return vol[years].fillna(0).mean(axis=1) if years else pd.Series(np.nan, index=vol.index)


def harmonise(d, restricted, start_year, end_year, zone_of=None):
    """d: BNPE rows (code_ouvrage, annee, volume, usage, code_usage, source).
    restricted: (set of restricted years, set of years covered by the orders).
    zone_of: code_ouvrage -> zone (e.g. 'plain' / 'outside'). Rules 3 and 4 are estimated
    per source x usage x zone: the plain's Têt canals and the mountain canals of Cerdagne
    are restricted and declared on different schedules (in 2024, 148 mountain canals
    had declared and none of the plain's 39 canal intakes).
    Returns one row per ouvrage x source x usage x year with columns volume,
    imputation ('' = reported) and imputed, plus a log of the rules applied."""
    restr, covered = restricted
    d = d.copy()
    known = (d.dropna(subset=["code_usage"]).groupby("code_ouvrage")["usage"]
             .agg(lambda s: s.mode().iat[0]))
    miss = d["code_usage"].isna()
    d.loc[miss, "usage"] = d.loc[miss, "code_ouvrage"].map(known)
    log = [f"rule 1: {int(miss.sum())} rows without usage, "
           f"{int(d.loc[miss, 'usage'].isna().sum())} dropped (ouvrage never declares one)"]
    d = d.dropna(subset=["usage"])
    d = d[~d["usage"].astype(str).str.startswith("hydropower")]
    d["zone"] = d["code_ouvrage"].map(zone_of) if zone_of is not None else "all"
    d["zone"] = d["zone"].fillna("outside")
    a = d.groupby(["source", "usage", "zone", "code_ouvrage", "annee"])["volume"].sum()
    vol = a.unstack("annee")
    first, last = int(vol.columns.min()), int(vol.columns.max())
    for y in range(start_year, end_year + 1):
        if y not in vol.columns:
            vol[y] = np.nan
    vol = vol[sorted(vol.columns)]
    vol.columns.name = "annee"
    imp = pd.DataFrame("", index=vol.index, columns=vol.columns)
    imp[vol.isna()] = None
    groups = list(vol.index.droplevel("code_ouvrage").unique())

    # rule 2: 2018 reporting break (groundwater irrigation)
    n_new = 0
    for grp in [g for g in groups if g[:2] == ("groundwater", "irrigation")]:
        gi = vol.loc[grp]
        fy = gi.notna().idxmax(axis=1).where(gi.notna().any(axis=1))
        for o in fy[fy.isin([2018, 2019])].index:
            y0 = int(fy[o])
            v = gi.loc[o, list(range(y0, last + 1))].dropna().iloc[:3].mean()
            for y in range(first, y0):
                vol.loc[grp + (o,), y] = v
                imp.loc[grp + (o,), y] = "break2018"
            n_new += 1
    log.append(f"rule 2: {n_new} groundwater-irrigation ouvrages first declared in 2018/2019 "
               f"back-filled to {first}")

    # rule 3: consolidation lag in the last two published years
    unpublished = set()
    for y in (last - 1, last):
        for grp in groups:
            v, i = vol.loc[grp], imp.loc[grp]
            both = (i[y - 1] == "") & (i[y] == "")
            if both.sum() < MIN_PANEL:
                unpublished.add((grp, y))
                log.append(f"rule 3: {grp} {y}: {int(both.sum())} ouvrages declared both years "
                           f"-> unpublished (rule 4)")
                continue
            R = v.loc[both, y].sum() / v.loc[both, y - 1].sum()
            fill = v[y - 1].notna() & v[y].isna()
            idx = [grp + (o,) for o in v.index[fill]]
            if idx:
                vol.loc[idx, y] = vol.loc[idx, y - 1].to_numpy() * R
                imp.loc[idx, y] = "gap_ratio"
            log.append(f"rule 3: {grp} {y}: R = {R:.2f} from {int(both.sum())} ouvrages, "
                       f"{len(idx)} filled")

    # rule 4: unpublished years
    pub_restr = sorted(y for y in restr if first <= y <= last)
    for grp in groups:
        src = grp[0]
        years = [y for y in range(last + 1, end_year + 1)] + \
                sorted(y for g, y in unpublished if g == grp)
        published = [y for y in range(first, last + 1) if (grp, y) not in unpublished]
        v = vol.loc[grp]
        for y in years:
            todo = v[y].isna()
            if src == "surface":
                if y not in covered and y > last:
                    raise ValueError(f"no drought orders for {y}: cannot classify it")
                if y in restr:
                    # last published restricted year of this source x usage, else its last
                    # published year
                    ref = [r for r in pub_restr if r in published][-1:] or published[-1:]
                    label = "restricted"
                    fillv = _mean_zero(v, ref)
                else:
                    ref = [p for p in published if p not in restr][-3:]
                    label = "recent_normal"
                    fillv = _mean_zero(v, ref)
            else:
                ref = published[-3:]
                label = "recent_mean"
                fillv = _mean_zero(v, ref)
            idx = [grp + (o,) for o in v.index[todo]]
            if idx:
                vol.loc[idx, y] = fillv[todo].to_numpy()
                imp.loc[idx, y] = label
            v = vol.loc[grp]
            log.append(f"rule 4: {grp} {y}: {label} from {ref}, "
                       f"{fillv[todo].sum() / 1e6:.1f} Mm3 over {int(todo.sum())} ouvrages")

    # rule 5: before the first BNPE year
    back = _mean_zero(vol, [first, first + 1, first + 2])
    for y in range(start_year, first):
        vol[y] = back
        imp[y] = "backfill"
    log.append(f"rule 5: {start_year}-{first - 1} back-filled with each ouvrage's "
               f"{first}-{first + 2} mean")

    out = vol.stack(future_stack=True).dropna().rename("volume").to_frame()
    out["imputation"] = imp.stack(future_stack=True).reindex(out.index).fillna("")
    out = out.reset_index()
    out = out[out["volume"] > 0]
    out["imputed"] = out["imputation"] != ""
    return out, log
