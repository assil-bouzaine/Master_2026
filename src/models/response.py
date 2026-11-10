"""Response-function superposition, all wells trained together (simulation task).

    python -m src.models.response --mode free   --run resp_free      # rung 1 of the ladder
    python -m src.models.response --mode pooled --lam 1 --run resp_pooled_l1   # rung 2
    python -m src.models.response --mode shared --run resp_shared    # one response per group
    python -m src.models.response --mode free --seeds 0 --steps 20 --run _smoke   # smoke test

The first rungs of the model ladder (fable_review.md §6.1; docs/analysis_plan.md §14 item 18).
The head of well i is a sum of responses to stresses, as in Pastas (Collenteur et al. 2019,
doi:10.1111/gwat.12925), but written in PyTorch and fitted for every well at once:

    head_i(t) - mu_i = d_i + sum_r  G_ir * (k_ir (*) s_ir)(t)

    r         stress            s_ir                                        sign of G_ir
    recharge  linear recharge   (rain - f_i * ETP) of the well's cell       >= 0
    pumping   abstraction       groundwater pumping within 3 km of the well  <= 0
    canal     canal water       canal intakes of the plain                   >= 0

- k_ir is a Gamma kernel on the weekly grid, k(j) ~ (j + 0.5)^(n - 1) exp(-(j + 0.5) / a),
  j = 0 .. KERNEL_WEEKS - 1, with non-negative weights that sum to 1. The gain G_ir is then the
  head change (m) under a sustained unit stress, and gain and kernel cannot trade scale.
- Signs hold by construction: G = +softplus(.) or -softplus(.), f_i in (0, F_MAX), kernel
  weights >= 0, and no parameter depends on a stress (analysis plan §10, hard monotonicity;
  tests/test_response.py checks finite differences through the whole path).
- The contributions G_ir * (k_ir (*) s_ir) are exact and additive: they are saved per seed
  (contrib_seed_<k>.parquet). An exact decomposition explains the model's computation; it is
  not the physical contribution (analysis plan §12).
- Time scales are bounded: a in (A_MIN, --amax) weeks, n in (N_MIN, N_MAX). The Pastas
  multistart of 2026-10-25 put pumping and canal time scales at their 27-year bound, where a
  response acts as a free trend (fable_review.md §4.1). The bounds are wider than any published
  response of this aquifer: BRGM's transfer model of two of our core wells finds impulse
  responses of 300 and 520 days and mean transit times of 89 and 220 days (Caballero & Ladouche
  2015, doi:10.5194/hessd-12-10109-2015, Table 1).
- --pumping split (a sensitivity; Gate 3 decides): pumping enters as two stresses, as in that
  paper: a permanent part (per well and calendar year, the mean weekly pumping of January-March
  and October-December, constant within a year) and a seasonal part (the rest, not below 0),
  each with its own response and a non-positive gain. The permanent part only varies between
  years, which is the variation pumping effects may be claimed from (analysis plan §8).
- --gain-units sd (follow-up of 2026-11-10): the gains are in units of each well's training sd
  instead of metres, so that pooled or shared gains mean "the same share of the well's own
  swing" (heads swing by centimetres at some wells and by metres at others; sharing gains in
  metres within an aquifer group was poor). The saved gains and contributions stay in metres.
- --arm C | D (rung 4): the stresses of each well are routed by the edges of a graph arm
  (src/kg/export.py through src/models/routing.py) instead of the panel's own cell and 3 km sum:
  recharge from its recharge-edge cells, pumping from its pumping-edge facilities (distance
  weighted), the unattributed pumping of arm D as its own stress, the river from its gauge edges,
  the canal where it has a canal edge. A well without an edge for a relation has no such stress.
  Two runs that differ only in --arm differ only in the edges (analysis plan §10).
  --signs structure (default): recharge, river and canal gains >= 0, both pumping gains <= 0, as
  in rungs 1-2; --signs approved: only the signs the export policy has approved (pumping; the
  recharge, river and canal signs are pending at Gate 3) are built in, the other gains are free.
  --wells: only these wells (the two-well demonstration path). No real-data contrast between
  arms is scored before the twin's design is written and the plan is tagged (items 17-18).
- --fixed-steps N (diagnostic): no early stopping, N steps for every start: separates "starts
  stopped early at different places" from "several optima" when reading the spread over starts.
- Weeks before the first forcing week (2000) are filled with each input's training mean,
  as Pastas does.

Three ways of sharing (--mode), one code path: every raw parameter is p_i = m_g(i) + delta_i,
where g(i) is the well's aquifer group.
    free    no penalty on delta: per-well parameters, as Pastas (rung 1: does fitting all
            wells together with bounded kernels remove the dependence on the start?)
    pooled  penalty lam * mean(delta^2): partial pooling towards the group (rung 2)
    shared  delta = 0: one response per aquifer group (the other end of the scale)
The constant d_i is always per well and never penalised.

Inputs are those of the Pastas reference (pastas_seasonal_canal): weather of the well's SAFRAN
cell, seasonal drinking-water pumping within 3 km, plain canal volume; weekly instead of daily.
No observed head is an input. Loss: mean over wells of MSE(m) / sd_i^2 on observed training
weeks (every well counts equally, as in the other baselines). Early stopping on the median
validation NSE of the core wells trained on. Seeds differ in their starting values: they are
the "starts" of this model, and their disagreement is a result (ladder report).

Outputs (results/<run>/): seed_<k>.parquet (z), seed_<k>.json, seed_<k>.pt,
contrib_seed_<k>.parquet (m), params_seed_<k>.csv, predictions.parquet (mean over seeds),
config.json, schema.json, manifest.json; scored by src.models.evaluate.
"""
import argparse
import json
import math
import os
import time

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as Fn
from torch import nn

from src.models.evaluate import RESULTS, evaluate_run
from src.models.features import build_panel
from src.models.lstm import (cached_seed, median_nse, refit_epochs, regime_masks, save_seed,
                             save_seed_model, seed_mean_predictions, write_config)
from src.models.manifest import write_manifest, write_schema

STRESSES = ("recharge", "pumping", "canal")
STRESS_SETS = {"sum": STRESSES,
               "split": ("recharge", "pumping_permanent", "pumping_seasonal", "canal"),
               "arm": ("recharge", "pumping", "pumping_unattributed", "river", "canal")}
STRESS_INPUT = {"pumping": "pump_gw", "pumping_permanent": "pump_pp", "pumping_seasonal": "pump_sp",
                "pumping_unattributed": "pump_un", "river": "river", "canal": "canal"}
SIGN = {"recharge": 1.0, "pumping": -1.0, "pumping_permanent": -1.0, "pumping_seasonal": -1.0,
        "pumping_unattributed": -1.0, "river": 1.0, "canal": 1.0}
# --signs approved: the signs an export policy has approved as constraints (configs/
# constraint_decisions.csv: pumping); 0 = no sign built in, the gain is a free number
SIGN_SETS = {"structure": SIGN,
             "approved": {s: (v if s.startswith("pumping") and s != "pumping_unattributed" else 0.0)
                          for s, v in SIGN.items()}}
WINTER_MONTHS = (1, 2, 3, 10, 11, 12)   # the permanent part of pumping is their mean, per year
# fixed input scales (the same for every well, so that shared gains mean the same thing):
# rain, ETP, PE in cm/week; pumping in 1e5 m3/week; canal volume in 10 Mm3/week
SCALE = {"rain": 10.0, "ETP": 10.0, "PE": 10.0, "pump_gw": 100.0, "canal": 10.0}
RAW_INPUTS = ("rain", "ETP", "PE", "pump_gw", "canal")
SCALE |= {"pump_pp": SCALE["pump_gw"], "pump_sp": SCALE["pump_gw"]}   # derived in panel_arrays
SCALE |= {"pump_un": SCALE["pump_gw"], "river": 1.0}                  # routed inputs (--arm)
ROUTED = ("rain", "ETP", "PE", "pump_gw", "pump_un", "river", "canal")
KERNEL_WEEKS = 312           # 6 years of memory at most
A_MIN, A_MAX = 0.5, 52.0     # Gamma scale a, weeks
N_MIN, N_MAX = 0.5, 3.0      # Gamma shape n
F_MAX = 1.5                  # evaporation factor of the linear recharge
SD_FLOOR = 1e-3              # m; a well whose training heads never move
INIT = {"gain": 0.1,                                                  # m per unit stress
        "a": {"recharge": 6.0}, "a_other": 13.0,                      # weeks
        "n": 1.5, "f": 0.6}


def _logit(p):
    return math.log(p / (1 - p))


def _inv_softplus(y):
    return math.log(math.expm1(y))


class ResponseModel(nn.Module):
    """head anomaly (m) = d + sum of signed gains times kernel-smoothed stresses."""

    def __init__(self, group_of, n_groups, mode="free", kernel_weeks=KERNEL_WEEKS, amax=A_MAX,
                 recharge="linear", init_sd=0.0, generator=None, pumping="sum", gain_scale=None,
                 signs="structure"):
        super().__init__()
        if mode not in ("free", "pooled", "shared"):
            raise ValueError(mode)
        self.mode, self.K, self.amax, self.recharge = mode, int(kernel_weeks), float(amax), recharge
        self.names = STRESS_SETS[pumping]
        self.register_buffer("sign", torch.tensor([SIGN_SETS[signs][s] for s in self.names]))
        self.register_buffer("group_of", torch.as_tensor(group_of, dtype=torch.long))
        self.register_buffer("lag", torch.arange(self.K, dtype=torch.float32) + 0.5)
        # metres per unit of gain: 1 (gains in metres) or the well's training sd (--gain-units sd)
        self.register_buffer("gain_scale", torch.ones(len(group_of)) if gain_scale is None
                             else torch.as_tensor(gain_scale, dtype=torch.float32))
        N, R = len(group_of), len(self.names)
        a0 = torch.tensor([_logit((math.log(INIT["a"].get(s, INIT["a_other"])) - math.log(A_MIN))
                                  / (math.log(self.amax) - math.log(A_MIN))) for s in self.names])
        g0 = torch.tensor([_inv_softplus(INIT["gain"]) if SIGN_SETS[signs][s] else 0.0   # free: from 0
                           for s in self.names])
        n0 = torch.full((R,), _logit((INIT["n"] - N_MIN) / (N_MAX - N_MIN)))
        f0 = torch.tensor([_logit(INIT["f"] / F_MAX)])
        base = torch.cat([g0, a0, n0, f0])                    # (3R + 1,)
        noise = lambda *shape: init_sd * torch.randn(*shape, generator=generator)  # noqa: E731
        self.group_mean = nn.Parameter(base.repeat(n_groups, 1) + noise(n_groups, len(base)))
        # per-well deviations; frozen at 0 in "shared" mode
        self.delta = nn.Parameter(noise(N, len(base)) if mode == "free" else torch.zeros(N, len(base)),
                                  requires_grad=mode != "shared")
        self.d = nn.Parameter(torch.zeros(N))

    def raw(self):
        return self.group_mean[self.group_of] + self.delta      # (N, 3R + 1)

    def parameters_physical(self):
        """gain (N, R) signed, m per unit stress; a (N, R) weeks; n (N, R); f (N,)."""
        p, R = self.raw(), len(self.names)
        g = p[:, :R]
        gain = torch.where(self.sign != 0, self.sign * Fn.softplus(g), g) * self.gain_scale[:, None]
        a = torch.exp(math.log(A_MIN) + torch.sigmoid(p[:, R:2 * R])
                      * (math.log(self.amax) - math.log(A_MIN)))
        n = N_MIN + torch.sigmoid(p[:, 2 * R:3 * R]) * (N_MAX - N_MIN)
        f = F_MAX * torch.sigmoid(p[:, 3 * R])
        return gain, a, n, f

    def kernels(self, a, n):
        """(N, R, K) non-negative weights summing to 1 along K; index j = lag in weeks."""
        logk = (n[..., None] - 1) * torch.log(self.lag) - self.lag / a[..., None]
        return torch.softmax(logk, dim=-1)

    def stresses(self, X, f):
        """X: dict of (N, T + K - 1) scaled inputs, padded on the left -> (N, R, T + K - 1)."""
        rch = X["PE"] if self.recharge == "pe" else X["rain"] - f[:, None] * X["ETP"]
        return torch.stack([rch] + [X[STRESS_INPUT[s]] for s in self.names[1:]], dim=1)

    def contributions(self, X):
        """(N, R, T) in metres: gain times the causal convolution of each stress."""
        gain, a, n, f = self.parameters_physical()
        S = self.stresses(X, f)                                  # (N, R, T + K - 1)
        N, R, L = S.shape
        w = self.kernels(a, n).flip(-1).reshape(N * R, 1, self.K)   # correlation -> convolution
        c = Fn.conv1d(S.reshape(1, N * R, L), w, groups=N * R).reshape(N, R, L - self.K + 1)
        return gain[..., None] * c

    def forward(self, X):
        return self.d[:, None] + self.contributions(X).sum(1)    # (N, T), m above mu

    def penalty(self):
        return (self.delta ** 2).mean()


def panel_arrays(P, kernel_weeks=KERNEL_WEEKS, routed=None):
    """Panel -> wells, weeks, padded inputs and targets.
    Inputs: dict name -> (N, T + K - 1) float32, scaled by SCALE, gaps and the K - 1 weeks
    before the first week filled with the well's training mean of that input. With `routed`
    (src.models.routing.routed_inputs of a graph arm) the weather, pumping, river and canal series
    come from it instead of the panel's columns."""
    P = P.sort_values(["code_bss", "week"])
    codes = list(dict.fromkeys(P["code_bss"]))
    weeks = np.sort(P["week"].unique())
    N, T = len(codes), len(weeks)
    piv = lambda c: P[c].to_numpy().reshape(N, T)  # noqa: E731
    split = piv("split")
    train = split == "train"
    X = {}
    raw = {c: piv(c).astype(np.float64) / SCALE[c] for c in RAW_INPUTS}
    if routed is not None:
        if not (np.array_equal(pd.DatetimeIndex(routed["weeks"]).to_numpy(), pd.DatetimeIndex(weeks).to_numpy())):
            raise ValueError("the routed inputs are on other weeks than the panel")
        row = {c: i for i, c in enumerate(routed["codes"])}
        idx = [row[c] for c in codes]
        raw |= {c: np.asarray(routed[c], dtype=np.float64)[idx] / SCALE[c] for c in ROUTED}
    # permanent and seasonal parts of pumping (--pumping split): per well and calendar year, the
    # mean of the winter weeks, constant within the year; the rest, not below 0
    wk = pd.DatetimeIndex(weeks)
    pp = np.zeros_like(raw["pump_gw"])
    for y in np.unique(wk.year):
        in_year = wk.year == y
        winter = in_year & np.isin(wk.month, WINTER_MONTHS)
        pp[:, in_year] = np.nanmean(raw["pump_gw"][:, winter if winter.any() else in_year],
                                    axis=1, keepdims=True)
    raw["pump_pp"], raw["pump_sp"] = pp, np.clip(raw["pump_gw"] - pp, 0.0, None)
    for c, v in raw.items():
        mean = np.nanmean(np.where(train, v, np.nan), axis=1, keepdims=True)
        mean = np.where(np.isfinite(mean), mean, 0.0)
        v = np.where(np.isfinite(v), v, mean)
        X[c] = np.concatenate([np.repeat(mean, kernel_weeks - 1, axis=1), v], axis=1).astype(np.float32)
    head, mu, sd = piv("head").astype(np.float64), piv("mu").astype(np.float64), piv("sd").astype(np.float64)
    groups = sorted(P["group"].unique())
    group_of = np.array([groups.index(g) for g in P.drop_duplicates("code_bss")["group"]])
    return {"codes": codes, "weeks": weeks, "X": X, "head": head, "mu": mu, "sd": sd,
            "split": split, "core": piv("core").astype(bool), "groups": groups,
            "group_of": group_of}


def train_seed(seed, data, mode, lam=0.0, steps=4000, lr=0.05, patience=15, eval_every=20,
               kernel_weeks=KERNEL_WEEKS, amax=A_MAX, recharge="linear", init_sd=0.5,
               train_mask=None, es_wells=None, fixed_steps=None, state_out=None, pumping="sum",
               gain_units="m", signs="structure"):
    """One start. Returns (model, best validation median NSE, best step)."""
    torch.manual_seed(seed)
    torch.set_num_threads(int(os.environ.get("PFE_THREADS", 4)))
    gen = torch.Generator().manual_seed(seed)
    X = {k: torch.from_numpy(v) for k, v in data["X"].items()}
    head, mu, sd, split, core = (data[k] for k in ("head", "mu", "sd", "split", "core"))
    sd_safe = np.maximum(sd, SD_FLOOR)
    if train_mask is None:
        train_mask = split == "train"
    obs = np.isfinite(head) & train_mask
    y = torch.from_numpy(np.nan_to_num(head - mu).astype(np.float32))
    wgt = obs / np.maximum(obs.sum(1, keepdims=True), 1) / sd_safe ** 2     # per well: mean / var
    wgt = torch.from_numpy((wgt / max((obs.sum(1) > 0).sum(), 1)).astype(np.float32))
    es_core = core & (es_wells[:, None] if es_wells is not None else True)
    net = ResponseModel(data["group_of"], len(data["groups"]), mode, kernel_weeks, amax, recharge,
                        init_sd=init_sd, generator=gen, pumping=pumping,
                        gain_scale=sd_safe[:, 0] if gain_units == "sd" else None, signs=signs)
    opt = torch.optim.Adam([p for p in net.parameters() if p.requires_grad], lr=lr)
    best, best_state, best_step, bad = -np.inf, None, 0, 0
    n_steps = fixed_steps or steps
    t0 = time.time()
    for step in range(1, n_steps + 1):
        loss = (wgt * (net(X) - y) ** 2).sum()
        if mode == "pooled" and lam > 0:
            loss = loss + lam * net.penalty()
        opt.zero_grad()
        loss.backward()
        opt.step()
        if fixed_steps or step % eval_every:
            continue
        with torch.no_grad():
            pz = (net(X).numpy() / sd_safe).astype(np.float32)
        score = median_nse(pz, head, split, es_core, mu, sd_safe, head)
        if score > best:
            best, best_step, bad = score, step, 0
            best_state = {k: v.clone() for k, v in net.state_dict().items()}
        else:
            bad += 1
            if bad >= patience:
                break
    if best_state is not None:
        net.load_state_dict(best_state)
    else:                                   # fixed number of steps: the last step, scored once
        with torch.no_grad():
            pz = (net(X).numpy() / sd_safe).astype(np.float32)
        best, best_step = median_nse(pz, head, split, es_core, mu, sd_safe, head), n_steps
    print(f"    seed {seed}: step {best_step} of {step}, loss {loss.item():.4f}, "
          f"val median NSE {best:.3f} ({time.time() - t0:.0f}s)", flush=True)
    if state_out is not None:
        state_out.update({k: v.detach().clone() for k, v in net.state_dict().items()})
    return net, best, best_step


def seed_outputs(net, data):
    """Predictions in z, contributions (long table, m) and parameters (per well) of one start."""
    X = {k: torch.from_numpy(v) for k, v in data["X"].items()}
    with torch.no_grad():
        contrib = net.contributions(X).numpy()                   # (N, R, T)
        gain, a, n, f = (t.numpy() for t in net.parameters_physical())
        d = net.d.numpy()
    out = d[:, None] + contrib.sum(1)
    pz = (out / np.maximum(data["sd"], SD_FLOOR)).astype(np.float32)
    N, R, T = contrib.shape
    idx = pd.MultiIndex.from_product([data["codes"], pd.DatetimeIndex(data["weeks"])],
                                     names=["code_bss", "week"])
    c = pd.DataFrame({s: contrib[:, r].reshape(-1).astype(np.float32)
                      for r, s in enumerate(net.names)}, index=idx).reset_index()
    p = pd.DataFrame({"code_bss": data["codes"], "group": [data["groups"][g] for g in data["group_of"]],
                      "d_m": d, "f": f})
    for r, s in enumerate(net.names):
        p[f"gain_{s}"], p[f"a_{s}_wk"], p[f"n_{s}"] = gain[:, r], a[:, r], n[:, r]
        p[f"mean_lag_{s}_wk"] = a[:, r] * n[:, r]
    return pz, c, p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["free", "pooled", "shared"], required=True)
    ap.add_argument("--lam", type=float, default=0.0, help="pooled: weight of mean(delta^2)")
    ap.add_argument("--run", default=None, help="results sub-folder (default resp_<mode>)")
    ap.add_argument("--seeds", type=int, nargs="*", default=list(range(10)))
    ap.add_argument("--steps", type=int, default=4000)
    ap.add_argument("--lr", type=float, default=0.05)
    ap.add_argument("--amax", type=float, default=A_MAX, help="upper bound of the Gamma scale, weeks")
    ap.add_argument("--kernel-weeks", type=int, default=KERNEL_WEEKS)
    ap.add_argument("--recharge", choices=["linear", "pe"], default="linear",
                    help="linear: rain - f * ETP (as Pastas); pe: SIM2 effective rainfall")
    ap.add_argument("--pumping", choices=["sum", "split"], default="sum",
                    help="split: a permanent and a seasonal pumping stress (sensitivity)")
    ap.add_argument("--arm", choices=["C", "D"], default=None,
                    help="route the stresses by the edges of this graph arm (src.kg.export)")
    ap.add_argument("--policy", default="main", help="with --arm: the export policy")
    ap.add_argument("--signs", choices=list(SIGN_SETS), default="structure",
                    help="approved: only the signs the export policy has approved are built in")
    ap.add_argument("--wells", nargs="*", default=None, help="only these wells (code_bss)")
    ap.add_argument("--gain-units", choices=["m", "sd"], default="m",
                    help="sd: gains in units of each well's training sd (for pooling and sharing)")
    ap.add_argument("--fixed-steps", type=int, default=None,
                    help="diagnostic: this many steps for every start, no early stopping")
    ap.add_argument("--fold", type=int, default=None, help="leave-wells-out fold (0-4)")
    ap.add_argument("--train-start", default=None, help="shorter training period (regime R3)")
    ap.add_argument("--refit-from", default=None, help="refit on train+validation (steps of run)")
    args = ap.parse_args()
    if args.mode == "pooled" and args.lam <= 0:
        ap.error("--mode pooled needs --lam > 0")
    run = args.run or f"resp_{args.mode}"
    pumping = args.pumping
    if pumping == "sum":          # the default leaves the fingerprints of earlier runs unchanged
        del args.pumping
    names = STRESS_SETS[pumping]
    gain_units, fixed_steps = args.gain_units, args.fixed_steps
    arm, policy, signs, only = args.arm, args.policy, args.signs, args.wells
    if gain_units == "m":
        del args.gain_units
    if fixed_steps is None:
        del args.fixed_steps
    if arm is None:               # as above: defaults leave earlier fingerprints unchanged
        del args.arm, args.policy
    else:
        pumping, names = "arm", STRESS_SETS["arm"]
    if signs == "structure":
        del args.signs
    if only is None:
        del args.wells
    P = build_panel(train_start=args.train_start)
    P = P[P["mu"].notna()]
    if only is not None:
        missing = sorted(set(only) - set(P["code_bss"]))
        if missing:
            ap.error(f"unknown wells: {missing}")
        P = P[P["code_bss"].isin(only)]
    routed, extra = None, None
    if arm is not None:
        from src.models.routing import coverage, routed_inputs
        routed = routed_inputs(arm, policy)
        core_of = P.drop_duplicates("code_bss").set_index("code_bss")["core"]
        keep = [c in core_of.index for c in routed["codes"]]
        cov = {k: {"wells": int(routed[f"has_{k}"][keep].sum())} for k in coverage(routed, [True] * len(keep))}
        extra = {"arm": arm, "export": routed["export"], "wells_with_relation": cov}
        print(f"arm {arm} ({policy}): wells with each relation {{{', '.join(f'{k} {v['wells']}' for k, v in cov.items())}}} "
              f"of {sum(keep)}", flush=True)
    data = panel_arrays(P, args.kernel_weeks, routed)
    out = RESULTS / run / (f"fold_{args.fold}" if args.fold is not None else "")
    out.mkdir(parents=True, exist_ok=True)
    inputs = [f"{c}/{SCALE[c]:g}" for c in (ROUTED if arm else RAW_INPUTS)]
    fp = write_config(out, args, inputs, extra and {"export_release": extra["export"]["release"]})
    write_schema(out, {"nodes": data["codes"], "weeks": [str(data["weeks"][0])[:10], str(data["weeks"][-1])[:10]],
                       "inputs": inputs, "stresses": list(names),
                       "signs": {s: SIGN_SETS[signs][s] for s in names}, **(extra or {}),
                       "groups": data["groups"], "group_of": data["group_of"].tolist(),
                       "kernel_weeks": args.kernel_weeks, "a_bounds_wk": [A_MIN, args.amax],
                       "n_bounds": [N_MIN, N_MAX], "f_max": F_MAX, "mode": args.mode})
    train_mask, keep = regime_masks(data["split"], data["weeks"], data["codes"], args.fold,
                                    args.train_start, refit=args.refit_from is not None)
    for s in args.seeds:
        path = out / f"seed_{s}.parquet"
        if cached_seed(path, fp):
            continue
        fixed = refit_epochs(args.refit_from, s) if args.refit_from else fixed_steps
        state = {}
        net, best, best_step = train_seed(s, data, args.mode, args.lam, args.steps, args.lr,
                                          kernel_weeks=args.kernel_weeks, amax=args.amax,
                                          recharge=args.recharge, train_mask=train_mask,
                                          es_wells=keep, fixed_steps=fixed, state_out=state,
                                          pumping=pumping, gain_units=gain_units, signs=signs)
        pz, contrib, params = seed_outputs(net, data)
        contrib.to_parquet(out / f"contrib_seed_{s}.parquet", index=False)
        params.to_csv(out / f"params_seed_{s}.csv", index=False)
        save_seed_model(out, s, state, best, best_step, fp)
        save_seed(path, pz, data["codes"], data["weeks"], best, best_step, fp)
        write_manifest(out, vars(args) | {"fingerprint": fp}, [s])
    if args.fold is not None:
        return
    pred, n = seed_mean_predictions(out, P, args.seeds)
    pred.to_parquet(out / "predictions.parquet", index=False)
    s = evaluate_run(run)
    c = s[(s["group"] == "all core") & (s["variant"] == "all")]
    print(f"== {run} ({n} seeds)")
    print(c[["split", "n_wells", "NSE", "skill", "KGE", "RMSE"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
