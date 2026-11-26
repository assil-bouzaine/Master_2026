"""Synthetic benchmark of the CQ15 completeness check (docs/notes/step16_v5.md, R2.2, 2026-11-26).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v5 .venv/bin/python scripts/diag_bench_not_exists.py

A NOT EXISTS block with `?c lulcw:derivationRule $this` under apply_rules.fast_sparql's static
ordering (and under a runtime-aware ordering by number of unbound terms) is quadratic in the number
of parcel-seasons; the rewritten block (`?c lulcw:derivationRule ?rule . FILTER (?rule = $this)`,
the outer-bound pattern first) is linear. Measured 2026-11-26: original 12.5 s (500) and 40.9 s
(1,000); rewritten 1.1 s (500), 1.7 s (2,000), 9.2 s (13,260), same violations."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
import rdflib
from rdflib import Literal, URIRef, Variable, BNode
from rdflib.namespace import RDF, XSD
from rdflib.plugins.sparql import evaluate as ev
from rdflib.plugins.sparql.sparql import AlreadyBound

from src.kg import apply_rules as ar

L = rdflib.Namespace("https://w3id.org/lulcw#")
SOSA = rdflib.Namespace("http://www.w3.org/ns/sosa/")
D = "https://w3id.org/lulcw/data/"
R = URIRef(D + "rule/probable-irrigation")

Q = """PREFIX lulcw: <https://w3id.org/lulcw#>
PREFIX sosa: <http://www.w3.org/ns/sosa/>
SELECT $this ?value WHERE {
    $this a lulcw:DerivationRule .
    ?value a lulcw:SatelliteIndexObservation ;
           sosa:observedProperty lulcw:SummerNDVI ;
           sosa:hasFeatureOfInterest ?p ;
           lulcw:seasonYear ?y .
    FILTER NOT EXISTS {
        ?c lulcw:classifiedParcel ?p ; lulcw:seasonYear ?y ; lulcw:derivationRule $this .
    }
}"""


def graph(n, missing=3):
    g = rdflib.Graph()
    g.add((R, RDF.type, L.DerivationRule))
    for i in range(n):
        p, o, c = URIRef(D + f"parcel/{i}"), URIRef(D + f"ndvi/{i}"), URIRef(D + f"cls/{i}")
        g.add((o, RDF.type, L.SatelliteIndexObservation))
        g.add((o, SOSA.observedProperty, L.SummerNDVI))
        g.add((o, SOSA.hasFeatureOfInterest, p))
        g.add((o, L.seasonYear, Literal(2020, datatype=XSD.integer)))
        if i >= missing:
            g.add((c, L.classifiedParcel, p))
            g.add((c, L.seasonYear, Literal(2020, datatype=XSD.integer)))
            g.add((c, L.derivationRule, R))
    return g


def eval_bgp_runtime(ctx, bgp):
    """rdflib's evalBGP, choosing at each step the pattern with the fewest unbound terms under the
    current bindings (ties: a pattern sharing a bound variable, then the written order)."""
    if not bgp:
        yield ctx.solution()
        return

    def cost(k):
        t = bgp[k]
        free = joined = 0
        for x in t:
            if isinstance(x, (Variable, BNode)):
                if ctx[x] is None:
                    free += 1
                else:
                    joined = 1
        return free, not joined, k

    i = min(range(len(bgp)), key=cost)
    s, p, o = bgp[i]
    rest = bgp[:i] + bgp[i + 1:]
    _s, _p, _o = ctx[s], ctx[p], ctx[o]
    for ss, sp, so in ctx.graph.triples((_s, _p, _o)):
        c = ctx.push() if None in (_s, _p, _o) else ctx
        if _s is None:
            c[s] = ss
        try:
            if _p is None:
                c[p] = sp
        except AlreadyBound:
            continue
        try:
            if _o is None:
                c[o] = so
        except AlreadyBound:
            continue
        yield from eval_bgp_runtime(c, rest)


Q_FIXED = Q.replace("""        ?c lulcw:classifiedParcel ?p ; lulcw:seasonYear ?y ; lulcw:derivationRule $this .
    }""", """        ?c lulcw:classifiedParcel ?p ; lulcw:seasonYear ?y ; lulcw:derivationRule ?rule .
        FILTER (?rule = $this)
    }""")
assert Q_FIXED != Q

for n in (500, 1000):
    g = graph(n)
    with ar.fast_sparql():
        t = time.time()
        rows = list(g.query(Q, initBindings={"this": R}))
        t_static = time.time() - t
        orig = ev.evalBGP
        ev.evalBGP = eval_bgp_runtime
        try:
            t = time.time()
            rows2 = list(g.query(Q, initBindings={"this": R}))
            t_rt = time.time() - t
        finally:
            ev.evalBGP = orig
    assert sorted(map(str, rows)) == sorted(map(str, rows2)), (rows, rows2)
    print(f"n={n:6d}  violations={len(rows)}  original static {t_static:7.2f} s   runtime-aware {t_rt:6.2f} s", flush=True)

for n in (500, 2000, 13260):
    g = graph(n)
    with ar.fast_sparql():
        t = time.time()
        rows = list(g.query(Q_FIXED, initBindings={"this": R}))
        dt = time.time() - t
    assert len(rows) == 3
    print(f"n={n:6d}  violations={len(rows)}  rewritten {dt:6.2f} s", flush=True)
