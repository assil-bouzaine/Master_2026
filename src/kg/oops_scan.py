"""OOPS! (OntOlogy Pitfall Scanner) on the LULC-Water network: one of the quality gates of CLAUDE.md §3.

    python -m src.kg.oops_scan            # scan, keep the raw answer, write docs/oops_report.md
    python -m src.kg.oops_scan --report   # rewrite the report from the stored answer of today

OOPS! (Poveda-Villalón, Gómez-Pérez and Suárez-Figueroa 2014, doi:10.4018/ijswis.2014040102) is a web
service: https://oops.linkeddata.es/rest takes the ontology as content (scanning by URL "is no longer
allowed", answer of 2026-11-16) and returns its pitfalls. The ontology files are public (the
repository is public on GitHub), so sending them exposes nothing new.

What is sent: the whole network (ontology/lulcw-meta.ttl and its imports, merged by ROBOT through
the catalog), as RDF/XML, without owl:imports statements. Two lessons of 2026-11-16: the service
fails ("unexpected error") on the owl:imports of lulcw.ttl, whose w3id.org IRIs do not resolve
until the redirect is accepted; and lulcw.ttl alone makes the reused terms look undeclared
(P08 and P34 on SOSA, PROV, SKOS and GeoSPARQL classes), which the merged network does not.

Outputs: data/raw/oops/<YYYY-MM-DD>/response.xml and release.json (endpoint, date, lulcw version,
SHA-256 and size of the content sent); docs/oops_report.md: every pitfall with its importance, the
number of elements it affects in all and among lulcw's own terms, the lulcw elements, and the
verdict of configs/oops_verdicts.csv (fixed, accepted with its reason, not ours, not reproduced).
"""
import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import rdflib
from rdflib import OWL, RDF

from src.config import RAW, ROOT

URL = "https://oops.linkeddata.es/rest"
ONTO = ROOT / "ontology"
ROBOT = ROOT / "tools" / "robot.jar"
OUT = RAW / "oops"
REPORT = ROOT / "docs" / "oops_report.md"
VERDICTS = ROOT / "configs" / "oops_verdicts.csv"
L = "https://w3id.org/lulcw#"


def merged_network():
    """The network as one RDF/XML document without owl:imports, and lulcw's version."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "merged.owl"
        r = subprocess.run(["java", "-jar", str(ROBOT), "--catalog", str(ONTO / "catalog-v001.xml"), "merge",
                            "--input", str(ONTO / "lulcw-meta.ttl"), "--collapse-import-closure", "true",
                            "--output", str(out)], capture_output=True, text=True, cwd=ONTO)
        if r.returncode:
            raise SystemExit(f"ROBOT merge failed:\n{r.stdout}{r.stderr}")
        g = rdflib.Graph().parse(out)
    for t in list(g.triples((None, OWL.imports, None))):
        g.remove(t)
    version = str(next(rdflib.Graph().parse(ONTO / "lulcw.ttl").objects(None, OWL.versionInfo)))
    return g, g.serialize(format="xml"), version


def scan():
    g, xml, version = merged_network()
    if "]]>" in xml:
        raise SystemExit("the ontology text contains ']]>' and cannot be sent in a CDATA section")
    body = ("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<OOPSRequest>\n  <OntologyUrl></OntologyUrl>\n"
            f"  <OntologyContent><![CDATA[{xml}]]></OntologyContent>\n  <Pitfalls></Pitfalls>\n"
            "  <OutputFormat>XML</OutputFormat>\n</OOPSRequest>\n").encode("utf-8")
    from src.web import TIMEOUT, make_session
    r = make_session().post(URL, data=body, headers={"Content-Type": "application/xml; charset=utf-8"},
                            timeout=TIMEOUT)
    r.raise_for_status()
    if "unexpected_error" in r.text or "invalid_parameters" in r.text:
        raise SystemExit(f"OOPS! refused the request:\n{r.text[:600]}")
    d = OUT / date.today().isoformat()
    d.mkdir(parents=True, exist_ok=True)
    (d / "response.xml").write_text(r.text, encoding="utf-8")
    (d / "release.json").write_text(json.dumps({
        "endpoint": URL, "date": date.today().isoformat(), "lulcw_version": version, "triples_sent": len(g),
        "bytes_sent": len(xml.encode("utf-8")), "sha256_sent": hashlib.sha256(xml.encode("utf-8")).hexdigest()},
        indent=1))
    print(f"-> {d}: {len(g)} triples sent (lulcw {version})")
    return d


def parse(text):
    """Pitfalls and suggestions of an OOPS! XML answer."""
    out = []
    for p in re.findall(r"<oops:Pitfall>(.*?)</oops:Pitfall>", text, re.S):
        get = lambda t: (re.search(rf"<oops:{t}>(.*?)</oops:{t}>", p, re.S) or [None, ""])[1].strip()  # noqa: E731
        els = re.findall(r"<oops:AffectedElement>(.*?)</oops:AffectedElement>", p)
        out.append({"code": get("Code"), "name": get("Name"), "importance": get("Importance"),
                    "affected": int(get("NumberAffectedElements") or len(els)),
                    "lulcw": sorted({e for e in els if e.startswith(L)})})
    for kind, w in re.findall(r"<oops:(Warning|Suggestion)>(.*?)</oops:\1>", text, re.S):
        words = re.sub(r"\s+", " ", re.sub("<[^>]+>", " ", w)).strip()
        els = sorted(set(re.findall(r"https?://\S+", words)))
        out.append({"code": f"{kind.upper()}-" + "-".join(e.split("#")[-1] for e in els if e.startswith(L)),
                    "name": words.split(".")[0], "importance": kind, "affected": len(els),
                    "lulcw": [e for e in els if e.startswith(L)]})
    return out


def naming_check():
    """Every lulcw local name in CamelCase: classes and individuals upper, properties lower."""
    g = rdflib.Graph().parse(ONTO / "lulcw.ttl")
    props = {s for t in (OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty)
             for s in g.subjects(RDF.type, t)}
    bad = []
    for s in {s for s in g.subjects() if str(s).startswith(L)}:
        n = str(s)[len(L):]
        want = r"[a-z][A-Za-z0-9]*" if s in props else r"[A-Z][A-Za-z0-9]*"
        if not re.fullmatch(want, n):
            bad.append(n)
    return sorted(bad)


def report(d):
    pit = parse((d / "response.xml").read_text(encoding="utf-8"))
    rel = json.loads((d / "release.json").read_text())
    ver = pd.read_csv(VERDICTS).set_index("code")
    bad = naming_check()
    lines = [
        "# OOPS! pitfall scan of the LULC-Water network (generated)", "",
        f"Generated by `python -m src.kg.oops_scan` from the answer of {rel['date']} "
        f"(`{d.relative_to(ROOT)}/response.xml`); do not edit by hand. OOPS! (Poveda-Villalón et al. 2014, "
        f"doi:10.4018/ijswis.2014040102), {rel['endpoint']}; sent: the merged network (lulcw "
        f"{rel['lulcw_version']} and its imports, {rel['triples_sent']:,} triples, without owl:imports). "
        "Verdicts: `configs/oops_verdicts.csv`.", "",
        "| code | pitfall | importance | elements affected | of which lulcw terms | verdict |",
        "|---|---|---|---:|---:|---|"]
    for p in sorted(pit, key=lambda p: ({"Critical": 0, "Important": 1, "Minor": 2}.get(p["importance"], 3), p["code"])):
        v = ver["verdict"].get(p["code"], "**no verdict yet**")
        lines.append(f"| {p['code']} | {p['name']} | {p['importance']} | {p['affected']} | {len(p['lulcw'])} | {v} |")
    lines += ["", f"No critical pitfall: {'yes' if not any(p['importance'] == 'Critical' for p in pit) else 'NO'}. "
              f"lulcw names not in CamelCase (classes upper, properties lower): {bad or 'none'}.", ""]
    for p in pit:
        if p["code"] in ver.index:
            lines += [f"## {p['code']}: {p['name']}", "", ver.loc[p["code"], "reason"], ""]
        if p["lulcw"]:
            names = ", ".join(f"`{e[len(L):]}`" for e in p["lulcw"])
            lines += [f"lulcw terms ({len(p['lulcw'])}): {names}", ""]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    missing = [p["code"] for p in pit if p["code"] not in ver.index]
    print(f"-> {REPORT.relative_to(ROOT)}: {len(pit)} pitfalls and suggestions"
          + (f"; WITHOUT a verdict: {missing}" if missing else ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--report", action="store_true", help="only rewrite the report from today's stored answer")
    a = ap.parse_args()
    d = OUT / date.today().isoformat() if a.report else scan()
    report(d)


if __name__ == "__main__":
    main()
