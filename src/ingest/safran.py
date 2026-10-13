"""Download Météo-France SIM2 (SAFRAN-ISBA) daily data and keep the dept-66 cells.

    python -m src.ingest.safran                  # 2005..current year, resumable
    python -m src.ingest.safran --start 1990     # other first year

Source: data.gouv.fr "Données changement climatique - SIM quotidienne"
(dataset 6569b27598256cc583c917a7). One csv.gz per year for all of France
(~140 MB each, ~9,900 cells of 8 km), plus QUOT_SIM2_latest (last ~60 days).

Each year is streamed, filtered to the grid cells inside DEPT_BBOX, saved as
data/raw/safran/sim2_66_<year>.parquet, and the national file is deleted.
A sidecar <year>.json stores the server's Last-Modified: finished years are
skipped, and a year is re-fetched only when the server copy is newer (the
current year is updated monthly). The latest file is merged into the
current year so the series reaches yesterday.

Outputs (data/raw/safran/):
    grid_cells_66.parquet        cell id, Lambert II (m), lon/lat
    sim2_66_<year>.parquet       daily values for the kept cells
"""
import argparse
import datetime as dt
import json

import pandas as pd

from src.config import RAW
from src.web import TIMEOUT, make_session

BASE = "https://meteofrance.s3.sbg.io.cloud.ovh.net/data/REF_CC/SIM"
GRID_URL = f"{BASE}/coordonnees_grille_safran_lambert-2-etendu.csv"
OUT = RAW / "safran"
# Pyrénées-Orientales with a margin of about one cell (lon_min, lat_min, lon_max, lat_max).
# Wider than the plain on purpose: mountain rain feeds the Têt/Agly/Tech.
DEPT_BBOX = (1.65, 42.30, 3.25, 43.00)
# Variables kept (see SIM_QUOTIDIENNE_parametres.pdf): liquid/solid rain,
# temperature, potential ET (FAO-56 Penman-Monteith), actual ET, effective rain,
# soil wetness index, drainage below the root zone (recharge proxy), runoff.
KEEP = ["LAMBX", "LAMBY", "DATE", "PRELIQ", "PRENEI", "T", "ETP", "EVAP", "PE",
        "SWI", "DRAINC", "RUNC"]


def grid_cells(session):
    path = OUT / "grid_cells_66.parquet"
    if path.exists():
        return pd.read_parquet(path)
    raw = OUT / "coordonnees_grille_safran_lambert-2-etendu.csv"
    if not raw.exists():
        r = session.get(GRID_URL, timeout=TIMEOUT)
        r.raise_for_status()
        raw.write_bytes(r.content)
    g = pd.read_csv(raw, sep=";", decimal=",")
    g.columns = ["LAMBX", "LAMBY", "lat", "lon"]
    lon0, lat0, lon1, lat1 = DEPT_BBOX
    g = g[g["lon"].between(lon0, lon1) & g["lat"].between(lat0, lat1)].copy()
    g["cell_id"] = g["LAMBX"].astype(str) + "_" + g["LAMBY"].astype(str)
    g.to_parquet(path, index=False)
    return g


def remote_modified(session, url):
    r = session.head(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.headers.get("Last-Modified"), int(r.headers.get("Content-Length", 0))


def download(session, url, dest):
    tmp = dest.with_suffix(dest.suffix + ".part")
    with session.get(url, stream=True, timeout=TIMEOUT) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    tmp.replace(dest)


def filter_file(gz, cells):
    keys = set(zip(cells["LAMBX"], cells["LAMBY"]))
    parts = []
    for chunk in pd.read_csv(gz, sep=";", usecols=KEEP, chunksize=1_000_000):
        mask = [k in keys for k in zip(chunk["LAMBX"], chunk["LAMBY"])]
        parts.append(chunk[mask])
    df = pd.concat(parts, ignore_index=True)
    df["date"] = pd.to_datetime(df.pop("DATE").astype(str), format="%Y%m%d")
    return df


def fetch(session, name, cells, out_parquet):
    """Fetch QUOT_SIM2_<name>.csv.gz unless the cached extract is up to date."""
    url = f"{BASE}/QUOT_SIM2_{name}.csv.gz"
    meta_path = out_parquet.with_suffix(".json")
    modified, size = remote_modified(session, url)
    if out_parquet.exists() and meta_path.exists():
        if json.loads(meta_path.read_text())["last_modified"] == modified:
            return "cached", None
    gz = OUT / f"QUOT_SIM2_{name}.csv.gz"
    print(f"  {name}: downloading {size / 1e6:.0f} MB ...", flush=True)
    download(session, url, gz)
    df = filter_file(gz, cells)
    tmp = out_parquet.with_suffix(".parquet.part")
    df.to_parquet(tmp, index=False)
    tmp.replace(out_parquet)
    meta_path.write_text(json.dumps({"url": url, "last_modified": modified,
                                     "national_bytes": size, "rows": len(df),
                                     "retrieved": dt.date.today().isoformat()}))
    gz.unlink()
    return "downloaded", df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=2005)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    s = make_session()
    cells = grid_cells(s)
    print(f"{len(cells)} SAFRAN cells inside {DEPT_BBOX}")
    this_year = dt.date.today().year
    for year in range(args.start, this_year + 1):
        status, df = fetch(s, str(year), cells, OUT / f"sim2_66_{year}.parquet")
        if status == "cached":
            print(f"  {year}: cached")
        else:
            print(f"  {year}: {len(df):,} rows, {df['date'].min().date()} .. {df['date'].max().date()}")

    # Extend the current year with the rolling 'latest' file (last ~60 days).
    status, latest = fetch(s, "latest", cells, OUT / "sim2_66_latest.parquet")
    latest = pd.read_parquet(OUT / "sim2_66_latest.parquet")
    cur_path = OUT / f"sim2_66_{this_year}.parquet"
    cur = pd.read_parquet(cur_path)
    merged = (pd.concat([cur, latest[latest["date"].dt.year == this_year]])
              .drop_duplicates(["LAMBX", "LAMBY", "date"], keep="last")
              .sort_values(["date", "LAMBX", "LAMBY"]))
    if len(merged) != len(cur):
        merged.to_parquet(cur_path, index=False)
    print(f"  {this_year} extended with latest: up to {merged['date'].max().date()}")

    files = sorted(OUT.glob("sim2_66_[0-9]*.parquet"))
    total = sum(len(pd.read_parquet(f, columns=["date"])) for f in files)
    print(f"done: {len(files)} years, {total:,} cell-days, "
          f"{sum(f.stat().st_size for f in files) / 1e6:.1f} MB on disk")


if __name__ == "__main__":
    main()
