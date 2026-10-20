"""Global LSTM / EA-LSTM baselines (simulation task), one network for all wells.

    python -m src.models.lstm                        # LSTM, 5 seeds, resumable per seed
    python -m src.models.lstm --arch ealstm --run ealstm
    python -m src.models.lstm --seeds 0 --epochs 5   # quick smoke test
    # regimes of docs/analysis_plan.md section 4 (usually driven by src.models.regimes):
    python -m src.models.lstm --run lstm_tuned_lwo --fold 2 ...      # leave-wells-out fold 2
    python -m src.models.lstm --run lstm_tuned_f25 --train-start 2016-04-01 ...
    python -m src.models.lstm --run lstm_tuned_refit --refit-from lstm_tuned ...

Architectures (Kratzert et al. 2019, doi:10.5194/hess-23-5089-2019; Wunsch et al. 2021,
doi:10.5194/hess-25-1671-2021 for groundwater):
    lstm    the static attributes are appended to every input step
    ealstm  entity-aware LSTM: the static attributes alone set the input gate, the
            dynamic inputs drive the forget/cell/output gates
For each target week t, the input is the previous LOOKBACK weeks of weather, pumping,
rivers (dataset v3) and season. The output is the z-scored head at t. No observed head is
ever an input (simulation task), so the model also applies to unseen wells.

Training: weeks of the train split with an observed head; loss = MSE in z, each well
weighted equally (same reason as lgbm.py). Early stopping on the median validation NSE
over the core wells that are trained on. Each seed is cached in
results/<run>/seed_<k>.parquet (+ .json with the best epoch), so an interrupted run
resumes; the reported prediction is the mean over seeds.
Leave-wells-out (--fold k): the wells of fold k (splits.json) are removed from the loss
and from early stopping; their predictions are kept in fold_<k>/ and assembled by
src.models.regimes. Refit (--refit-from run): trained on train + validation for the
number of epochs early stopping chose for the same seed in `run`.
"""
import argparse
import json
import time

import warnings

import numpy as np
import pandas as pd
import torch
from torch import _VF, nn

from src.models.evaluate import DS, RESULTS, evaluate_run
from src.models.features import STATIC, build_panel

DYNAMIC = ["rain", "ETP", "EVAP", "PE", "DRAINC", "RUNC", "T", "SWI", "pump_gw", "canal",
           "season_sin", "season_cos"]
RIVER_DYNAMIC = ["river_tet", "river_agly", "river_tech", "river_near"]  # in panels from v3
LOOKBACK = 104
RUN = "lstm"
# Runs on a GPU automatically when one is present (Colab/Kaggle/Camber), else CPU.
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
# EALSTM hands freshly assembled weights to the fused kernel; cuDNN copies them into one
# buffer at each call (small at this size) and would otherwise warn about it.
warnings.filterwarnings("ignore", message="RNN module weights are not part")


def set_lookback(weeks):
    """Change the input window length (used by the tuners and the CLI)."""
    global LOOKBACK
    LOOKBACK = int(weeks)


class Net(nn.Module):
    def __init__(self, n_in, hidden=64, dropout=0.2, n_static=0):
        super().__init__()
        self.lstm = nn.LSTM(n_in, hidden, batch_first=True)
        self.head = nn.Sequential(nn.Dropout(dropout), nn.Linear(hidden, 1))

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.head(out[:, -1]).squeeze(-1)


class EALSTM(nn.Module):
    """Entity-aware LSTM (Kratzert et al. 2019): input gate i = sigmoid(W s + b) from the
    static attributes s only; forget, cell and output gates from the dynamic inputs."""

    def __init__(self, n_in, hidden=64, dropout=0.2, n_static=0, forget_bias=3.0):
        super().__init__()
        self.n_static, self.hidden = n_static, hidden
        self.gate_i = nn.Linear(n_static, hidden)
        self.w = nn.Linear(n_in - n_static, 3 * hidden)
        self.u = nn.Linear(hidden, 3 * hidden, bias=False)
        with torch.no_grad():
            self.w.bias[:hidden].fill_(forget_bias)
        self.head = nn.Sequential(nn.Dropout(dropout), nn.Linear(hidden, 1))

    def forward(self, x):
        """The same cell run by the fused LSTM kernel (cuDNN on a GPU), assembled from the
        parameters above: the input-gate row reads only the static columns and has no
        hidden-to-gate weights, the forget/cell/output rows read only the dynamic columns.
        The statics are constant along a window, so i = sigmoid(W s + b) at every week and
        this equals the explicit loop over the weeks (tests/test_ealstm.py), ~10x faster."""
        H, n_dyn = self.hidden, x.shape[2] - self.n_static
        zeros = x.new_zeros
        w_ih = torch.cat([torch.cat([zeros(H, n_dyn), self.gate_i.weight], 1),    # gate order
                          torch.cat([self.w.weight, zeros(3 * H, self.n_static)], 1)])  # i,f,g,o
        w_hh = torch.cat([zeros(H, H), self.u.weight])
        b_ih = torch.cat([self.gate_i.bias, self.w.bias])
        h0 = zeros(1, x.shape[0], H)
        out = _VF.lstm(x, (h0, h0), [w_ih, w_hh, b_ih, zeros(4 * H)], True, 1, 0.0,
                       self.training, False, True)[0]
        return self.head(out[:, -1]).squeeze(-1)


ARCHS = {"lstm": Net, "ealstm": EALSTM}


def input_cols(P):
    return DYNAMIC + [c for c in RIVER_DYNAMIC if c in P.columns] + STATIC


def arrays(P):
    """(N wells, T weeks, F) inputs standardised with training statistics."""
    P = P.sort_values(["code_bss", "week"])
    codes = list(dict.fromkeys(P["code_bss"]))
    weeks = np.sort(P["week"].unique())
    tr = P[P["split"] == "train"]
    cols = input_cols(P)
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
    return float(np.median(scores)) if scores else float("nan")


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


def regime_masks(split, weeks, codes, fold=None, train_start=None, refit=False):
    """Training mask (N, T) and the wells used for early stopping (N,) for a regime."""
    train = split == "train"
    if refit:
        train = train | (split == "validation")
    if train_start:
        train = train & (weeks >= np.datetime64(train_start))[None, :]
    keep = np.ones(len(codes), dtype=bool)
    if fold is not None:
        folds = json.loads((DS / "splits.json").read_text())["leave_wells_out"]["fold_of_well"]
        keep = np.array([folds.get(c, -1) != fold for c in codes])
        train = train & keep[:, None]
    return train, keep


def train_seed(seed, X, Z, split, core, mu, sd, head, epochs, patience=8,
               hidden=64, dropout=0.2, lr=1e-3, arch="lstm", train_mask=None, es_wells=None,
               fixed_epochs=None):
    torch.manual_seed(seed)
    np.random.seed(seed)
    torch.set_num_threads(4)
    N, T, F = X.shape
    if train_mask is None:
        train_mask = split == "train"
    es_core = core & (es_wells[:, None] if es_wells is not None else True)
    tr_idx = [(i, t) for i in range(N) for t in range(LOOKBACK - 1, T)
              if train_mask[i, t] and not np.isnan(Z[i, t])]
    counts = pd.Series([i for i, _ in tr_idx]).value_counts()
    w = np.array([1.0 / counts[i] for i, _ in tr_idx])
    w = w / w.sum()
    net = ARCHS[arch](F, hidden=hidden, dropout=dropout, n_static=len(STATIC)).to(DEVICE)
    opt = torch.optim.Adam(net.parameters(), lr=lr, weight_decay=1e-5)
    # during training, score only core wells on validation weeks (fast)
    val_mask = (split == "validation") & es_core
    best, best_state, bad, best_ep = -np.inf, None, 0, 0
    steps = max(1, len(tr_idx) // 256)
    n_ep = fixed_epochs or epochs
    for ep in range(n_ep):
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
        if fixed_epochs:
            print(f"    seed {seed} epoch {ep + 1:3d}/{n_ep} loss {loss.item():.3f} "
                  f"({time.time() - t0:.0f}s)", flush=True)
            continue
        pz = predict_all(net, X, mask=val_mask)
        score = median_nse(pz, Z, split, es_core, mu, sd, head)
        print(f"    seed {seed} epoch {ep + 1:3d} loss {loss.item():.3f} "
              f"val median NSE {score:.3f} ({time.time() - t0:.0f}s)", flush=True)
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
    return predict_all(net, X), best, best_ep


def save_seed(path, pz, codes, weeks, best, best_ep):
    df = pd.DataFrame(pz, index=codes, columns=pd.DatetimeIndex(weeks)).stack(future_stack=True)
    df.rename("z").rename_axis(["code_bss", "week"]).reset_index().to_parquet(path, index=False)
    path.with_suffix(".json").write_text(json.dumps({"best_val_nse": best, "best_epoch": best_ep}))


def seed_mean_predictions(out, P):
    seeds = [pd.read_parquet(f) for f in sorted(out.glob("seed_*.parquet"))]
    zz = pd.concat(seeds).groupby(["code_bss", "week"])["z"].agg(["mean", "std"]).reset_index()
    zz = zz.merge(P[["code_bss", "week", "mu", "sd"]], on=["code_bss", "week"])
    pred = pd.DataFrame({"code_bss": zz["code_bss"], "week": zz["week"],
                         "pred": zz["mu"] + zz["sd"] * zz["mean"],
                         "pred_seed_sd": zz["sd"] * zz["std"], "task": "simulation",
                         "horizon": 0}).dropna(subset=["pred"])
    return pred, len(seeds)


def refit_epochs(run, seed):
    f = RESULTS / run / f"seed_{seed}.json"
    if f.exists():
        return int(json.loads(f.read_text())["best_epoch"])
    eps = [json.loads(p.read_text())["best_epoch"] for p in (RESULTS / run).glob("seed_*.json")]
    if not eps:
        raise FileNotFoundError(f"no seed_*.json in results/{run}: run it before --refit-from")
    return int(np.median(eps))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="*", default=[0, 1, 2, 3, 4])
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--run", default=RUN, help="results sub-folder name")
    ap.add_argument("--arch", choices=list(ARCHS), default="lstm")
    ap.add_argument("--lookback", type=int, default=LOOKBACK)
    ap.add_argument("--hidden", type=int, default=64)
    ap.add_argument("--dropout", type=float, default=0.2)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--fold", type=int, default=None, help="leave-wells-out fold (0-4)")
    ap.add_argument("--train-start", default=None, help="shorter training period (regime R3)")
    ap.add_argument("--refit-from", default=None, help="refit on train+validation (epochs of run)")
    args = ap.parse_args()
    set_lookback(args.lookback)
    P = build_panel()
    P = P[P["mu"].notna()]
    codes, weeks, X, Z, split, core, mu, sd, head = arrays(P)
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
        pz, best, best_ep = train_seed(s, X, Z, split, core, mu, sd, head, args.epochs,
                                       hidden=args.hidden, dropout=args.dropout, lr=args.lr,
                                       arch=args.arch, train_mask=train_mask, es_wells=keep,
                                       fixed_epochs=fixed)
        save_seed(path, pz, codes, weeks, best, best_ep)
        print(f"seed {s}: best validation median NSE {best:.3f} (epoch {best_ep})", flush=True)
    if args.fold is not None:
        return  # folds are assembled by src.models.regimes
    pred, n = seed_mean_predictions(out, P)
    pred.to_parquet(out / "predictions.parquet", index=False)
    s = evaluate_run(args.run)
    core_s = s[(s["group"] == "all core") & (s["variant"] == "all")]
    print(f"== {args.run} ({n} seeds)")
    print(core_s[["split", "n_wells", "NSE", "skill", "KGE", "RMSE"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
