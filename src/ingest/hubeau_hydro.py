"""Download Hub'Eau hydrometry stations and daily mean flows for one département.

    python -m src.ingest.hubeau_hydro            # resume: skip cached stations
    python -m src.ingest.hubeau_hydro --refresh  # re-download every series

API v2 (https://hubeau.eaufrance.fr/api/v2/hydrometrie):
    referentiel/stations?code_departement=66   station list
    obs_elab?code_entite=<station>&grandeur_hydro_elab=QmnJ
                                               daily mean flow, litres per second

Keeps the stations open at any time since START (rivers *and* gauged irrigation
canals, which carry the canal-return recharge signal). Each station is cached
separately and written atomically, so a crash never restarts the whole pull.

Outputs (data/raw/hubeau_hydro/):
    stations_<dept>.parquet            one row per station
    qmnj/<code_station>.parquet        daily mean flow since START
"""
import argparse

import pandas as pd

from src.config import DEPARTEMENT, RAW
from src.ingest.hubeau_piezo import fetch_all
from src.web import make_session

BASE = "https://hubeau.eaufrance.fr/api/v2/hydrometrie"
OUT = RAW / "hubeau_hydro"
QDIR = OUT / "qmnj"
START = "2005-01-01"
PAGE_SIZE = 5000
STATION_COLS = ["code_station", "libelle_station", "libelle_cours_eau", "code_cours_eau",
                "en_service", "date_ouverture_station", "date_fermeture_station",
                "longitude_station", "latitude_station", "type_station",
                "influence_locale_station", "commentaire_influence_locale_station"]


def get_stations(session, dept):
    records, count = fetch_all(session, f"{BASE}/referentiel/stations",
                               {"code_departement": dept, "size": 200, "format": "json"})
    assert len(records) == count, f"got {len(records)} stations, API says {count}"
    df = pd.DataFrame(records)[STATION_COLS]
    # Two stations have lon/lat swapped in the referential (lat ~2.x, lon ~42.x).
    swap = df["longitude_station"] > df["latitude_station"]
    df.loc[swap, ["longitude_station", "latitude_station"]] = (
        df.loc[swap, ["latitude_station", "longitude_station"]].values)
    df["is_canal"] = df["libelle_station"].str.contains("canal", case=False)
    df.to_parquet(OUT / f"stations_{dept}.parquet", index=False)
    return df


def get_series(session, code):
    records, _ = fetch_all(session, f"{BASE}/obs_elab",
                           {"code_entite": code, "grandeur_hydro_elab": "QmnJ",
                            "date_debut_obs_elab": START, "size": PAGE_SIZE})
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)[["code_station", "date_obs_elab", "resultat_obs_elab",
                                "libelle_statut", "libelle_qualification"]]
    df["date_obs_elab"] = pd.to_datetime(df["date_obs_elab"])
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    QDIR.mkdir(parents=True, exist_ok=True)
    s = make_session()
    st = get_stations(s, DEPARTEMENT)
    closed = pd.to_datetime(st["date_fermeture_station"], utc=True).dt.tz_localize(None)
    keep = st[closed.isna() | (closed >= START)]
    print(f"{len(st)} stations in dept {DEPARTEMENT}; {len(keep)} open since {START} "
          f"({int(keep['is_canal'].sum())} canals)")
    done = cached = empty = failed = 0
    for code in keep["code_station"]:
        path = QDIR / f"{code}.parquet"
        if path.exists() and not args.refresh:
            cached += 1
            continue
        try:
            df = get_series(s, code)
        except Exception as e:  # keep going; the next run retries this station
            print(f"  {code}: FAILED ({e})")
            failed += 1
            continue
        tmp = path.with_suffix(".parquet.part")
        df.to_parquet(tmp, index=False)
        tmp.replace(path)
        if df.empty:
            empty += 1
        else:
            done += 1
            print(f"  {code}: {len(df):,} days {df['date_obs_elab'].min().date()} .. "
                  f"{df['date_obs_elab'].max().date()}", flush=True)
    print(f"downloaded {done}, cached {cached}, empty {empty}, failed {failed}")


if __name__ == "__main__":
    main()
