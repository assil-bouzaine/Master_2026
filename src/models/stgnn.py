"""Distance-graph spatio-temporal GNN baseline (simulation task).

    python -m src.models.stgnn               # 5 seeds, resumable per seed

The "graph without knowledge" that the ontology-derived graph must beat.
Design after Taccari et al. 2024 (doi:10.1038/s41598-024-75385-2): a
predefined graph built from geometry only. Here every well is a node linked
to its K nearest wells, weight exp(-d / median distance); symmetric
normalised adjacency with self-loops (Kipf & Welling GCN propagation).

Per node, a shared GRU reads the last LOOKBACK weeks of weather, pumping and
season (+ static attributes); two graph-convolution layers mix the node
embeddings; a linear head outputs the z-scored head at the target week. No
observed head is an input (simulation task). Loss: masked MSE on observed
training heads, wells weighted equally; early stopping on the median
validation NSE over core wells. Mean over seeds is reported.
"""
import argparse
import time

import geopandas as gpd
import numpy as np
import pandas as pd
import torch
from torch import nn

from src.config import CRS_L93, CRS_WGS84
from src.models.evaluate import DS, RESULTS, evaluate_run
from src.models.features import build_panel
from src.models.lstm import DEVICE, LOOKBACK, arrays, median_nse

RUN = "stgnn_distance"
K = 3


def distance_adjacency(codes, wells):
    w = wells.set_index("code_bss").loc[codes]
    g = gpd.GeoSeries(gpd.points_from_xy(w["x"], w["y"]), crs=CRS_WGS84).to_crs(CRS_L93)
    xy = np.c_[g.x, g.y]
    d = np.sqrt(((xy[:, None] - xy[None]) ** 2).sum(-1))
    A = np.zeros_like(d)
    for i in range(len(codes)):
        nn_idx = np.argsort(d[i])[1:K + 1]
        A[i, nn_idx] = 1.0
    A = np.maximum(A, A.T)
    sigma = np.median(d[A > 0])
    A = A * np.exp(-d / sigma)
    A = A + np.eye(len(codes))
    dinv = 1.0 / np.sqrt(A.sum(1))
    return torch.tensor(dinv[:, None] * A * dinv[None], dtype=torch.float32)


class Net(nn.Module):
    def __init__(self, n_in, A, hidden=64, dropout=0.2):
        super().__init__()
        self.register_buffer("A", A)  # moves with .to(DEVICE)
        self.gru = nn.GRU(n_in, hidden, batch_first=True)
        self.g1, self.g2 = nn.Linear(hidden, hidden), nn.Linear(hidden, hidden)
        self.out = nn.Sequential(nn.Dropout(dropout), nn.Linear(2 * hidden, 1))

    def forward(self, x):                       # x: (B, N, L, F)
        B, N, L, F = x.shape
        _, h = self.gru(x.reshape(B * N, L, F))
        h = h[-1].reshape(B, N, -1)              # (B, N, H)
        m = torch.relu(self.g1(self.A @ h))
        m = torch.relu(self.g2(self.A @ m))
        return self.out(torch.cat([h, m], -1)).squeeze(-1)   # (B, N)


def batch_x(X, ts):
    return torch.from_numpy(np.stack([X[:, t - LOOKBACK + 1:t + 1] for t in ts])).to(DEVICE)


def predict_all(net, X, batch=8, ts=None):
    """Predict all weeks (or only the weeks `ts`, e.g. validation during training)."""
    N, T, _ = X.shape
    out = np.full((N, T), np.nan, dtype=np.float32)
    ts = list(range(LOOKBACK - 1, T)) if ts is None else list(ts)
    net.eval()
    with torch.no_grad():
        for k in range(0, len(ts), batch):
            b = ts[k:k + batch]
            out[:, b] = net(batch_x(X, b)).cpu().numpy().T
    return out


def train_seed(seed, A, X, Z, split, core, mu, sd, head, epochs, patience=8):
    torch.manual_seed(seed)
    np.random.seed(seed)
    torch.set_num_threads(4)
    N, T, F = X.shape
    train_t = [t for t in range(LOOKBACK - 1, T) if (split[:, t] == "train").any()
               and np.isfinite(Z[:, t][split[:, t] == "train"]).any()]
    obs = np.isfinite(Z) & (split == "train")
    wgt = 1.0 / np.maximum(obs.sum(1, keepdims=True), 1)          # equal weight per well
    net = Net(F, A).to(DEVICE)
    opt = torch.optim.Adam(net.parameters(), lr=1e-3, weight_decay=1e-5)
    val_t = [t for t in range(LOOKBACK - 1, T) if (split[:, t] == "validation").any()]
    best, best_state, bad = -np.inf, None, 0
    for ep in range(epochs):
        net.train()
        t0 = time.time()
        perm = np.random.permutation(train_t)
        for k in range(0, len(perm), 8):
            b = perm[k:k + 8]
            yhat = net(batch_x(X, b))
            y = torch.from_numpy(np.nan_to_num(Z[:, b].T)).to(DEVICE)
            m = torch.from_numpy((obs[:, b] * wgt).T.astype(np.float32)).to(DEVICE)
            loss = (m * (yhat - y) ** 2).sum() / m.sum()
            opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            opt.step()
        pz = predict_all(net, X, ts=val_t)
        score = median_nse(pz, Z, split, core, mu, sd, head)
        print(f"    seed {seed} epoch {ep + 1:3d} val median NSE {score:.3f} "
              f"({time.time() - t0:.0f}s)", flush=True)
        if score > best:
            best, best_state, bad = score, {k: v.clone() for k, v in net.state_dict().items()}, 0
        else:
            bad += 1
            if bad >= patience:
                break
    net.load_state_dict(best_state)
    return predict_all(net, X), best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="*", default=[0, 1, 2, 3, 4])
    ap.add_argument("--epochs", type=int, default=60)
    args = ap.parse_args()
    P = build_panel()
    P = P[P["mu"].notna()]
    codes, weeks, X, Z, split, core, mu, sd, head = arrays(P)
    wells = pd.read_parquet(DS / "wells.parquet")
    A = distance_adjacency(codes, wells)
    out = RESULTS / RUN
    out.mkdir(parents=True, exist_ok=True)
    for s in args.seeds:
        path = out / f"seed_{s}.parquet"
        if path.exists():
            print(f"seed {s}: cached")
            continue
        pz, best = train_seed(s, A, X, Z, split, core, mu, sd, head, args.epochs)
        df = pd.DataFrame(pz, index=codes, columns=pd.DatetimeIndex(weeks)).stack(future_stack=True)
        df.rename("z").rename_axis(["code_bss", "week"]).reset_index().to_parquet(path, index=False)
        print(f"seed {s}: best validation median NSE {best:.3f}", flush=True)
    seeds = [pd.read_parquet(f) for f in sorted(out.glob("seed_*.parquet"))]
    zz = pd.concat(seeds).groupby(["code_bss", "week"])["z"].agg(["mean", "std"]).reset_index()
    zz = zz.merge(P[["code_bss", "week", "mu", "sd"]], on=["code_bss", "week"])
    pred = pd.DataFrame({"code_bss": zz["code_bss"], "week": zz["week"],
                         "pred": zz["mu"] + zz["sd"] * zz["mean"],
                         "pred_seed_sd": zz["sd"] * zz["std"], "task": "simulation",
                         "horizon": 0}).dropna(subset=["pred"])
    pred.to_parquet(out / "predictions.parquet", index=False)
    s = evaluate_run(RUN)
    c = s[(s["group"] == "all core") & (s["variant"] == "all")]
    print(f"== {RUN} ({len(seeds)} seeds)")
    print(c[["split", "n_wells", "NSE", "KGE", "RMSE"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
