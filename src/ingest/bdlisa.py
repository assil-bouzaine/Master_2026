"""Extract the manually downloaded BD LISA V3 archive and list its layers.

    python -m src.ingest.bdlisa

Manual step (no API): download the Occitanie extract from
https://bdlisa.eaufrance.fr (Téléchargement) and save the zip under
data/raw/bdlisa/. GeoPackage preferred (BDLISA_V3_OCC-gpkg.zip); the older
FileGDB zip (BDLISA-V3-OCC-gdb.zip) also works with pyogrio.

Output: data/raw/bdlisa/<zip stem>/ (extracted), layer list printed.
"""
import zipfile

import pyogrio

from src.config import RAW

OUT = RAW / "bdlisa"


def find_dataset():
    zips = sorted(OUT.glob("*.zip"))
    if not zips:
        raise SystemExit(f"No zip in {OUT}. Download BD LISA V3 (Occitanie) from "
                         "https://bdlisa.eaufrance.fr and save it there.")
    z = zips[0]
    target = OUT / z.stem
    marker = target / "_EXTRACTED"
    if not marker.exists():
        print(f"extracting {z.name} -> {target.name}/")
        with zipfile.ZipFile(z) as f:
            f.extractall(target)
        marker.write_text("ok\n")
    ds = sorted(target.rglob("*.gpkg")) + sorted(p for p in target.rglob("*.gdb") if p.is_dir())
    if not ds:
        raise SystemExit(f"no .gpkg or .gdb inside {z.name}")
    return ds[0]


def main():
    ds = find_dataset()
    print(f"dataset: {ds.relative_to(OUT)}")
    for name, geom in pyogrio.list_layers(ds):
        info = pyogrio.read_info(ds, layer=name)
        print(f"  {name:<40} {str(geom):<16} {info['features']:>8} rows  fields={list(info['fields'])}")


if __name__ == "__main__":
    main()
