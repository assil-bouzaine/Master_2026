"""Time the CQ15 rule (order 70) piece by piece on a sample of the v5 facts, to find which part makes it slow.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v5 .venv/bin/python scripts/diag_cq15_rule_parts.py SAMPLE.ttl [N]

The sample (the first N summer-NDVI observations, their parcels, every soil-wetness observation, the rule node)
is written to SAMPLE.ttl on the first run and read from it afterwards.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
import rdflib
from rdflib import URIRef
from rdflib.namespace import RDF, SH

from src.kg import apply_rules as ar

L = rdflib.Namespace("https://w3id.org/lulcw#")
SOSA = rdflib.Namespace("http://www.w3.org/ns/sosa/")
THIS = URIRef("https://w3id.org/lulcw/data/rule/probable-irrigation")
sample, N = Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 300

rules = rdflib.Graph().parse(ar.RULES)
construct = str(rules.value(URIRef("https://w3id.org/lulcw/rules#probableIrrigation"), SH.construct))
decl = "".join(f"PREFIX {rules.value(d, SH.prefix)}: <{rules.value(d, SH.namespace)}>\n"
               for d in rules.objects(URIRef("https://w3id.org/lulcw/rules"), SH.declare))
if not sample.exists():
    facts = rdflib.Graph().parse(ar.OUT / f"lulcw_kg_{ar.DATASET}.ttl")
    obs = sorted(facts.subjects(RDF.type, L.SatelliteIndexObservation))[:N]
    keep = set(obs) | {facts.value(o, SOSA.hasFeatureOfInterest) for o in obs}
    keep |= set(facts.subjects(SOSA.observedProperty, L.SummerSoilWetness)) | {THIS}
    g = rdflib.Graph()
    for s in keep:
        for t in facts.triples((s, None, None)):
            g.add(t)
    g.serialize(sample, format="turtle")
g = rdflib.Graph().parse(sample)
print(f"sample {len(g)} triples", flush=True)

head, where = construct.split("WHERE {", 1)
body = where.rsplit("}", 1)[0]
lines = body.splitlines()
# the WHERE block's parts, in order: main patterns up to the first OPTIONAL, then each OPTIONAL block, then the BINDs
def block(start_marker):
    i = next(k for k, l in enumerate(lines) if l.strip().startswith(start_marker))
    depth, out = 0, []
    for l in lines[i:]:
        out.append(l)
        depth += l.count("{") - l.count("}")
        if depth <= 0:
            break
    return "\n".join(out)

main_end = next(k for k, l in enumerate(lines) if l.strip().startswith("OPTIONAL"))
main = "\n".join(lines[:main_end])
opts = []
k = main_end
while k < len(lines):
    l = lines[k].strip()
    if l.startswith("OPTIONAL"):
        depth, j = 0, k
        while True:
            depth += lines[j].count("{") - lines[j].count("}")
            if depth <= 0:
                break
            j += 1
        opts.append("\n".join(lines[k:j + 1]))
        k = j + 1
    else:
        break
binds = "\n".join(lines[k:])
variants = [("main", main, False)]
for n in range(1, len(opts) + 1):
    variants.append((f"main+opt1..{n}", main + "\n" + "\n".join(opts[:n]), False))
variants.append(("full (committed)", body, True))
for name, w, full in variants:
    q = decl + ("SELECT * WHERE {" + w + "\n}" if not full else construct)
    with ar.fast_sparql():
        t = time.time()
        n = len(list(g.query(q, initBindings={"this": THIS})))
    print(f"{name:20s} {n:7d} rows/triples  {time.time() - t:7.2f} s", flush=True)
for i, o in enumerate(opts, 1):
    print(f"--- opt{i}:\n{o}")
