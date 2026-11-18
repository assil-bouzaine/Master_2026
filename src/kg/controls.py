"""Control graphs for arms E and F (docs/analysis_plan.md §10 and §14 item 20).

    PFE_DATASET=v4 python -m src.kg.controls

The controls share D's node inventory and model. Each changes how edges are selected.

  E_degree    Swaps endpoints within each relation and preserves each node's degree.
              This tests whether D gains from which links it has given those degrees.
  E_distance  Draws from the five eligible sources closest to each original edge length.
              A gain for D on well-matched relations is evidence beyond locality.
  F_random    Draws the same number of edges as D per relation from all compatible pairs.
              This tests what the model can learn from a graph of the same size by chance.
  F_complete  Connects every compatible pair to test what the model can learn with all links.

Arm E keeps the evidence bundles with the target wells, including recharge weights. Each
well keeps its constraint setting. Shared bipartite pairs in both E controls keep their D bundles.
The canal has one source, so E keeps its original edges. Arm F carries no edge evidence.
Every control recalculates unattributed pumping within 5 km so each nearby facility's volume
is represented once. The D-only recharge_unitwide sensitivity relation is omitted.

Pumping and well links use the graph's Lambert-93 coordinates written to 0.1 m for matching
and weighting. Unattributed pumping, recharge and rivers use full-precision node coordinates.

The CLI writes edges_<kind>_<draw>.parquet for five draws per random kind by default, plus
edges_F_complete.parquet, summary.csv and manifest.json under the export's controls/ directory.
The manifest records the SHA-256 hashes of edges_D.parquet and nodes.parquet. load_control
refuses stale controls.

For v4 main, E_distance draw 0 changed lengths by a median of 44.65 m for pumping,
6,949.55 m for recharge, 13,221.12 m for rivers and 4,861.43 m for well links.
Rivers have only five gauges, and recharge uses 8 km cells whose nearest choices are
often already linked by D, so alternatives can be much farther away.
"""
import argparse
import json
from itertools import combinations, product
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from src.config import DATASET, PROCESSED, ROOT
from src.kg.export import CANAL, D_RADIUS_M, EDGE_COLS, PUMP_DECAY_M, SRC_TYPE, _dist, edge, out_dir
from src.kg.release import sha256

try:
    from src.models.manifest import code_version
except ImportError:
    from src.kg.build_kg import git_version as code_version

KIND_ID = {"E_degree": 0, "E_distance": 1, "F_random": 2, "F_complete": 3}
REL_ID = {"pumping": 0, "recharge": 1, "river": 2, "canal": 3, "well_link": 4}
SOURCE_TYPE = {**{rel: SRC_TYPE[rel] for rel in REL_ID if rel != "well_link"}, "well_link": "well"}
UNATTRIBUTED = "pumping_unattributed"
PAIR_COLS = ["src", "dst"]
SORT_COLS = ["relation", *PAIR_COLS]
MATCH_K = 5
SWAPS_PER_EDGE = 10
ATTEMPTS_PER_EDGE = 100
DEFAULT_DRAWS = 5
HASH_FILES = ("edges_D.parquet", "nodes.parquet")
STALE = "controls are stale, re-run python -m src.kg.controls"


def _read_export(directory, dataset):
    edges = pd.read_parquet(directory / "edges_D.parquet")
    nodes = pd.read_parquet(directory / "nodes.parquet")
    wells = pd.read_parquet(PROCESSED / f"dataset_{dataset}" / "wells.parquet",
                            columns=["code_bss", "profondeur_investigation"])
    meta = json.loads((directory / "manifest.json").read_text())
    return edges, nodes, wells.set_index("code_bss")["profondeur_investigation"], meta


def _nodes_by_type(nodes):
    return {kind: group.set_index("code").sort_index() for kind, group in nodes.groupby("type")}


def _distance_grid(relation, wells, sources):
    """One row per well and one column per source, both in code order."""
    # build_kg.py formats KG points to 0.1 m. export.py uses full precision for unattributed pumping.
    if relation in ("pumping", "well_link"):
        wells, sources = (nodes[["x93", "y93"]].map(lambda value: float(f"{value:.1f}"))
                          for nodes in (wells, sources))
    return pd.DataFrame(_dist(wells, sources), index=wells.index, columns=sources.index)


def _pairs(edges):
    return list(edges[PAIR_COLS].itertuples(index=False, name=None))


def _lengths(pairs, distances):
    src, dst = zip(*pairs) if pairs else ([], [])
    rows = distances.index.get_indexer(dst)
    cols = distances.columns.get_indexer(src)
    if (rows < 0).any() or (cols < 0).any():
        raise ValueError("edge endpoints are missing from the export's node inventory")
    return distances.to_numpy()[rows, cols]


def _edge_table(relation, pairs, distances=None, depths=None, sigma=None, original=None):
    """Fill the export's columns and recalculate geometry for the selected endpoints."""
    src_type = "facility" if relation == UNATTRIBUTED else SOURCE_TYPE[relation]
    if original is None:
        defaults = edge(relation, src_type, None, None, 1.0)
        defaults.update(distance_m=np.nan, depth_diff_m=np.nan)
        table = pd.DataFrame(pairs, columns=PAIR_COLS)
        table = table.assign(**{key: value for key, value in defaults.items() if key not in PAIR_COLS})
    else:
        # The pair list keeps the same row order, so each attribute bundle stays with its well.
        table = original.copy()
        table[PAIR_COLS] = np.asarray(pairs, dtype=object).reshape(-1, 2)

    if relation in ("pumping", UNATTRIBUTED, "well_link"):
        table["distance_m"] = _lengths(pairs, distances)
        decay = sigma if relation == "well_link" else PUMP_DECAY_M
        table["weight"] = np.exp(-table["distance_m"] / decay)
    if relation == "well_link":
        table["depth_diff_m"] = (table["src"].map(depths) - table["dst"].map(depths)).abs()
    return table[EDGE_COLS]


def _near_unattributed(pumping_edges, distances):
    linked = set(_pairs(pumping_edges))
    rows, cols = np.where(distances.to_numpy() <= D_RADIUS_M)
    return [(src, dst) for src, dst in zip(distances.columns[cols], distances.index[rows])
            if (src, dst) not in linked]


def unattributed(pumping_edges, nodes, wells):
    """Give the wells their nearby facilities that lack an explicit pumping edge."""
    by_type = _nodes_by_type(nodes)
    distances = _distance_grid(UNATTRIBUTED, by_type["well"].loc[sorted(wells)], by_type["facility"])
    pairs = _near_unattributed(pumping_edges, distances)
    table = _edge_table(UNATTRIBUTED, pairs, distances=distances)
    return table.sort_values(PAIR_COLS, ignore_index=True)


def _degree_swaps(pairs, rng, undirected):
    """Swap two links while keeping degrees and, for directed links, the target of each row."""
    pairs = pairs.copy()
    present = set(pairs)
    size = len(pairs)
    swapped = 0
    if size < 2:
        return pairs, swapped
    for _ in range(ATTEMPTS_PER_EDGE * size):
        first, second = rng.integers([size, size - 1])
        if second >= first:
            second += 1
        a, i = pairs[first]
        b, j = pairs[second]
        if undirected:
            if len({a, i, b, j}) < 4:
                continue
            proposed = ((a, j), (b, i)) if rng.integers(2) else ((a, b), (i, j))
            one, two = (tuple(sorted(pair)) for pair in proposed)
        else:
            if a == b or i == j:
                continue
            one, two = (b, i), (a, j)
        if one in present or two in present:
            continue
        present.remove(pairs[first])
        present.remove(pairs[second])
        pairs[first], pairs[second] = one, two
        present.update((one, two))
        swapped += 1
        if swapped == SWAPS_PER_EDGE * size:
            break
    return pairs, swapped


def _keep_shared_bundles(original, rewired):
    """Put shared pairs back in their original bundle slots within the same well."""
    position = {pair: i for i, pair in enumerate(rewired)}
    for i, pair in enumerate(original):
        j = position.get(pair)
        if j is not None and j != i:
            displaced = rewired[i]
            rewired[i], rewired[j] = pair, displaced
            position[pair], position[displaced] = i, j


def _match_distances(pairs, distances, rng, undirected):
    """Draw from the five closest lengths in code order for each original edge."""
    excluded = set(pairs)
    if undirected:
        excluded.update((dst, src) for src, dst in pairs)
    used, rewired, errors = set(), [], []
    kept = 0
    for src, dst in pairs:
        length = distances.at[dst, src]
        row = distances.loc[dst]
        # The columns are sorted by source code, so a stable sort resolves ties by code.
        ranked = (row - length).abs().sort_values(kind="stable")
        best = []
        for candidate, error in ranked.items():
            if candidate != dst and (candidate, dst) not in excluded and (candidate, dst) not in used:
                best.append((candidate, error))
                if len(best) == MATCH_K:
                    break
        if best:
            chosen, error = best[rng.integers(len(best))]
        else:
            chosen, error = src, 0.0
            kept += 1
        rewired.append((chosen, dst))
        errors.append(error)
        used.add((chosen, dst))
        if undirected:
            # A later anchor can also be this source. Both directions occupy the same link.
            used.add((dst, chosen))
    return rewired, {"kept": kept,
                     "median_abs_delta_m": float(np.median(errors)) if errors else np.nan,
                     "max_abs_delta_m": max(errors, default=np.nan)}


def _summary(relation, control, original, distances, details):
    pairs, before = _pairs(control), _pairs(original)
    shared = len(set(pairs).intersection(before))
    return {"relation": relation, "edges": len(control), "wells": control["dst"].nunique(),
            "sources": control["src"].nunique(), "overlap": shared / len(before) if before else np.nan,
            "out_degree_preserved": control["src"].value_counts().sort_index().equals(
                original["src"].value_counts().sort_index()),
            "in_degree_preserved": control["dst"].value_counts().sort_index().equals(
                original["dst"].value_counts().sort_index()),
            "successful_swaps": details.get("successful_swaps"),
            "kept": details.get("kept"),
            "median_abs_delta_m": details.get("median_abs_delta_m"),
            "max_abs_delta_m": details.get("max_abs_delta_m"),
            "median_distance_m": float(np.median(_lengths(pairs, distances)))
            if distances is not None and pairs else np.nan,
            "d_median_distance_m": float(np.median(_lengths(before, distances)))
            if distances is not None and before else np.nan}


def _control_relation(kind, draw, relation, original, by_type, distances, depths, sigma):
    rng = np.random.default_rng([KIND_ID[kind], draw, REL_ID[relation]])
    undirected = relation == "well_link"
    pairs = _pairs(original)
    if undirected:
        pairs = [(src, dst) for src, dst in pairs if src < dst]
    details = {}
    if kind.startswith("E_") and relation == "canal":
        details = {"successful_swaps": 0} if kind == "E_degree" else {"kept": len(pairs)}
        return original, details
    if kind == "E_degree":
        pairs, swapped = _degree_swaps(pairs, rng, undirected)
        details["successful_swaps"] = swapped
    elif kind == "E_distance":
        if undirected:
            # Each original pair starts with its lower-code well. Keep that end as the target.
            pairs = [(hi, lo) for lo, hi in pairs]
        pairs, details = _match_distances(pairs, distances, rng, undirected)
    else:
        wells = by_type["well"].index
        sources = [CANAL] if relation == "canal" else by_type[SOURCE_TYPE[relation]].index
        compatible = list(combinations(wells, 2) if undirected else product(sources, wells))
        if kind == "F_random":
            pairs = [compatible[i] for i in rng.choice(len(compatible), len(pairs), replace=False)]
        else:
            pairs = compatible
    if undirected:
        pairs += [(dst, src) for src, dst in pairs]
    template = original if kind.startswith("E_") and not undirected else None
    if template is not None:
        _keep_shared_bundles(_pairs(template), pairs)
    return _edge_table(relation, pairs, distances, depths, sigma, template), details


def _build_control(kind, draw, edges, nodes, depths, sigma, summarize=False):
    edges = edges.sort_values(SORT_COLS, ignore_index=True)
    by_type = _nodes_by_type(nodes)
    wells = by_type["well"]
    tables, summary = {}, []
    pumping_wells = set(edges.loc[edges["relation"].isin(("pumping", UNATTRIBUTED)), "dst"])
    originals = {rel: edges[edges["relation"] == rel] for rel in (*REL_ID, UNATTRIBUTED)}
    for relation in REL_ID:
        distances = None if relation == "canal" else _distance_grid(relation, wells, by_type[SOURCE_TYPE[relation]])
        original = originals[relation]
        control, details = _control_relation(kind, draw, relation, original, by_type, distances, depths, sigma)
        tables[relation] = control
        if summarize:
            summary.append(_summary(relation, control, original, distances, details))
    tables[UNATTRIBUTED] = unattributed(tables["pumping"], nodes, pumping_wells)
    if summarize:
        distances = _distance_grid(UNATTRIBUTED, wells, by_type["facility"])
        summary.append(_summary(UNATTRIBUTED, tables[UNATTRIBUTED], originals[UNATTRIBUTED], distances, {}))
    table = pd.concat([t.astype(edges.dtypes) for t in tables.values() if not t.empty], ignore_index=True
                      ) if any(not t.empty for t in tables.values()) else edges.iloc[:0].copy()
    return table.sort_values(SORT_COLS, ignore_index=True), summary


def control_well_links(kind, draw, d_links, policy="main", dataset=DATASET):
    """The `well_link` rows of a control drawn from a given set of D's well links (both directions),
    with the same seeds and rules as the saved controls. Rung 5 needs it: D's links are kept per
    regime by the depth threshold (src/models/depth_threshold.py), so a control of that regime must
    rewire the links D keeps there, not all of them (analysis plan §14 item 20). With every D link it
    returns exactly the saved control's well links."""
    _filename(kind, draw)
    _, nodes, depths, meta = _read_export(out_dir(policy, dataset), dataset)
    by_type = _nodes_by_type(nodes)
    d_links = d_links[d_links["relation"] == "well_link"].sort_values(SORT_COLS, ignore_index=True)
    distances = _distance_grid("well_link", by_type["well"], by_type["well"])
    table, _ = _control_relation(kind, draw, "well_link", d_links, by_type, distances, depths,
                                 meta["rules"]["well_link_sigma_m"])
    return table.sort_values(SORT_COLS, ignore_index=True)


def make_control(kind, draw=0, policy="main", dataset=DATASET):
    """Build one control from the given policy's export."""
    _filename(kind, draw)
    edges, nodes, depths, meta = _read_export(out_dir(policy, dataset), dataset)
    return _build_control(kind, draw, edges, nodes, depths, meta["rules"]["well_link_sigma_m"])[0]


def _filename(kind, draw):
    if kind not in KIND_ID:
        raise ValueError(f"unknown control kind: {kind}")
    return "edges_F_complete.parquet" if kind == "F_complete" else f"edges_{kind}_{draw}.parquet"


def _hashes(directory):
    return {name: sha256(directory / name) for name in HASH_FILES}


def load_control(kind, draw=0, policy="main", dataset=DATASET):
    """Load a saved control only if it was built from the current export."""
    filename = _filename(kind, draw)
    directory = out_dir(policy, dataset)
    controls = directory / "controls"
    manifest = json.loads((controls / "manifest.json").read_text())
    try:
        current = _hashes(directory)
    except FileNotFoundError as err:
        raise RuntimeError(STALE) from err
    if manifest["export_sha256"] != current:
        raise RuntimeError(STALE)
    if kind != "F_complete" and draw not in manifest["draws"]:
        raise FileNotFoundError(f"{filename} is not listed in the controls manifest")
    return pd.read_parquet(controls / filename)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--policy", default="main", choices=("main", "confident-only", "all-links"))
    parser.add_argument("--draws", type=int, default=DEFAULT_DRAWS)
    args = parser.parse_args()
    if args.draws < 0:
        parser.error("--draws must be nonnegative")

    directory = out_dir(args.policy)
    hashes = _hashes(directory)
    edges, nodes, depths, meta = _read_export(directory, DATASET)
    schema = pq.read_schema(directory / "edges_D.parquet").remove_metadata()
    sigma = meta["rules"]["well_link_sigma_m"]
    draws = list(range(args.draws))
    results = []
    controls = directory / "controls"
    controls.mkdir(exist_ok=True)
    # Build the whole batch before replacing files so a failed build leaves the previous batch usable.
    with TemporaryDirectory(dir=controls) as staging:
        staging = Path(staging)
        for kind in KIND_ID:
            for draw in ([0] if kind == "F_complete" else draws):
                table, summaries = _build_control(kind, draw, edges, nodes, depths, sigma, summarize=True)
                table.to_parquet(staging / _filename(kind, draw), index=False, schema=schema)
                results.extend({"kind": kind, "draw": draw, **row} for row in summaries)
        summary = pd.DataFrame(results).astype({"successful_swaps": "Int64", "kept": "Int64"})
        summary.to_csv(staging / "summary.csv", index=False)
        manifest = {"dataset": DATASET, "policy": args.policy, "release": meta["release"],
                    "export_sha256": hashes, "code_version": code_version(),
                    "constants": {"kind_id": KIND_ID, "relation_id": REL_ID, "match_k": MATCH_K,
                                  "swaps_per_edge": SWAPS_PER_EDGE, "attempts_per_edge": ATTEMPTS_PER_EDGE,
                                  "pump_decay_m": PUMP_DECAY_M, "radius_m": D_RADIUS_M,
                                  "well_link_sigma_m": sigma, "canal": CANAL},
                    "kinds": list(KIND_ID), "draws": draws}
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
        if _hashes(directory) != hashes:
            raise RuntimeError(STALE)
        for file in staging.iterdir():
            if file.name != "manifest.json":
                file.replace(controls / file.name)
        (staging / "manifest.json").replace(controls / "manifest.json")
    print(summary.to_string(index=False))
    print(f"-> {controls.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
