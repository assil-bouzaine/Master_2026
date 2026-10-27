"""Run manifests and model checkpoints (third review, docs/review_codex_2026-10-24.md §7).

Stored predictions reproduce a results table, but they cannot be re-run on weeks observed
after the freeze (docs/analysis_plan.md §11), explained or probed with interventions. From
2026-10-24 every run folder of the neural and LightGBM runners therefore also holds:
    manifest.json   what produced it: code version (git commit when there is a repository,
                    always a hash of the src/ tree that ran, which bundles on Kaggle/Colab
                    carry without .git), dataset version and file hashes, resolved
                    configuration and fingerprint, seeds done, Python/package/device versions
    schema.json     (neural) node order, input columns and their training standardisation,
                    lookback: what a checkpoint needs to see the same inputs again
    seed_<k>.pt     (neural) the weights of the selected epoch, with its seed, epoch and
                    validation score; LightGBM writes model_seed_<k>.txt
Pastas needs none of this: params.csv holds every fitted parameter, and
tests/test_replay.py rebuilds the models from it and checks they give the stored predictions.
"""
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone

from src.config import DATASET, DATASET_DIR, RAW, ROOT

# Every dataset file a run reads (src.models.features, the runners, src.models.evaluate). rivers,
# gauges and pumping points were missing until 2026-10-27 (Codex review of 2026-10-26, §8): older
# manifests do not prove those inputs, and are not completed after the fact.
DATASET_FILES = ("meta.json", "splits.json", "wells.parquet", "heads_weekly.parquet",
                 "forcing_weekly.parquet", "pumping_weekly.parquet", "pumping_points.parquet",
                 "rivers_weekly.parquet", "gauges.parquet", "placeholder_weeks.parquet")


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def code_version():
    """git commit and dirty flag if available; always the hash of the src/*.py that ran."""
    h = hashlib.sha256()
    for f in sorted((ROOT / "src").rglob("*.py")):
        h.update(str(f.relative_to(ROOT)).encode())
        h.update(f.read_bytes())
    out = {"src_sha256": h.hexdigest()}
    try:
        run = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True,  # noqa: E731
                                        timeout=10, check=True).stdout.strip()
        out["git_commit"] = run("rev-parse", "HEAD")
        out["git_dirty"] = bool(run("status", "--porcelain", "--", "src"))
    except Exception:  # noqa: BLE001 - no repository on Kaggle/Colab bundles
        out["git_commit"] = None
    return out


def environment():
    env = {"python": sys.version.split()[0], "platform": platform.platform()}
    for name in ("numpy", "pandas", "scipy", "torch", "lightgbm", "pastas", "optuna"):
        mod = sys.modules.get(name)
        if mod is not None:
            env[name] = getattr(mod, "__version__", None)
    torch = sys.modules.get("torch")
    if torch is not None:
        env["cuda"] = torch.version.cuda
        env["device"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
        env["threads"] = torch.get_num_threads()
    return env


# inputs outside the dataset folder (src.models.taccari reads the SAFRAN grid points)
OTHER_INPUTS = {"safran_grid": RAW / "safran" / "grid_cells_66.parquet"}


def dataset_hashes():
    return {f: sha256_file(DATASET_DIR / f)[:16] for f in DATASET_FILES
            if (DATASET_DIR / f).exists()}


def other_input_hashes():
    return {k: sha256_file(p)[:16] for k, p in OTHER_INPUTS.items() if p.exists()}


def write_manifest(out, config, seeds_done=()):
    """Create or update out/manifest.json; a resumed run appends its session."""
    f = out / "manifest.json"
    m = json.loads(f.read_text()) if f.exists() else {"created": None, "sessions": []}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    m["created"] = m["created"] or now
    m["dataset"] = {"version": DATASET, "files_sha256_16": dataset_hashes(),
                    "other_inputs_sha256_16": other_input_hashes()}
    m["config"] = json.loads(json.dumps(config, default=str))
    m["seeds_done"] = sorted(set(m.get("seeds_done", [])) | set(seeds_done))
    m["sessions"].append({"at": now, "code": code_version(), "environment": environment()})
    f.write_text(json.dumps(m, indent=1))
    return m


def write_schema(out, schema):
    """out/schema.json; a folder whose cached seeds saw other inputs stops the run."""
    f = out / "schema.json"
    new = json.loads(json.dumps(schema, default=float))
    if f.exists() and json.loads(f.read_text()) != new:
        raise SystemExit(f"{f} differs from the inputs of this run: its checkpoints saw other "
                         "inputs (node order, columns or standardisation); use another --run")
    f.write_text(json.dumps(new, indent=1))


def save_checkpoint(path, state, meta):
    """Weights (CPU tensors) and their metadata, loadable with torch.load(weights_only=True)."""
    import torch
    torch.save({"state_dict": {k: v.detach().cpu() for k, v in state.items()},
                "meta": json.loads(json.dumps(meta, default=float))}, path)


def load_checkpoint(path):
    import torch
    return torch.load(path, map_location="cpu", weights_only=True)
