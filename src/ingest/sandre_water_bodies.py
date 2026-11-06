"""Official river water bodies (WFD "masses d'eau cours d'eau", 2022 reporting) for the département box:
the sections that the groundwater-body sheets qualify (CQ5; e.g. FRDR224 "La Têt du barrage de Vinca
à la Comelade").

    python -m src.ingest.sandre_water_bodies    # first run downloads; later runs reuse the snapshot

Source: the Sandre WFS https://services.sandre.eaufrance.fr/geo/MasseDEau_VRAP2022, layer
sa:MasseDEauRiviere_VRAP2022_FXX (fields CdMasseDEau, CdEuMasseDEau, NomMasseDEau, ...; checked by
DescribeFeatureType on 2026-11-06), inside DEPT_BBOX, in Lambert-93. The service refuses GeoJSON for
this layer, so it is read as a GeoPackage, which the server sends zipped (one member,
'%TYPENAME%.gpkg'); the member is read in place from the zip, never extracted.

Outputs: data/raw/sandre_water_bodies/<YYYY-MM-DD>/masses_eau_riviere_vrap2022.zip, .parquet,
         release.json
"""
import hashlib
import json
import zipfile
from datetime import date

import geopandas as gpd

from src.config import CRS_L93, RAW
from src.ingest.safran import DEPT_BBOX
from src.web import TIMEOUT, make_session

URL = "https://services.sandre.eaufrance.fr/geo/MasseDEau_VRAP2022"
LAYER = "sa:MasseDEauRiviere_VRAP2022_FXX"
OUT = RAW / "sandre_water_bodies"
NAME = "masses_eau_riviere_vrap2022"


def snapshot():
    done = sorted(d for d in OUT.glob("????-??-??") if (d / "release.json").exists())
    return done[-1] if done else None


def main():
    have = snapshot()
    if have is not None:
        print(f"snapshot exists: {have} (remove the folder to pull again)")
        return
    lon0, lat0, lon1, lat1 = DEPT_BBOX
    params = {"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": LAYER,
              "BBOX": f"{lat0},{lon0},{lat1},{lon1},urn:ogc:def:crs:EPSG::4326",
              "SRSNAME": "EPSG:2154", "OUTPUTFORMAT": "GPKG"}
    r = make_session().get(URL, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    assert r.content[:2] == b"PK", f"not a zip: {r.content[:200]!r}"
    folder = OUT / date.today().isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    z = folder / f"{NAME}.zip"
    z.write_bytes(r.content)
    member = zipfile.ZipFile(z).namelist()
    assert len(member) == 1 and member[0].endswith(".gpkg"), member
    g = gpd.read_file(f"/vsizip/{z}/{member[0]}")
    g = g.to_crs(CRS_L93)
    assert g["CdEuMasseDEau"].is_unique, "a water body appears twice"
    out = folder / f"{NAME}.parquet"
    g.to_parquet(out, index=False)
    rel = {"source": "Sandre, référentiel des masses d'eau, version rapportage 2022 (WFS)", "url": URL,
           "layer": LAYER, "params": params, "retrieved": date.today().isoformat(),
           "features": len(g), "zip_bytes": z.stat().st_size,
           "zip_md5": hashlib.md5(z.read_bytes()).hexdigest(), "parquet": out.name}
    (folder / "release.json").write_text(json.dumps(rel, indent=1, ensure_ascii=False))
    print(f"{len(g)} river water bodies -> {out}")


if __name__ == "__main__":
    main()
