"""Check the generated ontology documentation and its freshness gate (v5 plan R2.4).

    PFE_DATASET=v5 python -m tests.test_ontology_docs

The freshness fixtures never run pyLODE. When the separate 3.6.1 tool is installed,
a tiny bilingual ontology checks deterministic rendering, coverage of classes,
a property and a SKOS concept, and rejection after a term is removed from the HTML.
Supplement fixtures check source-derived bilingual values, escaping, SKOS links,
anchor collisions, insertion position, and that rendered terms are never repeated.
The real index must match all current repository module/profile sources.
"""
import json
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from unittest.mock import patch

import rdflib
from rdflib.namespace import RDF, RDFS, SKOS

from src.config import ROOT
from src.kg import ontology_docs as docs


def fixture_source(ontology):
    """An isolated concept must be documented even when nothing else links to it."""
    source = ontology / "modules/lulcw-fixture.ttl"
    source.parent.mkdir(parents=True)
    source.write_text('''@prefix lulcw: <https://w3id.org/lulcw#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

<https://w3id.org/lulcw/core> a owl:Ontology ;
    dcterms:title "Documentation fixture"@en ;
    owl:versionInfo "fixture" .

lulcw:FixtureOne a owl:Class ;
    rdfs:label "first class"@en, "première classe"@fr ;
    skos:definition "The first class in this documentation test."@en ;
    lulcw:definedInModule <https://w3id.org/lulcw/core> .
lulcw:FixtureTwo a owl:Class ;
    rdfs:label "second class"@en, "deuxième classe"@fr ;
    skos:definition "The second class in this documentation test."@en ;
    lulcw:definedInModule <https://w3id.org/lulcw/core> .
lulcw:fixtureRelation a owl:ObjectProperty ;
    rdfs:domain lulcw:FixtureOne ; rdfs:range lulcw:FixtureTwo ;
    rdfs:label "fixture relation"@en, "relation de test"@fr ;
    skos:definition "Relates the two classes in this test."@en ;
    lulcw:definedInModule <https://w3id.org/lulcw/core> .
lulcw:FixtureConcept a skos:Concept ;
    rdfs:label "fixture concept"@en, "concept de test"@fr ;
    skos:definition "An isolated controlled value in this test."@en ;
    lulcw:definedInModule <https://w3id.org/lulcw/core> .
''', encoding="utf-8")
    return source


def expect_error(operation, *names):
    try:
        operation()
    except docs.DocumentationError as error:
        for name in names:
            assert name in str(error), (name, str(error))
        return
    raise AssertionError(f"Expected DocumentationError naming {names}")


def test_freshness():
    with tempfile.TemporaryDirectory(prefix="t90-freshness-") as folder:
        ontology = Path(folder) / "ontology"
        out = Path(folder) / "html"
        out.mkdir()
        source = fixture_source(ontology)
        record, terms = docs.source_record(source, ontology)
        assert len(terms) == record["terms"] == 4
        assert record["title"] == "Documentation fixture" and record["version"] == "fixture"
        page = out / record["page"]
        page.write_text("<!doctype html><p>Freshness fixture</p>", encoding="utf-8")
        docs.write_index([record], out)
        # Prove the freshness gate is independent of both the tool and its discovery.
        with (patch.object(docs, "find_pylode", side_effect=AssertionError("pyLODE discovery")),
              patch.object(docs.subprocess, "run", side_effect=AssertionError("subprocess"))):
            assert docs.check(out, ontology)["sources"] == [record]
            original = source.read_bytes()
            source.write_bytes(original + b"\n")
            expect_error(lambda: docs.check(out, ontology), page.name, "stale")
            source.write_bytes(original)
            page.unlink()
            expect_error(lambda: docs.check(out, ontology), page.name, "missing page")
            source.write_bytes(original + b"\n")
            expect_error(lambda: docs.check(out, ontology), "stale", "missing page")
            source.write_bytes(original)
            page.write_text("<!doctype html><p>Freshness fixture</p>", encoding="utf-8")
            docs.write_index([record], out, [f"{page.name}: missing fixture term"])
            expect_error(lambda: docs.check(out, ontology), "incomplete build", "missing fixture term")
            docs.write_index([record], out)
            extra = ontology / "profiles/lulcw-fixture-profile.ttl"
            extra.parent.mkdir()
            extra.write_bytes(original)
            expect_error(lambda: docs.check(out, ontology), "lulcw-fixture-profile.html")
            extra.unlink()
            source.unlink()
            expect_error(lambda: docs.check(out, ontology), page.name, "no longer exists")
    print("  Freshness: current passes; changed byte, missing page, added/deleted sources are named")


def test_completeness_parser():
    with tempfile.TemporaryDirectory(prefix="t90-coverage-") as folder:
        page = Path(folder) / "coverage.html"
        terms = [docs.L + name for name in ("FixtureOne", "FixtureTwo", "fixtureRelation")]
        page.write_text(
            '<div id="FixtureOne"></div><a href="https://w3id.org/lulcw#FixtureTwo">second</a>'
            '<div class="property entity" id="fixturerelation"><table><tr><td>'
            '<code>https://w3id.org/lulcw#fixtureRelation</code></td></tr></table></div>',
            encoding="utf-8")
        docs.check_completeness(page, terms)
        page.write_text('<p>https://w3id.org/lulcw#FixtureOne</p>'
                        '<script>{"@id":"https://w3id.org/lulcw#FixtureTwo"}</script>'
                        '<div class="property entity" id="unrelated"><code>unrelated-IRI</code>'
                        '<p><code>https://w3id.org/lulcw#fixtureRelation</code></p></div>',
                        encoding="utf-8")
        expect_error(lambda: docs.check_completeness(page, terms), *terms)
    print("  Coverage parser: exact anchors, links and anchored IRI definitions pass; prose/JSON do not")


def test_tool_guards():
    with (patch.object(docs.shutil, "which", return_value=None),
          patch.object(docs.Path, "is_file", return_value=False)):
        expect_error(docs.find_pylode, "missing", docs.INSTALL)
    with (patch.object(docs.shutil, "which", return_value="/fixture/pylode"),
          patch.object(docs.subprocess, "run", return_value=subprocess.CompletedProcess(
              [], 0, stdout="3.6.0\n", stderr=""))):
        expect_error(docs.find_pylode, "3.6.1", "3.6.0", docs.INSTALL)
    ordered_list = {"@list": ["second", "first"]}
    assert docs._ordered_json(ordered_list) == ordered_list
    print("  Tool guards: absent and wrong versions refused; JSON-LD ordered lists preserved")


def test_normalization():
    english = ('<a class="hover_property" href="https://w3id.org/lulcw#definedInModule" '
               'title="annotation description">Defined In Module</a>')
    french = english.replace('>Defined In Module<', '>Défini Dans Le Module<')
    first, second = (docs.normalize_html(value) for value in (english, french))
    assert first == second
    assert 'Defined In Module / Défini Dans Le Module' in first
    assert 'title="annotation description"' in first
    assert docs.normalize_html(first) == first
    prose = '<p>Défini Dans Le Module</p>'
    assert docs.normalize_html(prose) == prose
    print("  Normalization: random heading language is stable, bilingual and idempotent; prose is preserved")


def test_supplement():
    with tempfile.TemporaryDirectory(prefix="t90b-supplement-") as folder:
        ontology = Path(folder) / "ontology"
        source = fixture_source(ontology)
        graph = rdflib.Graph().parse(source, format="turtle")
        concept = rdflib.URIRef(docs.L + "FixtureConcept")
        scheme = rdflib.URIRef(docs.L + "FixtureScheme")
        observable = rdflib.URIRef(docs.L + "FixtureObservable")
        observable_type = rdflib.URIRef("http://www.w3.org/ns/sosa/ObservableProperty")
        header = next(graph.subjects(RDF.type, rdflib.OWL.Ontology))
        graph.bind("sosa", rdflib.Namespace("http://www.w3.org/ns/sosa/"))
        graph.add((concept, RDF.type, rdflib.URIRef(docs.L + "FixtureOne")))
        graph.add((concept, SKOS.inScheme, scheme))
        graph.add((concept, SKOS.broader, rdflib.URIRef(docs.L + "FixtureTwo")))
        graph.add((concept, SKOS.notation, rdflib.Literal('A<&>"')))
        graph.add((concept, SKOS.prefLabel, rdflib.Literal('English <script> & "label"', lang="en")))
        graph.add((concept, SKOS.prefLabel, rdflib.Literal("Français <étiquette>", lang="fr")))
        graph.add((concept, SKOS.definition, rdflib.Literal("Définition <fr> & suite.", lang="fr")))
        for term, kind in ((scheme, SKOS.ConceptScheme), (observable, observable_type)):
            graph.add((term, RDF.type, kind))
            graph.add((term, docs.DEFINED_IN_MODULE, header))
            graph.add((term, RDFS.label, rdflib.Literal('Label <b> & "quoted"', lang="en")))
            graph.add((term, RDFS.label, rdflib.Literal("Étiquette <fr>", lang="fr")))
            graph.add((term, SKOS.definition, rdflib.Literal("Definition from the source.", lang="en")))
        graph.serialize(source, format="turtle")
        _, terms = docs.source_record(source, ontology)
        # The property has a label-derived id, as some real pyLODE properties do.
        rendered = ('<div class="property entity" id="FixtureOne"></div>'
                    '<div class="property entity" id="FixtureTwo"></div>'
                    '<div class="property entity" id="fixture-relation">'
                    f'<code>{docs.L}fixtureRelation</code></div>')
        original = '<html><body><main>' + rendered + '</main><footer>End</footer></body></html>'
        first = docs.supplement_html(original, source, terms)
        supplement = first.split('<section>')[1].split('</section>')[0]
        assert '<h2>Terms not rendered by pyLODE</h2>' in supplement
        assert source.name in supplement and docs.sha256(source)[:12] in supplement
        assert docs.PYLODE_VERSION in supplement
        assert supplement.count('class="property entity"') == 3
        for term in ("FixtureConcept", "FixtureObservable", "FixtureScheme"):
            assert f'id="{term}"' in supplement
            assert f'href="{docs.L}{term}"><code>{docs.L}{term}</code>' in supplement
        assert supplement.index('id="FixtureConcept"') < supplement.index('id="FixtureObservable"')
        assert supplement.index('id="FixtureObservable"') < supplement.index('id="FixtureScheme"')
        for term in ("FixtureOne", "FixtureTwo", "fixtureRelation"):
            assert f'id="{term}"' not in supplement, term
        assert 'lulcw:FixtureOne' in supplement and 'skos:Concept' in supplement
        assert 'skos:ConceptScheme' in supplement and 'sosa:ObservableProperty' in supplement
        for predicate in ("rdfs:label", "skos:prefLabel", "skos:definition"):
            assert supplement.index(predicate + ' (en)') < supplement.index(predicate + ' (fr)')
        assert 'English &lt;script&gt; &amp; &quot;label&quot;' in supplement
        assert 'Français &lt;étiquette&gt;' in supplement
        assert 'Définition &lt;fr&gt; &amp; suite.' in supplement
        assert 'Label &lt;b&gt; &amp; &quot;quoted&quot;' in supplement
        assert 'A&lt;&amp;&gt;&quot;' in supplement
        assert '<script>' not in supplement and '<b>' not in supplement
        for predicate in ("skos:inScheme", "skos:broader", "skos:notation"):
            assert predicate in supplement
        assert f'href="{scheme}"' in supplement and f'href="{docs.L}FixtureTwo"' in supplement
        assert '</section>\n</main>' in first
        assert docs.supplement_html(original, source, list(reversed(terms))) == first
        assert docs.supplement_html(first, source, terms) == first, "Supplement must be idempotent"
        assert docs.missing_terms(first, terms) == []
        body_only = original.replace('<main>', '').replace('</main>', '')
        assert '</section>\n</body>' in docs.supplement_html(body_only, source, terms)
        expect_error(lambda: docs.supplement_html(rendered, source, terms), source.name, "closing")
        ids = {"FixtureConcept"}
        entry = docs._supplement_entry(graph, str(concept), ids)
        assert 'id="supp-FixtureConcept"' in entry
        assert 'id="supp-supp-FixtureConcept"' in docs._supplement_entry(graph, str(concept), ids)
        # Read a modified source again: a supplement must not contain copied fixture text.
        graph.set((concept, SKOS.prefLabel, rdflib.Literal("Changed at source", lang="en")))
        graph.serialize(source, format="turtle")
        assert "Changed at source" in docs.supplement_html(original, source, terms)
    print("  Supplement: source values, compact types, bilingual order, escaping, SKOS links, "
          "IRI order, collision fallback, insertion, no duplicates and idempotence pass")


def test_pylode_fixture():
    try:
        docs.find_pylode()
    except docs.DocumentationError as error:
        if "pyLODE is missing" in str(error):
            print("  pyLODE rendering skipped: pyLODE is not installed")
            return
        raise
    with tempfile.TemporaryDirectory(prefix="t90-render-") as folder:
        ontology = Path(folder) / "ontology"
        source = fixture_source(ontology)
        outputs = [Path(folder) / name for name in ("first", "second")]
        for out in outputs:
            docs.build(out, ontology)
        first, second = (out / (source.stem + '.html') for out in outputs)
        for path in outputs[0].iterdir():
            assert path.read_bytes() == (outputs[1] / path.name).read_bytes(), path.name
        print("  pyLODE fixture: two builds have identical page and index bytes")
        _, terms = docs.source_record(source, ontology)
        supplement = first.read_text(encoding="utf-8").split('<section>')[1].split('</section>')[0]
        assert 'id="FixtureConcept"' in supplement
        for rendered in ("FixtureOne", "FixtureTwo", "fixtureRelation"):
            assert docs.L + rendered not in supplement, rendered
        print("  pyLODE fixture: isolated concept supplemented; rendered classes/property never repeated")
        for local in ("fixtureRelation", "FixtureConcept"):
            removed = docs.L + local
            second.write_text(first.read_text(encoding="utf-8").replace(removed, "removed-IRI")
                              .replace(local, "removed-local-name"), encoding="utf-8")
            expect_error(lambda: docs.check_completeness(second, terms), removed)
        print("  pyLODE fixture: deleting a rendered or supplemented term is rejected")
        docs.check_completeness(first, terms)
        print("  pyLODE fixture: all four terms pass completeness")


def test_repository_current():
    result = subprocess.run([sys.executable, "-m", "src.kg.ontology_docs", "--check"],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, f"Repository --check failed:\n{result.stdout}\n{result.stderr}"
    manifest = json.loads((docs.OUTPUT / "index.json").read_text(encoding="utf-8"))
    assert len(manifest["sources"]) == len(docs.sources()) == 10
    print(f"  Repository freshness: {result.stdout.strip()}")


def main():
    started = time.perf_counter()
    failures = []
    for test in (test_freshness, test_completeness_parser, test_tool_guards, test_normalization,
                 test_supplement, test_pylode_fixture, test_repository_current):
        try:
            test()
        except Exception:
            failures.append(test.__name__)
            traceback.print_exc()
    print(f"test_ontology_docs: {len(failures)} failures ({time.perf_counter() - started:.2f} s)", flush=True)
    if failures:
        raise AssertionError(f"Failed checks: {', '.join(failures)}")


if __name__ == "__main__":
    main()
