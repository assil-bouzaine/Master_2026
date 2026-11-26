"""Unit tests for Hybrid-GNN v2 (src/models/hybrid_gnn.py, analysis plan v3 §3 and §7).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v5 .venv/bin/python -m tests.test_hybrid_gnn

No real-data training happens here: at most 5 optimisation steps are run on a single
3-well toy problem.

Checks:
1. Finite-difference sign test (plan v3 §7): random parameters and stresses with the bounded
   residual row active; 200 perturbations per signed stress (rain and ETP for every recharge
   channel, pumping, unattributed pumping, constrained river, constrained canal) with centres
   held fixed -> 0 violations; slow kernel shape n_slow >= 1; |rho| <= 0.20 * sd.
2. Centring: under observed forcing, mean of y_hat_i over each well's observed training weeks
   is 0 (< 1e-6), including a held-out well (delta = 0); counterfactual forward passes leave
   the stored centres buffer unchanged; inactive channels have strictly zero stress and
   contribution (no initial bucket-storage leak).
3. Pumping reliability (plan v3 §3.6): gradient of a loss restricted to weeks before
   RELIABLE_PUMPING_FROM ("2012-01-01") with respect to pumping gains and kernels is exactly
   0, while gradient with respect to recharge gains is non-zero; post-2012 loss produces
   non-zero pumping gradients; a probe loss linear in the post-2012 predictions has the same
   pumping gradients when every imputed pumping week is multiplied by 100 (no path through the
   centres or the kernel's memory: docs/v5_bugs_to_fix.md item 1); training values = inference values.
4. Stage A has no delta parameter; stage B = the stage-A fit followed by a delta-only refinement
   (its first phase equals a stage-A run, every parameter but delta is unchanged after it, the
   held-out well's predictions equal stage A's: docs/v5_bugs_to_fix.md item 4); a held-out
   well's delta stays identically 0.
5. Replay: save checkpoint + outputs, reload into a fresh HybridGNN (restoring centres buffer
   without re-estimating), predict on observed and counterfactual forcings -> identical to
   < 1e-5 m; exact additive decomposition of saved centred contributions.
6. Tiny fit (5 steps, 3 wells, toy data): loss decreases; CLI refuses to train without
   PFE_ALLOW_TRAIN=1; RQ2 --signs none and --soft penalty match hand calculation.
7. Encoder never sees a stress: forward pre-hook proves only static HeteroData tensors
   (x, edge_index, edge_attr) reach HeteroEncoder, and perturbing stresses leaves encoder
   output and physical parameters bit-for-bit unchanged; zero-training real v5 forward pass
   (arms C and D, K = 416, basin canals) checks shapes, alignment, masking, and centring, and that
   pumping before the pumping record (1990-2002) is the well's training mean, not 0.
"""
from __future__ import annotations

import io
import json
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch_geometric.data import HeteroData

from src.models import hybrid_gnn as H
from src.models import response as R
from src.models.lstm import save_seed, save_seed_model, write_config
from src.models.manifest import load_checkpoint


# ---------------------------------------------------------------------------
# Toy fixtures
# ---------------------------------------------------------------------------

def _toy_graph(n_wells=4, seed=0):
    """Small static HeteroData with wells, facilities, weather cells, gauges, and canals."""
    rng = np.random.default_rng(seed)
    data = HeteroData()
    data["well"].x = torch.from_numpy(rng.normal(0.0, 1.0, (n_wells, 6)).astype(np.float32))
    data["facility"].x = torch.from_numpy(rng.normal(0.0, 1.0, (3, 4)).astype(np.float32))
    data["weather_cell"].x = torch.from_numpy(rng.normal(0.0, 1.0, (2, 3)).astype(np.float32))
    data["gauge"].x = torch.from_numpy(rng.normal(0.0, 1.0, (2, 1)).astype(np.float32))
    data["canal"].x = torch.from_numpy(rng.normal(0.0, 1.0, (1, 1)).astype(np.float32))

    # Edges (forward + reverse, matching hetero_graph.py convention)
    edge_specs = [
        ("weather_cell", "recharge", "well", [[0, 1, 0, 1][:n_wells], list(range(n_wells))]),
        ("facility", "pumping", "well", [[0, 1, 2, 0][:n_wells], list(range(n_wells))]),
        ("gauge", "river", "well", [[0, 1, 0, 1][:n_wells], list(range(n_wells))]),
        ("canal", "canal", "well", [[0] * n_wells, list(range(n_wells))]),
        ("well", "well_link", "well", [[0, 1], [1, 0]] if n_wells >= 2 else [[0], [0]]),
    ]
    for st, rel, dt, ei_list in edge_specs:
        ei = torch.tensor(ei_list, dtype=torch.long)
        ea = torch.from_numpy(rng.uniform(0.1, 1.0, (ei.shape[1], 5)).astype(np.float32))
        data[(st, rel, dt)].edge_index = ei
        data[(st, rel, dt)].edge_attr = ea
        data[(dt, f"rev_{rel}", st)].edge_index = ei.flip(0).contiguous()
        data[(dt, f"rev_{rel}", st)].edge_attr = ea.clone()
    return data


def _toy_stresses(N=4, T=48, K=24, seed=0):
    """Positive toy stresses (N, T + K - 1) in HybridGNN's expected units."""
    rng = np.random.default_rng(seed)
    L = T + K - 1
    X = {}
    for ch in H.RECHARGE_CHANNELS:
        # Include dry weeks (rain = 0) and storms (mm/week) to hit all bucket regimes.
        rain = np.where(rng.random((N, L)) < 0.3, 0.0, rng.gamma(0.6, 20.0, (N, L)))
        etp = 2.0 + rng.gamma(2.0, 12.0, (N, L))
        X[f"rain_{ch}"] = rain.astype(np.float32)
        X[f"ETP_{ch}"] = etp.astype(np.float32)
    X["pump_gw"] = rng.gamma(2.0, 0.4, (N, L)).astype(np.float32)
    X["pump_un"] = rng.gamma(2.0, 0.3, (N, L)).astype(np.float32)
    riv = (0.5 + rng.random((N, L))).astype(np.float32)
    can = rng.gamma(1.5, 0.4, (N, L)).astype(np.float32)
    # Well 0 and 2 are river_c; well 1 and 3 are free river.
    # Well 0 is canal_c; wells 1..3 are free canal.
    river_c_mask = np.array([i % 2 == 0 for i in range(N)], dtype=bool)
    canal_c_mask = np.array([i == 0 for i in range(N)], dtype=bool)
    X["river_c"] = np.where(river_c_mask[:, None], riv, 0.0).astype(np.float32)
    X["river"] = np.where(river_c_mask[:, None], 0.0, riv).astype(np.float32)
    X["canal_c"] = np.where(canal_c_mask[:, None], can, 0.0).astype(np.float32)
    X["canal"] = np.where(canal_c_mask[:, None], 0.0, can).astype(np.float32)
    return X, river_c_mask, canal_c_mask


def _to_torch(X):
    return {k: torch.from_numpy(v.copy()) for k, v in X.items()}


def _randomise_net(net, seed=7, spread=2.0):
    """Randomise group means, encoder output head, delta, and residual MLP weights."""
    g = torch.Generator().manual_seed(seed)
    with torch.no_grad():
        net.theta_group.normal_(0.0, spread, generator=g)
        net.encoder.head.weight.normal_(0.0, 0.5, generator=g)
        net.encoder.head.bias.normal_(0.0, 0.3, generator=g)
        if net.delta is not None:
            net.delta.normal_(0.0, spread * 0.5, generator=g)
        if net.residual_mlp is not None:
            for p in net.residual_mlp.parameters():
                p.normal_(0.0, 0.8, generator=g)


def _graph_to_dtype(graph, dtype):
    """Copy a HeteroData casting only floating tensors (x, edge_attr) to `dtype`."""
    g = graph.clone()
    for nt in g.node_types:
        g[nt].x = g[nt].x.to(dtype)
    for et in g.edge_types:
        g[et].edge_attr = g[et].edge_attr.to(dtype)
    return g


# ---------------------------------------------------------------------------
# 1. Finite-difference sign test (plan v3 §7)
# ---------------------------------------------------------------------------

def test_finite_difference_signs():
    torch.manual_seed(10)
    N, T, K = 4, 48, 24
    L = T + K - 1
    weeks = pd.date_range("2010-01-03", periods=T, freq="W-SUN")
    graph = _toy_graph(N, seed=11)
    X_np, river_c_mask, canal_c_mask = _toy_stresses(N, T, K, seed=12)
    sd = np.linspace(0.4, 2.0, N).astype(np.float32)

    # All channels active where their slot applies; leave one well (well 3) without leakage to also
    # test inactive channel invariance inside the same model.
    ch_mask = np.ones((N, H.N_CHANNELS), dtype=bool)
    ch_mask[:, H.CHANNELS.index("river_c")] = river_c_mask
    ch_mask[:, H.CHANNELS.index("river")] = ~river_c_mask
    ch_mask[:, H.CHANNELS.index("canal_c")] = canal_c_mask
    ch_mask[:, H.CHANNELS.index("canal")] = ~canal_c_mask
    ch_mask[3, H.CHANNELS.index("recharge_leakage")] = False

    res_basis = R.seasonal_basis(weeks, harmonics=H.RESIDUAL_HARMONICS)
    res_bound = H.RESIDUAL_BOUND_SD * sd
    net = H.HybridGNN(
        graph_data=graph,
        group_of=np.arange(N) % 2,
        n_groups=2,
        gain_scale=sd,
        channel_mask=ch_mask,
        stage="B",
        signs="gate3",
        kernel_weeks=K,
        residual="bounded",
        residual_basis=res_basis,
        residual_bound=res_bound,
    )
    _randomise_net(net, seed=13, spread=2.0)
    # Run the 200-perturbation-per-stress finite-difference check in float64 (tol = 1e-9, matching
    # tests/test_bucket.py) to separate exact sign monotonicity from float32 FFT rounding noise.
    net = net.double()
    net.graph_data = _graph_to_dtype(graph, torch.float64)
    net.eval()

    # Check slow kernel shape bound n_slow >= 1 and residual bound |rho| <= 0.2 * sd.
    with torch.no_grad():
        params = net.parameters_physical()
        assert float(params.n_slow.min()) >= 1.0, f"n_slow < 1: {params.n_slow.min()}"
        res = net.residual()
        assert res is not None and float(res.abs().max()) > 1e-3, "residual must be active and non-zero"
        assert (res.abs() <= torch.from_numpy(res_bound.astype(np.float64))[:, None] + 1e-12).all()

    X_base = {k: torch.from_numpy(v.astype(np.float64)) for k, v in X_np.items()}
    obs_mask = torch.zeros((N, T), dtype=torch.bool)
    obs_mask[:, :30] = True
    centres_before = net.estimate_centres(X_base, obs_mask)

    with torch.no_grad():
        y_base = net(X_base).numpy()

    rng = np.random.default_rng(14)
    n_perturb = 200
    tol = 1e-9

    # Every signed stress channel: (label, X_key, expected_sign, affected_wells_slice, delta_range)
    specs = [
        ("rain_local", "rain_recharge_local", +1.0, np.arange(N), (0.5, 40.0)),
        ("rain_regional", "rain_recharge_regional", +1.0, np.arange(N), (0.5, 40.0)),
        ("rain_leakage", "rain_recharge_leakage", +1.0, np.array([0, 1, 2]), (0.5, 40.0)),
        ("ETP_local", "ETP_recharge_local", -1.0, np.arange(N), (0.5, 25.0)),
        ("ETP_regional", "ETP_recharge_regional", -1.0, np.arange(N), (0.5, 25.0)),
        ("ETP_leakage", "ETP_recharge_leakage", -1.0, np.array([0, 1, 2]), (0.5, 25.0)),
        ("pumping", "pump_gw", -1.0, np.arange(N), (0.1, 3.0)),
        ("pumping_unattributed", "pump_un", -1.0, np.arange(N), (0.1, 3.0)),
        ("river_c", "river_c", +1.0, np.where(river_c_mask)[0], (0.1, 3.0)),
        ("canal_c", "canal_c", +1.0, np.where(canal_c_mask)[0], (0.1, 3.0)),
    ]

    counts = {}
    worst_margin = float("inf")
    for label, key, sign, wells_idx, (lo, hi) in specs:
        violations = 0
        any_effect = False
        for _ in range(n_perturb):
            t0 = int(rng.integers(0, L))
            delta_val = float(rng.uniform(lo, hi))
            X_pert = {k: v.clone() for k, v in X_base.items()}
            X_pert[key][:, t0] += delta_val
            with torch.no_grad():
                y_pert = net(X_pert).numpy()
            dy = y_pert[wells_idx] - y_base[wells_idx]
            signed = sign * dy
            worst_margin = min(worst_margin, float(signed.min()))
            if float(signed.min()) < -tol:
                violations += 1
            if float(signed.max()) > 1e-7:
                any_effect = True
            # Inactive well 3 for leakage must stay completely unaffected.
            if key.endswith("leakage"):
                assert float(np.abs(y_pert[3] - y_base[3]).max()) == 0.0
        assert violations == 0, f"{label}: {violations}/{n_perturb} sign violations"
        assert any_effect, f"{label}: perturbations produced zero effect"
        counts[label] = (violations, n_perturb)

    # Centres buffer must remain untouched across all counterfactual passes.
    assert torch.equal(net.centres, centres_before)

    # Free river and free canal channels may have negative gains and lower y_hat.
    with torch.no_grad():
        net.theta_group[:, H.CHANNELS.index("river")] = -2.0
        net.delta[:, H.CHANNELS.index("river")] = 0.0
        net.encoder.head.weight[H.CHANNELS.index("river")] = 0.0
        net.encoder.head.bias[H.CHANNELS.index("river")] = 0.0
        y_b2 = net(X_base).numpy()
        X_r = {k: v.clone() for k, v in X_base.items()}
        X_r["river"][:, K:] += 2.0
        y_r2 = net(X_r).numpy()
        assert float((y_r2[~river_c_mask] - y_b2[~river_c_mask]).min()) < -1e-4

    summary = ", ".join(f"{k}={v}/{n}" for k, (v, n) in counts.items())
    print(f"  1. finite-difference signs (residual ON, centres fixed, n_slow>=1): "
          f"0 violations across {len(specs) * n_perturb} perturbations [{summary}]; "
          f"worst signed delta {worst_margin:+.2e}")


# ---------------------------------------------------------------------------
# 2. Centring (observed forcing & held-out well)
# ---------------------------------------------------------------------------

def test_centring():
    torch.manual_seed(20)
    N, T, K = 4, 60, 24
    graph = _toy_graph(N, seed=21)
    X_np, river_c_mask, canal_c_mask = _toy_stresses(N, T, K, seed=22)
    sd = np.array([0.5, 1.0, 1.5, 0.8], dtype=np.float32)

    # Well 3 is held out (LWO: train_well_mask[3] = False) and also lacks recharge_leakage & canal.
    train_well_mask = np.array([True, True, True, False], dtype=bool)
    ch_mask = np.ones((N, H.N_CHANNELS), dtype=bool)
    ch_mask[:, H.CHANNELS.index("river_c")] = river_c_mask
    ch_mask[:, H.CHANNELS.index("river")] = ~river_c_mask
    ch_mask[:, H.CHANNELS.index("canal_c")] = canal_c_mask
    ch_mask[:, H.CHANNELS.index("canal")] = ~canal_c_mask
    ch_mask[3, H.CHANNELS.index("recharge_leakage")] = False
    ch_mask[3, H.CHANNELS.index("canal")] = False

    net = H.HybridGNN(
        graph_data=graph,
        group_of=np.array([0, 0, 1, 1]),
        n_groups=2,
        gain_scale=sd,
        channel_mask=ch_mask,
        stage="B",
        signs="gate3",
        kernel_weeks=K,
        train_well_mask=train_well_mask,
    )
    _randomise_net(net, seed=23, spread=1.0)
    # Zero out held-out well's raw delta explicitly (as during training); effective_delta is 0 anyway.
    with torch.no_grad():
        net.delta[3].zero_()
    net.eval()

    # Verify there is no free intercept parameter.
    param_names = set(dict(net.named_parameters()).keys())
    assert "d" not in param_names and "intercept" not in param_names

    # Different observed-training masks per well (with gaps).
    rng = np.random.default_rng(24)
    obs_mask = torch.zeros((N, T), dtype=torch.bool)
    for i in range(N):
        obs_mask[i, :40] = torch.from_numpy(rng.random(40) > 0.2)
        obs_mask[i, 0] = True

    X_obs = _to_torch(X_np)
    net.estimate_centres(X_obs, obs_mask)

    with torch.no_grad():
        c = net.contributions(X_obs)
        yhat = net(X_obs)

    # Inactive channels (including inactive recharge_leakage despite s0 = s_max/2) must be identically 0.
    leak_idx = H.CHANNELS.index("recharge_leakage")
    can_idx = H.CHANNELS.index("canal")
    assert float(c[3, leak_idx].abs().max()) == 0.0
    assert float(net.centres[3, leak_idx].abs()) == 0.0
    assert float(c[3, can_idx].abs().max()) == 0.0
    assert float(net.centres[3, can_idx].abs()) == 0.0

    # Mean of y_hat over each well's observed training weeks is 0 (< 1e-6), including held-out well 3.
    max_mean_err = 0.0
    for i in range(N):
        m_i = float(yhat[i, obs_mask[i]].mean().item())
        max_mean_err = max(max_mean_err, abs(m_i))
        assert abs(m_i) < 1e-6, f"well {i} (held_out={not train_well_mask[i]}): mean={m_i}"

    # Counterfactual forward pass must NOT modify stored centres.
    saved_centres = net.centres.clone()
    X_cf = {k: v.clone() for k, v in X_obs.items()}
    X_cf["rain_recharge_local"] += 15.0
    with torch.no_grad():
        y_cf = net(X_cf)
    assert torch.equal(net.centres, saved_centres)
    assert float((y_cf - yhat).mean()) > 0.0

    print(f"  2. centring: max |mean_train(y_hat)| = {max_mean_err:.2e} (< 1e-6) across trained and "
          f"held-out wells; counterfactual keeps centres fixed; inactive recharge bucket = 0")


# ---------------------------------------------------------------------------
# 3. Pumping reliability (pre-2012 detached pumping parameters)
# ---------------------------------------------------------------------------

def test_pumping_reliability():
    torch.manual_seed(30)
    assert H.RELIABLE_PUMPING_FROM == "2012-01-01"
    N, K = 3, 16
    weeks = pd.date_range("2010-01-03", "2013-12-29", freq="W-SUN")
    T = len(weeks)
    reliable_mask = torch.from_numpy(np.asarray(weeks >= pd.Timestamp(H.RELIABLE_PUMPING_FROM), dtype=bool))
    assert (~reliable_mask).any() and reliable_mask.any()

    graph = _toy_graph(N, seed=31)
    X_np, _, _ = _toy_stresses(N, T, K, seed=32)
    X_t = _to_torch(X_np)
    rng = np.random.default_rng(33)
    y_target = torch.from_numpy(rng.normal(0.0, 1.0, (N, T)).astype(np.float32))
    obs_train = torch.ones((N, T), dtype=torch.bool)

    net = H.HybridGNN(
        graph_data=graph,
        group_of=np.zeros(N, dtype=np.int64),
        n_groups=1,
        gain_scale=np.ones(N, dtype=np.float32),
        stage="B",
        signs="gate3",
        kernel_weeks=K,
        dropout=0.0,
    )
    _randomise_net(net, seed=34, spread=0.5)
    net.train()

    # 3a. Loss strictly on pre-2012 weeks: pumping gain & kernel gradients MUST be exactly 0;
    # recharge gain gradient MUST be non-zero.
    pred, _, _, _ = net.training_forward(X_t, obs_train, reliable_mask)
    pre_w = (~reliable_mask).to(torch.float32)[None, :]
    loss_pre = (pre_w * (pred - y_target) ** 2).mean()
    net.zero_grad()
    loss_pre.backward()

    p_idx = H.CHANNELS.index("pumping")
    pu_idx = H.CHANNELS.index("pumping_unattributed")
    rl_idx = H.CHANNELS.index("recharge_local")

    def _kernel_slice(ch_idx):
        s = H.N_CHANNELS + ch_idx * H.N_KERNEL_PARAMS
        return slice(s, s + H.N_KERNEL_PARAMS)

    for pname, param in (("theta_group", net.theta_group), ("delta", net.delta)):
        assert param.grad is not None
        assert float(param.grad[:, p_idx].abs().max()) == 0.0, f"{pname} pumping gain grad != 0"
        assert float(param.grad[:, pu_idx].abs().max()) == 0.0, f"{pname} pump_un gain grad != 0"
        assert float(param.grad[:, _kernel_slice(p_idx)].abs().max()) == 0.0, f"{pname} pumping kernel grad != 0"
        assert float(param.grad[:, _kernel_slice(pu_idx)].abs().max()) == 0.0, f"{pname} pump_un kernel grad != 0"
        assert float(param.grad[:, rl_idx].abs().max()) > 1e-6, f"{pname} recharge gain grad unexpectedly 0"

    pre_rch_grad = float(net.theta_group.grad[:, rl_idx].abs().max())

    # 3b. Loss on post-2012 weeks: pumping gain gradient MUST be non-zero.
    pred2, _, _, _ = net.training_forward(X_t, obs_train, reliable_mask)
    post_w = reliable_mask.to(torch.float32)[None, :]
    loss_post = (post_w * (pred2 - y_target) ** 2).mean()
    net.zero_grad()
    loss_post.backward()
    post_pump_grad = float(net.theta_group.grad[:, p_idx].abs().max())
    post_pu_grad = float(net.theta_group.grad[:, pu_idx].abs().max())
    assert post_pump_grad > 1e-6 and post_pu_grad > 1e-6

    # 3c. No path from imputed pumping to a pumping parameter (docs/v5_bugs_to_fix.md item 1). A probe
    # loss that is linear in the predictions on declared weeks has a gradient that depends on imputed
    # pumping only through gradient paths (no residual-value effect): multiplying every imputed
    # pumping week (warm-up and pre-2012) by 100 must leave the pumping gradients unchanged. The first
    # version leaked through the training-mean centres and through the kernel's memory after 2012.
    net64 = net.double()
    net64.graph_data = _graph_to_dtype(graph, torch.float64)
    probe = torch.from_numpy(rng.normal(0.0, 1.0, (N, T))) * reliable_mask.to(torch.float64)[None, :]
    first = int(np.argmax(reliable_mask.numpy()))

    def _probe_grads(scale):
        X = {k: torch.from_numpy(v.astype(np.float64)) for k, v in X_np.items()}
        for key in ("pump_gw", "pump_un"):
            X[key] = X[key].clone()
            X[key][:, : K - 1 + first] *= scale
        net64.zero_grad()
        pred_p, _, _, _ = net64.training_forward(X, obs_train, reliable_mask)
        (probe * pred_p).sum().backward()
        grads = {}
        for pname, param in (("theta_group", net64.theta_group), ("delta", net64.delta)):
            for ch_idx in (p_idx, pu_idx):
                grads[(pname, ch_idx, "gain")] = param.grad[:, ch_idx].clone()
                grads[(pname, ch_idx, "kernel")] = param.grad[:, _kernel_slice(ch_idx)].clone()
        enc_grad = torch.cat([q.grad.reshape(-1) for q in net64.encoder.head.parameters()])
        return grads, enc_grad, pred_p.detach()

    g1, enc1, pred1 = _probe_grads(1.0)
    g100, enc100, pred100 = _probe_grads(100.0)
    leak = max(float((g1[k] - g100[k]).abs().max()) for k in g1)
    size = max(float(g1[k].abs().max()) for k in g1)
    assert size > 1e-6, "declared pumping must still train the pumping parameters"
    assert leak <= 1e-10 * max(1.0, size), f"imputed pumping reaches a pumping parameter: {leak:.3e}"
    assert float((pred1 - pred100).abs().max()) > 1e-3, "the imputed values must still enter the predictions"

    # 3d. Values unchanged: the training pass equals the inference pass (centres from estimate_centres).
    X64 = {k: torch.from_numpy(v.astype(np.float64)) for k, v in X_np.items()}
    with torch.no_grad():
        pred_train, _, _, _ = net64.training_forward(X64, obs_train, reliable_mask)
        net64.estimate_centres(X64, obs_train)
        pred_inf = net64(X64)
    value_err = float((pred_train - pred_inf).abs().max())
    assert value_err < 1e-9, value_err

    print(f"  3. pumping reliability ({H.RELIABLE_PUMPING_FROM}): pre-2012 pumping & pump_un gain/kernel "
          f"grads = 0.0 exactly, recharge grad = {pre_rch_grad:.3e}; post-2012 pumping grad = {post_pump_grad:.3e}; "
          f"imputed pumping x100 moves no pumping gradient (max change {leak:.1e} vs size {size:.2e}); "
          f"training values = inference values ({value_err:.1e})")


# ---------------------------------------------------------------------------
# 4 & 6. Stage A vs Stage B held-out delta + 5-step 3-well toy fit + CLI guard + RQ2 soft
# ---------------------------------------------------------------------------

def test_stages_tiny_fit_and_guards():
    N, T, K = 3, 60, 16
    weeks = pd.date_range("2011-01-02", periods=T, freq="W-SUN")
    graph = _toy_graph(N, seed=41)
    X_np, river_c_mask, canal_c_mask = _toy_stresses(N, T, K, seed=42)
    ch_mask = np.ones((N, H.N_CHANNELS), dtype=bool)
    ch_mask[:, H.CHANNELS.index("river_c")] = river_c_mask
    ch_mask[:, H.CHANNELS.index("river")] = ~river_c_mask
    ch_mask[:, H.CHANNELS.index("canal_c")] = canal_c_mask
    ch_mask[:, H.CHANNELS.index("canal")] = ~canal_c_mask

    # 4a. Stage A has NO delta parameter at all.
    net_a = H.HybridGNN(
        graph_data=graph,
        group_of=np.zeros(N, dtype=np.int64),
        n_groups=1,
        gain_scale=np.ones(N, dtype=np.float32),
        channel_mask=ch_mask,
        stage="A",
        kernel_weeks=K,
    )
    assert net_a.delta is None
    assert "delta" not in dict(net_a.named_parameters())
    assert float(net_a.delta_penalty().item()) == 0.0

    # 4b & 6a. ONE tiny fit: 5 optimisation steps on a 3-well toy problem (stage B, well 2 held out).
    rng = np.random.default_rng(43)
    # Build synthetic target heads from a ground-truth HybridGNN (no training needed for truth).
    truth = H.HybridGNN(
        graph_data=graph,
        group_of=np.zeros(N, dtype=np.int64),
        n_groups=1,
        gain_scale=np.ones(N, dtype=np.float32),
        channel_mask=ch_mask,
        stage="A",
        kernel_weeks=K,
    )
    _randomise_net(truth, seed=44, spread=1.0)
    truth.eval()
    obs_tr = torch.zeros((N, T), dtype=torch.bool)
    obs_tr[:, :45] = True
    truth.estimate_centres(_to_torch(X_np), obs_tr)
    with torch.no_grad():
        head = truth(_to_torch(X_np)).numpy() + rng.normal(0.0, 0.05, (N, T)).astype(np.float32)

    split = np.array(["train"] * 45 + ["validation"] * (T - 45))[None, :].repeat(N, axis=0)
    mu = head[:, :45].mean(axis=1, keepdims=True).repeat(T, axis=1)
    sd = np.maximum(head[:, :45].std(axis=1, keepdims=True), 0.1).repeat(T, axis=1)
    toy_data = {
        "codes": [f"w{i}" for i in range(N)],
        "weeks": weeks.to_numpy(),
        "X": X_np,
        "head": head.astype(np.float64),
        "mu": mu.astype(np.float64),
        "sd": sd.astype(np.float64),
        "split": split,
        "core": np.ones((N, T), dtype=bool),
        "groups": ["g0"],
        "group_of": np.zeros(N, dtype=np.int64),
        "channel_mask": ch_mask,
        "river_c_mask": river_c_mask,
        "canal_c_mask": canal_c_mask,
    }
    keep_wells = np.array([True, True, False], dtype=bool)
    train_mask = (split == "train") & keep_wells[:, None]

    fit_kwargs = dict(
        seed=0,
        data=toy_data,
        graph_data=graph,
        epochs=5,
        lr=1e-2,
        lam_shape=0.05,
        lam_gain=0.01,
        lam_delta=0.05,
        signs="gate3",
        kernel_weeks=K,
        dropout=0.0,
        train_mask=train_mask,
        keep_wells=keep_wells,
        device="cpu",
        verbose=False,
    )
    state_out = {}
    net_b, _, n_ep, losses = H.train_seed(stage="B", epochs_b=5, state_out=state_out, **fit_kwargs)
    assert n_ep == 10 and len(losses) == 10, (n_ep, len(losses))
    assert losses[-1] < losses[0], f"loss did not decrease over 5 + 5 steps: {losses}"
    assert losses[-1] <= losses[4] + 1e-6, f"the delta-only refinement raised the loss: {losses}"

    # Stage B checks: delta exists; trained wells moved; held-out well 2 stayed identically 0.
    assert "delta" in dict(net_b.named_parameters())
    assert float(net_b.delta[:2].detach().abs().max()) > 1e-4, "trained wells' delta should update"
    assert torch.equal(net_b.delta[2], torch.zeros_like(net_b.delta[2])), "held-out delta must stay 0"
    assert torch.equal(net_b.effective_delta()[2], torch.zeros_like(net_b.delta[2]))

    # 4c. Stage B refines stage A (docs/v5_bugs_to_fix.md item 4): its first phase is exactly a stage-A
    # fit, and the refinement changes only delta. So every parameter but delta equals a stage-A run's
    # bit for bit, and the held-out well's predictions are exactly stage A's.
    net_a_fit, _, n_ep_a, losses_a = H.train_seed(stage="A", **fit_kwargs)
    assert n_ep_a == 5 and losses_a == losses[:5], "stage B's first phase must be the stage-A fit"
    params_a = dict(net_a_fit.named_parameters())
    for name, param in net_b.named_parameters():
        if name != "delta":
            assert torch.equal(param, params_a[name]), f"stage B changed {name}"
    X_toy = _to_torch(X_np)
    with torch.no_grad():
        y_a, y_b = net_a_fit(X_toy).numpy(), net_b(X_toy).numpy()
    held_diff = float(np.abs(y_a[2] - y_b[2]).max())
    assert held_diff < 1e-6, f"held-out well differs from stage A: {held_diff}"
    assert float(np.abs(y_a[:2] - y_b[:2]).max()) > 1e-6, "the refinement must move the trained wells"

    # Held-out well centring after train_seed (eval mode): mean over its observed training weeks == 0.
    with torch.no_grad():
        y_after = net_b(_to_torch(X_np)).numpy()
    held_mean = float(y_after[2, :45].mean())
    assert abs(held_mean) < 1e-6, f"held-out well mean after train_seed = {held_mean}"

    # 6b. RQ2 --signs none and --soft penalty check (no fitting).
    net_none = H.HybridGNN(
        graph_data=graph,
        group_of=np.zeros(N, dtype=np.int64),
        n_groups=1,
        gain_scale=sd[:, 0],
        channel_mask=ch_mask,
        stage="B",
        signs="none",
        sign_ref="gate3",
        kernel_weeks=K,
    )
    raw_g = torch.tensor(
        [[-0.3, 0.2, 0.1, 0.4, -0.2, 0.5, -0.1, 0.2, -0.3],
         [0.3, 0.2, 0.1, -0.4, -0.2, 0.5, -0.1, 0.2, -0.3],
         [0.3, 0.2, 0.1, -0.4, 0.2, -0.5, -0.1, 0.2, -0.3]],
        dtype=torch.float32,
    )
    with torch.no_grad():
        net_none.theta_group[:, :H.N_CHANNELS] = 0.0
        net_none.delta[:, :H.N_CHANNELS] = raw_g
    gain = net_none.parameters_physical().gain.detach()
    assert torch.allclose(gain, raw_g * torch.from_numpy(sd[:, 0])[:, None], atol=1e-6)
    mask_t = torch.zeros((N, T), dtype=torch.bool)
    mask_t[:, :45] = True
    sd_t = torch.from_numpy(sd[:, 0].astype(np.float32))
    c_none = net_none.contributions(_to_torch(X_np))
    pen = net_none.soft_penalty(c_none, mask_t, sd_t)
    cn = c_none.detach().numpy()[:, :, :45]
    wrong = (net_none.expected[None, :] * gain < 0).numpy()
    want = float(np.mean([(wrong[i] * cn[i].var(-1)).sum() / sd[i, 0] ** 2 for i in range(N)]))
    assert abs(pen.item() - want) < 1e-5 * max(1.0, want), (pen.item(), want)
    pen.backward()
    # Well 1 has all gate3-signed channels right -> zero soft-penalty grad on well 1.
    assert float(net_none.delta.grad[1, :H.N_CHANNELS].abs().max()) == 0.0
    # Well 0 recharge_local is negative (wrong) -> positive gradient pulls it up (Wait: wrong negative -> grad < 0 pushes up).
    assert float(net_none.delta.grad[0, H.CHANNELS.index("recharge_local")]) < 0.0

    # 6c. CLI refuses to train without PFE_ALLOW_TRAIN=1.
    for val in (None, "0", ""):
        env = {k: v for k, v in os.environ.items() if k != H.ALLOW_TRAIN_ENV}
        if val is not None:
            env[H.ALLOW_TRAIN_ENV] = val
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(sys, "argv", ["hybrid_gnn", "--arm", "D", "--epochs", "1", "--seeds", "0"]),
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
        ):
            try:
                H.main()
            except SystemExit as exc:
                assert H.ALLOW_TRAIN_ENV in str(exc)
            else:
                raise AssertionError(f"CLI trained without {H.ALLOW_TRAIN_ENV}=1 (val={val!r})")

    print(f"  4&6. stage A has no delta; 3-well stage B fit (5 stage-A + 5 delta-only steps) loss "
          f"{losses[0]:.4f} -> {losses[4]:.4f} -> {losses[-1]:.4f}; its first phase = the stage-A fit and only "
          f"delta changes after it; held-out well = stage A (max diff {held_diff:.1e}), held-out delta = 0.0, "
          f"held-out mean = {held_mean:.2e}; RQ2 soft penalty ok; CLI refuses without {H.ALLOW_TRAIN_ENV}=1")


# ---------------------------------------------------------------------------
# 5. Replay (save, reload, predict identical to < 1e-5 m)
# ---------------------------------------------------------------------------

def test_replay():
    torch.manual_seed(50)
    N, T, K = 4, 48, 24
    weeks = pd.date_range("2012-01-01", periods=T, freq="W-SUN")
    graph = _toy_graph(N, seed=51)
    X_np, river_c_mask, canal_c_mask = _toy_stresses(N, T, K, seed=52)
    sd = np.linspace(0.5, 1.8, N).astype(np.float32)
    ch_mask = np.ones((N, H.N_CHANNELS), dtype=bool)
    ch_mask[:, H.CHANNELS.index("river_c")] = river_c_mask
    ch_mask[:, H.CHANNELS.index("river")] = ~river_c_mask
    ch_mask[:, H.CHANNELS.index("canal_c")] = canal_c_mask
    ch_mask[:, H.CHANNELS.index("canal")] = ~canal_c_mask

    res_basis = R.seasonal_basis(weeks, harmonics=H.RESIDUAL_HARMONICS)
    res_bound = H.RESIDUAL_BOUND_SD * sd
    kwargs = dict(
        group_of=np.arange(N) % 2,
        n_groups=2,
        gain_scale=sd,
        channel_mask=ch_mask,
        stage="B",
        signs="gate3",
        kernel_weeks=K,
        residual="bounded",
        residual_basis=res_basis,
        residual_bound=res_bound,
    )
    net = H.HybridGNN(graph_data=graph, **kwargs)
    _randomise_net(net, seed=53, spread=1.2)
    net.eval()

    X_obs = _to_torch(X_np)
    obs_mask = torch.ones((N, T), dtype=torch.bool)
    obs_mask[:, 35:] = False
    net.estimate_centres(X_obs, obs_mask)

    data = {
        "codes": [f"w{i}" for i in range(N)],
        "weeks": weeks.to_numpy(),
        "X": X_np,
        "sd": sd[:, None].repeat(T, axis=1).astype(np.float64),
        "groups": ["g0", "g1"],
        "group_of": np.arange(N) % 2,
        "river_c_mask": river_c_mask,
        "canal_c_mask": canal_c_mask,
    }
    pz, contrib_df, params_df = H.seed_outputs(net, data, graph)

    # Exact additive decomposition check on saved contrib_df (merged river & canal + residual).
    with torch.no_grad():
        y_orig = net(X_obs).numpy()
    c_cols = [c for c in contrib_df.columns if c not in ("code_bss", "week")]
    assert "river_c" not in c_cols and "canal_c" not in c_cols
    assert "river" in c_cols and "canal" in c_cols and "residual" in c_cols
    assert "river_constrained" in params_df.columns and "canal_constrained" in params_df.columns
    summed = contrib_df[c_cols].sum(axis=1).to_numpy().reshape(N, T)
    decomp_err = float(np.abs(summed - y_orig).max())
    assert decomp_err < 1e-5, f"decomposition error {decomp_err}"

    # Counterfactual input for replay check.
    X_cf = {k: v.clone() for k, v in X_obs.items()}
    X_cf["rain_recharge_local"][:, K + 5] += 25.0
    with torch.no_grad():
        y_cf_orig = net(X_cf).numpy()

    with TemporaryDirectory() as tmp:
        out = Path(tmp)
        args = H.build_parser().parse_args(["--arm", "D", "--residual", "bounded", "--seeds", "0"])
        fp = write_config(out, args, ["toy"], {"model": "hybrid_gnn_v2"})
        save_seed_model(out, 0, net.state_dict(), 0.5, 5, fp)
        save_seed(out / "seed_0.parquet", pz, data["codes"], data["weeks"], 0.5, 5, fp)
        contrib_df.to_parquet(out / "contrib_seed_0.parquet", index=False)
        params_df.to_csv(out / "params_seed_0.csv", index=False)

        # Reload into a brand-new model via replay() using injected prep (and verify direct load_checkpoint).
        prep_stub = {"graph_data": graph, "data": data, "model_kwargs": kwargs}
        reloaded, _, _ = H.replay(out, 0, prep=prep_stub)
        ckpt = load_checkpoint(out / "seed_0.pt")
        assert "centres" in ckpt["state_dict"]
        assert torch.equal(reloaded.centres, net.centres)

        with torch.no_grad():
            y_rep = reloaded(X_obs).numpy()
            y_cf_rep = reloaded(X_cf).numpy()

    obs_diff = float(np.abs(y_rep - y_orig).max())
    cf_diff = float(np.abs(y_cf_rep - y_cf_orig).max())
    assert obs_diff < 1e-5 and cf_diff < 1e-5, (obs_diff, cf_diff)
    print(f"  5. replay: obs max diff = {obs_diff:.2e} m, counterfactual max diff = {cf_diff:.2e} m, "
          f"additive decomposition err = {decomp_err:.2e} m (< 1e-5 m)")


# ---------------------------------------------------------------------------
# 7. Encoder never sees a stress + real v5 forward pass (zero training)
# ---------------------------------------------------------------------------

def test_encoder_never_sees_stress_and_v5_forward():
    torch.manual_seed(70)
    N, T, K = 4, 48, 24
    graph = _toy_graph(N, seed=71)
    X_np, river_c_mask, canal_c_mask = _toy_stresses(N, T, K, seed=72)
    X_t = _to_torch(X_np)

    net = H.HybridGNN(
        graph_data=graph,
        group_of=np.arange(N) % 2,
        n_groups=2,
        gain_scale=np.ones(N, dtype=np.float32),
        stage="B",
        kernel_weeks=K,
    )
    _randomise_net(net, seed=73, spread=1.0)
    net.eval()

    # Record every argument passed to HeteroEncoder.forward via a PyTorch pre-hook.
    seen_calls = []

    def _pre_hook(_mod, inputs):
        seen_calls.append(inputs)

    handle = net.encoder.register_forward_pre_hook(_pre_hook)
    try:
        obs_mask = torch.ones((N, T), dtype=torch.bool)
        net.estimate_centres(X_t, obs_mask)
        with torch.no_grad():
            _ = net(X_t)
            _ = net.contributions(X_t)
            _ = net.training_forward(X_t, obs_mask)
            p1 = net.parameters_physical()
            e1 = net.encode()

        # Wildly alter every stress tensor: encoder output and physical parameters must be bit-for-bit identical.
        X_wild = {k: v * 100.0 + 50.0 for k, v in X_t.items()}
        with torch.no_grad():
            _ = net(X_wild)
            p2 = net.parameters_physical()
            e2 = net.encode()
    finally:
        handle.remove()

    assert len(seen_calls) >= 4
    for args_tuple in seen_calls:
        assert len(args_tuple) == 1 and isinstance(args_tuple[0], HeteroData)
        gd = args_tuple[0]
        for nt in gd.node_types:
            tensor_keys = {k for k, v in gd[nt].items() if isinstance(v, torch.Tensor)}
            assert tensor_keys == {"x"}, f"unexpected tensor keys on {nt}: {tensor_keys}"
        for et in gd.edge_types:
            tensor_keys = {k for k, v in gd[et].items() if isinstance(v, torch.Tensor)}
            assert tensor_keys == {"edge_index", "edge_attr"}, f"unexpected tensor keys on {et}: {tensor_keys}"

    assert torch.equal(e1, e2)
    for a, b in zip(p1, p2):
        assert torch.equal(a, b)

    # Zero-training real v5 verification (only when export_v5_main is present for active dataset).
    # Redirect panel cache to a TemporaryDirectory so tests never write into results/.
    v5_msg = "skipped (not v5)"
    exp_dir = H._export_dir("main")
    if exp_dir.is_dir() and (exp_dir / "edges_D.parquet").is_file():
        from src.models import features as F_mod

        summaries = []
        with TemporaryDirectory() as tmp_cache, patch.object(
            F_mod, "CACHE", Path(tmp_cache) / "panel.parquet"
        ):
            for arm in ("C", "D"):
                args = H.build_parser().parse_args(["--arm", arm, "--stage", "B", "--epochs", "1"])
                prep = H.prepare(args, verbose=False)
                data = prep["data"]
                gd = prep["graph_data"]
                # Check well-order alignment between data["codes"] and graph_data["well"].node_codes.
                graph_codes = gd["well"].node_codes
                for i, code in enumerate(data["codes"]):
                    assert graph_codes[int(prep["well_graph_idx"][i])] == code

                net_real = H.HybridGNN(graph_data=gd, **prep["model_kwargs"])
                net_real.eval()
                X_real = {k: torch.from_numpy(v) for k, v in data["X"].items()}
                obs_real = torch.from_numpy(np.isfinite(data["head"]) & (data["split"] == "train"))
                net_real.estimate_centres(X_real, obs_real)
                with torch.no_grad():
                    c_real = net_real.contributions(X_real).numpy()
                    y_real = net_real(X_real).numpy()
                assert np.isfinite(c_real).all() and np.isfinite(y_real).all()
                # Every inactive (well, channel) must have exact 0 contribution.
                inactive = ~data["channel_mask"]
                if inactive.any():
                    assert float(np.abs(c_real[inactive]).max()) == 0.0
                # Centring on all 65 real wells with training observations.
                real_err = max(
                    abs(float(y_real[i, obs_real[i].numpy()].mean()))
                    for i in range(len(data["codes"]))
                    if obs_real[i].any()
                )
                assert real_err < 1e-5, (arm, real_err)
                # Pumping before the pumping record is unknown, not zero: the warm-up and the weeks before
                # the record's first week carry the well's training mean (no step from 0 in 2003).
                rec = pd.Timestamp(prep["routed"]["pumping_record_start"])
                n_pre = int(np.sum(pd.DatetimeIndex(data["weeks"]) < rec))
                kw = prep["config_args"].kernel_weeks
                train_w = data["split"][0] == "train"
                for key, ch in (("pump_gw", "pumping"), ("pump_un", "pumping_unattributed")):
                    active = data["channel_mask"][:, H.CHANNELS.index(ch)]
                    arr = data["X"][key][active]
                    if n_pre and arr.size:
                        pre = arr[:, : kw - 1 + n_pre]
                        mean = arr[:, kw - 1:][:, train_w].mean(axis=1, keepdims=True)
                        assert np.allclose(pre, mean, rtol=1e-5, atol=1e-6), (arm, key)
                        assert (mean > 0).any(), (arm, key)
                summaries.append(
                    f"arm {arm}: {len(data['codes'])}x{len(data['weeks'])}, "
                    f"canal_mode={prep['routed']['canal_mode']}, max_centre_err={real_err:.2e}"
                )
        v5_msg = "; ".join(summaries)

    print(f"  7. encoder never sees stresses ({len(seen_calls)} hooked calls, only x/edge_index/edge_attr; "
          f"wild stresses -> identical params); real export check: {v5_msg}")


if __name__ == "__main__":
    started = time.perf_counter()
    test_finite_difference_signs()
    test_centring()
    test_pumping_reliability()
    test_stages_tiny_fit_and_guards()
    test_replay()
    test_encoder_never_sees_stress_and_v5_forward()
    print(f"test_hybrid_gnn: all checks passed ({time.perf_counter() - started:.2f}s)")
