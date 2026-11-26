"""Check the control graphs of analysis plan §10 and analysis plan v3 §2 on the v5 main export.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v5 .venv/bin/python -m tests.test_controls

Compare the controls with the exported D graph across every relation of arm D (pumping, three
recharge channels, river, basin canal, well links, monitors, overlies) and independently check
the geometry and nearby pumping coverage. Route each control through both v4 routing
(src.models.routing.routed_inputs) and v5 routing (src.models.hybrid_gnn.routed_v5_inputs).
Use a temporary copy to check that stale controls cannot be loaded.
"""
import json
from collections import Counter
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
import pandas as pd

from src.config import DATASET_DIR
from src.kg import controls as C
from src.kg.export import D_RADIUS_M, EDGE_COLS, PUMP_DECAY_M, out_dir
from src.models.hybrid_gnn import RECHARGE_RELATIONS, routed_v5_inputs
from src.models.routing import routed_inputs

SOURCE_TYPES = {
    "pumping": "facility",
    "recharge": "weather_cell",
    "recharge_unitwide": "weather_cell",
    "recharge_leakage": "weather_cell",
    "river": "gauge",
    "canal": "canal",
    "well_link": "well",
    "monitors": "aquifer_unit",
    "overlies": "aquifer_unit",
}
TARGET_TYPES = {rel: "aquifer_unit" if rel == "overlies" else "well" for rel in SOURCE_TYPES}
RECHARGE_RELS = frozenset({"recharge", "recharge_unitwide", "recharge_leakage"})
SWAP_ONLY_DISTANCE_RELS = frozenset({"monitors", "overlies"})
KEY = ["src", "dst"]
BUNDLE = ["sign", "eligible", "constrained", "n_paths", "association_types"]
UNATTRIBUTED = "pumping_unattributed"


def relation(edges, name):
    return edges.loc[edges["relation"] == name]


def pairs(edges):
    return set(edges[KEY].itertuples(index=False, name=None))


def lengths(edges, xy):
    src = xy.loc[edges["src"]].to_numpy()
    dst = xy.loc[edges["dst"]].to_numpy()
    return np.hypot(*(src - dst).T)


def test_unattributed(edges, nodes, wells):
    expected = relation(edges, UNATTRIBUTED).sort_values(KEY, ignore_index=True)
    actual = C.unattributed(relation(edges, "pumping"), nodes, wells)
    assert pairs(actual) == pairs(expected)
    np.testing.assert_allclose(actual["weight"], expected["weight"], rtol=0, atol=1e-12)
    np.testing.assert_allclose(actual["distance_m"], expected["distance_m"], rtol=0, atol=1e-6)
    pd.testing.assert_frame_equal(actual.drop(columns=["weight", "distance_m"]),
                                  expected.drop(columns=["weight", "distance_m"]))
    print(f"  1. D's pumping rebuilds {len(actual)} unattributed rows across {len(wells)} wells")


def check_well_links(edges, depths, sigma):
    assert pairs(edges) == {(dst, src) for src, dst in pairs(edges)}
    diff = np.abs(depths.loc[edges["src"]].to_numpy() - depths.loc[edges["dst"]].to_numpy())
    np.testing.assert_array_equal(edges["depth_diff_m"].isna(), np.isnan(diff))
    np.testing.assert_allclose(edges["depth_diff_m"], diff, rtol=0, atol=1e-9)
    np.testing.assert_allclose(edges["weight"], np.exp(-edges["distance_m"] / sigma), rtol=0, atol=1e-12)


def test_geometry(edges, nodes, depths, sigma):
    by_type = C._nodes_by_type(nodes)
    maximum = {}
    for name in ("pumping", "well_link"):
        group = relation(edges, name)
        grid = C._distance_grid(name, by_type["well"], by_type[SOURCE_TYPES[name]])
        actual = C._lengths(list(group[KEY].itertuples(index=False, name=None)), grid)
        np.testing.assert_allclose(actual, group["distance_m"], rtol=0, atol=1e-6)
        maximum[name] = np.abs(actual - group["distance_m"]).max()
    check_well_links(relation(edges, "well_link"), depths, sigma)
    print(f"  2. Control geometry reproduces D's pumping and well-link distances "
          f"(maximum differences {maximum['pumping']:.2e} and {maximum['well_link']:.2e} m). "
          "Depths and well-link weights agree.")


def bundle_counts(edges, columns):
    return {well: Counter(group[columns].itertuples(index=False, name=None))
            for well, group in edges.groupby("dst")}


def check_shared_bundles(shared):
    for name, group in shared.groupby("relation"):
        columns = BUNDLE + ["weight"] if name in RECHARGE_RELS else BUNDLE
        original = group[[f"{col}_d" for col in columns]].set_axis(columns, axis=1)
        control = group[[f"{col}_e" for col in columns]].set_axis(columns, axis=1)
        pd.testing.assert_frame_equal(original, control, check_exact=True, obj=f"{name} shared bundles")


def test_degree(edges, tables, summaries):
    for draw, table in enumerate(tables):
        shared = edges.merge(table, on=["relation", *KEY], suffixes=("_d", "_e"), validate="one_to_one")
        check_shared_bundles(shared)
        for field in ("distance_m", "weight"):
            np.testing.assert_allclose(shared[f"{field}_d"], shared[f"{field}_e"], rtol=0, atol=1e-9,
                                       err_msg=f"E_degree draw {draw}, shared {field}")
        for name in SOURCE_TYPES:
            old, new = relation(edges, name), relation(table, name)
            assert len(new) == len(old), (draw, name)
            for col in KEY:
                assert Counter(old[col]) == Counter(new[col]), (draw, name, col)
            cols = BUNDLE + ["weight"] if name in RECHARGE_RELS else BUNDLE
            assert bundle_counts(old, cols) == bundle_counts(new, cols), (draw, name)
            swaps = summaries[draw][name]["successful_swaps"]
            if name == "canal":
                pd.testing.assert_frame_equal(old.reset_index(drop=True), new.reset_index(drop=True))
                assert swaps == 0
            else:
                assert pairs(old) != pairs(new), (draw, name)
                expected = len(old) // 2 if name == "well_link" else len(old)
                assert swaps == 10 * expected, (draw, name, swaps)
    print("  3. E_degree draws 0–2 preserve each degree (including monitors and overlies) and bundle "
          "multiset, with 10 swaps per edge or unordered well pair. Shared edges keep D's distance, "
          "weight and bundle.")


def distance_oracle(old, candidates, xy, rng, undirected):
    """Replay the choices with a direct code-and-distance sort of eligible sources."""
    original = pairs(old)
    rows = sorted(original)
    if undirected:
        rows = [(hi, lo) for lo, hi in rows if lo < hi]
    drawn, errors, kept = [], [], 0
    available = {well: set(candidates) - {well} for _, well in rows}
    for src, dst in original:
        if dst in available:
            available[dst].discard(src)

    def distance(a, b):
        return np.linalg.norm(xy.loc[a].to_numpy() - xy.loc[b].to_numpy())

    for src, dst in rows:
        target_xy = xy.loc[dst, ["x93", "y93"]].to_numpy()
        reference = distance(src, dst)
        options = sorted(available[dst])
        offsets = xy.loc[options].to_numpy() - target_xy
        ranking = sorted(zip(np.abs(np.linalg.norm(offsets, axis=1) - reference), options))[:5]
        if ranking:
            error, chosen = ranking[rng.integers(len(ranking))]
            available[dst].remove(chosen)
            if undirected and chosen in available:
                available[chosen].discard(dst)
        else:
            error, chosen = 0.0, src
            kept += 1
        drawn.append((src, dst, chosen))
        errors.append(error)
    return drawn, errors, kept


def test_distance(edges, nodes, coordinates, tables, degree_tables, summaries):
    for draw, table in enumerate(tables):
        shared = edges.merge(table, on=["relation", *KEY], suffixes=("_d", "_e"), validate="one_to_one")
        check_shared_bundles(shared)
        for name, source_type in SOURCE_TYPES.items():
            old, new = relation(edges, name), relation(table, name)
            assert len(new) == len(old), (draw, name)
            details = summaries[draw][name]
            if name == "canal":
                pd.testing.assert_frame_equal(old.reset_index(drop=True), new.reset_index(drop=True))
                assert details["kept"] == len(old)
                continue
            if name in SWAP_ONLY_DISTANCE_RELS:
                for col in KEY:
                    assert Counter(old[col]) == Counter(new[col]), (draw, name, col)
                assert bundle_counts(old, BUNDLE) == bundle_counts(new, BUNDLE), (draw, name)
                assert pairs(old) != pairs(new), (draw, name)
                assert pairs(new) != pairs(relation(degree_tables[draw], name)), (draw, name)
                assert details["successful_swaps"] == 10 * len(old), (draw, name, details)
                continue
            undirected = name == "well_link"
            if not undirected:
                assert Counter(old["dst"]) == Counter(new["dst"]), (draw, name)
            rng = np.random.default_rng([C.KIND_ID["E_distance"], draw, C.REL_ID[name]])
            codes = nodes.loc[nodes["type"] == source_type, "code"]
            drawn, errors, kept = distance_oracle(old, codes, coordinates[name], rng, undirected)
            expected = {(chosen, dst) for _, dst, chosen in drawn}
            if undirected:
                expected |= {(dst, src) for src, dst in expected}
            assert pairs(new) == expected, (draw, name)
            assert details["kept"] == kept, (draw, name)
            assert len(expected & pairs(old)) == (2 if undirected else 1) * kept, (draw, name)
            np.testing.assert_allclose([details["median_abs_delta_m"], details["max_abs_delta_m"]],
                                       [np.median(errors), max(errors)], rtol=0, atol=1e-9)
            if not undirected:
                cols = BUNDLE + ["weight"] if name in RECHARGE_RELS else BUNDLE
                prior = old.set_index(KEY)[cols]
                after = new.set_index(KEY)[cols]
                for src, dst, chosen in drawn:
                    assert tuple(prior.loc[(src, dst), :]) == tuple(after.loc[(chosen, dst), :]), (draw, name, src, dst)
    print("  4. E_distance draws 0–2 agree with independent top-five choices (including all 3 recharge "
          "channels), degree-preserving swaps with distinct seeds for monitors/overlies, kept counts, "
          "length errors and original target bundles")


def test_random(edges, nodes, tables):
    for draw, table in enumerate(tables):
        for name, source_type in SOURCE_TYPES.items():
            target_type = TARGET_TYPES[name]
            group = relation(table, name)
            assert len(group) == len(relation(edges, name)), (draw, name)
            assert group["src_type"].eq(source_type).all()
            assert set(group["src"]) <= set(nodes.loc[nodes["type"] == source_type, "code"])
            assert set(group["dst"]) <= set(nodes.loc[nodes["type"] == target_type, "code"])
            assert group[["sign", "association_types"]].isna().all().all()
            assert not group[["eligible", "constrained"]].any().any()
            assert group["n_paths"].eq(1).all()
        for rel in RECHARGE_RELS:
            assert relation(table, rel)["weight"].eq(1.0).all(), (draw, rel)
    print("  5. F_random draws 0–2 match D's relation counts across all 9 relations, with compatible "
          "endpoints and empty bundles")


def test_complete(nodes, table):
    sizes = nodes["type"].value_counts()
    for name, source_type in SOURCE_TYPES.items():
        target_type = TARGET_TYPES[name]
        n_src = sizes[source_type] - (source_type == target_type)
        assert len(relation(table, name)) == n_src * sizes[target_type], name
    assert relation(table, UNATTRIBUTED).empty
    print(f"  6. F_complete contains all {len(table)} compatible directed edges across all 9 relations "
          f"and no unattributed rows")


def test_all(tables, edges, nodes, coordinates, wells, depths, sigma):
    xy = coordinates[UNATTRIBUTED]
    facilities = nodes.loc[nodes["type"] == "facility", "code"]
    points = xy.loc[facilities].to_numpy()
    near = {well: set(facilities[np.linalg.norm(points - xy.loc[well].to_numpy(), axis=1) <= D_RADIUS_M])
            for well in wells}
    codes_by_type = nodes.groupby("type")["code"].agg(set)
    for kind, draws in tables.items():
        pd.testing.assert_frame_equal(draws[0], C.make_control(kind))
        shuffled = C._build_control(kind, 0, edges.sample(frac=1, random_state=1),
                                    nodes.sample(frac=1, random_state=2),
                                    depths, sigma)[0]
        pd.testing.assert_frame_equal(draws[0], shuffled)
        if kind == "F_complete":
            pd.testing.assert_frame_equal(draws[0], C.make_control(kind, draw=1))
        else:
            for name in (*SOURCE_TYPES, UNATTRIBUTED):
                if not (kind.startswith("E_") and name == "canal"):
                    assert pairs(relation(draws[0], name)) != pairs(relation(draws[1], name)), (kind, name)
        for table in draws:
            assert table.columns.tolist() == EDGE_COLS
            pd.testing.assert_series_equal(table.dtypes, edges.dtypes)
            assert not table.duplicated(["relation", *KEY]).any()
            assert not table["src"].eq(table["dst"]).any()
            assert set(table["relation"]) <= {*SOURCE_TYPES, UNATTRIBUTED}
            for name, group in table.groupby("relation"):
                src_type = "facility" if name == UNATTRIBUTED else SOURCE_TYPES[name]
                dst_type = "well" if name == UNATTRIBUTED else TARGET_TYPES[name]
                assert group["src_type"].eq(src_type).all() and set(group["src"]) <= codes_by_type[src_type]
                assert set(group["dst"]) <= codes_by_type[dst_type], (kind, name)
                if name in ("pumping", UNATTRIBUTED, "well_link"):
                    distance = lengths(group, coordinates[name])
                    np.testing.assert_allclose(group["distance_m"], distance, atol=1e-6, rtol=0)
                    decay = sigma if name == "well_link" else PUMP_DECAY_M
                    np.testing.assert_allclose(group["weight"], np.exp(-distance / decay), atol=1e-12, rtol=0)
                else:
                    assert group["distance_m"].isna().all()
                    if name in ("river", "canal", "monitors", "overlies"):
                        assert group["weight"].eq(1.0).all()
            check_well_links(relation(table, "well_link"), depths, sigma)
            pump = relation(table, "pumping").groupby("dst")["src"].agg(set).to_dict()
            un = relation(table, UNATTRIBUTED).groupby("dst")["src"].agg(set).to_dict()
            assert set(un) <= wells
            for b, nearby in near.items():
                assert un.get(b, set()) == nearby - pump.get(b, set()), (kind, b)
    print("  7. Every control covers each nearby facility once and preserves the export's schema. "
          "Fixed seeds and shuffled inputs reproduce each table.")


def test_routing(edges, tables):
    original = routed_inputs(edges=edges)
    orig_v5 = routed_v5_inputs(edges=edges)
    pumping_start = pd.read_parquet(DATASET_DIR / "pumping_weekly.parquet", columns=["week"])["week"].min()
    in_record = orig_v5["weeks"] >= pumping_start
    for kind, draws in tables.items():
        actual = routed_inputs(edges=draws[0])
        for key, value in original.items():
            if isinstance(value, np.ndarray):
                assert actual[key].shape == value.shape and np.isfinite(actual[key]).all(), (kind, key)
        act_v5 = routed_v5_inputs(edges=draws[0])
        for key, value in orig_v5.items():
            if not isinstance(value, np.ndarray):
                continue
            assert act_v5[key].shape == value.shape, (kind, key)
            if np.issubdtype(value.dtype, np.floating) and value.ndim == 2:
                assert not np.isinf(act_v5[key]).any(), (kind, key)
                if np.isfinite(value).all():
                    assert np.isfinite(act_v5[key]).all(), (kind, key)
                else:
                    # Pre-record weeks (before pumping_weekly's first week) are intentionally NaN.
                    assert np.isfinite(act_v5[key][:, in_record]).all(), (kind, key)
            else:
                assert np.isfinite(act_v5[key]).all(), (kind, key)
        for ch, rel in RECHARGE_RELATIONS.items():
            if (edges["relation"] == rel).any():
                assert act_v5[f"has_{ch}"].any(), (kind, ch, rel)
    print(f"  8. Every draw-0 control routes finite arrays on D's {original['rain'].shape} grid "
          f"(v4 routing and v5 routing from {pumping_start.date()}; all 3 recharge channels active)")


def test_stale(directory, table):
    with TemporaryDirectory() as tmp:
        export = Path(tmp)
        names = ("edges_D.parquet", "nodes.parquet")
        for name in names:
            copyfile(directory / name, export / name)
        controls = export / "controls"
        controls.mkdir()
        table.to_parquet(controls / "edges_E_degree_0.parquet", index=False)
        hashes = {name: C.sha256(export / name) for name in names}
        manifest = controls / "manifest.json"
        with patch.object(C, "out_dir", return_value=export):
            manifest.write_text(json.dumps({"export_sha256": hashes, "draws": [0]}))
            pd.testing.assert_frame_equal(C.load_control("E_degree"), table)
            for name in names:
                wrong = {**hashes, name: "0" * 64}
                manifest.write_text(json.dumps({"export_sha256": wrong, "draws": [0]}))
                try:
                    C.load_control("E_degree")
                except RuntimeError as err:
                    assert str(err) == "controls are stale, re-run python -m src.kg.controls"
                else:
                    raise AssertionError(f"accepted the wrong hash for {name}")
    print("  9. load_control accepts matching hashes and rejects a mismatch in either export table")


def main():
    directory = out_dir("main")
    edges = pd.read_parquet(directory / "edges_D.parquet").sort_values(["relation", *KEY], ignore_index=True)
    nodes = pd.read_parquet(directory / "nodes.parquet")
    depths = pd.read_parquet(DATASET_DIR / "wells.parquet").set_index("code_bss")["profondeur_investigation"]
    meta = json.loads((directory / "manifest.json").read_text())
    sigma = meta["rules"]["well_link_sigma_m"]
    wells = set(edges.loc[edges["relation"].isin(("pumping", UNATTRIBUTED)), "dst"])
    test_unattributed(edges, nodes, wells)
    test_geometry(edges, nodes, depths, sigma)

    # Use the KG's printed precision in the independent distance oracles.
    xy = nodes.set_index("code")[["x93", "y93"]]
    kg_xy = xy.map(lambda value: float("%.1f" % value))
    coordinates = {name: xy for name in (*SOURCE_TYPES, UNATTRIBUTED)}
    coordinates.update(pumping=kg_xy, well_link=kg_xy)

    tables, summaries = {}, {}
    for kind in C.KIND_ID:
        tables[kind], summaries[kind] = [], []
        for draw in range(1 if kind == "F_complete" else 3):
            table, summary = C._build_control(kind, draw, edges, nodes, depths, sigma, summarize=True)
            tables[kind].append(table)
            summaries[kind].append({row["relation"]: row for row in summary})
    test_degree(edges, tables["E_degree"], summaries["E_degree"])
    test_distance(edges, nodes, coordinates, tables["E_distance"], tables["E_degree"], summaries["E_distance"])
    test_random(edges, nodes, tables["F_random"])
    test_complete(nodes, tables["F_complete"][0])
    test_all(tables, edges, nodes, coordinates, wells, depths, sigma)
    test_routing(edges, tables)
    test_stale(directory, tables["E_degree"][0])
    print("test_controls: all checks passed")


if __name__ == "__main__":
    main()
