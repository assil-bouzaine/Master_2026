"""Local copies of the reused vocabulary terms (task 12.4): ontology/imports/*_terms.ttl.

    .venv/bin/python -m src.kg.build_imports          # cached downloads, then ROBOT extracts
    .venv/bin/python -m src.kg.build_imports --only saref envo   # only these sources
    .venv/bin/python -m src.kg.build_imports --only gemet        # GEMET concepts (rdflib copy)

Each source is downloaded once into data/raw/vocab/ (content negotiation for the W3C
namespaces; the GeoSPARQL 1.1 file from OGC's 1.1.0 tag, because the OGC server now answers
with a catalogue page; SWEET from its GitHub repository). Every download is logged in
data/raw/vocab/sources.json with its URL, date, size and sha256. ROBOT 1.9.11
(tools/robot.jar) then extracts, with the MIREOT method, only the terms LULC-Water uses:
their declarations, labels, definitions and hierarchy, but not their domain or range axioms.
That keeps the imports small and keeps HermiT away from xsd:date ranges (OWL-Time), which it
rejects. The GWML2/HyFO terms have no source file (docs/ontology_design.md §1): their extract,
ontology/imports/gwml2_hyfo_terms.ttl, is written by hand from the SAWGraph documentation.
HY_Features (OGC 14-111) has no OWL file either: the OGC definitions server returns one SKOS page
per term (FeatureType and skos:Concept; HY_FlowPath also owl:Class). Those pages are downloaded and
logged here (HYF_PAGES, checked 2026-11-06), and ontology/imports/hyf_terms.ttl is written by hand
from them.
Added 2026-11-26 (v5 plan R2.3): SAREF4WATR v2.1.1 (ETSI) and ENVO's 2026-10-23 release, both from
versioned URLs, and three more SWEET modules (rivers and canals, hydrological phenomena, agriculture).
MIREOT keeps an individual's label and comment (SAREF4WATR's water uses and flow properties), not its
class membership. SAREF4WATR's licence is ETSI's BSD-3-Clause, ENVO's and SWEET's CC0.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

import rdflib
import requests
from rdflib.namespace import OWL

from src.config import RAW, ROOT

VOCAB = RAW / "vocab"
OUT = ROOT / "ontology" / "imports"
ROBOT = ROOT / "tools" / "robot.jar"
SOSA, PROV = "http://www.w3.org/ns/sosa/", "http://www.w3.org/ns/prov#"
TIME, SKOS = "http://www.w3.org/2006/time#", "http://www.w3.org/2004/02/skos/core#"
GEO, SWEET = "http://www.opengis.net/ont/geosparql#", "http://sweetontology.net/"
S4WATR, OBO = "https://saref.etsi.org/saref4watr/", "http://purl.obolibrary.org/obo/"
SWEET_SRC = "https://raw.githubusercontent.com/ESIPFed/sweet/master/src/"

# name -> files (url, accept header), terms; the URLs and terms were checked on 2026-10-24
SOURCES = {
    "sosa": ([("sosa.ttl", "https://www.w3.org/ns/sosa/", "text/turtle")],
             [SOSA + t for t in ("Observation", "ObservableProperty", "FeatureOfInterest", "Platform",
                                 "Procedure", "hasFeatureOfInterest", "observedProperty",
                                 "hasSimpleResult", "phenomenonTime", "resultTime", "usedProcedure")]),
    "prov": ([("prov-o.ttl", "https://www.w3.org/ns/prov-o", "text/turtle")],
             [PROV + t for t in ("Entity", "Activity", "Plan", "Agent", "wasDerivedFrom",
                                 "wasGeneratedBy", "used", "generatedAtTime", "wasAttributedTo",
                                 "hadPrimarySource")]),
    "time": ([("time.ttl", "https://www.w3.org/2006/time", "text/turtle")],
             [TIME + t for t in ("TemporalEntity", "Interval", "ProperInterval", "Instant",
                                 "hasBeginning", "hasEnd", "inXSDDate")]),
    "skos": ([("skos.rdf", "https://www.w3.org/2004/02/skos/core", "application/rdf+xml")],
             [SKOS + t for t in ("Concept", "ConceptScheme", "inScheme", "topConceptOf",
                                 "hasTopConcept", "prefLabel", "altLabel", "definition",
                                 "scopeNote", "notation", "broader", "narrower", "closeMatch",
                                 "exactMatch", "broadMatch", "narrowMatch",
                                 "relatedMatch")]),     # relatedMatch: GEMET and CLC rows, 2026-11-27
    "geo": ([("geo.ttl", "https://raw.githubusercontent.com/opengeospatial/ogc-geosparql/"
                         "1.1.0-ghpages/geosparql11/geo.ttl", "text/turtle")],
            [GEO + t for t in ("SpatialObject", "Feature", "Geometry", "hasGeometry",
                               "hasDefaultGeometry", "asWKT", "sfIntersects", "sfWithin",
                               "hasMetricArea")]),       # hasMetricArea: added for 12.5
    "sweet": ([("sweet_realmHydro.ttl", SWEET_SRC + "realmHydro.ttl", "text/turtle"),
               ("sweet_matrWater.ttl", SWEET_SRC + "matrWater.ttl", "text/turtle"),
               # added 2026-11-26 (v5 plan R2.3, deeper SWEET): rivers and canals, hydrological
               # phenomena, agriculture
               ("sweet_realmHydroBody.ttl", SWEET_SRC + "realmHydroBody.ttl", "text/turtle"),
               ("sweet_phenHydro.ttl", SWEET_SRC + "phenHydro.ttl", "text/turtle"),
               ("sweet_humanAgriculture.ttl", SWEET_SRC + "humanAgriculture.ttl", "text/turtle")],
              [SWEET + "realmHydro/" + t for t in ("Aquifer", "ConfinedAquifer", "UnconfinedAquifer",
                                                   "Aquitard", "WaterTable")]
              + [SWEET + "matrWater/Groundwater"]
              + [SWEET + "realmHydroBody/" + t for t in ("River", "Canal")]
              + [SWEET + "phenHydro/" + t for t in ("Recharge", "StreamDischarge", "DeepPercolation")]
              + [SWEET + "humanAgriculture/Irrigation"]),
    # added 2026-11-26 (v5 plan R2.3), versioned files, licences checked at the source the same day:
    # SAREF4WATR v2.1.1 (ETSI, BSD-3-Clause, https://forge.etsi.org/etsi-software-license);
    # ENVO release 2026-10-23 (CC0 1.0). Terms: the asserted correspondences of
    # ontology/alignments/lulcw-saref.ttl and lulcw-envo.ttl (individuals keep label and comment).
    "saref": ([("saref4watr.ttl", "https://saref.etsi.org/saref4watr/v2.1.1/saref4watr.ttl", "text/turtle")],
              [S4WATR + t for t in ("MonitoringInfrastructure", "GaugingStation", "Intake", "Channel",
                                    "River", "Aquifer", "WaterUse", "Domestic", "Agriculture",
                                    "Industry", "FlowRate")]),
    "envo": ([("envo.owl", "http://purl.obolibrary.org/obo/envo/releases/2026-10-23/envo.owl",
               "application/rdf+xml")],
             [OBO + t for t in ("ENVO_00012408", "ENVO_01000002", "ENVO_00000022", "ENVO_00000014",
                                "ENVO_01001632")]),
}

# GEMET 4.2.3 (EEA/Eionet thesaurus, CC BY 4.0 as stated in the file), added 2026-11-27 (v5 plan R2.3). Eionet was
# unreachable, so data/raw/vocab/gemet.rdf.gz is the Internet Archive's raw copy of the official URL (logged in
# sources.json and data/README.md, 2026-11-26). GEMET is a SKOS thesaurus: its concepts are copied by rdflib (type,
# English and French preferred labels, English definition; not the broader links, whose targets the
# copy does not declare), not by ROBOT's MIREOT. Terms: the
# concepts of ontology/alignments/lulcw-gemet.ttl and its rejected ledger rows.
GEMET = "http://www.eionet.europa.eu/gemet/concept/"
GEMET_FILE = ("gemet.rdf.gz", "https://www.eionet.europa.eu/gemet/latest/gemet.rdf.gz")
GEMET_TERMS = [GEMET + c for c in ("15334", "2343", "4505", "6655", "2735", "3780", "8229", "9161", "4507",
                                   "9290", "15394", "3781", "9190", "12104", "4291", "4731", "637", "7874",
                                   "9164", "518")]


def extract_gemet(log):
    """The GEMET concepts LULC-Water names, with their labels and definition, into
    ontology/imports/gemet_terms.ttl (the file is never downloaded again here: see GEMET_FILE)."""
    import gzip
    from rdflib import Literal, URIRef
    from rdflib.namespace import DCTERMS, RDF, RDFS
    name, url = GEMET_FILE
    f = VOCAB / name
    if not f.exists():
        sys.exit(f"{f} missing: see data/README.md (GEMET and CORINE from the Internet Archive)")
    entry = log[name]
    if hashlib.sha256(f.read_bytes()).hexdigest() != entry["sha256"]:
        sys.exit(f"{f} differs from its logged sha256")
    src = rdflib.Graph()
    with gzip.open(f, "rb") as fh:
        src.parse(fh, format="xml", publicID="http://www.eionet.europa.eu/gemet/")
    sk = rdflib.Namespace(SKOS)
    out = rdflib.Graph()
    out.bind("skos", sk)
    out.bind("gemet", GEMET)
    onto = URIRef("https://w3id.org/lulcw/imports/gemet")
    out.add((onto, RDF.type, OWL.Ontology))
    out.add((onto, RDFS.comment, Literal(
        f"Copies of the GEMET concepts LULC-Water uses (type, English and French preferred labels, English "
        f"definition), built by src/kg/build_imports.py from {url} (GEMET Concepts 4.2.3 of "
        f"2021-12-06; Internet Archive copy of {entry.get('archive_snapshot', '?')}, retrieved "
        f"{entry['retrieved']}, sha256 {entry['sha256'][:12]}). Licence: CC BY 4.0 (stated in the file).")))
    out.add((onto, DCTERMS.license, URIRef("http://creativecommons.org/licenses/by/4.0/")))
    for t in GEMET_TERMS:
        c = URIRef(t)
        if (c, RDF.type, sk.Concept) not in src:
            sys.exit(f"{t} is not a skos:Concept of {name}")
        out.add((c, RDF.type, sk.Concept))
        out.add((c, RDF.type, OWL.NamedIndividual))     # an OWL declaration: SKOS concepts are individuals
        for p, langs in ((sk.prefLabel, ("en", "fr")), (sk.definition, ("en",))):
            for o in src.objects(c, p):
                if getattr(o, "language", None) in langs:
                    out.add((c, p, o))
    target = OUT / "gemet_terms.ttl"
    out.serialize(target, format="turtle")
    print(f"{target.relative_to(ROOT)}: {len(GEMET_TERMS)} concepts")


HYF = "https://www.opengis.net/def/schema/hy_features/hyf/"
HYF_PAGES = {f"hyf_{t}.ttl": HYF + t for t in ("HY_WaterBody", "HY_River", "HY_FlowPath",
                                               "HY_CatchmentRealization")}


def download(name, url, accept, log):
    """url -> data/raw/vocab/name, once (kept if it exists), and its entry in log."""
    f = VOCAB / name
    entry = log.setdefault(name, {})
    if not f.exists() or f.stat().st_size == 0:
        r = requests.get(url, headers={"Accept": accept}, timeout=60)
        r.raise_for_status()
        f.write_bytes(r.content)
        entry.update(final_url=r.url, retrieved=date.today().isoformat())
    # a file fetched before this script existed keeps its file date as retrieval date
    entry.setdefault("retrieved", date.fromtimestamp(f.stat().st_mtime).isoformat())
    entry.update(url=url, accept=accept, bytes=f.stat().st_size,
                 sha256=hashlib.sha256(f.read_bytes()).hexdigest())


def extract(name, files, terms, log):
    """ROBOT: merge the source files, MIREOT-extract the terms, set the import's IRI."""
    out = OUT / f"{name}_terms.ttl"
    entries = [log[f] for f, _, _ in files]
    note = (f"MIREOT extract (declarations, annotations, hierarchy) of the terms LULC-Water uses, "
            f"built by src/kg/build_imports.py with ROBOT from "
            + "; ".join(f"{e['url']} (retrieved {e['retrieved']}, sha256 {e['sha256'][:12]})"
                        for e in entries) + ".")
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as t:
        t.write("\n".join(terms) + "\n")
    # one input without owl:imports: ROBOT would otherwise fetch the imported modules from the
    # web, and SWEET's modules import each other (the second file then clashes with the copy)
    g = rdflib.Graph()
    for f, _, _ in files:
        g.parse(VOCAB / f)
    g.remove((None, OWL.imports, None))
    src = VOCAB / f"{name}_noimports.ttl"
    g.serialize(src, format="turtle")
    cmd = ["java", "-jar", str(ROBOT), "extract", "--input", str(src),
           "--method", "MIREOT", "--lower-terms", t.name, "--intermediates", "minimal",
            "annotate", "--ontology-iri", f"https://w3id.org/lulcw/imports/{name}",
            "--annotation", "http://www.w3.org/2000/01/rdf-schema#comment", note,
            "--output", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    Path(t.name).unlink()
    if r.returncode:
        sys.exit(f"ROBOT failed for {name}:\n{r.stdout}{r.stderr}")
    print(f"{out.relative_to(ROOT)}: {len(terms)} terms")


def main(only=None):
    """Every source, or only the names given (`--only saref envo`): the others' files are untouched."""
    VOCAB.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    log_file = VOCAB / "sources.json"
    log = json.loads(log_file.read_text()) if log_file.exists() else {}
    unknown = set(only or ()) - set(SOURCES) - {"gemet"}
    if unknown:
        sys.exit(f"unknown sources: {sorted(unknown)}; known: {sorted(SOURCES)}")
    for name, (files, terms) in SOURCES.items():
        if only and name not in only:
            continue
        for f, url, accept in files:
            download(f, url, accept, log)
        log_file.write_text(json.dumps(log, indent=1, sort_keys=True))
        extract(name, files, terms, log)
    if not only or "gemet" in only:
        extract_gemet(log)
    for f, url in HYF_PAGES.items():       # provenance of the hand-written hyf_terms.ttl
        download(f, url, "text/turtle", log)
    log_file.write_text(json.dumps(log, indent=1, sort_keys=True))


if __name__ == "__main__":
    args = sys.argv[1:]
    main(args[1:] if args[:1] == ["--only"] else None)
