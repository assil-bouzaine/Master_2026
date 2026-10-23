"""Copy the configurations selected on dataset v3 into results/v4 (analysis plan v2, §5).

    .venv/bin/python scripts/v4_from_v3.py          # skips models whose v3 selection is missing

Dataset v4 changes 71 of 29,784 training weeks, the leave-wells-out folds and the R3
statistics, so the baselines keep the configuration chosen on v3 (24 Optuna trials and the
3-seed re-selection) and only their final seeds and regimes are re-run on v4. Each copied
best.json records where it came from. An existing v4 best.json is never overwritten.
"""
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V3, V4 = ROOT / "results" / "v3", ROOT / "results" / "v4"
SELECTIONS = ["lgbm_noclim_tuned", "lstm_tuning", "ealstm_tuning", "stgnn_tuning",
              "taccari_tuning"]


def main():
    missing = []
    for name in SELECTIONS:
        src, dst = V3 / name / "best.json", V4 / name / "best.json"
        if dst.exists():
            print(f"{name}: v4 selection exists, kept")
            continue
        if not src.exists():
            missing.append(name)
            continue
        best = json.loads(src.read_text())
        best["copied_from"] = str(src.relative_to(ROOT))
        best["copied_on"] = date.today().isoformat()
        best["reason"] = "dataset v4 re-run with the v3 selection (analysis plan v2, section 5)"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(json.dumps(best, indent=1))
        print(f"{name}: {best['params']}")
    if missing:
        print("not selected on v3 yet (run again later):", " ".join(missing), file=sys.stderr)


if __name__ == "__main__":
    main()
