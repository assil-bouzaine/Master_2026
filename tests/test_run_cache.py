"""Resumable runs reuse a cached result only if it was made with the same settings.

    python -m tests.test_run_cache

Third review (docs/review_codex_2026-10-24.md §7): the neural runners skipped a seed whose
file existed, overwrote config.json, and averaged whatever seed files a folder held; the
leave-wells-out assembly accepted a fold with some seeds missing. Checked here, without
training anything:
1. config.json carries a fingerprint; the same settings pass, other settings stop the run,
   and a folder written before fingerprints is compared on the settings both versions record.
2. A cached seed of other settings stops the run; a seed saved before fingerprints passes.
3. The mean over seeds uses exactly the requested seeds and fails if one is missing.
4. A leave-wells-out fold is assembled only with exactly the expected seeds.
"""
import argparse
import json
import tempfile
from pathlib import Path

import pandas as pd

from src.models import regimes
from src.models.lstm import cached_seed, save_seed, seed_mean_predictions, write_config


def args(**kw):
    base = dict(seeds=[0, 1], epochs=60, run="x", arch="lstm", lookback=104, hidden=64,
                dropout=0.2, lr=1e-3, fold=None, train_start=None, refit_from=None)
    return argparse.Namespace(**(base | kw))


def stops(f, *a):
    try:
        f(*a)
    except SystemExit:
        return True
    return False


def main():
    inputs = ["rain", "ETP"]
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "run"
        out.mkdir()
        fp = write_config(out, args(), inputs)
        assert json.loads((out / "config.json").read_text())["fingerprint"] == fp
        assert write_config(out, args(seeds=[2, 3], run="y"), inputs) == fp, "seeds/run matter"
        assert stops(write_config, out, args(hidden=32), inputs), "other settings accepted"
        legacy = vars(args()) | {"inputs": inputs}                  # no fingerprint, no dataset
        (out / "config.json").write_text(json.dumps(legacy))
        assert write_config(out, args(), inputs) == fp, "legacy folder with same settings refused"
        (out / "config.json").write_text(json.dumps(legacy | {"lr": 0.01}))
        assert stops(write_config, out, args(), inputs), "legacy folder with other lr accepted"
        print("  1. config.json: same settings pass, other settings stop, legacy folders compared")

        codes, weeks = ["W1", "W2"], pd.date_range("2019-01-06", periods=3, freq="W-SUN")
        pz = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        assert not cached_seed(out / "seed_0.parquet", fp)
        save_seed(out / "seed_0.parquet", pz, codes, weeks, 0.5, 7, fp)
        assert cached_seed(out / "seed_0.parquet", fp)
        assert stops(cached_seed, out / "seed_0.parquet", "other"), "seed of other settings reused"
        save_seed(out / "seed_1.parquet", pz, codes, weeks, 0.5, 7)          # as before 2026-10-25
        meta = json.loads((out / "seed_1.json").read_text())
        (out / "seed_1.json").write_text(json.dumps({k: v for k, v in meta.items()
                                                     if k != "fingerprint"}))
        assert cached_seed(out / "seed_1.parquet", fp), "legacy seed refused"
        print("  2. cached seeds: same settings reused, other settings stop, legacy seeds pass")

        P = pd.DataFrame([(c, w, 10.0, 2.0) for c in codes for w in weeks],
                         columns=["code_bss", "week", "mu", "sd"])
        pred, n = seed_mean_predictions(out, P, [0, 1])
        assert n == 2 and len(pred) == 6
        try:
            seed_mean_predictions(out, P, [0, 1, 2])
            raise AssertionError("a missing seed was not reported")
        except FileNotFoundError:
            pass
        print("  3. the seed mean uses exactly the requested seeds; a missing one fails")

        regimes.RESULTS = Path(d)
        for k in (0, 1):
            (Path(d) / "lwo" / f"fold_{k}").mkdir(parents=True)
            for s in ([0, 1, 2] if k == 0 else [0, 1]):
                (Path(d) / "lwo" / f"fold_{k}" / f"seed_{s}.parquet").touch()
        assert len(regimes.fold_seed_files("lwo", 0, [0, 1, 2])) == 3
        try:
            regimes.fold_seed_files("lwo", 1, [0, 1, 2])
            raise AssertionError("a fold with a missing seed was accepted")
        except FileNotFoundError:
            pass
        regimes.EXTRA[:] = ["--seeds", "0", "1", "--epochs", "2"]
        assert regimes.expected_seeds() == [0, 1]
        regimes.EXTRA[:] = []
        assert regimes.expected_seeds() == [0, 1, 2, 3, 4]
        print("  4. a leave-wells-out fold is assembled only with exactly the expected seeds")
    print("test_run_cache: all checks passed")


if __name__ == "__main__":
    main()
