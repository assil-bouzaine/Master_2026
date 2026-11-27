"""Compare the CQ15 rule (order 70, lulcwr:probableIrrigation) as committed with its rewrite: same constructed
triples on the v5 facts, and the time of each. The rewrite (2026-11-27) folds the parcel's weather cell into the
soil-wetness OPTIONAL and joins on the outer ?cell and ?year inside its patterns instead of comparing fresh
variables in a FILTER: rdflib then prunes the 40 candidate observations inside the pattern match, instead of
running the nested OPTIONAL and the FILTER expression for each of them (27 ms per parcel-season before). A parcel
without a matched cell gets no soil wetness, as before (the whole OPTIONAL fails).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v5 .venv/bin/python scripts/diag_cq15_rule_rewrite.py
"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
import rdflib
from rdflib import URIRef
from rdflib.namespace import SH

from src.kg import apply_rules as ar

OLD_OPT = """    OPTIONAL { ?parcel lulcw:matchedWeatherCell ?cell . }
    OPTIONAL {
        ?swiObs sosa:observedProperty lulcw:SummerSoilWetness ;
                sosa:hasFeatureOfInterest ?scell ;
                lulcw:seasonYear ?syear .
        OPTIONAL { ?swiObs sosa:hasSimpleResult ?swi . }
        FILTER (BOUND(?cell) && ?scell = ?cell && ?syear = ?year)
    }"""
NEW_OPT = """    OPTIONAL {
        ?parcel lulcw:matchedWeatherCell ?cell .
        ?swiObs sosa:hasFeatureOfInterest ?cell ;
                lulcw:seasonYear ?year ;
                sosa:observedProperty lulcw:SummerSoilWetness .
        OPTIONAL { ?swiObs sosa:hasSimpleResult ?swi . }
    }"""


def construct_of(text):
    rules = rdflib.Graph().parse(data=text, format="turtle")
    construct = str(rules.value(URIRef("https://w3id.org/lulcw/rules#probableIrrigation"), SH.construct))
    onto = URIRef("https://w3id.org/lulcw/rules")
    decl = "".join(f"PREFIX {rules.value(d, SH.prefix)}: <{rules.value(d, SH.namespace)}>\n"
                   for d in rules.objects(onto, SH.declare))
    return decl + construct


def main():
    """old = the rule at git HEAD (or the working file with NEW_OPT swapped back if HEAD has it already),
    new = the rule in the working tree."""
    head = subprocess.run(["git", "show", "HEAD:ontology/rules/lulcw-rules.ttl"], capture_output=True, text=True,
                          check=True).stdout
    work = ar.RULES.read_text()
    old_q, new_q = construct_of(head), construct_of(work)
    if NEW_OPT in old_q:                            # HEAD already has the rewrite: rebuild the old form
        old_q = old_q.replace(NEW_OPT, OLD_OPT)
    assert OLD_OPT in old_q and NEW_OPT in new_q, "unexpected rule texts"
    t0 = time.time()
    facts = rdflib.Graph().parse(ar.OUT / f"lulcw_kg_{ar.DATASET}.ttl")
    print(f"[{time.time() - t0:.0f} s] facts {len(facts)}", flush=True)
    this = URIRef("https://w3id.org/lulcw/data/rule/probable-irrigation")
    out = {}
    for name in sys.argv[1:] or ["new", "old"]:
        with ar.fast_sparql():
            t = time.time()
            out[name] = set(facts.query(new_q if name == "new" else old_q, initBindings={"this": this}))
            print(f"{name}: {len(out[name])} triples in {time.time() - t:.1f} s", flush=True)
    if len(out) == 2:
        a, b = out["old"], out["new"]
        print("identical" if a == b else f"DIFFERENT: only old {len(a - b)}, only new {len(b - a)}")


if __name__ == "__main__":
    main()
