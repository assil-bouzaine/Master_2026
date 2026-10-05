"""Download BNPE water-abstraction points and annual volumes from Hub'Eau.

    python -m src.ingest.hubeau_bnpe            # skip files already cached
    python -m src.ingest.hubeau_bnpe --refresh

Outputs (data/raw/hubeau_bnpe/):
    points_prelevement_<dept>.parquet   abstraction points (one row per point)
    chroniques_<dept>.parquet           annual volumes (one row per ouvrage x year x usage)

Volumes are reported per *ouvrage* (facility); the water source
(code_type_milieu: CONT = surface, SOUT = groundwater) is an attribute of
the *points*. Join the two on code_ouvrage.
"""
import argparse

import pandas as pd

from src.config import DEPARTEMENT, RAW
from src.ingest.hubeau_piezo import fetch_all
from src.web import make_session

BASE = "https://hubeau.eaufrance.fr/api/v1/prelevements"
OUT = RAW / "hubeau_bnpe"
PAGE_SIZE = 2000  # 5000 got the connection reset once (2026-10-05)


def flatten(records):
    df = pd.DataFrame(records).drop(columns=["geometry"], errors="ignore")
    for col in df.columns:  # lists -> ';'-joined strings so parquet stays simple
        if df[col].map(lambda v: isinstance(v, list)).any():
            df[col] = df[col].map(lambda v: ";".join(v) if isinstance(v, list) else v)
    return df


def pull(session, endpoint, dept, dest, refresh):
    if dest.exists() and dest.stat().st_size > 0 and not refresh:
        df = pd.read_parquet(dest)
        print(f"cached {dest.name}: {len(df)} rows")
        return df
    records, count = fetch_all(session, f"{BASE}/{endpoint}",
                               {"code_departement": dept, "size": PAGE_SIZE})
    if len(records) != count:
        raise RuntimeError(f"{endpoint}: got {len(records)} rows, API says {count}")
    df = flatten(records)
    tmp = dest.with_suffix(".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(dest)
    print(f"downloaded {dest.name}: {len(df)} rows")
    return df


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dept", default=DEPARTEMENT)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    s = make_session()
    pull(s, "referentiel/points_prelevement", args.dept,
         OUT / f"points_prelevement_{args.dept}.parquet", args.refresh)
    pull(s, "chroniques", args.dept, OUT / f"chroniques_{args.dept}.parquet", args.refresh)


if __name__ == "__main__":
    main()
