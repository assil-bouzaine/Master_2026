"""Global LSTM baseline (simulation task), entity-aware via static attributes.

    python -m src.models.lstm                  # 5 seeds, resumable per seed
    python -m src.models.lstm --seeds 0 --epochs 5   # quick smoke test

One network for all wells (Kratzert et al. 2019, doi:10.5194/hess-23-5089-2019;
Wunsch et al. 2021, doi:10.5194/hess-25-1671-2021 for groundwater). For each
target week t, the input is the sequence of the previous LOOKBACK weeks of
weather, pumping and season; the static attributes of the well are appended
to every step. The output is the z-scored head at t. No observed head is ever
an input (simulation task), so the model also applies to unseen wells.

Training: weeks of the train split with an observed head; loss = MSE in z,
each well weighted equally (same reason as lgbm.py). Early stopping on the
median validation NSE over core wells. Each seed is cached in
results/lstm/seed_<k>.parquet, so an interrupted run resumes; the reported
prediction is the mean over seeds.
"""
import argparse
import json
import time

import numpy as np
import pandas as pd
import torch
from torch import nn

from src.models.evaluate import RESULTS, evaluate_run
from src.models.features import STATIC, build_panel

DYNAMIC = ["rain", "ETP", "EVAP", "PE", "DRAINC", "RUNC", "T", "SWI", "pump_gw", "canal",
           "season_sin", "season_cos"]
LOOKBACK = 104
RUN = "lstm"
# Runs on a GPU automatically when one is present (Colab/Kaggle/Camber), else CPU.
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def set_lookback(weeks):
    """Change the input window length (used by tune_lstm.py and the CLI)."""
    global LOOKBACK
    LOOKBACK = int(weeks)


class Net(nn.Module):
    def __init__(self, n_in, hidden=64, dropout=0.2):
        super().__init__()
        self.lstm = nn.LSTM(n_in, hidden, batch_first=True)
        self.head = nn.Sequential(nn.Dropout(dropout), nn.Linear(hidden, 1))

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.head(out[:, -1]).squeeze(-1)


def arrays(P):
    """(N wells, T weeks, F) inputs standardised with training statistics."""
    P = P.sort_values(["code_bss", "week"])
    codes = list(dict.fromkeys(P["code_bss"]))
    weeks = np.sort(P["week"].unique())
    tr = P[P["split"] == "train"]
    cols = DYNAMIC + STATIC
    mean, std = tr[cols].mean(), tr[cols].std().replace(0, 1)
    X = ((P[cols] - mean) / std).fillna(0.0).to_numpy(np.float32).reshape(len(codes), len(weeks), -1)
    piv = lambda c: P[c].to_numpy().reshape(len(codes), len(weeks))  # noqa: E731
    return codes, weeks, X, piv("z").astype(np.float32), piv("split"), piv("core").astype(bool), \
        piv("mu"), piv("sd"), piv("head")


def windows(X, idx):
    """Stack input windows ending at (well, week) pairs idx."""
    return torch.from_numpy(np.stack([X[i, t - LOOKBACK + 1:t + 1] for i, t in idx])).to(DEVICE)


def median_nse(pred_z, Z, split, core, mu, sd, head, name="validation"):
    scores = []
    for i in range(Z.shape[0]):
        m = (split[i] == name) & ~np.isnan(head[i]) & ~np.isnan(pred_z[i])
        if core[i, 0] and m.sum() >= 26:
            o, s = head[i, m], mu[i, m] + sd[i, m] * pred_z[i, m]
            scores.append(1 - ((s - o) ** 2).sum() / ((o - o.mean()) ** 2).sum())
    return float(np.median(scores))


def predict_all(net, X, batch=2048, mask=None):
    """Predict every (well, week), or only where `mask` (N, T) is True."""
    N, T, _ = X.shape
    out = np.full((N, T), np.nan, dtype=np.float32)
    idx = [(i, t) for i in range(N) for t in range(LOOKBACK - 1, T)
           if mask is None or mask[i, t]]
    net.eval()
    with torch.no_grad():
        for k in range(0, len(idx), batch):
            b = idx[k:k + batch]
            y = net(windows(X, b)).cpu().numpy()
            for (i, t), v in zip(b, y):
                out[i, t] = v
    return out


def train_seed(seed, X, Z, split, core, mu, sd, head, epochs, patience=8,
               hidden=64, dropout=0.2, lr=1e-3):
    torch.manual_seed(seed)
    np.random.seed(seed)
    torch.set_num_threads(4)
    N, T, F = X.shape
    tr_idx = [(i, t) for i in range(N) for t in range(LOOKBACK - 1, T)
              if split[i, t] == "train" and not np.isnan(Z[i, t])]
    counts = pd.Series([i for i, _ in tr_idx]).value_counts()
    w = np.array([1.0 / counts[i] for i, _ in tr_idx])
    w = w / w.sum()
    net = Net(F, hidden=hidden, dropout=dropout).to(DEVICE)
    opt = torch.optim.Adam(net.parameters(), lr=lr, weight_decay=1e-5)
    # during training, score only core wells on validation weeks (fast)
    val_mask = (split == "validation") & core
    best, best_state, bad = -np.inf, None, 0
    steps = max(1, len(tr_idx) // 256)
    for ep in range(epochs):
        net.train()
        t0 = time.time()
        for _ in range(steps):
            pick = np.random.choice(len(tr_idx), 256, p=w)  # equal weight per well
            b = [tr_idx[k] for k in pick]
            x = windows(X, b)
            y = torch.from_numpy(np.array([Z[i, t] for i, t in b], dtype=np.float32)).to(DEVICE)
            loss = nn.functional.mse_loss(net(x), y)
            opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            opt.step()
        pz = predict_all(net, X, mask=val_mask)
        score = median_nse(pz, Z, split, core, mu, sd, head)
        print(f"    seed {seed} epoch {ep + 1:3d} loss {loss.item():.3f} "
              f"val median NSE {score:.3f} ({time.time() - t0:.0f}s)", flush=True)
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
    ap.add_argument("--run", default=RUN, help="results sub-folder name")
    ap.add_argument("--lookback", type=int, default=LOOKBACK)
    ap.add_argument("--hidden", type=int, default=64)
    ap.add_argument("--dropout", type=float, default=0.2)
    ap.add_argument("--lr", type=float, default=1e-3)
    args = ap.parse_args()
    set_lookback(args.lookback)
    P = build_panel()
    P = P[P["mu"].notna()]
    codes, weeks, X, Z, split, core, mu, sd, head = arrays(P)
    out = RESULTS / args.run
    out.mkdir(parents=True, exist_ok=True)
    (out / "config.json").write_text(json.dumps(vars(args), indent=1))
    for s in args.seeds:
        path = out / f"seed_{s}.parquet"
        if path.exists():
            print(f"seed {s}: cached")
            continue
        pz, best = train_seed(s, X, Z, split, core, mu, sd, head, args.epochs,
                              hidden=args.hidden, dropout=args.dropout, lr=args.lr)
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
    s = evaluate_run(args.run)
    core_s = s[(s["group"] == "all core") & (s["variant"] == "all")]
    print(f"== {args.run} ({len(seeds)} seeds)")
    print(core_s[["split", "n_wells", "NSE", "KGE", "RMSE"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
