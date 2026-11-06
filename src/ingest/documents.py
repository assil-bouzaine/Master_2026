"""Documents cited as evidence in the knowledge graph (CQ5 river exchange, CQ6 canal return flow),
kept as dated local copies so that every curated statement points at the exact file it was read from.

    python -m src.ingest.documents      # downloads the missing ones; later runs only check them

Each document is stored once under data/raw/documents/<key>.<pdf|html> with its URL, retrieval date,
size and md5 in documents.json. The statements taken from them live in configs/exchange_evidence.csv,
with the printed page and a short quote (tests/test_exchange_evidence.py finds every quote on its page);
the PDFs are read only with pdftotext and the web page as text, never executed.

Interrupted runs (Codex review of 2026-11-06, S2): a file is written under a temporary name and
renamed when complete, and the index is saved after each document, so a failure leaves only complete
files that the index describes. A stored copy without an index entry (an index lost or written by
an older version of this script) gets no guessed date: it is fetched again and compared, and
recorded with the date of that fetch and a note; a copy that differs from the source is refused
(delete it to replace it). Tested by tests/test_documents.py.
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


def fetch(session, key, d, kind):
    r = session.get(d["url"], timeout=TIMEOUT)
    r.raise_for_status()
    if kind == "pdf":
        assert r.content[:5] == b"%PDF-", f"{key}: not a PDF"
    else:
        assert b"<html" in r.content[:2000].lower(), f"{key}: not an HTML page"
    return r.content


def save(path, content):
    """Write under a temporary name, then rename: an interrupted write leaves no partial file."""
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(content)
    tmp.replace(path)


def main(out=OUT, docs=DOCS, session=None):
    out.mkdir(parents=True, exist_ok=True)
    index = out / "documents.json"
    log = json.loads(index.read_text()) if index.exists() else {}
    session = session or make_session()
    today = date.today().isoformat()

    def save_index():
        save(index, json.dumps(log, indent=1, ensure_ascii=False).encode("utf-8"))

    for key, d in docs.items():
        kind = d.get("kind", "pdf")
        f = out / f"{key}.{kind}"
        if not f.exists():
            save(f, fetch(session, key, d, kind))
            log[key] = {**d, "file": f.name, "retrieved": today}
            save_index()
        elif key not in log:
            # a stored copy the index does not describe: its first retrieval date is unknown, so it
            # is fetched again and compared instead of being dated by guess
            new = fetch(session, key, d, kind)
            if hashlib.md5(new).hexdigest() != hashlib.md5(f.read_bytes()).hexdigest():
                raise RuntimeError(f"{key}: {f} has no entry in {index.name} and differs from the source; "
                                   "delete it to download the current version")
            log[key] = {**d, "file": f.name, "retrieved": today,
                        "note": f"stored copy found without an index entry; fetched again on {today} and "
                                "identical, so dated by that fetch (its first retrieval date is unknown)"}
            save_index()
        md5 = hashlib.md5(f.read_bytes()).hexdigest()
        if "md5" in log[key]:
            assert log[key]["md5"] == md5, f"{key}: the stored copy changed"
        log[key].update(bytes=f.stat().st_size, md5=md5)
        print(f"{key}: {f.stat().st_size:,} bytes, md5 {md5}")
    save_index()
    return log


if __name__ == "__main__":
    main()
