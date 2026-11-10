"""Per-well input series of a graph arm, from the export's edge tables (ladder rung 4).

    from src.models.routing import routed_inputs
    R = routed_inputs("D")          # dict of (N wells, T weeks) arrays + coverage flags

The response model (src/models/response.py) reads one series per stress and well. For the first
rungs these come from the feature panel: the weather of the well's own SAFRAN cell, the pumping
within 3 km, the plain's canal volume. Here they come from the edges of an arm
(src/kg/export.py): arm C's distance rules or arm D's knowledge-graph edges. Nothing else changes,
so two runs that differ only in the arm differ only in which sources reach each well (analysis
plan §10, the experiment contract; §14 item 18, rung 4).

    stress               series of a well
    rain, ETP, PE        weighted mean over its recharge-edge cells (weights renormalised to 1)
    pump_gw              sum over its pumping edges of weight x the facility's weekly volume
    pump_un              the same over its "pumping_unattributed" edges (arm D; zero in arm C,
                         whose distance rule connects every facility): the explicit unattributed
                         input, never zero by omission (analysis plan §8)
    river                weighted mean over its river edges of log(1 + weekly discharge)
    canal                the plain's canal volume if it has a canal edge, else 0

Units as in the panel (mm/week; thousand m3/week before the response model's scaling; Mm3/week).
A well without an edge for a relation gets zeros for that stress and has_<relation> = False:
arm D has no distance fallback (item 14), and the share of wells without each relation is
reported beside every D vs C result. Facility volumes use the seasonal drinking-water profile,
like every baseline. tests/test_routing.py checks that the "baseline" edges (own cell, facilities
within 3 km with weight 1, the canal for every well) reproduce the panel's columns exactly.
"""
import json

import numpy as np
import pandas as pd

from src.config import DATASET, DATASET_DIR, PROCESSED
from src.dataset.pumping import canal_series, seasonal_drinking_water
from src.models.features import river_series

WEATHER = ("rain", "ETP", "PE")
EXPORT = PROCESSED / "kg"


def load_edges(arm, policy="main", dataset=DATASET):
    d = EXPORT / f"export_{dataset}_{policy}"
    meta = json.loads((d / "manifest.json").read_text())
    return pd.read_parquet(d / f"edges_{arm}.parquet"), meta


def _matrix(edges, relation, codes, sources):
    """(N wells, S sources) weights of one relation; rows = codes, columns = sources."""
    e = edges[edges["relation"] == relation]
    row = {c: i for i, c in enumerate(codes)}
    col = {s: j for j, s in enumerate(sources)}
    W = np.zeros((len(codes), len(sources)))
    for s, d, w in zip(e["src"], e["dst"], e["weight"]):
        if d in row:
            W[row[d], col[s]] = w
    return W


def routed_inputs(arm=None, policy="main", edges=None, codes=None, weeks=None, recharge="recharge"):
    """Inputs of the wells `codes` on `weeks` (default: the dataset's wells and the panel's
    weeks) routed by the edges of `arm` (or by an explicit `edges` table with the export's
    columns). `recharge` names the relation used for the weather ("recharge", or
    "recharge_unitwide" for arm D's sensitivity)."""
    splits = json.loads((DATASET_DIR / "splits.json").read_text())
    wells = pd.read_parquet(DATASET_DIR / "wells.parquet")
    forcing = pd.read_parquet(DATASET_DIR / "forcing_weekly.parquet")
    heads = pd.read_parquet(DATASET_DIR / "heads_weekly.parquet", columns=["week"])
    if weeks is None:
        weeks = pd.date_range(forcing["week"].min(), heads["week"].max(), freq=splits["week_rule"])
    weeks = pd.DatetimeIndex(weeks)
    codes = list(wells["code_bss"]) if codes is None else list(codes)
    meta = None
    if edges is None:
        edges, meta = load_edges(arm, policy)
    out = {"codes": codes, "weeks": weeks, "arm": arm, "export": meta and
           {"release": meta["release"], "policy": meta["policy"], "code_version": meta["code_version"]}}
    # weather: weighted mean over the recharge-edge cells
    e = edges[edges["relation"] == recharge]
    cells = sorted(e["src"].unique())
    W = _matrix(edges, recharge, codes, cells)
    tot = W.sum(1, keepdims=True)
    out["has_recharge"] = tot[:, 0] > 0
    Wn = np.divide(W, tot, out=np.zeros_like(W), where=tot > 0)
    f = forcing[forcing["cell_id"].isin(cells)]
    for v in WEATHER:
        series = f.pivot(index="week", columns="cell_id", values=v).reindex(index=weeks, columns=cells)
        out[v] = Wn @ series.to_numpy(dtype=float).T                     # (N, T)
    # pumping: weighted sums of the facilities' weekly volumes (thousand m3/week)
    pw = pd.read_parquet(DATASET_DIR / "pumping_weekly.parquet")
    pts = pd.read_parquet(DATASET_DIR / "pumping_points.parquet")
    pe = edges[edges["relation"].isin(("pumping", "pumping_unattributed"))]
    fac = sorted(pe["src"].unique())
    sp = seasonal_drinking_water(pw, pts)
    vol = (sp[sp["code_ouvrage"].isin(fac)].groupby(["week", "code_ouvrage"])["volume_m3"].sum()
           .unstack("code_ouvrage").reindex(index=weeks, columns=fac).fillna(0.0).to_numpy().T / 1e3)
    for name, rel in (("pump_gw", "pumping"), ("pump_un", "pumping_unattributed")):
        Wp = _matrix(edges, rel, codes, fac)
        out[name] = Wp @ vol
        out["has_" + rel] = Wp.sum(1) > 0
    # rivers: weighted mean of log(1 + discharge) over the river-edge gauges
    riv = river_series(weeks, splits["train"][1])
    gauges = sorted(edges.loc[edges["relation"] == "river", "src"].unique())
    Wr = _matrix(edges, "river", codes, gauges)
    tot = Wr.sum(1, keepdims=True)
    out["has_river"] = tot[:, 0] > 0
    out["river"] = (np.divide(Wr, tot, out=np.zeros_like(Wr), where=tot > 0)
                    @ riv[gauges].to_numpy(dtype=float).T) if gauges else np.zeros((len(codes), len(weeks)))
    # canal: the plain's canal volume (Mm3/week) for the wells with a canal edge
    canal = canal_series(pw, pts).reindex(weeks).fillna(0.0).to_numpy() / 1e6
    has = np.isin(codes, edges.loc[edges["relation"] == "canal", "dst"].unique())
    out["has_canal"] = has
    out["canal"] = has[:, None] * canal[None, :]
    return out


def coverage(R, core):
    """Share of wells (all, core) with each relation: reported beside every arm result."""
    core = np.asarray(core, dtype=bool)
    return {k[4:]: {"wells": int(R[k].sum()), "core_wells": int((R[k] & core).sum())}
            for k in R if k.startswith("has_")}
