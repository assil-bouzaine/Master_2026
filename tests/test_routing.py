"""Checks of the routed inputs (src/models/routing.py).

    PFE_DATASET=v4 python -m tests.test_routing

1. Baseline edges reproduce the feature panel: with each well's own SAFRAN cell, the groundwater
   facilities within 3 km (weight 1) and the canal for every well, the routed rain, ETP, PE,
   pumping and canal series equal the panel's columns (the inputs of rungs 1-2 and of the
   baselines). The routing code and the panel code are separate, so this is a check of both. The
   "baseline" arm (routing.baseline_edges, arms A and B) has exactly these edges.
2. Arms C and D (the export): shapes, no missing value, non-negative volumes; a well without an
   edge for a relation has zeros and its flag off; coverage = the export's manifest; arm C has no
   unattributed input; arm D's routed plus unattributed pumping equals the distance-weighted sum
   over every groundwater facility within 5 km (nothing lost, nothing counted twice).
3. A hand-made case: two cells with weights 1 and 3 give the 1:3 weighted mean; two facilities
   with weights 0.5 and 2 give that weighted sum.
4. Control arms preserve their provenance and route like their explicit edge tables.
5. Pumping reconstructions preserve annual totals, keep drinking water flat in reconstruction 2,
   use crop-calendar irrigation in reconstruction 3, and supply the corresponding canal proxy.
"""
import numpy as np
import pandas as pd

from src.config import DATASET_DIR
from src.kg import export as E
from src.models.evaluate import RESULTS
from src.models.routing import coverage, load_edges, routed_inputs

EDGE = E.EDGE_COLS


def edge_table(rows):
    return pd.DataFrame([E.edge(*r) for r in rows], columns=EDGE)


def test_baseline():
    wells, fac, _, _ = E.tables()
    d = E._dist(wells, fac)
    rows = [("recharge", "weather_cell", c, w, 1.0) for w, c in zip(wells["code_bss"], wells["cell_id"])]
    rows += [("canal", "canal", E.CANAL, w, 1.0) for w in wells["code_bss"]]
    # the panel selects facilities with "contains" on a 3 km buffer polygon (src/dataset/load.py),
    # whose 64 sides lie up to 3.6 m inside the circle: 3 wells have a facility at 2,999.3-2,999.9 m
    # that the panel leaves out (found here on 2026-11-10). Same predicate, so the check is exact.
    from shapely.geometry import Point
    pts = [Point(x, y) for x, y in zip(fac["x93"], fac["y93"])]
    edge_cases = 0
    for i, (x, y) in enumerate(zip(wells["x93"], wells["y93"])):
        buf = Point(x, y).buffer(3000.0)
        for j in np.where(d[i] <= 3000.0)[0]:
            if buf.contains(pts[j]):
                rows.append(("pumping", "facility", fac["code_ouvrage"].iloc[j], wells["code_bss"].iloc[i], 1.0, d[i, j]))
            else:
                edge_cases += 1
    oracle = edge_table(rows)
    from src.models.routing import baseline_edges
    module = baseline_edges()                     # the "baseline" arm: must be this oracle's edges
    key = ["relation", "src", "dst"]
    pd.testing.assert_frame_equal(module.sort_values(key, ignore_index=True)[key + ["weight"]],
                                  oracle.sort_values(key, ignore_index=True)[key + ["weight"]])
    R = routed_inputs("baseline")
    assert R["export"]["policy"].startswith("baseline")
    P = pd.read_parquet(RESULTS / "_cache" / "panel.parquet",
                        columns=["code_bss", "week", "rain", "ETP", "PE", "pump_gw", "canal"])
    worst = {}
    for v in ("rain", "ETP", "PE", "pump_gw", "canal"):
        want = P.pivot(index="code_bss", columns="week", values=v).reindex(index=R["codes"], columns=R["weeks"])
        diff = np.abs(R[v] - want.to_numpy())
        scale = max(1.0, float(np.nanmax(np.abs(want.to_numpy()))))
        worst[v] = float(np.nanmax(diff)) / scale
        assert worst[v] < 1e-6, (v, worst[v])
    print(f"  1. baseline edges (own cell, facilities within 3 km, canal) reproduce the panel's rain, ETP, PE, "
          f"pumping and canal columns for {len(R['codes'])} wells x {len(R['weeks'])} weeks "
          f"(largest relative difference {max(worst.values()):.1e}); {edge_cases} facility-well pairs lie within "
          f"3 km but outside the panel's buffer polygon")


def test_arms():
    wells = pd.read_parquet(DATASET_DIR / "wells.parquet")
    core = wells["core"].to_numpy()
    out = {}
    for arm in ("C", "D"):
        R = routed_inputs(arm)
        edges, meta = load_edges(arm)
        N, T = len(R["codes"]), len(R["weeks"])
        for v in ("rain", "ETP", "PE", "pump_gw", "pump_un", "river", "canal"):
            assert R[v].shape == (N, T) and np.isfinite(R[v]).all(), (arm, v)
        assert (R["pump_gw"] >= 0).all() and (R["pump_un"] >= 0).all() and (R["canal"] >= 0).all()
        for rel, vars_ in (("recharge", ("rain", "ETP", "PE")), ("pumping", ("pump_gw",)),
                           ("pumping_unattributed", ("pump_un",)), ("river", ("river",)), ("canal", ("canal",))):
            off = ~R["has_" + rel]
            assert all(np.abs(R[v][off]).max(initial=0.0) == 0.0 for v in vars_), (arm, rel)
            want = meta["arms"][arm].get(rel, {"wells": 0, "core_wells": 0})
            got = coverage(R, core)[rel]
            assert (got["wells"], got["core_wells"]) == (want["wells"], want["core_wells"]), (arm, rel, got, want)
        out[arm] = R
    assert not out["C"]["has_pumping_unattributed"].any()
    # arm D: routed + unattributed = every groundwater facility within 5 km, distance-weighted
    t_wells, t_fac, _, _ = E.tables()
    d = E._dist(t_wells, t_fac)
    rows = [("pumping", "facility", t_fac["code_ouvrage"].iloc[j], t_wells["code_bss"].iloc[i],
             np.exp(-d[i, j] / E.PUMP_DECAY_M), d[i, j])
            for i in range(len(t_wells)) for j in np.where(d[i] <= E.D_RADIUS_M)[0]]
    allnear = routed_inputs(edges=edge_table(rows))
    total = out["D"]["pump_gw"] + out["D"]["pump_un"]
    # the graph's facility points are rounded to 0.1 m: its distances differ from the dataset's by
    # at most 0.08 m, the weights by about 1e-5
    assert np.allclose(total, allnear["pump_gw"], rtol=1e-4, atol=1e-6)
    cov = {a: coverage(out[a], core) for a in out}
    print("  2. arms C and D: finite series, zeros where a well has no edge, coverage = the export's manifest; "
          "arm D's routed + unattributed pumping = every groundwater facility within 5 km. Core wells with "
          "each relation, C / D: " + ", ".join(
              f"{rel} {cov['C'][rel]['core_wells']} / {cov['D'][rel]['core_wells']}" for rel in cov["D"]))


def test_weights():
    wells, fac, _, cells = E.tables()
    w = wells["code_bss"].iloc[0]
    c1, c2 = cells["cell_id"].iloc[0], cells["cell_id"].iloc[1]
    f1, f2 = fac["code_ouvrage"].iloc[0], fac["code_ouvrage"].iloc[1]
    single = {}
    for name, rows in (("c1", [("recharge", "weather_cell", c1, w, 1.0)]), ("c2", [("recharge", "weather_cell", c2, w, 1.0)]),
                       ("f1", [("pumping", "facility", f1, w, 1.0)]), ("f2", [("pumping", "facility", f2, w, 1.0)]),
                       ("mix", [("recharge", "weather_cell", c1, w, 1.0), ("recharge", "weather_cell", c2, w, 3.0),
                                ("pumping", "facility", f1, w, 0.5), ("pumping", "facility", f2, w, 2.0)])):
        single[name] = routed_inputs(edges=edge_table(rows), codes=[w])
    assert np.allclose(single["mix"]["rain"], 0.25 * single["c1"]["rain"] + 0.75 * single["c2"]["rain"])
    assert np.allclose(single["mix"]["pump_gw"], 0.5 * single["f1"]["pump_gw"] + 2.0 * single["f2"]["pump_gw"])
    print("  3. hand-made weights: cells 1 and 3 give the 1:3 mean; facilities 0.5 and 2 give that weighted sum")


def test_control_arms():
    """The control graphs of item 20 load by name, carry the export they were built from, and route
    exactly as their edge table does; unknown names are refused (--arm in the response model)."""
    from src.kg.controls import load_control
    from src.models.routing import load_arm, parse_arm
    assert parse_arm("D") == ("D", None) and parse_arm("E_degree:3") == ("E_degree", 3)
    assert parse_arm("F_complete") == ("F_complete", 0)
    assert parse_arm("baseline") == ("baseline", None)
    for bad in ("E", "E_degree", "E_degree:x", "F_complete:1", "G:0", "", "Baseline"):
        try:
            parse_arm(bad)
            raise AssertionError(f"{bad!r} must be refused")
        except ValueError:
            pass
    codes = ["10906X0039/C2-1", "10964X0119/NYLS-1"]
    edges, meta = load_arm("E_degree:0")
    assert meta["control"] == "E_degree:0" and set(meta["export_sha256"]) == {"edges_D.parquet", "nodes.parquet"}
    by_name = routed_inputs("E_degree:0", codes=codes)
    by_table = routed_inputs(edges=load_control("E_degree", 0), codes=codes)
    for k in ("rain", "pump_gw", "pump_un", "river", "canal"):
        assert np.array_equal(by_name[k], by_table[k]), k
    assert by_name["export"]["control"] == "E_degree:0" and by_table["export"] is None
    print("  4. control arms: names parsed, provenance carried, routing equals the edge table's")


def _check_reconstruction_cli(routed):
    """Stop the CLI before arrays or fitting: inspect dispatch and the fingerprint arguments."""
    import argparse
    import io
    import sys
    from contextlib import redirect_stderr, redirect_stdout
    from unittest.mock import patch

    from src.models import response

    class StopBeforeArrays(Exception):
        pass

    def preview(arguments):
        parsed = []
        original_parse = argparse.ArgumentParser.parse_args

        def capture(parser, *args, **kwargs):
            namespace = original_parse(parser, *args, **kwargs)
            parsed.append(namespace)
            return namespace

        panel = pd.DataFrame({"code_bss": routed["codes"], "mu": 0.0, "core": True})
        with (patch.object(sys, "argv", ["response", "--mode", "free", *arguments]),
              patch.object(argparse.ArgumentParser, "parse_args", capture),
              patch.object(response, "build_panel", return_value=panel),
              patch("src.models.routing.routed_inputs", return_value=routed) as dispatch,
              patch.object(response, "panel_arrays", side_effect=StopBeforeArrays),
              redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO())):
            try:
                response.main()
            except StopBeforeArrays:
                return vars(parsed[0]).copy(), dispatch.call_args
        raise AssertionError("CLI should have stopped before arrays and any output files")

    panel_args, dispatch = preview([])
    assert "pumping_reconstruction" not in panel_args and dispatch is None
    for arm in ("baseline", "C", "D", "E_degree:0", "E_distance:0", "F_random:0", "F_complete"):
        default, call = preview(["--arm", arm])
        explicit, _ = preview(["--arm", arm, "--pumping-reconstruction", "1"])
        assert default == explicit and "pumping_reconstruction" not in default
        assert call.args == (arm, "main") and call.kwargs == {"reconstruction": 1}
        for reconstruction in (2, 3):
            args, call = preview(["--arm", arm, "--pumping-reconstruction", str(reconstruction)])
            assert args["pumping_reconstruction"] == reconstruction
            assert call.args == (arm, "main") and call.kwargs == {"reconstruction": reconstruction}
    for arguments in (["--pumping-reconstruction", "2"], ["--pumping-reconstruction", "3"],
                      ["--arm", "D", "--pumping-reconstruction", "4"]):
        try:
            preview(arguments)
        except SystemExit as error:
            assert error.code == 2
        else:
            raise AssertionError(f"Invalid reconstruction arguments accepted: {arguments}")


def test_reconstructions():
    """Read all facilities for annual conservation, but route only two wells for speed."""
    import time
    from pathlib import Path
    from unittest.mock import patch

    from src.dataset.pumping import canal_series
    from src.models.routing import RECONSTRUCTIONS, facility_volumes, pumping_table

    started = time.perf_counter()
    assert RECONSTRUCTIONS == {1: "current", 2: "flat drinking water", 3: "crop calendar"}
    codes = ["10906X0039/C2-1", "10964X0119/NYLS-1"]
    default = routed_inputs("D", codes=codes)
    current = routed_inputs("D", codes=codes, reconstruction=1)
    assert default["reconstruction"] == current["reconstruction"] == 1
    for name, value in default.items():
        if isinstance(value, np.ndarray):
            np.testing.assert_array_equal(value, current[name], err_msg=name)
    weeks = default["weeks"]
    years = [year for year in sorted(set(weeks.year))
             if weeks[weeks.year == year].equals(pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="W-SUN"))]
    skipped = sorted(set(weeks.year) - set(years))
    assert years
    volumes = {number: facility_volumes(weeks, reconstruction=number) for number in RECONSTRUCTIONS}
    annual = {number: frame.groupby(weeks.year).sum().loc[years] for number, frame in volumes.items()}
    largest_relative = 0.0
    for number in (2, 3):
        pd.testing.assert_index_equal(volumes[1].columns, volumes[number].columns)
        reference, candidate = annual[1].to_numpy(), annual[number].to_numpy()
        np.testing.assert_allclose(candidate, reference, rtol=1e-9, atol=0)
        relative = np.abs(candidate - reference) / np.maximum(np.abs(reference), 1e-30)
        largest_relative = max(largest_relative, float(relative.max()))

    raw = pumping_table(2)
    pd.testing.assert_frame_equal(raw, pumping_table(1))
    drinking = sorted(set(raw.loc[raw["usage"] == "drinking water", "code_ouvrage"]) & set(volumes[2].columns))

    def weekly(rows, facilities):
        return (rows.groupby(["week", "code_ouvrage"])["volume_m3"].sum().unstack("code_ouvrage")
                .reindex(index=weeks, columns=facilities).fillna(0.0) / 1000)

    drinking_component = weekly(raw.loc[raw["usage"] == "drinking water"], drinking)
    other_rows = raw.loc[(raw["usage"] != "drinking water") & raw["code_ouvrage"].isin(drinking)]
    other_component = weekly(other_rows, drinking)
    pure_drinking = sorted(set(drinking) - set(other_rows["code_ouvrage"]))
    np.testing.assert_allclose(volumes[2][drinking], drinking_component + other_component,
                               rtol=1e-12, atol=1e-10)
    for year in years:
        for frame in (drinking_component, volumes[2][pure_drinking]):
            block = frame.loc[weeks.year == year].to_numpy()
            np.testing.assert_allclose(block.max(0), block.min(0), rtol=1e-12, atol=1e-12)

    cropcal = pumping_table(3)
    assert list(cropcal.columns) == list(raw.columns)
    edges, _ = load_edges("D")
    local = edges.loc[(edges["dst"] == codes[0]) & edges["relation"].isin(("pumping", "pumping_unattributed"))]
    irrigation = sorted(set(raw.loc[raw["usage"] == "irrigation", "code_ouvrage"]) & set(local["src"]))
    assert irrigation and not (set(irrigation) & set(drinking))
    expected = weekly(cropcal.loc[cropcal["code_ouvrage"].isin(irrigation)], irrigation)
    np.testing.assert_array_equal(volumes[3][irrigation].to_numpy(), expected.to_numpy())
    changed = np.count_nonzero(volumes[3][irrigation].to_numpy() != volumes[1][irrigation].to_numpy())
    assert changed > 0

    points = pd.read_parquet(DATASET_DIR / "pumping_points.parquet")
    for number in (2, 3):
        routed = routed_inputs("D", codes=codes, reconstruction=number)
        assert routed["reconstruction"] == number and isinstance(routed["reconstruction"], int)
        for name in ("rain", "ETP", "PE", "river"):
            np.testing.assert_array_equal(routed[name], default[name])
        for relation, name in (("pumping", "pump_gw"), ("pumping_unattributed", "pump_un")):
            for row, code in enumerate(codes):
                links = edges.loc[(edges["relation"] == relation) & (edges["dst"] == code)]
                expected = volumes[number][list(links["src"])].to_numpy() @ links["weight"].to_numpy()
                np.testing.assert_allclose(routed[name][row], expected, rtol=1e-12, atol=1e-10)
        if number == 2:
            np.testing.assert_array_equal(routed["canal"], default["canal"])
        else:
            canal = canal_series(cropcal, points).reindex(weeks).fillna(0.0).to_numpy() / 1e6
            np.testing.assert_array_equal(routed["canal"], routed["has_canal"][:, None] * canal[None, :])

    for bad in (0, 4):
        try:
            pumping_table(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Invalid reconstruction {bad} accepted")
    with patch.object(Path, "is_file", return_value=False):
        try:
            pumping_table(3)
        except FileNotFoundError as error:
            assert "python -m src.dataset.pumping_cropcal" in str(error)
        else:
            raise AssertionError("Missing crop-calendar table must explain how to build it")
    _check_reconstruction_cli(default)
    print(f"  5. reconstructions: {len(volumes[1].columns)} facilities, whole years {years}; "
          f"partial years skipped {skipped}; largest annual relative difference {largest_relative:.2e}")
    print(f"     flat drinking water: all {len(drinking)} components and {len(pure_drinking)} pure-facility series; "
          f"{len(drinking) - len(pure_drinking)} mixed-use facilities retain their other uses")
    print(f"     crop-calendar irrigation: {len(irrigation)} facilities near {codes[0]}, {changed} changed values; "
          f"canal proxies, metadata and CLI dispatch pass ({time.perf_counter() - started:.1f}s)")


if __name__ == "__main__":
    test_baseline()
    test_arms()
    test_weights()
    test_control_arms()
    test_reconstructions()
    print("test_routing: all checks passed")
