"""Check the paper's data tables against saved inputs (analysis plan sections 2 to 4).

Run the real CLI twice in temporary folders, parse every printed number and
date, and check the source files independently. Also check calendar weeks,
LaTeX structure and command names shared with the KG paper tables. No data
is rebuilt and no model is fitted.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_data_tables
"""
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_EVEN
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

import pandas as pd

from paper.tools import data_tables as tables
from src.config import TEST_PERIODS
from src.models.features import NEAR_CANDIDATES, RIVERS

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data/processed/dataset_v4"
SCRATCH = ROOT / "results/_agents/tmp/T20"
FILES = ("data_sources.tex", "data_periods.tex", "data_numbers.tex")
DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
LABELS = {"warmup": "Warm-up", "train": "Train", "validation": "Validation", "test": "Test",
          "drought": "Test: drought", "recovery": "Test: recovery"}


def _read_data():
    data = {name: pd.read_parquet(DATASET / (name + ".parquet")) for name in (
        "wells", "heads_weekly", "forcing_weekly", "pumping_points", "pumping_weekly", "gauges", "rivers_weekly")}
    data |= {name: json.loads((DATASET / (name + ".json")).read_text(encoding="utf-8"))
             for name in ("meta", "splits")}
    data["kg"] = json.loads((ROOT / "data/processed/kg/lulcw_kg_v4_summary.json").read_text(encoding="utf-8"))
    data["rpg_files"] = sorted((ROOT / "data/interim").glob("rpg_dept_[0-9][0-9][0-9][0-9].parquet"))
    return data


def _numbers(text):
    return [Decimal(value) for value in re.findall(r"\\num\{([^{}]*)\}", text)]


def _rows(text):
    return [line.removesuffix(r" \\").split(" & ") for line in text.splitlines()
            if " & " in line and r"\num{" in line]


def _dates(frame, variable=None):
    available = frame[frame[variable].notna()] if variable else frame
    return [available["week"].min().date().isoformat(), available["week"].max().date().isoformat()]


def _sundays(first, last):
    """Use date arithmetic rather than the generator's pandas calendar construction."""
    first, last = date.fromisoformat(first), date.fromisoformat(last)
    sunday = first + timedelta(days=(6 - first.weekday()) % 7)
    return 0 if sunday > last else (last - sunday).days // 7 + 1


def _period_bounds(data):
    splits = data["splits"]
    bounds = {"warmup": [splits["forcing_start"],
                         (date.fromisoformat(splits["model_start"]) - timedelta(days=1)).isoformat()]}
    bounds |= {name: splits[name] for name in ("train", "validation", "test")}
    for name in ("drought", "recovery"):
        first, last = TEST_PERIODS["test_" + name]
        bounds[name] = [max(first, splits["test"][0]),
                        min(last or data["meta"]["last_week"], splits["test"][1], data["meta"]["last_week"])]
    assert splits["week_rule"] == "W-SUN"
    return bounds


def _used_rivers(data):
    used = set(RIVERS.values()) | set(NEAR_CANDIDATES)
    return used, data["rivers_weekly"][data["rivers_weekly"]["code_station"].isin(used)]


def _imputed_percent(pumping):
    numerator = Decimal(int(pumping["imputed"].sum()))
    return (100 * numerator / Decimal(len(pumping))).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


def _check_sources(text, data):
    wells, forcing, points, pumping = (data[name] for name in (
        "wells", "forcing_weekly", "pumping_points", "pumping_weekly"))
    groups = {group: len(set(frame["code_bss"])) for group, frame in wells.groupby("group")}
    group_order = sorted(groups, key=lambda group: (-groups[group], group))
    used, rivers = _used_rivers(data)
    years = sorted(int(path.stem.rsplit("_", 1)[1]) for path in data["rpg_files"])
    want = {
        "Groundwater heads": [wells["code_bss"].nunique(), wells.loc[wells["core"], "code_bss"].nunique(),
                              *(groups[group] for group in group_order)],
        "Weather": [forcing["cell_id"].nunique()],
        "Abstraction": [points.loc[points["source"] == "groundwater", "code_ouvrage"].nunique(),
                        points.loc[points["source"] == "surface", "code_ouvrage"].nunique(),
                        pumping.loc[~pumping["imputed"], "week"].dt.year.min(), data["meta"]["last_bnpe_year"],
                        pumping.loc[~pumping["imputed"], "week"].dt.year.min(),
                        data["meta"]["last_bnpe_year"]],
        "Rivers": [len(used), data["gauges"]["code_station"].nunique()],
        "Hydrogeology": [data["kg"]["polygons"], data["kg"]["instances_by_class"]["HydrogeologicalUnit"]],
        "Land use": [len(data["rpg_files"]), *years],
    }
    providers = {"Groundwater heads": "Hub'Eau piezometers", "Weather": "Météo-France; SAFRAN / SIM2",
                 "Abstraction": "Hub'Eau; BNPE", "Rivers": "Hub'Eau hydrometrie", "Hydrogeology": "BD LISA",
                 "Land use": "IGN; RPG"}
    wanted_dates = {"Groundwater heads": _dates(data["heads_weekly"], "head"), "Weather": _dates(forcing),
                    "Abstraction": _dates(pumping), "Rivers": _dates(rivers, "q_m3s"),
                    "Hydrogeology": [], "Land use": []}
    rows = _rows(text)
    assert [cells[0] for cells in rows] == list(want)
    expected_numbers = []
    for cells in rows:
        family = cells[0]
        assert len(cells) == 5 and cells[1] == providers[family], cells
        expected = [Decimal(str(value)) for value in want[family]]
        assert _numbers(" & ".join(cells)) == expected, (family, cells, expected)
        assert DATE.findall(cells[4]) == wanted_dates[family], (family, cells[4], wanted_dates[family])
        expected_numbers.extend(expected)
    by_family = {cells[0]: cells for cells in rows}
    for group in groups:
        assert f"{group} \\num{{{groups[group]}}}" in by_family["Groundwater heads"][2]
    variables = [column for column in forcing.columns if column not in ("cell_id", "week")]
    assert re.findall(r"\\texttt\{([^{}]+)\}", by_family["Weather"][2]) == variables
    assert re.findall(r"\\texttt\{([^{}]+)\}", by_family["Rivers"][2]) == sorted(used)
    for usage in pumping["usage"].unique():
        assert usage in by_family["Abstraction"][2]
    assert "are filled and marked as imputed" in by_family["Abstraction"][2]
    for family in ("Groundwater heads", "Weather", "Rivers"):
        assert by_family[family][3] == "Weekly"
    assert by_family["Abstraction"][3] == "Annual declarations spread to weeks"
    assert by_family["Hydrogeology"][3:] == ["Static", "—"]
    assert by_family["Land use"][3] == "Annual"
    assert "restriction" not in text.lower()
    assert _numbers(text) == expected_numbers
    assert r"\label{tab:data-sources}" in text
    print(f"  1. sources: {len(rows)} data families, {len(expected_numbers)} numbers from their sources, "
          "all observed date ranges, groups, variables, uses, model gauges and RPG editions")


def _check_periods(text, data):
    bounds = _period_bounds(data)
    rows = _rows(text)
    assert len(rows) == len(bounds) + 1
    expected_numbers = []
    for (name, (first, last)), cells in zip(bounds.items(), rows[:-1]):
        assert len(cells) == 5 and cells[0] == LABELS[name]
        assert cells[1:3] == [first, last], (name, cells)
        wanted = Decimal(_sundays(first, last))
        assert _numbers(" & ".join(cells)) == [wanted], (name, cells, wanted)
        expected_numbers.append(wanted)
    folds, distance = data["splits"]["leave_wells_out"]["n_folds"], data["meta"]["config"]["fold_link_m"]
    assert rows[-1][:3] == ["Leave-wells-out", "—", "—"]
    assert _numbers(" & ".join(rows[-1])) == [folds, distance]
    expected_numbers += [Decimal(folds), Decimal(distance)]
    assert _numbers(text) == expected_numbers
    assert (_sundays(*bounds["drought"]) + _sundays(*bounds["recovery"])) == _sundays(*bounds["test"])
    assert sum(_sundays(*bounds[name]) for name in ("train", "validation", "test")) == _sundays(
        bounds["train"][0], bounds["test"][1])
    assert r"\label{tab:periods}" in text
    print("  2. periods: all six boundary pairs match splits/TEST_PERIODS/last_week; independent Sunday counts "
          + ", ".join(f"{name} {_sundays(*limits)}" for name, limits in bounds.items())
          + f"; {folds} folds and {distance} m grouping distance")


def _check_macros(text, data):
    wells, points, pumping, forcing = (data[name] for name in (
        "wells", "pumping_points", "pumping_weekly", "forcing_weekly"))
    used, rivers = _used_rivers(data)
    years = [int(path.stem.rsplit("_", 1)[1]) for path in data["rpg_files"]]
    want = {
        "nDataWells": wells["code_bss"].nunique(), "nDataCoreWells": wells.loc[wells["core"], "code_bss"].nunique(),
        "nDataWeatherCells": forcing["cell_id"].nunique(),
        "nDataGroundwaterPoints": points.loc[points["source"] == "groundwater", "code_ouvrage"].nunique(),
        "nDataSurfacePoints": points.loc[points["source"] == "surface", "code_ouvrage"].nunique(),
        "nDataGauges": data["gauges"]["code_station"].nunique(), "nDataGaugesUsed": len(used),
        "nDataRpgEditions": len(years), "nDataRpgFirstYear": min(years), "nDataRpgLastYear": max(years),
        "nDataFolds": data["splits"]["leave_wells_out"]["n_folds"],
        "nDataFoldLinkMetres": data["meta"]["config"]["fold_link_m"],
        "nDataPolygons": data["kg"]["polygons"], "nDataUnits": data["kg"]["instances_by_class"]["HydrogeologicalUnit"],
        "nDataFirstDeclaredYear": pumping.loc[~pumping["imputed"], "week"].dt.year.min(),
        "nDataLastDeclaredYear": data["meta"]["last_bnpe_year"],
        "nDataImputedRows": pumping["imputed"].sum(), "nDataPumpingRows": len(pumping),
        "nDataImputedPercent": _imputed_percent(pumping),
    }
    group_names = {"Pliocene multilayer": "PlioceneMultilayer", "other": "Other", "Corbières karst": "CorbieresKarst",
                   "recent alluvium": "RecentAlluvium", "ancient alluvium": "AncientAlluvium"}
    for group, frame in wells.groupby("group"):
        want["nDataGroup" + group_names[group] + "Wells"] = frame["code_bss"].nunique()
    expected_dates = {"dataLastWeek": data["meta"]["last_week"]}
    for name, limits in _period_bounds(data).items():
        want["nData" + name.capitalize() + "Weeks"] = _sundays(*limits)
        expected_dates |= {"data" + name.capitalize() + boundary: value
                           for boundary, value in zip(("Start", "End"), limits)}
    for name, frame, variable in (("Heads", data["heads_weekly"], "head"), ("Weather", forcing, None),
                                   ("Pumping", pumping, None), ("Rivers", rivers, "q_m3s")):
        expected_dates |= {"data" + name + boundary + "Week": value
                           for boundary, value in zip(("First", "Last"), _dates(frame, variable))}
    numbers = re.findall(r"^\\newcommand\{\\([A-Za-z]+)\}\{\\num\{([^{}]+)\}\} % (.+)$", text, re.MULTILINE)
    assert len(numbers) == len(want)
    assert {name: Decimal(value) for name, value, _ in numbers} == {name: Decimal(str(value)) for name, value in want.items()}
    assert _numbers(text) == [Decimal(value) for _, value, _ in numbers]
    dates = re.findall(r"^\\newcommand\{\\([A-Za-z]+)\}\{(\d{4}-\d{2}-\d{2})\} % (.+)$", text, re.MULTILINE)
    assert len(dates) == len(expected_dates) and {name: value for name, value, _ in dates} == expected_dates
    all_names = re.findall(r"\\newcommand\{\\([^{}]+)\}", text)
    assert len(set(all_names)) == len(all_names) == len(numbers) + len(dates)
    assert all(name.startswith("nData") for name, _, _ in numbers)
    assert all(name.startswith("data") for name, _, _ in dates)
    assert all(re.fullmatch("[A-Za-z]+", name) for name in all_names)
    for _, _, reference in numbers + dates:
        assert reference.startswith(("data/", "src/")) and ":" in reference or "matching edition filenames" in reference
    kg_text = (ROOT / "paper/tables/kg_numbers.tex").read_text(encoding="utf-8")
    kg_names = set(re.findall(r"\\newcommand\{\\([^{}]+)\}", kg_text))
    assert kg_names and not (set(all_names) & kg_names)
    print(f"  3. macros: all {len(numbers)} numbers and {len(dates)} dates equal their sources; "
          "letter-only data prefixes, source comments and no name shared with kg_numbers.tex")


def _check_latex(documents, data):
    for name, text in documents.items():
        first = text.splitlines()[0]
        assert first.startswith("% Generated by " + tables.COMMAND)
        for path in [*tables.SOURCES.values(), *tables.PROVIDER_FILES, *data["rpg_files"]]:
            assert path.relative_to(ROOT).as_posix() in first, (name, path)
        body = re.sub(r"(?<!\\)%[^\n]*", "", text)
        depth = 0
        for token in re.findall(r"\\.|[{}]", body):
            if token == "{":
                depth += 1
            elif token == "}":
                depth -= 1
                assert depth >= 0, name
        assert depth == 0, name
        environments = []
        for kind, environment in re.findall(r"\\(begin|end)\{([^{}]+)\}", body):
            if kind == "begin":
                environments.append(environment)
            else:
                assert environments and environments.pop() == environment, name
        assert not environments, name
        if name != "data_numbers.tex":
            for command in (r"\toprule", r"\midrule", r"\bottomrule", r"\begin{table}", r"\end{table}"):
                assert command in body, (name, command)
            assert re.search(r"\\caption\{[^\n]+\}", body)
    print("  4. LaTeX: balanced braces and environments, captions, labels, booktabs rules, "
          "and complete source/command headers")


def test_generated_tables():
    started = time.perf_counter()
    data = _read_data()
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=SCRATCH) as temporary:
        outputs = []
        for name in ("first", "second"):
            out = Path(temporary) / name
            result = subprocess.run([sys.executable, "paper/tools/data_tables.py", "--out", str(out)],
                                    cwd=ROOT, capture_output=True, text=True)
            assert result.returncode == 0, result.stdout + result.stderr
            assert {p.name for p in out.iterdir()} == set(FILES)
            outputs.append({filename: (out / filename).read_bytes() for filename in FILES})
        assert outputs[0] == outputs[1]
        documents = {name: content.decode("utf-8") for name, content in outputs[0].items()}
        _check_sources(documents["data_sources.tex"], data)
        _check_periods(documents["data_periods.tex"], data)
        _check_macros(documents["data_numbers.tex"], data)
        _check_latex(documents, data)
    print(f"  5. two CLI runs into different temporary folders produce identical bytes "
          f"({time.perf_counter() - started:.2f}s including source checks)")


def main():
    started = time.perf_counter()
    test_generated_tables()
    print(f"test_data_tables: all checks passed ({time.perf_counter() - started:.2f}s)")


if __name__ == "__main__":
    main()
