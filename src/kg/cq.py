"""Run the competency-question queries of tests/cq/ on the knowledge graph (task 12.7).

    from src.kg.cq import ask, kg_store
    s = kg_store()                                   # facts + rule outputs of PFE_DATASET
    ask(s, "cq07_crops", W=<piezometer IRI>, year=2023)

The queries are SPARQL files; their headers state the parameters, what they read and their
columns (docs/competency_questions.md §6). Parameters are bound by a VALUES clause placed at the
top of the query's WHERE block: standard SPARQL 1.1, evaluated first by any engine. pyoxigraph's
own substitutions (SEP-0007) act as a join after evaluation in 0.5, too late for the status
queries, which must give a row even where the graph holds no data. Distances use XPath 3.1
math:sqrt, registered here for pyoxigraph (src.kg.apply_rules registers it for rdflib).
Used by tests/test_cq.py and by the reports that answer questions from the graph.
"""
import math

import pyoxigraph as ox
import rdflib
from rdflib.namespace import XSD

from src.config import DATASET, PROCESSED, ROOT

CQ = ROOT / "tests" / "cq"
KG = PROCESSED / "kg"
XSD_DOUBLE = ox.NamedNode(str(XSD.double))
XSD_INTEGER = ox.NamedNode(str(XSD.integer))


def sqrt(x):
    return ox.Literal(repr(math.sqrt(float(x.value))), datatype=XSD_DOUBLE)


FUNCTIONS = {ox.NamedNode("http://www.w3.org/2005/xpath-functions/math#sqrt"): sqrt}


def term(v):
    """A Python value as a pyoxigraph term: IRIs for rdflib URIRefs, xsd:double for floats,
    xsd:integer for ints. A plain str is refused: an IRI passed as a string would silently become
    a literal and match nothing (it happened twice on 2026-10-26); pass rdflib.URIRef or
    ox.NamedNode for an IRI, ox.Literal for a string."""
    if isinstance(v, (ox.NamedNode, ox.Literal)):
        return v
    if isinstance(v, rdflib.URIRef):
        return ox.NamedNode(str(v))
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise TypeError(f"parameter {v!r}: use rdflib.URIRef / ox.NamedNode for an IRI, ox.Literal for text")
    if isinstance(v, float):
        return ox.Literal(repr(v), datatype=XSD_DOUBLE)
    return ox.Literal(str(v), datatype=XSD_INTEGER)


def py(v):
    if v is None:
        return None
    if isinstance(v, ox.Literal):
        dt = v.datatype.value
        if dt.endswith(("#double", "#decimal", "#float")):
            return float(v.value)
        if dt.endswith(("#integer", "#int", "#long")):
            return int(v.value)
        if dt.endswith("#boolean"):
            return v.value == "true"
        return v.value
    return v.value


def bind(query, params):
    """The query with its parameters bound by a VALUES clause at the top of its WHERE block."""
    if not params:
        return query
    i = query.index("WHERE {") + len("WHERE {")
    row = " ".join(str(term(v)) for v in params.values())
    return f"{query[:i]}\n    VALUES ({' '.join('?' + k for k in params)}) {{ ({row}) }}{query[i:]}"


def ask(store, name, **params):
    """Run tests/cq/<name>.rq with the parameters bound; rows as dicts of Python values."""
    res = store.query(bind((CQ / f"{name}.rq").read_text(), params), custom_functions=FUNCTIONS)
    cols = [v.value for v in res.variables]
    return [{c: py(r[c]) for c in cols} for r in res]


def one(store, name, **params):
    rows = ask(store, name, **params)
    assert len(rows) == 1, f"{name} {params}: {len(rows)} rows"
    return rows[0]


def local(iri):
    return iri.rsplit("/", 1)[-1].rsplit("#", 1)[-1] if iri else iri


def kg_store(dataset=DATASET):
    """pyoxigraph store of the facts and the rule outputs (src.kg.build_kg, src.kg.apply_rules)."""
    s = ox.Store()
    for f in (KG / f"lulcw_kg_{dataset}.ttl", KG / f"lulcw_kg_{dataset}_rules.ttl"):
        s.bulk_load(path=str(f), format=ox.RdfFormat.TURTLE)
    return s


def iris(store, q):
    """{literal value: IRI term} from a two-column query (lulcw: prefix declared)."""
    return {r[0].value: r[1] for r in store.query("PREFIX lulcw: <https://w3id.org/lulcw#> " + q)}
