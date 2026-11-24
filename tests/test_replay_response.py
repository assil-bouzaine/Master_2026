"""Guard tests for response-model refactoring and replay (src/models/response.py).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_replay_response

Why this test exists (docs/analysis_plan.md §11 and §12; task T49)
------------------------------------------------------------------
To test explanation faithfulness and later score frozen models on weeks observed after the
freeze (§11), we must rebuild any saved response-model run from its ``config.json`` and
``seed_<k>.pt`` and reproduce its saved per-stress contributions and z-predictions without
re-fitting. At the same time, refactoring ``main()`` into ``build_parser()`` and ``prepare()``
must preserve every saved run's fingerprint so ``cached_seed`` still recognises finished starts.

Checks:
1. For the six ladder runs (resp_free, resp_pooled_l001, resp_shared, resp_pooled_l01_conv,
   resp_free_split, resp_pooled_sd_l01), plus any routed Phase 4 run (e.g. p4_B2_D_r1) and
   seasonal-residual B8 run when present on disk:
   - replaying seeds 0 and 9 reproduces contrib_seed_<k>.parquet within 1e-5 m on every well-week;
   - replayed z-predictions match seed_<k>.parquet within 1e-5 on every well-week;
   - the rebuilt fingerprint equals config.json["fingerprint"] and cached_seed returns True.
2. Pure-prepare check: prepare(args) writes no file.
3. Zero-training forward-pass round-trip on a routed Phase 4 leave-wells-out fold folder with
   arm D, gate3 signs, statics B, message passing (1 hop), FFT convolution, and seasonal residual:
   verifies replay and fingerprint matching on the full Phase 4 feature set even before Colab
   runs are pulled.
"""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch

import numpy as np
import pandas as pd
import torch

from src.models import response as R
from src.models.evaluate import RESULTS
from src.models.lstm import cached_seed, run_fingerprint, save_seed, save_seed_model, write_config

LADDER_RUNS = (
    "resp_free",
    "resp_pooled_l001",
    "resp_shared",
    "resp_pooled_l01_conv",
    "resp_free_split",
    "resp_pooled_sd_l01",
)
SEEDS = (0, 9)
CONTRIB_TOL_M = 1e-5
Z_TOL = 1e-5


def _optional_phase4_runs() -> list[str]:
    """Return optional Phase 4 runs (one routed, one B8 seasonal residual) when present on disk."""
    found: list[str] = []
    for candidate in ("p4_B2_D_r1", "p4_B2conv_D_r1", "p4_B2_C_r1"):
        if (RESULTS / candidate / "config.json").is_file() and (RESULTS / candidate / "seed_0.pt").is_file():
            found.append(candidate)
            break
    if RESULTS.is_dir():
        b8_dirs = sorted(
            p.name
            for p in RESULTS.iterdir()
            if p.is_dir() and p.name.startswith("p4_B8_") and (p / "config.json").is_file()
            and (p / "seed_0.pt").is_file()
        )
        if b8_dirs:
            found.append(b8_dirs[0])
    return found


def _check_run_replay(run_dir: Path, seeds: tuple[int, ...] = SEEDS) -> tuple[float, float, str]:
    """Replay `seeds` of `run_dir`, check contributions (<= 1e-5 m), z (<= 1e-5), and fingerprint."""
    cfg = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    args = R.args_from_config(cfg)
    prep = R.prepare(args, verbose=False)

    # Guard 3: rebuilt fingerprint equals saved config.json fingerprint, and cached_seed accepts it.
    fp = run_fingerprint(prep["config_args"], prep["inputs"], prep["fp_extra"] or None)
    assert fp == prep["fingerprint"], (run_dir.name, fp, prep["fingerprint"])
    assert fp == cfg["fingerprint"], (
        f"{run_dir.name}: rebuilt fingerprint {fp} != saved {cfg['fingerprint']}"
    )

    max_contrib_diff = 0.0
    max_z_diff = 0.0
    for idx, seed in enumerate(seeds):
        seed_path = run_dir / f"seed_{seed}.parquet"
        assert cached_seed(seed_path, fp), f"{run_dir.name}: cached_seed rejected seed {seed}"

        # Exercise both the standalone 2-arg replay() call and the prep-reusing call.
        if idx == 0:
            net, data = R.replay(run_dir, seed)
        else:
            net, data = R.replay(run_dir, seed, prep=prep)

        X_t = {k: torch.from_numpy(v) for k, v in data["X"].items()}
        with torch.no_grad():
            raw_contrib = net.contributions(X_t).numpy()  # (N, R, T)
            res = None if net.res_coef is None else net.residual().numpy()  # (N, T)
            out = net.d.numpy()[:, None] + raw_contrib.sum(1)
            if res is not None:
                out = out + res
        sd_safe = np.maximum(data["sd"], R.SD_FLOOR)
        replayed_z = (out / sd_safe).astype(np.float32)

        # Build replayed contribution columns matching saved parquet (merge river_c into river if present).
        c_dict = {name: raw_contrib[:, r] for r, name in enumerate(net.names)}
        if "river_c" in c_dict:
            c_dict["river"] = c_dict["river"] + c_dict.pop("river_c")
        if res is not None:
            c_dict["residual"] = res

        saved_c = pd.read_parquet(run_dir / f"contrib_seed_{seed}.parquet")
        saved_c["week"] = pd.to_datetime(saved_c["week"])
        saved_c = saved_c.sort_values(["code_bss", "week"], kind="mergesort").reset_index(drop=True)
        expected_cols = [c for c in saved_c.columns if c not in ("code_bss", "week")]
        assert set(expected_cols) == set(c_dict), (
            f"{run_dir.name} seed {seed}: columns {expected_cols} != {sorted(c_dict)}"
        )

        N, T = len(data["codes"]), len(data["weeks"])
        assert len(saved_c) == N * T
        for col in expected_cols:
            got = c_dict[col].astype(np.float64).reshape(-1)
            want = saved_c[col].to_numpy(dtype=np.float64)
            diff = float(np.max(np.abs(got - want)))
            max_contrib_diff = max(max_contrib_diff, diff)
            assert diff <= CONTRIB_TOL_M, (
                f"{run_dir.name} seed {seed} {col}: max |contrib diff| = {diff:.3e} m > {CONTRIB_TOL_M:.1e}"
            )

        saved_z = pd.read_parquet(seed_path)
        saved_z["week"] = pd.to_datetime(saved_z["week"])
        saved_z = saved_z.sort_values(["code_bss", "week"], kind="mergesort").reset_index(drop=True)
        assert len(saved_z) == N * T
        z_diff = float(np.max(np.abs(replayed_z.astype(np.float64).reshape(-1) - saved_z["z"].to_numpy(dtype=np.float64))))
        max_z_diff = max(max_z_diff, z_diff)
        assert z_diff <= Z_TOL, (
            f"{run_dir.name} seed {seed}: max |z diff| = {z_diff:.3e} > {Z_TOL:.1e}"
        )

        # Also verify seed_outputs(net, data) agrees identically with the direct computation.
        pz_so, c_so, _ = R.seed_outputs(net, data)
        assert np.allclose(pz_so, replayed_z, atol=1e-7)
        for col in expected_cols:
            assert np.allclose(c_so[col].to_numpy(), c_dict[col].reshape(-1), atol=1e-7)

    return max_contrib_diff, max_z_diff, fp


def test_prepare_writes_no_files():
    """prepare(args) must be pure: it writes no files under RESULTS."""
    with TemporaryDirectory() as tmp:
        fake_results = Path(tmp)
        args = R.build_parser().parse_args(["--mode", "pooled", "--lam", "0.01", "--run", "_pure_check"])
        with patch.object(R, "RESULTS", fake_results):
            prep = R.prepare(args, verbose=False)
        assert list(fake_results.iterdir()) == [], "prepare() must not write any files"
        assert "data" in prep and "model_kwargs" in prep and "fingerprint" in prep
    print("  1. prepare(args) writes no files and returns inputs, schema, fingerprint, and model_kwargs")


def test_saved_runs_replay_and_fingerprints():
    """Replay seeds 0 and 9 and verify fingerprints for all ladder runs (+ Phase 4 runs when present)."""
    runs = list(LADDER_RUNS) + _optional_phase4_runs()
    print(f"  2. Checking replay and fingerprints on {len(runs)} saved runs (seeds {SEEDS}):")
    for name in runs:
        run_dir = RESULTS / name
        assert run_dir.is_dir(), f"Expected run folder not found: {run_dir}"
        max_c, max_z, fp = _check_run_replay(run_dir, seeds=SEEDS)
        print(f"     {name:24s}  fp={fp}  max|Δcontrib|={max_c:.2e} m  max|Δz|={max_z:.2e}")
    if len(runs) == len(LADDER_RUNS):
        print("     (note: no routed p4_* or B8 residual runs present on disk yet; covered by test 3 below)")


def test_phase4_fold_gate3_residual_roundtrip():
    """Zero-training forward-pass round-trip for arm D + gate3 + statics B + message 1 + seasonal residual
    inside a leave-wells-out fold_0 folder (proves replay handles every Phase 4 feature and folds)."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        argv = [
            "--mode", "pooled", "--lam", "0.01", "--run", "_p4_b8_roundtrip",
            "--arm", "D", "--policy", "main", "--signs", "gate3",
            "--conv", "fft", "--statics", "B", "--static-control", "shuffled",
            "--message", "1", "--residual", "seasonal", "--fold", "0", "--seeds", "0",
        ]
        args = R.build_parser().parse_args(argv)
        R._canonicalize_args(args)
        prep = R.prepare(args, verbose=False)

        fold_dir = root / "_p4_b8_roundtrip" / "fold_0"
        fold_dir.mkdir(parents=True, exist_ok=True)
        fp = write_config(fold_dir, args, prep["inputs"], prep["fp_extra"] or None)
        assert fp == prep["fingerprint"]

        # Build an untrained model with non-zero random weights and residual coefficients (no training!).
        Z = R.seed_statics(prep["Z0"], prep["static_control"], 0)
        gen = torch.Generator().manual_seed(42)
        net = R.ResponseModel(**prep["model_kwargs"], statics=Z, init_sd=0.5, generator=gen)
        with torch.no_grad():
            net.d.copy_(torch.randn(net.d.shape, generator=gen) * 0.2)
            net.res_coef.copy_(torch.randn(net.res_coef.shape, generator=gen) * 0.4)
            net.static_map.weight.copy_(torch.randn(net.static_map.weight.shape, generator=gen) * 0.05)

        pz, contrib, params = R.seed_outputs(net, prep["data"])
        contrib.to_parquet(fold_dir / "contrib_seed_0.parquet", index=False)
        params.to_csv(fold_dir / "params_seed_0.csv", index=False)
        save_seed_model(fold_dir, 0, net.state_dict(), best=0.0, best_ep=0, fp=fp)
        save_seed(fold_dir / "seed_0.parquet", pz, prep["data"]["codes"], prep["data"]["weeks"], 0.0, 0, fp)

        max_c, max_z, fp_rebuilt = _check_run_replay(fold_dir, seeds=(0,))
        assert fp_rebuilt == fp
        print(
            f"  3. Phase 4 fold_0 round-trip (arm D + gate3 + statics B shuffled + message 1 + fft + "
            f"seasonal residual, no training): fp={fp_rebuilt}  max|Δcontrib|={max_c:.2e} m  max|Δz|={max_z:.2e}"
        )


def main():
    started = time.perf_counter()
    test_prepare_writes_no_files()
    test_saved_runs_replay_and_fingerprints()
    test_phase4_fold_gate3_residual_roundtrip()
    print(f"test_replay_response: all checks passed ({time.perf_counter() - started:.1f}s)")


if __name__ == "__main__":
    main()
