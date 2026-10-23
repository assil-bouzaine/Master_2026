"""Download the Hub'Eau groundwater-quality stations (ADES water points) of one département.

    python -m src.ingest.hubeau_qualite_stations            # skip if cached
    python -m src.ingest.hubeau_qualite_stations --refresh  # download again

Why: competency question CQ2 needs the aquifer unit each abstraction point pumps from. BNPE
gives no unit (`code_bdlisa` is always empty), but 235 BNPE points carry a BSS code, and most
of those boreholes are also ADES quality stations, whose record lists the BD LISA entity
(`codes_entite_hg_bdlisa`) and often the investigation depth.

Outputs (data/raw/hubeau_qualite/):
    stations_<dept>.json      raw API response (all pages)
    stations_<dept>.parquet   flat table, one row per station (lists joined with ';')
"""
import argparse
import json

import pandas as pd

from src.config import DEPARTEMENT, RAW
from src.ingest.hubeau_piezo import fetch_all
from src.web import make_session

BASE = "https://hubeau.eaufrance.fr/api/v1/qualite_nappes/stations"
OUT = RAW / "hubeau_qualite"
PAGE_SIZE = 2000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dept", default=DEPARTEMENT)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    raw, table = OUT / f"stations_{args.dept}.json", OUT / f"stations_{args.dept}.parquet"
    if table.exists() and table.stat().st_size > 10_000 and not args.refresh:
        print(f"cached: {table}")
        return
    # this endpoint filters on num_departement (code_departement is ignored)
    records, count = fetch_all(make_session(), BASE, {"num_departement": args.dept,
                                                      "size": PAGE_SIZE})
    assert len(records) == count, f"got {len(records)} stations, API says {count}"
    raw.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    df = pd.DataFrame(records).drop(columns=["geometry"])
    for col in df.columns:  # lists -> ';'-joined strings so parquet stays simple
        if df[col].map(lambda v: isinstance(v, list)).any():
            df[col] = df[col].map(lambda v: ";".join(map(str, v)) if isinstance(v, list) else v)
    df.to_parquet(table, index=False)
    print(f"{len(df)} stations -> {table} ({table.stat().st_size / 1e3:.0f} kB); "
          f"with a BD LISA code: {df['codes_entite_hg_bdlisa'].fillna('').ne('').sum()}")


if __name__ == "__main__":
    main()
