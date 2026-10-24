"""Quality gates of the LULC-Water ontology (docs/ontology_design.md §5; run on every change).

    python -m tests.test_ontology          # needs Java 17 and tools/robot.jar for gates 5-7

1. Every module of ontology/catalog-v001.xml parses, and every owl:imports resolves to a file
   listed in the catalog (the network loads offline).
2. Each module has a title, a description and a licence; lulcw.ttl has a version IRI.
3. Every lulcw: term has exactly one label in English and one in French (rdfs:label, and
   skos:prefLabel for concepts) and an English skos:definition.
4. Every lulcw: IRI used anywhere is declared in lulcw.ttl (catches typos), and every reused
   class or property in our modules is declared in the import closure, i.e. was checked at
   its source and copied locally (CLAUDE.md rule 12).
5. ROBOT reason with ELK and HermiT: the network is consistent, no class is unsatisfiable and
   no two named classes are inferred equivalent.
6. Negative control: a unit typed both alluvial and karst (disjoint) makes HermiT fail, so the
   reasoner gate can fail.
7. ROBOT report on lulcw.ttl with ontology/report_profile.txt: no ERROR. The profile drops two
   OBO conventions that gate 3 replaces (one label per language is not "multiple labels"; the
   definitions are skos:definition, not IAO:0000115). The reused W3C and OGC vocabularies are
   not reported on: their own label conventions are not ours to change.
The OOPS! pitfall scan is a web service and is run separately (docs/notes/step12_ontology.md).
"""
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import rdflib
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from src.config import ROOT

ONTO = ROOT / "ontology"
ROBOT = ROOT / "tools" / "robot.jar"
L = "https://w3id.org/lulcw#"
DCT = rdflib.Namespace("http://purl.org/dc/terms/")
BUILTIN = (str(RDF), str(RDFS), str(OWL), "http://www.w3.org/2001/XMLSchema#")
DECLARED = (OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty,
            RDFS.Datatype, OWL.NamedIndividual)


def catalog():
    """Import IRI -> local file, from catalog-v001.xml."""
    root = ET.parse(ONTO / "catalog-v001.xml").getroot()
    return {u.get("name"): ONTO / u.get("uri") for u in root.iter() if u.tag.endswith("uri")}


def closure(entry, cat):
    """The graph of an ontology and of everything it imports, through the catalog."""
    g, todo, seen = rdflib.Graph(), [entry], set()
    while todo:
        iri = todo.pop()
        if iri in seen:
            continue
        seen.add(iri)
        part = rdflib.Graph().parse(cat[iri])
        g += part
        todo += [str(o) for o in part.objects(None, OWL.imports)]
    return g, seen


def test_modules_load(cat):
    for iri, f in cat.items():
        g = rdflib.Graph().parse(f)
        assert (rdflib.URIRef(iri), RDF.type, OWL.Ontology) in g, f"{f.name}: not {iri}"
        missing = [str(o) for o in g.objects(None, OWL.imports) if str(o) not in cat]
        assert not missing, f"{f.name} imports IRIs outside the catalog: {missing}"
    _, seen = closure("https://w3id.org/lulcw/meta", cat)
    assert seen == set(cat), f"modules not reached from the meta-ontology: {set(cat) - seen}"
    print(f"  1. {len(cat)} modules parse; the meta-ontology reaches all of them")


def test_metadata(cat):
    for iri in [i for i in cat if "/imports/" not in i]:
        g, o = rdflib.Graph().parse(cat[iri]), rdflib.URIRef(iri)
        for p in (DCT.title, DCT.description, DCT.license):
            assert g.value(o, p) is not None, f"{iri}: no {p}"
    g = rdflib.Graph().parse(cat["https://w3id.org/lulcw"])
    assert g.value(rdflib.URIRef("https://w3id.org/lulcw"), OWL.versionIRI) is not None
    print("  2. every own module has a title, a description and a licence; lulcw has a version IRI")


def test_labels_and_definitions(core):
    terms = {s for s in core.subjects(RDF.type, None)
             if isinstance(s, rdflib.URIRef) and str(s).startswith(L)}
    bad = []
    for t in sorted(terms):
        for p in [RDFS.label] + ([SKOS.prefLabel] if (t, SKOS.inScheme, None) in core else []):
            langs = sorted(lab.language or "" for lab in core.objects(t, p))
            if langs != ["en", "fr"]:
                bad.append(f"{t.removeprefix(L)} {p.split('#')[-1]} {langs}")
        if not any(d.language == "en" for d in core.objects(t, SKOS.definition)):
            bad.append(f"{t.removeprefix(L)} has no English skos:definition")
    assert not bad, "\n".join(bad)
    print(f"  3. {len(terms)} lulcw terms: one English and one French label each, and a definition")


def test_declarations(core, cat):
    declared = {s for s in core.subjects(RDF.type, None) if str(s).startswith(L)}
    own = rdflib.Graph()
    for iri, f in cat.items():
        if "/imports/" not in iri:
            own.parse(f)
    used = {x for t in own for x in t if isinstance(x, rdflib.URIRef) and str(x).startswith(L)}
    assert not used - declared, f"lulcw IRIs used but not declared: {sorted(used - declared)}"
    net, _ = closure("https://w3id.org/lulcw/meta", cat)
    known = {s for s in net.subjects(RDF.type, None) if any((s, RDF.type, k) in net for k in DECLARED)}
    reused = set()
    for s, p, o in own:
        if p in (RDFS.subClassOf, RDFS.subPropertyOf, RDFS.domain, RDFS.range, RDF.type,
                 SKOS.closeMatch, SKOS.exactMatch):
            reused |= {x for x in (s, o) if isinstance(x, rdflib.URIRef)}
        reused.add(p)
    reused = {x for x in reused if not str(x).startswith((L, *BUILTIN))
              and not str(x).startswith("https://w3id.org/lulcw")}
    missing = sorted(str(x) for x in reused - known)
    assert not missing, "reused terms not declared in any local copy:\n" + "\n".join(missing)
    print(f"  4. every lulcw IRI is declared; {len(reused)} reused terms all come from local copies")


def robot(*args):
    r = subprocess.run(["java", "-jar", str(ROBOT), "--catalog", str(ONTO / "catalog-v001.xml"),
                        *map(str, args)], capture_output=True, text=True, cwd=ONTO)
    return r.returncode, r.stdout + r.stderr


def test_reasoners():
    with tempfile.TemporaryDirectory() as d:
        for reasoner in ("ELK", "HermiT"):
            rc, out = robot("reason", "--input", ONTO / "lulcw-meta.ttl", "--reasoner", reasoner,
                            "--equivalent-classes-allowed", "none", "--output", Path(d) / "r.ttl")
            assert rc == 0, f"{reasoner}:\n{out}"
    print("  5. ELK and HermiT: consistent, no unsatisfiable class, no inferred equivalence")


def test_negative_control():
    with tempfile.TemporaryDirectory() as d:
        bad = Path(d) / "bad.ttl"
        bad.write_text(
            "@prefix lulcw: <https://w3id.org/lulcw#> .\n@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
            "<https://w3id.org/lulcw/test/bad> a owl:Ontology ; owl:imports <https://w3id.org/lulcw/meta> .\n"
            "<https://w3id.org/lulcw/data/unit_X> a lulcw:AlluvialAquifer , lulcw:KarstAquifer .\n")
        rc, out = robot("reason", "--input", bad, "--reasoner", "HermiT", "--output", Path(d) / "o.ttl")
    assert rc != 0 and "inconsistent" in out, f"HermiT did not reject the contradiction:\n{out}"
    print("  6. negative control: a unit both alluvial and karst is rejected as inconsistent")


def test_report():
    with tempfile.TemporaryDirectory() as d:
        out_tsv = Path(d) / "report.tsv"
        robot("report", "--input", ONTO / "lulcw.ttl", "--profile", ONTO / "report_profile.txt",
              "--fail-on", "none", "--output", out_tsv)
        rows = [r.split("\t") for r in out_tsv.read_text().splitlines()[1:]]
    errors = [r for r in rows if r and r[0] == "ERROR"]
    assert not errors, "\n".join("\t".join(r[:3]) for r in errors)
    print(f"  7. ROBOT report on lulcw.ttl: no ERROR ({len(rows)} INFO/WARN rows)")


def main():
    cat = catalog()
    core = rdflib.Graph().parse(cat["https://w3id.org/lulcw"])
    test_modules_load(cat)
    test_metadata(cat)
    test_labels_and_definitions(core)
    test_declarations(core, cat)
    if not (ROBOT.exists() and shutil.which("java")):
        print("  5-7 skipped: Java or tools/robot.jar missing (docs/notes/step12_ontology.md)")
        return
    test_reasoners()
    test_negative_control()
    test_report()
    print("test_ontology: all checks passed")


if __name__ == "__main__":
    main()
