"""Checks of the graph export (src/kg/export.py, task 12.8): the equivalence test.

    PFE_DATASET=v4 python -m tests.test_export            # ~2-3 min (GeoPandas overlays)

The export reads arm D's edges through the competency-question queries. Here the same edge lists
are obtained three other ways, and arm C's rules are recomputed by brute force:

1. Identity: the manifest binds the tables to the current validated release; every edge endpoint
   is a node; one node per code; both arms use the one node inventory.
2. D against the inventory (src/kg/inventory.py): per well and relation, the same sources,
   eligible and constrained edges; the well links and their counts under each depth threshold.
3. D against whole-graph queries written here, not the CQ files: per well and mechanism, the
   number of distinct drivers of the influences the policy selects.
4. D against pandas rules on the source tables (never on the graph's answers):
   - pumping, exact-unit edges: the attribution table of task 12.3 and the BNPE points: a facility
     attributed to the well's recorded unit within 5 km, at a confidence the policy admits
     (tests.test_cq.pump_oracle restates the confidences); distances within 0.5 m;
   - recharge edges and their weights, local and unit-wide: GeoPandas on BD LISA and the raw
     SAFRAN grid (tests.test_kg_rules.oracle_coverage), weights within 1e-5, summing to 1;
   - the unattributed input: with the pumping edges it is exactly the dataset's groundwater
     facilities within 5 km of the well, each once.
   River and canal edges rest on curated documentary evidence: their source-level oracle is
   tests.test_kg_rules.test_data_rivers (BD TOPO reaches x BD LISA polygons); here they are
   covered by checks 2 and 3.
5. C by brute force: one weather edge (the well's own cell), the 2 nearest pool gauges, every
   groundwater facility within 10 km and no other, at least 3 symmetric well links, the canal for
   the wells of the plain; the distance weights of pumping and well links follow the same
   functions in both arms.
Equal edges are necessary, not sufficient, for equal predictions (analysis plan §10): node order,
features, masks and a fixed-weight forward pass are compared when the tensors are built.
"""
import json

import numpy as np
import pandas as pd

from src.config import DATASET, DATASET_DIR
from src.kg import export as E
from src.kg import release
from src.kg.cq import KG, kg_store
from src.kg.inventory import THRESHOLDS, tag

POLICY = "main"
PRE = ("PREFIX lulcw: <https://w3id.org/lulcw#> PREFIX prov: <http://www.w3.org/ns/prov#> "
       "BASE <https://w3id.org/lulcw/data/> ")
MECH = {"PumpingDrawdown": "pumping", "DiffuseRecharge": "recharge", "RiverExchange": "river",
        "CanalReturnFlow": "canal"}


def load():
    out = E.out_dir(POLICY)
    return (pd.read_parquet(out / "nodes.parquet"), pd.read_parquet(out / "edges_C.parquet"),
            pd.read_parquet(out / "edges_D.parquet"), json.loads((out / "manifest.json").read_text()))


def test_identity(nodes, ec, ed, meta):
    m = release.check()
    assert meta["release"] == m["released"] and meta["release_files"] == {
        k: v["sha256"] for k, v in m["files"].items()}, "the export was made from another release: run src.kg.export"
    assert not nodes.duplicated(["type", "code"]).any()
    have = set(zip(nodes["type"], nodes["code"]))
    for name, e in (("C", ec), ("D", ed)):
        missing = (set(zip(e["src_type"], e["src"])) | {("well", c) for c in e["dst"]}) - have
        assert not missing, f"arm {name}: edge endpoints that are not nodes: {sorted(missing)[:5]}"
        assert not e.duplicated(["relation", "src", "dst"]).any(), f"arm {name}: a driver connected twice"
    assert nodes["has_series"].all(), "a node without an input series"
    print(f"  1. export bound to the release of {meta['release']}; {len(nodes)} nodes "
          f"({nodes['type'].value_counts().to_dict()}), every edge endpoint is one, no driver twice")


def test_inventory(ed):
    inv = pd.read_parquet(KG / f"inventory_{DATASET}_{POLICY}.parquet")
    n = 0
    for r in inv.itertuples():
        e = ed[(ed["relation"] == r.relation) & (ed["dst"] == r.code_bss)]
        want = set(r.sources.split()) if isinstance(r.sources, str) and r.sources else set()
        assert set(e["src"]) == want, (r.code_bss, r.relation, sorted(set(e["src"]) ^ want)[:4])
        if r.relation == "well_link":
            for t in THRESHOLDS:
                got = len(e) if t is None else int((e["depth_diff_m"].abs() <= t).sum())
                assert got == getattr(r, f"links_{tag(t)}"), (r.code_bss, t)
        else:
            assert int(e["eligible"].sum()) == r.eligible and int(e["constrained"].sum()) == r.constrained, \
                (r.code_bss, r.relation)
        n += len(e)
    print(f"  2. arm D = the inventory: {n} edges, the same sources per well and relation, the same eligible "
          f"and constrained edges, the same links under each depth threshold")


def test_graph(store, ed):
    got = {}
    for b, mech, wide, n in store.query(PRE + f"""
            SELECT ?b ?mech ?wide (COUNT(DISTINCT ?drv) AS ?n) WHERE {{
              ?i a lulcw:Influence ; lulcw:selectedUnder <policy/{POLICY}> ; lulcw:mechanism ?mech ;
                 lulcw:driverEntity ?drv ; lulcw:targetEntity/lulcw:bssCode ?b .
              OPTIONAL {{ ?i lulcw:withinExtent ?s }}
              BIND (BOUND(?s) && !STRSTARTS(STR(?s), STR(<outcrop-zone/>)) AS ?wide) }}
            GROUP BY ?b ?mech ?wide"""):
        rel = MECH[mech.value.rsplit("#", 1)[-1]]
        if rel == "recharge" and wide.value == "true":
            rel = "recharge_unitwide"
        got[(b.value, rel)] = int(n.value)
    e = ed[ed["relation"].isin(set(MECH.values()) | {"recharge_unitwide"})]
    want = e.groupby(["dst", "relation"]).size().to_dict()
    assert got == want, sorted(set(got.items()) ^ set(want.items()))[:6]
    print(f"  3. arm D = whole-graph queries: {len(want)} (well, relation) pairs, the same number of distinct "
          f"drivers among the influences the policy selects ({sum(want.values())} edges)")


def test_pandas(store, ed):
    from tests.test_cq import ADMITS, pump_oracle
    from tests.test_kg_rules import RADIUS, l93, oracle_coverage
    wells = pd.read_parquet(DATASET_DIR / "wells.parquet")
    wx, wy = l93(wells["x"], wells["y"])
    # pumping, exact unit
    gw, fac, attr, best = pump_oracle()
    a = attr.dropna(subset=["unit"])
    a = a[a["code_ouvrage"].isin(fac.index)].join(fac[["x93", "y93"]], on="code_ouvrage")
    conf = np.where(a["rank"] == 1, a["code_ouvrage"].map(best["exact_conf"]), a["confidence"])
    a = a[pd.Series(conf, index=a.index).isin(ADMITS[POLICY])]
    want = {}
    for b, u, x, y in zip(wells["code_bss"], wells["code_bdlisa"], wx, wy):
        if isinstance(u, str):
            m = a[a["unit"] == u]
            dist = np.hypot(m["x93"] - x, m["y93"] - y)
            for c, dd in zip(m["code_ouvrage"], dist):
                if dd <= RADIUS:
                    want[(c, b)] = min(dd, want.get((c, b), np.inf))
    e = ed[(ed["relation"] == "pumping") & ed["eligible"]]
    got = dict(zip(zip(e["src"], e["dst"]), e["distance_m"]))
    assert set(got) == set(want), f"pumping edges differ: {sorted(set(got) ^ set(want))[:6]}"
    assert all(abs(got[k] - want[k]) < 0.5 for k in want)
    assert (e["sign"] == "NegativeResponse").all() and e["constrained"].all()
    n_pump = len(want)
    # recharge: cells and weights
    described = {r[0].value for r in store.query(
        PRE + "SELECT ?c WHERE { ?u lulcw:bdlisaCode ?c ; prov:wasDerivedFrom ?r }")}
    oracle = oracle_coverage(described, wells)
    n_rch = 0
    for kind, rel in (("local", "recharge"), ("unit-wide", "recharge_unitwide")):
        e = ed[ed["relation"] == rel]
        got = {b: dict(zip(g["src"], g["weight"])) for b, g in e.groupby("dst")}
        want, sliver = {}, set()
        for b, u in zip(wells["code_bss"], wells["code_bdlisa"]):
            if not isinstance(u, str) or u not in described:
                continue
            o, c, by_cell = oracle.get((b if kind == "local" else "forcing-cells", u), (0.0, 0.0, {}))
            if o >= 50.0 and c > 0:
                want[b] = {cell: v / c for cell, v in by_cell.items() if v >= 1.0}
            elif o > 0:
                sliver.add(b)
        assert set(got) - sliver == set(want), (rel, sorted((set(got) - sliver) ^ set(want))[:6])
        for b, cells in want.items():
            big = {c for c, w in cells.items() if w > 1e-5}
            assert big <= set(got[b]) and all(abs(got[b].get(c, 0.0) - w) <= 1e-5 for c, w in cells.items()), (rel, b)
            assert abs(sum(got[b].values()) - 1) <= 1e-9, (rel, b)
        assert (e["sign"] == "PositiveResponse").all() and e["eligible"].all() and not e["constrained"].any()
        n_rch += len(e)
    # the unattributed input
    t_wells, t_fac, _, _ = E.tables()
    d = E._dist(t_wells, t_fac)
    codes = t_fac["code_ouvrage"].to_numpy()
    n_un = 0
    for i, b in enumerate(t_wells["code_bss"]):
        near = set(codes[d[i] <= E.D_RADIUS_M])
        un = set(ed[(ed["relation"] == "pumping_unattributed") & (ed["dst"] == b)]["src"])
        pu = set(ed[(ed["relation"] == "pumping") & (ed["dst"] == b)]["src"])
        assert not (un & pu) and un == near - pu, b
        n_un += len(un)
    print(f"  4. arm D = pandas rules on the source tables: {n_pump} exact-unit pumping edges (attribution table, "
          f"BNPE points, distances within 0.5 m), {n_rch} recharge edges with their weights (GeoPandas on BD LISA "
          f"and the SAFRAN grid), {n_un} unattributed facility-well pairs = the other groundwater facilities "
          f"within 5 km")


def test_arm_c(ec, ed):
    wells, fac, gauges, _ = E.tables()
    codes = wells["code_bss"].to_numpy()
    w = ec[ec["relation"] == "recharge"].set_index("dst")["src"]
    assert len(w) == len(wells) and (w.reindex(codes).to_numpy() == wells["cell_id"].to_numpy()).all()
    dg = E._dist(wells, gauges)
    r = ec[ec["relation"] == "river"]
    for i, b in enumerate(codes):
        e = r[r["dst"] == b]
        assert len(e) == 2 and e["distance_m"].max() <= np.sort(dg[i])[1] + 1e-6, b
    df = E._dist(wells, fac)
    p = ec[ec["relation"] == "pumping"]
    assert len(p) == int((df <= E.C_PUMP_KM * 1000).sum()) and p["distance_m"].max() <= E.C_PUMP_KM * 1000
    k = ec[ec["relation"] == "well_link"]
    pairs = set(zip(k["src"], k["dst"]))
    assert all((b, a) in pairs for a, b in pairs) and k.groupby("dst").size().min() >= E.C_NEAREST_WELLS
    assert set(ec[ec["relation"] == "canal"]["dst"]) == set(codes[wells["in_plain"].to_numpy()])
    assert not ec["eligible"].any() and not ec["constrained"].any() and ec["sign"].isna().all()
    sigma = E.link_sigma(wells)
    for e in (ec, ed):
        x = e[e["relation"].isin(("pumping", "pumping_unattributed"))]
        assert np.allclose(x["weight"], np.exp(-x["distance_m"] / E.PUMP_DECAY_M))
        x = e[e["relation"] == "well_link"]
        assert np.allclose(x["weight"], np.exp(-x["distance_m"] / sigma))
    print(f"  5. arm C by brute force: {len(w)} weather edges (each well's own cell), {len(r)} river edges (2 nearest "
          f"pool gauges), {len(p)} pumping edges (every groundwater facility within {E.C_PUMP_KM:g} km), {len(k)} "
          f"symmetric well links, the canal for the {wells['in_plain'].sum()} wells of the plain; no sign in C; "
          f"the same distance weights in both arms")


def main():
    nodes, ec, ed, meta = load()
    store = kg_store()
    test_identity(nodes, ec, ed, meta)
    test_inventory(ed)
    test_graph(store, ed)
    test_pandas(store, ed)
    test_arm_c(ec, ed)
    print("test_export: all checks passed")


if __name__ == "__main__":
    main()
