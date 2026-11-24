"""Checks of the explanation contribution numbers (src/explain/contributions.py).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_explain_contributions

1. Synthetic average_forcing (default, input space) hand-checkable runs with real ResponseModel
   checkpoints (no training):
   - constant inputs equal to their reference -> every anomaly is exact 0;
   - one-week input shift on pumping -> moves only pumping by exact gain * delta * kernel[lag]
     (single-week and multi-week targets), all other stresses stay exact 0;
   - replayed reference contributions are cached in memory (second call triggers zero replays);
   - routed Phase 4 run with gate3 (river_c/river merged) and bounded seasonal residual: verifies
     residual anomaly equals residual minus its own training ISO-week seasonal mean.
2. Synthetic 3-seed, 2-well, 3-year run in a temporary directory: verifies hand-calculated
   training-seasonal anomalies (including ISO week 53 merged into week 52), explicit reference
   window changes, sample sds, sign agreements (including 2/3 and zero-as-own-sign cases),
   report-group and driver-group sums, exact additivity, reconstruction check (pass and fail),
   data-quality flags (observed, strict, placeholder, volume-weighted pumping imputation), and
   loud failures on seed mismatches and unmapped stresses.
3. Synthetic routed run with all Phase 4 stress names (recharge, pumping, pumping_unattributed,
   canal, river, residual): verifies SummerDemand aggregation, ungrouped residual accounting,
   reconstruction, and echoed Phase 4 metadata/protocol.
4. Real run results/v4/resp_pooled_l001: verifies reconstruction (<= 1e-4 m on all 63 non-constant
   wells including all 33 core wells, and <= 1e-4 m across all 64 wells against SD_FLOOR-decoded
   seed files, while confirming the known pre-f2cd482 predictions.parquet discrepancy on the
   constant-head non-core well 10984X0003/AIGUAN), times a full 64-well x 10-start default
   average_forcing decomposition (cold and warm cache), checks exact per-seed additivity, checks
   data-quality flags, and prints average_forcing vs training_seasonal side by side for two core
   wells.
"""
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

from src.config import DATASET
from src.explain import contributions as C
from src.models import response as R
from src.models.lstm import save_seed, save_seed_model, write_config

CONSTANT_WELL = "10984X0003/AIGUAN"
CORE_SAMPLE = ("10964X0119/NYLS-1", "10906X0039/C2-1")


def _write_synthetic_dataset(ds_dir: Path, weeks: pd.DatetimeIndex) -> tuple[dict[str, float], pd.DataFrame]:
    """Create a tiny self-contained dataset folder for isolated unit tests."""
    ds_dir.mkdir(parents=True, exist_ok=True)
    wells_df = pd.DataFrame(
        [
            {"code_bss": "W1", "core": True, "group": "Pliocene multilayer", "libelle_pe": "WELL 1"},
            {"code_bss": "W2", "core": False, "group": "recent alluvium", "libelle_pe": "WELL 2"},
        ]
    )
    wells_df.to_parquet(ds_dir / "wells.parquet", index=False)

    # Training heads (year 2020): W1 mean = 10.0, W2 mean = 20.0.
    # In summer 2022 (2022-06-01..2022-09-30, 17 W-SUN weeks):
    # - W1: 15 observed weeks (2 missing), 12 strictly validated, 1 unqualified, 2 placeholders.
    # - W2: all 17 observed and strictly validated, 0 placeholders.
    train_weeks = weeks[(weeks >= "2020-01-01") & (weeks <= "2020-12-31")]
    summer22 = weeks[(weeks >= "2022-06-01") & (weeks <= "2022-09-30")]
    assert len(summer22) == 17

    head_rows = []
    # Training year: symmetric around 10.0 and 20.0 so exact means are 10.0 and 20.0.
    offsets = np.linspace(-1.0, 1.0, len(train_weeks))
    for wk, off in zip(train_weeks, offsets):
        head_rows.append({"code_bss": "W1", "week": wk, "head": 10.0 + off, "share_not_validated": 0.0})
        head_rows.append({"code_bss": "W2", "week": wk, "head": 20.0 + 2.0 * off, "share_not_validated": 0.0})

    for i, wk in enumerate(summer22):
        if i < 15:  # W1 misses the last 2 weeks of summer 2022
            snv = 0.5 if i == 12 else 0.0
            head_rows.append({"code_bss": "W1", "week": wk, "head": 9.5, "share_not_validated": snv})
        head_rows.append({"code_bss": "W2", "week": wk, "head": 19.5, "share_not_validated": 0.0})
    pd.DataFrame(head_rows).to_parquet(ds_dir / "heads_weekly.parquet", index=False)

    # W1 has 2 placeholder weeks inside summer 2022 (weeks 13 and 14, which had share_not_validated=0).
    ph_df = pd.DataFrame([{"code_bss": "W1", "week": summer22[13]}, {"code_bss": "W1", "week": summer22[14]}])
    ph_df.to_parquet(ds_dir / "placeholder_weeks.parquet", index=False)

    # Pumping: F1 (declared) = 100 m3/wk, F2 (imputed) = 50 m3/wk; W1 has edges weight 1.0 to F1 and 2.0 to F2
    # -> per week: routed total = 1*100 + 2*50 = 200, imputed = 2*50 = 100 -> share_pumping_imputed = 0.5.
    # W2 has no pumping edges -> routed = 0, share_pumping_imputed = NaN.
    pump_rows = []
    for wk in summer22:
        pump_rows.append({"code_ouvrage": "F1", "usage": "irrigation", "week": wk, "volume_m3": 100.0, "imputed": False})
        pump_rows.append({"code_ouvrage": "F2", "usage": "irrigation", "week": wk, "volume_m3": 50.0, "imputed": True})
    pd.DataFrame(pump_rows).to_parquet(ds_dir / "pumping_weekly.parquet", index=False)

    splits = {"week_rule": "W-SUN", "train": ["2020-01-01", "2020-12-31"]}
    (ds_dir / "splits.json").write_text(json.dumps(splits), encoding="utf-8")

    edges = pd.DataFrame(
        [
            {"relation": "pumping", "src_type": "facility", "src": "F1", "dst": "W1", "weight": 1.0},
            {"relation": "pumping_unattributed", "src_type": "facility", "src": "F2", "dst": "W1", "weight": 2.0},
        ]
    )
    return {"W1": 10.0, "W2": 20.0}, edges


def _save_synthetic_model_run(
    run_dir: Path,
    net: R.ResponseModel,
    data: dict,
    cli_args: list[str],
    inputs_schema: list[str],
    *,
    seeds: tuple[int, ...] = (0,),
    extra_cfg: dict | None = None,
) -> dict:
    """Write config.json, seed_<k>.pt, contrib_seed_<k>.parquet, params_seed_<k>.csv for a synthetic net."""
    run_dir.mkdir(parents=True, exist_ok=True)
    args = R.build_parser().parse_args(cli_args)
    R._canonicalize_args(args)
    fp = write_config(run_dir, args, inputs_schema, extra=extra_cfg)
    pz, contrib, params = R.seed_outputs(net, data)
    for s in seeds:
        contrib.to_parquet(run_dir / f"contrib_seed_{s}.parquet", index=False)
        params.to_csv(run_dir / f"params_seed_{s}.csv", index=False)
        save_seed_model(run_dir, s, net.state_dict(), 0.0, 0, fp)
        save_seed(run_dir / f"seed_{s}.parquet", pz, data["codes"], data["weeks"], 0.0, 0, fp)
    return {
        "data": data,
        "Z0": None,
        "static_control": None,
        "names": net.names,
        "signs": "gate3" if "--signs" in cli_args and "gate3" in cli_args else "structure",
        "gain_units": "m",
        "model_kwargs": {
            "group_of": data["group_of"],
            "n_groups": len(data["groups"]),
            "mode": net.mode,
            "kernel_weeks": net.K,
            "amax": net.amax,
            "recharge": net.recharge,
            "pumping": R.GATE3_STRESSES if "river_c" in net.names else "sum",
            "gain_scale": None,
            "signs": "gate3" if "river_c" in net.names else "structure",
            "conv": net.conv,
            "static_net": "linear",
            "sign_ref": "gate3" if "river_c" in net.names else "structure",
            "soft_stresses": None,
            "residual": net.residual_kind,
            "residual_basis": None if net.res_coef is None else net.res_basis.numpy(),
            "residual_bound": None if net.res_coef is None else net.res_bound.numpy(),
        },
    }


def test_synthetic_average_forcing():
    """Test 0: default average_forcing reference — exact 0 on constant inputs, exact gain*kernel on 1-week shift,
    cache reuse, and gate3 + seasonal residual handling."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        ds_dir = root / "dataset_af"
        weeks = pd.date_range("2020-01-05", "2022-12-31", freq="W-SUN")
        T, N, K = len(weeks), 2, 12
        codes = ["W1", "W2"]
        _, edges = _write_synthetic_dataset(ds_dir, weeks)
        train_win = ("2020-01-01", "2020-12-31")
        target_win = ("2022-06-01", "2022-09-30")
        t_idx = np.where((weeks >= target_win[0]) & (weeks <= target_win[1]))[0]

        gen = torch.Generator().manual_seed(11)
        net = R.ResponseModel(
            group_of=np.array([0, 1]),
            n_groups=2,
            mode="free",
            kernel_weeks=K,
            amax=20.0,
            recharge="linear",
            init_sd=0.6,
            generator=gen,
        )
        with torch.no_grad():
            net.d.copy_(torch.tensor([0.2, -0.3]))
            gain, a, n, _ = (t.numpy().astype(np.float64) for t in net.parameters_physical())
            kernels = net.kernels(
                torch.from_numpy(a.astype(np.float32)), torch.from_numpy(n.astype(np.float32))
            ).numpy().astype(np.float64)
        net.eval()

        # 0a. Constant inputs equal to their reference over the whole record -> anomalies are EXACTLY 0.
        L = T + K - 1
        X_const = {
            "rain": np.full((N, L), 1.5, dtype=np.float32),
            "ETP": np.full((N, L), 0.8, dtype=np.float32),
            "PE": np.full((N, L), 0.7, dtype=np.float32),
            "pump_gw": np.full((N, L), 2.0, dtype=np.float32),
            "canal": np.full((N, L), 0.4, dtype=np.float32),
        }
        data_const = {
            "codes": codes,
            "weeks": weeks.to_numpy(),
            "X": X_const,
            "head": np.full((N, T), 10.0),
            "mu": np.full((N, T), 10.0),
            "sd": np.ones((N, T)),
            "split": np.where(weeks <= "2020-12-31", "train", "test")[None, :].repeat(N, 0),
            "core": np.ones((N, T), dtype=bool),
            "groups": ["g0", "g1"],
            "group_of": np.array([0, 1]),
        }
        run_const = root / "run_const"
        prep_const = _save_synthetic_model_run(
            run_const,
            net,
            data_const,
            ["--mode", "free", "--kernel-weeks", str(K), "--amax", "20.0", "--seeds", "0"],
            ["rain/10", "ETP/10", "PE/10", "pump_gw/100", "canal/10"],
        )
        C.clear_reference_cache()
        with patch.object(R, "prepare", return_value=prep_const):
            res_const = C.decompose(
                run_const,
                target=target_win,
                dataset_dir=ds_dir,
                train_window=train_win,
                edges=edges,
            )
        assert res_const["reference"]["kind"] == "average_forcing"
        assert res_const["reference"]["space"] == "input"
        assert np.allclose(res_const["by_stress"]["mean_m"].to_numpy(), 0.0, atol=1e-7)
        assert np.allclose(res_const["by_report_group"]["mean_m"].to_numpy(), 0.0, atol=1e-7)
        assert np.allclose(res_const["total"]["mean_m"].to_numpy(), 0.0, atol=1e-7)

        # 0b. One-week input shift on pump_gw at week t_imp -> moves ONLY pumping by exact gain * delta * kernel[lag].
        X_shift = {k: v.copy() for k, v in X_const.items()}
        t_imp = int(t_idx[0]) + 1
        delta_u = 3.0
        X_shift["pump_gw"][:, t_imp + K - 1] += np.float32(delta_u)
        data_shift = dict(data_const, X=X_shift)
        run_shift = root / "run_shift"
        prep_shift = _save_synthetic_model_run(
            run_shift,
            net,
            data_shift,
            ["--mode", "free", "--kernel-weeks", str(K), "--amax", "20.0", "--seeds", "0"],
            ["rain/10", "ETP/10", "PE/10", "pump_gw/100", "canal/10"],
        )
        # Single-week target at lag j = 3 after the impulse -> exact gain * delta_u * kernel[3].
        lag_j = 3
        single_wk = str(weeks[t_imp + lag_j].date())
        with patch.object(R, "prepare", return_value=prep_shift), patch.object(
            R, "replay", wraps=R.replay
        ) as spy_replay:
            res_single = C.decompose(
                run_shift,
                target=(single_wk, single_wk),
                dataset_dir=ds_dir,
                train_window=train_win,
                edges=edges,
            )
            assert spy_replay.call_count == 1
            # Second call on the same run (different target window) must reuse cached reference contributions!
            res_multi = C.decompose(
                run_shift,
                target=target_win,
                dataset_dir=ds_dir,
                train_window=train_win,
                edges=edges,
            )
            assert spy_replay.call_count == 1

        s_single = res_single["by_stress"].set_index(["code_bss", "stress"])["mean_m"]
        for wi, code in enumerate(codes):
            expected_single = gain[wi, 1] * delta_u * kernels[wi, 1, lag_j]
            assert np.isclose(s_single.loc[(code, "pumping")], expected_single, atol=1e-6)
            assert np.isclose(s_single.loc[(code, "recharge")], 0.0, atol=1e-7)
            assert np.isclose(s_single.loc[(code, "canal")], 0.0, atol=1e-7)

        max_lag = min(K - 1, int(t_idx[-1]) - t_imp)
        s_multi = res_multi["by_stress"].set_index(["code_bss", "stress"])["mean_m"]
        for wi, code in enumerate(codes):
            expected_multi = gain[wi, 1] * delta_u * kernels[wi, 1, : max_lag + 1].sum() / len(t_idx)
            assert np.isclose(s_multi.loc[(code, "pumping")], expected_multi, atol=1e-6)
            assert np.isclose(s_multi.loc[(code, "recharge")], 0.0, atol=1e-7)
            assert np.isclose(s_multi.loc[(code, "canal")], 0.0, atol=1e-7)

        # 0c. Gate3 (river_c + river merged) + seasonal residual under default average_forcing:
        #     driver stresses use input-space reference; residual uses its own training seasonal mean.
        res_basis = R.seasonal_basis(weeks)
        res_bound = np.full(N, 0.25, dtype=np.float32)
        g_net = R.ResponseModel(
            group_of=np.array([0, 1]),
            n_groups=2,
            mode="free",
            kernel_weeks=K,
            amax=20.0,
            recharge="linear",
            init_sd=0.5,
            generator=torch.Generator().manual_seed(19),
            pumping=R.GATE3_STRESSES,
            signs="gate3",
            residual="seasonal",
            residual_basis=res_basis,
            residual_bound=res_bound,
        )
        with torch.no_grad():
            g_net.res_coef.copy_(torch.tensor([[0.4, -0.2, 0.1, 0.3], [-0.3, 0.5, -0.2, 0.1]]))
            g_gain, g_a, g_n, _ = (t.numpy().astype(np.float64) for t in g_net.parameters_physical())
            g_kernels = g_net.kernels(
                torch.from_numpy(g_a.astype(np.float32)), torch.from_numpy(g_n.astype(np.float32))
            ).numpy().astype(np.float64)
        g_net.eval()

        X_g = {
            "rain": np.full((N, L), 1.0, dtype=np.float32),
            "ETP": np.full((N, L), 0.5, dtype=np.float32),
            "PE": np.full((N, L), 0.5, dtype=np.float32),
            "pump_gw": np.full((N, L), 1.0, dtype=np.float32),
            "pump_un": np.full((N, L), 0.4, dtype=np.float32),
            "canal": np.full((N, L), 0.2, dtype=np.float32),
            "river": np.full((N, L), 2.0, dtype=np.float32),
        }
        # One-week shift on river at t_imp: moves W1 via river_c (slot 3) and W2 via river (slot 4).
        X_g["river"][:, t_imp + K - 1] += np.float32(1.5)
        g_data = R.split_river(dict(data_const, X=X_g), {"W1"})
        run_g3 = root / "run_g3_res"
        prep_g3 = _save_synthetic_model_run(
            run_g3,
            g_net,
            g_data,
            [
                "--mode", "free", "--kernel-weeks", str(K), "--amax", "20.0",
                "--arm", "D", "--signs", "gate3", "--residual", "seasonal", "--seeds", "0",
            ],
            ["rain/10", "ETP/10", "PE/10", "pump_gw/100", "pump_un/100", "canal/10", "river/10"],
        )
        with patch.object(R, "prepare", return_value=prep_g3):
            res_g3 = C.decompose(
                run_g3,
                target=(single_wk, single_wk),
                dataset_dir=ds_dir,
                train_window=train_win,
                edges=edges,
            )
            res_g3_ts = C.decompose(
                run_g3,
                target=(single_wk, single_wk),
                reference="training_seasonal",
                dataset_dir=ds_dir,
                train_window=train_win,
                edges=edges,
            )
        sg = res_g3["by_stress"].set_index(["code_bss", "stress"])["mean_m"]
        sg_ts = res_g3_ts["by_stress"].set_index(["code_bss", "stress"])["mean_m"]
        # W1 uses river_c (slot 3), W2 uses river (slot 4).
        assert np.isclose(sg.loc[("W1", "river")], g_gain[0, 3] * 1.5 * g_kernels[0, 3, lag_j], atol=1e-6)
        assert np.isclose(sg.loc[("W2", "river")], g_gain[1, 4] * 1.5 * g_kernels[1, 4, lag_j], atol=1e-6)
        for s in ("recharge", "pumping", "pumping_unattributed", "canal"):
            assert np.isclose(sg.loc[("W1", s)], 0.0, atol=1e-7)
            assert np.isclose(sg.loc[("W2", s)], 0.0, atol=1e-7)
        # Residual anomaly under average_forcing equals residual anomaly under training_seasonal identically.
        assert np.isclose(sg.loc[("W1", "residual")], sg_ts.loc[("W1", "residual")], atol=1e-12)
        assert np.isclose(sg.loc[("W2", "residual")], sg_ts.loc[("W2", "residual")], atol=1e-12)

    print(
        "  0. synthetic average_forcing (default): constant inputs -> exact 0, 1-week shift -> exact "
        "gain*kernel on shifted stress only, replay cache hit verified, gate3 river_c/river & residual pass"
    )


def test_synthetic_ladder():
    """Test 1: hand-constructed 3-seed, 2-well, 3-year run with ISO week 53 and known answers."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        ds_dir = root / "dataset_syn"
        run_dir = root / "run_syn"
        run_dir.mkdir()

        # 3 years of W-SUN dates: 2020-01-05 .. 2022-12-25.
        # 2021-01-03 has ISO calendar (2020, 53, 7) -> tests ISO week 53 merging into week 52!
        weeks = pd.date_range("2020-01-01", "2022-12-31", freq="W-SUN")
        iso_weeks = pd.DatetimeIndex(weeks).isocalendar().week.to_numpy()
        w53_mask = iso_weeks == 53
        assert w53_mask.sum() == 1 and weeks[w53_mask][0] == pd.Timestamp("2021-01-03")
        mu_map, edges = _write_synthetic_dataset(ds_dir, weeks)

        woy = np.minimum(iso_weeks, 52)
        seasonal_base = 0.01 * woy  # known deterministic seasonal cycle per ISO week (1..52)

        # Year-specific shifts added on top of seasonal_base (year 2020 shift = 0 -> training ref = seasonal_base).
        # W1 in year 2021: recharge = +0.50 (all seeds), pumping = [-0.20, -0.30, +0.10] (mean -0.1333, sign agr 2/3),
        #                  canal = [0.0, 0.0, 0.0] (mean 0.0, sign agr 1.0).
        # W1 in year 2022: recharge = [-1.0, -0.4, +0.2] (mean -0.4, sign agr 2/3),
        #                  pumping = [-0.6, -0.3, 0.0] (mean -0.3, 0 counts as own sign -> sign agr 2/3!),
        #                  canal = [+0.1, +0.1, +0.1] (mean +0.1, sign agr 1.0).
        # W2 in year 2021: recharge = +0.2, pumping = -0.1, canal = +0.05 (all seeds).
        # W2 in year 2022: recharge = -0.3, pumping = -0.2, canal = +0.15 (all seeds).
        shifts = {
            ("W1", 2021): {"recharge": [0.5, 0.5, 0.5], "pumping": [-0.2, -0.3, 0.1], "canal": [0.0, 0.0, 0.0]},
            ("W1", 2022): {"recharge": [-1.0, -0.4, 0.2], "pumping": [-0.6, -0.3, 0.0], "canal": [0.1, 0.1, 0.1]},
            ("W2", 2021): {"recharge": [0.2, 0.2, 0.2], "pumping": [-0.1, -0.1, -0.1], "canal": [0.05, 0.05, 0.05]},
            ("W2", 2022): {"recharge": [-0.3, -0.3, -0.3], "pumping": [-0.2, -0.2, -0.2], "canal": [0.15, 0.15, 0.15]},
        }
        d_by_seed = {0: {"W1": 0.25, "W2": -0.50}, 1: {"W1": 0.35, "W2": -0.40}, 2: {"W1": 0.45, "W2": -0.30}}

        cfg = {
            "mode": "pooled",
            "lam": 0.01,
            "run": "run_syn",
            "seeds": [0, 1, 2],
            "fold": None,
            "train_start": None,
            "refit_from": None,
            "dataset": "syn",
        }
        (run_dir / "config.json").write_text(json.dumps(cfg), encoding="utf-8")

        pred_accum = []
        for seed in (0, 1, 2):
            rows = []
            for code in ("W1", "W2"):
                for wk, base in zip(weeks, seasonal_base):
                    yr = wk.year
                    sh = shifts.get((code, yr), {"recharge": [0, 0, 0], "pumping": [0, 0, 0], "canal": [0, 0, 0]})
                    r_val = float(np.float32(base + sh["recharge"][seed]))
                    p_val = float(np.float32(-0.5 * base + sh["pumping"][seed]))
                    c_val = float(np.float32(0.2 * base + sh["canal"][seed]))
                    rows.append({"code_bss": code, "week": wk, "recharge": r_val, "pumping": p_val, "canal": c_val})
            cdf = pd.DataFrame(rows)
            for s in ("recharge", "pumping", "canal"):
                cdf[s] = cdf[s].astype(np.float32)
            cdf.to_parquet(run_dir / f"contrib_seed_{seed}.parquet", index=False)

            pdf = pd.DataFrame([{"code_bss": c, "group": "g", "d_m": d_by_seed[seed][c]} for c in ("W1", "W2")])
            pdf.to_csv(run_dir / f"params_seed_{seed}.csv", index=False)

            anom = cdf[["recharge", "pumping", "canal"]].astype(float).sum(axis=1) + cdf["code_bss"].map(d_by_seed[seed])
            pred_accum.append(pd.DataFrame({"code_bss": cdf["code_bss"], "week": cdf["week"], "anom": anom}))

        mean_anom = pd.concat(pred_accum).groupby(["code_bss", "week"])["anom"].mean().reset_index()
        mean_anom["pred"] = mean_anom["code_bss"].map(mu_map) + mean_anom["anom"]
        mean_anom["task"] = "simulation"
        mean_anom["horizon"] = 0
        mean_anom[["code_bss", "week", "pred", "task", "horizon"]].to_parquet(
            run_dir / "predictions.parquet", index=False
        )

        # 1a. Reconstruction check passes, and fails loudly when perturbed.
        max_diff = C.reconstruct(run_dir, dataset_dir=ds_dir, train_window=("2020-01-01", "2020-12-31"))
        assert max_diff <= 1e-6, max_diff
        pred_bad = pd.read_parquet(run_dir / "predictions.parquet")
        pred_bad.loc[0, "pred"] += 5e-4
        bad_dir = root / "run_bad_pred"
        bad_dir.mkdir()
        for f in run_dir.iterdir():
            if f.name != "predictions.parquet":
                (bad_dir / f.name).write_bytes(f.read_bytes())
        pred_bad.to_parquet(bad_dir / "predictions.parquet", index=False)
        try:
            C.reconstruct(bad_dir, dataset_dir=ds_dir, train_window=("2020-01-01", "2020-12-31"))
            raise AssertionError("Perturbed predictions.parquet should have failed reconstruct()")
        except ValueError as err:
            assert "exceeds" in str(err)

        # 1b. ISO week 53 test: target window = single week 2021-01-03 (ISO week 53 -> merged into 52).
        # Because seasonal_base(2021-01-03) == 0.01 * 52 == seasonal_base(2020-12-27), the training-seasonal
        # anomaly on 2021-01-03 equals the exact year-2021 shift!
        res53 = C.decompose(
            run_dir,
            target=("2021-01-03", "2021-01-03"),
            reference="training_seasonal",
            dataset_dir=ds_dir,
            train_window=("2020-01-01", "2020-12-31"),
            edges=edges,
        )
        assert res53["n_target_weeks"] == 1
        s53 = res53["by_stress"].set_index(["code_bss", "stress"])
        assert np.isclose(s53.loc[("W1", "recharge"), "mean_m"], 0.5, atol=1e-6)
        assert np.isclose(s53.loc[("W1", "pumping"), "mean_m"], -0.4 / 3.0, atol=1e-6)
        assert np.isclose(s53.loc[("W1", "pumping"), "sd_m"], np.std([-0.2, -0.3, 0.1], ddof=1), atol=1e-6)
        assert np.isclose(s53.loc[("W1", "pumping"), "sign_agreement"], 2.0 / 3.0)
        assert np.isclose(s53.loc[("W1", "canal"), "mean_m"], 0.0, atol=1e-6)
        assert np.isclose(s53.loc[("W1", "canal"), "sign_agreement"], 1.0)

        # 1c. Summer 2022 training_seasonal: verify means, sds, sign agreements (including 0 as own sign),
        #     report groups, driver groups, total, and data-quality flags.
        res22 = C.decompose(
            run_dir,
            target="2022-06-01:2022-09-30",
            reference="training_seasonal",
            dataset_dir=ds_dir,
            train_window=("2020-01-01", "2020-12-31"),
            edges=edges,
        )
        s22 = res22["by_stress"].set_index(["code_bss", "stress"])
        assert np.isclose(s22.loc[("W1", "recharge"), "mean_m"], -0.4, atol=1e-6)
        assert np.isclose(s22.loc[("W1", "recharge"), "sd_m"], np.std([-1.0, -0.4, 0.2], ddof=1), atol=1e-6)
        assert np.isclose(s22.loc[("W1", "recharge"), "sign_agreement"], 2.0 / 3.0)
        # W1 pumping seeds = [-0.6, -0.3, 0.0], mean = -0.3 -> 0 has sign 0 != -1 -> sign agreement = 2/3.
        assert np.isclose(s22.loc[("W1", "pumping"), "mean_m"], -0.3, atol=1e-6)
        assert np.isclose(s22.loc[("W1", "pumping"), "sign_agreement"], 2.0 / 3.0)
        # Driver group SummerDemand = pumping + canal = [-0.5, -0.2, +0.1], mean = -0.2, sign agr = 2/3.
        dg22 = res22["by_driver_group"].set_index(["code_bss", "driver_group"])
        assert np.isclose(dg22.loc[("W1", "lulcw:SummerDemand"), "mean_m"], -0.2, atol=1e-6)
        assert np.isclose(
            dg22.loc[("W1", "lulcw:SummerDemand"), "sd_m"],
            np.std([-0.5, -0.2, 0.1], ddof=1),
            atol=1e-6,
        )
        assert np.isclose(dg22.loc[("W1", "lulcw:SummerDemand"), "sign_agreement"], 2.0 / 3.0)
        # Total for W1: [-1.5, -0.6, +0.3], mean = -0.6, sign agr = 2/3.
        tot22 = res22["total"].set_index("code_bss")
        assert np.isclose(tot22.loc["W1", "mean_m"], -0.6, atol=1e-6)
        assert np.isclose(tot22.loc["W1", "sd_m"], np.std([-1.5, -0.6, 0.3], ddof=1), atol=1e-6)
        assert np.isclose(tot22.loc["W1", "sign_agreement"], 2.0 / 3.0)

        # Data-quality flags for summer 2022 (17 weeks):
        # W1: 15 observed, 12 strict (1 unqualified + 2 placeholders excluded), 2 placeholders, 0.5 imputed pumping.
        # W2: 17 observed, 17 strict, 0 placeholders, NaN imputed pumping (0 routed volume).
        fl = res22["flags"].set_index("code_bss")
        assert fl.loc["W1", "n_weeks"] == 17
        assert np.isclose(fl.loc["W1", "share_observed"], 15 / 17)
        assert np.isclose(fl.loc["W1", "share_strict"], 12 / 17)
        assert np.isclose(fl.loc["W1", "share_placeholder"], 2 / 17)
        assert np.isclose(fl.loc["W1", "share_pumping_imputed"], 0.5)
        assert np.isclose(fl.loc["W2", "share_observed"], 1.0)
        assert np.isclose(fl.loc["W2", "share_strict"], 1.0)
        assert np.isclose(fl.loc["W2", "share_placeholder"], 0.0)
        assert np.isnan(fl.loc["W2", "share_pumping_imputed"])

        # 1d. Explicit reference window: summer 2022 minus summer 2021.
        # Because both windows cover the same ISO weeks (or slightly shifted by calendar), compute exact base diff.
        w22_wks = weeks[(weeks >= "2022-06-01") & (weeks <= "2022-09-30")]
        w21_wks = weeks[(weeks >= "2021-06-01") & (weeks <= "2021-09-30")]
        base_diff = 0.01 * (
            np.mean(np.minimum(w22_wks.isocalendar().week.to_numpy(), 52))
            - np.mean(np.minimum(w21_wks.isocalendar().week.to_numpy(), 52))
        )
        res_win = C.decompose(
            run_dir,
            target=("2022-06-01", "2022-09-30"),
            reference=("2021-06-01", "2021-09-30"),
            dataset_dir=ds_dir,
            edges=edges,
        )
        sw = res_win["by_stress"].set_index(["code_bss", "stress"])
        # W1 recharge shift diff = [-1.5, -0.9, -0.3] -> mean = -0.9 (+ base_diff), sign agr = 1.0.
        assert np.isclose(sw.loc[("W1", "recharge"), "mean_m"], -0.9 + base_diff, atol=1e-6)
        assert np.isclose(sw.loc[("W1", "recharge"), "sign_agreement"], 1.0)
        # W1 pumping shift diff = [-0.4, 0.0, -0.1] -> mean = -0.5/3 (- 0.5*base_diff).
        expected_p_seeds = np.array([-0.4, 0.0, -0.1]) - 0.5 * base_diff
        assert np.isclose(sw.loc[("W1", "pumping"), "mean_m"], expected_p_seeds.mean(), atol=1e-6)
        assert np.isclose(sw.loc[("W1", "pumping"), "sd_m"], expected_p_seeds.std(ddof=1), atol=1e-6)

        # 1e. Seed mismatch fails loudly in load_run; unknown stress fails loudly in decompose.
        bad_seed_dir = root / "run_bad_seed"
        bad_seed_dir.mkdir()
        for f in run_dir.iterdir():
            (bad_seed_dir / f.name).write_bytes(f.read_bytes())
        c2 = pd.read_parquet(bad_seed_dir / "contrib_seed_2.parquet")
        c2[c2["code_bss"] == "W1"].to_parquet(bad_seed_dir / "contrib_seed_2.parquet", index=False)
        try:
            C.load_run(bad_seed_dir)
            raise AssertionError("Mismatched wells across seeds should fail load_run()")
        except ValueError as err:
            assert "wells differ" in str(err)

        bad_stress_dir = root / "run_bad_stress"
        bad_stress_dir.mkdir()
        for f in run_dir.iterdir():
            (bad_stress_dir / f.name).write_bytes(f.read_bytes())
        for seed in (0, 1, 2):
            c = pd.read_parquet(bad_stress_dir / f"contrib_seed_{seed}.parquet")
            c["mystery_driver"] = np.float32(0.0)
            c.to_parquet(bad_stress_dir / f"contrib_seed_{seed}.parquet", index=False)
        try:
            C.decompose(
                bad_stress_dir,
                target=("2022-06-01", "2022-09-30"),
                dataset_dir=ds_dir,
                train_window=("2020-01-01", "2020-12-31"),
                edges=edges,
            )
            raise AssertionError("Unknown stress absent from explain_groups.csv must fail decompose()")
        except ValueError as err:
            assert "mystery_driver" in str(err)

    print("  1. synthetic 3-seed x 2-well x 3-year run: ISO week 53, training_seasonal, window change, "
          "sd, sign agreement (incl. 2/3 & 0-sign), flags, reconstruction, and error guards pass")


def test_synthetic_routed_phase4():
    """Test 3 readiness: routed Phase 4 stress names (pumping_unattributed, river, residual) work unchanged."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        ds_dir = root / "dataset_p4"
        run_dir = root / "p4_B2conv_D_r2"
        run_dir.mkdir()

        weeks = pd.date_range("2020-01-01", "2022-12-31", freq="W-SUN")
        mu_map, edges = _write_synthetic_dataset(ds_dir, weeks)
        stresses = ("recharge", "pumping", "pumping_unattributed", "canal", "river", "residual")
        cfg = {
            "mode": "pooled",
            "lam": 0.1,
            "fixed_steps": 3000,
            "arm": "D",
            "policy": "main",
            "pumping_reconstruction": 2,
            "signs": "gate3",
            "residual": "seasonal",
            "run": "p4_B2conv_D_r2",
            "seeds": [0, 1],
            "fold": None,
            "train_start": None,
            "refit_from": None,
            "dataset": "v4",
        }
        (run_dir / "config.json").write_text(json.dumps(cfg), encoding="utf-8")

        vals_2022 = {
            0: {"recharge": -0.5, "pumping": -0.2, "pumping_unattributed": -0.1, "canal": 0.05, "river": -0.05, "residual": 0.02},
            1: {"recharge": -0.3, "pumping": -0.4, "pumping_unattributed": -0.2, "canal": 0.15, "river": 0.05, "residual": 0.02},
        }
        preds = []
        for seed in (0, 1):
            rows = []
            for code in ("W1", "W2"):
                for wk in weeks:
                    row = {"code_bss": code, "week": wk}
                    for s in stresses:
                        row[s] = np.float32(vals_2022[seed][s] if wk.year == 2022 else 0.0)
                    rows.append(row)
            cdf = pd.DataFrame(rows)
            cdf.to_parquet(run_dir / f"contrib_seed_{seed}.parquet", index=False)
            pd.DataFrame([{"code_bss": c, "group": "g", "d_m": 0.1} for c in ("W1", "W2")]).to_csv(
                run_dir / f"params_seed_{seed}.csv", index=False
            )
            anom = cdf[list(stresses)].astype(float).sum(axis=1) + 0.1
            preds.append(pd.DataFrame({"code_bss": cdf["code_bss"], "week": cdf["week"], "anom": anom}))

        mp = pd.concat(preds).groupby(["code_bss", "week"])["anom"].mean().reset_index()
        mp["pred"] = mp["code_bss"].map(mu_map) + mp["anom"]
        mp["task"] = "simulation"
        mp["horizon"] = 0
        mp[["code_bss", "week", "pred", "task", "horizon"]].to_parquet(
            run_dir / "predictions.parquet", index=False
        )

        diff = C.reconstruct(run_dir, dataset_dir=ds_dir, train_window=("2020-01-01", "2020-12-31"))
        assert diff <= 1e-6, diff
        res = C.decompose(
            run_dir,
            target=("2022-06-01", "2022-09-30"),
            reference="training_seasonal",
            dataset_dir=ds_dir,
            train_window=("2020-01-01", "2020-12-31"),
            edges=edges,
        )
        assert res["metadata"]["protocol"] == "pooled_l0.1_fixed3000"
        assert res["metadata"]["arm"] == "D"
        assert res["metadata"]["export_policy"] == "main"
        assert res["metadata"]["pumping_reconstruction"] == 2
        assert res["metadata"]["residual"] == "seasonal"
        dg = res["by_driver_group"].set_index(["code_bss", "driver_group"])
        # SummerDemand = pumping + pumping_unattributed + canal:
        # seed 0: -0.2 - 0.1 + 0.05 = -0.25; seed 1: -0.4 - 0.2 + 0.15 = -0.45 -> mean = -0.35
        assert np.isclose(dg.loc[("W1", "lulcw:SummerDemand"), "mean_m"], -0.35, atol=1e-6)
        assert np.isclose(dg.loc[("W1", "lulcw:RiverDischargeGroup"), "mean_m"], 0.0, atol=1e-6)
        # Residual has empty driver_group -> absent from by_driver_group, present in by_report_group and total.
        assert "" not in set(res["by_driver_group"]["driver_group"])
        rg = res["by_report_group"].set_index(["code_bss", "report_group"])
        assert np.isclose(rg.loc[("W1", "residual"), "mean_m"], 0.02, atol=1e-6)
        # Total: seed 0 = -0.78, seed 1 = -0.68 -> mean = -0.73.
        tot = res["total"].set_index("code_bss")
        assert np.isclose(tot.loc["W1", "mean_m"], -0.73, atol=1e-6)

    print("  2. routed Phase 4 stress names (pumping_unattributed, river, residual): SummerDemand, "
          "ungrouped residual, reconstruction, and metadata/protocol pass")


def test_real_run():
    """Test 2: real run results/v4/resp_pooled_l001 reconstruction, additivity, and summer 2024 output."""
    run = "resp_pooled_l001"
    data = C.load_run(run, dataset="v4")
    all_wells = sorted(data.d_m["code_bss"].unique())
    non_const_wells = [w for w in all_wells if w != CONSTANT_WELL]

    # Reconstruction on all 63 wells with sd >= SD_FLOOR (including all 33 core wells) passes <= 1e-4 m.
    max_diff_63 = C.reconstruct(run, dataset="v4", wells=non_const_wells)
    assert max_diff_63 <= 1e-4, max_diff_63

    # Against SD_FLOOR-decoded seed_<k>.parquet (current response.py post-f2cd482), ALL 64 wells pass <= 1e-4 m.
    max_diff_seeds_64 = C.reconstruct_from_seeds(run, dataset="v4")
    assert max_diff_seeds_64 <= 1e-4, max_diff_seeds_64

    # On the un-rebuilt pre-f2cd482 predictions.parquet, reconstruct() honestly flags CONSTANT_WELL only.
    try:
        C.reconstruct(run, dataset="v4")
        raise AssertionError("Expected pre-f2cd482 AIGUAN discrepancy to be caught when all 64 wells are checked")
    except ValueError as err:
        assert CONSTANT_WELL in str(err) and "1 well(s)" in str(err), str(err)

    # Full decomposition across all 64 wells x 10 starts under the new default average_forcing (cold + warm cache).
    C.clear_reference_cache()
    t_cold = time.perf_counter()
    res_af = C.decompose(run, target="2024-06-01:2024-09-30", dataset="v4")
    cold_s = time.perf_counter() - t_cold
    t_warm = time.perf_counter()
    res_af_warm = C.decompose(run, target="2024-06-01:2024-09-30", dataset="v4")
    warm_s = time.perf_counter() - t_warm

    assert res_af["reference"]["kind"] == "average_forcing"
    assert res_af["n_seeds"] == 10
    assert len(res_af["total"]) == len(all_wells)
    assert set(res_af["stresses"]) == {"recharge", "pumping", "canal"}
    np.testing.assert_allclose(
        res_af["by_report_group"]["mean_m"].to_numpy(),
        res_af_warm["by_report_group"]["mean_m"].to_numpy(),
        atol=1e-12,
    )

    # Output-space training_seasonal sensitivity across all 64 wells.
    res_ts = C.decompose(run, target="2024-06-01:2024-09-30", reference="training_seasonal", dataset="v4")
    assert res_ts["reference"]["kind"] == "training_seasonal"

    # Check CORNEILLA PD5 placeholder flag in summer 2023.
    res_23 = C.decompose(
        run,
        target="2023-06-01:2023-09-30",
        wells=["10971X0155/PD5"],
        dataset="v4",
    )
    pd5_flags = res_23["flags"].set_index("code_bss").loc["10971X0155/PD5"]
    assert pd5_flags["share_placeholder"] == 1.0 and pd5_flags["share_strict"] == 0.0

    # Check CLI default (average_forcing) and explicit training_seasonal headers on the two anchor core wells.
    buf_af = StringIO()
    with redirect_stdout(buf_af):
        rc = C.main([run, "--target", "2024-06-01:2024-09-30", "--well", *CORE_SAMPLE, "--dataset", "v4"])
    assert rc == 0
    cli_af = buf_af.getvalue()
    assert "Reference: average_forcing" in cli_af
    for code in CORE_SAMPLE:
        assert code in cli_af

    buf_ts = StringIO()
    with redirect_stdout(buf_ts):
        rc = C.main(
            [
                run,
                "--target",
                "2024-06-01:2024-09-30",
                "--reference",
                "training_seasonal",
                "--well",
                *CORE_SAMPLE,
                "--dataset",
                "v4",
            ]
        )
    assert rc == 0
    assert "Reference: training_seasonal" in buf_ts.getvalue()

    # Side-by-side comparison table for NYLS-1 and C2-1 (average_forcing vs training_seasonal).
    af_rg = res_af["by_report_group"].set_index(["code_bss", "report_group"])
    ts_rg = res_ts["by_report_group"].set_index(["code_bss", "report_group"])
    af_tot = res_af["total"].set_index("code_bss")
    ts_tot = res_ts["total"].set_index("code_bss")
    side_rows = []
    for code in CORE_SAMPLE:
        for grp in ("recharge", "pumping_attributed", "canal"):
            a = af_rg.loc[(code, grp)]
            t = ts_rg.loc[(code, grp)]
            side_rows.append(
                {
                    "code_bss": code,
                    "group": grp,
                    "average_forcing": f"{a['mean_m']:+.4f} ± {a['sd_m']:.4f} ({a['sign_agreement']:.2f})",
                    "training_seasonal": f"{t['mean_m']:+.4f} ± {t['sd_m']:.4f} ({t['sign_agreement']:.2f})",
                    "af_minus_ts_m": f"{a['mean_m'] - t['mean_m']:+.4f}",
                }
            )
        at, tt = af_tot.loc[code], ts_tot.loc[code]
        side_rows.append(
            {
                "code_bss": code,
                "group": "TOTAL",
                "average_forcing": f"{at['mean_m']:+.4f} ± {at['sd_m']:.4f} ({at['sign_agreement']:.2f})",
                "training_seasonal": f"{tt['mean_m']:+.4f} ± {tt['sd_m']:.4f} ({tt['sign_agreement']:.2f})",
                "af_minus_ts_m": f"{at['mean_m'] - tt['mean_m']:+.4f}",
            }
        )

    print(
        f"  3. real run {run}: reconstruction max_diff = {max_diff_63:.2e} m on 63/64 wells (all 33 core; "
        f"{max_diff_seeds_64:.2e} m on all 64 wells vs SD_FLOOR-decoded seeds; pre-f2cd482 AIGUAN caught "
        f"honestly); full average_forcing ({len(all_wells)} wells x {res_af['n_seeds']} starts): "
        f"cold {cold_s:.2f}s, warm {warm_s:.2f}s"
    )
    print("\n--- Summer 2024: average_forcing vs training_seasonal side by side (resp_pooled_l001) ---")
    print(pd.DataFrame(side_rows).to_string(index=False))
    print("\n--- CLI default (average_forcing) output ---")
    print(cli_af.rstrip())


def main():
    started = time.perf_counter()
    test_synthetic_average_forcing()
    test_synthetic_ladder()
    test_synthetic_routed_phase4()
    test_real_run()
    print(f"\ntest_explain_contributions: all checks passed ({time.perf_counter() - started:.1f}s)")


if __name__ == "__main__":
    main()
