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
     SAFRAN grid (tests.test_kg_rules.oracle_coverage), applying the Gate 3 point 12 cutoff
     (cell share >= 0.001) independently on every side (inventory, whole-graph queries, pandas
     oracle), weights within 1e-5, no well losing all recharge edges, manifest drop counts equal
     to each oracle's;
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
import math

import numpy as np
import pandas as pd
import rdflib

from src.config import DATASET, DATASET_DIR, ROOT
from src.kg import export as E
from src.kg import release
from src.kg.cq import KG, ask, kg_store
from src.kg.inventory import THRESHOLDS, dataset_wells, edges_of, summarise, tag

POLICY = "main"
MIN_CELL_SHARE = 0.001      # Gate 3 point 12, applied independently of src.kg.export
RECHARGE_RELS = ("recharge", "recharge_unitwide", "recharge_leakage")
D_IRI = "https://w3id.org/lulcw/data/"
PRE = ("PREFIX lulcw: <https://w3id.org/lulcw#> PREFIX prov: <http://www.w3.org/ns/prov#> "
       "BASE <https://w3id.org/lulcw/data/> ")
MECH = {"PumpingDrawdown": "pumping", "DiffuseRecharge": "recharge", "VerticalLeakage": "recharge_leakage",
        "RiverExchange": "river", "CanalReturnFlow": "canal"}


def load():
    out = E.out_dir(POLICY)
    return (pd.read_parquet(out / "nodes.parquet"), pd.read_parquet(out / "edges_C.parquet"),
            pd.read_parquet(out / "edges_D.parquet"), json.loads((out / "manifest.json").read_text()))



def _dropped(meta, rel):
    """The manifest's record of the dropped recharge edges of a relation: edges and wells (the
    oracles recount them), after checking its eligible and constrained counts are consistent."""
    d = meta["dropped_small_cells"][rel]
    assert 0 <= d["constrained"] <= d["eligible"] <= d["edges"], (rel, d)
    return {"edges": d["edges"], "wells": d["wells"]}

def test_identity(nodes, ec, ed, meta):
    m = release.check()
    assert meta["release"] == m["released"] and meta["release_files"] == {
        k: v["sha256"] for k, v in m["files"].items()}, "the export was made from another release: run src.kg.export"
    assert meta["rules"]["D"]["min_cell_share"] == MIN_CELL_SHARE
    assert not nodes.duplicated(["type", "code"]).any()
    have = set(zip(nodes["type"], nodes["code"]))
    for name, e in (("C", ec), ("D", ed)):
        missing = (set(zip(e["src_type"], e["src"])) | {("well", c) for c in e["dst"]}) - have
        assert not missing, f"arm {name}: edge endpoints that are not nodes: {sorted(missing)[:5]}"
        assert not e.duplicated(["relation", "src", "dst"]).any(), f"arm {name}: a driver connected twice"
    assert nodes["has_series"].all(), "a node without an input series"
    for rel in RECHARGE_RELS:
        rch = ed[ed["relation"] == rel]
        assert (rch["weight"] >= MIN_CELL_SHARE).all(), (rel, float(rch["weight"].min()))
    print(f"  1. export bound to the release of {meta['release']}; {len(nodes)} nodes "
          f"({nodes['type'].value_counts().to_dict()}), every edge endpoint is one, no driver twice, "
          f"every D recharge weight >= {MIN_CELL_SHARE:g}")


def test_inventory(store, ed, meta):
    inv = pd.read_parquet(KG / f"inventory_{DATASET}_{POLICY}.parquet")
    iri_of = dict(zip(*dataset_wells(store)[["code_bss", "iri"]].to_numpy().T))
    policy_iri = rdflib.URIRef(D_IRI + f"policy/{POLICY}")
    inf_by_well = {}
    dropped = {rel: {"edges": 0, "wells": set()} for rel in RECHARGE_RELS}
    n = 0
    for r in inv.itertuples():
        e = ed[(ed["relation"] == r.relation) & (ed["dst"] == r.code_bss)]
        want = set(r.sources.split()) if isinstance(r.sources, str) and r.sources else set()
        if r.relation in RECHARGE_RELS:
            if r.code_bss not in inf_by_well:
                inf_by_well[r.code_bss] = edges_of(ask(store, "cq08_influences",
                                                       W=rdflib.URIRef(iri_of[r.code_bss]), policy=policy_iri))
            raw = inf_by_well[r.code_bss][r.relation]
            assert set(raw) == want, (r.code_bss, r.relation, sorted(set(raw) ^ want)[:4])
            kept = {}
            for src, paths in raw.items():
                ws = [p["cellWeight"] for p in paths if p["cellWeight"] is not None]
                if math.fsum(ws) / len(ws) < MIN_CELL_SHARE:
                    dropped[r.relation]["edges"] += 1
                    dropped[r.relation]["wells"].add(r.code_bss)
                else:
                    kept[src] = paths
            if raw:
                assert kept, (r.code_bss, r.relation, "lost every recharge edge")
            rec = summarise(kept) if kept else {"eligible": 0, "constrained": 0}
            assert set(e["src"]) == set(kept), (r.code_bss, r.relation, sorted(set(e["src"]) ^ set(kept))[:4])
            assert int(e["eligible"].sum()) == rec["eligible"] and int(e["constrained"].sum()) == rec["constrained"], \
                (r.code_bss, r.relation)
        else:
            assert set(e["src"]) == want, (r.code_bss, r.relation, sorted(set(e["src"]) ^ want)[:4])
            if r.relation == "well_link":
                for t in THRESHOLDS:
                    got = len(e) if t is None else int((e["depth_diff_m"].abs() <= t).sum())
                    assert got == getattr(r, f"links_{tag(t)}"), (r.code_bss, t)
            else:
                assert int(e["eligible"].sum()) == r.eligible and int(e["constrained"].sum()) == r.constrained, \
                    (r.code_bss, r.relation)
        n += len(e)
    for rel in RECHARGE_RELS:
        assert _dropped(meta, rel) == {
            "edges": dropped[rel]["edges"], "wells": sorted(dropped[rel]["wells"])}, (rel, "inventory")
    print(f"  2. arm D = the inventory (with cell share >= {MIN_CELL_SHARE:g} applied on its own weights): "
          f"{n} edges, the same sources per well and relation, the same eligible and constrained edges, "
          f"the same links under each depth threshold")


def test_graph(store, ed, meta):
    by = {}
    for b, mech, wide, drv, w in store.query(PRE + f"""
            SELECT ?b ?mech ?wide ?drv ?w WHERE {{
              ?i a lulcw:Influence ; lulcw:selectedUnder <policy/{POLICY}> ; lulcw:mechanism ?mech ;
                 lulcw:driverEntity ?drv ; lulcw:targetEntity/lulcw:bssCode ?b .
              OPTIONAL {{ ?i lulcw:withinExtent ?s }}
              OPTIONAL {{ ?cw lulcw:cellWeight ?w . ?i prov:wasDerivedFrom ?cw . }}
              BIND (BOUND(?s) && !STRSTARTS(STR(?s), STR(<outcrop-zone/>)) AS ?wide) }}"""):
        rel = MECH[mech.value.rsplit("#", 1)[-1]]
        if rel == "recharge" and wide.value == "true":
            rel = "recharge_unitwide"
        ws = by.setdefault((b.value, rel, drv.value), [])
        if w is not None:
            ws.append(float(w.value))
    got = {}
    undropped_wells = {rel: set() for rel in RECHARGE_RELS}
    kept_wells = {rel: set() for rel in RECHARGE_RELS}
    dropped = {rel: {"edges": 0, "wells": set()} for rel in RECHARGE_RELS}
    for (b, rel, _), ws in by.items():
        if rel in RECHARGE_RELS:
            undropped_wells[rel].add(b)
            if math.fsum(ws) / len(ws) < MIN_CELL_SHARE:
                dropped[rel]["edges"] += 1
                dropped[rel]["wells"].add(b)
                continue
            kept_wells[rel].add(b)
        got[(b, rel)] = got.get((b, rel), 0) + 1
    e = ed[ed["relation"].isin(set(MECH.values()) | {"recharge_unitwide"})]
    want = e.groupby(["dst", "relation"]).size().to_dict()
    assert got == want, sorted(set(got.items()) ^ set(want.items()))[:6]
    for rel in RECHARGE_RELS:
        assert kept_wells[rel] == undropped_wells[rel], (rel, sorted(undropped_wells[rel] - kept_wells[rel]))
        assert _dropped(meta, rel) == {
            "edges": dropped[rel]["edges"], "wells": sorted(dropped[rel]["wells"])}, (rel, "graph")
    print(f"  3. arm D = whole-graph queries (with cell share >= {MIN_CELL_SHARE:g}): {len(want)} (well, relation) "
          f"pairs, the same number of distinct drivers among the influences the policy selects "
          f"({sum(want.values())} edges)")


def test_pandas(store, ed, meta):
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
    # recharge: cells and weights, applying the < 0.001 cutoff independently on the GeoPandas oracle
    described = {r[0].value for r in store.query(
        PRE + "SELECT ?c WHERE { ?u lulcw:bdlisaCode ?c ; prov:wasDerivedFrom ?r }")}
    oracle = oracle_coverage(described, wells)
    n_rch = 0
    dropped_counts = {}
    for kind, rel in (("local", "recharge"), ("unit-wide", "recharge_unitwide")):
        e = ed[ed["relation"] == rel]
        assert (e["weight"] >= MIN_CELL_SHARE).all(), (rel, float(e["weight"].min()))
        got = {b: dict(zip(g["src"], g["weight"])) for b, g in e.groupby("dst")}
        want_full, want_kept, sliver = {}, {}, set()
        dropped_edges, dropped_wells = 0, set()
        for b, u in zip(wells["code_bss"], wells["code_bdlisa"]):
            if not isinstance(u, str) or u not in described:
                continue
            o, c, by_cell = oracle.get((b if kind == "local" else "forcing-cells", u), (0.0, 0.0, {}))
            if o >= 50.0 and c > 0:
                full = {cell: v / c for cell, v in by_cell.items() if v >= 1.0}
                kept = {cell: w for cell, w in full.items() if w >= MIN_CELL_SHARE}
                tiny = {cell: w for cell, w in full.items() if w < MIN_CELL_SHARE}
                want_full[b] = full
                want_kept[b] = kept
                if full:
                    assert kept, f"{rel}: {b} lost every recharge edge after dropping < {MIN_CELL_SHARE}"
                if tiny:
                    dropped_edges += len(tiny)
                    dropped_wells.add(b)
            elif o > 0:
                sliver.add(b)
        assert set(got) - sliver == set(want_full), (rel, sorted((set(got) - sliver) ^ set(want_full))[:6])
        assert set(got) - sliver == set(want_kept), (rel, sorted((set(got) - sliver) ^ set(want_kept))[:6])
        for b, cells in want_kept.items():
            assert set(got[b]) == set(cells), (rel, b, sorted(set(got[b]) ^ set(cells))[:6])
            assert all(abs(got[b][c] - w) <= 1e-5 for c, w in cells.items()), (rel, b)
            assert abs(sum(got[b].values()) - sum(cells.values())) <= 1e-5 * len(cells) + 1e-9, (rel, b)
        assert (e["sign"] == "PositiveResponse").all() and e["eligible"].all() and e["constrained"].all()
        assert _dropped(meta, rel) == {
            "edges": dropped_edges, "wells": sorted(dropped_wells)}, (rel, "pandas oracle")
        dropped_counts[rel] = (dropped_edges, len(dropped_wells))
        n_rch += len(e)
    # overlying-leakage recharge: stack directly above each well's attributed unit (cross-checking
    # data/interim/bdlisa_station_stacks.csv for the 33 core wells, and reading BD LISA for all 65)
    import geopandas as gpd
    import pyogrio
    from src.analysis.bdlisa_profile import GPKG
    from src.config import CRS_L93, CRS_WGS84, INTERIM
    pts = gpd.GeoSeries(gpd.points_from_xy(wells["x"], wells["y"]), crs=CRS_WGS84).to_crs(CRS_L93)
    poly = pyogrio.read_dataframe(GPKG, layer="POLYG_ELEMENTAIRES", columns=["codepoly"]).to_crs(CRS_L93)
    j = gpd.sjoin(gpd.GeoDataFrame(geometry=pts), poly, how="left", predicate="within")
    w_cp = j[~j.index.duplicated()]["codepoly"].reindex(wells.index)
    pile = pyogrio.read_dataframe(GPKG, layer="TABLE_PILE_ENTITES_NIV3", read_geometry=False)
    pile = pile.assign(cp=pile["CodePoly"].astype(int)).sort_values(["cp", "OrdRelatif"])
    stack_of = pile.groupby("cp")["CodeEH"].agg(list).to_dict()
    stacks_csv = pd.read_csv(INTERIM / "bdlisa_station_stacks.csv").set_index("code_bss")
    upper_of = {}
    for idx_row, wrow in wells.iterrows():
        b, u = wrow["code_bss"], wrow["code_bdlisa"]
        cp = w_cp.loc[idx_row]
        st = stack_of.get(int(cp), []) if pd.notna(cp) else []
        if b in stacks_csv.index:
            csv_st = stacks_csv.loc[b, "stack_str"].split(" > ")
            assert st == csv_st, (b, st, csv_st)
        if isinstance(u, str) and u in st:
            pos = st.index(u)
            if pos > 0:
                upper_of[b] = st[pos - 1]
    rel = "recharge_leakage"
    e = ed[ed["relation"] == rel]
    assert (e["weight"] >= MIN_CELL_SHARE).all(), (rel, float(e["weight"].min()))
    got = {b: dict(zip(g["src"], g["weight"])) for b, g in e.groupby("dst")}
    want_full, want_kept, sliver = {}, {}, set()
    dropped_edges, dropped_wells = 0, set()
    for b, v in upper_of.items():
        if v not in described:
            continue
        o, c, by_cell = oracle.get((b, v), (0.0, 0.0, {}))
        if o >= 50.0 and c > 0:
            full = {cell: a_ / c for cell, a_ in by_cell.items() if a_ >= 1.0}
            kept = {cell: w for cell, w in full.items() if w >= MIN_CELL_SHARE}
            tiny = {cell: w for cell, w in full.items() if w < MIN_CELL_SHARE}
            want_full[b] = full
            want_kept[b] = kept
            if full:
                assert kept, f"{rel}: {b} lost every leakage edge after dropping < {MIN_CELL_SHARE}"
            if tiny:
                dropped_edges += len(tiny)
                dropped_wells.add(b)
        elif o > 0:
            sliver.add(b)
    assert set(got) - sliver == set(want_full), (rel, sorted((set(got) - sliver) ^ set(want_full))[:6])
    assert set(got) - sliver == set(want_kept), (rel, sorted((set(got) - sliver) ^ set(want_kept))[:6])
    for b, cells in want_kept.items():
        assert set(got[b]) == set(cells), (rel, b, sorted(set(got[b]) ^ set(cells))[:6])
        assert all(abs(got[b][c] - w) <= 1e-5 for c, w in cells.items()), (rel, b)
        assert abs(sum(got[b].values()) - sum(cells.values())) <= 1e-5 * len(cells) + 1e-9, (rel, b)
    assert (e["sign"] == "PositiveResponse").all() and e["eligible"].all() and e["constrained"].all()
    assert _dropped(meta, rel) == {
        "edges": dropped_edges, "wells": sorted(dropped_wells)}, (rel, "pandas oracle")
    dropped_counts[rel] = (dropped_edges, len(dropped_wells))
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
          f"BNPE points, distances within 0.5 m), {n_rch} recharge edges across 3 channels with their weights >= {MIN_CELL_SHARE:g} "
          f"(dropped: {dropped_counts['recharge'][0]} local across {dropped_counts['recharge'][1]} wells, "
          f"{dropped_counts['recharge_unitwide'][0]} unit-wide across {dropped_counts['recharge_unitwide'][1]} wells, "
          f"{dropped_counts['recharge_leakage'][0]} leakage across {dropped_counts['recharge_leakage'][1]} wells; "
          f"every well keeps >= 1 edge), {n_un} unattributed facility-well pairs = the other groundwater "
          f"facilities within 5 km")


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
    unchanged = ""
    print(f"  5. arm C by brute force: {len(w)} weather edges (each well's own cell), {len(r)} river edges (2 nearest "
          f"pool gauges), {len(p)} pumping edges (every groundwater facility within {E.C_PUMP_KM:g} km), {len(k)} "
          f"symmetric well links, the canal for the {wells['in_plain'].sum()} wells of the plain; no sign in C; "
          f"the same distance weights in both arms{unchanged}")


def main():
    nodes, ec, ed, meta = load()
    store = kg_store()
    test_identity(nodes, ec, ed, meta)
    test_inventory(store, ed, meta)
    test_graph(store, ed, meta)
    test_pandas(store, ed, meta)
    test_arm_c(ec, ed)
    print("test_export: all checks passed")


if __name__ == "__main__":
    main()
