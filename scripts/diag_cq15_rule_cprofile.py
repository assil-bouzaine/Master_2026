"""cProfile of the CQ15 rule (order 70) on a sample of the v5 facts: the first N summer-NDVI observations,
their parcels, every soil-wetness observation and the rule node; prints the time of the committed query
and of the rewrite (scripts/diag_cq15_rule_rewrite.py) and the functions where each spends it.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v5 .venv/bin/python scripts/diag_cq15_rule_cprofile.py [N]
"""
import cProfile
import pstats
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
import rdflib
from rdflib import URIRef
from rdflib.namespace import RDF, SH

from src.kg import apply_rules as ar
from scripts.diag_cq15_rule_rewrite import NEW_OPT, OLD_OPT

N = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
L = rdflib.Namespace("https://w3id.org/lulcw#")
SOSA = rdflib.Namespace("http://www.w3.org/ns/sosa/")
THIS = URIRef("https://w3id.org/lulcw/data/rule/probable-irrigation")

rules = rdflib.Graph().parse(ar.RULES)
construct = str(rules.value(URIRef("https://w3id.org/lulcw/rules#probableIrrigation"), SH.construct))
decl = "".join(f"PREFIX {rules.value(d, SH.prefix)}: <{rules.value(d, SH.namespace)}>\n"
               for d in rules.objects(URIRef("https://w3id.org/lulcw/rules"), SH.declare))
t0 = time.time()
facts = rdflib.Graph().parse(ar.OUT / f"lulcw_kg_{ar.DATASET}.ttl")
obs = sorted(facts.subjects(RDF.type, L.SatelliteIndexObservation))[:N]
parcels = {facts.value(o, SOSA.hasFeatureOfInterest) for o in obs}
swi = set(facts.subjects(SOSA.observedProperty, L.SummerSoilWetness))
keep = set(obs) | parcels | swi | {THIS}
g = rdflib.Graph()
for s in keep:
    for t in facts.triples((s, None, None)):
        g.add(t)
del facts
print(f"[{time.time() - t0:.0f} s] sample: {len(obs)} observations, {len(parcels)} parcels, {len(swi)} soil-wetness, "
      f"{len(g)} triples", flush=True)
res = {}
for name, q in (("old", construct), ("new", construct.replace(OLD_OPT, NEW_OPT))):
    pr = cProfile.Profile()
    with ar.fast_sparql():
        t = time.time()
        pr.enable()
        out = set(g.query(decl + q, initBindings={"this": THIS}))
        pr.disable()
    res[name] = out
    print(f"\n=== {name}: {len(out)} triples in {time.time() - t:.1f} s", flush=True)
    pstats.Stats(pr).sort_stats("tottime").print_stats(12)
print("identical" if res["old"] == res["new"] else f"DIFFERENT: {len(res['old'] ^ res['new'])} triples differ")
