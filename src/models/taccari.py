"""Taccari-style spatio-temporal GNN (simulation task): the RQ1 graph baseline.

    python -m src.models.taccari                       # 5 seeds, default hyperparameters
    python -m src.models.tune --model taccari          # equal-budget tuning -> taccari_tuned
    python -m src.models.regimes --model taccari       # leave-wells-out, less data, refit

Taccari et al. 2024, Sci. Rep. 14, doi:10.1038/s41598-024-75385-2 (design checked in the
open-access version): every measurement is a node. Piezometers are the targets; rain/ET
stations, river points and pumping stations are exogenous nodes. A piezometer is linked to
its 3 nearest piezometers, the pumping stations, its nearest rain/ET station and its 2
nearest river points; the graph is predefined (it beat a learned graph) and the network is
MTGNN without graph learning: gated dilated temporal convolutions + mix-hop propagation.

Here (docs/feedback.md section 4.1; docs/analysis_plan.md section 10):
    node types   piezometers (65), SAFRAN cells nearest to a piezometer (weather), the main
                 river gauges (dataset v3), groundwater-abstraction fields (abstraction points
                 grouped in FIELD_KM Lambert-93 cells), one plain canal-intake node
    edges        default distance rules: 3 nearest piezometers, nearest SAFRAN cell, 2 nearest
                 gauges, abstraction fields within PUMP_KM (weight exp(-d / 5 km)), canal node
                 -> piezometers of the plain. Exogenous nodes only keep their own state.
    inputs       piezometers carry their static attributes + season; each exogenous node its
                 own weekly series (no observed head anywhere: simulation task)

With --edges D, the same network reads the Phase 4 arm D export for the comparison in
docs/gate3_decisions.md, point 21. Recharge edges bring in SAFRAN cells, river edges bring
in gauges, pumping edges bring in individual facilities, and canal edges share one canal
node. Well links connect the piezometers. Unattributed pumping is summed with export weights
into one node per receiving well. The hybrid reads the same source-unknown sum, and this
keeps the graph small enough for the comparison. Gauges use the declared gap rule shared
by the real-data Phase 4 runs (docs/analysis_plan.md section 7b).

    PFE_DATASET=v4 python -m src.models.taccari --edges D --run taccari_D --lookback 156 --hidden 64 --dropout 0.22864303352275453 --lr 0.0008210305468215977
"""
import json
from functools import partial

import geopandas as gpd
import numpy as np
import pandas as pd
import torch
import torch.nn.functional as Fn
from torch import nn

from src.config import CRS_L93, CRS_WGS84, RAW
from src.analysis.piezo_profile import PLAIN_BBOX
from src.dataset.pumping import canal_series, seasonal_drinking_water
from src.models import routing
from src.models.evaluate import DS, RESULTS
from src.models.features import RIVERS, NEAR_CANDIDATES, STATIC, WITH_RIVERS, river_series
from src.models.stgnn import parser, run_graph_model

RUN = "taccari"
FIELD_KM, PUMP_KM = 5.0, 10.0
WEATHER = ["rain", "ETP", "EVAP", "PE", "DRAINC", "RUNC", "T", "SWI"]
TYPES = ["piezometer", "weather", "river", "pumping", "canal"]
EXPORT_PREFIX = {"recharge": "cell", "river": "gauge", "pumping": "facility"}
EXPORT_RELATIONS = {*EXPORT_PREFIX, "pumping_unattributed", "canal", "well_link"}
# Relations of the v5 export this v4 baseline does not use: the regional and leakage recharge channels and
# the unit structure (monitors: unit -> well, overlies: unit -> unit), which only Hybrid-GNN v2 reads.
IGNORED_RELATIONS = {"recharge_unitwide", "recharge_leakage", "monitors", "overlies"}
_GRAPH = {}   # node codes -> adjacency, filled by prepare()


def _xy(lon, lat):
    g = gpd.GeoSeries(gpd.points_from_xy(lon, lat), crs=CRS_WGS84).to_crs(CRS_L93)
    return np.c_[g.x, g.y]


def _std(a, train_cols):
    m, s = np.nanmean(a[:, train_cols], axis=1, keepdims=True), np.nanstd(a[:, train_cols], axis=1,
                                                                          keepdims=True)
    return np.nan_to_num((a - m) / np.where(s > 0, s, 1.0))


def _check_sources(sources, available, kind):
    missing = sorted(set(sources) - set(available))
    if missing:
        raise ValueError(f"{kind} sources without a series: {', '.join(map(str, missing))}")


def weather_nodes(sources, weeks):
    """SAFRAN weather and long rolling means for the requested cells."""
    if not len(sources):
        return []
    f = pd.read_parquet(DS / "forcing_weekly.parquet")
    _check_sources(sources, f["cell_id"], "weather")
    cells = pd.read_parquet(RAW / "safran" / "grid_cells_66.parquet")
    cxy = dict(zip(cells["cell_id"], _xy(cells["lon"], cells["lat"])))
    nodes = []
    for cell in sources:
        g = f[f["cell_id"] == cell].set_index("week")[WEATHER].reindex(weeks)
        g["deficit"] = (g["ETP"] - g["rain"])
        feats = {v: g[v].to_numpy() for v in WEATHER}
        for v, k in (("rain", 52), ("rain", 104), ("DRAINC", 52), ("deficit", 52)):
            feats[f"{v}_m{k}"] = g[v].rolling(k, min_periods=k // 2).mean().to_numpy()
        nodes.append((f"cell:{cell}", "weather", *cxy.get(cell, (np.nan, np.nan)), feats))
    return nodes


def river_nodes(sources, weeks, train_cols, rule):
    if not len(sources):
        return []
    riv = river_series(pd.DatetimeIndex(weeks), str(weeks[train_cols][-1])[:10], rule=rule)
    _check_sources(sources, riv.columns[riv.notna().any()], "river")
    gauges = pd.read_parquet(DS / "gauges.parquet").set_index("code_station").reindex(sources)
    gxy = _xy(gauges["longitude_station"], gauges["latitude_station"])
    return [(f"gauge:{code}", "river", x, y, {"logq": riv[code].to_numpy()})
            for code, (x, y) in zip(sources, gxy)]


def pumping_features(volume):
    """Log of weekly volume in thousand cubic metres and its 52-week mean."""
    v = np.log1p(volume)
    return {"logvol": v, "logvol_m52": pd.Series(v).rolling(52, min_periods=1).mean().to_numpy()}


def canal_node(pw, pts, weeks):
    c = canal_series(pw, pts).reindex(weeks).fillna(0).to_numpy() / 1e6
    return ("canal:plain", "canal", np.nan, np.nan, {"canal": c})


def exogenous_nodes(P, codes, weeks, train_cols):
    """Series (nodes x T x features) and coordinates of the distance graph's exogenous nodes."""
    wells = pd.read_parquet(DS / "wells.parquet").set_index("code_bss").loc[codes]
    nodes = weather_nodes(sorted(wells["cell_id"].unique()), weeks)
    # rivers (dataset v3 on)
    if WITH_RIVERS:
        nodes += river_nodes(sorted(set(NEAR_CANDIDATES) | set(RIVERS.values())), weeks, train_cols,
                             rule="legacy")  # the distance runs of record use the old gap rule
    # groundwater-abstraction fields (seasonal drinking-water profile, as the baselines)
    pw = pd.read_parquet(DS / "pumping_weekly.parquet")
    pts = pd.read_parquet(DS / "pumping_points.parquet")
    gpts = pts[pts["source"] == "groundwater"].copy()
    gxy = _xy(gpts["longitude"], gpts["latitude"])
    k = FIELD_KM * 1000
    gpts["field"] = [f"field:{int(x // k)}_{int(y // k)}" for x, y in gxy]
    gpts["fx"], gpts["fy"] = gxy[:, 0], gxy[:, 1]
    sp = seasonal_drinking_water(pw, pts).merge(gpts[["code_ouvrage", "field"]], on="code_ouvrage")
    vol = sp.groupby(["field", "week"])["volume_m3"].sum().unstack("field").reindex(weeks).fillna(0)
    centre = gpts.groupby("field")[["fx", "fy"]].mean()
    wxy = _xy(wells["x"], wells["y"])
    dmin = np.hypot(centre["fx"].to_numpy()[:, None] - wxy[:, 0][None],
                    centre["fy"].to_numpy()[:, None] - wxy[:, 1][None]).min(axis=1)
    centre = centre[dmin <= PUMP_KM * 1000]   # fields that reach at least one piezometer
    for fld in [c for c in vol.columns if c in centre.index]:
        nodes.append((fld, "pumping", centre.loc[fld, "fx"], centre.loc[fld, "fy"],
                      pumping_features(vol[fld].to_numpy() / 1e3)))
    # canal intakes of the plain (one node)
    nodes.append(canal_node(pw, pts, weeks))
    return nodes


def select_export_edges(edges, codes):
    """Validate the export and keep links that reach the run's piezometers."""
    relations = set(edges["relation"])
    unknown = relations - EXPORT_RELATIONS - IGNORED_RELATIONS
    if unknown:
        raise ValueError(f"unknown arm D relations: {', '.join(sorted(map(str, unknown)))}")
    key = ["relation", "src", "dst"]
    duplicate = edges.duplicated(key)
    if duplicate.any():
        raise ValueError(f"duplicated arm D edge (relation, src, dst): "
                         f"{tuple(edges.loc[duplicate, key].iloc[0])}")
    ignored = ", ".join(sorted(relations & IGNORED_RELATIONS))
    print(f"Arm D ignored relations: {ignored or '(none)'}", flush=True)
    in_graph = edges["dst"].isin(codes) & (
        (edges["relation"] != "well_link") | edges["src"].isin(codes))
    return edges.loc[in_graph & edges["relation"].isin(EXPORT_RELATIONS)]


def export_nodes(edges, codes, weeks, train_cols):
    """Build exogenous series from the selected arm D edges."""
    by_relation = edges.groupby("relation")["src"].agg(set)
    nodes = weather_nodes(sorted(by_relation.get("recharge", ())), weeks)
    nodes += river_nodes(sorted(by_relation.get("river", ())), weeks, train_cols, rule="declared")
    pumps = sorted(by_relation.get("pumping", ()))
    un = edges[edges["relation"] == "pumping_unattributed"]
    facilities = sorted(set(pumps) | set(un["src"]))
    has_canal = "canal" in by_relation
    if facilities or has_canal:
        pw = pd.read_parquet(DS / "pumping_weekly.parquet")
        pts = pd.read_parquet(DS / "pumping_points.parquet")
    if facilities:
        # facility_volumes fills requested columns even when the seasonal merge had no source.
        available = set(pw["code_ouvrage"]) & set(pts["code_ouvrage"])
        _check_sources(facilities, available, "pumping")
        volumes = routing.facility_volumes(weeks, facilities, reconstruction=1)
        _check_sources(facilities, volumes.columns, "pumping")
        coords = pts.set_index("code_ouvrage").reindex(pumps)
        pxy = _xy(coords["longitude"], coords["latitude"])
        for code, (x, y) in zip(pumps, pxy):
            nodes.append((f"facility:{code}", "pumping", x, y,
                          pumping_features(volumes[code].to_numpy())))
        targets = sorted(un["dst"].unique())
        # The hybrid uses this same weighted sum as its source-unknown pumping input.
        weights = routing._matrix(un, "pumping_unattributed", targets, facilities)
        for code, volume in zip(targets, weights @ volumes[facilities].to_numpy().T):
            nodes.append((f"unattributed:{code}", "pumping", np.nan, np.nan,
                          pumping_features(volume)))
    if has_canal:
        nodes.append(canal_node(pw, pts, weeks))
    return nodes


def export_adjacency(codes, nodes, edges):
    """Identity plus arm D's directed weights, before row normalisation."""
    A = np.eye(len(codes) + len(nodes))
    row = {code: i for i, code in enumerate(codes)}
    col = row | {name: i for i, (name, *_) in enumerate(nodes, start=len(codes))}
    for edge in edges.itertuples(index=False):
        relation = edge.relation
        weight = edge.weight
        if relation == "well_link":
            source = edge.src
        elif relation == "pumping_unattributed":
            source = f"unattributed:{edge.dst}"
            weight = 1.0
        elif relation == "canal":
            source = "canal:plain"
        else:
            source = f"{EXPORT_PREFIX[relation]}:{edge.src}"
        A[row[edge.dst], col[source]] = weight
    return A


def normalise_adjacency(A):
    return torch.tensor(A / A.sum(1, keepdims=True), dtype=torch.float32)


def adjacency(codes, wells_xy, plain, nodes):
    """Distance-rule edges, self-loops, rows normalised to 1 (mean aggregation)."""
    nw, n = len(codes), len(codes) + len(nodes)
    A = np.eye(n)
    d = np.hypot(*(wells_xy[:, None] - wells_xy[None]).transpose(2, 0, 1))
    sigma = np.median(np.sort(d, axis=1)[:, 1:4])
    for i in range(nw):
        for j in np.argsort(d[i])[1:4]:
            w = np.exp(-d[i, j] / sigma)
            A[i, j] = A[j, i] = max(A[i, j], w)
    typ = np.array([t for _, t, *_ in nodes])
    nxy = np.array([[x, y] for _, _, x, y, _ in nodes], dtype=float)
    for t, rule in (("weather", "nearest1"), ("river", "nearest2"), ("pumping", "radius")):
        idx = np.where(typ == t)[0]
        if not len(idx):
            continue
        dd = np.hypot(*(wells_xy[:, None] - nxy[idx][None]).transpose(2, 0, 1))
        for i in range(nw):
            if rule == "nearest1":
                A[i, nw + idx[dd[i].argmin()]] = 1.0
            elif rule == "nearest2":
                for j in np.argsort(dd[i])[:2]:
                    A[i, nw + idx[j]] = np.exp(-dd[i, j] / np.median(dd))
            else:
                for j in np.where(dd[i] <= PUMP_KM * 1000)[0]:
                    A[i, nw + idx[j]] = np.exp(-dd[i, j] / 5000.0)
    for j in np.where(typ == "canal")[0]:
        A[np.where(plain)[0], nw + j] = 1.0
    return normalise_adjacency(A)


def prepare(P, data, edges=None):
    """Per-well arrays -> node arrays (piezometers first, then exogenous nodes)."""
    codes, weeks, X, Z, split, core, mu, sd, head = data
    T = len(weeks)
    train_cols = np.where(split[0] == "train")[0]
    if edges is None:
        nodes = exogenous_nodes(P, codes, weeks, train_cols)
        wells = pd.read_parquet(DS / "wells.parquet").set_index("code_bss").loc[codes]
        wxy = _xy(wells["x"], wells["y"])
        lon0, lat0, lon1, lat1 = PLAIN_BBOX
        plain = (wells["x"].between(lon0, lon1) & wells["y"].between(lat0, lat1)).to_numpy()
        A = adjacency(codes, wxy, plain, nodes)
    else:
        edges = select_export_edges(edges, codes)
        nodes = export_nodes(edges, codes, weeks, train_cols)
        A = normalise_adjacency(export_adjacency(codes, nodes, edges))
    feat_names = sorted({k for *_, f in nodes for k in f})
    n_static = len(STATIC)
    # piezometer slots: statics (already standardised, last columns of X) + season
    from src.models.lstm import input_cols
    cols = input_cols(P)
    season = [cols.index("season_sin"), cols.index("season_cos")]
    F = n_static + 2 + len(feat_names) + len(TYPES)
    nw = len(codes)
    Xn = np.zeros((nw + len(nodes), T, F), dtype=np.float32)
    Xn[:nw, :, :n_static] = X[:, :, -n_static:]
    Xn[:nw, :, n_static:n_static + 2] = X[:, :, season]
    Xn[:nw, :, -len(TYPES)] = 1.0
    for j, (_, t, _, _, feats) in enumerate(nodes):
        for name, v in feats.items():
            a = _std(np.asarray(v, dtype=float)[None], train_cols)[0]
            Xn[nw + j, :, n_static + 2 + feat_names.index(name)] = a
        Xn[nw + j, :, -len(TYPES) + TYPES.index(t)] = 1.0
    all_codes = list(codes) + [name for name, *_ in nodes]
    _GRAPH[tuple(all_codes)] = A

    def pad(a, fill):
        return np.concatenate([a, np.full((len(nodes),) + a.shape[1:], fill, dtype=a.dtype)])
    split_n = np.concatenate([split, np.repeat(split[:1], len(nodes), axis=0)])
    return (all_codes, weeks, Xn, pad(Z, np.nan), split_n, pad(core, False), pad(mu, np.nan),
            pad(sd, np.nan), pad(head, np.nan))


class GatedTCN(nn.Module):
    """Gated causal convolution of dilation d = 2^k, evaluated only where it is needed.

    The network reads the last week only, and the dilations double from layer to layer, so
    layer k is read at every second position of its input grid (step d), counted back from
    the last week, and each of those outputs uses 3 consecutive grid positions. forward()
    therefore takes the input on its grid and runs the same kernel with stride 2 and no
    dilation: the final output equals the full causal dilated stack (zeros before the window
    start, as before) at about 1/6 of the cost (tests/test_taccari.py checks the equality;
    the mix-hop, norm and residual are position-wise). Memory: with the defaults (6 layers,
    kernel 3, dilations 1..32) the receptive field is 1 + 2 * 63 = 127 weeks, so a 156-week
    lookback gives 127 weeks of raw input to the output (plus the rolling-mean features);
    describe it as such, not as 156 weeks (third review §4)."""

    def __init__(self, c, kernel, dilation):
        super().__init__()
        self.f = nn.Conv1d(c, c, kernel, dilation=dilation)   # weights used with stride 2
        self.g = nn.Conv1d(c, c, kernel, dilation=dilation)

    def forward(self, h):                        # (B, N, L, C) -> (B, N, ceil(L / 2), C)
        B, N, L, C = h.shape
        k = self.f.kernel_size[0]
        pad = k - 1 if L % 2 else k - 2           # aligns the last output with the last week
        x = Fn.pad(h.reshape(B * N, L, C).transpose(1, 2), (pad, 0))
        y = (torch.tanh(Fn.conv1d(x, self.f.weight, self.f.bias, stride=2))
             * torch.sigmoid(Fn.conv1d(x, self.g.weight, self.g.bias, stride=2)))
        return y.transpose(1, 2).reshape(B, N, -1, C)


class MixHop(nn.Module):
    """MTGNN mix-hop propagation: H_k = beta H + (1 - beta) A H_(k-1), summed after a
    linear map per hop."""

    def __init__(self, c, depth=2, beta=0.05):
        super().__init__()
        self.beta = beta
        self.lin = nn.ModuleList([nn.Linear(c, c) for _ in range(depth + 1)])

    def forward(self, h, A):
        out, hk = self.lin[0](h), h
        for lin in self.lin[1:]:
            hk = self.beta * h + (1 - self.beta) * torch.einsum("nm,bmlc->bnlc", A, hk)
            out = out + lin(hk)
        return out


class TaccariNet(nn.Module):
    def __init__(self, n_in, A, hidden=32, dropout=0.3, layers=6, kernel=3, depth=2, beta=0.05):
        super().__init__()
        self.register_buffer("A", A)
        self.inp = nn.Linear(n_in, hidden)
        self.tcn = nn.ModuleList([GatedTCN(hidden, kernel, 2 ** k) for k in range(layers)])
        self.mix = nn.ModuleList([MixHop(hidden, depth, beta) for _ in range(layers)])
        self.norm = nn.ModuleList([nn.LayerNorm(hidden) for _ in range(layers)])
        self.drop = nn.Dropout(dropout)
        self.out = nn.Sequential(nn.ReLU(), nn.Linear(hidden, hidden), nn.ReLU(),
                                 nn.Linear(hidden, 1))

    def forward(self, x):                        # (B, N, L, F) -> (B, N)
        h = self.inp(x)
        for tcn, mix, norm in zip(self.tcn, self.mix, self.norm):
            # residual taken at the positions the strided TCN returns (every second, from
            # the last week back)
            h = norm(self.drop(mix(tcn(h), self.A)) + h[:, :, (h.shape[2] - 1) % 2::2])
        return self.out(h[:, :, -1]).squeeze(-1)


def build(codes, wells, n_in, args):
    A = _GRAPH[tuple(codes)]
    return lambda F: TaccariNet(F, A, hidden=args.hidden, dropout=args.dropout)


def main():
    ap = parser(None)
    ap.add_argument("--edges", choices=("distance", "D"), default="distance")
    args = ap.parse_args()
    if args.run is None:
        args.run = f"{RUN}_D" if args.edges == "D" else RUN
    prepare_graph = prepare
    if args.edges == "D":
        # A run folder made by a distance run must never hand its seeds to arm D: a folder from
        # before 2026-10-25 has no fingerprint, and write_config then compares only the settings
        # both versions record, which do not include the edges (lead's review of T17).
        made = [f for f in (RESULTS / args.run).glob("**/config.json")
                if json.loads(f.read_text()).get("edges") != "D"]
        if made:
            raise SystemExit(f"{made[0]} was not made with --edges D; use another --run "
                             f"(default {RUN}_D)")
        edges, meta = routing.load_arm("D")
        args.release = meta["release"]
        args.policy = meta["policy"]
        args.code_version = meta["code_version"]
        prepare_graph = partial(prepare, edges=edges)
    else:
        del args.edges  # keep the distance-run fingerprint used by existing seed caches
    run_graph_model(args, build, prepare_graph)


if __name__ == "__main__":
    main()
