"""Profile Hub'Eau piezometer series and select the working set.

    python -m src.analysis.piezo_profile

Inputs : data/raw/hubeau/stations_66.parquet, data/raw/hubeau/chroniques/*.parquet
Outputs: data/interim/piezo_stations.{parquet,csv}       one row per station
         data/interim/piezo_working_set.{parquet,csv}    stations passing all filters
         data/interim/piezo_series_window.parquet        working-set series, 2016-2025
         reports/figures/piezo_stations_record_length.png
"""
import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd

from src.config import CRS_WGS84, DEPARTEMENT, FIGURES, INTERIM, RAW, WINDOW_END, WINDOW_START
from src.ingest.hubeau_piezo import CHRON, safe_name

# --- Working-set criteria (CLAUDE.md section 7, Step 4) ---------------------
MIN_YEARS = 8
ACTIVE_SINCE = "2024-01-01"
MIN_OBS_PER_YEAR = 50

# --- Extent of the Roussillon plain -----------------------------------------
# Bounding box in WGS84 degrees (lon_min, lat_min, lon_max, lat_max). See
# data/README.md "Study-area definition" for how it was chosen.
PLAIN_BBOX = (2.55, 42.50, 3.06, 42.88)

# BD LISA level-3 entities of the plain's aquifer system (reported, not filtered on)
PLAIN_ENTITIES = {
    "718BP": "recent alluvium (Têt/Agly/Réart/Tech)",
    "671AB": "ancient alluvium",
    "671AA": "Pliocene multilayer",
}


def layer_of(code):
    if not code:
        return "unknown"
    for prefix, name in PLAIN_ENTITIES.items():
        if code.startswith(prefix):
            return name
    return "outside plain aquifers"


def profile_station(code_bss):
    df = pd.read_parquet(CHRON / f"{safe_name(code_bss)}.parquet")
    if df.empty:
        return {"code_bss": code_bss, "n_obs": 0}
    d = pd.to_datetime(df["date_mesure"])
    start, end = d.min(), d.max()
    span_days = (end - start).days + 1
    years = span_days / 365.25
    days = d.dt.normalize().nunique()
    w = d[(d >= WINDOW_START) & (d <= WINDOW_END)]
    w_days_total = (pd.Timestamp(WINDOW_END) - pd.Timestamp(WINDOW_START)).days + 1
    return {
        "code_bss": code_bss,
        "start": start,
        "end": end,
        "record_years": round(years, 2),
        "n_obs": len(df),
        "obs_per_year": round(len(df) / years, 1),
        "pct_missing_days": round(100 * (1 - days / span_days), 1),
        "n_obs_window": len(w),
        "pct_missing_days_window": round(100 * (1 - w.dt.normalize().nunique() / w_days_total), 1),
    }


def main():
    INTERIM.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)

    st = pd.read_parquet(RAW / "hubeau" / f"stations_{DEPARTEMENT}.parquet")
    prof = pd.DataFrame([profile_station(c) for c in st["code_bss"]])
    keep = ["code_bss", "bss_id", "libelle_pe", "nom_commune", "x", "y",
            "altitude_station", "profondeur_investigation", "code_bdlisa",
            "codes_masse_eau_edl", "noms_masse_eau_edl"]
    t = st[keep].merge(prof, on="code_bss", how="left")
    t["layer"] = t["code_bdlisa"].map(layer_of)

    lon0, lat0, lon1, lat1 = PLAIN_BBOX
    t["ok_years"] = t["record_years"] >= MIN_YEARS
    t["ok_active"] = t["end"] >= ACTIVE_SINCE
    t["ok_freq"] = t["obs_per_year"] >= MIN_OBS_PER_YEAR
    t["ok_plain"] = t["x"].between(lon0, lon1) & t["y"].between(lat0, lat1)
    t["working_set"] = t[["ok_years", "ok_active", "ok_freq", "ok_plain"]].all(axis=1)

    t.to_parquet(INTERIM / "piezo_stations.parquet", index=False)
    t.to_csv(INTERIM / "piezo_stations.csv", index=False)
    ws = t[t["working_set"]].reset_index(drop=True)
    ws.to_parquet(INTERIM / "piezo_working_set.parquet", index=False)
    ws.to_csv(INTERIM / "piezo_working_set.csv", index=False)

    # Working-set series restricted to the common window
    cols = ["code_bss", "date_mesure", "niveau_nappe_eau", "profondeur_nappe",
            "qualification", "statut", "mode_obtention"]
    series = pd.concat(
        [pd.read_parquet(CHRON / f"{safe_name(c)}.parquet", columns=cols) for c in ws["code_bss"]],
        ignore_index=True,
    )
    series["date_mesure"] = pd.to_datetime(series["date_mesure"])
    series = series[series["date_mesure"].between(WINDOW_START, WINDOW_END)]
    series.to_parquet(INTERIM / "piezo_series_window.parquet", index=False)

    # --- Report -----------------------------------------------------------
    print(f"stations in dept {DEPARTEMENT}: {len(t)}")
    print(f"  >= {MIN_YEARS} y record and active since {ACTIVE_SINCE}: "
          f"{(t.ok_years & t.ok_active).sum()}")
    print(f"  ... and >= {MIN_OBS_PER_YEAR} obs/year: {(t.ok_years & t.ok_active & t.ok_freq).sum()}")
    print(f"  ... and inside plain bbox = WORKING SET: {len(ws)}")
    print("\nworking set by layer:")
    print(ws.groupby(["layer", "code_bdlisa"], dropna=False)
            .agg(n=("code_bss", "size"), median_record_years=("record_years", "median"))
            .to_string())
    print(f"\nmeasurements {WINDOW_START[:4]}-{WINDOW_END[:4]} (working set): {len(series):,}")
    print("qualification:", series["qualification"].value_counts(dropna=False).to_dict())

    # --- Map --------------------------------------------------------------
    g = gpd.GeoDataFrame(t, geometry=gpd.points_from_xy(t.x, t.y), crs=CRS_WGS84)
    fig, ax = plt.subplots(figsize=(9, 8))
    out = g[~g.working_set]
    ax.scatter(out.x, out.y, s=18, facecolors="none", edgecolors="grey",
               linewidths=0.8, label="not in working set")
    sc = ax.scatter(g[g.working_set].x, g[g.working_set].y, c=g[g.working_set].record_years,
                    cmap="viridis", s=55, edgecolors="black", linewidths=0.5,
                    label="working set")
    fig.colorbar(sc, ax=ax, shrink=0.7, label="record length (years)")
    ax.plot([lon0, lon1, lon1, lon0, lon0], [lat0, lat0, lat1, lat1, lat0],
            "--", color="tab:red", lw=1, label="plain extent (bbox)")
    ax.set_xlabel("longitude (°E)")
    ax.set_ylabel("latitude (°N)")
    ax.set_aspect(1 / 0.735)  # cos(42.7°): keeps distances undistorted
    ax.set_title(f"Hub'Eau piezometers, dept {DEPARTEMENT}: {len(ws)} of {len(t)} in working set")
    ax.legend(loc="lower left", fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIGURES / "piezo_stations_record_length.png", dpi=150)
    print(f"\nmap -> {FIGURES / 'piezo_stations_record_length.png'}")


if __name__ == "__main__":
    main()
