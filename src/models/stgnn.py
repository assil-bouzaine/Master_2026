"""Distance-graph spatio-temporal GNN baseline (simulation task).

    python -m src.models.stgnn                          # 5 seeds, resumable per seed
    python -m src.models.stgnn --run stgnn_tuned --hidden 128 --lr 0.002 ...
    # regimes (docs/analysis_plan.md section 4), usually driven by src.models.regimes:
    python -m src.models.stgnn --run stgnn_tuned_lwo --fold 1 ...
    python -m src.models.stgnn --run stgnn_tuned_f50 --train-start 2012-07-01 ...
    python -m src.models.stgnn --run stgnn_tuned_refit --refit-from stgnn_tuned ...

The "graph without knowledge": every well is a node linked to its K nearest wells, weight
exp(-d / median distance); symmetric normalised adjacency with self-loops (Kipf & Welling
GCN propagation). This is a wells-only graph. The Taccari et al. (2024,
doi:10.1038/s41598-024-75385-2) design, with rain, river and pumping nodes, is
src.models.taccari.

Per node, a shared GRU reads the last LOOKBACK weeks of weather, pumping, rivers (v3) and
season (+ static attributes); two graph-convolution layers mix the node embeddings; a
linear head outputs the z-scored head at the target week. No observed head is an input
(simulation task). Loss: masked MSE on observed training heads, wells weighted equally;
early stopping on the median validation NSE over core wells. Mean over seeds is reported.
Leave-wells-out: the wells of the fold stay in the graph (their weather and pumping are
known) but leave the loss and the early stopping.
"""
import argparse
import json
import os
import time

import geopandas as gpd
import numpy as np
import pandas as pd
import torch
from torch import nn

from src.config import CRS_L93, CRS_WGS84
from src.models.evaluate import DS, RESULTS, evaluate_run
from src.models.features import build_panel
from src.models.lstm import (DEVICE, arrays, input_cols, median_nse, refit_epochs,
                             regime_masks, save_seed, seed_mean_predictions)

RUN = "stgnn_distance"
K = 3
LOOKBACK = 104


def distance_adjacency(codes, wells, k=K):
    w = wells.set_index("code_bss").loc[codes]
    g = gpd.GeoSeries(gpd.points_from_xy(w["x"], w["y"]), crs=CRS_WGS84).to_crs(CRS_L93)
    xy = np.c_[g.x, g.y]
    d = np.sqrt(((xy[:, None] - xy[None]) ** 2).sum(-1))
    A = np.zeros_like(d)
    for i in range(len(codes)):
        nn_idx = np.argsort(d[i])[1:k + 1]
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


def batch_x(X, ts, lookback):
    return torch.from_numpy(np.stack([X[:, t - lookback + 1:t + 1] for t in ts])).to(DEVICE)


def predict_all(net, X, lookback, batch=8, ts=None):
    """Predict all weeks (or only the weeks `ts`, e.g. validation during training)."""
    N, T, _ = X.shape
    out = np.full((N, T), np.nan, dtype=np.float32)
    ts = list(range(lookback - 1, T)) if ts is None else list(ts)
    net.eval()
    with torch.no_grad():
        for k in range(0, len(ts), batch):
            b = ts[k:k + batch]
            out[:, b] = net(batch_x(X, b, lookback)).cpu().numpy().T
    return out


def train_seed(seed, A, X, Z, split, core, mu, sd, head, epochs, patience=8, hidden=64,
               dropout=0.2, lr=1e-3, lookback=LOOKBACK, train_mask=None, es_wells=None,
               fixed_epochs=None, make_net=None):
    """Shared training loop for graph models (also used by src.models.taccari through
    make_net, which builds the network from the number of inputs)."""
    torch.manual_seed(seed)
    np.random.seed(seed)
    torch.set_num_threads(int(os.environ.get("PFE_THREADS", 4)))
    N, T, F = X.shape
    if train_mask is None:
        train_mask = split == "train"
    es_core = core & (es_wells[:, None] if es_wells is not None else True)
    obs = np.isfinite(Z) & train_mask
    train_t = [t for t in range(lookback - 1, T) if obs[:, t].any()]
    wgt = 1.0 / np.maximum(obs.sum(1, keepdims=True), 1)          # equal weight per well
    net = (make_net(F) if make_net else Net(F, A, hidden, dropout)).to(DEVICE)
    opt = torch.optim.Adam(net.parameters(), lr=lr, weight_decay=1e-5)
    val_t = [t for t in range(lookback - 1, T) if (split[:, t] == "validation").any()]
    best, best_state, bad, best_ep = -np.inf, None, 0, 0
    n_ep = fixed_epochs or epochs
    for ep in range(n_ep):
        net.train()
        t0 = time.time()
        perm = np.random.permutation(train_t)
        for k in range(0, len(perm), 8):
            b = perm[k:k + 8]
            yhat = net(batch_x(X, b, lookback))
            y = torch.from_numpy(np.nan_to_num(Z[:, b].T)).to(DEVICE)
            m = torch.from_numpy((obs[:, b] * wgt).T.astype(np.float32)).to(DEVICE)
            loss = (m * (yhat - y) ** 2).sum() / m.sum()
            opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            opt.step()
        if fixed_epochs:
            print(f"    seed {seed} epoch {ep + 1:3d}/{n_ep} ({time.time() - t0:.0f}s)", flush=True)
            continue
        pz = predict_all(net, X, lookback, ts=val_t)
        score = median_nse(pz, Z, split, es_core, mu, sd, head)
        print(f"    seed {seed} epoch {ep + 1:3d} val median NSE {score:.3f} "
              f"({time.time() - t0:.0f}s)", flush=True)
        if score > best:
            best, best_ep, bad = score, ep + 1, 0
            best_state = {k: v.clone() for k, v in net.state_dict().items()}
        else:
            bad += 1
            if bad >= patience:
                break
    if best_state is not None:
        net.load_state_dict(best_state)
    else:
        best, best_ep = float("nan"), n_ep
    return predict_all(net, X, lookback), best, best_ep


def parser(run=RUN):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="*", default=[0, 1, 2, 3, 4])
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--run", default=run)
    ap.add_argument("--lookback", type=int, default=LOOKBACK)
    ap.add_argument("--hidden", type=int, default=64)
    ap.add_argument("--dropout", type=float, default=0.2)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--fold", type=int, default=None)
    ap.add_argument("--train-start", default=None)
    ap.add_argument("--refit-from", default=None)
    return ap


def run_graph_model(args, build, prepare=None):
    """Train the seeds of a graph model; `build(codes, wells, F, args)` returns make_net.
    `prepare(P, arrays)` may replace the per-well arrays by node arrays (extra nodes such as
    weather cells or pumping fields get no target, so they leave the loss and the scores)."""
    P = build_panel()
    P = P[P["mu"].notna()]
    data = arrays(P)
    if prepare is not None:
        data = prepare(P, data)
    codes, weeks, X, Z, split, core, mu, sd, head = data
    wells = pd.read_parquet(DS / "wells.parquet")
    make_net = build(codes, wells, X.shape[2], args)
    out = RESULTS / args.run / (f"fold_{args.fold}" if args.fold is not None else "")
    out.mkdir(parents=True, exist_ok=True)
    (out / "config.json").write_text(json.dumps(vars(args) | {"inputs": input_cols(P)}, indent=1))
    train_mask, keep = regime_masks(split, weeks, codes, args.fold, args.train_start,
                                    refit=args.refit_from is not None)
    for s in args.seeds:
        path = out / f"seed_{s}.parquet"
        if path.exists():
            print(f"seed {s}: cached")
            continue
        fixed = refit_epochs(args.refit_from, s) if args.refit_from else None
        pz, best, best_ep = train_seed(s, None, X, Z, split, core, mu, sd, head, args.epochs,
                                       lr=args.lr, lookback=args.lookback,
                                       train_mask=train_mask, es_wells=keep, fixed_epochs=fixed,
                                       make_net=make_net)
        save_seed(path, pz, codes, weeks, best, best_ep)
        print(f"seed {s}: best validation median NSE {best:.3f} (epoch {best_ep})", flush=True)
    if args.fold is not None:
        return
    pred, n = seed_mean_predictions(out, P)
    pred.to_parquet(out / "predictions.parquet", index=False)
    s = evaluate_run(args.run)
    c = s[(s["group"] == "all core") & (s["variant"] == "all")]
    print(f"== {args.run} ({n} seeds)")
    print(c[["split", "n_wells", "NSE", "skill", "KGE", "RMSE"]].round(3).to_string(index=False))


def build_distance(codes, wells, n_in, args):
    A = distance_adjacency(codes, wells)
    return lambda F: Net(F, A, args.hidden, args.dropout)


def main():
    run_graph_model(parser().parse_args(), build_distance)


if __name__ == "__main__":
    main()
