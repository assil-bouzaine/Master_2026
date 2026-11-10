"""Node and edge tables of the graph arms, from the validated graph release (task 12.8, step 2).

    PFE_DATASET=v4 python -m src.kg.export                     # main policy
    PFE_DATASET=v4 python -m src.kg.export --policy confident-only

One node inventory, two edge tables that differ only in the rule that makes the edges (analysis
plan §10, §14 items 14-18):

  arm C  distance rules only, those of the Taccari-style baseline (src/models/taccari.py) applied
         to single facilities: a well's 3 nearest wells; its nearest SAFRAN cell; its 2 nearest
         pool gauges; every groundwater facility within C_PUMP_KM; the plain's canal node for the
         wells of the plain.
  arm D  every edge comes from the knowledge graph, read through the competency-question queries
         (src.kg.cq) like the inventory: the influences the export policy selects (pumping from the
         facilities attributed to the well's unit within 5 km; recharge proxies from the weather
         cells over the outcrop of its unit, in its 5 km zone, and unit-wide as a sensitivity
         relation; river exchange from the pool gauge of an associated watercourse; canal return
         where a return is documented) and the same-unit well links. Where the graph holds no
         link, D has none: never a distance fallback.

Several evidence paths between one driver and one well make one edge (item 17): it lists the
number of paths, carries a sign only if every path gives the same one, and is eligible, or
constrained, only if every path is. "constrained" follows the policy's constraint decisions
(until Gate 3 only pumping). Weights: the same functions of distance in both arms, so that the
arms differ in which edges exist, not in how an edge is weighted: pumping exp(-d / 5 km), well
links exp(-d / sigma) with sigma the median distance of C's 3-nearest links; recharge edges carry
the cell's share of the outcrop in D and 1 in C; river and canal edges 1 in D, C's river edges
exp(-d / median well-gauge distance) as in the baseline.

D also lists, per well, the groundwater facilities of the dataset within 5 km that no selected
pumping edge connects to it (relation "pumping_unattributed"): the volume outside the policy enters
every model as an explicit input, never as zero (analysis plan §8). The well links keep their
depth difference: the threshold is chosen per regime from that regime's training heads (item 15),
not here. Arms E and F (rewired, random, complete) are drawn from these tables when the arms run.

Output: data/processed/kg/export_<dataset>_<policy>/nodes.parquet, edges_C.parquet,
edges_D.parquet, manifest.json (the release's hashes, the policy, the code version, counts, the
wells without each relation). tests/test_export.py checks the tables against the inventory,
against whole-graph queries and against pandas rules on the source tables (the equivalence test).
"""
import argparse
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import rdflib

from src.analysis.piezo_profile import PLAIN_BBOX
from src.config import CRS_L93, CRS_WGS84, DATASET, DATASET_DIR, RAW, ROOT
from src.kg import release
from src.kg.build_kg import git_version
from src.kg.cq import KG, ask, kg_store, local
from src.kg.inventory import MECHANISM, dataset_wells
from src.models.features import NEAR_CANDIDATES, RIVERS

D_IRI = "https://w3id.org/lulcw/data/"
C_NEAREST_WELLS, C_NEAREST_GAUGES = 3, 2
C_PUMP_KM = 10.0            # arm C: facilities within this distance
PUMP_DECAY_M = 5000.0       # both arms: pumping weight exp(-d / 5 km)
D_RADIUS_M = 5000.0         # the search radius of the graph's pumping and well-link rules
CANAL = "canal-intakes:plain"
EDGE_COLS = ["relation", "src_type", "src", "dst", "weight", "distance_m", "n_paths", "sign",
             "eligible", "constrained", "depth_diff_m", "association_types"]


def l93(lon, lat):
    p = gpd.GeoSeries(gpd.points_from_xy(lon, lat), crs=CRS_WGS84).to_crs(CRS_L93)
    return p.x.to_numpy(), p.y.to_numpy()


def tables():
    """The source tables both arms read: wells, groundwater facilities, pool gauges, cells."""
    wells = pd.read_parquet(DATASET_DIR / "wells.parquet")
    wells["x93"], wells["y93"] = l93(wells["x"], wells["y"])
    lon0, lat0, lon1, lat1 = PLAIN_BBOX
    wells["in_plain"] = wells["x"].between(lon0, lon1) & wells["y"].between(lat0, lat1)
    pts = pd.read_parquet(DATASET_DIR / "pumping_points.parquet")
    fac = pts[pts["source"] == "groundwater"].drop_duplicates("code_ouvrage").copy()
    fac["x93"], fac["y93"] = l93(fac["longitude"], fac["latitude"])
    g = pd.read_parquet(DATASET_DIR / "gauges.parquet").set_index("code_station")
    pool = sorted(set(NEAR_CANDIDATES) | set(RIVERS.values()))
    gauges = g.loc[pool].reset_index()
    gauges["x93"], gauges["y93"] = l93(gauges["longitude_station"], gauges["latitude_station"])
    cells = pd.read_parquet(RAW / "safran" / "grid_cells_66.parquet")
    cells["x93"], cells["y93"] = l93(cells["lon"], cells["lat"])
    return wells, fac, gauges, cells


def _dist(a, b):
    return np.hypot(a["x93"].to_numpy()[:, None] - b["x93"].to_numpy()[None],
                    a["y93"].to_numpy()[:, None] - b["y93"].to_numpy()[None])


def link_sigma(wells):
    """Median distance of the 3-nearest-well links: the decay length of every well link."""
    d = _dist(wells, wells)
    return float(np.median(np.sort(d, axis=1)[:, 1:C_NEAREST_WELLS + 1]))


def edge(relation, src_type, src, dst, weight, distance_m=None, n_paths=1, sign=None,
         eligible=False, constrained=False, depth_diff_m=None, association_types=None):
    return dict(zip(EDGE_COLS, (relation, src_type, src, dst, float(weight),
                                None if distance_m is None else float(distance_m), int(n_paths), sign,
                                bool(eligible), bool(constrained), depth_diff_m, association_types)))


def edges_c(wells, fac, gauges):
    """Arm C: distance rules only."""
    rows, codes = [], wells["code_bss"].to_numpy()
    d = _dist(wells, wells)
    sigma = link_sigma(wells)
    pairs = set()
    for i in range(len(codes)):
        for j in np.argsort(d[i], kind="stable")[1:C_NEAREST_WELLS + 1]:
            pairs |= {(i, int(j)), (int(j), i)}                    # symmetric
    rows += [edge("well_link", "well", codes[j], codes[i], np.exp(-d[i, j] / sigma), d[i, j])
             for i, j in sorted(pairs)]
    rows += [edge("recharge", "weather_cell", c, w, 1.0) for w, c in zip(codes, wells["cell_id"])]
    dg = _dist(wells, gauges)
    med = float(np.median(dg))
    for i in range(len(codes)):
        for j in np.argsort(dg[i], kind="stable")[:C_NEAREST_GAUGES]:
            rows.append(edge("river", "gauge", gauges["code_station"].iloc[j], codes[i],
                             np.exp(-dg[i, j] / med), dg[i, j]))
    df = _dist(wells, fac)
    for i in range(len(codes)):
        for j in np.where(df[i] <= C_PUMP_KM * 1000)[0]:
            rows.append(edge("pumping", "facility", fac["code_ouvrage"].iloc[j], codes[i],
                             np.exp(-df[i, j] / PUMP_DECAY_M), df[i, j]))
    rows += [edge("canal", "canal", CANAL, w, 1.0) for w in codes[wells["in_plain"].to_numpy()]]
    return pd.DataFrame(rows, columns=EDGE_COLS)


def aggregate(paths):
    """One edge from the selected evidence paths of one driver and one well (item 17)."""
    signs = {local(p["responseSign"]) for p in paths}
    one_sign = len(signs) == 1
    dist = [p["distanceM"] for p in paths if p["distanceM"] is not None]
    w = [p["cellWeight"] for p in paths if p["cellWeight"] is not None]
    types = sorted({p["associationType"] for p in paths if p["associationType"]})
    return {"n_paths": len(paths), "sign": signs.pop() if one_sign else "mixed",
            "eligible": one_sign and all(local(p["eligibility"]) == "EligibleConstraint" for p in paths),
            "constrained": one_sign and all(p["constrained"] for p in paths),
            "distance_m": min(dist) if dist else None,
            "cell_weight": float(np.mean(w)) if w else None,
            "association_types": " ".join(types) or None}


SRC_TYPE = {"pumping": "facility", "recharge": "weather_cell", "recharge_unitwide": "weather_cell",
            "river": "gauge", "canal": "canal"}


def edges_d(store, kg_wells, wells, fac, policy):
    """Arm D: the selected influences and well links of the graph, one edge per driver and well."""
    rows, sigma = [], link_sigma(wells)
    dfac = _dist(wells, fac)
    fac_codes = fac["code_ouvrage"].to_numpy()
    row_of = {c: i for i, c in enumerate(wells["code_bss"])}
    for w in kg_wells.itertuples():
        W = rdflib.URIRef(w.iri)
        by = {}
        for r in ask(store, "cq08_influences", W=W, policy=policy):
            if not r["selected"]:
                continue
            rel = MECHANISM[local(r["mechanism"])]
            if rel == "recharge" and r["extent"] and r["extent"].endswith("forcing-cells"):
                rel = "recharge_unitwide"
            by.setdefault((rel, r["driverCode"]), []).append(r)
        for (rel, src), paths in sorted(by.items()):
            a = aggregate(paths)
            weight = (np.exp(-a["distance_m"] / PUMP_DECAY_M) if rel == "pumping"
                      else a["cell_weight"] if rel.startswith("recharge") else 1.0)
            rows.append(edge(rel, SRC_TYPE[rel], src, w.code_bss, weight, a["distance_m"], a["n_paths"],
                             a["sign"], a["eligible"], a["constrained"], None, a["association_types"]))
        linked = {src for (rel, src) in by if rel == "pumping"}
        i = row_of[w.code_bss]
        for j in np.where(dfac[i] <= D_RADIUS_M)[0]:        # the explicit unattributed input
            if fac_codes[j] not in linked:
                rows.append(edge("pumping_unattributed", "facility", fac_codes[j], w.code_bss,
                                 np.exp(-dfac[i, j] / PUMP_DECAY_M), dfac[i, j]))
        for r in ask(store, "cq11_neighbours", W=W, r=D_RADIUS_M, policy=policy):
            if r["selected"]:
                rows.append(edge("well_link", "well", r["neighbourCode"], w.code_bss,
                                 np.exp(-r["distanceM"] / sigma), r["distanceM"],
                                 depth_diff_m=r["depthDifferenceM"]))
    return pd.DataFrame(rows, columns=EDGE_COLS)


def nodes_of(edge_tables, wells, fac, gauges, cells):
    """One node inventory for every arm: the wells and every source an arm connects."""
    used = pd.concat(edge_tables)[["src_type", "src"]].drop_duplicates()
    out = [pd.DataFrame({"type": "well", "code": wells["code_bss"], "x93": wells["x93"], "y93": wells["y93"],
                         "core": wells["core"], "group": wells["group"], "unit": wells["code_bdlisa"],
                         "in_plain": wells["in_plain"], "has_series": True})]
    f = fac.set_index("code_ouvrage")
    for t, table, has in (("facility", f, True), ("weather_cell", cells.set_index("cell_id"), True),
                          ("gauge", gauges.set_index("code_station"), True)):
        codes = sorted(used.loc[used["src_type"] == t, "src"])
        known = [c in table.index for c in codes]
        out.append(pd.DataFrame({"type": t, "code": codes,
                                 "x93": [table.loc[c, "x93"] if k else np.nan for c, k in zip(codes, known)],
                                 "y93": [table.loc[c, "y93"] if k else np.nan for c, k in zip(codes, known)],
                                 "has_series": known}))
    out.append(pd.DataFrame({"type": ["canal"], "code": [CANAL], "x93": [np.nan], "y93": [np.nan],
                             "has_series": [True]}))
    n = pd.concat(out, ignore_index=True)
    n.insert(0, "node_id", np.arange(len(n)))
    return n


def counts(edges, wells):
    """Per relation: edges, wells with one (all, core), eligible and constrained edges, and the
    core wells without the relation."""
    core = set(wells.loc[wells["core"], "code_bss"])
    out = {}
    for rel, g in edges.groupby("relation", sort=True):
        has = set(g["dst"])
        out[rel] = {"edges": int(len(g)), "wells": len(has), "core_wells": len(has & core),
                    "sources": int(g["src"].nunique()), "eligible": int(g["eligible"].sum()),
                    "constrained": int(g["constrained"].sum()),
                    "core_wells_without": sorted(core - has)}
    return out


def out_dir(policy, dataset=DATASET):
    return KG / f"export_{dataset}_{policy}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--policy", default="main", choices=("main", "confident-only", "all-links"))
    args = ap.parse_args()
    m = release.check()
    store = kg_store()
    wells, fac, gauges, cells = tables()
    kg_wells = dataset_wells(store)
    ec = edges_c(wells, fac, gauges)
    ed = edges_d(store, kg_wells, wells, fac, rdflib.URIRef(D_IRI + f"policy/{args.policy}"))
    nodes = nodes_of([ec, ed], wells, fac, gauges, cells)
    out = out_dir(args.policy)
    out.mkdir(parents=True, exist_ok=True)
    nodes.to_parquet(out / "nodes.parquet", index=False)
    ec.to_parquet(out / "edges_C.parquet", index=False)
    ed.to_parquet(out / "edges_D.parquet", index=False)
    no_series = nodes[~nodes["has_series"]]
    meta = {"dataset": DATASET, "policy": args.policy, "release": m["released"],
            "release_files": {k: v["sha256"] for k, v in m["files"].items()},
            "code_version": git_version(("src/kg", "ontology", "configs", "tests/cq")),
            "rules": {"C": {"nearest_wells": C_NEAREST_WELLS, "nearest_gauges": C_NEAREST_GAUGES,
                            "pump_km": C_PUMP_KM}, "D": {"radius_m": D_RADIUS_M},
                      "pump_decay_m": PUMP_DECAY_M, "well_link_sigma_m": link_sigma(wells)},
            "nodes": nodes["type"].value_counts().to_dict(),
            "nodes_without_series": {t: sorted(g["code"]) for t, g in no_series.groupby("type")},
            "arms": {"C": counts(ec, wells), "D": counts(ed, wells)}}
    (out / "manifest.json").write_text(json.dumps(meta, indent=1))
    for arm in ("C", "D"):
        print(f"arm {arm}: " + "; ".join(f"{rel} {c['edges']} edges, {c['wells']} wells ({c['core_wells']} core)"
                                         for rel, c in meta["arms"][arm].items()))
    print(f"nodes: {meta['nodes']}; without a series: "
          f"{ {t: len(v) for t, v in meta['nodes_without_series'].items()} }")
    print(f"-> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
