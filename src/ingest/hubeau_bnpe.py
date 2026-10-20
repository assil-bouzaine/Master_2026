"""Download BNPE water-abstraction points and annual volumes from Hub'Eau.

    python -m src.ingest.hubeau_bnpe                         # skip files already cached
    python -m src.ingest.hubeau_bnpe --snapshot 2026-10-20   # dated snapshot (dataset v3)

Outputs (data/raw/hubeau_bnpe/, or data/raw/hubeau_bnpe/<snapshot>/):
    points_prelevement_<dept>.parquet   abstraction points (one row per point)
    chroniques_<dept>.parquet           annual volumes (one row per ouvrage x year x usage)

BNPE keeps growing (a new year is published about two years later, and recent
years are revised), so each dataset version reads a dated snapshot: v1/v2 the
pull of 2026-10-05 (top folder), v3 the snapshot of 2026-10-20. A snapshot is
never overwritten, which keeps every dataset version reproducible.

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
    ap.add_argument("--refresh", action="store_true", help="re-download the top-folder files")
    ap.add_argument("--snapshot", help="write to a dated sub-folder, e.g. 2026-10-20")
    args = ap.parse_args()

    out = OUT / args.snapshot if args.snapshot else OUT
    out.mkdir(parents=True, exist_ok=True)
    s = make_session()
    pull(s, "referentiel/points_prelevement", args.dept,
         out / f"points_prelevement_{args.dept}.parquet", args.refresh and not args.snapshot)
    pull(s, "chroniques", args.dept, out / f"chroniques_{args.dept}.parquet",
         args.refresh and not args.snapshot)


if __name__ == "__main__":
    main()
