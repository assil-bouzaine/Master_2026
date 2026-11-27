"""Measure ontology availability for Tunisia (docs/v5_plan.md, R2.4).

    PFE_DATASET=v5 python -m src.kg.reuse_report [--kg PATH]

The assignment table decides which terms are country-bound. Shapes, rule shapes and
queries are checked for those terms, including SPARQL text. This measures static
availability; it does not establish that a rule's scientific assumptions transfer.
An optional Tunisian graph adds a separate count of the vocabulary actually used.
No graph release, network request or model fit is needed.
"""
import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path
from time import perf_counter

import rdflib
from rdflib import BNode, Literal, URIRef
from rdflib.compare import to_canonical_graph
from rdflib.namespace import OWL, RDF, SH

from src.config import ROOT
from src.kg.ontology_modules import CORE_MODULES

L = "https://w3id.org/lulcw#"
ONTO = ROOT / "ontology"
ASSIGNMENT = ONTO / "modules" / "assignment.csv"
OUTPUT = ROOT / "docs" / "ontology_reuse_tn.md"
KINDS = ("class", "object property", "datatype property", "annotation property",
         "individual", "concept scheme")
COUNTRY_BOUND = frozenset(("profile/fr", "profile/eu"))
AVAILABLE = frozenset(CORE_MODULES) | {"profile/tn"}
CATEGORIES = ("shapes", "rules", "queries")
SPARQL_PROPERTIES = frozenset((SH.select, SH.construct, SH.ask))
PREFIXED = re.compile(r"(?<![\w:])lulcw:([\w](?:[\w.:-]*[\w:-])?)")
FULL_IRI = re.compile(r"<https://w3id\.org/lulcw#([^<>\s]+)>")


def read_assignment(path=ASSIGNMENT):
    """Read every term row, ignoring repeated header rows from table exports."""
    terms = {}
    with Path(path).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not {"term", "kind", "module", "rule"} <= set(reader.fieldnames or ()):
            raise ValueError("assignment.csv needs columns term,kind,module,rule")
        for row in reader:
            if row["kind"] == "kind":
                continue
            term = row["term"]
            if not term or term in terms:
                raise ValueError(f"Empty or duplicate assignment term: {term!r}")
            if row["kind"] not in KINDS or row["module"] not in AVAILABLE | COUNTRY_BOUND:
                raise ValueError(f"Invalid kind or module for {term}: {row}")
            terms[term] = row
    return terms


def percentage(count, total):
    """Empty groups have a displayed share of zero, without division by zero."""
    return 100.0 * count / total if total else 0.0


def counts(total, reusable):
    return {"total": total, "reusable": reusable, "percent": percentage(reusable, total)}


def static_availability(assignment):
    rows = {}
    for kind in (*KINDS, "total"):
        selected = [row for row in assignment.values() if kind == "total" or row["kind"] == kind]
        rows[kind] = counts(len(selected), sum(row["module"] in AVAILABLE for row in selected))
        rows[kind]["country_bound"] = sum(row["module"] in COUNTRY_BOUND for row in selected)
    return rows


def sparql_terms(text):
    """Collect both required spellings, without treating a PREFIX namespace as a term."""
    return set(PREFIXED.findall(text)) | set(FULL_IRI.findall(text))


def iri_terms(nodes):
    return {str(node)[len(L):] for node in nodes
            if isinstance(node, URIRef) and str(node).startswith(L)}


def shape_terms(graph, root):
    """Walk outgoing blank nodes, lists, and the shape's attached SHACL-AF rules.

    Rule bodies in this repository are named IRIs, so sh:rule must be followed
    explicitly. Other named objects are term references, not subgraphs to import.
    A visited set also handles shared or cyclic blank-node structures.
    """
    found, visited, pending = set(), set(), [root]
    while pending:
        subject = pending.pop()
        if subject in visited:
            continue
        visited.add(subject)
        for triple in graph.triples((subject, None, None)):
            found.update(iri_terms(triple))
            _, predicate, obj = triple
            if predicate in SPARQL_PROPERTIES and isinstance(obj, Literal):
                found.update(sparql_terms(str(obj)))
            if isinstance(obj, BNode) or (predicate == SH.rule and isinstance(obj, URIRef)):
                pending.append(obj)
    return found


def classify(category, name, terms, assignment):
    blocked = sorted(term for term in terms if term in assignment
                     and assignment[term]["module"] in COUNTRY_BOUND)
    missing = sorted(terms - assignment.keys())
    return {"category": category, "name": name, "terms": sorted(terms),
            "blocked": blocked, "missing": missing, "reusable": not blocked and not missing}


def artefacts(assignment, shapes, rules, query_files):
    """Classify every NodeShape, rule-bearing NodeShape, and query file once."""
    rows = []
    for category, graph in (("shapes", shapes), ("rules", rules)):
        # Anonymous NodeShapes also need stable names across parses of the same file.
        if any(isinstance(s, BNode) for s in graph.subjects(RDF.type, SH.NodeShape)):
            graph = to_canonical_graph(graph)
        for subject in sorted(set(graph.subjects(RDF.type, SH.NodeShape)), key=str):
            if category == "rules" and not any(graph.objects(subject, SH.rule)):
                continue
            name = subject.n3() if isinstance(subject, BNode) else str(subject)
            rows.append(classify(category, name, shape_terms(graph, subject), assignment))
    for path in sorted(map(Path, query_files)):
        rows.append(classify("queries", path.name,
                             sparql_terms(path.read_text(encoding="utf-8")), assignment))
    return rows


def artefact_summary(rows):
    summary = {}
    for category in CATEGORIES:
        selected = [row for row in rows if row["category"] == category]
        summary[category] = counts(len(selected), sum(row["reusable"] for row in selected))
    return summary


def used_reuse(graph, assignment=None):
    """Count distinct lulcw IRIs in any triple position, including rdf:type objects.

    Counts are vocabulary terms, not triple frequencies. Country-bound and unknown
    terms remain in the denominator and are returned as errors for a Tunisian KG.
    """
    if assignment is None:
        assignment = read_assignment()
    terms = set()
    for triple in graph:
        terms.update(iri_terms(triple))
    groups = {"core": [], "profile/tn": [], "country-bound": [], "unknown": []}
    for term in sorted(terms):
        module = assignment[term]["module"] if term in assignment else None
        group = ("core" if module in CORE_MODULES else "profile/tn" if module == "profile/tn"
                 else "country-bound" if module in COUNTRY_BOUND else "unknown")
        groups[group].append(term)
    errors = [f"Country-bound term used by Tunisian graph: lulcw:{term}"
              for term in groups["country-bound"]]
    errors += [f"Graph term absent from assignment.csv: lulcw:{term}" for term in groups["unknown"]]
    return {"total": len(terms), "groups": groups, "errors": errors,
            "percentages": {name: percentage(len(values), len(terms))
                            for name, values in groups.items()}}


def audit(assignment_path=ASSIGNMENT, shapes_path=ONTO / "shapes" / "lulcw-shapes.ttl",
          rules_path=ONTO / "rules" / "lulcw-rules.ttl", query_dir=ROOT / "tests" / "cq",
          ontology_path=ONTO / "lulcw.ttl", kg_path=None):
    assignment = read_assignment(assignment_path)
    shapes = rdflib.Graph().parse(shapes_path, format="turtle")
    rules = rdflib.Graph().parse(rules_path, format="turtle")
    ontology = rdflib.Graph().parse(ontology_path, format="turtle")
    versions = {str(value) for subject in ontology.subjects(RDF.type, OWL.Ontology)
                for value in ontology.objects(subject, OWL.versionInfo)}
    if len(versions) != 1:
        raise ValueError(f"Expected one ontology versionInfo, found {sorted(versions)}")
    rows = artefacts(assignment, shapes, rules, Path(query_dir).glob("*.rq"))
    errors = [f"{row['category']} {row['name']}: lulcw:{term} absent from assignment.csv"
              for row in rows for term in row["missing"]]
    used = used_reuse(rdflib.Graph().parse(kg_path), assignment) if kg_path is not None else None
    if used is not None:
        errors.extend(used["errors"])
    return {"version": versions.pop(), "assignment": assignment,
            "static": static_availability(assignment), "artefacts": rows,
            "summary": artefact_summary(rows), "used": used, "errors": errors}


def term_list(terms):
    return ", ".join(f"`lulcw:{term}`" for term in terms) or "—"


def report(result):
    lines = ["# France → Tunisia ontology reuse (generated)", "",
             f"Ontology version **{result['version']}**; generated by "
             "`python -m src.kg.reuse_report`. Do not edit by hand.", "",
             "Each term row in `ontology/modules/assignment.csv` counts once. The seven core "
             "modules and `profile/tn` are available to Tunisia unchanged; `profile/fr` and "
             "`profile/eu` are country-bound because French registers and EU Water Framework "
             "Directive codes do not apply to Tunisia. Each SHACL NodeShape, each rule-bearing "
             "NodeShape and each `tests/cq/*.rq` file is reusable when it mentions no country-bound "
             "term. The scan includes triples, reachable blank nodes, attached rule bodies and "
             "SPARQL strings (prefixed names and full IRIs). This is static vocabulary availability, "
             "not evidence that scientific assumptions transfer. Used reuse is measured separately "
             "when a Manouba graph is supplied.", "", "## Static availability", "",
             "| kind | total | available unchanged | available % | country-bound | country-bound % |",
             "|---|---:|---:|---:|---:|---:|"]
    for kind, row in result["static"].items():
        lines.append(f"| {kind} | {row['total']} | {row['reusable']} | {row['percent']:.2f}% | "
                     f"{row['country_bound']} | {percentage(row['country_bound'], row['total']):.2f}% |")
    lines += ["", "## Artefact availability", "",
              "| artefacts | total | reusable unchanged | reusable % |", "|---|---:|---:|---:|"]
    for category, row in result["summary"].items():
        lines.append(f"| {category} | {row['total']} | {row['reusable']} | {row['percent']:.2f}% |")
    lines += ["", "## Country-bound terms and the artefacts they block", "",
              "| term | module | blocked artefacts |", "|---|---|---|"]
    blockers = defaultdict(list)
    for row in result["artefacts"]:
        for term in row["blocked"]:
            blockers[term].append(f"{row['category']}: `{row['name']}`")
    for term, row in sorted(result["assignment"].items()):
        if row["module"] in COUNTRY_BOUND:
            lines.append(f"| `lulcw:{term}` | {row['module']} | "
                         f"{'; '.join(sorted(blockers[term])) or '—'} |")
    lines += ["", "## Used reuse", ""]
    used = result["used"]
    if used is None:
        lines.append("The Manouba graph does not exist yet. Used reuse has not been measured; "
                     "supply `--kg PATH` when it is available.")
    else:
        lines += [f"The supplied Tunisian graph uses **{used['total']}** distinct lulcw terms "
                  "in any triple position. Repeated occurrences count once.", "",
                  "| group | used terms | share of all used terms |", "|---|---:|---:|"]
        for group, terms in used["groups"].items():
            lines.append(f"| {group} | {len(terms)} | {used['percentages'][group]:.2f}% |")
        lines += ["", "Country-bound terms used (errors): " + term_list(used["groups"]["country-bound"]),
                  "", "Terms absent from the assignment (errors): " + term_list(used["groups"]["unknown"])]
    lines += ["", "## Errors", ""]
    lines += [f"- {error}" for error in result["errors"]] or ["None."]
    return "\n".join(lines) + "\n"


def write_report(result, output=OUTPUT):
    Path(output).write_text(report(result), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kg", type=Path, help="Tunisian RDF graph; format inferred from filename")
    args = parser.parse_args()
    started = perf_counter()
    try:
        result = audit(kg_path=args.kg)
        write_report(result)
    except (ValueError, OSError) as error:
        print(f"reuse_report: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    total = result["static"]["total"]
    print(f"lulcw {result['version']}: {total['reusable']}/{total['total']} terms available "
          f"unchanged ({total['percent']:.2f}%)")
    for category, row in result["summary"].items():
        print(f"{category}: {row['reusable']}/{row['total']} reusable ({row['percent']:.2f}%)")
    if result["used"] is not None:
        print(f"Used reuse: {result['used']['total']} terms; "
              f"{len(result['used']['errors'])} errors")
    print(f"-> {OUTPUT.relative_to(ROOT)} ({perf_counter() - started:.2f}s)")
    for error in result["errors"]:
        print(error, file=sys.stderr)
    if result["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
