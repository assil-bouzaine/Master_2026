"""Check GPU runner inputs for the R1 black box and refits (analysis plan sections 4 and 14).

    PFE_DATASET=v4 python -m tests.test_gpu_steps

The runner gets a stand-in for the model interpreter that prints its arguments. The bundle
check lists files without creating an archive. Neither check needs a GPU or fits a model.
"""
import json
import os
import shlex
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from scripts.make_gpu_bundle import ROOT, bundle_files
from src.config import DATASET, PROCESSED

RESULTS = ROOT / "results" / DATASET
TUNING = Path("taccari_tuning/best.json")


def test_runner(tmp_path):
    stub = tmp_path / "python-stub"
    stub.write_text('#!/usr/bin/env bash\nif [ "$1" = -m ]; then printf "model %s\\n" "$*"; fi\n')
    stub.chmod(0o755)
    results = tmp_path / "results"
    env = dict(os.environ, PY=str(stub), SKIP_PIP="1", PIN_TARGET=str(tmp_path / "pins"),
               PFE_DATASET=DATASET, PFE_RESULTS=str(results), STEPS="taccari_D")
    params = json.loads((RESULTS / TUNING).read_text())["params"]
    expected = ["-m", "src.models.taccari", "--edges", "D", "--run", "taccari_D"]
    for name in ("lookback", "hidden", "dropout", "lr"):
        expected.extend([f"--{name}", str(params[name])])

    def run_step():
        run = subprocess.run(["bash", "scripts/run_gpu.sh"], cwd=ROOT, env=env,
                             capture_output=True, text=True, check=True, timeout=30)
        lines = [shlex.split(line)[1:] for line in run.stdout.splitlines() if line.startswith("model ")]
        assert lines == [expected], (run.stdout, run.stderr)
        assert "failed, continuing" not in run.stdout, (run.stdout, run.stderr)

    run_step()
    print(f"  taccari_D echoes the R1 command with all four bundled values: {params}")
    records = sorted(RESULTS.glob("*_tuned/seed_*.json"))
    assert records
    for source in [*records, *sorted(RESULTS.glob("*_tuned/best.json")), RESULTS / TUNING]:
        target = results / source.relative_to(RESULTS)
        assert target.read_bytes() == source.read_bytes(), target
    assert not list(results.glob("*_tuned/*.parquet"))

    seed = results / "taccari_tuned" / "seed_0.json"
    kept = json.loads(seed.read_text())
    kept["best_epoch"] += 1
    seed.write_text(json.dumps(kept))
    kept_seed = seed.read_bytes()
    choice = results / TUNING
    choice.write_text(json.dumps({"params": params | {"hidden": params["hidden"] + 1}}))
    kept_choice = choice.read_bytes()
    run_step()
    assert seed.read_bytes() == kept_seed
    assert choice.read_bytes() == kept_choice
    print(f"  fresh results receive {len(records)} refit seed JSONs; existing seed and tuning JSONs are kept")


def test_bundle_files():
    files = set(bundle_files())
    seeds = {RESULTS / "taccari_tuned" / f"seed_{seed}.json" for seed in range(5)}
    assert seeds <= files, seeds - files
    assert set(RESULTS.glob("*_tuned/best.json")) <= files
    assert not [f for f in files if f.match("*_tuned/*.parquet")]
    export = PROCESSED / "kg" / f"export_{DATASET}_main"
    graph_files = {export / "edges_D.parquet", export / "manifest.json"}
    assert graph_files <= files, graph_files - files
    print(f"  bundle lists all {len(seeds)} Taccari seed JSONs and arm D's edges and manifest")


if __name__ == "__main__":
    start = perf_counter()
    with TemporaryDirectory() as tmp:
        test_runner(Path(tmp))
    test_bundle_files()
    print(f"test_gpu_steps: all checks passed ({perf_counter() - start:.2f}s)")
