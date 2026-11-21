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

import pandas as pd

from src.analysis import baseline_report
from src.analysis.baseline_report import main_table, reference_spread, regimes_table
from src.analysis.pastas_stability import BASE as PASTAS_BASE, start_runs
from src.analysis.stats import clusters, holm, paired, sign_flip_p
from src.config import TEST_PERIODS
from src.models.evaluate import DS, RESULTS

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / "results/_agents/tmp/T39"
SCRIPT = "paper/tools/baseline_tables.py"
FILES = ("baselines_simulation.tex", "baselines_forecast.tex", "baselines_numbers.tex")


def printed_number(value, precision=2, *, signed=False):
    if math.isnan(value):
        return r"\textemdash{}"
    spec = f"+.{precision}f" if signed else f".{precision}f"
    return r"\num{" + format(value, spec) + "}"


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


def _drought_metric(path, metric):
    df = pd.read_csv(path)
    mask = (
        (df["task"] == "simulation")
        & (df["horizon"] == 0)
        & (df["split"] == "test_drought")
        & (df["variant"] == "all")
        & df["core"]
    )
    return df.loc[mask].set_index("code_bss")[metric]


def _cluster_holm(metric, ref_path, sim_runs, well_clusters):
    b = _drought_metric(ref_path, metric)
    rows = []
    for run in sim_runs:
        a = _drought_metric(RESULTS / run / "metrics_per_well.csv", metric)
        j = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
        diff = j["a"] - j["b"]
        groups = [g.to_numpy() for _, g in diff.groupby(well_clusters.loc[diff.index].to_numpy())]
        pc = sign_flip_p(groups, seed=2026) if (diff != 0).any() else 1.0
        rows.append({"run": run, "median_diff": float(diff.median()),
                     "n_clusters": len(groups), "p_cluster": pc})
    df = pd.DataFrame(rows).set_index("run")
    df["p_holm"] = holm(df["p_cluster"].to_numpy())
    return df


def check_macros(text, simulation, forecast):
    expected = {}
    for horizon, word in ((4, "Four"), (12, "Twelve")):
        scores = forecast.loc[forecast["h"] == horizon].set_index("model")
        chronos = [model for model in scores.index if model.startswith("Chronos-2 ")]
        assert len(chronos) == 3, (horizon, chronos)
        best = max(chronos, key=scores["NSE drought"].__getitem__)
        expected[f"baselineChronos{word}Variant"] = best
        for name, model in (("Chronos", best), ("LightGBM", "LightGBM"),
                            ("AnomalyPersistence", "Anomaly persistence (floor)")):
            expected[f"baseline{name}{word}DroughtNSE"] = printed_number(scores.at[model, "NSE drought"])
        expected[f"baselineChronos{word}DroughtSkill"] = printed_number(scores.at[best, "skill drought"])

    reference = simulation.loc[simulation["model"].str.endswith("[reference]"), "model"].item()
    scores = simulation.set_index("model")
    for name, label in (("Pastas", reference), ("LSTM", "LSTM tuned (Optuna, 5 seeds)"),
                        ("DistanceSTGNN", "Distance-graph ST-GNN tuned (5 seeds)"),
                        ("Ensemble", "Ensemble (members chosen on validation)")):
        for metric, suffix in (("NSE drought", "NSE"), ("skill drought", "Skill")):
            expected[f"baseline{name}Drought{suffix}"] = printed_number(scores.at[label, metric])

    expected["baselineClimatologyDroughtNSE"] = printed_number(
        scores.at["Climatology (floor)", "NSE drought"]
    )
    ealstm = "EA-LSTM tuned (Optuna, 5 seeds)"
    expected["baselineEALSTMDroughtNSE"] = printed_number(scores.at[ealstm, "NSE drought"])
    expected["baselineEALSTMDroughtSkill"] = printed_number(scores.at[ealstm, "skill drought"])
    tuned_single_labels = [dict(baseline_report.SIM)[f"{m}_tuned"]
                           for m, _ in baseline_report.REGIME_MODELS]
    assert scores.loc[tuned_single_labels, "NSE drought"].idxmin() == ealstm
    assert scores.loc[tuned_single_labels, "NSE drought"].idxmax() == "LSTM tuned (Optuna, 5 seeds)"
    assert scores.loc[tuned_single_labels, "skill drought"].idxmin() == ealstm
    assert scores.loc[tuned_single_labels, "skill drought"].idxmax() == "LSTM tuned (Optuna, 5 seeds)"

    spread = reference_spread()
    trainobs = spread.loc[spread["construction"] == "training heads only"].iloc[0]
    start_cols = [col for col in spread.columns if col.startswith("start ")]
    start_vals = [float(trainobs[col]) for col in start_cols]
    expected["baselinePastasStarts"] = printed_number(len(start_cols), 0)
    expected["baselinePastasStartMinDroughtNSE"] = printed_number(min(start_vals))
    expected["baselinePastasStartMaxDroughtNSE"] = printed_number(max(start_vals))
    expected["baselinePastasWellRangeMedian"] = printed_number(float(trainobs["per-well range, median"]))

    wells = pd.read_parquet(DS / "wells.parquet")
    well_clusters = clusters(wells)
    sim_runs = [
        run for run, _ in baseline_report.SIM
        if run != baseline_report.REFERENCE and (RESULTS / run / "metrics_per_well.csv").exists()
    ]
    ref_path = RESULTS / baseline_report.REFERENCE / "metrics_per_well.csv"
    sig_nse = _cluster_holm("NSE", ref_path, sim_runs, well_clusters)
    sig_skill = _cluster_holm("skill", ref_path, sim_runs, well_clusters)
    # Spot-check against paired() to confirm exact equivalence with significance_table().
    mb = pd.read_csv(ref_path)
    ens_paired_nse = paired(pd.read_csv(RESULTS / "ensemble_sim" / "metrics_per_well.csv"),
                            mb, wells, split="test_drought", metric="NSE")
    assert math.isclose(sig_nse.at["ensemble_sim", "median_diff"], ens_paired_nse["median_diff"])
    assert math.isclose(sig_nse.at["ensemble_sim", "p_cluster"], ens_paired_nse["p_cluster"])
    assert sig_nse.at["ensemble_sim", "n_clusters"] == ens_paired_nse["n_clusters"]

    expected["baselineClusterCount"] = printed_number(int(sig_nse.at["ensemble_sim", "n_clusters"]), 0)
    expected["baselineEnsembleDiffDroughtNSE"] = printed_number(
        sig_nse.at["ensemble_sim", "median_diff"], signed=True
    )
    expected["baselineEnsemblePHolmDroughtNSE"] = printed_number(
        sig_nse.at["ensemble_sim", "p_holm"], 3
    )
    expected["baselineEnsemblePHolmDroughtSkill"] = printed_number(
        sig_skill.at["ensemble_sim", "p_holm"], 3
    )
    expected["baselineDistanceSTGNNPHolmDroughtSkill"] = printed_number(
        sig_skill.at["stgnn_tuned", "p_holm"], 3
    )

    per_start = [_cluster_holm("NSE", d / "metrics_per_well.csv", sim_runs, well_clusters)
                 for d in start_runs(f"{PASTAS_BASE}_trainobs")]
    rob = pd.concat(per_start).groupby(level=0).agg(
        p_holm_max=("p_holm", "max"),
        pass_count=("p_holm", lambda p: int((p < 0.05).sum())),
    )
    expected["baselineEnsembleStartsPass"] = printed_number(int(rob.at["ensemble_sim", "pass_count"]), 0)
    expected["baselineEnsembleStartsMaxPHolm"] = printed_number(float(rob.at["ensemble_sim", "p_holm_max"]), 3)
    tuned_single_runs = [f"{m}_tuned" for m, _ in baseline_report.REGIME_MODELS]
    single_passes = [int(rob.at[run, "pass_count"]) for run in tuned_single_runs]
    expected["baselineSingleStartsPassMin"] = printed_number(min(single_passes), 0)
    expected["baselineSingleStartsPassMax"] = printed_number(max(single_passes), 0)

    reg = regimes_table()
    r2 = reg.loc[reg["regime"] == "R2 left-out monitored wells (5 folds)"]
    r3 = reg.loc[reg["regime"].isin(["R3 50 % of the training period", "R3 25 % of the training period"])]
    for tag, subset in (("Two", r2), ("Three", r3)):
        for metric, suffix in (("NSE drought", "NSE"), ("skill drought", "Skill")):
            expected[f"baselineRegime{tag}MinDrought{suffix}"] = printed_number(float(subset[metric].min()))
            expected[f"baselineRegime{tag}MaxDrought{suffix}"] = printed_number(float(subset[metric].max()))

    entries = [line for line in text.splitlines() if not line.startswith("%")]
    pairs = re.findall(r"^\\newcommand\{\\([A-Za-z]+)\}\{(.+)\} % .+$", text, re.MULTILINE)
    assert len(entries) == len(pairs) == len(expected)
    assert dict(pairs) == expected, (dict(pairs), expected)
    print(f"  All {len(pairs)} commands match their v4 sources, including both Chronos-2 winners.")
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
