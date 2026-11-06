"""Documents cited as evidence in the knowledge graph (CQ5 river exchange, CQ6 canal return flow),
kept as dated local copies so that every curated statement points at the exact file it was read from.

    python -m src.ingest.documents      # downloads the missing ones; later runs only check them

Each document is stored once under data/raw/documents/<key>.pdf with its URL, retrieval date, size
and md5 in documents.json. The statements taken from them live in configs/river_exchange_evidence.csv,
with the printed page and a short quote; the PDFs are read only with pdftotext, never executed.
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
        f = OUT / f"{key}.pdf"
        if not f.exists():
            r = session.get(d["url"], timeout=TIMEOUT)
            r.raise_for_status()
            assert r.content[:5] == b"%PDF-", f"{key}: not a PDF"
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
