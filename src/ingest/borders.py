"""Foreign land (Spain, Andorra) near dept 66, from Natural Earth admin-0 countries 1:10m.

    python -m src.ingest.borders

The RPG covers French parcels only. A 3 km zone around a well near the border is partly
Spanish or Andorran land, where crops are unknown (not absent); the sea, by contrast,
holds no crops. Natural Earth (public domain) separates the two: foreign land is the
union of the Spain and Andorra polygons. At 1:10m the border is placed within a few
hundred metres, enough to flag a share of a zone, not to map parcels.

Source : https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip
Outputs: data/raw/naturalearth/ne_10m_admin_0_countries.zip (cached)
         data/interim/foreign_land_66.parquet   Spain + Andorra inside DEPT_BBOX, Lambert-93
"""
from src.config import CRS_L93, INTERIM, RAW
from src.ingest.safran import DEPT_BBOX
from src.web import TIMEOUT, make_session

URL = "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip"
ZIP = RAW / "naturalearth" / "ne_10m_admin_0_countries.zip"
OUT = INTERIM / "foreign_land_66.parquet"
FOREIGN = ["ESP", "AND"]  # ADM0_A3; ISO_A3 is -99 for France in this release


def main():
    import pyogrio
    ZIP.parent.mkdir(parents=True, exist_ok=True)
    if not ZIP.exists():
        r = make_session().get(URL, timeout=TIMEOUT)
        r.raise_for_status()
        ZIP.write_bytes(r.content)
    print(f"{ZIP.name}: {ZIP.stat().st_size / 1e6:.1f} MB")
    g = pyogrio.read_dataframe(f"/vsizip/{ZIP}", bbox=DEPT_BBOX)
    print(f"countries in DEPT_BBOX: {list(g['ADM0_A3'])}")
    g = g[g["ADM0_A3"].isin(FOREIGN)][["ADM0_A3", "ADMIN", "geometry"]].to_crs(CRS_L93)
    g.to_parquet(OUT, index=False)
    print(f"-> {OUT.name}: {list(g['ADMIN'])}")


if __name__ == "__main__":
    main()
