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
    edges        DISTANCE RULES ONLY: 3 nearest piezometers, nearest SAFRAN cell, 2 nearest
                 gauges, abstraction fields within PUMP_KM (weight exp(-d / 5 km)), canal node
                 -> piezometers of the plain. Exogenous nodes only keep their own state.
    inputs       piezometers carry their static attributes + season; each exogenous node its
                 own weekly series (no observed head anywhere: simulation task)
The knowledge-graph model of Phase 4 uses the same node types and network with edges
generated from the knowledge graph, so the comparison isolates the edge semantics (RQ1).
"""
import argparse

import geopandas as gpd
import numpy as np
import pandas as pd
import torch
import torch.nn.functional as Fn
from torch import nn

from src.config import CRS_L93, CRS_WGS84, RAW
from src.analysis.piezo_profile import PLAIN_BBOX
from src.dataset.pumping import canal_series, seasonal_drinking_water
from src.models.evaluate import DS
from src.models.features import RIVERS, NEAR_CANDIDATES, STATIC, WITH_RIVERS, river_series
from src.models.stgnn import parser, run_graph_model

RUN = "taccari"
FIELD_KM, PUMP_KM = 5.0, 10.0
WEATHER = ["rain", "ETP", "EVAP", "PE", "DRAINC", "RUNC", "T", "SWI"]
TYPES = ["piezometer", "weather", "river", "pumping", "canal"]
_GRAPH = {}   # node codes -> adjacency, filled by prepare()


def _xy(lon, lat):
    g = gpd.GeoSeries(gpd.points_from_xy(lon, lat), crs=CRS_WGS84).to_crs(CRS_L93)
    return np.c_[g.x, g.y]


def _std(a, train_cols):
    m, s = np.nanmean(a[:, train_cols], axis=1, keepdims=True), np.nanstd(a[:, train_cols], axis=1,
                                                                          keepdims=True)
    return np.nan_to_num((a - m) / np.where(s > 0, s, 1.0))


def exogenous_nodes(P, codes, weeks, train_cols):
    """Series (nodes x T x features) and coordinates of the exogenous nodes."""
    wells = pd.read_parquet(DS / "wells.parquet").set_index("code_bss").loc[codes]
    nodes = []          # (name, type, x, y, feature dict of arrays (T,))
    # weather: SAFRAN cells nearest to a piezometer, with long rolling means (memory)
    f = pd.read_parquet(DS / "forcing_weekly.parquet")
    cells = pd.read_parquet(RAW / "safran" / "grid_cells_66.parquet")
    cxy = dict(zip(cells["cell_id"], _xy(cells["lon"], cells["lat"])))
    for cell in sorted(wells["cell_id"].unique()):
        g = f[f["cell_id"] == cell].set_index("week")[WEATHER].reindex(weeks)
        g["deficit"] = (g["ETP"] - g["rain"])
        feats = {v: g[v].to_numpy() for v in WEATHER}
        for v, k in (("rain", 52), ("rain", 104), ("DRAINC", 52), ("deficit", 52)):
            feats[f"{v}_m{k}"] = g[v].rolling(k, min_periods=k // 2).mean().to_numpy()
        nodes.append((f"cell:{cell}", "weather", *cxy[cell], feats))
    # rivers (dataset v3 on)
    if WITH_RIVERS:
        riv = river_series(pd.DatetimeIndex(weeks), str(weeks[train_cols][-1])[:10])
        gauges = pd.read_parquet(DS / "gauges.parquet").set_index("code_station")
        for code in sorted(set(NEAR_CANDIDATES) | set(RIVERS.values())):
            x, y = _xy([gauges.loc[code, "longitude_station"]], [gauges.loc[code, "latitude_station"]])[0]
            nodes.append((f"gauge:{code}", "river", x, y, {"logq": riv[code].to_numpy()}))
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
        v = np.log1p(vol[fld].to_numpy() / 1e3)
        nodes.append((fld, "pumping", centre.loc[fld, "fx"], centre.loc[fld, "fy"],
                      {"logvol": v, "logvol_m52": pd.Series(v).rolling(52, min_periods=1).mean()
                       .to_numpy()}))
    # canal intakes of the plain (one node)
    c = canal_series(pw, pts).reindex(weeks).fillna(0).to_numpy() / 1e6
    nodes.append(("canal:plain", "canal", np.nan, np.nan, {"canal": c}))
    return nodes


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
    A = A / A.sum(1, keepdims=True)
    return torch.tensor(A, dtype=torch.float32)


def prepare(P, data):
    """Per-well arrays -> node arrays (piezometers first, then exogenous nodes)."""
    codes, weeks, X, Z, split, core, mu, sd, head = data
    T = len(weeks)
    train_cols = np.where(split[0] == "train")[0]
    nodes = exogenous_nodes(P, codes, weeks, train_cols)
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
    wells = pd.read_parquet(DS / "wells.parquet").set_index("code_bss").loc[codes]
    wxy = _xy(wells["x"], wells["y"])
    lon0, lat0, lon1, lat1 = PLAIN_BBOX
    plain = (wells["x"].between(lon0, lon1) & wells["y"].between(lat0, lat1)).to_numpy()
    all_codes = list(codes) + [name for name, *_ in nodes]
    _GRAPH[tuple(all_codes)] = adjacency(codes, wxy, plain, nodes)

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
    the mix-hop, norm and residual are position-wise)."""

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
    args = parser(RUN).parse_args()
    run_graph_model(args, build, prepare)


if __name__ == "__main__":
    main()
