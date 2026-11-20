"""Check the arm D version of the Taccari graph (Gate 3 decision 21).

    PFE_DATASET=v4 python -m tests.test_taccari_export

The toy graph checks edge directions and weights. The real graph checks the input
series and the network's output shape. The command check intercepts the training runner.
"""
import json
import tempfile
from collections import Counter
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import numpy as np
import pandas as pd
import torch

from src.kg.export import EDGE_COLS, edge
from src.models import routing, taccari
from src.models.features import build_panel, river_series
from src.models.lstm import arrays, run_fingerprint


def edge_table(rows):
    return pd.DataFrame([edge(*row) for row in rows], columns=EDGE_COLS)


def test_toy_adjacency():
    codes = ["A", "B", "C"]
    edges = edge_table([
        ("recharge", "weather_cell", "c1", "A", 0.25),
        ("recharge", "weather_cell", "c2", "A", 0.75),
        ("recharge", "weather_cell", "c2", "C", 1.0),
        ("river", "gauge", "g1", "A", 1.5),
        ("pumping", "facility", "p1", "A", 3.0),
        ("pumping", "facility", "p2", "B", 4.0),
        ("pumping_unattributed", "facility", "p1", "A", 0.15),
        ("pumping_unattributed", "facility", "p2", "A", 0.35),
        ("pumping_unattributed", "facility", "p2", "C", 0.6),
        ("canal", "canal", "canal-intakes:plain", "B", 0.5),
        ("well_link", "well", "B", "A", 0.5),
        ("well_link", "well", "A", "B", 0.5),
        ("recharge_unitwide", "weather_cell", "c1", "B", 0.9),
        ("recharge", "weather_cell", "outside-cell", "outside-well", 1.0),
    ])
    names = ["cell:c1", "cell:c2", "gauge:g1", "facility:p1", "facility:p2",
             "unattributed:A", "unattributed:C", "canal:plain"]
    nodes = [(name, None, np.nan, np.nan, {}) for name in names]
    selected = taccari.select_export_edges(edges, codes)
    actual = taccari.export_adjacency(codes, nodes, selected)
    # Columns are A, B, C, then the exogenous names above. Exogenous rows are identity rows.
    self_only = np.eye(11)[3:]
    expected = np.vstack(([
        [1, 0.5, 0, 0.25, 0.75, 1.5, 3, 0, 1, 0, 0],
        [0.5, 1, 0, 0, 0, 0, 0, 4, 0, 0, 0.5],
        [0, 0, 1, 0, 1, 0, 0, 0, 0, 1, 0],
    ], self_only))
    expected_normalised = np.vstack(([
        [1/8, 1/16, 0, 1/32, 3/32, 3/16, 3/8, 0, 1/8, 0, 0],
        [1/12, 1/6, 0, 0, 0, 0, 0, 2/3, 0, 0, 1/12],
        [0, 0, 1/3, 0, 1/3, 0, 0, 0, 0, 1/3, 0],
    ], self_only))
    np.testing.assert_array_equal(actual, expected)
    np.testing.assert_array_equal(taccari.normalise_adjacency(actual).numpy(),
                                  expected_normalised.astype(np.float32))
    print("  1. Toy graph matches both hand-written matrices (11 nodes)")


def test_real_arm():
    P = build_panel()
    P = P[P["mu"].notna()]
    data = arrays(P)
    codes, weeks = data[:2]
    train_cols = np.flatnonzero(data[4][0] == "train")
    edges, _ = routing.load_arm("D")
    selected = taccari.select_export_edges(edges, codes)
    nodes = taccari.export_nodes(selected, codes, weeks, train_cols)
    well_edges = edges[edges["dst"].isin(codes)]
    sources = well_edges.groupby("relation")["src"].nunique()
    un_wells = set(well_edges.loc[well_edges["relation"] == "pumping_unattributed", "dst"])
    count = Counter(t for _, t, *_ in nodes)
    expected = {"weather": sources["recharge"], "river": sources["river"],
                "pumping": sources["pumping"] + len(un_wells), "canal": int("canal" in sources)}
    assert count == expected
    assert [(taccari.TYPES.index(t), name) for name, t, *_ in nodes] == sorted(
        (taccari.TYPES.index(t), name) for name, t, *_ in nodes)
    print(f"  2. D node counts: piezometer={len(codes)}, weather={count['weather']}, "
          f"river={count['river']}, pumping={count['pumping']} "
          f"({sources['pumping']} facilities + {len(un_wells)} unattributed), canal={count['canal']}")

    series = {name: features for name, _, _, _, features in nodes}
    routed = routing.routed_inputs("D", codes=codes, weeks=weeks)
    assert {n for n in series if n.startswith("unattributed:")} == {f"unattributed:{c}" for c in un_wells}
    max_error = 0.0
    for i, code in enumerate(codes):
        name = f"unattributed:{code}"
        if name in series:
            actual = np.expm1(series[name]["logvol"])
            want = routed["pump_un"][i]
            assert np.allclose(actual, want, rtol=1e-9, atol=1e-12), code
            max_error = max(max_error, float(np.max(np.abs(actual - want))))
    print(f"  3. Unattributed volumes match routing for every linked well (max error {max_error:.2e})")

    distance = {name: feats for name, _, _, _, feats in taccari.exogenous_nodes(P, codes, weeks, train_cols)}
    cell = sorted(name for name in series.keys() & distance.keys() if name.startswith("cell:"))[0]
    assert series[cell].keys() == distance[cell].keys()
    for feature in distance[cell]:
        np.testing.assert_array_equal(series[cell][feature], distance[cell][feature])
    train_end = str(weeks[train_cols][-1])[:10]
    declared = river_series(pd.DatetimeIndex(weeks), train_end, rule="declared")
    for gauge in well_edges.loc[well_edges["relation"] == "river", "src"].unique():
        np.testing.assert_array_equal(series[f"gauge:{gauge}"]["logq"], declared[gauge].to_numpy())
    np.testing.assert_array_equal(series["canal:plain"]["canal"], distance["canal:plain"]["canal"])
    print(f"  4. All weather features of {cell} match the distance graph. Every gauge matches "
          f"the declared rule through training end {train_end}. The canal series match.")

    names, _, Xn, *_ = taccari.prepare(P, data, edges=edges)
    assert names == list(codes) + [name for name, *_ in nodes]
    assert np.isfinite(Xn).all()
    net = taccari.TaccariNet(Xn.shape[-1], taccari._GRAPH[tuple(names)]).eval()
    generator = torch.Generator().manual_seed(17)
    with torch.no_grad():
        output = net(torch.randn(2, len(names), 7, Xn.shape[-1], generator=generator))
    assert output.shape == (2, len(names)) and torch.isfinite(output).all()
    print(f"  6. Finite forward output of shape {tuple(output.shape)} from node array {Xn.shape}")


def test_invalid_edges():
    row = ("recharge", "weather_cell", "c1", "A", 1.0)
    for rows, message in (([("unknown", *row[1:])], "unknown"),
                          ([row, (*row[:-1], 0.5)], "duplicated")):
        try:
            taccari.select_export_edges(edge_table(rows), ["A"])
        except ValueError as error:
            assert message in str(error)
        else:
            raise AssertionError(f"{message} relation or edge was accepted")

    weeks = pd.date_range("2019-12-01", periods=4, freq="W")
    for relation, kind in (("recharge", "weather_cell"), ("river", "gauge"),
                           ("pumping", "facility"), ("pumping_unattributed", "facility")):
        edges = edge_table([(relation, kind, "missing-source", "A", 1.0)])
        try:
            taccari.export_nodes(edges, ["A"], weeks, np.arange(len(weeks)))
        except ValueError as error:
            assert "without a series: missing-source" in str(error)
        else:
            raise AssertionError(f"a missing {kind} was accepted")
    print("  5. Unknown relations, duplicate keys and missing source series raise ValueError")


def test_command():
    _, meta = routing.load_arm("D")
    cases = (([], "taccari"), (["--edges", "distance"], "taccari"),
             (["--edges", "D"], "taccari_D"),
             (["--edges", "D", "--run", "taccari_D_named"], "taccari_D_named"))
    empty = Path(tempfile.mkdtemp())          # no run folder exists: the guard lets every case pass
    for flags, name in cases:
        with patch("sys.argv", ["taccari", *flags]), patch.object(taccari, "run_graph_model") as runner, \
                patch.object(taccari, "RESULTS", empty):
            taccari.main()
        runner.assert_called_once()
        args, build, prepare = runner.call_args.args
        assert args.run == name and build is taccari.build
        if "D" in flags:
            assert args.edges == "D"
            assert prepare.func is taccari.prepare and "edges" in prepare.keywords
            expected = {key: meta[key] for key in ("release", "policy", "code_version")}
            assert all(vars(args)[key] == value for key, value in expected.items())
            fp = run_fingerprint(args, [])
            for key, value in (expected | {"edges": "D"}).items():
                setattr(args, key, "changed")
                assert run_fingerprint(args, []) != fp
                setattr(args, key, value)
        else:
            assert prepare is taccari.prepare
            assert vars(args) == vars(taccari.parser(taccari.RUN).parse_args([]))
    print("  7. CLI selects the graph and run name, preserves distance settings and fingerprints D provenance")


def test_guard():
    """An arm D run refuses a folder made without --edges D (lead's review of T17): a folder
    from before the fingerprints would otherwise hand its distance seeds to arm D."""
    root = Path(tempfile.mkdtemp())
    for run, config in (("legacy", {"run": "legacy"}), ("old/fold_0", {"edges": "distance"}),
                        ("mine", {"edges": "D"})):
        (root / run).mkdir(parents=True)
        (root / run / "config.json").write_text(json.dumps(config))
    for run, refused in (("legacy", True), ("old", True), ("mine", False), ("new", False)):
        with patch("sys.argv", ["taccari", "--edges", "D", "--run", run]), \
                patch.object(taccari, "run_graph_model") as runner, patch.object(taccari, "RESULTS", root):
            try:
                taccari.main()
                stopped = False
            except SystemExit:
                stopped = True
        assert stopped == refused and runner.called == (not refused), run
    print("  8. --edges D refuses run folders made by distance runs (legacy, fold) and accepts its own")


if __name__ == "__main__":
    start = perf_counter()
    torch.set_num_threads(2)
    test_toy_adjacency()
    test_invalid_edges()
    test_real_arm()
    test_command()
    test_guard()
    print(f"test_taccari_export: all checks passed ({perf_counter() - start:.2f}s)")
