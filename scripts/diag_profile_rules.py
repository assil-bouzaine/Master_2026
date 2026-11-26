"""Time each SHACL-AF rule on the v5 facts (same inputs as apply_rules.run_rules); prints per rule.

Run from the repository root: PYTHONIOENCODING=utf-8 PFE_DATASET=v5 .venv/bin/python <this file>
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
import rdflib
from pyshacl.rules.sparql import SPARQLRule

from src.kg import apply_rules as ar
from src.kg.build_kg import git_version

times = {}
orig = SPARQLRule.apply


def timed(self, *a, **k):
    t = time.time()
    n = orig(self, *a, **k)
    name = str(self.node).split("#")[-1]
    times[name] = times.get(name, 0.0) + time.time() - t
    print(f"{time.time() - t:8.1f} s  {n:7d} triples  {name}", flush=True)
    return n


SPARQLRule.apply = timed
t0 = time.time()
facts = rdflib.Graph().parse(ar.OUT / f"lulcw_kg_{ar.DATASET}.ttl")
rules = rdflib.Graph().parse(ar.RULES)
records = ar.rule_records(rules, git_version(("src/kg", "ontology")), facts)
print(f"[{time.time() - t0:.0f} s] loaded {len(facts)} facts", flush=True)
t1 = time.time()
added = ar.run_rules(facts, rules, records)
print(f"rules total {time.time() - t1:.0f} s, {len(added)} triples added", flush=True)
for name, s in sorted(times.items(), key=lambda kv: -kv[1])[:15]:
    print(f"  {s:8.1f} s  {name}")
