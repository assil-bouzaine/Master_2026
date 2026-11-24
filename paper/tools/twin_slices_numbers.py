"""Write the paper's twin slice, RQ2 and slice F macros from saved world scores.

Use the twin report's scoring and summaries for analysis plan §14 items 19,
22 and 23. Each macro records where its value came from so the paper can use
these results without retyping numbers.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python paper/tools/twin_slices_numbers.py
"""
import argparse
from math import isfinite
from pathlib import Path
import re
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.analysis import twin_report as report
from src.config import ROOT

TABLES_OUT = ROOT / "paper" / "tables"
FILENAME = "twin_slices_numbers.tex"
COMMAND = "PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python paper/tools/twin_slices_numbers.py"
PROTOCOLS = dict(zip(("Free", "Pooled"), report.PROTOCOLS, strict=True))
SLICES = {
    "G": "e0.1_u0.3_p0.3_n0.25_rec_G",
    "I": "e0.1_u0.3_p0.3_n0.25_rec_I",
    "O": "e0.1_u0.3_p0.3_n0.25_rec_O",
    "S": "e0.1_u0.3_p0.3_n0.25_rec_S",
    "Ind": "e0.1_u0.3_p0.3_n0.25_ind_base",
    "PLow": "e0.1_u0.3_p0.1_n0.25_rec_base",
    "PHigh": "e0.1_u0.3_p0.5_n0.25_rec_base",
    "Noise": "e0.1_u0.3_p0.3_n1_rec_base",
}
SLICES_RUN = "twin_slices"
RQ2_RUN = "twin_rq2"
F_RUN = "twin_shortcut"
F_CELL = "e0.1_u0.3_p0.3_n0.25_rec_F2"
PILOT_CELL = "e0.1_u0.3_p0.3_n0.25_rec_F1"
BASE_CELL = report.BASE_CELL
DC, TC = "log_rmse_D_over_C", "log_rmse_T_over_C"
PUMP_D, PUMP_C = "recovery_pumping_D", "recovery_pumping_C"


def world_source(run, cell):
    directory = report.RESULTS / run / cell
    if directory.is_relative_to(ROOT):
        directory = directory.relative_to(ROOT)
    return f"{directory}/world_*.json"


def fit_source(run, cell, setting):
    return f"{world_source(run, cell)}:fits[{setting}]"


def report_rows(table):
    """Read fields from a single table returned by a live twin report helper."""
    header, _, *rows = (line.strip("|").split("|") for line in table.splitlines() if line.startswith("|"))
    columns = [name.strip() for name in header]
    return [dict(zip(columns, (value.strip() for value in row), strict=True)) for row in rows]


def count_pair(value):
    """Read k of n, with the optional percent or detection note after it."""
    match = re.fullmatch(r"(\d+) of (\d+)(?: \(.+\))?", value)
    if not match:
        raise ValueError(f"Expected a count of evaluable worlds, got {value!r}")
    return tuple(map(int, match.groups()))


def cell_median(rows, column):
    value = report._q(rows[column], 0.5)
    if not isfinite(value):
        raise ValueError(f"No finite median for {column}")
    return value


def add_slices(add, worlds, tau):
    rates = report_rows(report.test2_rates(worlds, tau, arms=("D",)))
    cells = worlds.groupby(["setting", "cell"])
    for protocol, setting in PROTOCOLS.items():
        dc_medians, wrong_total, worlds_total = {}, 0, 0
        for label, cell in SLICES.items():
            rows = cells.get_group((setting, cell))
            fit = fit_source(SLICES_RUN, cell, setting)
            macro = f"twinSlice{label}"
            dc = dc_medians[cell] = cell_median(rows, DC)
            for ratio, column, median in (("DC", DC, dc), ("TC", TC, cell_median(rows, TC))):
                add(f"{macro}{ratio}{protocol}", f"{median:+.3f}", f"{fit}:{column}, median (twin_report._q)")

            flags = rows[["wrong_reasons_D", "wrong_reasons_C"]].dropna()
            wrong_d, n = count_pair(report.count(flags["wrong_reasons_D"], share=False))
            wrong_c, _ = count_pair(report.count(flags["wrong_reasons_C"], share=False))
            for arm, wrong in (("D", wrong_d), ("C", wrong_c)):
                add(f"{macro}Wrong{arm}{protocol}", wrong, f"{fit}:arm {arm} score 6 count (twin_report.load, count)")
            add(f"{macro}Worlds{protocol}", n, f"{fit}:worlds with both score 6 flags (twin_report.load, count)")
            wrong_total += wrong_d
            worlds_total += n

            pump = rows[[PUMP_D, PUMP_C]].dropna()
            right = report.count(pump[PUMP_D].lt(pump[PUMP_C]))
            share = re.search(r" \((\d+)%\)$", right)
            if not share:
                raise ValueError(f"No paired pumping scores for {cell}, {setting}")
            add(f"{macro}RightPump{protocol}", share[1], f"{fit}:{PUMP_D} < {PUMP_C} (twin_report.count)")

        for bound, select in (("Min", min), ("Max", max)):
            cell = select(dc_medians, key=dc_medians.get)
            fit = fit_source(SLICES_RUN, cell, setting)
            add(f"twinSliceDC{bound}{protocol}", f"{dc_medians[cell]:+.3f}",
                f"{fit}:{DC}, {bound.lower()} of the eight slice medians (twin_report._q)")
        fit = fit_source(SLICES_RUN, "<eight slice cells>", setting)
        add(f"twinSliceWrongDTotal{protocol}", wrong_total, f"{fit}:sum of arm D score 6 counts (twin_report.load, count)")
        add(f"twinSliceWorldsTotal{protocol}", worlds_total, f"{fit}:sum of worlds with both score 6 flags (twin_report.load, count)")

        threshold = fit_source(report.GRID_RUN, "<grid cells>", setting)
        add(f"twinTauD{protocol}", f"{tau['D', setting][0]:.3f}",
            f"{threshold}:seed_disagreement_pumping_D (twin_report.seed_thresholds)")
        rows = [row for row in rates if row["setting"] == setting and row["cell"] in SLICES.values()]
        if len(rows) != len(SLICES):
            raise ValueError(f"Missing Test 2 results for {SLICES_RUN}, {setting}")
        k, n = map(sum, zip(*(count_pair(row["false alarms"]) for row in rows)))
        add(f"twinSliceFalseAlarmDK{protocol}", k, f"{fit}:sum of arm D false alarms (twin_report.test2_rates)")
        add(f"twinSliceFalseAlarmDN{protocol}", n, f"{fit}:sum of arm D negative worlds (twin_report.test2_rates)")
        add(f"twinSlicePositiveD{protocol}", sum(int(row["wrong reasons"]) > 0 for row in rows),
            f"{fit}:cells with positive cases for arm D (twin_report.test2_rates)")


def add_rq2(add, worlds):
    cells = worlds.groupby(["setting", "cell"])
    for label, setting in (("Hard", "free"), ("None", "free_none"), ("Soft", "free_soft1")):
        for metric, column, fmt in (("Viol", "violation_rate_D", ".0%"),
                                    ("CutSign", "intervention_well_sign_D", ".0%"),
                                    ("DT", "log_rmse_D_over_T", "+.3f")):
            medians = {cell: cell_median(cells.get_group((setting, cell)), column)
                       for cell in (BASE_CELL, *SLICES.values())}
            for bound, select in (("Min", min), ("Max", max)):
                cell = select(medians, key=medians.get)
                add(f"twinRQTwo{metric}{label}{bound}", format(medians[cell], fmt).removesuffix("%"),
                    f"{fit_source(RQ2_RUN, cell, setting)}:{column}, {bound.lower()} of nine cell medians (twin_report._q)")
            add(f"twinRQTwoBase{metric}{label}", format(medians[BASE_CELL], fmt).removesuffix("%"),
                f"{fit_source(RQ2_RUN, BASE_CELL, setting)}:{column}, base median (twin_report._q)")


def add_f(add, worlds, tau):
    main = worlds.loc[worlds["run"].eq(F_RUN) & worlds["cell"].eq(F_CELL)]
    pilot = worlds.loc[worlds["run"].eq(report.SHORTCUT_PILOT) & worlds["cell"].eq(PILOT_CELL)]
    pilot_choice = report._shortcut_pilot(pilot)
    for label, run, cell, rows, arms in (("F", F_RUN, F_CELL, main, report.ARMS),
                                         ("FPilot", report.SHORTCUT_PILOT, PILOT_CELL, pilot, ("D",))):
        variant, = rows["dial_variant"].unique()
        phi = f"{float(variant.removeprefix('F')):.1f}"
        source = world_source(run, cell)
        if label == "F" and not pilot_choice.endswith(f"φ = {phi}."):
            raise ValueError(f"The main F variant does not match the pilot decision: {pilot_choice}")
        add(f"twin{label}Phi", phi, f"{source}:dials.variant, both protocols (twin_report.load)")
        scores = {(row["protocol"], row["arm"]): row for row in report_rows(report._shortcut_scores(rows))}
        add(f"twin{label}Worlds", scores[PROTOCOLS["Free"], "D"]["worlds"],
            f"{fit_source(run, cell, PROTOCOLS['Free'])}:world count (twin_report._shortcut_scores)")
        for protocol, setting in PROTOCOLS.items():
            for arm in arms:
                k, _ = count_pair(scores[setting, arm]["score 6"])
                add(f"twin{label}Wrong{arm}{protocol}", k,
                    f"{fit_source(run, cell, setting)}:arm {arm} score 6 (twin_report._shortcut_scores)")

    # Realised fields belong to the generator and are shared by the two fits.
    free = main.loc[main["setting"].eq(PROTOCOLS["Free"])]
    for suffix, column, fmt in (("FarShare", "real_far_explained_median_core", ".0%"),
                                ("FarCorr", "real_far_local_pumping_corr_median_core", ".2f")):
        source = f"{world_source(F_RUN, F_CELL)}:realised.{column.removeprefix('real_')}"
        add(f"twinF{suffix}", format(cell_median(free, column), fmt).removesuffix("%"),
            f"{source}, median over free rows (twin_report._q)")

    comparisons = {row["protocol"]: row for row in report_rows(report._shortcut_comparison(main, worlds))}
    rates = {row["setting"]: row for row in report_rows(report.test2_rates(main, tau, arms=("D",)))}
    for protocol, setting in PROTOCOLS.items():
        fit = fit_source(F_RUN, F_CELL, setting)
        base = fit_source(report.GRID_RUN, BASE_CELL, setting)
        paired = f"{fit} and {base}, paired seeds (twin_report._shortcut_comparison)"
        add(f"twinFPumpChangeD{protocol}", comparisons[setting]["change in pumping recovery error"], f"{paired}:{PUMP_D}")
        add(f"twinFNSEChangeD{protocol}", comparisons[setting]["change in drought NSE"], f"{paired}:nse_drought_D")

        rate = rates[setting]
        detection = (0, 0) if rate["detection"] == "no positive case" else count_pair(rate["detection"])
        for name, pair in (("Detect", detection), ("False", count_pair(rate["false alarms"]))):
            for part, value in zip(("K", "N"), pair, strict=True):
                add(f"twinFTestTwo{name}{part}{protocol}", value,
                    f"{fit}:arm D {name.lower()} {part.lower()} (twin_report.test2_rates)")


def write_numbers(tables_out):
    worlds = report.load([SLICES_RUN, RQ2_RUN, F_RUN, report.SHORTCUT_PILOT, report.GRID_RUN])
    tau = report.seed_thresholds(worlds, arms=("D",))
    lines = [f"% Generated by {COMMAND}"]

    def add(name, value, source):
        lines.append(rf"\newcommand{{\{name}}}{{{value}}} % {source}")

    add_slices(add, worlds.loc[worlds["run"].eq(SLICES_RUN)], tau)
    add_rq2(add, worlds.loc[worlds["run"].eq(RQ2_RUN)])
    add_f(add, worlds, tau)
    tables_out.mkdir(parents=True, exist_ok=True)
    path = tables_out / FILENAME
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tables-out", type=Path, default=TABLES_OUT, help=f"directory for {FILENAME}")
    args = parser.parse_args()
    print(f"-> {write_numbers(args.tables_out)}")


if __name__ == "__main__":
    main()
