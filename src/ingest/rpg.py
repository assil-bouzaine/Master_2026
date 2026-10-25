"""Download and extract RPG (Registre Parcellaire Graphique) editions from IGN.

    python -m src.ingest.rpg                         # R76 (Occitanie), 2016 and 2023
    python -m src.ingest.rpg --region R76 --years 2016 2023
    python -m src.ingest.rpg --years 2016 2023 --clip dept            # raw files kept
    python -m src.ingest.rpg --years 2015 2017 2018 2019 2020 2021 2022 2024 2025 --clip dept --drop-raw

The Géoplateforme listing (/resource/RPG) is Atom XML, paginated and
rate-limited; names are found by regex in the raw text. Each edition's own feed
(/resource/RPG/<name>) lists its files: one .7z, or numbered parts .7z.001, .7z.002,
... (2022 has a single .7z.001), which are byte splits of one archive and are joined.
Files are downloaded with HTTP Range resume, checked against Content-Length and the
.md5 file when IGN publishes one, then extracted with py7zr.

Outputs: data/raw/rpg/<name>.7z and data/raw/rpg/<name>/ (extracted)
         --clip plain: data/interim/rpg_plain_<year>.parquet, parcels in the plain bbox
           + 3 km (the extent of src/analysis/rpg_profile.py)
         --clip dept: data/interim/rpg_dept_<year>.parquet, parcels in DEPT_BBOX of
           src/ingest/safran.py (dept 66 + about one SAFRAN cell), which holds the 3 km
           buffers of every well of the dataset (decided by Assil, 2026-10-25)
         --drop-raw: deletes the archive and the extracted folder once the clips are
           written (approved by Assil, 2026-10-25)
Clips keep every source column, upper-cased (the 2024+ GeoPackages may differ), with
CODE_GROUP as Int64 like rpg_profile. A year that fails is reported and the next one is
tried; the exit code is 1 if any year failed (rerun to resume).
"""
import argparse
import hashlib
import re
import shutil
import time

import geopandas as gpd
import numpy as np
import pandas as pd
import py7zr
import pyogrio

from src.config import CRS_L93, CRS_WGS84, INTERIM, RAW
from src.web import TIMEOUT, make_session

BASE = "https://data.geopf.fr/telechargement"
OUT = RAW / "rpg"
CHUNK = 1 << 20  # 1 MiB
REQUIRED = ["ID_PARCEL", "SURF_PARC", "CODE_CULTU", "CODE_GROUP"]


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
    # e.g. RPG_2-0__SHP_LAMB93_R76-2016_2016-01-01, RPG_2-2__SHP_LAMB93_R76_2023-01-01,
    # RPG_2-0_SHP_LAMB93_R76-2019 (no date suffix), RPG_4-0__GPKG_LAMB93_R76_2024-01-01
    pat = re.compile(rf"^RPG_[0-9-]+_+(?:SHP|GPKG)_LAMB93_{region}"
                     rf"(?:-{year}(?:_{year}-\d\d-\d\d)?|_{year}-\d\d-\d\d)$")
    hits = [n for n in names if pat.match(n)]
    if len(hits) != 1:
        avail = [n for n in names if region in n]
        raise LookupError(f"{region} {year}: expected 1 match, got {hits}. Available: {avail}")
    return hits[0]


def resource_files(session, name):
    """File names listed in the edition's own feed."""
    r = session.get(f"{BASE}/resource/RPG/{name}", timeout=TIMEOUT)
    r.raise_for_status()
    return sorted({h.rsplit("/", 1)[-1] for h in re.findall(r'href="([^"]+)"', r.text)
                   if f"/download/RPG/{name}/" in h})


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


def md5_table(session, url):
    """{file name: md5} from an IGN .md5 file ("<hash>  <dir>/<file>" lines, or a bare hash
    stored under None); {} when none is published."""
    r = session.get(url, timeout=TIMEOUT)
    if r.status_code != 200:
        return {}
    out = {}
    for line in r.text.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            out[parts[-1].rsplit("/", 1)[-1]] = parts[0].lower()
        elif len(parts) == 1:
            out[None] = parts[0].lower()
    return out


def verify(path, expected):
    if not expected:
        print(f"  {path.name}: no .md5 published; size check only")
        return
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    if h.hexdigest() != expected:
        path.unlink()
        raise RuntimeError(f"{path.name}: MD5 mismatch, file deleted; rerun to download again")
    print(f"  {path.name}: md5 OK")


def fetch_archive(session, name):
    """The edition's .7z, downloaded (and joined from numbered parts) and checked."""
    files = resource_files(session, name)
    parts = [f for f in files if re.fullmatch(rf"{re.escape(name)}\.7z(?:\.\d{{3}})?", f)]
    if not parts:
        raise RuntimeError(f"{name}: no archive among the listed files {files}")
    url = f"{BASE}/download/RPG/{name}"
    sums = md5_table(session, f"{url}/{name}.md5") if f"{name}.md5" in files else {}
    archive = OUT / f"{name}.7z"
    if parts == [archive.name]:
        download(session, f"{url}/{archive.name}", archive)
        verify(archive, sums.get(archive.name, sums.get(None)))
        return archive
    if archive.exists():  # joined in an earlier run, after its md5 checks
        print(f"  cached {archive.name} (joined from {len(parts)} part(s))")
        return archive
    pieces = []
    for p in sorted(parts):
        dest = download(session, f"{url}/{p}", OUT / p)
        verify(dest, sums.get(p))
        pieces.append(dest)
    tmp = archive.with_suffix(".7z.joining")
    with open(tmp, "wb") as out:
        for p in pieces:
            with open(p, "rb") as f:
                shutil.copyfileobj(f, out, CHUNK)
    tmp.replace(archive)
    for p in pieces:
        p.unlink()
    print(f"  joined {len(pieces)} part(s) -> {archive.name}")
    return archive


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


def parcel_layer(target):
    """(path, layer) of the parcel layer: a shapefile up to 2023, a GeoPackage from 2024."""
    shp = sorted(target.rglob("PARCELLES_GRAPHIQUES.shp"))
    if shp:
        return shp[0], None
    for gpkg in sorted(target.rglob("*.gpkg")):
        layers = [name for name, _ in pyogrio.list_layers(gpkg)]
        print(f"    {gpkg.name}: layers {layers}")
        hits = [name for name in layers if "PARCELLE" in name.upper()]
        if len(hits) == 1:
            return gpkg, hits[0]
    raise RuntimeError(f"no parcel layer found under {target}")


def extent_l93(which):
    """(xmin, ymin, xmax, ymax) in Lambert-93 of the clip extent."""
    if which == "plain":
        from src.analysis.rpg_profile import plain_bbox_l93
        return plain_bbox_l93()
    from src.ingest.safran import DEPT_BBOX
    lon0, lat0, lon1, lat1 = DEPT_BBOX
    # densified edges: parallels are arcs in Lambert-93, the corners alone miss a sliver
    t = np.linspace(0, 1, 101)
    lon = np.concatenate([lon0 + (lon1 - lon0) * t, np.full(101, lon1), lon1 - (lon1 - lon0) * t, np.full(101, lon0)])
    lat = np.concatenate([np.full(101, lat0), lat0 + (lat1 - lat0) * t, np.full(101, lat1), lat1 - (lat1 - lat0) * t])
    return tuple(gpd.GeoSeries.from_xy(lon, lat, crs=CRS_WGS84).to_crs(CRS_L93).total_bounds)


def clip_path(which, year):
    return INTERIM / f"rpg_{which}_{year}.parquet"


def clip(target, year, which):
    """Parcels inside the extent, all source columns (upper-cased), as GeoParquet."""
    out = clip_path(which, year)
    if out.exists():
        print(f"  cached {out.name}")
        return out
    path, layer = parcel_layer(target)
    g = pyogrio.read_dataframe(path, layer=layer, bbox=extent_l93(which))
    if g.crs is not None and g.crs.to_epsg() not in (None, 2154):
        raise RuntimeError(f"{year}: layer CRS {g.crs} is not Lambert-93; the bbox filter assumed it")
    g = g.set_crs(CRS_L93, allow_override=True)  # IGNF:LAMB93 == EPSG:2154
    print(f"  {year}: {len(g):,} parcels ({which} extent); columns {list(g.columns)}")
    print(f"    sample: {g.drop(columns='geometry').iloc[0].to_dict()}")
    g = g.rename(columns={c: c.upper() for c in g.columns if c != "geometry"})
    missing = [c for c in REQUIRED if c not in g.columns]
    if missing:
        raise RuntimeError(f"{year}: columns {missing} not found; inspect the layer before mapping")
    g["CODE_GROUP"] = pd.to_numeric(g["CODE_GROUP"], errors="coerce").astype("Int64")
    g.to_parquet(out, index=False)
    return out


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


def run_year(session, names, args, year):
    name = find_name(names, args.region, year)
    print(f"{year}: {name}")
    if args.drop_raw and all(clip_path(c, year).exists() for c in args.clip):
        print(f"  clips cached (raw already dropped): {[clip_path(c, year).name for c in args.clip]}")
        return
    archive = fetch_archive(session, name)
    target = OUT / name
    extract(archive, target)
    # archives sometimes extract flat, sometimes into sub-folders
    for f in sorted(target.rglob("*.shp")) + sorted(target.rglob("*.gpkg")):
        print(f"    {f.relative_to(OUT)}  ({f.stat().st_size / 1e6:.0f} MB)")
    for c in args.clip:
        clip(target, year, c)
    if args.drop_raw:
        archive.unlink()
        shutil.rmtree(target)
        print(f"  raw dropped: {archive.name} and {target.name}/")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--region", default="R76")
    ap.add_argument("--years", nargs="+", default=["2016", "2023"])
    ap.add_argument("--clip", nargs="+", default=[], choices=["plain", "dept"],
                    help="write interim/rpg_<extent>_<year>.parquet")
    ap.add_argument("--drop-raw", action="store_true", help="delete archive + extraction after the clips")
    args = ap.parse_args()
    if args.drop_raw and not args.clip:
        ap.error("--drop-raw needs --clip: the raw files would be lost unclipped")

    OUT.mkdir(parents=True, exist_ok=True)
    session = make_session()
    get_docs(session)
    names = list_names(session)
    print(f"{len(names)} RPG resources listed")

    failed = []
    for year in args.years:
        try:
            run_year(session, names, args, year)
        except Exception as e:  # report and go on with the next year
            print(f"  FAILED {year}: {type(e).__name__}: {e}")
            failed.append(year)
    if failed:
        raise SystemExit(f"failed years: {failed}; rerun to resume")


if __name__ == "__main__":
    main()
