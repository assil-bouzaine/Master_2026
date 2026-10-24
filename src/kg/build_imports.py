"""Local copies of the reused vocabulary terms (task 12.4): ontology/imports/*_terms.ttl.

    .venv/bin/python -m src.kg.build_imports          # cached downloads, then ROBOT extracts

Each source is downloaded once into data/raw/vocab/ (content negotiation for the W3C
namespaces; the GeoSPARQL 1.1 file from OGC's 1.1.0 tag, because the OGC server now answers
with a catalogue page; SWEET from its GitHub repository). Every download is logged in
data/raw/vocab/sources.json with its URL, date, size and sha256. ROBOT 1.9.11
(tools/robot.jar) then extracts, with the MIREOT method, only the terms LULC-Water uses:
their declarations, labels, definitions and hierarchy, but not their domain or range axioms.
That keeps the imports small and keeps HermiT away from xsd:date ranges (OWL-Time), which it
rejects. The GWML2/HyFO terms have no source file (docs/ontology_design.md §1): their extract,
ontology/imports/gwml2_hyfo_terms.ttl, is written by hand from the SAWGraph documentation.
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
                                 "exactMatch", "broadMatch", "narrowMatch")]),
    "geo": ([("geo.ttl", "https://raw.githubusercontent.com/opengeospatial/ogc-geosparql/"
                         "1.1.0-ghpages/geosparql11/geo.ttl", "text/turtle")],
            [GEO + t for t in ("SpatialObject", "Feature", "Geometry", "hasGeometry",
                               "hasDefaultGeometry", "asWKT", "sfIntersects", "sfWithin")]),
    "sweet": ([("sweet_realmHydro.ttl", "https://raw.githubusercontent.com/ESIPFed/sweet/master/"
                                        "src/realmHydro.ttl", "text/turtle"),
               ("sweet_matrWater.ttl", "https://raw.githubusercontent.com/ESIPFed/sweet/master/"
                                       "src/matrWater.ttl", "text/turtle")],
              [SWEET + "realmHydro/" + t for t in ("Aquifer", "ConfinedAquifer", "UnconfinedAquifer",
                                                   "Aquitard", "WaterTable")]
              + [SWEET + "matrWater/Groundwater"]),
}


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


def main():
    VOCAB.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    log_file = VOCAB / "sources.json"
    log = json.loads(log_file.read_text()) if log_file.exists() else {}
    for name, (files, terms) in SOURCES.items():
        for f, url, accept in files:
            download(f, url, accept, log)
        log_file.write_text(json.dumps(log, indent=1, sort_keys=True))
        extract(name, files, terms, log)


if __name__ == "__main__":
    main()
