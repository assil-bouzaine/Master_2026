"""Download Hub'Eau groundwater-level stations and series for one département.

    python -m src.ingest.hubeau_piezo            # resume: skip cached stations
    python -m src.ingest.hubeau_piezo --refresh  # re-download every series
    python -m src.ingest.hubeau_piezo --snapshot 2026-11-25   # full download into a dated folder

Outputs (data/raw/hubeau/):
    stations_<dept>.json                raw API response (all pages)
    stations_<dept>.parquet             flat table, one row per station
    chroniques/<code_bss>.parquet       one file per station (full history)

Each station is cached separately and written atomically, so a crash or
power cut never forces the whole download to restart.

--snapshot DAY (dataset v5, docs/v5_plan.md step R1.1b) downloads every series in full into
data/raw/hubeau/snapshots/<DAY>/ (stations files and chroniques/), resumable within that folder,
and leaves the default cache untouched: dataset v4 was built from that cache and must still
rebuild from cold. A full download also picks up the qualifications that changed since the
first pull (weeks validated later), which an incremental update would miss.
"""
import argparse
import json
import time

import pandas as pd

from src.config import DEPARTEMENT, RAW
from src.web import TIMEOUT, make_session

BASE = "https://hubeau.eaufrance.fr/api/v1/niveaux_nappes"
OUT = RAW / "hubeau"
CHRON = OUT / "chroniques"
PAGE_SIZE = 5000
MAX_DEPTH = 20000  # Hub'Eau refuses page * size beyond this


def fetch_all(session, url, params):
    """Follow the `next` links (HTTP 206 = more pages) and return all records."""
    records, count = [], None
    while url:
        r = session.get(url, params=params, timeout=TIMEOUT)
        if r.status_code not in (200, 206):
            r.raise_for_status()
        j = r.json()
        count = j.get("count")
        records.extend(j["data"])
        url, params = j.get("next"), None  # `next` already carries the query
    return records, count


def safe_name(code_bss: str) -> str:
    """BSS codes contain '/', e.g. 10906X0039/C2-1 -> 10906X0039_C2-1."""
    return code_bss.replace("/", "_")


def get_stations(session, dept, out=OUT):
    records, count = fetch_all(
        session, f"{BASE}/stations", {"code_departement": dept, "size": PAGE_SIZE}
    )
    assert len(records) == count, f"got {len(records)} stations, API says {count}"
    (out / f"stations_{dept}.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    df = pd.DataFrame(records).drop(columns=["geometry"])
    # one BD LISA code per station in practice; keep the list too
    df["code_bdlisa"] = df["codes_bdlisa"].map(lambda v: v[0] if v else None)
    for col in df.columns:  # lists -> ';'-joined strings so parquet stays simple
        if df[col].map(lambda v: isinstance(v, list)).any():
            df[col] = df[col].map(lambda v: ";".join(v) if isinstance(v, list) else v)
    df.to_parquet(out / f"stations_{dept}.parquet", index=False)
    return df


def get_series(session, code_bss, expected):
    if expected and expected > MAX_DEPTH:
        raise RuntimeError(
            f"{code_bss}: {expected} rows > {MAX_DEPTH}; split the request by date"
        )
    records, count = fetch_all(
        session, f"{BASE}/chroniques", {"code_bss": code_bss, "size": PAGE_SIZE}
    )
    if len(records) != count:
        raise RuntimeError(f"{code_bss}: got {len(records)} rows, API says {count}")
    return pd.DataFrame(records)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dept", default=DEPARTEMENT)
    ap.add_argument("--refresh", action="store_true", help="re-download cached series")
    ap.add_argument("--snapshot", metavar="DAY", help="full download into data/raw/hubeau/snapshots/DAY")
    args = ap.parse_args()

    out, chron = OUT, CHRON
    if args.snapshot:
        out = OUT / "snapshots" / args.snapshot
        chron = out / "chroniques"
    chron.mkdir(parents=True, exist_ok=True)
    session = make_session()

    stations = get_stations(session, args.dept, out)
    print(f"{len(stations)} stations in département {args.dept}")

    done = skipped = empty = 0
    failed = []
    for i, st in enumerate(stations.itertuples(), 1):
        path = chron / f"{safe_name(st.code_bss)}.parquet"
        if path.exists() and path.stat().st_size > 0 and not args.refresh:
            skipped += 1
            continue
        try:
            t0 = time.time()
            df = get_series(session, st.code_bss, st.nb_mesures_piezo)
        except Exception as e:  # keep going; report at the end
            failed.append((st.code_bss, repr(e)))
            print(f"[{i}/{len(stations)}] {st.code_bss}: FAILED {e!r}")
            continue
        if df.empty:
            empty += 1
        tmp = path.with_suffix(".tmp")
        df.to_parquet(tmp, index=False)
        tmp.replace(path)  # atomic: never leaves a half-written file
        done += 1
        print(f"[{i}/{len(stations)}] {st.code_bss}: {len(df):>6} rows ({time.time() - t0:.1f}s)")

    print(f"\ndownloaded {done}, cached {skipped}, empty {empty}, failed {len(failed)}")
    for code, err in failed:
        print("  FAILED", code, err)
    if failed:
        raise SystemExit("some stations failed; rerun to retry only those")


if __name__ == "__main__":
    main()
