"""Time each SHACL node shape on the released v5 graph (same inputs as apply_rules.check).

Run from the repository root:
  PYTHONIOENCODING=utf-8 PFE_DATASET=v5 .venv/bin/python <this file> [--first N]
Prints one line per node shape: seconds, focus-node count, shape name. New CQ15 shapes first.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
import rdflib
from rdflib.namespace import RDF
from pyshacl import validate

from src.kg import apply_rules as ar

SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")
t0 = time.time()
facts = rdflib.Graph().parse(ar.OUT / f"lulcw_kg_{ar.DATASET}.ttl")
derived = rdflib.Graph().parse(ar.OUT / f"lulcw_kg_{ar.DATASET}_rules.ttl")
onto = ar.ontology_network()
shapes = rdflib.Graph().parse(ar.SHAPES)
g = facts + derived + onto
print(f"[{time.time()-t0:6.0f} s] loaded {len(g)} triples", flush=True)

node_shapes = sorted(set(shapes.subjects(RDF.type, SH.NodeShape)), key=str)
first = [s for s in node_shapes if any(k in str(s) for k in (
    "RegisteredParcel", "ParcelZoneOverlap", "SatelliteIndexObservation", "IrrigationClassification",
    "ProbablyIrrigatedShare", "DerivationRule"))]
rest = [s for s in node_shapes if s not in first]
order = first + rest
if "--first" in sys.argv:
    order = order[: int(sys.argv[sys.argv.index("--first") + 1])]

total = 0.0
ar.register_math()
with ar.fast_sparql():
    for s in order:
        t = time.time()
        conforms, report, _ = validate(g, shacl_graph=shapes, inference="none", advanced=True,
                                       allow_infos=True, allow_warnings=True, inplace=True,
                                       use_shapes=[s])
        dt = time.time() - t
        total += dt
        n = len(set(report.subjects(SH.focusNode, None)))
        print(f"{dt:8.1f} s  conforms={conforms!s:5}  results={len(set(report.subjects(RDF.type, SH.ValidationResult))):4d}  {str(s).split('#')[-1]}",
              flush=True)
print(f"total {total:.0f} s", flush=True)
