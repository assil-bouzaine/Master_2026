"""Download and extract RPG (Registre Parcellaire Graphique) editions from IGN.

    python -m src.ingest.rpg                         # R76 (Occitanie), 2016 and 2023
    python -m src.ingest.rpg --region R76 --years 2016 2023

The Géoplateforme listing (/resource/RPG) is Atom XML, paginated and
rate-limited; names are found by regex in the raw text. Archives are
downloaded with HTTP Range resume, checked against Content-Length (and the
.md5 file when IGN publishes one), then extracted with py7zr.

Outputs: data/raw/rpg/<name>.7z and data/raw/rpg/<name>/ (extracted)
"""
import argparse
import hashlib
import re
import time

import py7zr

from src.config import RAW
from src.web import TIMEOUT, make_session

BASE = "https://data.geopf.fr/telechargement"
OUT = RAW / "rpg"
CHUNK = 1 << 20  # 1 MiB


def list_names(session):
    """All entry titles of the RPG feed (all pages)."""
    url = f"{BASE}/resource/RPG"
    first = session.get(url, timeout=TIMEOUT).text
    pages = int(re.search(r'pagecount="(\d+)"', first).group(1))
    text = [first]
    for p in range(2, pages + 1):
        time.sleep(1)  # the server answers 429 if we go faster
        text.append(session.get(url, params={"page": p}, timeout=TIMEOUT).text)
    return sorted(set(re.findall(r"<title>(RPG_[^<]+)</title>", "".join(text))))


def find_name(names, region, year):
    # e.g. RPG_2-0__SHP_LAMB93_R76-2016_2016-01-01 or RPG_2-2__SHP_LAMB93_R76_2023-01-01
    pat = re.compile(rf"^RPG_[0-9-]+_+SHP_LAMB93_{region}(?:-{year})?_{year}-\d\d-\d\d$")
    hits = [n for n in names if pat.match(n)]
    if len(hits) != 1:
        avail = [n for n in names if region in n]
        raise SystemExit(f"{region} {year}: expected 1 match, got {hits}.\nAvailable: {avail}")
    return hits[0]


def download(session, url, dest):
    """Stream to dest, resuming a partial .part file. Returns dest."""
    size = int(session.head(url, timeout=TIMEOUT, allow_redirects=True).headers["content-length"])
    if dest.exists() and dest.stat().st_size == size:
        print(f"  cached {dest.name} ({size / 1e6:.0f} MB)")
        return dest
    part = dest.with_suffix(dest.suffix + ".part")
    have = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    with session.get(url, headers=headers, stream=True, timeout=TIMEOUT) as r:
        r.raise_for_status()
        if have and r.status_code != 206:  # server ignored Range: start over
            have = 0
        mode = "ab" if have else "wb"
        print(f"  downloading {dest.name}: {size / 1e6:.0f} MB" + (f", resuming at {have / 1e6:.0f} MB" if have else ""))
        done, t0, last = have, time.time(), 0
        with open(part, mode) as f:
            for chunk in r.iter_content(CHUNK):
                f.write(chunk)
                done += len(chunk)
                if done - last > 50e6:
                    last = done
                    print(f"    {done / 1e6:.0f}/{size / 1e6:.0f} MB ({(done - have) / 1e6 / (time.time() - t0):.1f} MB/s)")
    if part.stat().st_size != size:
        raise RuntimeError(f"{dest.name}: got {part.stat().st_size} bytes, expected {size}; rerun to resume")
    part.replace(dest)
    return dest


def check_md5(session, url, path):
    r = session.get(url, timeout=TIMEOUT)
    if r.status_code != 200:
        print("  no .md5 published; size check only")
        return
    expected = r.text.split()[0].lower()
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    if h.hexdigest() != expected:
        path.unlink()
        raise RuntimeError(f"{path.name}: MD5 mismatch, file deleted; rerun to download again")
    print("  md5 OK")


def extract(archive, target):
    marker = target / "_EXTRACTED"
    if marker.exists():
        print(f"  already extracted -> {target.name}/")
        return
    target.mkdir(parents=True, exist_ok=True)
    print(f"  extracting -> {target.name}/")
    with py7zr.SevenZipFile(archive) as z:
        z.extractall(target)
    marker.write_text("ok\n")


DOCS = f"{BASE.rsplit('/', 1)[0]}/annexes/ressources/documentation"
# Official reference tables (crop code -> crop group). IGN publishes no 2016
# table; the 2023 one lists every code since 2014 with its validity period.
REF_TABLES = ["REF_CULTURES_GROUPES_CULTURES_2023.csv", "REF_CULTURES_GROUPES_CULTURES_2024.csv",
              "REF_CULTURES_2023.csv", "SE_RPG.pdf"]


def get_docs(session):
    (OUT / "docs").mkdir(parents=True, exist_ok=True)
    for f in REF_TABLES:
        dest = OUT / "docs" / f
        if not dest.exists():
            r = session.get(f"{DOCS}/{f}", timeout=TIMEOUT)
            r.raise_for_status()
            dest.write_bytes(r.content)
        print(f"  docs/{f} ({dest.stat().st_size / 1e3:.0f} KB)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--region", default="R76")
    ap.add_argument("--years", nargs="+", default=["2016", "2023"])
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    session = make_session()
    get_docs(session)
    names = list_names(session)
    print(f"{len(names)} RPG resources listed")

    for year in args.years:
        name = find_name(names, args.region, year)
        print(f"{year}: {name}")
        url = f"{BASE}/download/RPG/{name}/{name}"
        archive = download(session, url + ".7z", OUT / f"{name}.7z")
        check_md5(session, url + ".md5", archive)
        target = OUT / name
        extract(archive, target)
        # archives sometimes extract flat, sometimes into sub-folders
        for shp in sorted(target.rglob("*.shp")):
            print(f"    {shp.relative_to(OUT)}  ({shp.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
