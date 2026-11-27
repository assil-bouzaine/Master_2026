"""Checks of France → Tunisia reuse accounting (docs/v5_plan.md, R2.4).

    PFE_DATASET=v5 python -m tests.test_reuse_report

Small files make the expected counts independent of the changing ontology. The real
files check complete classification and repeatable Markdown without fixing their counts.
"""
import csv
import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from unittest.mock import patch

import rdflib
from rdflib import BNode, Literal, Namespace
from rdflib.namespace import RDF, SH

from src.kg import reuse_report as R

L = Namespace(R.L)
EX = Namespace("urn:reuse-test:")
PREFIXES = '''
@prefix lulcw: <https://w3id.org/lulcw#> .
@prefix ex: <urn:reuse-test:> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
'''
SHAPES = PREFIXES + '''
ex:Blocked a sh:NodeShape ; sh:sparql [ sh:select """
    SELECT $this WHERE { $this lulcw:french ?value . }
""" ] .
ex:Clean a sh:NodeShape ; sh:targetClass lulcw:Class ;
    sh:property [ sh:path [ sh:inversePath lulcw:link ] ] ;
    lulcw:note "Nested property paths must be visited." .
'''
RULES = PREFIXES + '''
ex:RuleShape a sh:NodeShape ; sh:rule ex:Body .
ex:Body a sh:SPARQLRule ; sh:construct """
    CONSTRUCT { ?s a <https://w3id.org/lulcw#Class> . }
    WHERE { ?s lulcw:link ?o . }
""" .
ex:NotARule a sh:NodeShape ; sh:targetClass lulcw:Class .
'''
TERM_ROWS = (
    ("Class", "class", "core", "4"),
    ("link", "object property", "hydro", "5"),
    ("french", "datatype property", "profile/fr", "1"),
    ("note", "annotation property", "core", "5"),
    ("Tunisian", "individual", "profile/tn", "3"),
    ("EU", "concept scheme", "profile/eu", "3"),
)


def fixture(directory):
    """Write a tiny versioned ontology and its audit inputs, without a graph release."""
    root = Path(directory)
    assignment = root / "assignment.csv"
    with assignment.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("term", "kind", "module", "rule"))
        writer.writerows(TERM_ROWS)
        writer.writerow(("term", "kind", "module", "rule"))
    shapes, rules, ontology = (root / name for name in ("shapes.ttl", "rules.ttl", "ontology.ttl"))
    shapes.write_text(SHAPES, encoding="utf-8")
    rules.write_text(RULES, encoding="utf-8")
    ontology.write_text('''
@prefix owl: <http://www.w3.org/2002/07/owl#> .
<urn:reuse-test:ontology> a owl:Ontology ; owl:versionInfo "fixture-1" .
''', encoding="utf-8")
    queries = root / "cq"
    queries.mkdir()
    (queries / "clean.rq").write_text("ASK { ?s a lulcw:Class . }", encoding="utf-8")
    (queries / "blocked.rq").write_text(
        "SELECT ?s WHERE { ?s ?p <https://w3id.org/lulcw#EU> . }", encoding="utf-8")
    return {"assignment_path": assignment, "shapes_path": shapes, "rules_path": rules,
            "query_dir": queries, "ontology_path": ontology}


def test_fixture():
    with TemporaryDirectory() as directory:
        paths = fixture(directory)
        result = R.audit(**paths)
        assert result["version"] == "fixture-1" and not result["errors"]
        total = result["static"]["total"]
        assert total == {"total": 6, "reusable": 4, "percent": 100 * 4 / 6, "country_bound": 2}
        assert set(result["static"]) == set(R.KINDS) | {"total"}
        for _, kind, module, _ in TERM_ROWS:
            row = result["static"][kind]
            assert row["total"] == 1
            assert row["reusable"] == (0 if module in R.COUNTRY_BOUND else 1)
            assert row["percent"] == (0.0 if module in R.COUNTRY_BOUND else 100.0)
        for category, (n, reused, pct) in {
                "shapes": (2, 1, 50.0), "rules": (1, 1, 100.0), "queries": (2, 1, 50.0)}.items():
            assert result["summary"][category] == R.counts(n, reused)
            assert result["summary"][category]["percent"] == pct
        rows = {row["name"]: row for row in result["artefacts"]}
        assert rows[str(EX.Blocked)]["terms"] == ["french"]
        assert rows[str(EX.Blocked)]["blocked"] == ["french"]
        assert rows[str(EX.Clean)]["terms"] == ["Class", "link", "note"]
        assert rows[str(EX.RuleShape)]["terms"] == ["Class", "link"]
        assert rows["blocked.rq"]["blocked"] == ["EU"]
        output = R.report(result)
        assert "| total | 6 | 4 | 66.67% | 2 | 33.33% |" in output
        assert "graph does not exist yet" in output and "None." in output
        assert "queries: `blocked.rq`" in output and "urn:reuse-test:Blocked" in output
    print("  1. six kinds, EU/France blockers, nested paths, SPARQL strings and exact shares pass")


def test_traversal():
    with TemporaryDirectory() as directory:
        paths = fixture(directory)
        assignment = R.read_assignment(paths["assignment_path"])
        graph = rdflib.Graph().parse(data=RULES, format="turtle")
        graph.add((EX.Body, SH.ask, Literal("ASK { ?s <https://w3id.org/lulcw#french> ?v }")))
        rows = R.artefacts(assignment, rdflib.Graph(), graph, [])
        assert len(rows) == 1 and rows[0]["blocked"] == ["french"]
        # TripleRules, RDF lists, shared nodes and cycles are reached without looping.
        child = BNode()
        graph.add((EX.RuleShape, SH.rule, child))
        graph.add((child, SH.object, L.EU))
        graph.add((child, SH.condition, child))
        assert R.shape_terms(graph, EX.RuleShape) == {"Class", "link", "french", "EU"}
        assert R.sparql_terms("PREFIX lulcw: <https://w3id.org/lulcw#> "
                              "lulcw:Class. lulcw:link/lulcw:french lulcw:Tunisian") == {
                                  "Class", "link", "french", "Tunisian"}
        anonymous = PREFIXES + "[] a sh:NodeShape ; sh:targetClass lulcw:Class ."
        first = R.artefacts(assignment, rdflib.Graph().parse(data=anonymous, format="turtle"),
                            rdflib.Graph(), [])
        second = R.artefacts(assignment, rdflib.Graph().parse(data=anonymous, format="turtle"),
                             rdflib.Graph(), [])
        assert first == second and first[0]["reusable"]
    print("  2. named rules, construct/ask, full IRIs, cycles and anonymous shapes pass")


def check_cli(result, output, arguments, expected_status):
    """Exercise CLI exit handling while keeping the fixture report in its temporary folder."""
    stdout, stderr = io.StringIO(), io.StringIO()
    original_write = R.write_report
    with (patch.object(R, "audit", return_value=result) as audit,
          patch.object(R, "write_report", side_effect=lambda value: original_write(value, output)),
          patch.object(R.sys, "argv", ["reuse_report", *arguments]),
          redirect_stdout(stdout), redirect_stderr(stderr)):
        try:
            R.main()
        except SystemExit as error:
            status = error.code
        else:
            status = 0
    assert status == expected_status
    assert output.read_text(encoding="utf-8") == R.report(result)
    assert "terms available unchanged" in stdout.getvalue()
    for error in result["errors"]:
        assert error in stderr.getvalue()
    return audit.call_args.kwargs


def test_missing_terms():
    with TemporaryDirectory() as directory:
        paths = fixture(directory)
        missing = paths["query_dir"] / "missing.rq"
        missing.write_text("ASK { ?s lulcw:Missing <https://w3id.org/lulcw#OtherMissing> }",
                           encoding="utf-8")
        result = R.audit(**paths)
        assert len(result["errors"]) == 2
        row = next(row for row in result["artefacts"] if row["name"] == "missing.rq")
        assert row["missing"] == ["Missing", "OtherMissing"] and not row["reusable"]
        assert "absent from assignment.csv" in R.report(result)
        check_cli(result, Path(directory) / "report.md", [], 1)
        graph = rdflib.Graph().parse(data=SHAPES, format="turtle")
        graph.add((EX.Clean, SH.targetClass, L.UnknownClass))
        rows = R.artefacts(result["assignment"], graph, rdflib.Graph(), [])
        assert next(row for row in rows if row["name"] == str(EX.Clean))["missing"] == ["UnknownClass"]
    print("  3. unassigned triple and SPARQL terms are reported; CLI writes errors and exits 1")


def test_used_reuse():
    with TemporaryDirectory() as directory:
        paths = fixture(directory)
        assignment = R.read_assignment(paths["assignment_path"])
        graph = rdflib.Graph()
        graph.add((L.Class, L.link, L.Tunisian))
        graph.add((EX.well, RDF.type, L.Class))
        graph.add((EX.well, L.french, Literal("code")))
        # Text resembling a term is not an IRI used by a KG.
        graph.add((EX.well, EX.comment, Literal("lulcw:NotAnIRI")))
        used = R.used_reuse(graph, assignment)
        assert used["total"] == 4
        assert used["groups"] == {"core": ["Class", "link"], "profile/tn": ["Tunisian"],
                                  "country-bound": ["french"], "unknown": []}
        assert used["percentages"] == {"core": 50.0, "profile/tn": 25.0,
                                       "country-bound": 25.0, "unknown": 0.0}
        assert used["errors"] == ["Country-bound term used by Tunisian graph: lulcw:french"]
        kg = Path(directory) / "tn.ttl"
        graph.serialize(kg, format="turtle")
        result = R.audit(**paths, kg_path=kg)
        assert result["used"] == used and result["errors"] == used["errors"]
        assert "| core | 2 | 50.00% |" in R.report(result)
        kwargs = check_cli(result, Path(directory) / "used.md", ["--kg", str(kg)], 1)
        assert kwargs == {"kg_path": kg}
        graph.add((EX.well, EX.unknown, L.Undeclared))
        assert R.used_reuse(graph, assignment)["groups"]["unknown"] == ["Undeclared"]
        empty = R.used_reuse(rdflib.Graph(), assignment)
        assert empty["total"] == 0 and not empty["errors"]
        assert set(empty["percentages"].values()) == {0.0}
        clean = R.audit(**paths)
        check_cli(clean, Path(directory) / "clean.md", [], 0)
    print("  4. used reuse counts unique IRIs in every position, flags errors, and handles --kg")


def test_real_files():
    result = R.audit()
    assert not result["errors"], result["errors"]
    with R.ASSIGNMENT.open(encoding="utf-8", newline="") as handle:
        expected_total = sum(row["kind"] != "kind" for row in csv.DictReader(handle))
    assert result["static"]["total"]["total"] == expected_total
    shapes = rdflib.Graph().parse(R.ONTO / "shapes" / "lulcw-shapes.ttl")
    rules = rdflib.Graph().parse(R.ONTO / "rules" / "lulcw-rules.ttl")
    expected = {
        "shapes": {str(s) for s in shapes.subjects(RDF.type, SH.NodeShape)},
        "rules": {str(s) for s in rules.subjects(RDF.type, SH.NodeShape)
                  if any(rules.objects(s, SH.rule))},
        "queries": {p.name for p in (R.ROOT / "tests" / "cq").glob("*.rq")},
    }
    for category, names in expected.items():
        rows = [row for row in result["artefacts"] if row["category"] == category]
        assert {row["name"] for row in rows} == names and len(rows) == len(names)
        assert result["summary"][category]["total"] == len(names)
        assert all(row["reusable"] == (not row["blocked"] and not row["missing"]) for row in rows)
    with TemporaryDirectory() as directory:
        output = Path(directory) / "reuse.md"
        R.write_report(result, output)
        first = output.read_bytes()
        R.write_report(R.audit(), output)
        assert first == output.read_bytes()
    print(f"  5. real files: {expected_total} terms, all artefacts classified, identical report bytes twice")


if __name__ == "__main__":
    started = perf_counter()
    test_fixture()
    test_traversal()
    test_missing_terms()
    test_used_reuse()
    test_real_files()
    print(f"test_reuse_report: all checks passed ({perf_counter() - started:.2f}s)")
