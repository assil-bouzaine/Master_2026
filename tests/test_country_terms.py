"""Checks of the France-term inventory (docs/v5_plan.md, R2.2).

    PFE_DATASET=v4 python -m tests.test_country_terms

Small fixtures check why a term matches. The real ontology check guards the exact term
set and confirms that its BD LISA code property is a name match. No model is fitted.
"""
from collections import Counter, defaultdict
from unittest.mock import patch

import rdflib

from src.kg import country_terms as C
from src.kg import term_usage as U

FIXTURE = '''
@prefix lulcw: <https://w3id.org/lulcw#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
lulcw:bnpeCode a owl:DatatypeProperty ; rdfs:label "BNPE code"@en ;
    skos:definition "Code of a French facility."@en .
lulcw:GenericSource a owl:Class ; skos:definition "A unit taken from BD LISA."@en .
lulcw:Plain a owl:Class ; rdfs:label "Design of a plain"@en ;
    skos:definition "No source is specified; BSSness is not a database name."@en .
lulcw:Department a owl:Class ; rdfs:label "Département"@fr .
lulcw:Weather a owl:Class ; rdfs:comment "Provided by Météo-France."@en .
lulcw:rpgEdition a owl:DatatypeProperty .
'''


def test_fixture():
    graph = rdflib.Graph().parse(data=FIXTURE, format="turtle")
    rows = {row["term"]: row for row in C.inventory(graph)}
    assert len(rows) == 5 and "Plain" not in rows
    bnpe = rows["bnpeCode"]
    assert bnpe["classification"] == "name" and bnpe["kind"] == "datatype property"
    assert set(bnpe["tokens"]) == {"bnpe", "france"}
    assert set(bnpe["fields"]) == {"name: IRI local name", "name: rdfs:label", "text: skos:definition"}
    assert bnpe["excerpt"] == "BNPE code"
    source = rows["GenericSource"]
    assert source["classification"] == "text-only" and source["tokens"] == ("bdlisa",)
    assert source["fields"] == ("text: skos:definition",)
    department = rows["Department"]
    assert department["classification"] == "name" and department["tokens"] == ("departement",)
    assert department["fields"] == ("name: rdfs:label",)
    assert department["excerpt"] == "Département"
    weather = rows["Weather"]
    assert weather["classification"] == "text-only"
    assert set(weather["tokens"]) == {"meteo_france", "france"}
    assert weather["fields"] == ("text: rdfs:comment",)
    assert weather["excerpt"] == "Provided by Météo-France."
    assert rows["rpgEdition"]["tokens"] == ("rpg",)
    assert rows["rpgEdition"]["fields"] == ("name: IRI local name",)
    assert all(row["usage"] == C.NO_USAGE for row in rows.values())
    counts = C.annotation_counts(graph)
    assert counts == {"skos:definition": 3, "rdfs:comment": 1, "skos:scopeNote": 0,
                      "skos:example": 0, "dcterms:description": 0}
    print("  1. six-term fixture: name/text-only precedence, tokens, fields, accents and excerpts pass")


def test_aliases():
    cases = {"BD LISA": "bdlisa", "bDlIsA": "bdlisa", "BNPE": "bnpe", "BSS": "bss",
             "RPG": "rpg", "SAFRAN": "safran", "SIM2": "safran", "Sandre": "sandre",
             "ADES": "ades", "BD TOPO": "bdtopo", "bdtopo": "bdtopo", "Carthage": "carthage",
             "Hub'Eau": "hubeau", "Hub’Eau": "hubeau", "hubeau": "hubeau", "BRGM": "brgm",
             "IGN": "ign", "Météo-France": "meteo_france", "Agreste": "agreste", "SMNPR": "smnpr",
             "OFB": "ofb", "Onema": "ofb", "INSEE": "insee", "Lambert-93": "lambert93",
             "Lambert93": "lambert93", "EPSG:2154": "lambert93", "FRDG243": "frdg", "FRDG": "frdg",
             "SIERM": "sierm", "France": "france", "French": "france", "français": "france",
             "française": "france", "Roussillon": "roussillon", "Pyrénées-Orientales": "pyrenees_orientales",
             "département": "departement"}
    for value, token in cases.items():
        assert token in C.matched_tokens(value), (value, token)
    for value in ("design", "bssness", "Frenchman", "xBNPE", "rpgExtra", "SAFRANISH"):
        assert not C.matched_tokens(value), value
    assert "bnpe" in C.matched_tokens("bnpeCode", local_name=True)
    assert "bdlisa" in C.matched_tokens("BDLISACode", local_name=True)
    assert "meteo_france" in C.matched_tokens("meteo_france", local_name=True)
    print(f"  2. {len(cases)} alias/accent cases, word boundaries and identifier splitting pass")


def test_usage_categories():
    terms = dict.fromkeys(("data", "rule", "shape", "query", "alignment", "axiom", "unused"), "class")
    data = defaultdict(Counter, {"data": Counter(predicate=1)})
    mentions = [Counter(rule=1), Counter(shape=1), Counter(query=1), Counter(alignment=1)]
    structural = Counter({term: 1 for term in terms if term != "unused"})
    manifest = {"released": "fixture"}
    with (patch.object(U.release, "check", return_value=manifest),
          patch.object(U, "kg_store", return_value=object()),
          patch.object(U, "data_counts", return_value=data),
          patch.object(U, "mentions", side_effect=mentions)):
        categories, got_manifest = C.usage_categories(terms, structural)
    assert got_manifest == manifest
    assert categories == {"data": C.STATUSES[0], "rule": C.STATUSES[1], "shape": C.STATUSES[1],
                          "query": C.STATUSES[1], "alignment": C.STATUSES[1], "axiom": C.STATUSES[2],
                          "unused": C.STATUSES[3]}
    print("  3. existing usage-category precedence includes rules, shapes, queries and alignments")


def test_real_ontology():
    graph = rdflib.Graph().parse(U.ONTO / "lulcw.ttl")
    terms, _ = U.declared()
    rows = C.inventory(graph, terms)
    assert rows and rows == C.inventory(graph)
    bdlisa = next(row for row in rows if row["term"] == "bdlisaCode")
    assert bdlisa["classification"] == "name" and "bdlisa" in bdlisa["tokens"]
    assert all(row["kind"] == terms[row["term"]] for row in rows)
    output = C.report(rows, len(terms), C.annotation_counts(graph))
    assert "generated" in output.splitlines()[0]
    assert "**49**" in output and "usage not checked" in output
    assert output.index("## Name matches") < output.index("## Text-only matches")
    assert all(len(row["excerpt"]) <= 100 for row in rows)
    print(f"  4. real ontology: {len(terms)} declared terms, {len(rows)} matches, bdlisaCode is a name match")


if __name__ == "__main__":
    test_fixture()
    test_aliases()
    test_usage_categories()
    test_real_ontology()
    print("test_country_terms: all checks passed")
