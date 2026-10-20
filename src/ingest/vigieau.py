"""Download the drought restriction orders (VigiEau) and tidy them per alert zone and day.

    python -m src.ingest.vigieau            # skip files already cached

Source: data.gouv.fr "Donnée Sécheresse - VigiEau" (dataset 662a5e2cd71b24df5e9a0827),
one CSV per year ("Arrêtés 2012" ... "Arrêtés 2024") plus the current file "Arrêtés"
(orders still in force or recent). One row per order; the alert zones it covers,
their type (SUP = surface water, SOU = groundwater) and the gravity level are JSON
lists in the columns zones_alerte.*.

Use in this project (docs/analysis_plan.md section 7): only SURFACE-water zones.
Groundwater zones are triggered by piezometers of the aquifers we predict, so
their levels must never become a model input.

Outputs
    data/raw/vigieau/arretes-<year>.csv, arretes.csv     downloads (cached)
    data/interim/vigieau_levels_daily_66.parquet         day x zone: level 0-4
        0 none, 1 vigilance, 2 alerte, 3 alerte renforcée, 4 crise
"""
import json

import pandas as pd

from src.config import DEPARTEMENT, INTERIM, RAW
from src.web import make_session

DATASET = "https://www.data.gouv.fr/api/1/datasets/662a5e2cd71b24df5e9a0827/"
OUT = RAW / "vigieau"
LEVEL = {"vigilance": 1, "alerte": 2, "alerte_renforcee": 3, "crise": 4}
FIRST_YEAR = 2012


def download(session):
    OUT.mkdir(parents=True, exist_ok=True)
    meta = session.get(DATASET, timeout=60).json()
    wanted = {f"Arrêtés {y}": OUT / f"arretes-{y}.csv" for y in range(FIRST_YEAR, 2100)}
    wanted["Arrêtés"] = OUT / "arretes.csv"
    for r in meta["resources"]:
        dest = wanted.get(r["title"])
        if dest is None:
            continue
        if dest.exists() and dest.stat().st_size > 0:
            print(f"cached {dest.name}")
            continue
        data = session.get(r["url"], timeout=120).content
        tmp = dest.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(dest)
        print(f"downloaded {dest.name}: {len(data) / 1e6:.2f} MB")


def zone_orders(dept=DEPARTEMENT):
    """One row per order x alert zone for the département."""
    rows = []
    for f in sorted(OUT.glob("arretes*.csv")):
        d = pd.read_csv(f, dtype=str)
        d = d[d["departement"] == dept]
        for _, a in d.iterrows():
            try:
                cols = [json.loads(a[f"zones_alerte.{k}"]) for k in ("type", "code", "nom",
                                                                    "niveau_gravite")]
            except (TypeError, ValueError):
                continue
            for t, code, name, lev in zip(*cols):
                rows.append({"order_id": a["id"], "start": a["date_debut"], "end": a["date_fin"],
                             "signed": a["date_signature"], "type": t, "zone_code": code,
                             "zone": name, "level": LEVEL.get(lev, 0)})
    z = pd.DataFrame(rows).drop_duplicates(["order_id", "zone_code", "zone"])
    for c in ("start", "end", "signed"):
        z[c] = pd.to_datetime(z[c], errors="coerce")
    return z


def daily_levels(z, end):
    """Day x zone level; when orders overlap, the one that starts last applies."""
    days = pd.date_range(f"{FIRST_YEAR}-01-01", end, freq="D")
    out = []
    for (t, name), g in z.groupby(["type", "zone"]):
        s = pd.Series(0, index=days, dtype=int)
        for _, a in g.sort_values(["start", "signed"]).iterrows():
            stop = a["end"] if pd.notna(a["end"]) else days[-1]
            s[(s.index >= a["start"]) & (s.index <= stop)] = a["level"]
        out.append(pd.DataFrame({"day": days, "type": t, "zone": name, "level": s.values}))
    return pd.concat(out, ignore_index=True)


def main():
    download(make_session())
    z = zone_orders()
    lv = daily_levels(z, pd.Timestamp.today().normalize())
    INTERIM.mkdir(parents=True, exist_ok=True)
    lv.to_parquet(INTERIM / f"vigieau_levels_daily_{DEPARTEMENT}.parquet", index=False)
    print(f"{z['order_id'].nunique()} orders, {z['zone'].nunique()} zone names "
          f"({(z['type'] == 'SUP').sum()} surface / {(z['type'] == 'SOU').sum()} groundwater rows)")
    sup = lv[(lv["type"] == "SUP") & lv["zone"].str.contains("Têt") & lv["day"].dt.month.between(4, 9)]
    d = sup.groupby("day")["level"].max()
    print("Têt surface zones, days at 'crise' in April-September:")
    print((d >= 4).groupby(d.index.year).sum().to_string())


if __name__ == "__main__":
    main()
