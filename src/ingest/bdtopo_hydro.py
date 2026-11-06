"""BD TOPO V3 hydrography (IGN) for the département box: river and canal reaches, and the
watercourses they belong to (CQ5 river reaches, CQ6 canal lines).

    python -m src.ingest.bdtopo_hydro           # first run downloads; later runs reuse the snapshot
    python -m src.ingest.bdtopo_hydro --check   # compares the snapshot's counts with the WFS (hits only)

Source: the IGN Géoplateforme WFS (https://data.geopf.fr/wfs/ows, WFS 2.0.0), layers
BDTOPO_V3:troncon_hydrographique and BDTOPO_V3:cours_d_eau, in Lambert-93 (EPSG:2154), inside
DEPT_BBOX (src.ingest.safran: lon 1.65-3.25, lat 42.30-43.00). BD TOPO hydrography is the
geometry from which the BD TOPAGE reference is built; each reach carries the BD Carthage code of
its watercourse (`code_du_cours_d_eau_bdcarthage`), the code Hub'Eau gives a gauge's river
(`code_cours_eau`, e.g. Y04-0400 for the Têt), so a gauge meets its reaches by code, never by name.

The WFS serves the current edition only, so the snapshot is kept under its retrieval date and never
fetched again unless its folder is removed. Paging: COUNT 5000 (the server's default and maximum),
STARTINDEX, sorted by `cleabs` so that pages do not overlap; each page is cached as it arrives, so an
interrupted pull resumes, and the pages are assembled into one GeoParquet per layer (identifiers
checked unique, count checked against numberMatched), after which they are deleted.

Outputs: data/raw/bdtopo_hydro/<YYYY-MM-DD>/troncon_hydrographique.parquet, cours_d_eau.parquet,
         release.json (URL, parameters, counts, sizes, md5 of the parquet files)
"""
import argparse
import hashlib
import json
from datetime import date

import geopandas as gpd
import pandas as pd

from src.config import CRS_L93, RAW
from src.ingest.safran import DEPT_BBOX
from src.web import TIMEOUT, make_session

URL = "https://data.geopf.fr/wfs/ows"
LAYERS = ("troncon_hydrographique", "cours_d_eau")
PAGE = 5000
OUT = RAW / "bdtopo_hydro"


def params(layer, **extra):
    lon0, lat0, lon1, lat1 = DEPT_BBOX
    p = {"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
         "TYPENAMES": f"BDTOPO_V3:{layer}",
         "BBOX": f"{lat0},{lon0},{lat1},{lon1},urn:ogc:def:crs:EPSG::4326"}
    p.update(extra)
    return p


def hits(session, layer):
    r = session.get(URL, params=params(layer, RESULTTYPE="hits"), timeout=TIMEOUT)
    r.raise_for_status()
    key = 'numberMatched="'
    i = r.text.index(key) + len(key)
    return int(r.text[i:r.text.index('"', i)])


def snapshot():
    """The newest complete snapshot folder, or None."""
    done = sorted(d for d in OUT.glob("????-??-??") if (d / "release.json").exists())
    return done[-1] if done else None


def pull_layer(session, layer, folder):
    n = hits(session, layer)
    pages = folder / f"{layer}_pages"
    pages.mkdir(parents=True, exist_ok=True)
    for start in range(0, n, PAGE):
        f = pages / f"{start:07d}.json"
        if f.exists() and f.stat().st_size > 100:
            continue
        r = session.get(URL, params=params(layer, COUNT=PAGE, STARTINDEX=start, SORTBY="cleabs",
                                           OUTPUTFORMAT="application/json", SRSNAME="EPSG:2154"),
                        timeout=TIMEOUT)
        r.raise_for_status()
        tmp = f.with_suffix(".part")
        tmp.write_bytes(r.content)
        tmp.replace(f)
        print(f"  {layer}: {min(start + PAGE, n):,} / {n:,}")
    parts = [gpd.read_file(f) for f in sorted(pages.glob("*.json"))]
    g = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=parts[0].crs)
    g = g.set_crs(CRS_L93, allow_override=True) if g.crs is None else g.to_crs(CRS_L93)
    assert g["cleabs"].is_unique, f"{layer}: pages overlap (duplicate cleabs)"
    assert len(g) == n, f"{layer}: {len(g)} features, the WFS matched {n}"
    out = folder / f"{layer}.parquet"
    g.to_parquet(out, index=False)
    for f in pages.glob("*.json"):
        f.unlink()
    pages.rmdir()
    return out, n


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    session = make_session()
    have = snapshot()
    if a.check:
        if have is None:
            print("no snapshot yet")
            return
        rel = json.loads((have / "release.json").read_text())
        for layer in LAYERS:
            print(f"{layer}: snapshot {rel['layers'][layer]['features']:,}, "
                  f"WFS now {hits(session, layer):,}")
        return
    if have is not None:
        print(f"snapshot exists: {have} (remove the folder to pull again)")
        return
    folder = OUT / date.today().isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    rel = {"source": "IGN Géoplateforme WFS, BD TOPO V3 hydrography", "url": URL,
           "bbox_wgs84": list(DEPT_BBOX), "srs": "EPSG:2154", "page_size": PAGE,
           "sort_by": "cleabs", "retrieved": date.today().isoformat(), "layers": {}}
    for layer in LAYERS:
        out, n = pull_layer(session, layer, folder)
        rel["layers"][layer] = {"typename": f"BDTOPO_V3:{layer}", "features": n,
                                "file": out.name, "bytes": out.stat().st_size, "md5": md5(out)}
        print(f"{layer}: {n:,} features -> {out}")
    (folder / "release.json").write_text(json.dumps(rel, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
