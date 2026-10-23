"""Pump -> aquifer unit attribution, with evidence and a measured confidence (task 12.3, CQ2).

    PFE_DATASET=v4 python -m src.kg.pump_attribution

Every groundwater abstraction ouvrage of the dataset gets zero, one or several candidate
units, each with the rule that produced it and a confidence (confident / probable /
possible), or "unknown". Nothing is forced to a single answer (second review, priority 5,
docs/review_codex_2026-10-23.md): main runs use confident links, sensitivity runs add the
others.

Evidence per ouvrage
  record  the BD LISA entity of the ADES quality station that has the ouvrage's BSS code
          (src.ingest.hubeau_qualite_stations), with its investigation depth and nature
  flag    BNPE `nappe_accompagnement`: the pumped aquifer is connected to a river
  stack   the BD LISA level-3 entities under the point, top to bottom. It describes the
          geology, not a proven hydraulic connection
  name    the BNPE point name: PUITS (dug well), PROFOND(E) (deep)

Rules (the first that applies gives the main candidate, rank 1)
  record           the recorded entity                                     confident
                   (probable when the entity is neither under the point nor
                   within EDGE_M of it)
  record_depth     a recent-alluvium record that is deeper than ALLUVIUM_MAX_DEPTH_M
                   or named "profond", above the Pliocene: Pliocene         probable
                   (the recorded entity is kept as rank 2, possible)
  flag_true        no record, flag True: the alluvial entity under the point, else the
                   nearest one within EDGE_M                               measured
  flag_false       no record, flag False, Pliocene in the stack: Pliocene  measured
  dug_well         no record, no flag, named PUITS, alluvium at the point  possible
  single_unit      no record, no flag, one entity in the stack             possible
  otherwise unknown
"measured": probable if the rule's precision on the recorded points (group level, the
record after the depth check as reference) is >= PRECISION_PROBABLE with at least MIN_EVAL
points, else possible. The thresholds were set before the precision was computed. The
measured level holds only for the uses present among the evaluated boreholes (at least
MIN_USE_EVAL of them): the recorded boreholes are drinking-water and industry wells, so an
irrigation borehole attributed by the same rule stays "possible".

Why the depth check: 7 of the 10 recorded "recent alluvium" boreholes with a False flag
are 96-130 m deep, one named "FORAGE DANS NAPPE PROFONDE", while the recorded alluvium
boreholes with a True flag are 6-23 m deep and the alluvium piezometers 9-12 m.
ALLUVIUM_MAX_DEPTH_M = 50 is about twice the deepest of them; the 10th percentile of
the investigation depth of the Pliocene quality stations in the plain is 40 m.
Why EDGE_M = 1000: when the recorded entity is not under the point, it lies a median
819 m away (36 of 130 recorded boreholes): point coordinates and polygon edges are
approximate.

Outputs (data/interim/)
  pump_unit_evidence.parquet       one row per groundwater ouvrage: evidence, use, volume
  pump_unit_attribution.parquet    one row per (ouvrage, candidate): unit, group, rule,
                                   confidence, rank
  pump_unit_attribution_eval.json  precision and recall of each rule on the recorded
                                   boreholes (both directions, by use), the flag x unit
                                   table, coverage by count, volume and use
"""
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio

from src.analysis.bdlisa_profile import GPKG, group_of, stacks_of
from src.config import CRS_L93, CRS_WGS84, DATASET, DATASET_DIR, INTERIM, RAW

BNPE_POINTS = RAW / "hubeau_bnpe" / "2026-10-20" / "points_prelevement_66.parquet"
QUALITY = RAW / "hubeau_qualite" / "stations_66.parquet"
ALLUVIUM_MAX_DEPTH_M = 50.0
EDGE_M = 1000.0
PRECISION_PROBABLE = 0.80
MIN_EVAL = 10
MIN_USE_EVAL = 5
PLIOCENE = "671AA00"
ALLUVIAL = ("recent alluvium", "ancient alluvium")
VOLUME_YEARS = (2012, 2024)  # declared BNPE years (imputed years excluded)


def is_alluvial(code):
    return group_of(code) in ALLUVIAL


def evidence():
    """One row per groundwater ouvrage of the dataset, with every piece of evidence."""
    pts = pd.read_parquet(DATASET_DIR / "pumping_points.parquet")
    gw = pts[pts["source"] == "groundwater"].copy()
    bnpe = pd.read_parquet(BNPE_POINTS)[["code_ouvrage", "nom_point_prelevement",
                                         "nappe_accompagnement", "code_bss_point_eau"]]
    gw = gw.drop(columns="code_bss_point_eau").merge(bnpe, on="code_ouvrage", how="left")
    gw["flag"] = gw["nappe_accompagnement"].map({True: "True", False: "False"}).fillna("empty")
    q = pd.read_parquet(QUALITY)[["code_bss", "codes_entite_hg_bdlisa", "profondeur_investigation",
                                  "nom_nature_pe", "nom_mode_gisement"]]
    q = q.rename(columns={"code_bss": "code_bss_point_eau", "codes_entite_hg_bdlisa": "rec_unit",
                          "profondeur_investigation": "rec_depth_m", "nom_nature_pe": "rec_nature",
                          "nom_mode_gisement": "rec_mode"})
    gw = gw.merge(q, on="code_bss_point_eau", how="left")
    gw["rec_unit"] = gw["rec_unit"].replace("", np.nan)
    assert not gw["rec_unit"].fillna("").str.contains(";").any(), "a record lists several units"

    # use and declared volume per ouvrage
    pw = pd.read_parquet(DATASET_DIR / "pumping_weekly.parquet",
                         columns=["code_ouvrage", "usage", "week", "volume_m3", "imputed"])
    y = pw["week"].dt.year
    pw = pw[~pw["imputed"] & y.between(*VOLUME_YEARS)]
    vol = pw.groupby(["code_ouvrage", "usage"])["volume_m3"].sum().unstack(fill_value=0.0)
    gw["usage_main"] = gw["code_ouvrage"].map(vol.idxmax(axis=1))
    gw["volume_mm3"] = gw["code_ouvrage"].map(vol.sum(axis=1) / 1e6).fillna(0.0)

    # BD LISA stack under the point, and the nearest alluvial entity within EDGE_M
    g = gpd.GeoDataFrame(gw, geometry=gpd.points_from_xy(gw["longitude"], gw["latitude"]),
                         crs=CRS_WGS84).to_crs(CRS_L93)
    poly = pyogrio.read_dataframe(GPKG, layer="POLYG_ELEMENTAIRES",
                                  bbox=tuple(g.total_bounds + [-EDGE_M, -EDGE_M, EDGE_M, EDGE_M]))
    pile = pyogrio.read_dataframe(GPKG, layer="TABLE_PILE_ENTITES_NIV3", read_geometry=False)
    stacks = stacks_of(pile, poly["codepoly"])
    j = gpd.sjoin(g, poly[["codepoly", "geometry"]], how="left", predicate="within")
    j = j[~j.index.duplicated()]
    gw["stack"] = j["codepoly"].map(lambda cp: " > ".join(stacks.get(cp, []))).values
    poly["alluvial"] = poly["codepoly"].map(
        lambda cp: next((c for c in stacks.get(cp, []) if is_alluvial(c)), None))
    allu = poly.dropna(subset=["alluvial"])
    near = gpd.sjoin_nearest(g[["geometry"]], allu[["alluvial", "geometry"]], how="left",
                             max_distance=EDGE_M, distance_col="alluvial_dist_m")
    near = near[~near.index.duplicated()]
    gw["near_alluvial"] = near["alluvial"].values
    gw["near_alluvial_m"] = near["alluvial_dist_m"].round(0).values
    # is the recorded entity under the point or within EDGE_M?
    has = {c: set(s) for c, s in stacks.items()}
    rec = g[gw["rec_unit"].notna().values]
    ok = []
    for i, r in rec.iterrows():
        cand = poly[poly["codepoly"].map(lambda cp: gw.at[i, "rec_unit"] in has.get(cp, ()))]
        ok.append(bool(len(cand)) and cand.distance(r.geometry).min() <= EDGE_M)
    gw["rec_near_point"] = pd.Series(ok, index=rec.index).reindex(gw.index)
    name = gw["nom_point_prelevement"].fillna("").str.upper()
    gw["name_puits"] = name.str.contains(r"\bPUITS\b")
    gw["name_profond"] = name.str.contains("PROFOND")
    return gw


def rules_without_record(r):
    """Main candidate from the flag, the stack and the name (the record is not used)."""
    stack = r["stack"].split(" > ") if r["stack"] else []
    alluvial_here = next((c for c in stack if is_alluvial(c)), None)
    if r["flag"] == "True":
        unit = alluvial_here or r["near_alluvial"]
        return (unit, "flag_true") if isinstance(unit, str) else (None, "flag_true_no_alluvium")
    if r["flag"] == "False":
        return (PLIOCENE, "flag_false") if PLIOCENE in stack else (None, "flag_false_no_pliocene")
    if r["name_puits"] and alluvial_here:
        return alluvial_here, "dug_well"
    if len(stack) == 1:
        return stack[0], "single_unit"
    return None, "unknown"


def record_rule(r):
    """(unit, rule, confidence) from the record, after the depth check; None if no record."""
    u = r["rec_unit"]
    if not isinstance(u, str):
        return None
    stack = r["stack"].split(" > ") if r["stack"] else []
    deep = (r["rec_depth_m"] > ALLUVIUM_MAX_DEPTH_M) or r["name_profond"]
    if group_of(u) == "recent alluvium" and deep and PLIOCENE in stack:
        return PLIOCENE, "record_depth", "probable"
    return u, "record", "confident" if r["rec_near_point"] else "probable"


def evaluate(gw):
    """Precision / recall of the rules on the recorded boreholes (one row per BSS code)."""
    rec = gw[gw["rec_unit"].notna()].drop_duplicates("code_bss_point_eau").copy()
    rec["truth"] = [record_rule(r)[0] for _, r in rec.iterrows()]
    rec["truth_group"] = rec["truth"].map(group_of).replace(dict.fromkeys(ALLUVIAL, "alluvium"))
    pred = [rules_without_record(r) for _, r in rec.iterrows()]
    rec["pred"], rec["rule"] = [p[0] for p in pred], [p[1] for p in pred]
    rec["pred_group"] = rec["pred"].map(lambda u: group_of(u) if isinstance(u, str) else "none")
    rec["pred_group"] = rec["pred_group"].replace(dict.fromkeys(ALLUVIAL, "alluvium"))
    out = {"n_recorded_boreholes": len(rec),
           "n_depth_conflicts": int(sum(record_rule(r)[1] == "record_depth"
                                        for _, r in rec.iterrows())),
           "flag_x_unit": pd.crosstab(rec["truth_group"], rec["flag"]).to_dict(),
           "rules": {}}
    for rule, target in (("flag_true", "alluvium"), ("flag_false", "Pliocene multilayer")):
        fired = rec[rec["rule"] == rule]
        is_target = rec["truth_group"] == target
        n_ok = int((fired["pred_group"] == fired["truth_group"]).sum())
        entity_ok = int((fired["pred"] == fired["truth"]).sum())
        prec = n_ok / len(fired) if len(fired) else np.nan
        raw = fired["rec_unit"].map(group_of).replace(dict.fromkeys(ALLUVIAL, "alluvium"))
        out["rules"][rule] = {
            "fires_on": len(fired), "correct_group": n_ok, "precision_group": round(prec, 3),
            "precision_entity": round(entity_ok / len(fired), 3) if len(fired) else None,
            "precision_group_raw_record": round(float((fired["pred_group"] == raw).mean()), 3),
            # recall: share of the boreholes of the target group that the rule finds
            "recall_group": round(int((is_target & (rec["rule"] == rule)
                                       & (rec["pred_group"] == target)).sum())
                                  / max(int(is_target.sum()), 1), 3),
            "wrong_groups": fired.loc[fired["pred_group"] != fired["truth_group"],
                                      "truth_group"].value_counts().to_dict(),
            "confidence": ("probable" if len(fired) >= MIN_EVAL and prec >= PRECISION_PROBABLE
                           else "possible"),
            "by_use": {u: {"n": len(f), "precision_group": round(
                float((f["pred_group"] == f["truth_group"]).mean()), 3)}
                for u, f in fired.groupby("usage_main") if len(f) >= MIN_USE_EVAL}}
    out["recorded_use_mix"] = rec["usage_main"].value_counts().to_dict()
    return out, rec


def attribute(gw, conf, uses):
    """conf: rule -> measured confidence; uses: rule -> the uses it was evaluated on."""
    rows = []
    for _, r in gw.iterrows():
        base = {"code_ouvrage": r["code_ouvrage"]}
        rr = record_rule(r)
        if rr is not None:
            unit, rule, c = rr
            rows.append(base | {"unit": unit, "rule": rule, "confidence": c, "rank": 1})
            if rule == "record_depth":
                rows.append(base | {"unit": r["rec_unit"], "rule": "record", "rank": 2,
                                    "confidence": "possible"})
            continue
        unit, rule = rules_without_record(r)
        c = conf.get(rule, "possible") if unit else "unknown"
        if c == "probable" and r["usage_main"] not in uses.get(rule, ()):
            c = "possible"  # the rule's precision was not measured on this use
        rows.append(base | {"unit": unit, "rule": rule, "confidence": c, "rank": 1})
    a = pd.DataFrame(rows)
    a["unit_group"] = a["unit"].map(lambda u: group_of(u) if isinstance(u, str) else "unknown")
    return a


def coverage(gw, a):
    main = a[a["rank"] == 1].merge(gw[["code_ouvrage", "zone", "usage_main", "volume_mm3"]],
                                   on="code_ouvrage")
    out = {}
    for zone, m in (("plain", main[main["zone"] == "plain"]), ("all", main)):
        by_conf = m.groupby("confidence").agg(n=("code_ouvrage", "size"),
                                              volume_mm3=("volume_mm3", "sum"))
        by_conf["share_n"] = (by_conf["n"] / by_conf["n"].sum()).round(3)
        by_conf["share_volume"] = (by_conf["volume_mm3"] / by_conf["volume_mm3"].sum()).round(3)
        vol_use = m.pivot_table(index="usage_main", columns="confidence", values="volume_mm3",
                                aggfunc="sum", fill_value=0.0)
        vol_group = m.pivot_table(index="unit_group", columns="confidence",
                                  values="volume_mm3", aggfunc="sum", fill_value=0.0)
        out[zone] = {"by_confidence": by_conf.round(2).to_dict("index"),
                     "volume_mm3_by_use": vol_use.round(2).to_dict("index"),
                     "volume_mm3_by_group": vol_group.round(2).to_dict("index")}
    return out


def main():
    gw = evidence()
    ev, rec = evaluate(gw)
    conf = {rule: v["confidence"] for rule, v in ev["rules"].items()}
    conf |= {"dug_well": "possible", "single_unit": "possible"}
    uses = {rule: set(v["by_use"]) for rule, v in ev["rules"].items()}
    a = attribute(gw, conf, uses)
    ev["coverage"] = coverage(gw, a)
    ev["parameters"] = {"ALLUVIUM_MAX_DEPTH_M": ALLUVIUM_MAX_DEPTH_M, "EDGE_M": EDGE_M,
                        "PRECISION_PROBABLE": PRECISION_PROBABLE, "MIN_EVAL": MIN_EVAL,
                        "MIN_USE_EVAL": MIN_USE_EVAL, "volume_years": VOLUME_YEARS,
                        "dataset": DATASET}
    INTERIM.mkdir(parents=True, exist_ok=True)
    gw.to_parquet(INTERIM / "pump_unit_evidence.parquet", index=False)
    a.to_parquet(INTERIM / "pump_unit_attribution.parquet", index=False)
    (INTERIM / "pump_unit_attribution_eval.json").write_text(
        json.dumps(ev, indent=1, ensure_ascii=False, default=str))

    pd.set_option("display.width", 200)
    print(f"{len(gw)} groundwater ouvrages ({int((gw['zone'] == 'plain').sum())} in the plain); "
          f"{int(gw['rec_unit'].notna().sum())} with a recorded unit "
          f"({ev['n_recorded_boreholes']} distinct boreholes, "
          f"{ev['n_depth_conflicts']} depth conflicts)")
    print("\nrecorded boreholes: reference group x BNPE flag")
    print(pd.DataFrame(ev["flag_x_unit"]).fillna(0).astype(int).to_string())
    for rule, v in ev["rules"].items():
        print(f"\n{rule}: fires on {v['fires_on']}, group precision {v['precision_group']} "
              f"(raw record {v['precision_group_raw_record']}), "
              f"entity precision {v['precision_entity']}, recall {v['recall_group']} "
              f"-> {v['confidence']}; wrong: {v['wrong_groups']}; by use: {v['by_use']}")
    print(f"\nrecorded boreholes by use: {ev['recorded_use_mix']}")
    for zone in ("plain", "all"):
        c = ev["coverage"][zone]
        print(f"\n[{zone}] main candidate by confidence (count, Mm3 {VOLUME_YEARS[0]}-"
              f"{VOLUME_YEARS[1]}):")
        print(pd.DataFrame(c["by_confidence"]).T.to_string())
        print(f"[{zone}] volume (Mm3) by use x confidence:")
        print(pd.DataFrame(c["volume_mm3_by_use"]).T.fillna(0).round(1).to_string())
        print(f"[{zone}] volume (Mm3) by unit group x confidence:")
        print(pd.DataFrame(c["volume_mm3_by_group"]).T.fillna(0).round(1).to_string())
    print(f"\n-> {INTERIM / 'pump_unit_attribution.parquet'}")


if __name__ == "__main__":
    main()
