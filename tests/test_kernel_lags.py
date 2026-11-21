"""Check weekly response delays used beside physical times (analysis plan §14 item 18).

An isolated unit stress passes through the model's real convolution. Its
observed delay must match the kernel summaries, including truncated kernels.
Read saved parameters to check the review's PONT example without refitting.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_kernel_lags
"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch

import numpy as np
import pandas as pd
import torch

from src.analysis import ladder_report as L
from src.config import ROOT
from src.models import response as R

SCRATCH = ROOT / "results" / "_agents" / "tmp"
PONT = "10972X0137/PONT"
MEAN_COLUMN = "implemented recharge mean delay, days"
PEAK_COLUMN = "implemented pumping peak delay, days"


def test_impulse():
    kernel_weeks, issue = 40, 3
    a = np.repeat(np.array([7.0, 12.0, 48.0], dtype=np.float32)[:, None], 3, axis=1)
    n = np.repeat(np.array([2.2, 1.0, 2.5], dtype=np.float32)[:, None], 3, axis=1)
    state = torch.random.get_rng_state().clone()
    mean, peak = R.kernel_moments(a, n, kernel_weeks)
    assert torch.equal(state, torch.random.get_rng_state()), "reporting changed the global random state"
    assert mean.shape == peak.shape == a.shape
    assert a[2, 0] * n[2, 0] > kernel_weeks
    assert peak[1, 0] == 0 and peak[2, 0] == kernel_weeks - 1
    assert (mean >= 0).all() and (mean < kernel_weeks).all()
    length = kernel_weeks + issue + 3
    for conv in ("direct", "fft"):
        net = R.ResponseModel([0, 0, 0], 1, kernel_weeks=kernel_weeks, conv=conv,
                              generator=torch.Generator().manual_seed(0))
        gain = torch.tensor([[1.0, -1.0, 1.0]] * 3)
        physical = gain, torch.from_numpy(a), torch.from_numpy(n), torch.zeros(3)
        inputs = {name: torch.zeros((3, length + kernel_weeks - 1))
                  for name in ("rain", "ETP", "PE", "pump_gw", "canal")}
        for name in ("rain", "pump_gw", "canal"):
            inputs[name][:, kernel_weeks - 1 + issue] = 1.0
        with patch.object(net, "parameters_physical", return_value=physical), torch.no_grad():
            response = net.contributions(inputs).numpy() / gain.numpy()[..., None]
        np.testing.assert_allclose(response[..., :issue], 0, rtol=0, atol=1e-7)
        np.testing.assert_allclose(response[..., issue + kernel_weeks:], 0, rtol=0, atol=1e-7)
        mass = response.sum(axis=-1)
        np.testing.assert_allclose(mass, 1, rtol=0, atol=1e-6)
        delay = np.arange(length) - issue
        observed_mean = (response * delay).sum(axis=-1) / mass
        observed_peak = response.argmax(axis=-1) - issue
        np.testing.assert_allclose(mean, observed_mean, rtol=0, atol=1e-5)
        np.testing.assert_array_equal(peak, observed_peak)
    print("  1. Direct and FFT unit impulses recover the mean and peak delays, including n = 1 "
          "and a continuous mean beyond the kernel; reporting preserves the random state.")


def test_seed_exports():
    weeks = pd.date_range("2024-01-07", periods=8, freq="W-SUN")
    for pumping in R.STRESS_SETS:
        net = R.ResponseModel([0, 0], 1, kernel_weeks=7, init_sd=0.3, pumping=pumping,
                              generator=torch.Generator().manual_seed(1))
        inputs = {name: np.ones((2, len(weeks) + net.K - 1), dtype=np.float32)
                  for name in ("rain", "ETP", "PE", *R.STRESS_INPUT.values())}
        data = {"X": inputs, "sd": np.ones((2, len(weeks))), "codes": ["toy0", "toy1"],
                "weeks": weeks, "groups": ["toy"], "group_of": np.array([0, 0])}
        _, _, params = R.seed_outputs(net, data)
        with torch.no_grad():
            _, a, n, _ = net.parameters_physical()
            weights = net.kernels(a, n).numpy()
        # --signs gate3 layout: the saved "river" is the slot each well feeds (river_c where its
        # river_c input is non-zero: every toy well here), so river_c has no columns of its own
        slot = {stress: np.full(2, index) for index, stress in enumerate(net.names)}
        if "river_c" in slot:
            fed = np.abs(inputs["river_c"]).sum(1) > 0
            slot["river"] = np.where(fed, slot.pop("river_c"), slot["river"])
        rows = np.arange(2)
        for stress, index in slot.items():
            np.testing.assert_array_equal(params[f"mean_lag_{stress}_wk"], (a * n).numpy()[rows, index])
            np.testing.assert_allclose(params[f"impl_mean_lag_{stress}_wk"],
                                       (weights[rows, index] * np.arange(net.K)).sum(axis=-1), rtol=0, atol=0)
            np.testing.assert_array_equal(params[f"impl_peak_lag_{stress}_wk"],
                                          weights[rows, index].argmax(axis=-1))
        assert not any(col.endswith("river_c_wk") for col in params.columns)
    print("  2. Every stress in the sum, split, arm and gate3 layouts retains its continuous mean "
          "and exports the implemented mean and peak using the model's kernel length.")


def test_saved_parameters():
    folder = L.RESULTS / "resp_free"
    path = folder / "params_seed_0.csv"
    params = pd.read_csv(path)
    print("     saved parameter columns:", params.columns.tolist())
    print(params.head(1).to_string(index=False))
    kernel_weeks = json.loads((folder / "schema.json").read_text())["kernel_weeks"]
    stresses = [column.removeprefix("a_").removesuffix("_wk") for column in params
                if column.startswith("a_") and column.endswith("_wk")]
    a = params[[f"a_{stress}_wk" for stress in stresses]].to_numpy()
    n = params[[f"n_{stress}" for stress in stresses]].to_numpy()
    mean, peak = R.kernel_moments(a, n, kernel_weeks)
    pont = int(np.flatnonzero(params["code_bss"].eq(PONT))[0])
    recharge = stresses.index("recharge")
    print(f"  3. PONT recharge, resp_free start 0, K={kernel_weeks}: "
          f"continuous mean {a[pont, recharge] * n[pont, recharge]:.6f} weeks; "
          f"implemented mean {mean[pont, recharge]:.6f} weeks; peak {peak[pont, recharge]} weeks.")
    differences = 7 * np.abs(a * n - mean)
    for index, stress in enumerate(stresses):
        well = int(differences[:, index].argmax())
        print(f"     largest {stress} mean-delay difference: {differences[well, index]:.6f} days "
              f"at {params.iloc[well]['code_bss']}")
    well, stress = np.unravel_index(differences.argmax(), differences.shape)
    print(f"     largest over all wells and stresses: {differences[well, stress]:.6f} days "
          f"at {params.iloc[well]['code_bss']}, {stresses[stress]}")


def test_comparator():
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=SCRATCH) as tmp:
        root = Path(tmp)
        runs = {"resp_fixture": "sum fixture", "resp_fixture_split": "split fixture"}
        with patch.object(L, "RESULTS", root), patch.object(L, "RUNS", runs):
            for run, pumping in (("resp_fixture", "pumping"), ("resp_fixture_split", "pumping_seasonal")):
                folder = root / run
                folder.mkdir()
                a, n = np.array([[4.0, 7.0], [5.0, 8.0]]), np.array([[2.5, 2.0], [2.5, 2.0]])
                for seed in (0, 1):
                    pd.DataFrame({"code_bss": [PONT], "a_recharge_wk": [a[seed, 0]],
                                  "n_recharge": [n[seed, 0]], f"a_{pumping}_wk": [a[seed, 1]],
                                  f"n_{pumping}": [n[seed, 1]],
                                  "mean_lag_recharge_wk": [a[seed, 0] * n[seed, 0]]}).to_csv(
                        folder / f"params_seed_{seed}.csv", index=False)
                for kernel_weeks in (5, 17):
                    (folder / "schema.json").write_text(json.dumps({"kernel_weeks": kernel_weeks}))
                    rows = L.comparator(run)
                    assert len(rows) == 1
                    mean, peak = R.kernel_moments(a, n, kernel_weeks)
                    for column, values in ((MEAN_COLUMN, 7 * mean[:, 0]), (PEAK_COLUMN, 7 * peak[:, 1])):
                        expected = np.median(values), np.min(values), np.max(values)
                        np.testing.assert_allclose(rows[0][1][column], expected, rtol=0, atol=0)
                    assert rows[0][1]["BRGM mean transit, days"] == L.BRGM[PONT][1]
                    assert rows[0][1]["BRGM, days"] == L.BRGM_PUMP_DAYS
            try:
                L.comparator("missing_schema")
            except FileNotFoundError as error:
                assert "schema.json" in str(error) and "kernel_weeks" in str(error), error
            else:
                raise AssertionError("a missing kernel length was guessed")
    print("  4. Physical comparisons read the saved kernel length, select seasonal pumping when present, "
          "convert weeks to days and refuse a missing schema.")


def main():
    started = time.perf_counter()
    torch.set_num_threads(4)
    with patch.object(R, "train_seed", side_effect=AssertionError("kernel checks must not fit")):
        test_impulse()
        test_seed_exports()
        test_saved_parameters()
        test_comparator()
    print(f"test_kernel_lags: all checks passed ({time.perf_counter() - started:.1f}s)")


if __name__ == "__main__":
    main()
