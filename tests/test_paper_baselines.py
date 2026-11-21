"""Check the paper's baseline fragments against the v4 report.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_paper_baselines

Rebuild twice with the CLI, check every cell and command against main_table(),
and compile all three fragments together when a LaTeX compiler is available.
"""
import math
from pathlib import Path
import re
from shutil import which
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

from src.analysis.baseline_report import main_table
from src.config import TEST_PERIODS

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / "results/_agents/tmp/T39"
SCRIPT = "paper/tools/baseline_tables.py"
FILES = ("baselines_simulation.tex", "baselines_forecast.tex", "baselines_numbers.tex")


def printed_number(value, precision=2):
    if math.isnan(value):
        return r"\textemdash{}"
    return r"\num{" + format(value, f".{precision}f") + "}"


def check_table(text, source, *, forecast=False):
    metrics = ["NSE drought", "skill drought", "NSE recovery", "skill recovery"]
    if not forecast:
        metrics.append("KGE'' test")
    body = text.split("\\midrule\n", 1)[1].split("\\bottomrule\n", 1)[0]
    rows = [line.removesuffix(r" \\").split(" & ") for line in body.splitlines()]
    assert len(rows) == len(source)
    for cells, (_, entry) in zip(rows, source.iterrows()):
        model = entry["model"].removesuffix(" [reference]")
        numbers = [printed_number(entry[metric]) for metric in metrics]
        numbers.append(printed_number(entry["wells"], 0))
        expected = [model, *numbers]
        if forecast:
            expected.insert(0, printed_number(entry["h"], 0))
        assert cells == expected, (entry["h"], model, cells, expected)

    caption = re.search(r"\\caption\{([^{}\n]+)\}", text)[1]
    assert "medians over the 33 core wells" in caption
    for phase in ("drought", "recovery"):
        first, last = TEST_PERIODS["test_" + phase]
        assert f"{phase.capitalize()} covers {first} to {last or 'end of record'}" in caption
    if forecast:
        assert "anomaly persistence" in caption
    else:
        reference = source.loc[source["model"].str.endswith("[reference]"), "model"].item()
        assert reference.removesuffix(" [reference]") in caption and "[reference]" not in text
        assert "training climatology" in caption
    assert r"\toprule" in text
    cells_checked = len(rows) * (len(metrics) + 1 + forecast)
    print(f"  {'Forecast' if forecast else 'Simulation'}: {len(rows)} rows, "
          f"{cells_checked} numeric cells match main_table().")


def check_macros(text, simulation, forecast):
    expected = {}
    for horizon, word in ((4, "Four"), (12, "Twelve")):
        scores = forecast.loc[forecast["h"] == horizon].set_index("model")["NSE drought"]
        chronos = [model for model in scores.index if model.startswith("Chronos-2 ")]
        assert len(chronos) == 3, (horizon, chronos)
        best = max(chronos, key=scores.__getitem__)
        expected[f"baselineChronos{word}Variant"] = best
        for name, model in (("Chronos", best), ("LightGBM", "LightGBM"),
                            ("AnomalyPersistence", "Anomaly persistence (floor)")):
            expected[f"baseline{name}{word}DroughtNSE"] = printed_number(scores[model])

    reference = simulation.loc[simulation["model"].str.endswith("[reference]"), "model"].item()
    scores = simulation.set_index("model")
    for name, label in (("Pastas", reference), ("LSTM", "LSTM tuned (Optuna, 5 seeds)"),
                        ("DistanceSTGNN", "Distance-graph ST-GNN tuned (5 seeds)"),
                        ("Ensemble", "Ensemble (members chosen on validation)")):
        for metric, suffix in (("NSE drought", "NSE"), ("skill drought", "Skill")):
            expected[f"baseline{name}Drought{suffix}"] = printed_number(scores.at[label, metric])

    entries = [line for line in text.splitlines() if not line.startswith("%")]
    pairs = re.findall(r"^\\newcommand\{\\([A-Za-z]+)\}\{(.+)\} % .+$", text, re.MULTILINE)
    assert len(entries) == len(pairs) == len(expected)
    assert dict(pairs) == expected, (dict(pairs), expected)
    print(f"  All {len(pairs)} commands match main_table(), including both Chronos-2 winners.")
    return list(expected)


def check_latex(out, macro_names):
    if compiler := which("latexmk"):
        command = [compiler, "-pdf"]
    elif compiler := which("pdflatex"):
        command = [compiler]
    else:
        print("  LaTeX fragment compilation skipped (latexmk and pdflatex are absent from PATH).")
        return

    fragment = "\n".join([
        r"\documentclass{article}", r"\usepackage{booktabs,siunitx}",
        r"\input{baselines_numbers.tex}", r"\begin{document}",
        r"\quad ".join("\\" + name + "{}" for name in macro_names),
        r"\input{baselines_simulation.tex}", r"\input{baselines_forecast.tex}",
        r"\end{document}", "",
    ])
    (out / "fragment.tex").write_text(fragment, encoding="utf-8")
    result = subprocess.run([*command, "-interaction=nonstopmode", "-halt-on-error", "fragment.tex"],
                            cwd=out, capture_output=True, text=True)
    assert result.returncode == 0 and (out / "fragment.pdf").is_file(), result.stdout + result.stderr
    print(f"  LaTeX fragment compilation passed with {Path(compiler).name}.")


def test_generated_baselines():
    source = main_table()
    simulation = source.loc[(source["task"] == "simulation") & (source["h"] == 0)]
    forecast = source.loc[(source["task"] == "forecast") & source["h"].isin((4, 12))]
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=SCRATCH) as temporary:
        outputs = []
        first = Path(temporary) / "first"
        for out in (first, Path(temporary) / "second"):
            result = subprocess.run([sys.executable, SCRIPT, "--out", str(out)],
                                    cwd=ROOT, capture_output=True, text=True)
            assert result.returncode == 0, result.stdout + result.stderr
            assert sorted(p.name for p in out.iterdir()) == sorted(FILES)
            outputs.append([(out / name).read_bytes() for name in FILES])
        assert outputs[0] == outputs[1]
        print("  Two CLI builds produced three byte-identical fragments.")
        sim_text, forecast_text, macro_text = (data.decode("utf-8") for data in outputs[0])
        for text in (sim_text, forecast_text, macro_text):
            assert text.splitlines()[0].startswith("% Generated by ")
            assert SCRIPT in text.splitlines()[0]
        check_table(sim_text, simulation)
        check_table(forecast_text, forecast, forecast=True)
        macro_names = check_macros(macro_text, simulation, forecast)
        check_latex(first, macro_names)


if __name__ == "__main__":
    started = time.perf_counter()
    test_generated_baselines()
    print(f"test_paper_baselines: all checks passed ({time.perf_counter() - started:.2f}s)")
