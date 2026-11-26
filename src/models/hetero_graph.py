"""Knowledge graph as a PyTorch Geometric HeteroData, and static-only graph encoder (Hybrid-GNN v2).

Implements analysis plan v3 §3.5 (`docs/analysis_plan_v3.md`).

Why this module exists
----------------------
In v4, the hybrid response model predicted per-well parameters from each well's own static
facts (`src/models/statics.py`, rung 3) or from a single-relation mean over well links
(`src/models/message.py`, rung 5). Hybrid-GNN v2 replaces that map with a heterogeneous graph
network that reads the full exported knowledge graph: wells, pumping facilities, SAFRAN
weather cells, river gauges, canals (and in v5, aquifer units, basin canals, and additional
hydrogeological relations such as ``monitors``, ``overlies``, ``recharge_leakage``, and
``recharge_regional``).

The no-stress rule (analysis plan v3 §3.5)
------------------------------------------
The ontology's response-sign constraints (for example, abstraction never raises head and rain
never lowers it) hold on the whole path only if the response parameters depend on static facts
and graph structure, never on a weekly forcing or head series. Therefore:

1. Every node feature in ``build_heterodata`` is a static fact or a training-window summary
   computed strictly inside ``[train_start, train_end]`` (default 2005-01-01 to 2019-12-31,
   matching ``statics.training_window``). Nothing from validation or test weeks ever enters.
2. ``HeteroEncoder.forward`` reads only ``x``, ``edge_index``, and ``edge_attr`` from the
   ``HeteroData`` object. No weekly time series is passed to or stored in the encoder.

Graph structure and features
----------------------------
- One node type per export node type, preserving the row order of ``nodes.parquet`` within
  each type. ``index`` maps ``node_type -> {node_code: row_index}``.
- One forward edge type ``(src_type, relation, dst_type)`` per export relation, plus an
  explicit reverse edge type ``(dst_type, f"rev_{relation}", src_type)`` with flipped indices
  and copied attributes so messages flow both ways while keeping every directed forward
  relation intact (including directed homogeneous relations such as v5's ``overlies``).
- ``edge_attr`` encodes ``[weight, log1p(distance_m / 1000), sign, eligible, constrained]``.
  Missing values are filled with ``0.0`` and a ``<col>_missing`` binary flag is appended for
  every column that has gaps in the export's edge table.
- Node features:
  - ``well``: ``statics.static_table(features="B", ...)`` standardised with
    ``statics.standardise`` (continuous columns mean 0 / sd 1, flags unchanged).
  - ``facility``: ``log1p`` of mean annual declared volume (training window, global declared
    year denominator as in ``statics.declared_volumes``), dominant training-window use one-hot
    (drinking water, irrigation, industry, other), and groundwater source flag; standardised
    per feature over all facility nodes (constant columns left at 0).
  - ``weather_cell``: training-window mean weekly precipitation, ETP, and effective
    precipitation, standardised over all weather-cell nodes.
  - ``gauge``: ``log1p`` of training-window mean weekly discharge, standardised over all gauge
    nodes.
  - ``canal``: ``log1p`` of training-window mean weekly canal volume (plain-wide in v4, or
    per-basin when ``canal_basins_weekly.parquet`` is available in v5), standardised over all
    canal nodes (left at 0 when there is only a single canal node).
  - ``aquifer_unit``: one-hot of ``unit_type`` over the five ontology classes
    (``alluvial_aquifer``, ``confining_unit``, ``karst_aquifer``,
    ``multilayer_aquifer_system``, ``unit``), standardised with ``_standardise_matrix``
    (matching the facility use one-hots).
  - Any other unknown node type: a single documented constant feature ``const_one = 1.0``
    (kept at 1.0, not zeroed).

Encoder architecture
--------------------
``HeteroEncoder`` projects each node type linearly to ``hidden=32``, applies two layers of
``HeteroConv`` with ``GATv2Conv`` per edge type (``heads=2``, ``concat=False``,
``dropout=0.1``, ``add_self_loops=False``, ``edge_dim=edge_attr.shape[1]``) with residual
connections (so nodes with no incoming edges or single-edge softmax preserve their own static
features without enlarging the 2-hop receptive field) and ELU between layers, and ends with a
linear head from the well embeddings to ``n_out`` raw parameters initialised to exact zero.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.data import HeteroData
from torch_geometric.nn import GATv2Conv, HeteroConv

from src.config import DATASET_DIR
from src.dataset.pumping import canal_series
from src.models import statics

# Forbidden weekly series names from the dataset's weekly tables (no node feature may carry
# a raw weekly stress series).
FORBIDDEN_WEEKLY_VARS = frozenset({
    "rain", "ETP", "PE", "DRAINC", "PRELIQ", "PRENEI", "EVAP", "RUNC", "T", "SWI",
    "q_m3s", "volume_m3", "head", "pump_gw", "pump_un",
})

SIGN_MAP = {
    "PositiveResponse": 1.0,
    "NegativeResponse": -1.0,
    "UnknownResponse": 0.0,
    "mixed": 0.0,
}

USE_CATEGORIES = ("drinking water", "irrigation", "industry", "other")
USE_COLUMNS = ("use_drinking_water", "use_irrigation", "use_industry", "use_other")
FACILITY_COLUMNS = ("log_annual_declared_vol", *USE_COLUMNS, "source_groundwater")
WEATHER_COLUMNS = ("clim_precip_mean", "clim_atm_demand_mean", "clim_net_precip_mean")
GAUGE_COLUMNS = ("clim_log_mean_discharge",)
CANAL_COLUMNS = ("clim_log_mean_canal_vol",)
UNIT_TYPE_CATEGORIES = (
    "alluvial_aquifer",
    "confining_unit",
    "karst_aquifer",
    "multilayer_aquifer_system",
    "unit",
)
# Prefix with "unit_class_" (not "unit_type_") so no feature name contains the weekly token "pe".
UNIT_TYPE_COLUMNS = tuple(f"unit_class_{cat}" for cat in UNIT_TYPE_CATEGORIES)
UNKNOWN_COLUMNS = ("const_one",)


def _load_table(tables, key, default_path):
    """Return an injected DataFrame without modifying it, or load the parquet from disk."""
    if tables is not None and key in tables:
        return tables[key]
    return pd.read_parquet(default_path)


def _standardise_matrix(df):
    """Standardise every column to mean 0 and population sd 1; constant/empty columns -> 0.

    Returns ``(float32 ndarray, column_names, stats_dict)``. Missing entries become 0 after
    standardisation so the GNN never receives NaN.
    """
    names = list(df.columns)
    values = df.astype(float)
    means = values.mean().fillna(0.0)
    raw_sds = values.std(ddof=0)
    constant = raw_sds.isna() | (raw_sds == 0.0)
    sds = raw_sds.where(~constant, 1.0)
    scaled = ((values - means) / sds).fillna(0.0)
    for col in names:
        if constant[col]:
            scaled[col] = 0.0
    Z = scaled.to_numpy(dtype=np.float32)
    return Z, names, {"mean": means.to_dict(), "sd": sds.to_dict()}


def _well_features(codes, train_start, policy, tables, static_edges, pumping_weekly, pumping_points,
                   features="B"):
    """Well static features: statics.static_table(features) in export well order, standardised
    (set B, the knowledge-graph facts, for every graph arm; set A only for arm A)."""
    statics_tables = {
        "wells": _load_table(tables, "wells", DATASET_DIR / "wells.parquet"),
        "pumping_weekly": pumping_weekly,
        "pumping_points": pumping_points,
        "edges": static_edges,
    }
    raw = statics.static_table(features=features, train_start=train_start, policy=policy, tables=statics_tables)
    raw = raw.reindex(codes)
    return statics.standardise(raw)


def _facility_features(codes, start, end, pumping_weekly, pumping_points):
    """Facility static features computed strictly from declared rows inside [start, end]."""
    weeks = pd.to_datetime(pumping_weekly["week"])
    keep = pumping_weekly["imputed"].eq(False) & weeks.between(start, end)
    dec = pumping_weekly.loc[keep, ["code_ouvrage", "usage", "volume_m3"]]
    years = sorted(int(y) for y in weeks.loc[keep].dt.year.unique())

    if years:
        annual = dec.groupby("code_ouvrage")["volume_m3"].sum() / len(years)
    else:
        annual = pd.Series(dtype=float)
    annual = annual.reindex(codes, fill_value=0.0).clip(lower=0.0)

    out = pd.DataFrame(index=pd.Index(codes, name="code"))
    out["log_annual_declared_vol"] = np.log1p(annual)

    # Dominant declared usage category within the training window (all zeros if undeclared in train).
    if len(dec):
        use_cat = dec["usage"].where(dec["usage"].isin(USE_CATEGORIES[:-1]), "other")
        grouped = (
            dec.assign(use_cat=use_cat)
            .groupby(["code_ouvrage", "use_cat"], as_index=False)
            .agg(total_vol=("volume_m3", "sum"), n_rows=("volume_m3", "size"))
            .sort_values(["code_ouvrage", "total_vol", "n_rows", "use_cat"],
                         ascending=[True, False, False, True])
            .drop_duplicates("code_ouvrage")
            .set_index("code_ouvrage")["use_cat"]
        )
        dominant = pd.Series(codes, index=out.index).map(grouped)
    else:
        dominant = pd.Series(np.nan, index=out.index, dtype=object)

    for cat, col in zip(USE_CATEGORIES, USE_COLUMNS):
        out[col] = (dominant == cat).astype(float)

    sources = pumping_points.drop_duplicates("code_ouvrage").set_index("code_ouvrage")["source"]
    out["source_groundwater"] = pd.Series(codes, index=out.index).map(sources).eq("groundwater").astype(float)
    return _standardise_matrix(out[list(FACILITY_COLUMNS)])


def _weather_cell_features(codes, start, end, forcing_weekly):
    """Weather-cell training-window climatological means (precipitation, ETP, effective precip)."""
    weeks = pd.to_datetime(forcing_weekly["week"])
    sub = forcing_weekly.loc[weeks.between(start, end), ["cell_id", "rain", "ETP", "PE"]]
    agg = sub.groupby("cell_id")[["rain", "ETP", "PE"]].mean()
    agg = agg.rename(columns={
        "rain": WEATHER_COLUMNS[0],
        "ETP": WEATHER_COLUMNS[1],
        "PE": WEATHER_COLUMNS[2],
    }).reindex(codes)
    return _standardise_matrix(agg[list(WEATHER_COLUMNS)])


def _gauge_features(codes, start, end, rivers_weekly):
    """Gauge log1p of training-window mean weekly discharge."""
    weeks = pd.to_datetime(rivers_weekly["week"])
    sub = rivers_weekly.loc[weeks.between(start, end), ["code_station", "q_m3s"]]
    mean_q = sub.groupby("code_station")["q_m3s"].mean().reindex(codes).clip(lower=0.0)
    df = pd.DataFrame({GAUGE_COLUMNS[0]: np.log1p(mean_q)}, index=pd.Index(codes, name="code"))
    return _standardise_matrix(df)


def _canal_features(codes, start, end, pumping_weekly, pumping_points, canal_basins_weekly=None):
    """Canal log1p of training-window mean weekly volume (plain-wide in v4, per-basin in v5)."""
    weeks = pd.to_datetime(pumping_weekly["week"])
    pw_tr = pumping_weekly.loc[weeks.between(start, end)]
    plain_series = canal_series(pw_tr, pumping_points)
    plain_mean = float(plain_series.mean()) if len(plain_series) else 0.0

    basin_means = {}
    if canal_basins_weekly is not None and len(canal_basins_weekly):
        cb_weeks = pd.to_datetime(canal_basins_weekly["week"])
        cb_tr = canal_basins_weekly.loc[cb_weeks.between(start, end)]
        if len(cb_tr):
            basin_means = cb_tr.groupby("basin")["volume_m3"].mean().to_dict()

    vals = []
    for code in codes:
        suffix = code.split(":", 1)[-1]
        if code in basin_means:
            vol = float(basin_means[code])
        elif suffix in basin_means:
            vol = float(basin_means[suffix])
        elif code == "canal-intakes:plain" or not basin_means:
            vol = plain_mean
        else:
            vol = np.nan
        vals.append(np.log1p(max(vol, 0.0)) if np.isfinite(vol) else np.nan)

    df = pd.DataFrame({CANAL_COLUMNS[0]: vals}, index=pd.Index(codes, name="code"))
    return _standardise_matrix(df)


def _aquifer_unit_features(codes, unit_nodes):
    """Aquifer-unit one-hot of unit_type over the five ontology classes, standardised."""
    if "unit_type" in unit_nodes.columns:
        ut = unit_nodes.set_index("code")["unit_type"].reindex(codes)
    else:
        ut = pd.Series("unit", index=codes, dtype=object)
    ut = ut.fillna("unit").astype(str)
    bad = sorted(set(ut) - set(UNIT_TYPE_CATEGORIES))
    if bad:
        raise ValueError(f"Unknown aquifer_unit unit_type values: {bad}")
    out = pd.DataFrame(index=pd.Index(codes, name="code"))
    for cat, col in zip(UNIT_TYPE_CATEGORIES, UNIT_TYPE_COLUMNS):
        out[col] = ut.eq(cat).astype(float)
    return _standardise_matrix(out[list(UNIT_TYPE_COLUMNS)])


def _unknown_type_features(codes):
    """Fallback static feature for node types without dedicated features: constant 1.0."""
    Z = np.ones((len(codes), 1), dtype=np.float32)
    return Z, list(UNKNOWN_COLUMNS), {"mean": {UNKNOWN_COLUMNS[0]: 1.0}, "sd": {UNKNOWN_COLUMNS[0]: 0.0}}


def _encode_sign(series):
    """Map ontology response signs to numeric values (+1, -1, 0), preserving NaN for gaps."""
    if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
        return series.astype(float)
    mapped = series.map(SIGN_MAP)
    unmapped = series.notna() & mapped.isna()
    if unmapped.any():
        # Fall back to numeric coercion if numeric values were stored in an object column.
        numeric = pd.to_numeric(series.loc[unmapped], errors="coerce")
        bad = numeric.isna()
        if bad.any():
            sample = series.loc[unmapped].loc[bad].iloc[0]
            raise ValueError(f"Unknown edge sign value: {sample!r}")
        mapped = mapped.copy()
        mapped.loc[unmapped] = numeric
    return mapped.astype(float)


def _encode_bool_col(series):
    """Convert a boolean/nullable column to float (0.0/1.0), preserving NaN for gaps."""
    if pd.api.types.is_bool_dtype(series):
        return series.astype(float)
    return series.map({True: 1.0, False: 0.0, 1: 1.0, 0: 0.0}).astype(float)


def _build_edge_attributes(edges):
    """Build [weight, log1p(distance_m / 1000), sign, eligible, constrained] + missing flags.

    Any base column with gaps anywhere in ``edges`` has its missing entries filled with 0.0
    and receives an explicit ``<col>_missing`` indicator column so every edge type in the
    graph shares one consistent ``edge_attr`` schema.
    """
    n = len(edges)
    weight = (pd.to_numeric(edges["weight"], errors="coerce")
              if "weight" in edges.columns else pd.Series(np.nan, index=edges.index))
    dist_raw = (pd.to_numeric(edges["distance_m"], errors="coerce")
                if "distance_m" in edges.columns else pd.Series(np.nan, index=edges.index))
    log_dist = np.log1p(dist_raw.clip(lower=0.0) / 1000.0)
    sign = (_encode_sign(edges["sign"])
            if "sign" in edges.columns else pd.Series(np.nan, index=edges.index))
    eligible = (_encode_bool_col(edges["eligible"])
                if "eligible" in edges.columns else pd.Series(np.nan, index=edges.index))
    constrained = (_encode_bool_col(edges["constrained"])
                   if "constrained" in edges.columns else pd.Series(np.nan, index=edges.index))

    base_specs = [
        ("weight", "weight", weight),
        ("distance_m", "log1p_distance_km", log_dist),
        ("sign", "sign", sign),
        ("eligible", "eligible", eligible),
        ("constrained", "constrained", constrained),
    ]

    cols = []
    names = []
    missing_cols = []
    missing_names = []
    for raw_name, attr_name, series in base_specs:
        is_missing = series.isna()
        cols.append(series.fillna(0.0).to_numpy(dtype=np.float32))
        names.append(attr_name)
        if bool(is_missing.any()):
            missing_cols.append(is_missing.to_numpy(dtype=np.float32))
            missing_names.append(f"{raw_name}_missing")

    all_cols = cols + missing_cols
    all_names = names + missing_names
    if n == 0:
        return np.empty((0, len(all_names)), dtype=np.float32), all_names
    return np.column_stack(all_cols).astype(np.float32, copy=False), all_names


def _resolve_endpoint_types(edges, nodes, col, type_col):
    """Return a Series of node types for edge endpoints (using type_col if present, else nodes)."""
    if type_col in edges.columns and edges[type_col].notna().all():
        return edges[type_col].astype(str)

    code_types = {}
    ambiguous = set()
    for ntype, code in zip(nodes["type"].astype(str), nodes["code"]):
        if code in code_types and code_types[code] != ntype:
            ambiguous.add(code)
        else:
            code_types[code] = ntype

    resolved = []
    for i, code in enumerate(edges[col]):
        if type_col in edges.columns and pd.notna(edges[type_col].iloc[i]):
            resolved.append(str(edges[type_col].iloc[i]))
        elif code in ambiguous:
            raise ValueError(f"Node code {code!r} appears under multiple node types; provide {type_col!r}")
        elif code in code_types:
            resolved.append(code_types[code])
        else:
            raise KeyError(f"Edge endpoint {code!r} (column {col!r}) not found in nodes table")
    return pd.Series(resolved, index=edges.index, dtype=object)


def build_heterodata(export_dir, arm, tables=None, train_start=None, policy="main"):
    """Build a PyG ``HeteroData`` and per-type node index from a KG export.

    Parameters
    ----------
    export_dir : str or Path
        Directory containing ``nodes.parquet`` and ``edges_<arm>.parquet`` (and optionally
        ``edges_D.parquet`` for arm-B well facts).
    arm : str
        Arm name (e.g. ``"C"`` or ``"D"``), used to read ``edges_<arm>.parquet`` when
        ``tables`` does not supply ``"edges"``.
    tables : dict[str, pd.DataFrame], optional
        Optional table overrides (any subset of ``nodes``, ``edges``, ``static_edges``,
        ``wells``, ``pumping_weekly``, ``pumping_points``, ``forcing_weekly``,
        ``rivers_weekly``, ``canal_basins_weekly``). Caller tables are never modified.
    train_start : str, optional
        Optional R3 window start (passed to ``statics.training_window``). Defaults to the
        dataset's full training start (2005-01-01).
    policy : str, default ``"main"``
        Export policy name recorded on the graph and passed to ``statics.static_table``.

    Returns
    -------
    data : torch_geometric.data.HeteroData
        Heterogeneous graph with static training-window node features, forward export edge
        types, and explicit ``rev_<relation>`` reverse edge types.
    index : dict[str, dict[str, int]]
        Mapping ``node_type -> {node_code: row_index}`` in the row order of each node type.
    """
    export_path = Path(export_dir) if export_dir is not None else None
    start, end, _ = statics.training_window(train_start)

    nodes = _load_table(tables, "nodes", export_path / "nodes.parquet")
    edges = _load_table(tables, "edges", export_path / f"edges_{arm}.parquet")

    # Arm-B well static features always come from arm D's KG edges (CLAUDE.md §1a: C and D
    # share the same KG features and differ only in graph edges), unless explicitly overridden.
    if tables is not None and "static_edges" in tables:
        static_edges = tables["static_edges"]
    elif export_path is not None and (export_path / "edges_D.parquet").is_file():
        static_edges = pd.read_parquet(export_path / "edges_D.parquet")
    else:
        static_edges = edges

    # Build node index preserving nodes.parquet order within each type.
    index = {}
    for ntype, grp in nodes.groupby("type", sort=False):
        ntype_str = str(ntype)
        codes = grp["code"].tolist()
        if len(set(codes)) != len(codes):
            raise ValueError(f"Duplicate node codes found for node type {ntype_str!r}")
        index[ntype_str] = {code: i for i, code in enumerate(codes)}

    # Load only the weekly/metadata tables needed by node types present in this export.
    pumping_weekly = None
    pumping_points = None
    if any(t in index for t in ("well", "facility", "canal")):
        pumping_weekly = _load_table(tables, "pumping_weekly", DATASET_DIR / "pumping_weekly.parquet")
        pumping_points = _load_table(tables, "pumping_points", DATASET_DIR / "pumping_points.parquet")

    data = HeteroData()
    for ntype, code_map in index.items():
        codes = list(code_map.keys())
        if ntype == "well":
            Z, feat_names, _ = _well_features(
                codes, train_start, policy, tables, static_edges, pumping_weekly, pumping_points
            )
        elif ntype == "facility":
            Z, feat_names, _ = _facility_features(codes, start, end, pumping_weekly, pumping_points)
        elif ntype == "weather_cell":
            forcing_weekly = _load_table(tables, "forcing_weekly", DATASET_DIR / "forcing_weekly.parquet")
            Z, feat_names, _ = _weather_cell_features(codes, start, end, forcing_weekly)
        elif ntype == "gauge":
            rivers_weekly = _load_table(tables, "rivers_weekly", DATASET_DIR / "rivers_weekly.parquet")
            Z, feat_names, _ = _gauge_features(codes, start, end, rivers_weekly)
        elif ntype == "canal":
            cb_path = DATASET_DIR / "canal_basins_weekly.parquet"
            canal_basins = (
                tables["canal_basins_weekly"]
                if tables is not None and "canal_basins_weekly" in tables
                else (pd.read_parquet(cb_path) if cb_path.is_file() else None)
            )
            Z, feat_names, _ = _canal_features(codes, start, end, pumping_weekly, pumping_points, canal_basins)
        elif ntype == "aquifer_unit":
            unit_nodes = nodes.loc[nodes["type"].astype(str) == "aquifer_unit"]
            Z, feat_names, _ = _aquifer_unit_features(codes, unit_nodes)
        else:
            Z, feat_names, _ = _unknown_type_features(codes)

        data[ntype].x = torch.from_numpy(np.ascontiguousarray(Z, dtype=np.float32))
        data[ntype].feature_names = list(feat_names)
        data[ntype].node_codes = codes

    # Build edge attributes once across the whole edge table for a uniform edge_dim.
    all_edge_attr, edge_attr_names = _build_edge_attributes(edges)
    src_types = _resolve_endpoint_types(edges, nodes, "src", "src_type")
    dst_types = _resolve_endpoint_types(edges, nodes, "dst", "dst_type")

    work = pd.DataFrame({
        "src_type": src_types.to_numpy(),
        "relation": edges["relation"].astype(str).to_numpy(),
        "dst_type": dst_types.to_numpy(),
        "src": edges["src"].to_numpy(),
        "dst": edges["dst"].to_numpy(),
        "pos": np.arange(len(edges), dtype=np.int64),
    })

    forward_edge_types = []
    reverse_edge_types = []
    for (st, rel, dt), grp in work.groupby(["src_type", "relation", "dst_type"], sort=True):
        et = (str(st), str(rel), str(dt))
        rev_et = (str(dt), f"rev_{rel}", str(st))
        src_map = index[et[0]]
        dst_map = index[et[2]]
        src_idx = np.fromiter((src_map[c] for c in grp["src"]), dtype=np.int64, count=len(grp))
        dst_idx = np.fromiter((dst_map[c] for c in grp["dst"]), dtype=np.int64, count=len(grp))
        pos = grp["pos"].to_numpy()

        fwd_index = torch.from_numpy(np.vstack([src_idx, dst_idx]))
        fwd_attr = torch.from_numpy(np.ascontiguousarray(all_edge_attr[pos], dtype=np.float32))

        data[et].edge_index = fwd_index
        data[et].edge_attr = fwd_attr
        data[et].edge_attr_names = list(edge_attr_names)
        forward_edge_types.append(et)

        data[rev_et].edge_index = fwd_index.flip(0).contiguous()
        data[rev_et].edge_attr = fwd_attr.clone()
        data[rev_et].edge_attr_names = list(edge_attr_names)
        reverse_edge_types.append(rev_et)

    data.arm = str(arm)
    data.policy = str(policy)
    data.train_start = start.date().isoformat()
    data.train_end = end.date().isoformat()
    data.forward_edge_types = forward_edge_types
    data.reverse_edge_types = reverse_edge_types
    data.edge_attr_names = list(edge_attr_names)
    data.validate(raise_on_error=True)
    return data, index


def build_well_graph(export_dir, features, codes=None, tables=None, train_start=None, policy="main"):
    """Arms A and B of analysis plan v3 §5 ("facts, no graph"): a HeteroData holding only the wells,
    with fact set ``features`` ("A": the baseline facts; "B": the knowledge-graph facts, the same as
    every graph arm's wells), and no edge type at all. ``HeteroEncoder`` then reduces to a small network
    applied to each well's own facts (input projection, ELU, head): no message passing, so a well's
    parameters depend on its own facts only. Returns ``(data, index)`` like ``build_heterodata``;
    ``codes`` (default: the export's wells in node order) fixes the well order."""
    export_path = Path(export_dir) if export_dir is not None else None
    start, end, _ = statics.training_window(train_start)
    if codes is None:
        nodes = _load_table(tables, "nodes", export_path / "nodes.parquet")
        codes = nodes.loc[nodes["type"].astype(str) == "well", "code"].tolist()
    codes = list(codes)
    if len(set(codes)) != len(codes):
        raise ValueError("Duplicate well codes")
    static_edges = None
    pumping_weekly = pumping_points = None
    if features == "B":
        if tables is not None and "static_edges" in tables:
            static_edges = tables["static_edges"]
        else:
            static_edges = pd.read_parquet(export_path / "edges_D.parquet")
        pumping_weekly = _load_table(tables, "pumping_weekly", DATASET_DIR / "pumping_weekly.parquet")
        pumping_points = _load_table(tables, "pumping_points", DATASET_DIR / "pumping_points.parquet")
    Z, feat_names, _ = _well_features(codes, train_start, policy, tables, static_edges, pumping_weekly,
                                      pumping_points, features=features)
    data = HeteroData()
    data["well"].x = torch.from_numpy(np.ascontiguousarray(Z, dtype=np.float32))
    data["well"].feature_names = list(feat_names)
    data["well"].node_codes = codes
    data.arm = f"facts {features}, no graph"
    data.policy = str(policy)
    data.train_start = start.date().isoformat()
    data.train_end = end.date().isoformat()
    data.forward_edge_types = []
    data.reverse_edge_types = []
    data.edge_attr_names = []
    data.validate(raise_on_error=True)
    return data, {"well": {c: i for i, c in enumerate(codes)}}


class HeteroEncoder(nn.Module):
    """Static-only heterogeneous GATv2 encoder mapping graph facts to per-well raw parameters.

    Architecture (analysis plan v3 §3.5):
    - Per-node-type linear input projection to ``hidden`` (default 32).
    - ``n_layers`` (default 2) ``HeteroConv`` layers of ``GATv2Conv`` per edge type
      (``heads=2``, ``concat=False``, ``dropout=0.1``, ``add_self_loops=False``,
      ``edge_dim`` = edge attribute width), with residual skips and ELU between layers.
    - Linear output head from the well embeddings to ``n_out`` raw parameters, initialised at
      exact zero so an untrained encoder adds 0 to the aquifer-group parameter means.
    """

    def __init__(
        self,
        in_channels,
        edge_types,
        edge_dim,
        n_out,
        hidden=32,
        heads=2,
        dropout=0.1,
        n_layers=2,
        well_type="well",
    ):
        super().__init__()
        if well_type not in in_channels:
            raise ValueError(f"well_type {well_type!r} missing from in_channels {list(in_channels)}")
        if n_layers < 1:
            raise ValueError(f"n_layers must be >= 1, got {n_layers}")

        self.node_types = list(in_channels.keys())
        self.edge_types = [tuple(et) for et in edge_types]
        self.hidden = int(hidden)
        self.heads = int(heads)
        self.dropout = float(dropout)
        self.n_layers = int(n_layers)
        self.n_out = int(n_out)
        self.well_type = str(well_type)

        self.in_proj = nn.ModuleDict({
            nt: nn.Linear(int(dim), self.hidden)
            for nt, dim in in_channels.items()
        })

        self.convs = nn.ModuleList()
        for _ in range(self.n_layers):
            conv_map = {}
            for et in self.edge_types:
                edim = int(edge_dim[et]) if isinstance(edge_dim, dict) else int(edge_dim)
                conv_map[et] = GATv2Conv(
                    in_channels=(self.hidden, self.hidden),
                    out_channels=self.hidden,
                    heads=self.heads,
                    concat=False,
                    dropout=self.dropout,
                    add_self_loops=False,
                    edge_dim=edim,
                )
            self.convs.append(HeteroConv(conv_map, aggr="sum"))

        self.head = nn.Linear(self.hidden, self.n_out)
        nn.init.zeros_(self.head.weight)
        nn.init.zeros_(self.head.bias)

    @classmethod
    def from_heterodata(
        cls,
        data,
        n_out,
        hidden=32,
        heads=2,
        dropout=0.1,
        n_layers=2,
        well_type="well",
    ):
        """Construct a ``HeteroEncoder`` directly from a built ``HeteroData`` instance."""
        in_channels = {nt: int(data[nt].x.size(-1)) for nt in data.node_types}
        edge_types = list(data.edge_types)
        edge_dim = {et: int(data[et].edge_attr.size(-1)) for et in edge_types}
        return cls(
            in_channels=in_channels,
            edge_types=edge_types,
            edge_dim=edge_dim,
            n_out=n_out,
            hidden=hidden,
            heads=heads,
            dropout=dropout,
            n_layers=n_layers,
            well_type=well_type,
        )

    def forward(self, data):
        """Run static message passing and return ``(n_wells, n_out)`` in ``index['well']`` order."""
        # Only static node features x, edge_index and edge_attr are read (no weekly stresses).
        h = {nt: self.in_proj[nt](data[nt].x) for nt in self.node_types}
        edge_index_dict = {et: data[et].edge_index for et in self.edge_types}
        edge_attr_dict = {et: data[et].edge_attr for et in self.edge_types}

        for layer_idx, conv in enumerate(self.convs):
            out = conv(h, edge_index_dict, edge_attr_dict=edge_attr_dict)
            next_h = {}
            for nt in self.node_types:
                # Residual skip keeps every node's own static features when add_self_loops=False
                # (including isolated nodes and degree-1 nodes where softmax attention is constant 1),
                # while adding 0 hops so 2-layer locality stays exact.
                updated = h[nt] + out[nt] if nt in out else h[nt]
                if layer_idx < self.n_layers - 1:
                    updated = F.elu(updated)
                next_h[nt] = updated
            h = next_h

        return self.head(h[self.well_type])
