"""Data for the plain-language explainer (docs/explainer/), taken from the project's files.

    .venv/bin/python -m src.analysis.explainer_data      # -> docs/explainer/data.js

The explainer is a static page opened from the file system, so its data is a script
(`window.EXPLAINER = {...}`): browsers block fetch() on file:// pages. Every number drawn in
a chart comes from here. Sources:
    data/processed/dataset_v3, dataset_v4      wells, weekly levels, folds, build records
    data/processed/dataset_v1, dataset_v2      build records (meta.json)
    results/v3/<run>/metrics_summary.csv       scores of the baselines (v3 report)
    data/interim/pump_unit_attribution_eval.json   task 12.3
The numbers quoted in the text (Step 4 counts, BNPE totals, ...) come from CLAUDE.md and
the step notes.
"""
import json
import subprocess
from datetime import date

import geopandas as gpd
import numpy as np
import pandas as pd

from src.config import CRS_L93, CRS_WGS84, INTERIM, PROCESSED, ROOT, TEST_PERIODS

OUT = ROOT / "docs" / "explainer" / "data.js"
RESULTS_V3 = ROOT / "results" / "v3"
LAYER = {"recent alluvium": "alluvium", "ancient alluvium": "alluvium",
         "Pliocene multilayer": "pliocene", "Corbières karst": "karst"}
EXAMPLES = ["10908X0263/FIGUER", "10971X0155/PD5", "10972X0003/ALENYA", "10903X0034/PZSTGL",
            "10906X0039/C2-1", "10906X0038/C2-2"]
RUNS = [("naive_climatology", "Normal-year guess", "guess"),
        ("pastas_seasonal_canal", "Pastas, the hydrologists' tool", "hydro"),
        ("pastas_wellmodel", "Pastas with pump distances", "hydro"),
        ("lgbm_noclim_tuned", "LightGBM (many small decision trees)", "ml"),
        ("lstm_tuned", "LSTM (a network with memory)", "ml"),
        ("stgnn_tuned", "Graph network (wells talk to neighbours)", "ml"),
        ("ensemble_sim", "Team of models (average of the best)", "ml")]
TWIN_M = 1000  # wells closer than this count as "twins" in the fold picture


def wells():
    w3 = pd.read_parquet(PROCESSED / "dataset_v3" / "wells.parquet")
    w4 = pd.read_parquet(PROCESSED / "dataset_v4" / "wells.parquet")[["code_bss", "fold"]]
    w = w3.merge(w4.rename(columns={"fold": "fold4"}), on="code_bss")
    w["layer"] = w["group"].map(LAYER).fillna("other")
    depth = pd.to_numeric(w["profondeur_investigation"], errors="coerce")
    out = [{"code": r.code_bss, "name": (r.libelle_pe or r.code_bss).strip(),
            "town": r.nom_commune, "lon": round(r.x, 5), "lat": round(r.y, 5),
            "layer": r.layer, "depth": None if np.isnan(d) else round(float(d), 1),
            "core": bool(r.core), "fold3": int(r.fold), "fold4": int(r.fold4)}
           for r, d in zip(w.itertuples(), depth)]
    g = gpd.GeoSeries(gpd.points_from_xy(w["x"], w["y"]), crs=CRS_WGS84).to_crs(CRS_L93)
    xy = np.c_[g.x, g.y]
    pairs = []
    for i in range(len(w)):
        for j in range(i + 1, len(w)):
            dist = float(np.hypot(*(xy[i] - xy[j])))
            if dist < TWIN_M:
                pairs.append({"a": w.at[i, "code_bss"], "b": w.at[j, "code_bss"],
                              "m": round(dist), "split3": bool(w.at[i, "fold"] != w.at[j, "fold"]),
                              "split4": bool(w.at[i, "fold4"] != w.at[j, "fold4"])})
    return out, pairs


def series():
    h = pd.read_parquet(PROCESSED / "dataset_v4" / "heads_weekly.parquet")
    weeks = pd.date_range("2005-01-02", h["week"].max(), freq="W-SUN")
    out = {}
    for code in EXAMPLES:
        s = h[h["code_bss"] == code].set_index("week")["head"].reindex(weeks)
        out[code] = [None if np.isnan(v) else round(float(v), 2) for v in s]
    return {"start": str(weeks[0].date()), "n": len(weeks), "values": out}


def versions():
    rows = {}
    for v in ("v1", "v2", "v3", "v4"):
        m = json.loads((PROCESSED / f"dataset_{v}" / "meta.json").read_text())
        rows[v] = {"built": m["built"], "wells": m["rows"]["wells"],
                   "core": m["rows"]["core_wells"], "weeks": m["rows"]["heads_weekly"],
                   "pumps": m["rows"]["pumping_points"], "last_bnpe": m.get("last_bnpe_year"),
                   "dropped": (m.get("quality_filter") or {}).get("values_dropped", 0)}
    return rows


def scores():
    out = []
    for run, label, kind in RUNS:
        f = RESULTS_V3 / run / "metrics_summary.csv"
        if not f.exists():
            continue
        s = pd.read_csv(f)
        s = s[(s["group"] == "all core") & (s["variant"] == "all") & (s["task"] == "simulation")]
        val = lambda split, col: round(float(s.loc[s["split"] == split, col].iloc[0]), 2)  # noqa: E731
        out.append({"run": run, "label": label, "kind": kind,
                    "skill_drought": val("test_drought", "skill"),
                    "nse_drought": val("test_drought", "NSE"),
                    "skill_recovery": val("test_recovery", "skill")})
    return out


def attribution():
    ev = json.loads((INTERIM / "pump_unit_attribution_eval.json").read_text())
    plain = ev["coverage"]["plain"]
    order = ["confident", "probable", "possible", "unknown"]
    by_use = {u: {c: round(v.get(c, 0.0), 1) for c in order}
              for u, v in plain["volume_mm3_by_use"].items()}
    return {"by_confidence": {c: {"n": int(plain["by_confidence"][c]["n"]),
                                  "mm3": round(plain["by_confidence"][c]["volume_mm3"], 1)}
                              for c in order},
            "by_use": by_use,
            "rules": {k: {"fires": v["fires_on"], "precision": v["precision_group"]}
                      for k, v in ev["rules"].items()},
            "n_recorded": ev["n_recorded_boreholes"]}


def main():
    w, pairs = wells()
    data = {"generated": date.today().isoformat(),
            "commit": subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                     capture_output=True, text=True).stdout.strip(),
            "periods": {"train": ["2005-01-01", "2019-12-31"],
                        "validation": ["2020-01-01", "2022-04-30"],
                        "drought": list(TEST_PERIODS["test_drought"]),
                        "recovery": [TEST_PERIODS["test_recovery"][0], None]},
            "wells": w, "twins": pairs, "series": series(), "versions": versions(),
            "scores": scores(), "attribution": attribution()}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("// Generated by src/analysis/explainer_data.py; do not edit by hand.\n"
                   "window.EXPLAINER = " + json.dumps(data, ensure_ascii=False,
                                                      separators=(",", ":")) + ";\n",
                   encoding="utf-8")
    print(f"{OUT}: {OUT.stat().st_size / 1e3:.0f} kB; {len(w)} wells, {len(pairs)} twin pairs, "
          f"{len(data['scores'])} scored runs")


if __name__ == "__main__":
    main()
