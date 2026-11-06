"""Documents cited as evidence in the knowledge graph (CQ5 river exchange, CQ6 canal return flow),
kept as dated local copies so that every curated statement points at the exact file it was read from.

    python -m src.ingest.documents      # downloads the missing ones; later runs only check them

Each document is stored once under data/raw/documents/<key>.<pdf|html> with its URL, retrieval date,
size and md5 in documents.json. The statements taken from them live in configs/exchange_evidence.csv,
with the printed page and a short quote (tests/test_exchange_evidence.py finds every quote on its page);
the PDFs are read only with pdftotext and the web page as text, never executed.
"""
import hashlib
import json
from datetime import date

from src.config import RAW
from src.web import TIMEOUT, make_session

OUT = RAW / "documents"
DOCS = {
    "brgm-rp-71486-fr": {
        "url": "https://infoterre.brgm.fr/rapports/RP-71486-FR.pdf",
        "title": "Ladouche B., Caballero Y. (2022). Flux d'eau entre canaux d'irrigation, cours d'eau "
                 "et nappes d'eau souterraine du BV de la Têt, amont de Perpignan. Rapport final, "
                 "BRGM/RP-71486-FR, Production #11b du projet Dem'Eaux Roussillon."},
    "sierm-frdg351": {
        "url": "https://www.rhone-mediterranee.eaufrance.fr/sites/sierm/files/underground_waterbody/FRDG351.pdf",
        "title": "Agence de l'eau Rhône Méditerranée Corse, fiche de caractérisation de la masse "
                 "d'eau souterraine FRDG351 'Alluvions quaternaires du Roussillon', état des "
                 "connaissances 2021 (printed 01/12/2021)."},
    "smnpr-fonctionnement-des-nappes": {
        "url": "https://nappes-roussillon.fr/en-pratique/fonctionnement-des-nappes/",
        "kind": "html",
        "title": "Syndicat mixte pour la protection et la gestion des nappes souterraines de la plaine du "
                 "Roussillon (SMNPR), 'Présentation des nappes' (web page; first read 2026-10-27, stored "
                 "2026-11-06)."},
    "sierm-frdg243": {
        "url": "https://www.rhone-mediterranee.eaufrance.fr/sites/sierm/files/underground_waterbody/FRDG243.pdf",
        "title": "Agence de l'eau Rhône Méditerranée Corse, fiche de caractérisation de la masse "
                 "d'eau souterraine FRDG243 'Multicouche pliocène du Roussillon', état des "
                 "connaissances 2021 (printed 01/12/2021)."},
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    index = OUT / "documents.json"
    log = json.loads(index.read_text()) if index.exists() else {}
    session = make_session()
    for key, d in DOCS.items():
        kind = d.get("kind", "pdf")
        f = OUT / f"{key}.{kind}"
        if not f.exists():
            r = session.get(d["url"], timeout=TIMEOUT)
            r.raise_for_status()
            if kind == "pdf":
                assert r.content[:5] == b"%PDF-", f"{key}: not a PDF"
            else:
                assert b"<html" in r.content[:2000].lower(), f"{key}: not an HTML page"
            f.write_bytes(r.content)
            log[key] = {**d, "file": f.name, "retrieved": date.today().isoformat()}
        md5 = hashlib.md5(f.read_bytes()).hexdigest()
        if "md5" in log.get(key, {}):
            assert log[key]["md5"] == md5, f"{key}: the stored copy changed"
        log[key].update(bytes=f.stat().st_size, md5=md5)
        print(f"{key}: {f.stat().st_size:,} bytes, md5 {md5}")
    index.write_text(json.dumps(log, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
