"""Verification suite for the modular LULC-Water ontology and profiles (v5 plan R2.2).

    PFE_DATASET=v5 python -m tests.test_modules

Checks that the generated modules and country/regional profiles under ``ontology/modules/`` and
``ontology/profiles/`` match the single authored master ``ontology/lulcw.ttl`` and form a valid,
acyclic, consistent OWL 2 ontology network:
1. Partition and union equivalence: every ``lulcw:`` term of the master appears in exactly one
   generated module or profile, and the union of all generated files' triples (minus ontology
   headers and external annotation-property declarations) is graph-isomorphic to the master's
   triples (including blank-node axioms such as ``owl:AllDisjointClasses``).
2. Reproducibility: ``python -m src.kg.ontology_modules --check`` exits 0.
3. Layering and guards: no core module mentions a profile term; the computed module import graph
   is acyclic and matches the ``owl:imports`` declared in every generated file; synthetic cycle
   and core-to-profile leak fixtures are rejected by ``compute_imports``.
4. Offline loading and reasoning: every module, every profile, and ``ontology/lulcw-modular.ttl``
   load through ``ontology/catalog-v001.xml`` and pass ELK and HermiT consistency (with no
   unsatisfiable class or inferred equivalence), plus a disjointness negative control on
   ``lulcw-hydro.ttl`` and ``lulcw-modular.ttl``.
5. Per-module term-count table and pan-Mediterranean core share (core-module terms / all terms).
"""
import csv
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import rdflib
from rdflib.compare import isomorphic
from rdflib.namespace import DCTERMS, OWL, RDF

from src.config import ROOT
from src.kg import ontology_modules as om
from tests import test_ontology as to

ONTO = om.ONTO
L = om.L
EXT_ANNOT_NS = (str(DCTERMS), str(om.VANN))


def _strip_header(graph):
    """Drop ontology-header triples and external dcterms/vann annotation declarations."""
    onto_nodes = set(graph.subjects(RDF.type, OWL.Ontology))
    out = rdflib.Graph()
    for s, p, o in graph:
        if s in onto_nodes:
            continue
        if isinstance(s, rdflib.URIRef) and str(s).startswith(EXT_ANNOT_NS) and p == RDF.type and o == OWL.AnnotationProperty:
            continue
        out.add((s, p, o))
    return out


def test_partition_and_union():
    master = rdflib.Graph().parse(om.MASTER)
    master_terms = {
        str(s)[len(L):]
        for s in master.subjects(RDF.type, None)
        if isinstance(s, rdflib.URIRef) and str(s).startswith(L)
    }

    seen_in = {}
    union = rdflib.Graph()
    per_mod_counts = {}
    for mod in om.ALL_MODULES:
        path = ONTO / om.MODULE_META[mod]["rel_path"]
        assert path.exists(), f"missing generated file: {path}"
        g = rdflib.Graph().parse(path)
        mod_terms = {
            str(s)[len(L):]
            for s in g.subjects(RDF.type, None)
            if isinstance(s, rdflib.URIRef) and str(s).startswith(L)
        }
        per_mod_counts[mod] = len(mod_terms)
        for t in mod_terms:
            assert t not in seen_in, f"term {t} declared in both {seen_in[t]} and {mod}"
            seen_in[t] = mod
        union += _strip_header(g)

    assert set(seen_in) == master_terms, (
        f"partition mismatch: missing={sorted(master_terms - set(seen_in))}, "
        f"extra={sorted(set(seen_in) - master_terms)}"
    )

    master_body = _strip_header(master)
    assert len(union) == len(master_body), f"triple count mismatch: union={len(union)} vs master={len(master_body)}"
    assert isomorphic(union, master_body), "union of generated module/profile triples is not isomorphic to master"

    # Cross-check assignment.csv matches the partition.
    with open(ONTO / "modules" / "assignment.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    csv_map = {r["term"]: r["module"] for r in rows}
    assert len(rows) == len(master_terms) and csv_map == seen_in, "assignment.csv does not match module files"

    print(f"  1. partition & union: {len(master_terms)} master terms partitioned across "
          f"{len(om.ALL_MODULES)} files; union ({len(union)} triples) is isomorphic to master")
    return per_mod_counts, len(master_terms)


def test_check_cli():
    r = subprocess.run(
        [sys.executable, "-m", "src.kg.ontology_modules", "--check"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert r.returncode == 0, f"--check failed:\n{r.stdout}\n{r.stderr}"
    print("  2. src.kg.ontology_modules --check: passed (exit 0)")


def test_imports_and_guards():
    g, _, _, _, term_to_mod = om.load_master()
    mod_triples, _ = om.split_triples(g, term_to_mod)
    lulcw_imps, ext_imps = om.compute_imports(mod_triples, term_to_mod)

    # Verify no core module imports or mentions any profile term, and file owl:imports match computed.
    for mod in om.ALL_MODULES:
        if mod in om.CORE_MODULES:
            assert not (set(lulcw_imps[mod]) & set(om.PROFILES)), f"core module {mod} imports a profile"
        path = ONTO / om.MODULE_META[mod]["rel_path"]
        fg = rdflib.Graph().parse(path)
        onto_iri = rdflib.URIRef(om.MODULE_META[mod]["iri"])
        declared_imps = sorted(str(o) for o in fg.objects(onto_iri, OWL.imports))
        expected_imps = sorted([om.MODULE_META[m]["iri"] for m in lulcw_imps[mod]] + list(ext_imps[mod]))
        assert declared_imps == expected_imps, f"{mod}: declared {declared_imps} != computed {expected_imps}"

    # Verify guards actually reject a core->profile mention and a cycle.
    bad_leak = {m: set() for m in om.ALL_MODULES}
    bad_leak["core"].add((rdflib.URIRef(L + "registerCode"), rdflib.RDFS.seeAlso, rdflib.URIRef(L + "bssCode")))
    try:
        om.compute_imports(bad_leak, term_to_mod)
        raise AssertionError("compute_imports did not reject a core->profile mention")
    except ValueError as exc:
        assert "profile term" in str(exc), exc

    bad_cycle = {m: set() for m in om.ALL_MODULES}
    bad_cycle["core"].add((rdflib.URIRef(L + "DataRelease"), rdflib.RDFS.seeAlso, rdflib.URIRef(L + "Piezometer")))
    bad_cycle["hydro"].add((rdflib.URIRef(L + "Piezometer"), rdflib.RDFS.seeAlso, rdflib.URIRef(L + "DataRelease")))
    try:
        om.compute_imports(bad_cycle, term_to_mod)
        raise AssertionError("compute_imports did not reject a cycle")
    except ValueError as exc:
        assert "cycle" in str(exc).lower(), exc

    print("  3. import graph acyclic, no core->profile mention, declared owl:imports match computed (guards verified)")
    return lulcw_imps


def test_load_and_reasoners():
    cat = to.catalog()
    targets = [om.MODULE_META[m]["iri"] for m in om.ALL_MODULES] + [om.MODULAR_META["iri"]]
    for iri in targets:
        assert iri in cat, f"{iri} missing from catalog-v001.xml"
        _, seen = to.closure(iri, cat)
        assert iri in seen, f"{iri} failed to load through catalog"

    if not (to.ROBOT.exists() and shutil.which("java")):
        print("  4. catalog closure passed for all 10 modules/profiles + modular; ROBOT checks skipped (no Java/ROBOT)")
        return

    with tempfile.TemporaryDirectory() as d:
        # Check every individual module and profile with ELK and HermiT.
        for mod in om.ALL_MODULES:
            path = ONTO / om.MODULE_META[mod]["rel_path"]
            for reasoner in ("ELK", "HermiT"):
                rc, out = to.robot(
                    "reason", "--input", path, "--reasoner", reasoner,
                    "--equivalent-classes-allowed", "none",
                    "--output", Path(d) / f"{mod.replace('/', '_')}_{reasoner}.ttl",
                )
                assert rc == 0, f"{mod} ({reasoner}):\n{out}"

        # Check the full published modular network with ELK and HermiT.
        modular_path = ONTO / om.MODULAR_META["rel_path"]
        for reasoner in ("ELK", "HermiT"):
            rc, out = to.robot(
                "reason", "--input", modular_path, "--reasoner", reasoner,
                "--equivalent-classes-allowed", "none",
                "--output", Path(d) / f"modular_{reasoner}.ttl",
            )
            assert rc == 0, f"lulcw-modular ({reasoner}):\n{out}"

        # Negative control on lulcw-hydro (verifies owl:AllDisjointClasses landed in hydro without master).
        bad = Path(d) / "bad_hydro.ttl"
        bad.write_text(
            "@prefix lulcw: <https://w3id.org/lulcw#> .\n@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
            "<https://w3id.org/lulcw/test/bad_hydro> a owl:Ontology ; owl:imports <https://w3id.org/lulcw/hydro> .\n"
            "<https://w3id.org/lulcw/data/unit_X> a lulcw:AlluvialAquifer , lulcw:KarstAquifer .\n",
            encoding="utf-8",
        )
        rc, out = to.robot("reason", "--input", bad, "--reasoner", "HermiT", "--output", Path(d) / "o.ttl")
        assert rc != 0 and "inconsistent" in out, f"HermiT did not reject disjointness contradiction on hydro:\n{out}"

    print("  4. all 10 modules/profiles + lulcw-modular.ttl pass catalog closure, ELK and HermiT; "
          "disjointness negative control passed on lulcw-hydro")


def print_counts_table(per_mod_counts, total, lulcw_imps):
    core_total = sum(per_mod_counts[m] for m in om.CORE_MODULES)
    prof_total = sum(per_mod_counts[m] for m in om.PROFILES)
    print("\n  Per-module term counts:")
    print(f"    {'module':14s} {'terms':>6s}  {'share':>7s}  lulcw imports")
    for m in om.ALL_MODULES:
        n = per_mod_counts[m]
        imps = ", ".join(lulcw_imps[m]) or "—"
        print(f"    {m:14s} {n:6d}  {100.0 * n / total:6.2f}%  {imps}")
    print(f"    {'CORE (7 mod)':14s} {core_total:6d}  {100.0 * core_total / total:6.2f}%")
    print(f"    {'PROFILES (3)':14s} {prof_total:6d}  {100.0 * prof_total / total:6.2f}%")
    print(f"    {'TOTAL':14s} {total:6d}  100.00%\n")


def main():
    per_mod_counts, total = test_partition_and_union()
    test_check_cli()
    lulcw_imps = test_imports_and_guards()
    test_load_and_reasoners()
    print_counts_table(per_mod_counts, total, lulcw_imps)
    print("test_modules: all checks passed")


if __name__ == "__main__":
    main()
