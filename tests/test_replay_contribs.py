"""Check the Phase 5 replay tolerance and restore the ladder's contributions (analysis plan §12).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_replay_contribs

Only a temporary copy is changed. The original tables provide an independent check
of the reconstruction, and a second invocation checks that the files are preserved.
"""
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from scripts.replay_contribs import HEAD_TOL_M, compare_predictions
from src.models.evaluate import RESULTS


def run_cli(folder):
    return subprocess.run([sys.executable, "-m", "scripts.replay_contribs", str(folder)],
                          capture_output=True, text=True)


def snapshot(paths):
    return {path.name: (path.stat().st_ino, path.stat().st_mtime_ns,
                        hashlib.sha256(path.read_bytes()).hexdigest()) for path in paths}


def test_head_tolerance():
    rebuilt = pd.DataFrame({"code_bss": ["ordinary", "floored"],
                            "week": pd.Timestamp("2024-01-07"), "z": 0.0})
    sd = np.array([[1.0], [1e-8]])
    saved = rebuilt.iloc[::-1].copy()
    saved.loc[saved["code_bss"] == "floored", "z"] = 1e-4
    delta_head, delta_z = compare_predictions(rebuilt, saved, sd, "predictions")
    np.testing.assert_allclose((delta_head, delta_z), (1e-7, 1e-4), rtol=1e-12, atol=0)

    saved.loc[saved["code_bss"] == "ordinary", "z"] = 1e-4
    try:
        compare_predictions(rebuilt, saved, sd, "predictions")
    except ValueError as error:
        assert "head at ('ordinary'," in str(error), error
        assert "differs by 0.0001 m" in str(error), error
    else:
        raise AssertionError("A head difference of 1e-4 m must fail")
    print("  The same 1e-4 z difference passes for a floored SD and fails for an SD of 1 m.")


def test_replay_contribs():
    original = RESULTS / "resp_pooled_l001"
    originals = sorted(original.glob("contrib_seed_*.parquet"))
    assert originals, f"Missing the ladder's original contribution files in {original}"
    with TemporaryDirectory() as tmp:
        copy = Path(tmp) / original.name
        shutil.copytree(original, copy, ignore=shutil.ignore_patterns("contrib_seed_*.parquet"))
        provenance = copy / "contrib_replayed.json"
        assert not list(copy.glob("contrib_seed_*.parquet")) and not provenance.exists()

        built = run_cli(copy)
        assert built.returncode == 0, built.stderr
        assert f"written={len(originals)} compared=0" in built.stdout, built.stdout
        paths = sorted(copy.glob("contrib_seed_*.parquet"))
        assert [path.name for path in paths] == [path.name for path in originals]
        for rebuilt, saved in zip(paths, originals):
            pd.testing.assert_frame_equal(pd.read_parquet(rebuilt), pd.read_parquet(saved),
                                          check_exact=False, rtol=0, atol=1e-5)

        record, = json.loads(provenance.read_text(encoding="utf-8"))["replays"]
        assert record["starts"] == sorted(int(path.stem.rsplit("_", 1)[1]) for path in originals)
        assert re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", record["commit"])
        assert datetime.fromisoformat(record["utc_time"]).utcoffset() == timedelta(0)
        assert 0 <= record["max_abs_delta_head_m"] <= HEAD_TOL_M
        assert record["max_abs_delta_z"] >= 0
        assert record["max_abs_delta_param"] >= 0
        before = snapshot([*paths, provenance])
        print(built.stdout.strip())

        compared = run_cli(copy)
        assert compared.returncode == 0, compared.stderr
        assert f"written=0 compared={len(originals)}" in compared.stdout, compared.stdout
        assert snapshot([*paths, provenance]) == before
        print(compared.stdout.strip())

        # A late mismatch must keep even an earlier, verified start unwritten.
        paths[0].unlink()
        late_seed = record["starts"][-1]
        late_prediction = copy / f"seed_{late_seed}.parquet"
        prediction = pd.read_parquet(late_prediction)
        prediction.loc[0, "z"] += 1.0
        prediction.to_parquet(late_prediction, index=False)
        rejected = run_cli(copy)
        assert rejected.returncode == 1, rejected.stderr
        assert f"{late_prediction.name}: head at " in rejected.stderr, rejected.stderr
        assert not paths[0].exists()
        assert snapshot([*paths[1:], provenance]) == {key: value for key, value in before.items()
                                                     if key != paths[0].name}
        print(rejected.stderr.strip())


if __name__ == "__main__":
    test_head_tolerance()
    test_replay_contribs()
    print("test_replay_contribs: all checks passed")
