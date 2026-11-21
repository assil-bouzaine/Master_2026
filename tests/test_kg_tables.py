"""Check the paper's saved KG numbers against their sources (analysis plan section 14).

Run the actual CLI in temporary folders. Read every printed number back, check
class coverage and LaTeX structure, and compare two builds byte for byte. Small
changed copies also check that new classes and stale inventory totals are visible.
No graph is rebuilt and no model is fitted.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_kg_tables
"""
from collections import Counter
from contextlib import redirect_stderr
from copy import deepcopy
import io
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

import pandas as pd

from paper.tools import kg_tables as tables

ROOT = Path(__file__).resolve().parents[1]
KG = ROOT / "data" / "processed" / "kg"
SCRATCH = ROOT / "results" / "_agents" / "tmp" / "T18"
FILES = ("kg_instances.tex", "kg_coverage.tex", "kg_numbers.tex")
RELATIONS = ("pumping", "pumping_unattributed", "recharge", "recharge_unitwide", "river", "canal", "well_link")
EXPECTED_GROUPS = (
    ("Hydrogeology", "HydrogeologicalUnit HydrogeologicalUnitGroup MultilayerAquiferSystem "
     "GroundwaterBody AlluvialAquifer KarstAquifer ConfiningUnit ElementaryPolygon StackLayer"),
    ("Monitoring", "Piezometer MonitoringStation ObservationSeries PressureStateSummary"),
    ("Abstraction", "AbstractionFacility Intake AnnualAbstractionRecord UnitAttribution SurfaceWaterIntake "
     "CanalIntakeGroup"),
    ("Surface water", "Watercourse RiverReach ReachPiece RiverSection RiverGauge GaugePool GaugeZoneRelation "
     "SurfaceWaterBody CanalReach ReachSearchZone"),
    ("Documents", "Document DocumentPassage ExchangeStatement"),
    ("Land use and demand", "CropCode CropClass CropAreaObservation CropDemandEstimate CropDemandZone"),
    ("Weather and recharge", "WeatherCell PolygonCellIntersection OutcropSearchZone"),
    ("Provenance and rules", "SourceRecord DataRelease DerivationRule Procedure RuleExecution RuleEvaluation "
     "ConstraintDecision ExportPolicy Ontology"),
    ("Geometry, time and vocabularies", "Geometry Feature Instant ProperInterval ConceptScheme"),
)


def _json(name):
    return json.loads((KG / name).read_text(encoding="utf-8"))


def _numbers(text):
    """Refuse a non-integer count instead of silently skipping an unreadable num command."""
    return [int(value) for value in re.findall(r"\\num\{([^{}]*)\}", text)]


def _data_rows(text):
    return [line.removesuffix(r" \\").split(" & ") for line in text.splitlines()
            if " & " in line and r"\num{" in line]


def _edge_counts(frame, core):
    """Use Python sets of rows, independently of the generator's pandas summaries."""
    records = list(frame.itertuples(index=False))
    destinations = {record.dst for record in records}
    return {"wells": len(destinations), "core_wells": len(destinations & core), "edges": len(records),
            "eligible_edges": sum(record.eligible == True for record in records),
            "constrained_edges": sum(record.constrained == True for record in records),
            "distinct_sources": len({(record.src_type, record.src) for record in records})}


def _core_codes(nodes):
    return {record.code for record in nodes.itertuples(index=False)
            if record.type == "well" and record.core == True}


def _check_instances(text, facts, rules):
    classes = facts["instances_by_class"]
    seen, groups, current = [], {}, None
    expected_numbers = []
    last_rows = []
    for cells in _data_rows(text):
        assert len(cells) == 3, cells
        theme = re.fullmatch(r"\\textbf\{([^{}]+)\}", cells[0])
        if theme:
            current = theme[1]
            assert current not in groups, current
            groups[current] = []
        class_name = re.fullmatch(r"\\texttt\{([A-Za-z]+)\}", cells[1])
        if class_name:
            name = class_name[1]
            assert name in classes and current is not None, cells
            assert _numbers(cells[2]) == [classes[name]], cells
            groups[current].append(name)
            seen.append(name)
            expected_numbers.append(classes[name])
        else:
            last_rows.append(cells[1])
            value = {"Facts graph triples": facts["triples"], "Triples derived by the rules": rules["rule_triples"]}[cells[1]]
            assert _numbers(cells[2]) == [value]
            expected_numbers.append(value)
    assert Counter(seen) == Counter({name: 1 for name in classes}), Counter(seen)
    assert list(groups) == [name for name, _ in EXPECTED_GROUPS]
    for theme, names in EXPECTED_GROUPS:
        assert set(groups[theme]) == set(names.split()), theme
        assert groups[theme] == sorted(groups[theme], key=lambda name: (-classes[name], name)), theme
    assert last_rows == ["Facts graph triples", "Triples derived by the rules"]
    assert _numbers(text) == expected_numbers
    assert r"\label{tab:kg-instances}" in text
    print(f"  1. instances: all {len(classes)} classes occur once, in the requested themes and descending order; "
          f"{len(expected_numbers)} numbers equal their JSON sources")


def _check_coverage(text, edges_c, edges_d, nodes, inventory, stderr, manifest):
    core = _core_codes(nodes)
    rows = _data_rows(text)
    assert len(rows) == len(RELATIONS)
    expected_numbers, source_differences, checked = [], 0, 0
    for relation, cells in zip(RELATIONS, rows):
        assert len(cells) == 9 and cells[0] == rf"\texttt{{{relation.replace('_', r'\_')}}}", cells
        d_rows = edges_d[edges_d["relation"] == relation]
        d = _edge_counts(d_rows, core)
        keys = ("wells", "core_wells", "edges", "eligible_edges", "constrained_edges", "distinct_sources")
        wanted = [d[key] for key in keys]
        assert _numbers(" & ".join(cells[1:6])) == wanted, relation
        assert cells[1] == rf"\num{{{d['wells']}}} (\num{{{d['core_wells']}}})"
        c_rows = edges_c[edges_c["relation"] == relation]
        if c_rows.empty:
            assert cells[6:] == ["—", "—", "—"], relation
        else:
            c = _edge_counts(c_rows, core)
            assert cells[6] == rf"\num{{{c['wells']}}} (\num{{{c['core_wells']}}})"
            wanted += [c[key] for key in ("wells", "core_wells", "edges", "distinct_sources")]
        assert _numbers(" & ".join(cells)) == wanted, (relation, cells, wanted)
        expected_numbers.extend(wanted)
        saved = tables.without_dropped(inventory["totals"], manifest.get("dropped_small_cells", {})).get(relation)
        if saved is None:
            assert f"totals has no {relation}" in stderr
            continue
        for key in ("wells", "core_wells", "eligible_edges", "constrained_edges"):
            if key in saved:
                assert d[key] == saved[key], (relation, key, d[key], saved[key])
                checked += 1
            else:
                assert f"totals.{relation}.{key} is absent" in stderr
        # The inventory counts a shared source once for each well it reaches.
        per_well_sources = {}
        for record in d_rows.itertuples(index=False):
            per_well_sources.setdefault(record.dst, set()).add(record.src)
        assert saved["sources"] == sum(len(sources) for sources in per_well_sources.values()) == d["edges"]
        checked += 1
        if saved["sources"] != d["distinct_sources"]:
            assert (f"inventory totals.{relation}.sources={saved['sources']}; "
                    f"edges_D.parquet distinct_sources={d['distinct_sources']}") in stderr
            source_differences += 1
    assert _numbers(text) == expected_numbers
    assert "sums per-well source counts" in stderr and "distinct sources" in stderr
    assert r"\label{tab:arm-coverage}" in text
    print(f"  2. coverage: {len(rows)} relations, {len(expected_numbers)} numbers from edge and node rows; "
          f"{checked} inventory totals agree under their definitions; {source_differences} distinct-source "
          "differences are printed, with unavailable inventory fields identified")


def _check_macros(text, facts, rules, nodes, release):
    classes = facts["instances_by_class"]
    derived = rules["derived"]
    mechanisms = derived["influences_by_mechanism"]
    pairs = derived["influence_facility_well_pairs_by_policy"]["main"]
    want = {
        "nKgFactTriples": facts["triples"], "nKgRuleTriples": rules["rule_triples"],
        "nKgClasses": len(classes), "nKgPiezometers": classes["Piezometer"],
        "nKgFacilities": classes["AbstractionFacility"], "nKgAnnualRecords": facts["annual_records"],
        "nKgPolygons": facts["polygons"], "nKgUnits": classes["HydrogeologicalUnit"],
        "nInflPumping": mechanisms["PumpingDrawdown"], "nInflRecharge": mechanisms["DiffuseRecharge"],
        "nInflRiver": mechanisms["RiverExchange"], "nInflCanal": mechanisms["CanalReturnFlow"],
        "nInflEligible": derived["influences_by_eligibility"]["EligibleConstraint"],
        "nInflIneligible": derived["influences_by_eligibility"]["IneligibleConstraint"],
        "nDPumpPairs": pairs["pairs"], "nDPumpFacilities": pairs["facilities"], "nDPumpWells": pairs["wells"],
        "nWellLinksMain": derived["well_links_selected_by_policy"]["main"],
        "nWells": len({record.code for record in nodes.itertuples(index=False) if record.type == "well"}),
        "nCoreWells": len(_core_codes(nodes)),
    }
    commands = re.findall(r"^\\newcommand\{\\([A-Za-z]+)\}\{\\num\{(\d+)\}\} % (.+)$", text, re.MULTILINE)
    assert len(commands) == len(want) and {name: int(value) for name, value, _ in commands} == want
    assert _numbers(text) == [int(value) for _, value, _ in commands]
    for _, _, source in commands:
        path, key = source.split(":", 1)
        assert path in {p.relative_to(ROOT).as_posix() for p in tables.SOURCES.values()} and key
    date = release["released"].split("T")[0]
    assert (rf"\newcommand{{\kgRelease}}{{{date}}} % data/processed/kg/lulcw_kg_v4_release.json:released (date part)") in text
    assert len(re.findall(r"\\newcommand\{\\([A-Za-z]+)\}", text)) == len(want) + 1
    print(f"  3. macros: all {len(want)} numbers equal their sources, with source comments and letter-only names; "
          f"release date {date}")


def _check_latex(documents, release):
    for name, text in documents.items():
        first = text.splitlines()[0]
        assert first.startswith("% Generated by " + tables.COMMAND)
        assert "released: " + release["released"] in first
        assert "lulcw_kg_v4_release.json" in first
        expected_sources = {"kg_instances.tex": ("facts", "rules", "release"),
                            "kg_coverage.tex": ("C", "D", "nodes", "inventory", "release"),
                            "kg_numbers.tex": ("facts", "rules", "nodes", "release")}[name]
        for source in expected_sources:
            assert tables.SOURCES[source].relative_to(ROOT).as_posix() in first, (name, source)
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
        if name != "kg_numbers.tex":
            for command in (r"\toprule", r"\midrule", r"\bottomrule", r"\begin{table}", r"\end{table}"):
                assert command in body, (name, command)
            assert re.search(r"\\caption\{[^\n]+\}", body)
    print("  4. LaTeX: balanced braces and environments, captions, labels and booktabs rules; "
          "all provenance headers name the command, sources and release timestamp")


def test_generated_tables():
    """Exercise --out in a new process and parse all numbers, not just chosen examples."""
    started = time.perf_counter()
    facts = _json("lulcw_kg_v4_summary.json")
    rules = _json("lulcw_kg_v4_rules_summary.json")
    release = _json("lulcw_kg_v4_release.json")
    inventory = _json("inventory_v4_main.json")
    export = KG / "export_v4_main"
    edges_c, edges_d, nodes = (pd.read_parquet(export / name)
                             for name in ("edges_C.parquet", "edges_D.parquet", "nodes.parquet"))
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=SCRATCH) as temporary:
        outputs = []
        for folder in ("first", "second"):
            out = Path(temporary) / folder
            result = subprocess.run([sys.executable, "paper/tools/kg_tables.py", "--out", str(out)],
                                    cwd=ROOT, capture_output=True, text=True)
            assert result.returncode == 0, result.stdout + result.stderr
            assert {p.name for p in out.iterdir()} == set(FILES)
            outputs.append({name: (out / name).read_bytes() for name in FILES})
        assert outputs[0] == outputs[1]
        documents = {name: content.decode("utf-8") for name, content in outputs[0].items()}
        _check_instances(documents["kg_instances.tex"], facts, rules)
        _check_coverage(documents["kg_coverage.tex"], edges_c, edges_d, nodes, inventory, result.stderr,
                        json.loads((KG / "export_v4_main" / "manifest.json").read_text()))
        _check_macros(documents["kg_numbers.tex"], facts, rules, nodes, release)
        _check_latex(documents, release)
    print(f"  5. two CLI runs into different temporary folders produce identical bytes "
          f"({time.perf_counter() - started:.2f}s including source checks)")


def test_class_changes():
    facts = _json("lulcw_kg_v4_summary.json")
    rules = _json("lulcw_kg_v4_rules_summary.json")
    release = _json("lulcw_kg_v4_release.json")["released"]
    extra = deepcopy(facts)
    extra["instances_by_class"]["ExtraClass"] = max(facts["instances_by_class"].values()) + 1
    stderr = io.StringIO()
    with redirect_stderr(stderr):
        text = tables.instances_table(extra, rules, release)
    assert "WARNING" in stderr.getvalue() and "ExtraClass" in stderr.getvalue()
    assert text.count(r"\texttt{ExtraClass}") == 1
    assert text.index(r"\textbf{Other}") > text.index(r"\textbf{Geometry, time and vocabularies}")
    assert _numbers(text.split(r"\textbf{Other}")[1])[0] == extra["instances_by_class"]["ExtraClass"]
    missing = deepcopy(facts)
    del missing["instances_by_class"]["Piezometer"]
    try:
        tables.instances_table(missing, rules, release)
    except ValueError as error:
        assert "Piezometer" in str(error) and "missing" in str(error)
    else:
        raise AssertionError("A listed class missing from the facts summary must be an error")
    print("  6. changed class summaries: an extra class appears once in Other with a warning; "
          "a missing listed class raises an error")


def test_inventory_changes():
    inventory = _json("inventory_v4_main.json")
    nodes = pd.read_parquet(KG / "export_v4_main" / "nodes.parquet")
    edges = pd.read_parquet(KG / "export_v4_main" / "edges_D.parquet")
    counts = {relation: _edge_counts(group, _core_codes(nodes))
              for relation, group in edges.groupby("relation")}
    before = deepcopy(counts)
    changed = deepcopy(inventory["totals"])
    for key in ("wells", "core_wells", "sources", "eligible_edges", "constrained_edges"):
        changed["pumping"][key] += 1
    diagnostics = "\n".join(tables.inventory_diagnostics(counts, changed))
    for key in changed["pumping"]:
        if key == "wells_with_eligible":
            continue
        source_key = "distinct_sources" if key == "sources" else key
        assert (f"inventory totals.pumping.{key}={changed['pumping'][key]}; "
                f"edges_D.parquet {source_key}={counts['pumping'][source_key]}") in diagnostics
    assert (f"edges_D.parquet edges={counts['pumping']['edges']}; the per-well source sum differs too") in diagnostics
    assert counts == before
    print("  7. stale inventory copy: all five changed totals print both values, "
          "including the per-well source sum; computed edge counts stay unchanged")


def main():
    started = time.perf_counter()
    test_generated_tables()
    test_class_changes()
    test_inventory_changes()
    print(f"test_kg_tables: all checks passed ({time.perf_counter() - started:.2f}s)")


if __name__ == "__main__":
    main()
