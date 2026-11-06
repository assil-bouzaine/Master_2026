"""The per-well, per-relation inventory of arm D (src.kg.inventory; task 12.8, step 1).

    PFE_DATASET=v4 python -m tests.test_inventory

1. Path aggregation: two evidence paths of one source make one edge, eligible (or constrained)
   only if both are and their signs agree (analysis plan §14 item 17, proposed).
2. The CQ fixture of tests/test_cq.py: W1's pumping edges (F1 and F6 eligible and constrained,
   F2 group-level, F4 not selected), W7's recharge cells (weights summing to 1, not constrained:
   pending decision), R1's river and canal edges (eligible, not constrained), R8's river answer
   (unknown: only off-map reaches), and the depth-2 reach through well links.
3. Data (the validated release): the inventory's totals equal independent counts of the selected
   influences and well links in the graph; no recharge, river or canal sign is constrained before
   Gate 3; every well has one row per relation.
"""
import pandas as pd
import pyoxigraph as ox
import rdflib

from src.config import DATASET, DATASET_DIR
from src.kg import inventory as inv
from src.kg import release
from src.kg.cq import KG

L = "https://w3id.org/lulcw#"
D = "https://w3id.org/lulcw/data/"


def path(sign="NegativeResponse", elig="EligibleConstraint", constrained=True):
    return {"responseSign": L + sign, "eligibility": L + elig, "constrained": constrained,
            "distanceM": 100.0, "cellWeight": None, "associationType": None}


def test_aggregation():
    s = inv.summarise({"F": [path(), path()]})
    assert (s["n_sources"], s["n_paths"], s["eligible"], s["constrained"]) == (1, 2, 1, 1), s
    s = inv.summarise({"F": [path(), path(elig="IneligibleConstraint", constrained=False)]})
    assert (s["eligible"], s["constrained"]) == (0, 0), s
    s = inv.summarise({"F": [path(), path(sign="PositiveResponse")]})
    assert (s["eligible"], s["constrained"]) == (0, 0), s
    print("  1. path aggregation: one edge per source, eligible or constrained only if every path is, with one sign")


def test_fixture():
    from tests.test_cq import fixture_store
    s, u, g = fixture_store()
    keys = [w for w in ("W1", "W2", "W5", "W7", "W8", "R1", "R2", "R6", "R7", "R8")]
    wells = pd.DataFrame({"code_bss": keys, "iri": [D + f"piezometer/{k}" for k in keys], "core": True, "unit": None})
    df = inv.inventory(s, wells, rdflib.URIRef(D + "policy/main")).set_index(["code_bss", "relation"])
    p = df.loc[("W1", "pumping")]
    assert (p["n_sources"], p["eligible"], p["constrained"]) == (3, 2, 2) and p["sources"] == "F1 F2 F6", p
    r = df.loc[("W7", "recharge")]
    assert (r["n_sources"], r["weight_sum"], r["eligible"], r["constrained"]) == (2, 1.0, 2, 0), r
    assert df.loc[("W8", "recharge"), "status"] == "none_found" and df.loc[("W8", "recharge_unitwide"), "n_sources"] == 1
    assert tuple(df.loc[("R1", "river"), ["n_sources", "eligible", "constrained", "status"]]) == (1, 1, 0, "derived")
    assert tuple(df.loc[("R1", "canal"), ["n_sources", "eligible", "constrained"]]) == (1, 1, 0)
    assert tuple(df.loc[("R6", "canal"), ["n_sources", "eligible"]]) == (1, 0)        # hedged, and C3 an aggregate
    assert df.loc[("R8", "river"), "status"] == "unknown" and df.loc[("R8", "river"), "n_sources"] == 0
    assert df.loc[("R2", "river"), "association_types"] == "OverCover"
    # well links: each linked pair is listed from both ends, and a depth-2 network reaches the
    # neighbours' sources only through links that pass the threshold
    links = df.xs("well_link", level="relation")
    for k, row in links.iterrows():
        for nb in (row["sources"] or "").split():
            if nb in links.index:
                assert k in links.loc[nb, "sources"].split(), (k, nb)
    for k in keys:
        for rel in ("pumping", "recharge", "river", "canal"):
            row = df.loc[(k, rel)]
            assert row["reach_k2_none"] >= row["n_sources"] and row["reach_k2_t10"] <= row["reach_k2_none"], (k, rel)
    print("  2. fixture: pumping edges per facility under the policy (F4 not selected), recharge weights, river and "
          "canal edges eligible but not constrained (pending), an off-map search unknown; links symmetric, reach monotone")


def test_data():
    m = release.check()
    df = pd.read_parquet(KG / f"inventory_{DATASET}_main.parquet")
    wells = pd.read_parquet(DATASET_DIR / "wells.parquet")
    assert len(df) == len(wells) * len(inv.RELATIONS) and set(df["code_bss"]) == set(wells["code_bss"])
    s = ox.Store()
    for f in (KG / f"lulcw_kg_{DATASET}.ttl", KG / f"lulcw_kg_{DATASET}_rules.ttl"):
        s.bulk_load(path=str(f), format=ox.RdfFormat.TURTLE)
    q = lambda t: [[x.value for x in r] for r in s.query("PREFIX lulcw: <https://w3id.org/lulcw#> " + t)]  # noqa: E731
    main = f"<{D}policy/main>"
    for mech, rel in (("RiverExchange", "river"), ("CanalReturnFlow", "canal")):
        got = df[df["relation"] == rel]
        wells_kg = q(f"""SELECT (COUNT(DISTINCT ?w) AS ?n) WHERE {{ ?i lulcw:mechanism lulcw:{mech} ;
            lulcw:targetEntity ?w ; lulcw:selectedUnder {main} }}""")[0][0]
        elig_kg = q(f"""SELECT (COUNT(DISTINCT ?i) AS ?n) WHERE {{ ?i lulcw:mechanism lulcw:{mech} ;
            lulcw:selectedUnder {main} ; lulcw:constraintEligibility lulcw:EligibleConstraint }}""")[0][0]
        assert int((got["n_sources"] > 0).sum()) == int(wells_kg) and int(got["eligible"].sum()) == int(elig_kg), (rel, wells_kg, elig_kg)
        assert int(got["constrained"].sum()) == 0, rel                    # pending until Gate 3
    rech = df[df["relation"] == "recharge"]
    assert int(rech["constrained"].sum()) == 0 and (rech.loc[rech["n_sources"] > 0, "weight_sum"] > 0.999).all()
    n_links = int(q(f"SELECT (COUNT(DISTINCT ?l) AS ?n) WHERE {{ ?l a lulcw:WellLink ; lulcw:selectedUnder {main} }}")[0][0])
    assert int(df.loc[df["relation"] == "well_link", "n_sources"].sum()) == 2 * n_links, n_links
    pairs = q(f"""SELECT (COUNT(*) AS ?n) WHERE {{ SELECT DISTINCT ?f ?w WHERE {{ ?i lulcw:mechanism lulcw:PumpingDrawdown ;
        lulcw:driverEntity ?f ; lulcw:targetEntity ?w ; lulcw:selectedUnder {main} }} }}""")[0][0]
    assert int(df.loc[df["relation"] == "pumping", "n_sources"].sum()) == int(pairs), pairs
    print(f"  3. data (release of {m['released']}): {len(df)} rows; river, canal, recharge, well-link and "
          f"pumping totals = independent counts of the graph; no recharge, river or canal sign constrained")


def main():
    test_aggregation()
    test_fixture()
    if (KG / f"inventory_{DATASET}_main.parquet").exists():
        test_data()
    else:
        print("  3. skipped: run src.kg.inventory first")
    print("test_inventory: all checks passed")


if __name__ == "__main__":
    main()
