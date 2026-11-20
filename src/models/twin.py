"""Semi-synthetic twin: synthetic heads from known responses on the real wells and inputs.

    python -m src.models.twin --run twin_pilot --worlds 0 1 2                       # base cell
    python -m src.models.twin --run twin_pilot_conv --worlds 0 --fits pooled:0.1:3000
    python -m src.models.twin --run twin_rq2 --worlds 0 --fits free free+none free+soft1 --arms D T
    python -m src.models.twin --run twin_map --grid --worlds 0-19                   # the map
    python -m src.models.twin --run twin_map --slices --worlds 0-19                 # its slices

Design, dials and scores: docs/analysis_plan.md §14 item 19 and its amendment of 2026-11-16, both
written before any world was generated. A world keeps what is real (wells, weeks, weather,
facility volumes, river and canal series, which weeks have a head, the splits) and replaces the
heads:

    head_i(t) = level_i + sum_r gain_ir (k_ir * s_ir)(t) + AR(1) noise,   r = recharge, pumping,
                                                                           river, canal

generated from the routed inputs of a truth graph the learner never sees. The learner, the response
model of rung 4 (src/models/response.py with routed stresses), is fitted on the same world and the
same starts three times: with arm C's edges, with arm D's, and with the truth's own (arm T, the
oracle: what routing could gain at most). The arms differ only in their routing, and the truth is
known.

Dials:
    eps      share of the graph's attributed pumping pairs that are not true (false attributions)
    u        share of a well's true pumping volume carried by pairs the graph does not attribute
    pi       pumping's share of the summed variances of the contributions (training period)
    nu       noise variance / variance of the noise-free head
    timing   "reconstructed" (within a year pumping follows the climatic deficit, as in the
             dataset) or "independent" (a fixed calendar profile per facility)
    variant  None, or one of: "I" hidden year-to-year variation where pumping is imputed, "O" an
             omitted slow driver in one aquifer group, "S" responses the model does not have
             (recharge only above a threshold, pumping delayed by a dead time), "G" the truth's
             recharge, river and canal edges are arm C's instead of arm D's

Truth graph: recharge, river and canal edges are arm D's (arm C's in variant G); a well without a
recharge edge in D gets its own cell, arm C's edge (the graph's silence is not absence of recharge,
so arm D's gaps cost it what they would cost in reality). Pumping pairs (facility, well) within
5 km: the attributed ones are true except a share eps of them, plus unattributed ones drawn until
they carry the share u of the true volume (of the well's unattributed volume when no attributed
pair is true). Arms C and D are the export's tables, unchanged: the dials move the truth away from
the graph, not the graph away from the truth (amendment of 2026-11-16, point 2). The draws use one
random stream per world, purpose and well, so cells with the same world seed share their
responses and noise, and their truths are nested: a larger eps drops more of the same attributed
pairs, a larger u adds more of the same unattributed ones.

The twin tests behaviour under these generators; it says nothing about what is true in the
aquifer (analysis plan §10). It fits models, so it runs on Kaggle CPU (scripts/run_v4_cpu.sh,
steps twin_*); tests/test_twin.py checks the generator.

Output: results/<dataset>/<run>/<cell>/world_<k>.json (dials, realised dials, scores per learner
setting and arm, per-well values) and manifest.json per cell.
"""
import argparse
import itertools
import json
import os
import time
import warnings

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as Fn

from src.config import DATASET_DIR, TEST_PERIODS
from src.models import response as R
from src.models.evaluate import MIN_WEEKS, RESULTS
from src.models.features import build_panel, river_series
from src.models.manifest import code_version, write_manifest
from src.models.routing import _matrix, facility_volumes, load_edges, routed_inputs

TRUTH = ("recharge", "pumping", "river", "canal")
SIGN = {"recharge": 1.0, "pumping": -1.0, "river": 1.0, "canal": 1.0}
LAG_WEEKS = {"recharge": (8.0, 40.0), "pumping": (2.0, 12.0), "river": (4.0, 20.0), "canal": (4.0, 20.0)}
SHAPE = (1.0, 2.5)
F_RANGE = (0.4, 1.0)
WELL_SD = 0.3                   # log-normal deviation of a well's mean lag from its group's
SHARE_RIVER = SHARE_CANAL = 0.1
MIN_RECHARGE_SHARE = 0.2
AR_RANGE = (0.8, 0.97)
OMITTED_SHARE, OMITTED_GROUP = 0.15, "Pliocene multilayer"
THRESHOLD_Q, DEAD_WEEKS = 0.60, 8
CUT = 0.20                      # the controlled intervention: true-edge facilities -20 % in the drought
GRID = {"eps": (0.0, 0.1, 0.25, 0.5), "u": (0.0, 0.3, 0.6)}
BASE = {"eps": 0.1, "u": 0.3, "pi": 0.3, "nu": 0.25, "timing": "reconstructed", "variant": None}
SLICES = ({"pi": 0.1}, {"pi": 0.5}, {"nu": 1.0}, {"timing": "independent"},
          {"variant": "I"}, {"variant": "O"}, {"variant": "S"}, {"variant": "G"})
ARMS = ("C", "D", "T")
OTHER = ("recharge", "river", "canal")
PAIR = ["src", "dst", "weight", "distance_m"]
STREAM = {"params": 1, "u": 2, "eps": 3, "hidden": 4, "omitted": 5, "noise": 6}
CONV = "fft"            # the learner's convolution (src/models/response.py --conv; same numbers, faster)
RIVER_RULE = "legacy"   # the river gap rule of every world (src/models/features.py river_series), pinned


def load_base(policy="main", kernel_weeks=R.KERNEL_WEEKS):
    """What every world reuses: the panel (its real heads give only the mask and the scale), the
    export's edges of arms C and D, the facilities' weekly volumes."""
    P = build_panel()
    P = P[P["mu"].notna()].sort_values(["code_bss", "week"]).reset_index(drop=True)
    codes = list(dict.fromkeys(P["code_bss"]))
    weeks = pd.DatetimeIndex(np.sort(P["week"].unique()))
    if len(P) != len(codes) * len(weeks):
        raise ValueError("the panel is not one row per well and week")
    split = P["split"].to_numpy().reshape(len(codes), len(weeks))
    if not (split == split[:1]).all():
        raise ValueError("the twin needs the same split for every well")
    ec, _ = load_edges("C", policy)
    ed, meta = load_edges("D", policy)
    keep = lambda e: e[e["dst"].isin(codes)].reset_index(drop=True)  # noqa: E731
    vol = facility_volumes(weeks)
    return {"P": P, "codes": codes, "weeks": weeks, "split": split, "train": split[0] == "train",
            "ec": keep(ec), "ed": keep(ed), "vol": vol, "K": kernel_weeks,
            "export": meta["release"], "policy": policy, "river_rule": RIVER_RULE,
            "inputs_sha256": inputs_sha256(P, vol, weeks, RIVER_RULE)}


def inputs_sha256(P, vol, weeks, river_rule):
    """Hash of what every world reuses besides the export: the panel's wells, weeks, splits, scale
    and observed-head mask, the facilities' weekly volumes and the river series. Worlds of one cell
    must share it (recorded from 2026-11-20; the first worlds have none)."""
    import hashlib
    h = hashlib.sha256()
    key = P[["code_bss", "week", "split", "core", "mu", "sd"]].assign(obs=P["head"].notna())
    h.update(pd.util.hash_pandas_object(key, index=False).to_numpy().tobytes())
    h.update(np.ascontiguousarray(vol.reindex(index=weeks).to_numpy(dtype=float)).tobytes())
    h.update("|".join(map(str, vol.columns)).encode())
    splits = json.loads((DATASET_DIR / "splits.json").read_text())
    h.update(np.ascontiguousarray(river_series(weeks, splits["train"][1], rule=river_rule)
                                  .sort_index(axis=1).to_numpy(dtype=float)).tobytes())
    return h.hexdigest()


def _route(base_or_world, **kw):
    """routed_inputs with the twin's pinned river rule."""
    return routed_inputs(river_rule=base_or_world["river_rule"], **kw)


def _gen(seed, purpose, i=0):
    return np.random.default_rng([seed, STREAM[purpose], i])


def pumping_graphs(base, eps, u, seed):
    """(true pumping pairs, per-well record); pairs are DataFrames with src, dst, weight,
    distance_m. Arm D, as the learner sees it, is the export's graph unchanged; the truth departs
    from it: a share eps of its attributed pairs are not true (false attributions, the error the
    measured precisions describe), and unattributed pairs are true until they carry the share u of
    the true volume (pairs the graph misses). Volumes are training-period mean weekly volumes times
    the edge weight (the share of the stress each pair carries)."""
    ed = base["ed"]
    A = ed.loc[ed["relation"] == "pumping", PAIR]
    U = ed.loc[ed["relation"] == "pumping_unattributed", PAIR]
    mean_vol = base["vol"].loc[base["weeks"][base["train"]]].mean()
    truth, rec = [], []
    for i, code in enumerate(base["codes"]):
        a, un = A[A["dst"] == code], U[U["dst"] == code]
        # a share eps of the attributed pairs are false: in arm D, not in the truth
        g = _gen(seed, "eps", i)
        r, order_a = g.random(), g.permutation(len(a))
        n_false = min(int(np.floor(eps * len(a) + r)), len(a))
        a_true = a.iloc[np.sort(order_a[n_false:])]
        va = float((a_true["weight"] * a_true["src"].map(mean_vol).fillna(0.0)).sum())
        vu = (un["weight"] * un["src"].map(mean_vol).fillna(0.0)).to_numpy()
        # unattributed pairs made true, in a fixed random order, until they carry the share u
        order = _gen(seed, "u", i).permutation(len(un))
        target = (u / (1 - u) * va if va > 0 else u * float(vu.sum())) if u > 0 else 0.0
        k = min(int(np.searchsorted(np.cumsum(vu[order]), target)) + 1, len(un)) if target > 0 else 0
        extra = un.iloc[np.sort(order[:k])]
        v_extra = float(vu[order[:k]].sum())
        truth.append(pd.concat([a_true, extra]))
        if va > 0:
            u_real = v_extra / (va + v_extra)          # share of the true volume
        elif vu.sum() > 0:
            u_real = v_extra / vu.sum()                # no true attributed pair: share of the unattributed volume
        else:
            u_real = np.nan
        rec.append({"code_bss": code, "attributed": len(a), "false_attributed": n_false, "true_extra": k,
                    "v_attributed_true": va, "v_extra": v_extra, "v_unattributed": float(vu.sum()),
                    "u_realised": u_real})
    return pd.concat(truth, ignore_index=True), pd.DataFrame(rec)


def edge_table(pairs, relation, cols):
    t = pd.DataFrame({"relation": relation, "src_type": "facility", "src": pairs["src"].to_numpy(),
                      "dst": pairs["dst"].to_numpy(), "weight": pairs["weight"].to_numpy(dtype=float),
                      "distance_m": pairs["distance_m"].to_numpy(dtype=float)})
    return t.reindex(columns=cols)


def truth_graph(base, eps, u, seed, variant=None):
    """Edge table of the truth (the learner never sees it) and the per-well record of the pumping
    draws. Arms C and D are the export's tables, unchanged."""
    ec, ed = base["ec"], base["ed"]
    truth_p, rec = pumping_graphs(base, eps, u, seed)
    if variant == "G":                       # the graph wrong on the other relations
        other = ec[ec["relation"].isin(OTHER)]
    else:
        other = ed[ed["relation"].isin(OTHER)]
        have = set(other.loc[other["relation"] == "recharge", "dst"])
        other = pd.concat([other, ec[(ec["relation"] == "recharge") & ~ec["dst"].isin(have)]])
    return pd.concat([other, edge_table(truth_p, "pumping", ed.columns)], ignore_index=True), rec


def imputed_years(weeks):
    """Calendar years whose pumping volume is mostly imputed in the dataset."""
    from src.config import DATASET_DIR
    pw = pd.read_parquet(DATASET_DIR / "pumping_weekly.parquet", columns=["week", "volume_m3", "imputed"])
    y = pw["week"].dt.year
    share = (pw["volume_m3"] * pw["imputed"]).groupby(y).sum() / pw["volume_m3"].groupby(y).sum().clip(lower=1e-9)
    return sorted(int(k) for k, v in share.items() if v > 0.5 and weeks.year.min() <= k <= weeks.year.max())


def calendar_volumes(vol, train):
    """Timing "independent": each facility's annual totals spread by its own mean calendar profile
    of the training years, the same every year (the mean profile of the others for a facility
    without training volume, so that no volume is lost)."""
    year = vol.index.year
    woy = np.minimum(vol.index.isocalendar().week.to_numpy(), 52)
    annual = vol.groupby(year).transform("sum")
    share = (vol / annual.where(annual > 0)).fillna(0.0)
    profile = share[train].groupby(woy[train]).mean().reindex(range(1, 53)).fillna(0.0)
    empty = profile.sum() <= 0
    if empty.any():
        mean = profile.loc[:, ~empty].mean(axis=1) if (~empty).any() else pd.Series(1.0, profile.index)
        profile.loc[:, empty] = np.repeat(mean.to_numpy()[:, None], int(empty.sum()), axis=1)
    p = pd.DataFrame(profile.to_numpy()[woy - 1], index=vol.index, columns=vol.columns)
    p = p / p.groupby(year).transform("sum").where(lambda s: s > 0)
    return (annual * p).fillna(0.0)


def hidden_variation(vol, years, declared, rng):
    """Variant I: in the imputed years the truth's volumes vary between years as much as each
    facility's declared years do (log-normal factor with mean 1, per facility and year)."""
    out = vol.copy()
    annual = vol.groupby(vol.index.year).sum()
    dec = annual.loc[[y for y in annual.index if y in declared]]
    cv = (dec.std() / dec.mean().where(dec.mean() > 0)).fillna(0.0).clip(upper=1.0).to_numpy()
    for y in years:
        out.loc[out.index.year == y] *= np.exp(rng.normal(0.0, 1.0, len(cv)) * cv - cv ** 2 / 2)
    return out


def _convolve(S, w):
    """S (N, R, T + K - 1), w (N, R, K) lag-indexed kernels -> (N, R, T): causal convolution."""
    N, Rr, L = S.shape
    K = w.shape[-1]
    return Fn.conv1d(S.reshape(1, N * Rr, L), w.flip(-1).reshape(N * Rr, 1, K),
                     groups=N * Rr).reshape(N, Rr, L - K + 1)


def draw_parameters(group_of, n_groups, rng):
    """Per well: Gamma scale a (weeks) and shape n per truth stress, evaporation factor f. A group
    draws a mean lag (log-uniform in LAG_WEEKS) and a shape; a well deviates from them."""
    N = len(group_of)
    a, n = np.zeros((N, len(TRUTH))), np.zeros((N, len(TRUTH)))
    for r, s in enumerate(TRUTH):
        lo, hi = LAG_WEEKS[s]
        lag = np.exp(rng.uniform(np.log(lo), np.log(hi), n_groups))[group_of] * np.exp(rng.normal(0.0, WELL_SD, N))
        n[:, r] = np.clip(rng.uniform(*SHAPE, n_groups)[group_of] * np.exp(rng.normal(0, 0.1, N)), *SHAPE)
        a[:, r] = np.clip(lag / n[:, r], R.A_MIN * 1.01, R.A_MAX * 0.99)
    f = np.clip(rng.uniform(*F_RANGE, n_groups)[group_of] * np.exp(rng.normal(0, 0.1, N)), *F_RANGE)
    return a, n, f


def truth_contributions(X, a, n, f, K, variant=None, train=None, gain=None):
    """Unit-gain (or `gain`-scaled) contributions (N, 4, T) of the truth stresses from scaled,
    padded inputs X (the learner's kernels and recharge stress); variant "S" thresholds the
    recharge and delays the pumping response."""
    N = len(f)
    kern = R.ResponseModel(np.zeros(N, dtype=int), 1, "free", K).kernels(
        torch.as_tensor(a, dtype=torch.float32), torch.as_tensor(n, dtype=torch.float32))
    rch = X["rain"] - torch.as_tensor(f, dtype=torch.float32)[:, None] * X["ETP"]
    if variant == "S":
        q = torch.quantile(rch[:, K - 1:][:, torch.as_tensor(train)], THRESHOLD_Q, dim=1, keepdim=True)
        rch = torch.clamp(rch - q, min=0.0)
    S = torch.stack([rch, X["pump_gw"], X["river"], X["canal"]], dim=1)
    c = _convolve(S, kern).numpy().astype(np.float64)
    if variant == "S":                       # dead time: the pumping response arrives DEAD_WEEKS later
        r = TRUTH.index("pumping")
        c[:, r] = np.concatenate([np.repeat(c[:, r, :1], DEAD_WEEKS, 1), c[:, r, :-DEAD_WEEKS]], 1)
    return c if gain is None else c * gain[:, :, None]


def make_world(base, seed, eps=0.1, u=0.3, pi=0.3, nu=0.25, timing="reconstructed", variant=None):
    """One world (one seed, one cell of dials)."""
    codes, weeks, K, train = base["codes"], base["weeks"], base["K"], base["train"]
    truth_edges, rec = truth_graph(base, eps, u, seed, variant)
    d_edges = base["ed"]
    vol = base["vol"] if timing == "reconstructed" else calendar_volumes(base["vol"], train)
    vol_truth = vol
    if variant == "I":
        imp = imputed_years(weeks)
        declared = [y for y in np.unique(weeks.year[train]) if y not in imp]
        vol_truth = hidden_variation(vol, imp, declared, _gen(seed, "hidden"))
    route = lambda e, v: _route(base, edges=e, codes=codes, weeks=weeks, volumes=v)  # noqa: E731
    routed = {"truth": route(truth_edges, vol_truth), "C": route(base["ec"], vol), "D": route(d_edges, vol)}
    routed["T"] = routed["truth"] if vol_truth is vol else route(truth_edges, vol)
    edges = {"truth": truth_edges, "C": base["ec"], "D": d_edges, "T": truth_edges}
    data = R.panel_arrays(base["P"], K, routed["truth"])
    X = {k: torch.from_numpy(v) for k, v in data["X"].items()}
    group_of, groups = data["group_of"], data["groups"]
    a, n, f = draw_parameters(group_of, len(groups), _gen(seed, "params"))
    unit = truth_contributions(X, a, n, f, K, variant, train)             # (N, 4, T)
    sd_real = np.maximum(data["sd"][:, 0], R.SD_FLOOR)
    sd_unit = unit[:, :, train].std(-1)
    has = {"pumping": routed["truth"]["has_pumping"], "river": routed["truth"]["has_river"],
           "canal": routed["truth"]["has_canal"]}
    share = np.zeros((len(codes), len(TRUTH)))
    for s, v in (("pumping", pi), ("river", SHARE_RIVER), ("canal", SHARE_CANAL)):
        r = TRUTH.index(s)
        share[:, r] = np.where(has[s] & (sd_unit[:, r] > 0), v, 0.0)
    share[:, 0] = np.maximum(1.0 - share[:, 1:].sum(1), MIN_RECHARGE_SHARE)
    sign = np.array([SIGN[s] for s in TRUTH])
    gain = np.where(sd_unit > 0, sign * np.sqrt(share) * sd_real[:, None] / np.where(sd_unit > 0, sd_unit, 1.0), 0.0)
    contrib = unit * gain[:, :, None]                                     # metres
    clean = contrib.sum(1)
    omitted = np.zeros_like(clean)
    if variant == "O":
        in_g = group_of == groups.index(OMITTED_GROUP)
        rw = np.cumsum(_gen(seed, "omitted").normal(0, 1, len(weeks)))
        rw = (rw - rw[train].mean()) / rw[train].std()
        omitted[in_g] = (np.sqrt(OMITTED_SHARE) * clean[in_g][:, train].std(1))[:, None] * rw[None]
    signal = clean + omitted
    g = _gen(seed, "noise")
    phi = g.uniform(*AR_RANGE, len(codes))
    e = g.normal(0, 1, signal.shape)
    noise = np.zeros_like(signal)
    noise[:, 0] = e[:, 0] / np.sqrt(1 - phi ** 2)                     # stationary start
    for t in range(1, signal.shape[1]):
        noise[:, t] = phi * noise[:, t - 1] + e[:, t]
    noise *= (np.sqrt(nu) * signal[:, train].std(1) / noise[:, train].std(1))[:, None]
    level = data["mu"][:, :1] - signal[:, train].mean(1, keepdims=True)
    head = np.where(np.isfinite(data["head"]), level + signal + noise, np.nan)   # the real missing weeks
    core = data["core"][:, 0]
    var_pump = contrib[:, 1][:, train].var(1)
    with np.errstate(invalid="ignore", divide="ignore"):
        pi_real = np.where(share[:, 1] > 0, var_pump / signal[:, train].var(1), np.nan)
    if list(data["codes"]) != list(codes):
        raise ValueError("panel and draws in different well orders")
    rec["core"] = core
    rec["true_pumping"] = share[:, 1] > 0
    attributed = rec["v_attributed_true"] > 0
    realised = {"u_median_core": _nanmed(rec.loc[rec["core"] & attributed, "u_realised"]),
                "u_median_core_without_attributed": _nanmed(rec.loc[rec["core"] & ~attributed, "u_realised"]),
                "eps": float(rec["false_attributed"].sum() / max(rec["attributed"].sum(), 1)),
                "pi_explained_median_core": _nanmed(pi_real[core]),
                "core_with_true_pumping": int((core & (share[:, 1] > 0)).sum()),
                "core_with_attributed_pumping": int((core & (rec["attributed"].to_numpy() > 0)).sum()),
                "core_with_river": int((core & (share[:, 2] > 0)).sum()),
                "core_with_canal": int((core & (share[:, 3] > 0)).sum())}
    return {"seed": seed, "dials": {"eps": eps, "u": u, "pi": pi, "nu": nu, "timing": timing, "variant": variant},
            "codes": codes, "weeks": weeks, "split": data["split"], "core": core,
            "group_of": group_of, "groups": groups, "head": head, "clean": level + signal,
            "contrib": {s: contrib[:, r] for r, s in enumerate(TRUTH)}, "omitted": omitted, "noise": noise,
            "level": level[:, 0], "params": {"a": a, "n": n, "f": f, "gain": gain, "share": share, "phi": phi},
            "routed": routed, "edges": edges, "vol": vol, "vol_truth": vol_truth, "draws": rec,
            "realised": realised, "river_rule": base["river_rule"]}


def _nanmed(x):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    return float(np.median(x)) if len(x) else None


def learner_data(base, world, arm, volumes=None, routed=None):
    """The response model's data for one arm of a world: the synthetic heads with their own
    training mean and sd, the arm's routed inputs (or the same edges under other `volumes`, or
    `routed` inputs given directly)."""
    P = base["P"].copy()
    T = len(world["weeks"])
    P["head"] = world["head"].reshape(-1)
    obs = np.where(world["split"] == "train", world["head"], np.nan)
    P["mu"] = np.repeat(np.nanmean(obs, 1), T)
    P["sd"] = np.repeat(np.nanstd(obs, 1, ddof=1), T)
    if routed is None:
        routed = world["routed"][arm] if volumes is None else _route(
            world, edges=world["edges"][arm], codes=world["codes"], weeks=world["weeks"], volumes=volumes)
    return R.panel_arrays(P, base["K"], routed)


def fit(base, world, arm, mode="free", lam=0.0, starts=(0, 1), steps=4000, fixed_steps=None,
        signs="structure", soft=None):
    """Fit the rung-4 response model on one arm from each start (the real data's protocol:
    early stopping on the median validation NSE of the core wells unless `fixed_steps`); `signs`
    and `soft` are the RQ2 settings (hard = "structure", none, soft)."""
    data = learner_data(base, world, arm)
    X = {k: torch.from_numpy(v) for k, v in data["X"].items()}
    nets, preds, contribs, lags, best, stops, gains = [], [], [], [], [], [], []
    t0 = time.time()
    for s in starts:
        net, b, step = R.train_seed(s, data, mode, lam, steps, kernel_weeks=base["K"], pumping="arm",
                                    fixed_steps=fixed_steps, signs=signs, soft=soft, conv=CONV)
        with torch.no_grad():
            c = net.contributions(X).numpy().astype(np.float64)
            g, a, n, _ = (t.numpy() for t in net.parameters_physical())
        gains.append(g)
        preds.append(data["mu"][:, :1] + net.d.detach().numpy()[:, None] + c.sum(1))
        contribs.append(c)
        lags.append(a * n)
        nets.append(net)
        best.append(b)
        stops.append(int(step))
    return {"arm": arm, "nets": nets, "names": nets[0].names, "pred": np.mean(preds, 0),
            "contrib_starts": np.stack(contribs), "lag": np.mean(lags, 0), "val": float(np.mean(best)),
            "steps": stops, "seconds": round(time.time() - t0, 1), "gains": np.stack(gains),
            "states": [{k: v.detach().clone() for k, v in net.state_dict().items()} for net in nets]}


def predict(base, world, fitted, volumes=None, routed=None):
    """Mean prediction of a fitted arm under other facility volumes or other routed inputs (an
    intervention)."""
    data = learner_data(base, world, fitted["arm"], volumes, routed)
    X = {k: torch.from_numpy(v) for k, v in data["X"].items()}
    with torch.no_grad():
        return np.mean([data["mu"][:, :1] + net(X).numpy() for net in fitted["nets"]], 0)


def per_well_cut(world, arm, volumes, cut=CUT):
    """Score 5 as the plan defines it ("every true-edge facility of a well -20 % for the drought
    years"): the routed inputs of `arm` when, for each well separately, only that well's true
    pumping facilities are cut. The pumping inputs are weighted sums of facility volumes, so well
    i's input changes only through the pairs (facility, i) that the arm shares with the truth; all
    wells are done in one pass. Before 2026-11-20 score 5 cut the union of every well's true
    facilities at once (astra review point 1), which also moves a well's input through facilities
    that are true for other wells only; that version is kept as the "plain-wide" score."""
    tr = world["edges"]["truth"]
    tp = tr[tr["relation"] == "pumping"]
    true_pairs = set(zip(tp["src"], tp["dst"]))
    e = world["edges"][arm]
    pe = e[e["relation"].isin(("pumping", "pumping_unattributed"))]
    shared = pe[[(s, d) in true_pairs for s, d in zip(pe["src"], pe["dst"])]]
    routed = dict(world["routed"][arm] if volumes is world["vol"] else
                  _route(world, edges=e, codes=world["codes"], weeks=world["weeks"], volumes=volumes))
    fac = sorted(shared["src"].unique())
    if fac:
        dr = drought(world["weeks"]).astype(float)
        dvol = -cut * volumes.reindex(index=world["weeks"], columns=fac).fillna(0.0).to_numpy().T * dr[None, :]
        for name, rel in (("pump_gw", "pumping"), ("pump_un", "pumping_unattributed")):
            routed[name] = routed[name] + _matrix(shared, rel, world["codes"], fac) @ dvol
    return routed


def drought(weeks):
    a, b = TEST_PERIODS["test_drought"]
    return np.asarray((weeks >= a) & (weeks <= b))


def _centred(x, train):
    return x - x[..., train].mean(-1, keepdims=True)


def by_truth(c, names):
    """Fitted contributions (..., R, T) -> the truth's four stresses; pumping = attributed +
    unattributed."""
    i = {s: k for k, s in enumerate(names)}
    return {"recharge": c[..., i["recharge"], :],
            "pumping": c[..., i["pumping"], :] + c[..., i["pumping_unattributed"], :],
            "river": c[..., i["river"], :], "canal": c[..., i["canal"], :]}


def score(base, world, fits):
    """The scores of item 19 and its amendment for one world and learner setting (core wells
    with at least MIN_WEEKS synthetic heads in the drought phase). `fits`: arm -> fit()."""
    weeks, train = world["weeks"], base["train"]
    dr, core = drought(weeks), world["core"]
    obs = world["head"][:, dr]
    ok = core & (np.isfinite(obs).sum(1) >= MIN_WEEKS)
    sd = world["clean"][:, train].std(1)
    true_c = {s: _centred(world["contrib"][s], train)[:, dr] for s in TRUTH}
    lag_true = world["params"]["a"] * world["params"]["n"]
    out = {"wells": int(ok.sum())}
    per_well = {"code_bss": [c for c, k in zip(world["codes"], ok) if k]}
    rmse = {}
    for arm, f in fits.items():
        err = f["pred"][:, dr] - obs
        with warnings.catch_warnings():              # wells without a drought head: NaN, not scored
            warnings.simplefilter("ignore", RuntimeWarning)
            rmse[arm] = np.sqrt(np.nanmean(err ** 2, 1))
            nse = 1 - np.nanmean(err ** 2, 1) / np.nanvar(obs, 1)
        out[f"nse_drought_{arm}"], per_well[f"nse_drought_{arm}"] = _nanmed(nse[ok]), nse[ok]
        out[f"val_{arm}"], out[f"steps_{arm}"], out[f"seconds_{arm}"] = f["val"], f["steps"], f["seconds"]
        fitted = by_truth(f["contrib_starts"].mean(0), f["names"])
        for s in TRUTH:                                             # score 2: recovery
            e = np.sqrt(np.mean((_centred(fitted[s], train)[:, dr] - true_c[s]) ** 2, 1)) / sd
            out[f"recovery_{s}_{arm}"], per_well[f"recovery_{s}_{arm}"] = _nanmed(e[ok]), e[ok]
        tp, fp = true_c["pumping"], _centred(fitted["pumping"], train)[:, dr]
        has = ok & (tp.std(1) > 0)                                  # score 3: right pumping
        if has.any():
            ratio = fp.std(1)[has] / tp.std(1)[has]
            corr = np.array([np.corrcoef(fp[i], tp[i])[0, 1] if fp[i].std() > 0 else 0.0
                             for i in np.where(has)[0]])
            out[f"pumping_right_{arm}"] = float(np.mean((corr > 0) & (ratio > 0.5) & (ratio < 2.0)))
        else:
            out[f"pumping_right_{arm}"] = None
        has_in = np.stack([world["routed"][arm]["has_" + n] for n in f["names"]], 1)   # (N, R): the arm has it
        expected = np.array([R.SIGN[n] for n in f["names"]])
        wrong = (expected * f["gains"] < 0).mean(0)                 # RQ2: share of starts, per (well, stress)
        out[f"violation_rate_{arm}"] = float(wrong[ok][has_in[ok]].mean()) if has_in[ok].any() else None
        out[f"lag_error_recharge_wk_{arm}"] = _nanmed(                # score 4
            np.abs(f["lag"][:, f["names"].index("recharge")] - lag_true[:, 0])[ok])
        starts = [_centred(by_truth(c, f["names"])["pumping"], train)[:, dr] for c in f["contrib_starts"]]
        if len(starts) > 1:                                         # shortcut test 2
            dis = np.mean([np.sqrt(np.mean((p - q) ** 2, 1)) for p, q in itertools.combinations(starts, 2)], 0) / sd
            out[f"seed_disagreement_pumping_{arm}"] = _nanmed(dis[ok])
    for arm in fits:                                                # score 1
        if arm != "C" and "C" in fits:
            lr = np.log(rmse[arm] / rmse["C"])
            out[f"log_rmse_{arm}_over_C"], per_well[f"log_rmse_{arm}_over_C"] = _nanmed(lr[ok]), lr[ok]
    if "D" in fits and "T" in fits:
        out["log_rmse_D_over_T"] = _nanmed(np.log(rmse["D"] / rmse["T"])[ok])
    # score 5: the response to a -20 % cut of true-edge facilities in the drought, fitted against
    # the true head change. "well" (the plan's definition, the score of record): each well's own
    # true facilities, one well at a time; "plain" (descriptive, the only version before
    # 2026-11-20): the union of every well's true facilities cut at once, so an arm's links to
    # facilities that are true for other wells move its prediction too. The truth's head change is
    # the same for both: in the truth a well feels only its own true facilities.
    tr = world["edges"]["truth"]
    true_fac = sorted(set(tr.loc[tr["relation"] == "pumping", "src"]))
    cut, cut_truth = world["vol"].copy(), world["vol_truth"].copy()
    for v in (cut, cut_truth):
        v.loc[dr, [c for c in true_fac if c in v.columns]] *= 1 - CUT
    rt = _route(world, edges=tr, codes=world["codes"], weeks=weeks, volumes=cut_truth)
    Xt = {k: torch.from_numpy(v) for k, v in R.panel_arrays(base["P"], base["K"], rt)["X"].items()}
    p = world["params"]
    new = truth_contributions(Xt, p["a"], p["n"], p["f"], base["K"], world["dials"]["variant"], train, p["gain"])
    d_true = (new[:, 1] - world["contrib"]["pumping"])[:, dr].mean(1)
    has = ok & (np.abs(d_true) > 1e-6)
    out["true_pumping_wells"] = int(has.sum())
    for arm, f in fits.items():
        changes = {"plain": predict(base, world, f, volumes=cut),
                   "well": predict(base, world, f, routed=per_well_cut(world, arm, world["vol"]))}
        for kind, pred_cut in changes.items():
            d_fit = (pred_cut - f["pred"])[:, dr].mean(1)
            if has.any():
                out[f"intervention_{kind}_rel_error_{arm}"] = _nanmed(np.abs(d_fit[has] - d_true[has]) / np.abs(d_true[has]))
                out[f"intervention_{kind}_sign_{arm}"] = float(np.mean(np.sign(d_fit[has]) == np.sign(d_true[has])))
            else:
                out[f"intervention_{kind}_rel_error_{arm}"] = out[f"intervention_{kind}_sign_{arm}"] = None
    return out, {k: _jsonable(v) for k, v in per_well.items()}


def _jsonable(v):
    if isinstance(v, np.ndarray):
        return [None if isinstance(x, float) and not np.isfinite(x) else x for x in v.tolist()]
    return v


def cell_tag(d):
    v = d["variant"] or "base"
    return f"e{d['eps']:g}_u{d['u']:g}_p{d['pi']:g}_n{d['nu']:g}_{d['timing'][:3]}_{v}"


def parse_fit(spec):
    """"free", "pooled:0.01", "pooled:0.1:3000" (λ, then a fixed number of steps), each with an
    optional RQ2 setting: "+none" (free gains) or "+soft<λ_s>" (free gains and the soft penalty);
    the default is hard (signs by construction). -> key, mode, λ, fixed steps, signs, soft."""
    spec, _, rq2 = spec.partition("+")
    parts = spec.split(":")
    mode = parts[0]
    lam = float(parts[1]) if len(parts) > 1 and parts[1] else 0.0
    fixed = int(parts[2]) if len(parts) > 2 else None
    if mode not in ("free", "pooled", "shared") or (mode == "pooled" and lam <= 0):
        raise ValueError(spec)
    if rq2 in ("", "hard"):
        signs, soft = "structure", None
    elif rq2 == "none":
        signs, soft = "none", None
    elif rq2.startswith("soft") and float(rq2[4:]) > 0:
        signs, soft = "none", float(rq2[4:])
    else:
        raise ValueError(spec)
    key = (mode + (f"_l{lam:g}" if mode == "pooled" else "") + (f"_fixed{fixed}" if fixed else "")
           + ("" if signs == "structure" else f"_soft{soft:g}" if soft else "_none"))
    return key, mode, lam, fixed, signs, soft


# What makes two worlds of a cell comparable: the same generator settings, inputs and fits. A world
# file whose saved config differs in any of these is never reused nor mixed with new worlds (astra
# review point 10, 2026-11-20); the code version is recorded per world, not compared (a scoring fix
# does not change the fits).
IDENTITY = ("dials", "fits", "arms", "starts", "steps", "export_release", "policy", "kernel_weeks", "conv")
OPTIONAL = ("river_rule", "inputs_sha256")      # recorded from 2026-11-20: compared when both have them
# 1: score 5 cut the union of the true facilities only ("intervention_*"); 2 (2026-11-20): score 5
# per well ("intervention_well_*", the plan's definition) and plain-wide ("intervention_plain_*"),
# and the fitted weights saved beside each world (world_<k>_nets.pt).
SCORES_VERSION = 2


def identity(config):
    out = {k: json.loads(json.dumps(config.get(k), default=float)) for k in IDENTITY}
    out.update({k: config[k] for k in OPTIONAL if config.get(k) is not None})
    return out


def identity_diff(config_a, config_b):
    """The identity keys on which two world configs differ (OPTIONAL keys only when both have
    them)."""
    a, b = identity(config_a), identity(config_b)
    return [k for k in IDENTITY if a[k] != b[k]] + [k for k in OPTIONAL if k in a and k in b and a[k] != b[k]]


def check_identity(path, config):
    """Stop if the world file at `path` was made with settings other than `config`'s."""
    old = json.loads(path.read_text()).get("config", {})
    a, b = identity(old), identity(config)
    diff = identity_diff(old, config)
    if diff:
        raise SystemExit(f"{path} was made with other settings ({', '.join(diff)}: saved "
                         f"{ {k: a[k] for k in diff} }, now { {k: b[k] for k in diff} }); use another --run")


def run_cell(base, dials, worlds, run, fits=("free",), starts=(0, 1), steps=4000, arms=ARMS):
    out = RESULTS / run / cell_tag(dials)
    out.mkdir(parents=True, exist_ok=True)
    config = {"dials": dials, "fits": list(fits), "arms": list(arms), "starts": list(starts),
              "steps": steps, "export_release": base["export"], "policy": base["policy"],
              "kernel_weeks": base["K"], "conv": CONV, "river_rule": base["river_rule"],
              "inputs_sha256": base["inputs_sha256"], "design": "docs/analysis_plan.md §14 item 19 (+ 2026-11-16)"}
    done = [int(f.stem.split("_")[1]) for f in out.glob("world_*.json")]
    for f in sorted(out.glob("world_*.json")):          # every world already in the cell
        check_identity(f, config)
    for w in worlds:
        path = out / f"world_{w}.json"
        if path.exists():
            check_identity(path, config)
            continue
        world = make_world(base, w, **dials)
        rec = {"world": w, "dials": dials, "realised": world["realised"], "fits": {}, "per_well": {},
               "config": config, "src_sha256": code_version()["src_sha256"], "scores_version": SCORES_VERSION}
        states = {}
        for spec in fits:
            key, mode, lam, fixed, signs, soft = parse_fit(spec)
            fitted = {arm: fit(base, world, arm, mode, lam, starts, steps, fixed, signs, soft) for arm in arms}
            rec["fits"][key], rec["per_well"][key] = score(base, world, fitted)
            states[key] = {arm: f["states"] for arm, f in fitted.items()}
            s = rec["fits"][key]
            num = lambda x, f="+.3f": "—" if x is None else format(x, f)  # noqa: E731
            print(f"  {cell_tag(dials)} world {w} {key}: log RMSE D/C {num(s.get('log_rmse_D_over_C'))}, "
                  f"T/C {num(s.get('log_rmse_T_over_C'))}; pumping recovery "
                  + " ".join(f"{a} {num(s[f'recovery_pumping_{a}'], '.2f')}" for a in arms), flush=True)
        nets, tmp_nets = out / f"world_{w}_nets.pt", out / f"world_{w}_nets.pt.tmp"
        torch.save({"world": w, "starts": list(starts), "states": states}, tmp_nets)
        tmp_nets.replace(nets)                        # the fitted weights: scores can be recomputed
        tmp = path.with_suffix(".tmp")                # the world file last: it marks the world done
        tmp.write_text(json.dumps(rec, indent=1, default=float))
        tmp.replace(path)
        done.append(w)
        write_manifest(out, config, sorted(set(done)))


def parse_worlds(items):
    out = []
    for it in items:
        a, _, b = it.partition("-")
        out += list(range(int(a), int(b) + 1)) if b else [int(a)]
    return out


def cells(args):
    if args.grid:
        return [dict(BASE, eps=e, u=u) for e in GRID["eps"] for u in GRID["u"]]
    if args.slices:
        return [dict(BASE, **s) for s in SLICES]
    return [{"eps": args.eps, "u": args.u, "pi": args.pi, "nu": args.nu, "timing": args.timing,
             "variant": args.variant}]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--worlds", nargs="+", default=["0"])
    ap.add_argument("--grid", action="store_true", help="the eps x u grid of item 19 at the base dials")
    ap.add_argument("--slices", action="store_true", help="the slices of item 19 from the base cell")
    ap.add_argument("--eps", type=float, default=BASE["eps"])
    ap.add_argument("--u", type=float, default=BASE["u"])
    ap.add_argument("--pi", type=float, default=BASE["pi"])
    ap.add_argument("--nu", type=float, default=BASE["nu"])
    ap.add_argument("--timing", choices=["reconstructed", "independent"], default=BASE["timing"])
    ap.add_argument("--variant", choices=["I", "O", "S", "G"], default=None)
    ap.add_argument("--fits", nargs="+", default=["free", "pooled:0.01"],
                    help="learner settings: free, pooled:<λ>, pooled:<λ>:<fixed steps>, each with "
                         "an optional +none or +soft<λ_s> (RQ2; default hard)")
    ap.add_argument("--arms", nargs="+", choices=ARMS, default=list(ARMS))
    ap.add_argument("--starts", type=int, nargs="+", default=[0, 1])
    ap.add_argument("--steps", type=int, default=4000)
    args = ap.parse_args()
    for spec in args.fits:
        parse_fit(spec)
    torch.set_num_threads(int(os.environ.get("PFE_THREADS", 4)))
    base = load_base()
    for w in parse_worlds(args.worlds):      # worlds outside, cells inside: a session cut short still
        for d in cells(args):                # leaves every cell of the map with the same worlds
            run_cell(base, d, [w], args.run, tuple(args.fits), tuple(args.starts), args.steps,
                     tuple(args.arms))


if __name__ == "__main__":
    main()
