"""Coverage of the pump -> unit attribution, by use x unit group x year (third review §3.4).

    PFE_DATASET=v4 python -m src.kg.pump_coverage

The headline of task 12.3 (main links = 72 % of the plain's groundwater volume) was computed
on each facility's main use, over 2012-2024, at unit-group resolution. Two facts change it
(docs/review_codex_2026-10-24.md §3.4):
- the KG of task 12.5 states the flag_true rule at two resolutions: "probable" for the
  alluvium group (group precision 0.947), "possible" for the exact BD LISA unit (entity
  precision 0.632 < 0.80). A graph whose edges go to exact units sees less volume;
- a model sees the weekly reconstruction, imputed rows included (2005-2011 backfill, the
  2018-break harmonisation of 2012-2017, 2025-26), not the declared rows only.
This script recomputes the coverage on what the model sees: the weekly groundwater pumping of
the dataset, by its actual use (a facility's minor uses are not folded into its main use),
summed per calendar year of the week label, assigned to the facility's main candidate (rank
1; an alternative is never added) with its confidence at both resolutions. The exact-unit
confidence follows src.kg.build_kg (measured(): the same thresholds as task 12.3).

Policies (CLAUDE.md §3, decided 2026-10-24): main = confident + probable; sensitivity =
confident only, and all links (+ possible). Volume outside a policy is reported as
"unattributed" with its reason (possible, unknown), never as zero pumping.

Also reported: Wilson 95 % intervals of the rule precisions measured on the recorded
boreholes (they assume independent boreholes and say nothing of selection bias).

Outputs
    data/interim/pump_unit_coverage.csv   zone x year x imputed x use x group x rule x
                                          confidence at both resolutions -> volume (m3)
    docs/pump_coverage.md                 tables (generated; do not edit by hand)
Nothing is fitted here.
"""
import json
from statistics import NormalDist

import pandas as pd

from src.config import DATASET, DATASET_DIR, INTERIM, ROOT
from src.kg import pump_attribution as pa

RANK = {"unknown": 0, "possible": 1, "probable": 2, "confident": 3}
POLICIES = {"confident only": ("confident",), "main (confident + probable)": ("confident", "probable"),
            "all links": ("confident", "probable", "possible")}
MEASURED_RULES = ("flag_true", "flag_false")
OUT_MD = ROOT / "docs" / "pump_coverage.md"


def wilson(k, n, z=NormalDist().inv_cdf(0.975)):
    """Wilson score interval of k successes out of n."""
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z / (1 + z * z / n) * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5
    return c - h, c + h


def exact_confidence(a, ev, usage_main):
    """Confidence of each rank-1 candidate at exact-unit resolution (as in build_kg)."""
    out = a["confidence"].copy()
    for rule in MEASURED_RULES:
        r = ev["rules"][rule]
        m = (a["rule"] == rule) & a["unit"].notna()
        use_ok = a.loc[m, "code_ouvrage"].map(usage_main).isin(r["by_use"])
        ok = (r["fires_on"] >= pa.MIN_EVAL) & (r["precision_entity"] >= pa.PRECISION_PROBABLE)
        exact = use_ok.map(lambda u: "probable" if (u and ok) else "possible")
        out[m] = [min(c, e, key=RANK.get) for c, e in zip(a.loc[m, "confidence"], exact)]
    return out


def coverage_table():
    ev = json.loads((INTERIM / "pump_unit_attribution_eval.json").read_text())
    evid = pd.read_parquet(INTERIM / "pump_unit_evidence.parquet").set_index("code_ouvrage")
    a = pd.read_parquet(INTERIM / "pump_unit_attribution.parquet")
    a = a[a["rank"] == 1].copy()
    assert a["code_ouvrage"].is_unique, "one main candidate per facility"
    a["conf_exact"] = exact_confidence(a, ev, evid["usage_main"])
    a = a.rename(columns={"confidence": "conf_group"})
    pw = pd.read_parquet(DATASET_DIR / "pumping_weekly.parquet",
                         columns=["code_ouvrage", "usage", "week", "volume_m3", "imputed"])
    pw = pw[pw["code_ouvrage"].isin(evid.index)]          # groundwater facilities only
    pw["year"] = pw["week"].dt.year
    t = (pw.groupby(["code_ouvrage", "year", "imputed", "usage"])["volume_m3"].sum()
         .reset_index().merge(a[["code_ouvrage", "unit", "unit_group", "rule", "conf_group",
                                 "conf_exact"]], on="code_ouvrage", how="left"))
    missing = t["rule"].isna()
    assert not missing.any(), f"{t.loc[missing, 'code_ouvrage'].nunique()} facilities without a rank-1 row"
    t["zone"] = t["code_ouvrage"].map(evid["zone"])
    keys = ["zone", "year", "imputed", "usage", "unit_group", "rule", "conf_group", "conf_exact"]
    return t.groupby(keys)["volume_m3"].sum().reset_index(), ev


def shares(t, by=()):
    """Share of volume inside each policy, at both resolutions (rows: by + resolution)."""
    rows = []
    for key, g in (t.groupby(list(by)) if by else [((), t)]):
        tot = g["volume_m3"].sum()
        for res, col in (("unit group", "conf_group"), ("exact unit", "conf_exact")):
            r = dict(zip(by, key if isinstance(key, tuple) else (key,))) | {
                "resolution": res, "total_Mm3": tot / 1e6}
            for name, keep in POLICIES.items():
                r[name] = g.loc[g[col].isin(keep), "volume_m3"].sum() / tot if tot else float("nan")
            r["unknown"] = g.loc[g[col] == "unknown", "volume_m3"].sum() / tot if tot else float("nan")
            rows.append(r)
    return pd.DataFrame(rows)


def by_year(t):
    """One row per year: total, imputed share, main policy at both resolutions, all links."""
    rows = []
    for y, g in t.groupby("year"):
        tot = g["volume_m3"].sum()
        main = POLICIES["main (confident + probable)"]
        rows.append({"year": y, "total_Mm3": round(tot / 1e6, 1),
                     "imputed %": round(100 * g.loc[g["imputed"], "volume_m3"].sum() / tot, 1),
                     "main, unit group %": round(100 * g.loc[g["conf_group"].isin(main), "volume_m3"].sum() / tot, 1),
                     "main, exact unit %": round(100 * g.loc[g["conf_exact"].isin(main), "volume_m3"].sum() / tot, 1),
                     "all links %": round(100 * g.loc[g["conf_exact"] != "unknown", "volume_m3"].sum() / tot, 1),
                     "unknown %": round(100 * g.loc[g["conf_exact"] == "unknown", "volume_m3"].sum() / tot, 1)})
    return pd.DataFrame(rows)


def pct(df):
    out = df.copy()
    for c in list(POLICIES) + ["unknown"]:
        out[c] = (100 * out[c]).round(1)
    out["total_Mm3"] = out["total_Mm3"].round(1)
    return out


def main():
    t, ev = coverage_table()
    INTERIM.mkdir(parents=True, exist_ok=True)
    t.to_csv(INTERIM / "pump_unit_coverage.csv", index=False)
    plain = t[t["zone"] == "plain"]
    declared = plain[~plain["imputed"] & plain["year"].between(*pa.VOLUME_YEARS)]
    model = plain[plain["year"].between(2005, plain["year"].max())]

    s_decl = pct(shares(declared))
    s_model = pct(shares(model))
    big = declared.groupby("usage")["volume_m3"].sum().gt(0.05e6)
    s_use = pct(shares(declared[declared["usage"].map(big)], ("usage",)))
    s_year_dw = by_year(model[model["usage"] == "drinking water"])
    s_year_irr = by_year(model[model["usage"] == "irrigation"])
    main_pol = POLICIES["main (confident + probable)"]
    grp = (declared.assign(main=declared["conf_exact"].isin(main_pol))
           .pivot_table(index=["usage", "unit_group"], columns="main", values="volume_m3",
                        aggfunc="sum", fill_value=0.0).div(1e6).round(2)
           .rename(columns={True: "main policy, exact unit (Mm3)",
                            False: "outside the main policy (Mm3)"}).reset_index())

    prec = []
    for rule, r in ev["rules"].items():
        n = r["fires_on"]
        for what, k in (("group", r["correct_group"]),
                        ("exact unit", round(r["precision_entity"] * n)),
                        ("group, raw record", round(r["precision_group_raw_record"] * n))):
            lo, hi = wilson(k, n)
            prec.append({"rule": rule, "reference": what, "correct": k, "n": n,
                         "precision": round(k / n, 3), "wilson_lo": round(lo, 3),
                         "wilson_hi": round(hi, 3), "confidence threshold": pa.PRECISION_PROBABLE})
    prec = pd.DataFrame(prec)

    y0, y1 = pa.VOLUME_YEARS
    md = [
        "# Coverage of the pump → unit links (generated)\n",
        f"Generated by `src/kg/pump_coverage.py` (dataset {DATASET}); do not edit by hand. "
        "Groundwater facilities of the plain; volume of the dataset's weekly reconstruction, "
        "split by actual use, assigned to each facility's main candidate (rank 1). "
        "\"Unit group\" = the resolution at which task 12.3 measured its rules; "
        "\"exact unit\" = the BD LISA entity, as stated in the KG (flag_true is only "
        "\"possible\" there). Shares in % of the volume; outside a policy = unattributed, "
        "never zero pumping.\n",
        f"## Declared years {y0}–{y1} (imputed rows excluded)\n",
        s_decl.to_markdown(index=False), "",
        "## What the model sees: 2005 → end of record, imputed rows included\n",
        s_model.to_markdown(index=False), "",
        f"## By use, declared years {y0}–{y1}\n",
        s_use.to_markdown(index=False), "",
        f"## By use and unit group, declared years {y0}–{y1}, main policy at exact-unit "
        "resolution (Mm³)\n",
        grp.to_markdown(index=False), "",
        "## Drinking water by year (model forcing, imputed rows included)\n",
        "Years are the calendar years of the week labels. Flat weekly weights (7/365.25 of the "
        "annual volume) give a year with 53 week labels 1.9 % more than a year with 52 "
        "(2006, 2012, 2017, 2023: see `tests/test_pumping_conservation.py`).\n",
        s_year_dw.to_markdown(index=False), "",
        "## Irrigation by year (model forcing, imputed rows included)\n",
        s_year_irr.to_markdown(index=False), "",
        "## Rule precision on the recorded boreholes, with Wilson 95 % intervals\n",
        "The intervals assume independent boreholes; they do not cover selection bias or "
        "spatial dependence, and a rule's precision is not the probability of one link.\n",
        prec.to_markdown(index=False), "",
    ]
    OUT_MD.write_text("\n".join(md) + "\n")

    pd.set_option("display.width", 200, "display.max_columns", 20)
    print(f"declared {y0}-{y1}, plain:\n{s_decl.to_string(index=False)}")
    print(f"\nmodel forcing 2005-, plain:\n{s_model.to_string(index=False)}")
    print(f"\nby use, declared:\n{s_use.to_string(index=False)}")
    print(f"\n{prec.to_string(index=False)}")
    print(f"\n-> {INTERIM / 'pump_unit_coverage.csv'}, {OUT_MD}")


if __name__ == "__main__":
    main()
