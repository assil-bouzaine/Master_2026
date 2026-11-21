"""Check the two B7 recharge sensitivities (analysis plan §14 items 15 and 18).

Run with PFE_DATASET=v4 python -m tests.test_recharge_options. The checks use the
v4 cache and export. They stop at the model's fitting entry point and use a
fixed initialization to compare predictions without fitting.
"""
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest.mock import patch

import numpy as np
import pandas as pd
import torch

from src.config import DATASET_DIR, ROOT
from src.models import response, routing
from src.models.features import CACHE

BEFORE_B7 = "8bb1a23cddfb1ff07c9f06a89d7c68afe055b369"
SCRATCH = ROOT / "results" / "_agents" / "tmp"


class BeforeFit(Exception):
    """Stop after the CLI builds the model inputs and run identity."""


def prepare_run(folder, options, module=response, route=routing.routed_inputs):
    routed = {}

    def record_route(*args, **kwargs):
        routed.update(route(*args, **kwargs))
        return routed

    assert CACHE.is_file(), f"v4 panel cache missing at {CACHE}"
    argv = ["response", "--mode", "free", "--seeds", "0", *options]
    with (patch.object(sys, "argv", argv), patch.object(module, "RESULTS", folder),
          patch.object(routing, "routed_inputs", record_route),
          patch.object(module, "train_seed", side_effect=BeforeFit) as train):
        try:
            module.main()
        except BeforeFit:
            train.assert_called_once()
        else:
            raise AssertionError("Expected the CLI to reach the fitting entry point")
    out = folder / "resp_free"
    return routed, train.call_args, (out / "config.json").read_bytes(), (out / "schema.json").read_bytes()


def historical_module(name):
    path = f"src/models/{name}.py"
    source = subprocess.check_output(["git", "show", f"{BEFORE_B7}:{path}"], cwd=ROOT)
    module = ModuleType(f"{name}_before_b7")
    exec(compile(source, path, "exec"), module.__dict__)
    return module


def assert_identical(actual, expected, label):
    if isinstance(expected, dict):
        assert list(actual) == list(expected), label
        for key in expected:
            assert_identical(actual[key], expected[key], f"{label}.{key}")
    elif isinstance(expected, np.ndarray):
        assert actual.dtype == expected.dtype and actual.shape == expected.shape, label
        if expected.dtype.hasobject:
            np.testing.assert_array_equal(actual, expected, err_msg=label)
        else:
            assert actual.tobytes() == expected.tobytes(), label
    elif isinstance(expected, pd.DatetimeIndex):
        pd.testing.assert_index_equal(actual, expected, obj=label)
    else:
        assert actual == expected, label


def model_at_start(module, call):
    seed, data, mode, *_ = call.args
    settings = {key: call.kwargs[key] for key in ("kernel_weeks", "amax", "recharge", "pumping", "conv")}
    return module.ResponseModel(data["group_of"], len(data["groups"]), mode, init_sd=0.5,
                                generator=torch.Generator().manual_seed(seed), **settings)


def test_bit_identity():
    old_response = historical_module("response")
    old_routing = historical_module("routing")
    SCRATCH.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(4)
    with TemporaryDirectory(prefix="T14_", dir=SCRATCH) as scratch:
        for arm, arm_args in (("raw", []), ("D", ["--arm", "D"])):
            for proxy, proxy_args in (("linear", []), ("pe", ["--recharge", "pe", "--conv", "fft"])):
                label = f"{arm}/{proxy}"
                folder = Path(scratch) / arm / proxy
                options = arm_args + proxy_args
                old, before, config_before, schema_before = prepare_run(
                    folder / "old", options, old_response, old_routing.routed_inputs)
                new, after, config_after, schema_after = prepare_run(folder / "new", options)
                assert_identical(new, old, f"{label} routing")
                assert config_after == config_before and schema_after == schema_before, label
                assert "DRAINC" not in after.args[1]["X"]
                assert_identical(after.args[1], before.args[1], f"{label} model arrays")
                for key in ("train_mask", "es_wells"):
                    assert_identical(after.kwargs[key], before.kwargs[key], f"{label} {key}")
                p0 = old_response.seed_outputs(model_at_start(old_response, before), before.args[1])[0]
                p1 = response.seed_outputs(model_at_start(response, after), after.args[1])[0]
                assert_identical(p1, p0, f"{label} predictions")
                if arm == "D" and proxy == "pe":
                    _, _, explicit_config, explicit_schema = prepare_run(
                        folder / "explicit", [*options, "--recharge-relation", "recharge"])
                    assert explicit_config == config_after and explicit_schema == schema_after
                print(f"  {label}: {p1.shape[0]} wells x {p1.shape[1]} weeks, "
                      f"fingerprint {json.loads(config_after)['fingerprint']}, exact arrays and predictions")


def weighted_weather(rows, variable, weeks):
    """An independent weighted mean for one well, over the supplied dates."""
    forcing = pd.read_parquet(DATASET_DIR / "forcing_weekly.parquet", columns=["week", "cell_id", variable])
    values = forcing.pivot(index="week", columns="cell_id", values=variable).loc[weeks, rows["src"]]
    weights = rows["weight"].to_numpy()
    return (values.to_numpy() * weights).sum(axis=1) / weights.sum()


def test_b7_options():
    edges, _ = routing.load_edges("D")
    counts = {}
    for relation in ("recharge", "recharge_unitwide"):
        links = edges[edges["relation"] == relation]
        assert len(links) and not links.duplicated(["dst", "src"]).any() and links["weight"].gt(0).all()
        counts[relation] = links.groupby("dst")["src"].nunique()
        # Gate 3 point 12: cells holding under 0.001 of an outcrop are dropped from the export (the
        # graph keeps them), so a well's stored weights may sum to slightly under 1; routing
        # renormalises them to 1 (src/kg/export.py docstring, weighted_weather below).
        sums = links.groupby("dst")["weight"].sum()
        assert ((sums > 0.99) & (sums <= 1 + 1e-12)).all(), sums[(sums <= 0.99) | (sums > 1 + 1e-12)]
        print(f"  {relation}: {len(counts[relation])} wells, {len(links)} edges, weights sum to at most 1 "
              f"per well (lowest {sums.min():.6f}: tiny cells dropped; routing renormalises)")
    comparisons = pd.DataFrame(counts).fillna(0)
    assert (comparisons["recharge_unitwide"] >= comparisons["recharge"]).all()
    wider = comparisons["recharge_unitwide"] > comparisons["recharge"]
    assert wider.any()
    well = comparisons.index[wider & (comparisons["recharge"] > 1)][0]
    links = edges[edges["dst"] == well]

    SCRATCH.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="T14_", dir=SCRATCH) as scratch:
        folder = Path(scratch)
        unit, _, unit_config, unit_schema = prepare_run(
            folder / "unitwide", ["--arm", "D", "--recharge", "pe", "--recharge-relation", "recharge_unitwide"])
        local, _, local_config, _ = prepare_run(folder / "local", ["--arm", "D", "--recharge", "pe"])
        drainage, call, drain_config, drain_schema = prepare_run(
            folder / "drainage", ["--arm", "D", "--recharge", "drainc"])
        _, raw_call, raw_config, raw_schema = prepare_run(folder / "raw", ["--recharge", "drainc"])

    configs = [json.loads(blob) for blob in (unit_config, local_config, drain_config)]
    assert len({config["fingerprint"] for config in configs}) == 3
    assert configs[0]["recharge_relation"] == json.loads(unit_schema)["recharge_relation"] == "recharge_unitwide"
    np.testing.assert_array_equal(unit["has_recharge"], np.isin(unit["codes"], counts["recharge_unitwide"].index))
    assert configs[0]["inputs"] == configs[1]["inputs"]
    assert "recharge_relation" not in configs[1] and "recharge_relation" not in configs[2]
    weeks = unit["weeks"][:3]
    row = unit["codes"].index(well)
    expected_pe = weighted_weather(links[links["relation"] == "recharge_unitwide"], "PE", weeks)
    np.testing.assert_allclose(unit["PE"][row, :3], expected_pe, rtol=1e-12, atol=1e-12)
    assert not np.allclose(unit["PE"][row, :3], local["PE"][row, :3])
    expected_drainage = weighted_weather(links[links["relation"] == "recharge"], "DRAINC", weeks)
    np.testing.assert_allclose(drainage["DRAINC"][row, :3], expected_drainage, rtol=1e-12, atol=1e-12)

    panel = pd.read_parquet(CACHE, columns=["week", "code_bss", "DRAINC"])
    panel_values = panel[panel["code_bss"] == well].set_index("week").loc[weeks, "DRAINC"].to_numpy()
    for case, config, schema, expected in ((call, drain_config, drain_schema, expected_drainage),
                                            (raw_call, raw_config, raw_schema, panel_values)):
        data = case.args[1]
        net = model_at_start(response, case)
        X = {k: torch.from_numpy(v) for k, v in data["X"].items()}
        with torch.no_grad():
            stress = net.stresses(X, net.parameters_physical()[3])
        assert stress.shape[1] == len(net.names) and torch.equal(stress[:, 0], X["DRAINC"])
        i, start = data["codes"].index(well), net.K - 1
        np.testing.assert_array_equal(stress[i, 0, start:start + 3].numpy(), (expected / 10).astype(np.float32))
        assert json.loads(config)["inputs"] == json.loads(schema)["inputs"]
        assert json.loads(config)["inputs"][-1] == "DRAINC/10"
    print(f"  {well}: first three weeks' routed {expected_drainage.tolist()} and panel "
          f"{panel_values.tolist()} mm/week match the single recharge stress at cm/week scale")


def test_relation_requires_arm():
    for relation in ("recharge", "recharge_unitwide"):
        argv = ["response", "--mode", "free", "--recharge-relation", relation]
        with (patch.object(sys, "argv", argv), patch.object(response, "build_panel") as panel,
              patch("sys.stderr") as stderr):
            try:
                response.main()
            except SystemExit as error:
                assert error.code == 2 and "--recharge-relation needs --arm" in stderr.write.call_args.args[0]
            else:
                raise AssertionError(f"Accepted {relation} without --arm")
            panel.assert_not_called()


if __name__ == "__main__":
    test_bit_identity()
    test_b7_options()
    test_relation_requires_arm()
    print("test_recharge_options: all checks passed")
