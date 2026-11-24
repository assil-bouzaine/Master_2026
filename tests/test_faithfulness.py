"""Checks of input-space intervention faithfulness (src/explain/faithfulness.py).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_faithfulness

Why this test exists (docs/analysis_plan.md §12; docs/notes/step15_explanations.md; tasks T49, T50)
--------------------------------------------------------------------------------------------------
1. Synthetic ResponseModel with known parameters (no training):
   - closed-form hand-computed intervention effects for sustained anomalies (kernel sums to 1)
     and for a single-week impulse at a known lag (exact kernel weight);
   - exact linear superposition (sum of single-group removals == all-group removal within 1e-6 m);
   - fidelity+ and fidelity- match hand formulas;
   - residual refuses direct intervention and does not alter any driver intervention;
   - gate3 river_c/river split and pe/drainc recharge modes intervene on the exact inputs from
     response.stress_inputs;
   - end-to-end fidelity() on a disk-backed synthetic run folder (with seasonal residual) verifies
     default average_forcing has |stated - intervened| <= 1e-6 m for every intervenable group and
     that the training_seasonal sensitivity table matches explicit reference="training_seasonal".
2. Real run results/v4/resp_pooled_l001 on summer 2024 (2024-06-01..2024-09-30) for two core
   wells (10964X0119/NYLS-1, 10906X0039/C2-1):
   - verifies superposition <= 1e-6 m across all 10 seeds;
   - verifies under default average_forcing that |stated - intervened| <= 1e-6 m for every group;
   - verifies the second table (training_seasonal sensitivity) preserves the documented warm-up gap;
   - verifies linear identities for fidelity+ and fidelity-;
   - runs the CLI and prints both tables.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch

import numpy as np
import pandas as pd
import torch

from src.explain import faithfulness as F
from src.explain.contributions import _iso_week_of_year
from src.models import response as R
from src.models.lstm import save_seed, save_seed_model, write_config

CORE_SAMPLE = ("10964X0119/NYLS-1", "10906X0039/C2-1")


def _build_known_network(
    N: int = 2,
    T: int = 208,
    K: int = 12,
    *,
    pumping: str = "sum",
    signs: str = "structure",
    recharge: str = "linear",
    residual: str = "none",
    weeks: pd.DatetimeIndex | None = None,
) -> R.ResponseModel:
    """Construct a deterministic ResponseModel with known non-trivial parameters (no training)."""
    if weeks is None:
        weeks = pd.date_range("2020-01-05", periods=T, freq="W-SUN")
    sd = np.full(N, 1.0, dtype=np.float32)
    res_basis = R.seasonal_basis(weeks) if residual == "seasonal" else None
    res_bound = R.RESIDUAL_BOUND_SD * sd if residual == "seasonal" else None
    gen = torch.Generator().manual_seed(7)
    net = R.ResponseModel(
        group_of=np.arange(N) % 2,
        n_groups=min(2, N),
        mode="free",
        kernel_weeks=K,
        amax=20.0,
        recharge=recharge,
        init_sd=0.8,
        generator=gen,
        pumping=pumping,
        signs=signs,
        residual=residual,
        residual_basis=res_basis,
        residual_bound=res_bound,
    )
    with torch.no_grad():
        net.d.copy_(torch.linspace(-0.3, 0.4, N))
        if net.res_coef is not None:
            net.res_coef.copy_(torch.tensor([[0.5, -0.3, 0.2, 0.1], [-0.4, 0.6, -0.1, 0.3]])[:N])
    net.eval()
    return net


def _periodic_inputs(weeks: pd.DatetimeIndex, K: int, N: int = 2) -> dict[str, np.ndarray]:
    """Generate strictly periodic (by ISO week of year) padded inputs across all columns."""
    padded = F._padded_weeks(weeks, K)
    woy = _iso_week_of_year(padded).astype(np.float64)
    phase = 2.0 * np.pi * (woy - 1.0) / 52.0
    X = {}
    scales = np.linspace(1.0, 1.4, N)[:, None]
    X["rain"] = (scales * (2.0 + 1.0 * np.cos(phase)[None, :])).astype(np.float32)
    X["ETP"] = (scales * (1.5 - 0.8 * np.cos(phase)[None, :])).astype(np.float32)
    X["PE"] = (scales * (1.0 + 0.7 * np.cos(phase)[None, :])).astype(np.float32)
    X["DRAINC"] = (scales * (0.8 + 0.5 * np.cos(phase)[None, :])).astype(np.float32)
    X["pump_gw"] = (scales * (1.2 - 0.5 * np.cos(phase)[None, :])).astype(np.float32)
    X["pump_un"] = (scales * (0.6 - 0.2 * np.cos(phase)[None, :])).astype(np.float32)
    X["river"] = (scales * (3.0 + 0.9 * np.sin(phase)[None, :])).astype(np.float32)
    X["canal"] = (scales * (0.5 - 0.3 * np.cos(phase)[None, :])).astype(np.float32)
    return X


def test_synthetic_hand_calculations_and_superposition():
    """Verify closed-form sustained and impulse interventions, keep_only, superposition, and residual."""
    K = 12
    # 4 years (2020-2023): train = 2020-2021, target = summer 2023 (far from 2020 ISO week 53).
    weeks = pd.date_range("2020-01-05", "2023-12-31", freq="W-SUN")
    T = len(weeks)
    N = 2
    codes = ["W0", "W1"]
    target = ("2023-06-01", "2023-09-30")
    train_win = ("2020-01-01", "2021-12-31")
    t_idx = np.where((weeks >= target[0]) & (weeks <= target[1]))[0]
    t0, t1 = int(t_idx[0]), int(t_idx[-1])
    mem_slice = slice(t0, t1 + K)

    net = _build_known_network(N=N, T=T, K=K, residual="seasonal", weeks=weeks)
    with torch.no_grad():
        gain, a, n, f = (t.numpy().astype(np.float64) for t in net.parameters_physical())
        kernels = net.kernels(
            torch.from_numpy(a.astype(np.float32)), torch.from_numpy(n.astype(np.float32))
        ).numpy().astype(np.float64)

    # Known sustained shifts over the full kernel memory of summer 2023.
    X = _periodic_inputs(weeks, K, N=N)
    d_rain = np.array([-1.5, -0.8], dtype=np.float64)
    d_etp = np.array([0.6, 0.4], dtype=np.float64)
    d_pump = np.array([0.9, 1.2], dtype=np.float64)
    d_canal = np.array([-0.5, 0.3], dtype=np.float64)
    X["rain"][:, mem_slice] += d_rain[:, None].astype(np.float32)
    X["ETP"][:, mem_slice] += d_etp[:, None].astype(np.float32)
    X["pump_gw"][:, mem_slice] += d_pump[:, None].astype(np.float32)
    X["canal"][:, mem_slice] += d_canal[:, None].astype(np.float32)

    data = {"codes": codes, "weeks": weeks.to_numpy(), "X": X}
    X_ref = F.reference_inputs(X, weeks, K, train_win)

    # Exact hand-computed attributed effects (h_orig - h_removed) since sum_j k(j) == 1:
    hand_eff = {
        "recharge": gain[:, 0] * (d_rain - f * d_etp),
        "pumping": gain[:, 1] * d_pump,
        "canal": gain[:, 2] * d_canal,
    }
    total_hand = hand_eff["recharge"] + hand_eff["pumping"] + hand_eff["canal"]

    # Check mode="remove" (counterfactual head shift = h_removed - h_orig = -hand_eff).
    rem = {}
    for stress in ("recharge", "pumping", "canal"):
        delta = F.intervene_model(net, data, (stress,), target, X_ref=X_ref)
        rem[stress] = delta
        np.testing.assert_allclose(-delta.to_numpy(), hand_eff[stress], atol=1e-5)

    # Check mode="keep_only": removing all OTHER stresses shifts head by -(total - hand_eff[s]).
    for stress in ("recharge", "pumping", "canal"):
        others = tuple(s for s in net.names if s != stress)
        delta_keep = F.intervene_model(net, data, others, target, X_ref=X_ref)
        np.testing.assert_allclose(-delta_keep.to_numpy(), total_hand - hand_eff[stress], atol=1e-5)

    # Check exact superposition: sum of single-group removals == all-group removal (<= 1e-6 m).
    delta_all = F.intervene_model(net, data, net.names, target, X_ref=X_ref)
    sup_err = float(np.max(np.abs((rem["recharge"] + rem["pumping"] + rem["canal"] - delta_all).to_numpy())))
    assert sup_err <= F.SUPERPOSITION_TOL_M, sup_err

    # Check single-week impulse at known lag inside target window (tests exact kernel weight).
    X_imp = _periodic_inputs(weeks, K, N=N)
    # Impulse at week t0 + 2 (padded index t0 + 2 + K - 1) of size +2.0 on pump_gw.
    p_imp = t0 + 2 + K - 1
    X_imp["pump_gw"][:, p_imp] += np.float32(2.0)
    data_imp = {"codes": codes, "weeks": weeks.to_numpy(), "X": X_imp}
    X_ref_imp = F.reference_inputs(X_imp, weeks, K, train_win)
    delta_imp = F.intervene_model(net, data_imp, ("pumping",), target, X_ref=X_ref_imp)
    # In target weeks t in [t0, t1], the impulse at t0 + 2 affects weeks t = t0 + 2 .. min(t1, t0 + 2 + K - 1)
    # with lags j = t - (t0 + 2) in 0 .. min(K - 1, t1 - (t0 + 2)).
    max_lag = min(K - 1, t1 - (t0 + 2))
    expected_imp_eff = gain[:, 1] * 2.0 * kernels[:, 1, : max_lag + 1].sum(axis=1) / len(t_idx)
    np.testing.assert_allclose(-delta_imp.to_numpy(), expected_imp_eff, atol=1e-5)

    # Check residual refusal and invariance of driver interventions to residual coefficients.
    try:
        F.resolve_group_stresses("residual", net.names)
        raise AssertionError("residual should be refused for intervention")
    except ValueError as err:
        assert "residual" in str(err)

    with torch.no_grad():
        net.res_coef.mul_(5.0)
    delta_after_res = F.intervene_model(net, data, ("recharge",), target, X_ref=X_ref)
    np.testing.assert_allclose(delta_after_res.to_numpy(), rem["recharge"].to_numpy(), atol=1e-7)

    # Check gate3 river_c/river split and pe/drainc recharge modes.
    g_net = _build_known_network(N=N, T=T, K=K, pumping=R.GATE3_STRESSES, signs="gate3", recharge="pe", weeks=weeks)
    X_g = _periodic_inputs(weeks, K, N=N)
    X_g["PE"][:, mem_slice] += np.float32(-1.0)
    X_g["river"][:, mem_slice] += np.float32(0.7)
    g_data = R.split_river({"codes": codes, "weeks": weeks.to_numpy(), "X": X_g}, {"W0"})
    X_g_ref = F.reference_inputs(g_data["X"], weeks, K, train_win)
    # Intervening on "river" must resolve to ("river_c", "river") and move BOTH W0 (constrained) and W1 (free).
    riv_stresses = F.resolve_group_stresses("river", g_net.names)
    assert set(riv_stresses) == {"river_c", "river"}
    d_riv = F.intervene_model(g_net, g_data, riv_stresses, target, X_ref=X_g_ref)
    with torch.no_grad():
        g_gain = g_net.parameters_physical()[0].numpy().astype(np.float64)
    np.testing.assert_allclose(-d_riv.loc["W0"], g_gain[0, 3] * 0.7, atol=1e-5)
    np.testing.assert_allclose(-d_riv.loc["W1"], g_gain[1, 4] * 0.7, atol=1e-5)
    # Under recharge="pe", intervening on recharge uses PE (not rain/ETP).
    assert R.stress_inputs("recharge", "pe") == ("PE",)
    assert R.stress_inputs("recharge", "drainc") == ("DRAINC",)
    d_pe = F.intervene_model(g_net, g_data, ("recharge",), target, X_ref=X_g_ref)
    np.testing.assert_allclose(-d_pe.to_numpy(), g_gain[:, 0] * (-1.0), atol=1e-5)

    print(
        f"  1. synthetic known-kernel checks (sustained, impulse, keep_only, residual, gate3 river_c/river, "
        f"pe/drainc): hand formulas exact within 1e-5 m; superposition max err = {sup_err:.2e} m"
    )


def test_synthetic_end_to_end_fidelity():
    """Disk-backed synthetic run verifying full fidelity() pipeline (stated vs intervened, fidelity+/−)."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        ds_dir = root / "dataset_syn"
        ds_dir.mkdir()
        run_dir = root / "run_syn"
        run_dir.mkdir()

        K = 12
        weeks = pd.date_range("2020-01-05", "2023-12-31", freq="W-SUN")
        T, N = len(weeks), 2
        codes = ["W0", "W1"]
        target = ("2023-06-01", "2023-09-30")
        t_idx = np.where((weeks >= target[0]) & (weeks <= target[1]))[0]
        mem_slice = slice(int(t_idx[0]), int(t_idx[-1]) + K)

        # Minimal dataset tables required by T46 decompose() data-quality flags.
        pd.DataFrame([{"code_bss": c, "core": True, "group": "g"} for c in codes]).to_parquet(
            ds_dir / "wells.parquet", index=False
        )
        head_rows = [
            {"code_bss": c, "week": wk, "head": 10.0, "share_not_validated": 0.0}
            for c in codes for wk in weeks
        ]
        pd.DataFrame(head_rows).to_parquet(ds_dir / "heads_weekly.parquet", index=False)
        (ds_dir / "splits.json").write_text(
            json.dumps({"week_rule": "W-SUN", "train": ["2020-01-01", "2021-12-31"]}), encoding="utf-8"
        )

        # Strictly periodic training + known 2023 anomalies.
        X = _periodic_inputs(weeks, K, N=N)
        X["rain"][:, mem_slice] += np.array([[-2.0], [-0.4]], dtype=np.float32)
        X["pump_gw"][:, mem_slice] += np.array([[0.3], [1.8]], dtype=np.float32)
        X["canal"][:, mem_slice] += np.array([[0.1], [-0.2]], dtype=np.float32)

        data = {
            "codes": codes,
            "weeks": weeks.to_numpy(),
            "X": X,
            "head": np.full((N, T), 10.0),
            "mu": np.full((N, T), 10.0),
            "sd": np.ones((N, T)),
            "split": np.where(weeks <= "2021-12-31", "train", "test")[None, :].repeat(N, 0),
            "core": np.ones((N, T), dtype=bool),
            "groups": ["g0", "g1"],
            "group_of": np.array([0, 1]),
        }
        net = _build_known_network(N=N, T=T, K=K, residual="seasonal", weeks=weeks)
        args = R.build_parser().parse_args(
            ["--mode", "free", "--kernel-weeks", str(K), "--amax", "20.0", "--residual", "seasonal", "--seeds", "0"]
        )
        R._canonicalize_args(args)
        fp = write_config(run_dir, args, ["rain/10", "ETP/10", "PE/10", "pump_gw/100", "canal/10"])
        pz, contrib, params = R.seed_outputs(net, data)
        contrib.to_parquet(run_dir / "contrib_seed_0.parquet", index=False)
        params.to_csv(run_dir / "params_seed_0.csv", index=False)
        save_seed_model(run_dir, 0, net.state_dict(), 0.0, 0, fp)
        save_seed(run_dir / "seed_0.parquet", pz, codes, data["weeks"], 0.0, 0, fp)

        fake_prep = {
            "data": data,
            "Z0": None,
            "static_control": None,
            "names": net.names,
            "signs": "structure",
            "gain_units": "m",
            "model_kwargs": {
                "group_of": data["group_of"],
                "n_groups": 2,
                "mode": "free",
                "kernel_weeks": K,
                "amax": 20.0,
                "recharge": "linear",
                "pumping": "sum",
                "gain_scale": None,
                "signs": "structure",
                "conv": "direct",
                "static_net": "linear",
                "sign_ref": "structure",
                "soft_stresses": None,
                "residual": "seasonal",
                "residual_basis": net.res_basis.numpy(),
                "residual_bound": net.res_bound.numpy(),
            },
        }
        with patch.object(R, "prepare", return_value=fake_prep), patch(
            "src.explain.contributions._pumping_edges_for_config",
            return_value=pd.DataFrame(columns=["relation", "src", "dst", "weight"]),
        ):
            res = F.fidelity(
                run_dir,
                target=target,
                dataset_dir=ds_dir,
                train_window=("2020-01-01", "2021-12-31"),
            )
            res_ts = F.fidelity(
                run_dir,
                target=target,
                reference="training_seasonal",
                dataset_dir=ds_dir,
                train_window=("2020-01-01", "2021-12-31"),
            )

        assert res["reference"]["kind"] == "average_forcing"
        assert res["superposition"]["passed"] and res["superposition"]["max_abs_err_m"] <= F.SUPERPOSITION_TOL_M
        bw = res["by_well"].set_index("code_bss")
        for code in codes:
            row = bw.loc[code]
            assert np.isclose(row["fidelity_plus_m"], abs(row["top_intervened_m"]), atol=1e-6)
            assert np.isclose(
                row["fidelity_minus_m"],
                abs(row["total_intervened_m"] - row["top_intervened_m"]),
                atol=1e-6,
            )

        # Under default average_forcing, stated - intervened <= 1e-6 m for every intervenable report group,
        # while residual stays untouched (intervened_m is NaN).
        rg = res["by_report_group"]
        rg_interv = rg[rg["report_group"] != "residual"]
        max_gap_af = float(rg_interv["abs_diff_m"].max())
        assert max_gap_af <= F.FAITHFULNESS_TOL_M, max_gap_af
        rg_res = rg[rg["report_group"] == "residual"]
        assert len(rg_res) == len(codes) and rg_res["intervened_m"].isna().all()

        # Second table (training_seasonal sensitivity) matches explicit reference="training_seasonal".
        assert res["sensitivity_training_seasonal"] is not None
        assert res_ts["sensitivity_training_seasonal"] is None
        np.testing.assert_allclose(
            res["sensitivity_training_seasonal"]["by_report_group"]["diff_m"].dropna().to_numpy(),
            res_ts["by_report_group"]["diff_m"].dropna().to_numpy(),
            atol=1e-12,
        )
        print(
            f"  2. end-to-end synthetic fidelity() (default average_forcing + seasonal residual): "
            f"superposition max err = {res['superposition']['max_abs_err_m']:.2e} m, "
            f"max |stated - intervened| = {max_gap_af:.2e} m (<= {F.FAITHFULNESS_TOL_M:.1e} m)"
        )


def test_real_run_resp_pooled_l001():
    """Fidelity tables for summer 2024 on resp_pooled_l001 for two core wells (all 10 seeds)."""
    run = "resp_pooled_l001"
    target = "2024-06-01:2024-09-30"
    res = F.fidelity(run, target=target, wells=CORE_SAMPLE, seeds="all", dataset="v4")

    assert res["reference"]["kind"] == "average_forcing"
    assert res["n_seeds"] == 10
    assert res["superposition"]["passed"], res["superposition"]
    assert res["superposition"]["max_abs_err_m"] <= F.SUPERPOSITION_TOL_M

    # Under default average_forcing, stated - intervened <= 1e-6 m for every group on this linear model.
    max_gap_af = float(res["by_report_group"]["abs_diff_m"].max())
    assert max_gap_af <= F.FAITHFULNESS_TOL_M, (
        f"Expected |stated - intervened| <= {F.FAITHFULNESS_TOL_M:.1e} m under average_forcing, "
        f"got {max_gap_af:.3e} m\n{res['by_report_group']}"
    )

    # Sensitivity table (training_seasonal, output space) preserves the documented warm-up gap on NYLS-1 recharge.
    sens = res["sensitivity_training_seasonal"]
    assert sens is not None and sens["reference"]["kind"] == "training_seasonal"
    ts_idx = sens["by_report_group"].set_index(["code_bss", "report_group"])
    nyls_rch_diff = float(ts_idx.loc[("10964X0119/NYLS-1", "recharge"), "diff_m"])
    assert nyls_rch_diff < -0.15, nyls_rch_diff  # stated (-2.288) - intervened (-2.127) ≈ -0.161 m

    bw = res["by_well"].set_index("code_bss")
    for code in CORE_SAMPLE:
        row = bw.loc[code]
        assert np.isclose(row["fidelity_plus_m"], abs(row["top_intervened_m"]), atol=1e-6)
        assert np.isclose(
            row["fidelity_minus_m"],
            abs(row["total_intervened_m"] - row["top_intervened_m"]),
            atol=1e-6,
        )
        assert np.isclose(row["total_diff_m"], 0.0, atol=F.FAITHFULNESS_TOL_M)
        assert np.sign(row["top_stated_m"]) == np.sign(row["top_intervened_m"])

    # Also test CLI entry point (prints default average_forcing + training_seasonal sensitivity tables).
    buf = StringIO()
    with redirect_stdout(buf):
        rc = F.main([run, "--target", target, "--well", *CORE_SAMPLE, "--dataset", "v4"])
    assert rc == 0
    cli_out = buf.getvalue()
    assert "Reference: average_forcing" in cli_out
    assert "Sensitivity — Stated (training_seasonal" in cli_out
    for code in CORE_SAMPLE:
        assert code in cli_out

    max_gap_ts = float(sens["by_report_group"]["abs_diff_m"].max())
    print(
        f"  3. real run {run} (summer 2024, 2 core wells, 10 seeds): "
        f"superposition max err = {res['superposition']['max_abs_err_m']:.2e} m, "
        f"average_forcing max |stated - intervened| = {max_gap_af:.2e} m (<= 1e-6 m), "
        f"training_seasonal max |stated - intervened| = {max_gap_ts:.4f} m"
    )
    print("\n--- Summer 2024 faithfulness tables (resp_pooled_l001, 2 core wells) ---")
    print(cli_out.rstrip())


def main():
    started = time.perf_counter()
    test_synthetic_hand_calculations_and_superposition()
    test_synthetic_end_to_end_fidelity()
    test_real_run_resp_pooled_l001()
    print(f"\ntest_faithfulness: all checks passed ({time.perf_counter() - started:.1f}s)")


if __name__ == "__main__":
    main()
