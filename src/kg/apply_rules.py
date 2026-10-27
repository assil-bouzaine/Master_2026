"""SHACL-AF rules and SHACL shapes on the LULC-Water knowledge graph (task 12.6).

    PFE_DATASET=v4 python -m src.kg.apply_rules

Reads the facts written by src.kg.build_kg (data/processed/kg/lulcw_kg_<dataset>.ttl), runs the
SHACL-AF rules of ontology/rules/lulcw-rules.ttl with pySHACL in advanced mode, then validates
the facts plus the derived links against ontology/shapes/lulcw-shapes.ttl, with the ontology
network mixed in (sh:class follows rdfs:subClassOf). Writes, next to the facts:
  lulcw_kg_<dataset>_rules.ttl           what the rules add, with the rules' descriptions,
                                         versions and the execution record
  lulcw_kg_<dataset>_shacl.ttl           the validation report
  lulcw_kg_<dataset>_rules_summary.json  counts, validation results, run time
  lulcw_kg_<dataset>_release.json        only when the shapes find no violation: the hashes of
                                         the facts, rules, shapes, ontology and outputs that
                                         belong together (src.kg.release; readers check them)
and exits with an error when the shapes find a violation (warnings and infos are reported).

The derived links are the ones the model's graph is made of (docs/ontology_design.md §4):
stratigraphic relations with their witness polygons and the `overlies` shortcut (CQ3), the
selections of each export policy and the main policy's monitors/pumpsFrom view (CQ1, CQ2),
same-unit well links within 5 km (CQ11) and pumping influences (CQ8); for land use (CQ7), the
crop class of each RPG code, class areas per zone and RPG year, and a dated high-irrigation-
demand category per zone and year. They are derived by SPARQL inside the graph, so that the
equivalence test of task 12.8 compares two independent derivations (pandas on the source tables
is the other).

Choices
- Facts and derived links stay in separate files: a query states whether it reads asserted
  facts or rule outputs (docs/competency_questions.md §6).
- Distances: Lambert-93 WKT points parsed in SPARQL; the square root is XPath 3.1's math:sqrt
  (a W3C function rdflib lacks), registered here as an rdflib custom function.
- The rules' parameters (search radii) and descriptions are data nodes of the rules file; they
  are copied into the graph first, so the rules read them and every derived link cites them.
- Speed (`fast_sparql`, results unchanged): pySHACL hands rdflib the text of a SPARQL
  constraint again for every focus node, and rdflib parses it each time, so each distinct text
  is parsed once; and rdflib orders a query's triple patterns before it knows that $this is
  pre-bound, and puts unrelated patterns side by side, so it could start from every rank-1
  attribution on both sides of a self-join (87 s for one facility). The patterns are ordered
  greedily instead: next, the pattern with the fewest unknown variables, preferring one joined
  to what is already bound, $this bound from the start (0.05 s).
"""
import json
import math
import sys
import time
from contextlib import contextmanager
from datetime import date

import numpy as np
import pyoxigraph
import rdflib
from pyshacl import shacl_rules, validate
from rdflib import BNode, Literal, URIRef, Variable
from rdflib.namespace import OWL, RDF, RDFS, SH, XSD
from rdflib.plugins.sparql import algebra as sparql_algebra
from rdflib.plugins.sparql import processor as sparql_processor
from rdflib.plugins.sparql.operators import register_custom_function

from src.config import DATASET, ROOT
from src.dataset.crop_demand import FROZEN_EDITION as LAST_TRAINING_YEAR   # 2019
from src.kg import release
from src.kg.build_kg import D, DCT, L, OUT, PROV, git_version, write_turtle

RULES, SHAPES = release.RULES, release.SHAPES
MATH_SQRT = URIRef("http://www.w3.org/2005/xpath-functions/math#sqrt")
EXECUTION = URIRef(D + "execution/kg-rules")
HIGH_DEMAND = URIRef(D + "rule/high-irrigation-demand")
PRE = ("PREFIX lulcw: <https://w3id.org/lulcw#> PREFIX prov: <http://www.w3.org/ns/prov#> "
       "PREFIX sosa: <http://www.w3.org/ns/sosa/> BASE <https://w3id.org/lulcw/data/> ")
T0 = time.time()


def log(msg):
    print(f"[{time.time() - T0:6.0f} s] {msg}", file=sys.stderr, flush=True)


def register_math():
    """XPath 3.1 math:sqrt for the distance rules (idempotent)."""
    def sqrt(x):
        return Literal(math.sqrt(float(x)), datatype=XSD.double)
    register_custom_function(MATH_SQRT, sqrt, override=True)


@contextmanager
def fast_sparql():
    """Parse and translate each distinct SPARQL text once (rdflib's documented reuse of a
    prepared query with new initial bindings), and evaluate the triple patterns that mention
    the pre-bound $this first. A basic graph pattern is a conjunction: only the work changes."""
    original_query, original_order = sparql_processor.SPARQLProcessor.query, sparql_algebra.reorderTriples
    this, cache = Variable("this"), {}

    def query(self, q, initBindings=None, initNs=None, base=None, DEBUG=False):
        if isinstance(q, str):
            key = (q, base, tuple(sorted((initNs or {}).items())))
            if key not in cache:
                cache[key] = sparql_processor.translateQuery(sparql_processor.parseQuery(q), base, initNs)
            q = cache[key]
        return original_query(self, q, initBindings, initNs, base, DEBUG)

    def order(triples):
        rest, known, out = list(triples), {this}, []
        while rest:
            def cost(t):
                free = [x for x in t if isinstance(x, (Variable, BNode)) and x not in known]
                joined = any(isinstance(x, (Variable, BNode)) and x in known for x in t)
                return len(free), not joined
            best = min(rest, key=cost)
            rest.remove(best)
            out.append(best)
            known |= {x for x in best if isinstance(x, (Variable, BNode))}
        return out

    sparql_processor.SPARQLProcessor.query, sparql_algebra.reorderTriples = query, order
    try:
        yield
    finally:
        sparql_processor.SPARQLProcessor.query, sparql_algebra.reorderTriples = original_query, original_order


def ontology_network():
    """The ontology network (lulcw-meta and every module of the catalog), parsed offline."""
    g = rdflib.Graph()
    for f in release.ontology_files().values():
        g.parse(f)
    return g


def demand_threshold(facts):
    """Upper tercile (numpy, linear interpolation) of the main potential-demand estimates of the
    training years 2015 to LAST_TRAINING_YEAR; None when the graph has no estimate."""
    q = (PRE + "SELECT ?v WHERE { ?e a lulcw:CropDemandEstimate ; sosa:observedProperty "
         "lulcw:PotentialIrrigationDemandMain ; lulcw:rpgEdition ?y ; sosa:hasSimpleResult ?v . "
         f"FILTER (?y <= {LAST_TRAINING_YEAR}) }}")
    v = [float(r[0]) for r in facts.query(q)]
    return float(np.quantile(v, 2 / 3)) if v else None


def rule_records(rules, version, facts=None):
    """The rules' data nodes (descriptions, parameters), versioned, the parameters computed from
    the facts (the high-demand threshold), and the execution record."""
    g = rdflib.Graph()
    for t in rules:
        if str(t[0]).startswith(D):
            g.add(t)
    for r in set(g.subjects(RDF.type, L.DerivationRule)):
        g.add((r, L.ruleVersion, Literal(version)))
    threshold = demand_threshold(facts) if facts is not None else None
    if threshold is not None:
        g.add((HIGH_DEMAND, L.demandThresholdM3, Literal(round(threshold, 1), datatype=XSD.double)))
    g.add((EXECUTION, RDF.type, L.RuleExecution))
    g.add((EXECUTION, RDFS.label, Literal(f"knowledge-graph rules, dataset {DATASET} (task 12.6)",
                                          lang="en")))
    g.add((EXECUTION, L.codeVersion, Literal(version)))
    g.add((EXECUTION, PROV.used, URIRef(D + f"kg-{DATASET}")))
    g.add((EXECUTION, RDFS.comment, Literal(
        f"SHACL-AF rules {RULES.relative_to(ROOT)} run with pySHACL (advanced mode) on "
        f"{date.today().isoformat()}", lang="en")))
    return g


def run_rules(facts, rules, records):
    """Apply the rules to facts + rule records; return only the triples the rules added."""
    register_math()
    data = rdflib.Graph()
    for t in facts:
        data.add(t)
    for t in records:
        data.add(t)
    before = len(data)
    with fast_sparql():
        shacl_rules(data, shacl_graph=rules, advanced=True, inplace=True, iterate_rules=False)
    added = rdflib.Graph()
    for t in data:
        if t not in facts and t not in records:
            added.add(t)
    assert len(added) == len(data) - before
    return added


def check(graph, shapes, onto):
    """pySHACL validation; returns (conforms, report graph, results by severity/shape/message).
    The ontology is added to the data graph here: pySHACL's ont_graph copies only the class
    hierarchy, not the typed concepts (lulcw:Probable a lulcw:ConfidenceLevel) that sh:class needs."""
    with fast_sparql():
        conforms, report, _ = validate(graph + onto, shacl_graph=shapes, inference="none",
                                       advanced=True, allow_infos=True, allow_warnings=True)
    results = {}
    for r in report.subjects(RDF.type, SH.ValidationResult):
        sev = str(report.value(r, SH.resultSeverity)).split("#")[-1]
        shape = report.value(r, SH.sourceShape)
        if not isinstance(shape, URIRef):           # a property shape: name its node shape
            shape = shapes.value(predicate=SH.property, object=shape) or shape
        name = str(shape).split("#")[-1] if isinstance(shape, URIRef) else "(anonymous)"
        path = report.value(r, SH.resultPath)
        msg = str(report.value(r, SH.resultMessage) or "")
        key = f"{sev} | {name}{' ' + str(path).split('#')[-1] if path is not None else ''} | {msg}"
        results[key] = results.get(key, 0) + 1
    return conforms, report, dict(sorted(results.items()))


def counts(facts, added):
    """What the rules derived, by kind (SPARQL on facts + rule outputs)."""
    g = facts + added
    pre = PRE

    def one(q):
        return {str(r[0]).split("#")[-1].split("/")[-1]: int(r[1]) for r in g.query(pre + q)}

    out = {
        "stratigraphic_relations_by_kind": one(
            "SELECT ?k (COUNT(?r) AS ?n) WHERE { ?r a lulcw:StratigraphicRelation ; "
            "lulcw:relationKind ?k } GROUP BY ?k"),
        "overlies_pairs": len(list(added.triples((None, L.overlies, None)))),
        "attributions_selected_by_policy": one(
            "SELECT ?p (COUNT(?a) AS ?n) WHERE { ?a a lulcw:UnitAttribution ; "
            "lulcw:selectedUnder ?p } GROUP BY ?p"),
        "monitors_main": len(list(added.triples((None, L.monitors, None)))),
        "pumpsFrom_main": len(list(added.triples((None, L.pumpsFrom, None)))),
        "well_links_by_confidence": one(
            "SELECT ?c (COUNT(?l) AS ?n) WHERE { ?l a lulcw:WellLink ; lulcw:confidence ?c } GROUP BY ?c"),
        "well_links_with_depth_difference": len(list(added.triples(
            (None, L.investigationDepthDifferenceM, None)))),
        "well_links_selected_by_policy": one(
            "SELECT ?p (COUNT(?l) AS ?n) WHERE { ?l a lulcw:WellLink ; lulcw:selectedUnder ?p } GROUP BY ?p"),
        "influences_by_resolution": one(
            "SELECT ?r (COUNT(?i) AS ?n) WHERE { ?i a lulcw:Influence ; lulcw:resolution ?r } GROUP BY ?r"),
        "influences_by_eligibility": one(
            "SELECT ?e (COUNT(?i) AS ?n) WHERE { ?i a lulcw:Influence ; lulcw:constraintEligibility ?e } "
            "GROUP BY ?e"),
        "influences_by_confidence": one(
            "SELECT ?c (COUNT(?i) AS ?n) WHERE { ?i a lulcw:Influence ; lulcw:confidence ?c } GROUP BY ?c"),
        "influences_selected_by_policy": one(
            "SELECT ?p (COUNT(?i) AS ?n) WHERE { ?i a lulcw:Influence ; lulcw:selectedUnder ?p } GROUP BY ?p"),
        "eligible_influences_selected_by_policy": one(
            "SELECT ?p (COUNT(?i) AS ?n) WHERE { ?i a lulcw:Influence ; lulcw:selectedUnder ?p ; "
            "lulcw:constraintEligibility lulcw:EligibleConstraint } GROUP BY ?p"),
    }
    pairs = g.query(pre + "SELECT ?p (COUNT(DISTINCT CONCAT(STR(?f), STR(?w))) AS ?n) "
                    "(COUNT(DISTINCT ?f) AS ?nf) (COUNT(DISTINCT ?w) AS ?nw) WHERE { ?i a lulcw:Influence ; "
                    "lulcw:driverEntity ?f ; lulcw:targetEntity ?w ; lulcw:selectedUnder ?p } GROUP BY ?p")
    out["influence_facility_well_pairs_by_policy"] = {
        str(r[0]).split("/")[-1]: {"pairs": int(r[1]), "facilities": int(r[2]), "wells": int(r[3])}
        for r in pairs}
    out["crop_codes_by_class"] = one(
        "SELECT ?c (COUNT(?k) AS ?n) WHERE { ?k a lulcw:CropCode ; lulcw:cropClass ?c } GROUP BY ?c")
    out["crop_codes_without_class"] = int(list(g.query(pre + "SELECT (COUNT(?k) AS ?n) WHERE { "
        "?k a lulcw:CropCode FILTER NOT EXISTS { ?k lulcw:cropClass ?c } }"))[0][0])
    out["crop_class_areas"] = len(list(added.subjects(RDF.type, L.CropClassArea)))
    out["demand_assessments_by_category"] = one(
        "SELECT ?c (COUNT(?a) AS ?n) WHERE { ?a a lulcw:IrrigationDemandAssessment ; "
        "lulcw:demandCategory ?c } GROUP BY ?c")
    out["outcrop_coverages_by_extent_kind"] = one(
        "SELECT ?k (COUNT(?v) AS ?n) WHERE { ?v a lulcw:OutcropCoverage ; lulcw:withinExtent ?s . "
        "BIND (IF(STRSTARTS(STR(?s), STR(<outcrop-zone/>)), <kind/search-zone>, ?s) AS ?k) } GROUP BY ?k")
    out["cell_weights"] = len(list(added.subjects(RDF.type, L.CellWeight)))
    thr = list(g.objects(HIGH_DEMAND, L.demandThresholdM3))
    out["high_demand_threshold_m3"] = float(thr[0]) if thr else None
    return out


def main():
    t0 = time.time()
    inputs = release.input_hashes()     # before anything is read; checked again at the end
    release.invalidate()                # a derivation in progress, or a failed one, has no release
    facts_file = OUT / f"lulcw_kg_{DATASET}.ttl"
    facts = rdflib.Graph().parse(facts_file)
    rules = rdflib.Graph().parse(RULES)
    shapes = rdflib.Graph().parse(SHAPES)
    onto = ontology_network()
    version = git_version(("src/kg", "ontology"))

    records = rule_records(rules, version, facts)
    log(f"facts loaded ({len(facts)} triples); applying the rules")
    added = run_rules(facts, rules, records)
    t_rules = time.time() - t0
    log(f"rules done: {len(added)} triples added; validating")

    out = rdflib.Graph()
    for p, ns in facts.namespaces():
        out.bind(p, ns)
    out.bind("lulcwr", "https://w3id.org/lulcw/rules#")
    head = URIRef(D + f"kg-{DATASET}-rules")
    out.add((head, RDF.type, OWL.Ontology))
    out.add((head, DCT.title, Literal(f"LULC-Water knowledge graph, dataset {DATASET}: links derived "
                                      "by the SHACL-AF rules", lang="en")))
    out.add((head, DCT.description, Literal(
        "Stratigraphic relations, policy selections, same-unit well links and pumping influences "
        f"derived from lulcw_kg_{DATASET}.ttl by ontology/rules/lulcw-rules.ttl (task 12.6).",
        lang="en")))
    out.add((head, DCT.created, Literal(date.today().isoformat(), datatype=XSD.date)))
    out.add((head, PROV.wasDerivedFrom, URIRef(D + f"kg-{DATASET}")))
    out.add((head, PROV.wasGeneratedBy, EXECUTION))
    out.add((head, OWL.versionInfo, Literal(version)))
    for t in records + added:
        out.add(t)

    conforms, report, results = check(facts + out, shapes, onto)
    t_all = time.time() - t0
    log("validation done; writing")

    rules_file = OUT / f"lulcw_kg_{DATASET}_rules.ttl"
    write_turtle(out, rules_file)
    report.serialize(OUT / f"lulcw_kg_{DATASET}_shacl.ttl", format="turtle")
    store = pyoxigraph.Store()
    for f in (facts_file, rules_file):
        store.bulk_load(path=str(f), format=pyoxigraph.RdfFormat.TURTLE)
    assert len(store) == len(facts | out), f"pyoxigraph loaded {len(store)} of {len(facts | out)} triples"

    summary = {
        "dataset": DATASET, "run": date.today().isoformat(), "code_version": version,
        "facts_triples": len(facts), "rule_triples": len(added), "rules_file_triples": len(out),
        "derived": counts(facts, out),   # out = the rule outputs + the rules' parameters
        "shacl_conforms_no_violation": bool(conforms),
        "shacl_results": results,
        "seconds_rules": round(t_rules), "seconds_total": round(t_all),
    }
    (OUT / f"lulcw_kg_{DATASET}_rules_summary.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False))
    print(json.dumps(summary, indent=1, ensure_ascii=False))
    print(f"-> {rules_file.relative_to(ROOT)}")
    if not conforms:
        raise SystemExit("SHACL violations: see the report and shacl_results above (no release written)")
    facts_summary = OUT / f"lulcw_kg_{DATASET}_summary.json"
    built = json.loads(facts_summary.read_text()) if facts_summary.exists() else {}
    release.write(inputs, rules_code_version=version, facts_code_version=built.get("code_version"),
                  facts_triples=len(facts), rule_outputs_triples=len(out),
                  shacl_results=results)
    print(f"-> {release.manifest_path().relative_to(ROOT)} (validated release)")


if __name__ == "__main__":
    main()
