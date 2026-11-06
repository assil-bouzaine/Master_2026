"""Per-well, per-relation inventory of arm D's connections (task 12.8, step 1).

    PFE_DATASET=v4 python -m src.kg.inventory                      # main policy
    PFE_DATASET=v4 python -m src.kg.inventory --policy confident-only

Before any arm is scored (analysis plan §14 items 15 and 17; Codex reviews of 2026-10-26, §2, and
2026-11-06, §2), what D's graph gives each well, read from the validated graph release through the
competency-question queries (src.kg.cq), so that the inventory and the CQ answers cannot drift apart:

  pumping   the facilities whose pumping influence on the well the policy selects. Several evidence
            paths of one facility (e.g. two candidate units) make one edge: its sign is eligible,
            or constrained, only if every selected path is (the path-aggregation rule proposed in
            analysis plan §14 item 17); the nearest distance
  recharge  the weather cells over the outcrop of the well's unit in its 5 km zone (main), and in the
            unit-wide extent (sensitivity, relation "recharge_unitwide"); the sum of the cell
            weights per path (1 where the zone's outcrop lies inside the cells)
  river     the pool gauges with a river influence, their association types, the eligible and the
            constrained edges; without one, CQ8's answer and reason (no_pool_gauge, none_found,
            unknown)
  canal     the canal intake group's influence, eligible and constrained; else CQ8's answer
  well_link the same-unit wells within 5 km whose link the policy selects, and how many remain under
            each candidate depth threshold (10, 20 and 50 m, or none; the threshold is chosen per
            regime from that regime's training heads, analysis plan §14 item 15, not here)

and, per well, relation and threshold, the distinct exogenous sources a message-passing network of
depth 2 reaches through the selected well links (its own and those of its linked wells): what D lets
a well see, not what a model uses. "constrained" follows the policy's constraint decisions
(lulcw:ConstraintDecision): until Gate 3 only pumping signs can be constrained.

Output: data/processed/kg/inventory_<dataset>_<policy>.parquet (one row per well and relation) and
.json (the release, the policy, the code version, totals per relation).
"""
import argparse
import json
from collections import defaultdict

import pandas as pd
import rdflib

from src.config import DATASET, DATASET_DIR, ROOT
from src.kg import release
from src.kg.build_kg import git_version
from src.kg.cq import KG, ask, iris, kg_store, local, one

D = "https://w3id.org/lulcw/data/"
THRESHOLDS = (10.0, 20.0, 50.0, None)          # candidate |Δ depth| thresholds of the well links (m)
RELATIONS = ("pumping", "recharge", "recharge_unitwide", "river", "canal", "well_link")
MECHANISM = {"PumpingDrawdown": "pumping", "DiffuseRecharge": "recharge", "RiverExchange": "river",
             "CanalReturnFlow": "canal"}


def tag(t):
    return f"t{int(t)}" if t is not None else "none"


def edges_of(rows):
    """Selected influence rows of one well -> {relation: {source: [paths]}}."""
    out = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if not r["selected"]:
            continue
        rel = MECHANISM[local(r["mechanism"])]
        if rel == "recharge" and r["extent"] and r["extent"].endswith("/forcing-cells"):
            rel = "recharge_unitwide"
        out[rel][r["driverCode"]].append(r)
    return out


def summarise(sources):
    """One inventory row's numbers from {source: [paths]}."""
    paths = [p for ps in sources.values() for p in ps]
    one_sign = {s: len({local(p["responseSign"]) for p in ps}) == 1 for s, ps in sources.items()}
    eligible = sum(one_sign[s] and all(local(p["eligibility"]) == "EligibleConstraint" for p in ps)
                   for s, ps in sources.items())
    constrained = sum(one_sign[s] and all(p["constrained"] for p in ps) for s, ps in sources.items())
    dist = [p["distanceM"] for p in paths if p["distanceM"] is not None]
    weights = [p["cellWeight"] for p in paths if p["cellWeight"] is not None]
    types = sorted({p["associationType"] for p in paths if p["associationType"]})
    return {"n_sources": len(sources), "n_paths": len(paths), "eligible": eligible,
            "constrained": constrained, "nearest_m": min(dist) if dist else None,
            "weight_sum": round(sum(weights), 6) if weights else None,
            "association_types": " ".join(types) or None,
            "sources": " ".join(sorted(map(str, sources)))}


def inventory(store, wells, policy):
    """The inventory of `wells` (DataFrame: code_bss, iri, core, unit) under `policy` (an IRI)."""
    rows, srcs, links, status = [], {}, {}, {}
    for w in wells.itertuples():
        W = rdflib.URIRef(w.iri)
        inf = edges_of(ask(store, "cq08_influences", W=W, policy=policy))
        st = one(store, "cq08_status", W=W)
        nb = ask(store, "cq11_neighbours", W=W, r=5000.0, policy=policy)
        links[w.code_bss] = [(r["neighbourCode"], r["depthDifferenceM"]) for r in nb if r["selected"]]
        srcs[w.code_bss] = {rel: set(inf[rel]) for rel in RELATIONS if rel != "well_link"}
        status[w.code_bss] = st
        for rel in RELATIONS:
            base = {"code_bss": w.code_bss, "core": bool(w.core), "unit": w.unit, "relation": rel}
            if rel == "well_link":
                nl = links[w.code_bss]
                rec = {"n_sources": len(nl), "n_paths": len(nl), "sources": " ".join(sorted(c for c, _ in nl))}
                for t in THRESHOLDS[:-1]:
                    rec[f"links_{tag(t)}"] = sum(d is not None and abs(d) <= t for _, d in nl)
                rec["links_none"] = len(nl)
                rec["missing_depth"] = sum(d is None for _, d in nl)
                rows.append(base | rec)
                continue
            rec = summarise(inf[rel]) if inf[rel] else {"n_sources": 0, "n_paths": 0, "eligible": 0,
                                                             "constrained": 0}
            if rel in ("river", "canal"):
                rec["status"], rec["reason"] = st[rel], st[f"{rel}Reason"]
            elif rel == "recharge":
                rec["status"], rec["reason"] = st["recharge"], st["reason"]
            rows.append(base | rec)
    df = pd.DataFrame(rows)
    # what a depth-2 network sees through the selected well links, per candidate threshold
    for t in THRESHOLDS:
        reach = []
        for r in df.itertuples():
            if r.relation == "well_link":
                reach.append(None)
                continue
            seen = set(srcs[r.code_bss][r.relation])
            for c, d in links[r.code_bss]:
                if c in srcs and (t is None or (d is not None and abs(d) <= t)):
                    seen |= srcs[c][r.relation]
            reach.append(len(seen))
        df[f"reach_k2_{tag(t)}"] = reach
    return df


def totals(df):
    """Per relation: wells with at least one source (all, core), eligible and constrained edges."""
    out = {}
    for rel, g in df.groupby("relation", sort=False):
        has = g[g["n_sources"] > 0]
        out[rel] = {"wells": int(len(has)), "core_wells": int(has["core"].sum()),
                    "sources": int(g["n_sources"].sum())}
        if rel != "well_link":
            out[rel] |= {"eligible_edges": int(g["eligible"].sum()), "constrained_edges": int(g["constrained"].sum()),
                         "wells_with_eligible": int((g["eligible"] > 0).sum())}
    return out


def dataset_wells(store):
    """The dataset's wells with their graph IRI and the unit the graph attributes to them."""
    wells = pd.read_parquet(DATASET_DIR / "wells.parquet")
    pz = iris(store, "SELECT ?c ?w WHERE { ?w a lulcw:Piezometer ; lulcw:bssCode ?c }")
    wells["iri"] = [pz[c].value for c in wells["code_bss"]]
    wells["unit"] = wells["code_bdlisa"].where(wells["code_bdlisa"].notna(), None)
    return wells[["code_bss", "iri", "core", "unit"]]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--policy", default="main", choices=("main", "confident-only", "all-links"))
    args = ap.parse_args()
    m = release.check()
    store = kg_store()
    df = inventory(store, dataset_wells(store), rdflib.URIRef(D + f"policy/{args.policy}"))
    out = KG / f"inventory_{DATASET}_{args.policy}.parquet"
    df.to_parquet(out, index=False)
    meta = {"dataset": DATASET, "policy": args.policy, "release": m["released"],
            "release_files": {k: v["sha256"] for k, v in m["files"].items()},
            "code_version": git_version(("src/kg", "ontology", "configs", "tests/cq")),
            "thresholds_m": [t for t in THRESHOLDS], "totals": totals(df)}
    out.with_suffix(".json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta["totals"], indent=1))
    print(f"-> {out.relative_to(ROOT)} ({len(df)} rows)")


if __name__ == "__main__":
    main()
