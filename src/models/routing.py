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
    rain, ETP, PE         weighted mean over its recharge-edge cells (weights renormalised to 1)
    DRAINC               the same mean for soil drainage, when requested for B7
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
Pumping robustness (analysis plan §8 and §10): reconstruction 1 is the current profile, 2 keeps
drinking water flat, and 3 uses crop-calendar irrigation with seasonal drinking water. The same
weekly reconstruction supplies both facility pumping and the canal proxy for every routed arm.
"""
import json

import numpy as np
import pandas as pd

from src.config import DATASET, DATASET_DIR, INTERIM, PROCESSED
from src.dataset.pumping import canal_series, seasonal_drinking_water
from src.models.features import river_series

DEFAULT_WEATHER = ("rain", "ETP", "PE")
WEATHER = (*DEFAULT_WEATHER, "DRAINC")
EXPORT = PROCESSED / "kg"
RECONSTRUCTIONS = {1: "current", 2: "flat drinking water", 3: "crop calendar"}


def load_edges(arm, policy="main", dataset=DATASET):
    d = EXPORT / f"export_{dataset}_{policy}"
    meta = json.loads((d / "manifest.json").read_text())
    return pd.read_parquet(d / f"edges_{arm}.parquet"), meta


CONTROL_KINDS = ("E_degree", "E_distance", "F_random", "F_complete")


def baseline_edges():
    """The panel's own rules written as edges ("baseline inputs, no graph", arms A and B of
    analysis plan §10): each well's own SAFRAN cell, the groundwater facilities inside the panel's
    3 km buffer (weight 1; the same buffer polygon and "contains" predicate as
    src/dataset/load.py, whose 64 sides lie up to 3.6 m inside the circle), and the plain's canal
    for every well. tests/test_routing.py checks that they reproduce the panel's columns exactly;
    routing them lets arms A and B use the pumping reconstructions like every graph arm."""
    import geopandas as gpd

    from src.config import CRS_L93, CRS_WGS84
    from src.dataset.load import PUMP_RADIUS_KM
    from src.kg import export as E
    wells, fac, _, _ = E.tables()
    gw = gpd.GeoDataFrame(wells[["code_bss"]], geometry=gpd.points_from_xy(wells["x"], wells["y"]),
                          crs=CRS_WGS84).to_crs(CRS_L93)
    gw["geometry"] = gw.buffer(PUMP_RADIUS_KM * 1000)
    gf = gpd.GeoDataFrame(fac[["code_ouvrage"]], geometry=gpd.points_from_xy(fac["longitude"], fac["latitude"]),
                          crs=CRS_WGS84).to_crs(CRS_L93)
    near = gpd.sjoin(gw, gf, predicate="contains")
    d = E._dist(wells, fac)
    row = {c: i for i, c in enumerate(wells["code_bss"])}
    col = {c: j for j, c in enumerate(fac["code_ouvrage"])}
    rows = [E.edge("recharge", "weather_cell", c, w, 1.0) for w, c in zip(wells["code_bss"], wells["cell_id"])]
    rows += [E.edge("canal", "canal", E.CANAL, w, 1.0) for w in wells["code_bss"]]
    rows += [E.edge("pumping", "facility", f, w, 1.0, d[row[w], col[f]])
             for w, f in sorted(zip(near["code_bss"], near["code_ouvrage"]))]
    return pd.DataFrame(rows, columns=E.EDGE_COLS)


def parse_arm(arm):
    """"baseline" (the panel's rules), "C", "D", or a control of analysis plan §14 item 20 written
    "<kind>:<draw>" (F_complete has one draw) -> (kind, draw); anything else is an error."""
    if arm in ("baseline", "C", "D"):
        return arm, None
    kind, sep, draw = str(arm).partition(":")
    if kind == "F_complete" and not sep:
        return kind, 0
    if kind in CONTROL_KINDS and kind != "F_complete" and sep and draw.isdigit():
        return kind, int(draw)
    raise ValueError(f"unknown arm {arm!r}: C, D, E_degree:<draw>, E_distance:<draw>, "
                     "F_random:<draw> or F_complete")


def load_arm(arm, policy="main", dataset=DATASET):
    """Edges and provenance of a graph arm: the export's C or D, or a control graph built from D
    (src/kg/controls.py), which refuses to load if the export changed since it was built."""
    kind, draw = parse_arm(arm)
    if kind == "baseline":            # no graph: nothing from the export, so no release to record
        return baseline_edges(), {"release": None, "policy": "baseline (panel rules, no graph)",
                                  "code_version": None, "control": "baseline"}
    if draw is None:
        return load_edges(arm, policy, dataset)
    from src.kg.controls import load_control
    edges = load_control(kind, draw, policy, dataset)
    m = json.loads((EXPORT / f"export_{dataset}_{policy}" / "controls" / "manifest.json").read_text())
    return edges, {"release": m["release"], "policy": m["policy"], "code_version": m["code_version"],
                   "control": arm, "export_sha256": m["export_sha256"]}


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


def pumping_table(reconstruction=1):
    """Weekly pumping before the drinking-water re-spread; preserve the dataset's columns."""
    if reconstruction not in RECONSTRUCTIONS:
        raise ValueError(f"unknown pumping reconstruction {reconstruction!r}: {RECONSTRUCTIONS}")
    path = (INTERIM / f"pumping_weekly_cropcal_{DATASET}.parquet" if reconstruction == 3
            else DATASET_DIR / "pumping_weekly.parquet")
    if reconstruction == 3 and not path.is_file():
        raise FileNotFoundError(f"{path} is missing; run python -m src.dataset.pumping_cropcal")
    return pd.read_parquet(path)


def facility_volumes(weeks, facilities=None, reconstruction=1):
    """Weekly groundwater volumes (thousand m3/week), as a weeks x facility table.

    Reconstructions 1 and 3 re-spread drinking water seasonally; reconstruction 2 keeps the
    dataset's flat drinking-water profile. Pumping stresses are weighted sums of the columns.
    """
    pw = pumping_table(reconstruction)
    pts = pd.read_parquet(DATASET_DIR / "pumping_points.parquet")
    sp = seasonal_drinking_water(pw, pts) if reconstruction != 2 else pw
    if facilities is None:
        facilities = sorted(pts.loc[pts["source"] == "groundwater", "code_ouvrage"].unique())
    sp = sp[sp["code_ouvrage"].isin(facilities)]
    return (sp.groupby(["week", "code_ouvrage"])["volume_m3"].sum().unstack("code_ouvrage")
            .reindex(index=pd.DatetimeIndex(weeks), columns=list(facilities)).fillna(0.0) / 1e3)


def routed_inputs(arm=None, policy="main", edges=None, codes=None, weeks=None, recharge="recharge",
                  volumes=None, reconstruction=1, river_rule="declared", *, include_drainc=False):
    """Inputs of the wells `codes` on `weeks` (default: the dataset's wells and the panel's
    weeks) routed by the edges of `arm` (or by an explicit `edges` table with the export's
    columns). `recharge` names the relation used for the weather ("recharge", or
    "recharge_unitwide" for arm D's sensitivity). `include_drainc` adds soil drainage over those
    cells as a replacement recharge proxy (analysis plan §14 item 15).
    `reconstruction` selects the pumping and canal table for every arm, including baseline
    inputs and graph controls. `river_rule` selects the gap rule
    of the river series (src.models.features.river_series): "declared" (analysis plan §7b; every
    real-data arm), "legacy" only for the twin, which pins the series of its first worlds."""
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
        edges, meta = load_arm(arm, policy)
    out = {"codes": codes, "weeks": weeks, "arm": arm, "reconstruction": int(reconstruction),
           "export": meta and
           {k: meta[k] for k in ("release", "policy", "code_version", "control", "export_sha256")
            if k in meta}}
    # weather: weighted mean over the recharge-edge cells
    e = edges[edges["relation"] == recharge]
    cells = sorted(e["src"].unique())
    W = _matrix(edges, recharge, codes, cells)
    tot = W.sum(1, keepdims=True)
    out["has_recharge"] = tot[:, 0] > 0
    Wn = np.divide(W, tot, out=np.zeros_like(W), where=tot > 0)
    f = forcing[forcing["cell_id"].isin(cells)]
    weather = WEATHER if include_drainc else DEFAULT_WEATHER
    for v in weather:
        series = f.pivot(index="week", columns="cell_id", values=v).reindex(index=weeks, columns=cells)
        out[v] = Wn @ series.to_numpy(dtype=float).T                     # (N, T)
    # pumping: weighted sums of the facilities' weekly volumes (thousand m3/week)
    pw = pumping_table(reconstruction)
    pts = pd.read_parquet(DATASET_DIR / "pumping_points.parquet")
    pe = edges[edges["relation"].isin(("pumping", "pumping_unattributed"))]
    fac = sorted(pe["src"].unique())
    table = facility_volumes(weeks, fac, reconstruction) if volumes is None else volumes
    vol = table.reindex(index=weeks, columns=fac).fillna(0.0).to_numpy().T      # (facilities, T)
    for name, rel in (("pump_gw", "pumping"), ("pump_un", "pumping_unattributed")):
        Wp = _matrix(edges, rel, codes, fac)
        out[name] = Wp @ vol
        out["has_" + rel] = Wp.sum(1) > 0
    # rivers: weighted mean of log(1 + discharge) over the river-edge gauges
    riv = river_series(weeks, splits["train"][1], rule=river_rule)
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
