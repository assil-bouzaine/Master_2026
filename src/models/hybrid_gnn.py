"""Hybrid-GNN v2 groundwater response model (analysis plan v3 §3).

    PFE_DATASET=v5 PFE_ALLOW_TRAIN=1 python -m src.models.hybrid_gnn \\
        --arm D --stage B --run hgnn_D_stageB

Why this module exists
----------------------
Hybrid-GNN v2 assembles the v5 upgrades planned in ``docs/analysis_plan_v3.md`` §3 into one
PyTorch module, keeping the exact additive decomposition and sign guarantees of
``src/models/response.py``:

    y_hat_i(t) = sum_r [ c_ir(t) - m_ir ] + rho_i(t),     c_ir = G_ir * (k_ir (*) s_ir)

1. **Per-well routed stresses (§2, §3):** from a v5 knowledge-graph export:
   - three recharge channels: ``recharge_local`` (export relation ``recharge``),
     ``recharge_regional`` (``recharge_unitwide``), and ``recharge_leakage``
     (``recharge_leakage``), each giving weighted weekly rain and ETP (mm/week);
   - ``pumping`` and ``pumping_unattributed`` (weighted sums of facility volumes);
   - ``river`` split into ``river_c`` (constrained in arm D's export, sign >= 0) and
     ``river`` (free), merged back into ``river`` in saved outputs;
   - ``canal`` using each well's river-basin series from ``canal_basins_weekly.parquet``
     (basin from ``src.dataset.canal_basins.canal_edge_well_basins``), split into
     ``canal_c`` (constrained in arm D's export, sign >= 0) and ``canal`` (free).
   A well without an edge for a channel gets zero stress and zero contribution there.
2. **Nonlinear monotone recharge (§3.3):** each recharge channel passes its weighted rain
   and ETP (mm/week) through ``src.models.bucket.bucket`` with per-(well, channel)
   parameters ``(S_max, kappa, beta)`` via ``bucket.raw_to_params``. The resulting recharge
   ``R >= 0`` (scaled from mm to cm/week so gains match ``response.py``) is the stress of
   that channel. Inactive recharge channels are masked to zero so initial soil storage never
   leaks into a well that has no edge for that channel.
3. **Two-component kernels (§3.4):** every channel convolves its stress with
   ``src.models.kernels.mixture_weights`` (fast + slow Gamma kernels, **slow shape
   ``n_slow >= 1``** to limit 416-week tail truncation) via ``kernels.causal_conv(..., "fft")``
   with ``K = 416`` weeks.
4. **Hard signs and sd-unit gains (§3.2):** ``G_ir = sigma_r * softplus(g_ir) * sd_i`` for
   signed channels (recharge +, pumping -, ``river_c`` +, ``canal_c`` +) and ``g_ir * sd_i``
   for free channels (``river``, ``canal``, or all channels under ``--signs none``). Supports
   RQ2's ``--signs none`` and ``--soft L`` using the same variance-share penalty as
   ``response.py``.
5. **Centring held fixed (§3.1):** ``m_ir`` is the mean of ``c_ir`` over well ``i``'s
   observed training weeks under the **observed** forcing, stored as a persistent buffer
   ``centres`` (never a free intercept). Two distinct paths are maintained:
   - **Training path** (``training_forward`` / ``centres_from_current``): recomputes ``m_ir``
     at every epoch from the observed-forcing contributions with autograd gradients flowing
     through the model parameters, and updates the ``centres`` buffer with detached values.
   - **Inference / counterfactual path** (``forward(X)`` / ``estimate_centres``): uses the
     fixed stored ``centres`` buffer without recomputing it from ``X``. Counterfactual
     perturbations therefore never shift ``m_ir`` and preserve exact monotonicity at every
     week. A held-out leave-wells-out well gets its ``m_ir`` from its own observed training
     weeks (no head value enters beyond the training mask that defines ``mu_i``).
6. **Graph parameter encoder and two stages (§3.5):** raw parameters
   ``theta_i = theta_group(i) + HeteroEncoder(data)_i + delta_i``. ``HeteroEncoder`` reads
   only the static ``HeteroData`` (never a stress). ``stage="A"`` omits ``delta`` (not a
   parameter); ``stage="B"`` adds per-well ``delta`` with ridge penalty ``lam_delta`` while
   always keeping ``delta_i = 0`` on held-out wells. Split regularisation penalises the
   spread ``enc + delta`` around the group mean with ``lam_shape`` on kernel and bucket raw
   parameters and ``lam_gain`` (< ``lam_shape``) on gain raw parameters.
7. **Pumping reliability (§3.6):** on training weeks before ``RELIABLE_PUMPING_FROM``
   (``"2012-01-01"``), the loss evaluates pumping contributions (and their centring terms)
   with detached pumping parameters so pre-declaration imputed pumping never calibrates a
   pumping gain or kernel while weather and other drivers still learn from 2005–2011.
8. **Optional bounded residual (§3.8):** ``residual="bounded"`` adds
   ``rho_i(t) = 0.2 * sd_i * tanh(MLP(day-of-year features, static facts))``, never seeing a
   stress; off by default.
9. **Training guard:** the CLI refuses to train unless ``PFE_ALLOW_TRAIN=1`` is set, so
   training runs only on Colab and never accidentally on the laptop.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import time
from typing import NamedTuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F

from src.config import DATASET, DATASET_DIR, PROCESSED, R3_STARTS
from src.dataset import canal_basins as CB
from src.dataset.pumping import canal_series
from src.models import bucket as BK
from src.models import kernels as KN
from src.models import response as R
from src.models import routing as RT
from src.models.evaluate import RESULTS, evaluate_run
from src.models.features import build_panel, river_series
from src.models.hetero_graph import HeteroEncoder, build_heterodata
from src.models.lstm import (
    cached_seed,
    median_nse,
    regime_masks,
    run_fingerprint,
    save_seed,
    save_seed_model,
    seed_mean_predictions,
    write_config,
)
from src.models.manifest import load_checkpoint, write_manifest, write_schema

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RECHARGE_CHANNELS = ("recharge_local", "recharge_regional", "recharge_leakage")
RECHARGE_RELATIONS = {
    "recharge_local": "recharge",
    "recharge_regional": "recharge_unitwide",
    "recharge_leakage": "recharge_leakage",
}
PUMPING_CHANNELS = ("pumping", "pumping_unattributed")
NON_RECHARGE_CHANNELS = ("pumping", "pumping_unattributed", "river_c", "river", "canal_c", "canal")
CHANNELS = RECHARGE_CHANNELS + NON_RECHARGE_CHANNELS
N_RECHARGE = len(RECHARGE_CHANNELS)
N_CHANNELS = len(CHANNELS)
PUMPING_INDICES = tuple(CHANNELS.index(ch) for ch in PUMPING_CHANNELS)

NON_RECHARGE_INPUT = {
    "pumping": "pump_gw",
    "pumping_unattributed": "pump_un",
    "river_c": "river_c",
    "river": "river",
    "canal_c": "canal_c",
    "canal": "canal",
}

# Input scaling matching response.py: bucket runs in mm/week and its output R is divided by
# RECHARGE_SCALE (10 mm -> cm/week); pumping in 1e5 m3/week; river in log(1+q); canal in 10 Mm3/week.
RECHARGE_SCALE = 10.0
STRESS_SCALE = {
    "pump_gw": 100.0,
    "pump_un": 100.0,
    "river": 1.0,
    "river_c": 1.0,
    "canal": 10.0,
    "canal_c": 10.0,
}

KERNEL_WEEKS = KN.KERNEL_WEEKS       # 416 weeks (8 years)
N_FAST_MIN, N_FAST_MAX = KN.N_MIN, KN.N_MAX
# Plan v3 §3.4: slow component shape bounded below at n >= 1 to limit 416-week tail truncation.
N_SLOW_MIN, N_SLOW_MAX = 1.0, KN.N_MAX

RELIABLE_PUMPING_FROM = "2012-01-01"
SD_FLOOR = R.SD_FLOOR
RESIDUAL_BOUND_SD = 0.20             # Plan v3 §3.8: |rho_i(t)| <= 0.20 * sd_i
RESIDUAL_HARMONICS = 2
RESIDUAL_HIDDEN = 16

SIGN_STRUCTURAL = {
    "recharge_local": 1.0,
    "recharge_regional": 1.0,
    "recharge_leakage": 1.0,
    "pumping": -1.0,
    "pumping_unattributed": -1.0,
    "river_c": 1.0,
    "river": 1.0,
    "canal_c": 1.0,
    "canal": 1.0,
}
SIGN_SETS = {
    "gate3": {ch: (0.0 if ch in ("river", "canal") else s) for ch, s in SIGN_STRUCTURAL.items()},
    "structure": dict(SIGN_STRUCTURAL),
    "none": {ch: 0.0 for ch in CHANNELS},
}

# Hydrologically sensible starting point for group means (raw space).
INIT_GAIN = 0.1
INIT_S_MAX = 100.0
INIT_KAPPA = 0.2
INIT_BETA = 0.1

REGIMES = ("R1", "R2", "R3_f25", "R3_f50", "refit")
ALLOW_TRAIN_ENV = "PFE_ALLOW_TRAIN"

# Raw parameter layout per well:
#   [0 : R]                 -> gain raw (R)
#   [R : R + 5*R]           -> kernel raw (R, 5): (mean_fast, n_fast, mean_slow, n_slow, w_slow)
#   [6*R : 6*R + 3*C]       -> bucket raw (C, 3): (s_max, kappa, beta)
N_KERNEL_PARAMS = 5
N_BUCKET_PARAMS = 3
N_RAW_PARAMS = N_CHANNELS + N_CHANNELS * N_KERNEL_PARAMS + N_RECHARGE * N_BUCKET_PARAMS


class PhysicalParams(NamedTuple):
    """Decoded physical parameters of ``HybridGNN``."""

    gain: torch.Tensor        # (N, R) signed metres per unit scaled stress
    mean_fast: torch.Tensor   # (N, R) weeks
    n_fast: torch.Tensor      # (N, R) in (N_FAST_MIN, N_FAST_MAX)
    mean_slow: torch.Tensor   # (N, R) weeks
    n_slow: torch.Tensor      # (N, R) in (N_SLOW_MIN, N_SLOW_MAX), n_slow >= 1
    w_slow: torch.Tensor      # (N, R) in (0, 1)
    s_max: torch.Tensor       # (N, C) mm
    kappa: torch.Tensor       # (N, C) in (KAPPA_MIN, KAPPA_MAX)
    beta: torch.Tensor        # (N, C) in (BETA_MIN, BETA_MAX)


def _logit(p):
    return math.log(p / (1.0 - p))


def _inv_softplus(y):
    return math.log(math.expm1(y))


def raw_to_kernel_params_v2(raw):
    """Map ``(..., 5)`` raw values to ``(mean_fast, n_fast, mean_slow, n_slow, w_slow)``.

    Uses ``src.models.kernels`` bounds for means and fast shape, and enforces
    ``n_slow in (1.0, N_MAX)`` per analysis plan v3 §3.4 (``kernels.raw_to_kernel_params``
    currently keeps ``n_slow >= 0.5``).
    """
    if raw.ndim < 1 or raw.shape[-1] != N_KERNEL_PARAMS:
        raise ValueError(f"Expected kernel raw shape (..., {N_KERNEL_PARAMS}), got {tuple(raw.shape)}")
    mf, nf, ms, ns, w = torch.sigmoid(raw).unbind(-1)
    mean_fast = torch.exp(
        math.log(KN.MEAN_FAST_MIN) + mf * math.log(KN.MEAN_FAST_MAX / KN.MEAN_FAST_MIN)
    )
    mean_slow = torch.exp(
        math.log(KN.MEAN_SLOW_MIN) + ms * math.log(KN.MEAN_SLOW_MAX / KN.MEAN_SLOW_MIN)
    )
    n_fast = N_FAST_MIN + nf * (N_FAST_MAX - N_FAST_MIN)
    n_slow = N_SLOW_MIN + ns * (N_SLOW_MAX - N_SLOW_MIN)
    return mean_fast, n_fast, mean_slow, n_slow, w


def _initial_raw_base(signs):
    """Default initial group-mean raw vector of length ``N_RAW_PARAMS``."""
    sign_map = SIGN_SETS[signs]
    g0 = torch.tensor(
        [_inv_softplus(INIT_GAIN) if sign_map[ch] != 0.0 else 0.0 for ch in CHANNELS],
        dtype=torch.float32,
    )
    # 0.0 maps kernel means to geometric midpoints, shapes to linear midpoints, w_slow to 0.5.
    k0 = torch.zeros(N_CHANNELS * N_KERNEL_PARAMS, dtype=torch.float32)

    s_p = (math.log(INIT_S_MAX) - math.log(BK.S_MAX_MIN)) / (
        math.log(BK.S_MAX_MAX) - math.log(BK.S_MAX_MIN)
    )
    k_p = (INIT_KAPPA - BK.KAPPA_MIN) / (BK.KAPPA_MAX - BK.KAPPA_MIN)
    b_p = (INIT_BETA - BK.BETA_MIN) / (BK.BETA_MAX - BK.BETA_MIN)
    one_bucket = torch.tensor([_logit(s_p), _logit(k_p), _logit(b_p)], dtype=torch.float32)
    b0 = one_bucket.repeat(N_RECHARGE)
    return torch.cat([g0, k0, b0])


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class HybridGNN(nn.Module):
    """Hybrid-GNN v2: static heterogeneous GNN parameter encoder + monotone soil buckets +
    two-component Gamma kernels + fixed-centre additive head anomaly.

    See module docstring and ``docs/analysis_plan_v3.md`` §3.
    """

    def __init__(
        self,
        graph_data,
        group_of,
        n_groups,
        *,
        well_graph_idx=None,
        gain_scale=None,
        channel_mask=None,
        stage="B",
        signs="gate3",
        sign_ref="gate3",
        soft_stresses=None,
        kernel_weeks=KERNEL_WEEKS,
        hidden=32,
        heads=2,
        dropout=0.1,
        n_layers=2,
        bucket_smooth=0.0,
        residual="none",
        residual_basis=None,
        residual_bound=None,
        train_well_mask=None,
        init_sd=0.0,
        generator=None,
    ):
        super().__init__()
        if stage not in ("A", "B"):
            raise ValueError(f"stage must be 'A' or 'B', got {stage!r}")
        if signs not in SIGN_SETS:
            raise ValueError(f"signs must be one of {list(SIGN_SETS)}, got {signs!r}")
        if sign_ref not in SIGN_SETS:
            raise ValueError(f"sign_ref must be one of {list(SIGN_SETS)}, got {sign_ref!r}")
        if residual not in ("none", "bounded"):
            raise ValueError(f"residual must be 'none' or 'bounded', got {residual!r}")

        group_t = torch.as_tensor(group_of, dtype=torch.long)
        if group_t.ndim != 1:
            raise ValueError(f"group_of must be 1D, got shape {tuple(group_t.shape)}")
        N = int(group_t.shape[0])
        R = N_CHANNELS
        C = N_RECHARGE

        n_graph_wells = int(graph_data["well"].x.shape[0])
        if well_graph_idx is None:
            if N != n_graph_wells:
                raise ValueError(
                    f"well_graph_idx required when model has {N} wells and graph has {n_graph_wells}"
                )
            w_idx = torch.arange(N, dtype=torch.long)
        else:
            w_idx = torch.as_tensor(well_graph_idx, dtype=torch.long)
            if w_idx.shape != (N,):
                raise ValueError(f"well_graph_idx must have shape ({N},), got {tuple(w_idx.shape)}")
            if int(w_idx.min()) < 0 or int(w_idx.max()) >= n_graph_wells:
                raise ValueError("well_graph_idx out of bounds for graph_data['well'].x")

        self.graph_data = graph_data
        self.stage = stage
        self.signs = signs
        self.sign_ref = sign_ref
        self.K = int(kernel_weeks)
        self.bucket_smooth = float(bucket_smooth)
        self.residual_kind = residual
        self.names = CHANNELS
        self.recharge_names = RECHARGE_CHANNELS
        self.pumping_indices = PUMPING_INDICES

        self.register_buffer("group_of", group_t)
        self.register_buffer("well_graph_idx", w_idx)
        self.register_buffer(
            "sign", torch.tensor([SIGN_SETS[signs][ch] for ch in CHANNELS], dtype=torch.float32)
        )
        ref = SIGN_SETS[sign_ref]
        expected = [
            (SIGN_STRUCTURAL[ch] if ch in soft_stresses else 0.0) if soft_stresses is not None else ref[ch]
            for ch in CHANNELS
        ]
        self.register_buffer("expected", torch.tensor(expected, dtype=torch.float32), persistent=False)

        g_scale = (
            torch.ones(N, dtype=torch.float32)
            if gain_scale is None
            else torch.as_tensor(np.asarray(gain_scale), dtype=torch.float32)
        )
        if g_scale.shape != (N,):
            raise ValueError(f"gain_scale must have shape ({N},), got {tuple(g_scale.shape)}")
        self.register_buffer("gain_scale", g_scale)

        if channel_mask is None:
            ch_mask = torch.ones((N, R), dtype=torch.float32)
        else:
            ch_mask = torch.as_tensor(np.asarray(channel_mask), dtype=torch.float32)
            if ch_mask.shape != (N, R):
                raise ValueError(f"channel_mask must have shape ({N}, {R}), got {tuple(ch_mask.shape)}")
        self.register_buffer("channel_mask", ch_mask)

        if train_well_mask is None:
            tw_mask = torch.ones(N, dtype=torch.bool)
        else:
            tw_mask = torch.as_tensor(np.asarray(train_well_mask), dtype=torch.bool)
            if tw_mask.shape != (N,):
                raise ValueError(f"train_well_mask must have shape ({N},), got {tuple(tw_mask.shape)}")
        self.register_buffer("train_well_mask", tw_mask)

        # Fixed per-(well, channel) centres m_ir (metres), estimated from observed forcing over
        # each well's observed training weeks. Saved in state_dict for exact replay.
        self.register_buffer("centres", torch.zeros((N, R), dtype=torch.float32))

        base = _initial_raw_base(signs)
        if init_sd > 0.0:
            noise = init_sd * torch.randn((int(n_groups), N_RAW_PARAMS), generator=generator)
        else:
            noise = torch.zeros((int(n_groups), N_RAW_PARAMS), dtype=torch.float32)
        self.theta_group = nn.Parameter(base.unsqueeze(0).repeat(int(n_groups), 1) + noise)

        # Static-only heterogeneous graph encoder (head initialised to exact zero).
        self.encoder = HeteroEncoder.from_heterodata(
            graph_data,
            n_out=N_RAW_PARAMS,
            hidden=hidden,
            heads=heads,
            dropout=dropout,
            n_layers=n_layers,
        )

        # Stage A has no delta parameter at all; Stage B adds per-well delta (always 0 for LWO wells).
        if stage == "B":
            self.delta = nn.Parameter(torch.zeros((N, N_RAW_PARAMS), dtype=torch.float32))
        else:
            self.delta = None

        # Optional bounded residual row: 0.2 * sd_i * tanh(MLP(day-of-year, static facts)).
        self.residual_mlp = None
        if residual == "bounded":
            if residual_basis is None or residual_bound is None:
                raise ValueError("residual='bounded' requires residual_basis and residual_bound")
            basis = torch.as_tensor(np.asarray(residual_basis), dtype=torch.float32)
            if basis.ndim != 2 or basis.shape[1] != 2 * RESIDUAL_HARMONICS:
                raise ValueError(
                    f"residual_basis must be (T, {2 * RESIDUAL_HARMONICS}), got {tuple(basis.shape)}"
                )
            bound = torch.as_tensor(np.asarray(residual_bound), dtype=torch.float32)
            if bound.shape != (N,) or (bound <= 0).any():
                raise ValueError(f"residual_bound must be positive ({N},), got {tuple(bound.shape)}")
            self.register_buffer("res_basis", basis)
            self.register_buffer("res_bound", bound)
            well_dim = int(graph_data["well"].x.shape[1])
            in_dim = int(basis.shape[1]) + well_dim
            first = nn.Linear(in_dim, RESIDUAL_HIDDEN)
            if generator is not None:
                with torch.no_grad():
                    scale = in_dim ** -0.5
                    first.weight.uniform_(-scale, scale, generator=generator)
                    first.bias.uniform_(-scale, scale, generator=generator)
            last = nn.Linear(RESIDUAL_HIDDEN, 1)
            nn.init.zeros_(last.weight)
            nn.init.zeros_(last.bias)
            self.residual_mlp = nn.Sequential(first, nn.Tanh(), last)

    def to(self, *args, **kwargs):
        """Move parameters, buffers, and the attached static ``HeteroData`` to the same device."""
        res = super().to(*args, **kwargs)
        if res.graph_data is not None:
            res.graph_data = res.graph_data.to(res.centres.device)
        return res

    def _resolve_graph(self, graph_data=None):
        gd = self.graph_data if graph_data is None else graph_data
        if gd is None:
            raise ValueError("graph_data must be provided either at init or to the call")
        return gd

    def encode(self, graph_data=None):
        """Run the static-only ``HeteroEncoder`` and select model wells in model order."""
        gd = self._resolve_graph(graph_data)
        return self.encoder(gd)[self.well_graph_idx]

    def effective_delta(self):
        """Per-well deviation ``delta`` masked to 0 on held-out wells (or ``None`` in stage A)."""
        if self.delta is None:
            return None
        return self.delta * self.train_well_mask[:, None].to(self.delta.dtype)

    def raw_components(self, graph_data=None):
        """Return ``(theta, dev, eff_delta)`` where ``theta = theta_group[group_of] + dev``."""
        enc = self.encode(graph_data)
        eff_delta = self.effective_delta()
        dev = enc if eff_delta is None else enc + eff_delta
        theta = self.theta_group[self.group_of] + dev
        return theta, dev, eff_delta

    def raw(self, graph_data=None):
        """Per-well raw parameters ``theta`` of shape ``(N, N_RAW_PARAMS)``."""
        return self.raw_components(graph_data)[0]

    def parameters_physical(self, graph_data=None, *, theta=None):
        """Decode raw parameters to ``PhysicalParams`` (gains, two-component kernels, buckets)."""
        p = self.raw(graph_data) if theta is None else theta
        N = p.shape[0]
        R = N_CHANNELS
        C = N_RECHARGE

        g_raw = p[:, :R]
        k_raw = p[:, R:R + R * N_KERNEL_PARAMS].reshape(N, R, N_KERNEL_PARAMS)
        b_raw = p[:, R + R * N_KERNEL_PARAMS:].reshape(N, C, N_BUCKET_PARAMS)

        sign = self.sign.to(dtype=p.dtype, device=p.device)
        g_scale = self.gain_scale.to(dtype=p.dtype, device=p.device)
        gain = torch.where(sign != 0.0, sign * F.softplus(g_raw), g_raw) * g_scale[:, None]
        mean_fast, n_fast, mean_slow, n_slow, w_slow = raw_to_kernel_params_v2(k_raw)
        s_max, kappa, beta = BK.raw_to_params(b_raw)
        return PhysicalParams(gain, mean_fast, n_fast, mean_slow, n_slow, w_slow, s_max, kappa, beta)

    def kernels(self, params):
        """Two-component Gamma mixture weights ``(N, R, K)`` summing to 1 along ``K``."""
        return KN.mixture_weights(
            params.mean_fast,
            params.n_fast,
            params.mean_slow,
            params.n_slow,
            params.w_slow,
            K=self.K,
        )

    def stresses(self, X, params):
        """Compute per-(well, channel) weekly stresses ``(N, R, T + K - 1)``.

        Recharge channels pass ``(rain, ETP)`` (mm/week) through ``bucket.bucket``, scale the
        resulting recharge by ``1 / RECHARGE_SCALE``, and mask inactive channels to zero so
        initial bucket storage never leaks into wells without that recharge edge.
        """
        mask = self.channel_mask.to(dtype=params.gain.dtype, device=params.gain.device)
        P = torch.stack([X[f"rain_{ch}"] for ch in RECHARGE_CHANNELS], dim=1)
        ETP = torch.stack([X[f"ETP_{ch}"] for ch in RECHARGE_CHANNELS], dim=1)
        R_mm, _ = BK.bucket(P, ETP, params.s_max, params.kappa, params.beta, smooth=self.bucket_smooth)
        R_scaled = (R_mm / RECHARGE_SCALE) * mask[:, :N_RECHARGE, None]
        other = torch.stack([X[NON_RECHARGE_INPUT[ch]] for ch in NON_RECHARGE_CHANNELS], dim=1)
        S = torch.cat([R_scaled, other], dim=1)
        return S * mask[:, :, None]

    def contributions(self, X, graph_data=None, *, theta=None, detach_pumping=False):
        """Uncentred per-(well, channel) contributions ``c_ir(t)`` of shape ``(N, R, T)`` (m)."""
        params = self.parameters_physical(graph_data, theta=theta)
        S = self.stresses(X, params)
        k = self.kernels(params)
        gain = params.gain

        if detach_pumping:
            k = k.clone()
            gain = gain.clone()
            for r in self.pumping_indices:
                k[:, r, :] = k[:, r, :].detach()
                gain[:, r] = gain[:, r].detach()

        conv = KN.causal_conv(S, k, method="fft")
        mask = self.channel_mask.to(dtype=conv.dtype, device=conv.device)
        return (gain[..., None] * conv) * mask[:, :, None]

    def residual(self, graph_data=None):
        """Bounded residual ``rho_i(t)`` of shape ``(N, T)`` in metres, or ``None`` if off."""
        if self.residual_mlp is None:
            return None
        gd = self._resolve_graph(graph_data)
        well_x = gd["well"].x[self.well_graph_idx]                # (N, F_well)
        N = well_x.shape[0]
        T = self.res_basis.shape[0]
        doy = self.res_basis.unsqueeze(0).expand(N, T, -1)        # (N, T, 4)
        stat = well_x.unsqueeze(1).expand(N, T, -1)               # (N, T, F_well)
        raw_res = self.residual_mlp(torch.cat([doy, stat], dim=-1)).squeeze(-1)  # (N, T)
        return self.res_bound[:, None] * torch.tanh(raw_res)

    @staticmethod
    def _compute_centres(c, obs_mask):
        """Mean of ``c`` ``(N, R, T)`` over boolean ``obs_mask`` ``(N, T)`` -> ``(N, R)``.

        Accumulates in float64 to avoid float32 summation drift across hundreds of training weeks.
        """
        c64 = c.to(torch.float64)
        m_w = obs_mask.to(dtype=torch.float64, device=c.device)
        denom = m_w.sum(dim=-1, keepdim=True)                     # (N, 1)
        has_obs = (denom > 0).to(torch.float64)
        centres = (c64 * m_w[:, None, :]).sum(dim=-1) / denom.clamp(min=1.0)
        return (centres * has_obs).to(c.dtype)

    @torch.no_grad()
    def estimate_centres(self, X, obs_mask, graph_data=None):
        """Compute ``m_ir`` from observed forcing ``X`` over ``obs_mask`` and store in buffer.

        Call this once (typically in ``eval()`` mode) before running counterfactual or
        evaluation passes via ``forward(X)``.
        """
        c = self.contributions(X, graph_data)
        centres = self._compute_centres(c, obs_mask)
        self.centres.copy_(centres)
        return self.centres.clone()

    def centres_from_current(self, c, obs_mask):
        """Differentiable per-epoch centre computation for training.

        Computes ``m_ir`` from the current forward pass's observed-forcing contributions ``c``
        so gradients flow through the parameters, while also refreshing the ``centres`` buffer
        with detached values.
        """
        centres = self._compute_centres(c, obs_mask)
        with torch.no_grad():
            self.centres.copy_(centres.detach())
        return centres

    def forward(self, X, graph_data=None):
        """Inference and counterfactual forward pass using the **fixed** stored ``centres`` buffer.

        ``y_hat_i(t) = sum_r (c_ir(t) - m_ir) (+ rho_i(t))`` in metres above ``mu_i``.
        Never recomputes ``centres`` from ``X``, so counterfactual input perturbations preserve
        exact sign monotonicity at every week (plan v3 §3.1).
        """
        c = self.contributions(X, graph_data)
        out = (c - self.centres[:, :, None]).sum(dim=1)
        if self.residual_mlp is not None:
            out = out + self.residual(graph_data)
        return out

    def training_forward(self, X, obs_train_mask, reliable_week_mask=None, graph_data=None):
        """Training forward pass with differentiable centring and pre-2012 pumping detachment.

        Runs ``HeteroEncoder``, ``bucket``, and ``causal_conv`` once per epoch. On weeks where
        ``reliable_week_mask`` is False (before ``RELIABLE_PUMPING_FROM``), both the pumping
        contributions and their centring means are detached from the autograd graph, so
        pre-2012 imputed pumping never calibrates pumping parameters (plan v3 §3.6).

        Returns ``(pred, c, dev, eff_delta)``.
        """
        theta, dev, eff_delta = self.raw_components(graph_data)
        c = self.contributions(X, graph_data, theta=theta)
        m_full = self.centres_from_current(c, obs_train_mask)
        res = self.residual(graph_data)

        y_rel = (c - m_full[:, :, None]).sum(dim=1)
        if res is not None:
            y_rel = y_rel + res

        if reliable_week_mask is not None and not bool(reliable_week_mask.all()):
            rel_mask = reliable_week_mask.to(device=c.device, dtype=torch.bool)
            # Detach pumping contributions (and hence pumping parameters) on pre-2012 weeks.
            c_pre = c.clone()
            for r in self.pumping_indices:
                c_pre[:, r, :] = c[:, r, :].detach()
            m_pre = self._compute_centres(c_pre, obs_train_mask)
            y_pre = (c_pre - m_pre[:, :, None]).sum(dim=1)
            if res is not None:
                y_pre = y_pre + res
            pred = torch.where(rel_mask[None, :], y_rel, y_pre)
        else:
            pred = y_rel

        return pred, c, dev, eff_delta

    def shape_penalty(self, graph_data=None, *, dev=None):
        """Mean squared spread of kernel and bucket raw parameters around the group mean."""
        d = self.raw_components(graph_data)[1] if dev is None else dev
        return (d[:, N_CHANNELS:] ** 2).mean()

    def gain_penalty(self, graph_data=None, *, dev=None):
        """Mean squared spread of gain raw parameters around the group mean."""
        d = self.raw_components(graph_data)[1] if dev is None else dev
        return (d[:, :N_CHANNELS] ** 2).mean()

    def delta_penalty(self, *, eff_delta=None):
        """Ridge penalty on stage-B ``delta`` over trained wells (0 in stage A)."""
        ed = self.effective_delta() if eff_delta is None else eff_delta
        if ed is None:
            return self.centres.new_zeros(())
        if not bool(self.train_well_mask.any()):
            return ed.new_zeros(())
        return (ed[self.train_well_mask] ** 2).mean()

    def residual_penalty(self):
        """Mean squared weights of the bounded residual MLP (0 when off)."""
        if self.residual_mlp is None:
            return self.centres.new_zeros(())
        weights = [p.reshape(-1) for name, p in self.residual_mlp.named_parameters() if name.endswith("weight")]
        return torch.cat(weights).pow(2).mean()

    def soft_penalty(self, c, mask, sd, graph_data=None, *, theta=None):
        """RQ2 soft sign penalty: mean over wells of the training-variance share carried by
        contributions whose gain has the wrong sign (identical definition to ``response.py``)."""
        gain = self.parameters_physical(graph_data, theta=theta).gain
        expected = self.expected.to(dtype=gain.dtype, device=gain.device)
        wrong = (expected * gain < 0).to(c.dtype)
        m = mask[:, None, :].to(dtype=c.dtype, device=c.device)
        n = m.sum(-1).clamp(min=1.0)
        mean = (c * m).sum(-1) / n
        var = ((c - mean[..., None]) ** 2 * m).sum(-1) / n
        sd_t = sd.to(dtype=c.dtype, device=c.device)
        return ((wrong * var).sum(1) / sd_t ** 2).mean()


# ---------------------------------------------------------------------------
# Routing & data preparation for v5 exports
# ---------------------------------------------------------------------------

def constrained_wells(relation, policy="main", dataset=DATASET, edges_d=None):
    """Set of well codes whose edges of ``relation`` in arm D's export are all ``constrained``.

    Always read from arm D so every arm shares the same sign slots (analysis plan §10).
    """
    if edges_d is None:
        edges_d, _ = RT.load_edges("D", policy, dataset)
    sub = edges_d[edges_d["relation"] == relation]
    if sub.empty:
        return set()
    ok = sub.groupby("dst")["constrained"].all()
    return set(ok.index[ok.astype(bool)])


def _canal_basin_wide(weeks, reconstruction, canal_basins_weekly=None, canal_intakes_basin=None):
    """Return ``(wide_df, mode)`` where ``wide_df`` is weekly Mm3/week per basin, or ``None``."""
    if canal_basins_weekly is not None:
        cb = canal_basins_weekly
        wide = cb.pivot(index="week", columns="basin", values="volume_m3") / 1e6
        return wide, "basin"

    cb_path = DATASET_DIR / "canal_basins_weekly.parquet"
    intakes_path = DATASET_DIR / "canal_intakes_basin.parquet"
    if reconstruction == 3 and (canal_intakes_basin is not None or intakes_path.is_file()):
        intakes = (
            canal_intakes_basin
            if canal_intakes_basin is not None
            else pd.read_parquet(intakes_path)
        )
        pw = RT.pumping_table(3)
        pts = pd.read_parquet(DATASET_DIR / "pumping_points.parquet")
        wide = CB.canal_series_by_basin(intakes, pw=pw, pts=pts) / 1e6
        return wide, "basin_cropcal"
    if cb_path.is_file():
        cb = pd.read_parquet(cb_path)
        wide = cb.pivot(index="week", columns="basin", values="volume_m3") / 1e6
        return wide, "basin"
    return None, "plain"


def routed_v5_inputs(
    arm=None,
    policy="main",
    edges=None,
    codes=None,
    weeks=None,
    reconstruction=1,
    river_rule="declared",
    dataset=DATASET,
    canal_basins_weekly=None,
    canal_intakes_basin=None,
    reaches=None,
):
    """Route v5 stresses per well from an export's edges (plan v3 §2 and §3).

    Produces:
    - ``rain_<ch>``, ``ETP_<ch>``, ``has_<ch>`` for each recharge channel in ``RECHARGE_CHANNELS``;
    - ``pump_gw``, ``pump_un``, ``has_pumping``, ``has_pumping_unattributed``;
    - ``river``, ``has_river``;
    - ``canal``, ``has_canal`` using each canal-edge well's river-basin series from
      ``canal_basins_weekly.parquet`` (nearest main river via ``canal_edge_well_basins``),
      falling back to plain-wide ``canal_series`` only when the basin table is absent.
    """
    splits = json.loads((DATASET_DIR / "splits.json").read_text())
    wells = pd.read_parquet(DATASET_DIR / "wells.parquet")
    forcing = pd.read_parquet(DATASET_DIR / "forcing_weekly.parquet")
    heads = pd.read_parquet(DATASET_DIR / "heads_weekly.parquet", columns=["week"])
    if weeks is None:
        weeks = pd.date_range(forcing["week"].min(), heads["week"].max(), freq=splits["week_rule"])
    weeks = pd.DatetimeIndex(weeks)
    codes = list(wells["code_bss"]) if codes is None else list(codes)

    meta = None
    if edges is None:
        edges, meta = RT.load_arm(arm, policy, dataset)

    N, T = len(codes), len(weeks)
    out = {
        "codes": codes,
        "weeks": weeks,
        "arm": arm,
        "reconstruction": int(reconstruction),
        "export": meta and {
            k: meta[k]
            for k in ("release", "policy", "code_version", "control", "export_sha256")
            if k in meta
        },
    }

    # 1. Three recharge channels (local, regional, leakage): weighted mean of rain and ETP (mm/week).
    all_rch_cells = sorted(
        edges.loc[edges["relation"].isin(RECHARGE_RELATIONS.values()), "src"].unique()
    )
    f_sub = forcing[forcing["cell_id"].isin(all_rch_cells)]
    rain_piv = (
        f_sub.pivot(index="week", columns="cell_id", values="rain").reindex(index=weeks, columns=all_rch_cells)
        if all_rch_cells
        else pd.DataFrame(index=weeks)
    )
    etp_piv = (
        f_sub.pivot(index="week", columns="cell_id", values="ETP").reindex(index=weeks, columns=all_rch_cells)
        if all_rch_cells
        else pd.DataFrame(index=weeks)
    )

    for ch, rel in RECHARGE_RELATIONS.items():
        e_rel = edges[edges["relation"] == rel]
        cells = sorted(e_rel["src"].unique())
        if cells:
            W = RT._matrix(edges, rel, codes, cells)
            tot = W.sum(axis=1, keepdims=True)
            has = tot[:, 0] > 0
            Wn = np.divide(W, tot, out=np.zeros_like(W), where=tot > 0)
            out[f"rain_{ch}"] = Wn @ rain_piv[cells].to_numpy(dtype=float).T
            out[f"ETP_{ch}"] = Wn @ etp_piv[cells].to_numpy(dtype=float).T
        else:
            has = np.zeros(N, dtype=bool)
            out[f"rain_{ch}"] = np.zeros((N, T), dtype=float)
            out[f"ETP_{ch}"] = np.zeros((N, T), dtype=float)
        out[f"has_{ch}"] = has

    # 2. Pumping and unattributed pumping (thousand m3/week).
    pw = RT.pumping_table(reconstruction)
    pts = pd.read_parquet(DATASET_DIR / "pumping_points.parquet")
    pe = edges[edges["relation"].isin(("pumping", "pumping_unattributed"))]
    fac = sorted(pe["src"].unique())
    if fac:
        table = RT.facility_volumes(weeks, fac, reconstruction)
        vol = table.reindex(index=weeks, columns=fac).fillna(0.0).to_numpy(dtype=float).T
    else:
        vol = np.zeros((0, T), dtype=float)
    for name, rel in (("pump_gw", "pumping"), ("pump_un", "pumping_unattributed")):
        Wp = RT._matrix(edges, rel, codes, fac) if fac else np.zeros((N, 0), dtype=float)
        out[name] = Wp @ vol if fac else np.zeros((N, T), dtype=float)
        out[f"has_{rel}"] = Wp.sum(axis=1) > 0 if fac else np.zeros(N, dtype=bool)

    # 3. River exchange (weighted mean of log(1 + discharge)).
    riv = river_series(weeks, splits["train"][1], rule=river_rule)
    gauges = sorted(edges.loc[edges["relation"] == "river", "src"].unique())
    if gauges:
        Wr = RT._matrix(edges, "river", codes, gauges)
        tot = Wr.sum(axis=1, keepdims=True)
        out["has_river"] = tot[:, 0] > 0
        out["river"] = np.divide(Wr, tot, out=np.zeros_like(Wr), where=tot > 0) @ riv[gauges].to_numpy(dtype=float).T
    else:
        out["has_river"] = np.zeros(N, dtype=bool)
        out["river"] = np.zeros((N, T), dtype=float)

    # 4. Basin-specific canal volume (Mm3/week) for wells with a canal edge.
    canal_edges = edges[edges["relation"] == "canal"]
    canal_well_set = set(canal_edges["dst"].unique())
    has_canal = np.array([c in canal_well_set for c in codes], dtype=bool)
    out["has_canal"] = has_canal

    wide_basin, canal_mode = _canal_basin_wide(
        weeks, reconstruction, canal_basins_weekly=canal_basins_weekly, canal_intakes_basin=canal_intakes_basin
    )
    out["canal_mode"] = canal_mode
    canal_arr = np.zeros((N, T), dtype=float)
    well_basins = {}

    if wide_basin is not None and has_canal.any():
        basin_cols = set(wide_basin.columns)
        # First check if edges explicitly name a basin on src (e.g. "canal:Tet" or "Tet").
        explicit = {}
        for src_val, dst_val in zip(canal_edges["src"], canal_edges["dst"]):
            suffix = str(src_val).split(":", 1)[-1]
            if str(src_val) in basin_cols:
                explicit[dst_val] = str(src_val)
            elif suffix in basin_cols:
                explicit[dst_val] = suffix

        need_snap = sorted(w for w in canal_well_set if w in codes and w not in explicit)
        snapped_map = {}
        if need_snap:
            sub_edges = canal_edges[canal_edges["dst"].isin(need_snap)]
            wb_df = CB.canal_edge_well_basins(edges_d=sub_edges, wells=wells, reaches=reaches)
            snapped_map = dict(zip(wb_df["code_bss"], wb_df["basin"]))

        cb_start = wide_basin.index.min()
        in_record = weeks >= cb_start
        for i, code in enumerate(codes):
            if not has_canal[i]:
                continue
            basin = explicit.get(code) or snapped_map.get(code)
            if basin is None or basin not in basin_cols:
                raise KeyError(f"Could not resolve canal basin for well {code!r} (got {basin!r})")
            well_basins[code] = basin
            series = wide_basin[basin].reindex(weeks).to_numpy(dtype=float)
            # Fill gaps inside the BNPE/canal record with 0.0; keep pre-record weeks (e.g. 1990-2002)
            # as NaN so hybrid_arrays fills them with the well's training mean instead of a step from 0.
            series = np.where(in_record & ~np.isfinite(series), 0.0, series)
            canal_arr[i] = series
    elif has_canal.any():
        plain = canal_series(pw, pts).reindex(weeks).fillna(0.0).to_numpy(dtype=float) / 1e6
        canal_arr[has_canal] = plain[None, :]

    out["canal"] = canal_arr
    out["well_canal_basin"] = well_basins
    return out


def hybrid_arrays(
    P,
    routed,
    *,
    kernel_weeks=KERNEL_WEEKS,
    river_c_wells=(),
    canal_c_wells=(),
):
    """Build padded ``HybridGNN`` input tensors, targets, splits, and ``channel_mask``."""
    P = P.sort_values(["code_bss", "week"])
    codes = list(dict.fromkeys(P["code_bss"]))
    weeks = np.sort(P["week"].unique())
    N, T = len(codes), len(weeks)
    piv = lambda col: P[col].to_numpy().reshape(N, T)  # noqa: E731
    split = piv("split")
    train = split == "train"

    if not np.array_equal(pd.DatetimeIndex(routed["weeks"]).to_numpy(), pd.DatetimeIndex(weeks).to_numpy()):
        raise ValueError("routed inputs are on different weeks than the panel")
    row = {c: i for i, c in enumerate(routed["codes"])}
    idx = [row[c] for c in codes]

    river_c_set = set(river_c_wells)
    canal_c_set = set(canal_c_wells)
    river_c_mask = np.array([c in river_c_set for c in codes], dtype=bool)
    canal_c_mask = np.array([c in canal_c_set for c in codes], dtype=bool)

    has = {}
    for ch in RECHARGE_CHANNELS:
        has[ch] = np.asarray(routed[f"has_{ch}"], dtype=bool)[idx]
    has["pumping"] = np.asarray(routed["has_pumping"], dtype=bool)[idx]
    has["pumping_unattributed"] = np.asarray(routed["has_pumping_unattributed"], dtype=bool)[idx]
    has_river = np.asarray(routed["has_river"], dtype=bool)[idx]
    has_canal = np.asarray(routed["has_canal"], dtype=bool)[idx]
    has["river_c"] = has_river & river_c_mask
    has["river"] = has_river & ~river_c_mask
    has["canal_c"] = has_canal & canal_c_mask
    has["canal"] = has_canal & ~canal_c_mask

    channel_mask = np.column_stack([has[ch] for ch in CHANNELS]).astype(bool)

    def _pad(arr, active, *, non_negative=False):
        arr = np.asarray(arr, dtype=np.float64).copy()
        mean = np.nanmean(np.where(train, arr, np.nan), axis=1, keepdims=True)
        mean = np.where(np.isfinite(mean), mean, 0.0)
        arr = np.where(np.isfinite(arr), arr, mean)
        padded = np.concatenate([np.repeat(mean, kernel_weeks - 1, axis=1), arr], axis=1)
        if non_negative:
            padded = np.clip(padded, 0.0, None)
        padded = np.where(active[:, None], padded, 0.0)
        return padded.astype(np.float32)

    X = {}
    for ch in RECHARGE_CHANNELS:
        # Keep rain and ETP in mm/week for bucket.bucket.
        X[f"rain_{ch}"] = _pad(np.asarray(routed[f"rain_{ch}"])[idx], has[ch], non_negative=True)
        X[f"ETP_{ch}"] = _pad(np.asarray(routed[f"ETP_{ch}"])[idx], has[ch], non_negative=True)

    X["pump_gw"] = _pad(np.asarray(routed["pump_gw"])[idx] / STRESS_SCALE["pump_gw"], has["pumping"], non_negative=True)
    X["pump_un"] = _pad(
        np.asarray(routed["pump_un"])[idx] / STRESS_SCALE["pump_un"],
        has["pumping_unattributed"],
        non_negative=True,
    )

    riv_raw = np.asarray(routed["river"])[idx] / STRESS_SCALE["river"]
    X["river_c"] = _pad(riv_raw, has["river_c"])
    X["river"] = _pad(riv_raw, has["river"])

    can_raw = np.asarray(routed["canal"])[idx] / STRESS_SCALE["canal"]
    X["canal_c"] = _pad(can_raw, has["canal_c"], non_negative=True)
    X["canal"] = _pad(can_raw, has["canal"], non_negative=True)

    head = piv("head").astype(np.float64)
    mu = piv("mu").astype(np.float64)
    sd = piv("sd").astype(np.float64)
    groups = sorted(P["group"].unique())
    group_of = np.array([groups.index(g) for g in P.drop_duplicates("code_bss")["group"]], dtype=np.int64)

    return {
        "codes": codes,
        "weeks": weeks,
        "X": X,
        "head": head,
        "mu": mu,
        "sd": sd,
        "split": split,
        "core": piv("core").astype(bool),
        "groups": groups,
        "group_of": group_of,
        "channel_mask": channel_mask,
        "river_c_mask": river_c_mask,
        "canal_c_mask": canal_c_mask,
    }


# ---------------------------------------------------------------------------
# Training, outputs, and replay
# ---------------------------------------------------------------------------

def _optimiser_groups(net, weight_decay):
    """Apply AdamW weight decay only to encoder/residual linear weights; never to theta_group or delta."""
    decay_params = []
    no_decay_params = []
    for name, param in net.named_parameters():
        if not param.requires_grad:
            continue
        if name in ("theta_group", "delta") or name.endswith(".bias"):
            no_decay_params.append(param)
        else:
            decay_params.append(param)
    groups = []
    if decay_params:
        groups.append({"params": decay_params, "weight_decay": float(weight_decay)})
    if no_decay_params:
        groups.append({"params": no_decay_params, "weight_decay": 0.0})
    return groups


def train_seed(
    seed,
    data,
    graph_data,
    well_graph_idx=None,
    *,
    epochs=500,
    lr=1e-2,
    weight_decay=1e-4,
    lam_shape=0.1,
    lam_gain=0.01,
    lam_delta=0.1,
    lam_res=None,
    stage="B",
    signs="gate3",
    sign_ref="gate3",
    soft=None,
    soft_stresses=None,
    residual="none",
    kernel_weeks=KERNEL_WEEKS,
    hidden=32,
    heads=2,
    dropout=0.1,
    n_layers=2,
    bucket_smooth=0.0,
    init_sd=0.2,
    train_mask=None,
    keep_wells=None,
    reliable_from=RELIABLE_PUMPING_FROM,
    device=None,
    state_out=None,
    verbose=True,
):
    """Train one seed of ``HybridGNN`` for a fixed number of epochs (no early stopping).

    Returns ``(net, val_median_nse, epochs, loss_history)`` with ``net`` in ``eval()`` mode
    and ``net.centres`` refreshed on CPU from the observed forcing over every well's observed
    training weeks (including held-out wells in LWO).
    """
    torch.manual_seed(seed)
    torch.set_num_threads(int(os.environ.get("PFE_THREADS", 4)))
    gen = torch.Generator().manual_seed(seed)

    dev = torch.device(device) if device is not None else torch.device("cuda" if torch.cuda.is_available() else "cpu")

    head, mu, sd, split, core = (data[k] for k in ("head", "mu", "sd", "split", "core"))
    sd_safe = np.maximum(sd, SD_FLOOR)
    N, T = head.shape

    if train_mask is None:
        train_mask = split == "train"
    if keep_wells is None:
        keep_wells = np.ones(N, dtype=bool)
    else:
        keep_wells = np.asarray(keep_wells, dtype=bool)

    # Loss mask: observed training weeks of training wells only (held-out wells never enter loss).
    obs_loss = np.isfinite(head) & train_mask & keep_wells[:, None]
    # Centring mask: observed training weeks of EVERY well (including held-out LWO wells, using
    # the same training period weeks that define mu_i, never reading any held-out head value).
    # Note: for R3 or refit, train_mask already encodes the time window on kept wells; reconstruct
    # the pure time mask across all wells from train_mask on any kept well (or split == "train").
    if keep_wells.any():
        time_mask = train_mask[np.argmax(keep_wells)]
        obs_centres = np.isfinite(head) & time_mask[None, :]
    else:
        obs_centres = np.isfinite(head) & (split == "train")

    y_np = np.nan_to_num(head - mu).astype(np.float32)
    wgt_np = obs_loss / np.maximum(obs_loss.sum(1, keepdims=True), 1) / sd_safe ** 2
    wgt_np = (wgt_np / max((obs_loss.sum(1) > 0).sum(), 1)).astype(np.float32)

    res_basis = R.seasonal_basis(data["weeks"], harmonics=RESIDUAL_HARMONICS) if residual == "bounded" else None
    res_bound = RESIDUAL_BOUND_SD * sd_safe[:, 0] if residual == "bounded" else None

    net = HybridGNN(
        graph_data=graph_data,
        group_of=data["group_of"],
        n_groups=len(data["groups"]),
        well_graph_idx=well_graph_idx,
        gain_scale=sd_safe[:, 0],
        channel_mask=data.get("channel_mask"),
        stage=stage,
        signs=signs,
        sign_ref=sign_ref,
        soft_stresses=soft_stresses,
        kernel_weeks=kernel_weeks,
        hidden=hidden,
        heads=heads,
        dropout=dropout,
        n_layers=n_layers,
        bucket_smooth=bucket_smooth,
        residual=residual,
        residual_basis=res_basis,
        residual_bound=res_bound,
        train_well_mask=keep_wells,
        init_sd=init_sd,
        generator=gen,
    ).to(dev)

    X_t = {k: torch.from_numpy(np.asarray(v, dtype=np.float32)).to(dev) for k, v in data["X"].items()}
    y_t = torch.from_numpy(y_np).to(dev)
    wgt_t = torch.from_numpy(wgt_np).to(dev)
    obs_centres_t = torch.from_numpy(obs_centres).to(dev)
    loss_mask_t = torch.from_numpy(train_mask & keep_wells[:, None]).to(dev)
    sd_t = torch.from_numpy(sd_safe[:, 0].astype(np.float32)).to(dev)

    if reliable_from is not None:
        wk = pd.DatetimeIndex(data["weeks"])
        rel_np = np.asarray(wk >= pd.Timestamp(reliable_from), dtype=bool)
        reliable_t = torch.from_numpy(rel_np).to(dev)
    else:
        reliable_t = None

    opt = torch.optim.AdamW(_optimiser_groups(net, weight_decay), lr=float(lr))
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        opt, T_max=max(int(epochs), 1), eta_min=float(lr) * 1e-2
    )
    eff_lam_res = float(lam_shape) if lam_res is None else float(lam_res)

    loss_history = []
    t0 = time.time()
    net.train()
    for _ in range(int(epochs)):
        pred, c, dev_raw, eff_delta = net.training_forward(X_t, obs_centres_t, reliable_t)
        loss = (wgt_t * (pred - y_t) ** 2).sum()
        if lam_shape > 0:
            loss = loss + float(lam_shape) * net.shape_penalty(dev=dev_raw)
        if lam_gain > 0:
            loss = loss + float(lam_gain) * net.gain_penalty(dev=dev_raw)
        if stage == "B" and lam_delta > 0:
            loss = loss + float(lam_delta) * net.delta_penalty(eff_delta=eff_delta)
        if soft:
            theta_cur = net.theta_group[net.group_of] + dev_raw
            loss = loss + float(soft) * net.soft_penalty(c, loss_mask_t, sd_t, theta=theta_cur)
        if residual == "bounded" and eff_lam_res > 0:
            loss = loss + eff_lam_res * net.residual_penalty()

        opt.zero_grad()
        loss.backward()
        opt.step()
        scheduler.step()
        loss_history.append(float(loss.detach().cpu().item()))

    # Refresh centres in eval mode under observed forcing (no dropout) before saving/scoring.
    net.eval()
    net.estimate_centres(X_t, obs_centres_t)

    with torch.no_grad():
        pred_eval = net(X_t).detach().cpu().numpy()
    pz = (pred_eval / sd_safe).astype(np.float32)
    es_core = core & keep_wells[:, None]
    val_score = median_nse(pz, head, split, es_core, mu, sd_safe, head)

    net = net.to("cpu")
    if state_out is not None:
        state_out.update({k: v.detach().cpu().clone() for k, v in net.state_dict().items()})

    if verbose:
        last_loss = loss_history[-1] if loss_history else float("nan")
        print(
            f"    seed {seed}: epochs {epochs}, loss {last_loss:.4f}, "
            f"val median NSE {val_score:.3f} ({time.time() - t0:.0f}s)",
            flush=True,
        )
    return net, val_score, int(epochs), loss_history


def _merge_constrained_slot(c_df, p_df, constrained_name, free_name, mask, flag_col):
    """Merge a ``<name>_c`` / ``<name>`` slot pair into one logical column in saved outputs."""
    mask = np.asarray(mask, dtype=bool)
    c_df = c_df.assign(**{free_name: c_df[free_name] + c_df[constrained_name]}).drop(
        columns=constrained_name
    )
    templates = (
        "gain_{}",
        "mean_fast_{}_wk",
        "n_fast_{}",
        "mean_slow_{}_wk",
        "n_slow_{}",
        "w_slow_{}",
        "impl_mean_lag_{}_wk",
        "impl_peak_lag_{}_wk",
        "centre_{}_m",
    )
    for tmpl in templates:
        p_df[tmpl.format(free_name)] = np.where(
            mask, p_df[tmpl.format(constrained_name)], p_df[tmpl.format(free_name)]
        )
    p_df = p_df.drop(columns=[tmpl.format(constrained_name) for tmpl in templates])
    p_df[flag_col] = mask
    return c_df, p_df


def seed_outputs(net, data, graph_data=None):
    """Predictions in z, centred contributions (m), and per-well physical parameters.

    Each saved contribution column is ``c_ir(t) - m_ir`` (metres), so summing the saved
    contribution columns (plus ``residual`` when enabled) equals the predicted head anomaly
    ``y_hat_i(t)`` with no free intercept. Uncentred channel means ``m_ir`` are saved in
    ``params_seed_<k>.csv`` as ``centre_<channel>_m``.
    """
    net.eval()
    device = net.centres.device
    X_t = {k: torch.from_numpy(np.asarray(v, dtype=np.float32)).to(device) for k, v in data["X"].items()}
    with torch.no_grad():
        params = net.parameters_physical(graph_data)
        k_weights = net.kernels(params).cpu().numpy()                         # (N, R, K)
        c_raw = net.contributions(X_t, graph_data).cpu().numpy()              # (N, R, T)
        centres = net.centres.cpu().numpy()                                   # (N, R)
        c_centred = c_raw - centres[:, :, None]
        res = None if net.residual_mlp is None else net.residual(graph_data).cpu().numpy()
        out = c_centred.sum(axis=1)
        if res is not None:
            out = out + res

    pz = (out / np.maximum(data["sd"], SD_FLOOR)).astype(np.float32)
    idx = pd.MultiIndex.from_product(
        [data["codes"], pd.DatetimeIndex(data["weeks"])], names=["code_bss", "week"]
    )
    c_cols = {ch: c_centred[:, r].reshape(-1).astype(np.float32) for r, ch in enumerate(net.names)}
    if res is not None:
        c_cols["residual"] = res.reshape(-1).astype(np.float32)
    c_df = pd.DataFrame(c_cols, index=idx).reset_index()

    lags = np.arange(net.K, dtype=np.float64)
    impl_mean = (k_weights * lags).sum(axis=-1)
    impl_peak = k_weights.argmax(axis=-1)

    p_df = pd.DataFrame({
        "code_bss": data["codes"],
        "group": [data["groups"][g] for g in data["group_of"]],
    })
    gain = params.gain.cpu().numpy()
    mean_fast = params.mean_fast.cpu().numpy()
    n_fast = params.n_fast.cpu().numpy()
    mean_slow = params.mean_slow.cpu().numpy()
    n_slow = params.n_slow.cpu().numpy()
    w_slow = params.w_slow.cpu().numpy()
    s_max = params.s_max.cpu().numpy()
    kappa = params.kappa.cpu().numpy()
    beta = params.beta.cpu().numpy()

    for r, ch in enumerate(net.names):
        p_df[f"gain_{ch}"] = gain[:, r]
        p_df[f"mean_fast_{ch}_wk"] = mean_fast[:, r]
        p_df[f"n_fast_{ch}"] = n_fast[:, r]
        p_df[f"mean_slow_{ch}_wk"] = mean_slow[:, r]
        p_df[f"n_slow_{ch}"] = n_slow[:, r]
        p_df[f"w_slow_{ch}"] = w_slow[:, r]
        p_df[f"impl_mean_lag_{ch}_wk"] = impl_mean[:, r]
        p_df[f"impl_peak_lag_{ch}_wk"] = impl_peak[:, r]
        p_df[f"centre_{ch}_m"] = centres[:, r]

    for c_idx, rch in enumerate(RECHARGE_CHANNELS):
        p_df[f"s_max_{rch}_mm"] = s_max[:, c_idx]
        p_df[f"kappa_{rch}"] = kappa[:, c_idx]
        p_df[f"beta_{rch}"] = beta[:, c_idx]

    if res is not None:
        p_df["residual_bound_m"] = net.res_bound.cpu().numpy()

    river_mask = data.get("river_c_mask")
    if river_mask is None:
        river_mask = np.abs(np.asarray(data["X"]["river_c"])).sum(axis=1) > 0
    c_df, p_df = _merge_constrained_slot(c_df, p_df, "river_c", "river", river_mask, "river_constrained")

    canal_mask = data.get("canal_c_mask")
    if canal_mask is None:
        canal_mask = np.abs(np.asarray(data["X"]["canal_c"])).sum(axis=1) > 0
    c_df, p_df = _merge_constrained_slot(c_df, p_df, "canal_c", "canal", canal_mask, "canal_constrained")

    return pz, c_df, p_df


# ---------------------------------------------------------------------------
# CLI, preparation, and replay
# ---------------------------------------------------------------------------

def _arm_name(s):
    try:
        RT.parse_arm(s)
    except ValueError as err:
        raise argparse.ArgumentTypeError(str(err)) from err
    return s


def build_parser():
    """CLI argument parser mirroring ``src/models/response.py``."""
    ap = argparse.ArgumentParser(description="Hybrid-GNN v2 groundwater model (plan v3 §3)")
    ap.add_argument("--arm", type=_arm_name, default="D", help="graph arm: C, D, or control")
    ap.add_argument("--policy", default="main", help="KG export policy (default: main)")
    ap.add_argument("--regime", choices=list(REGIMES), default="R1", help="evaluation regime")
    ap.add_argument("--fold", type=int, default=None, help="leave-wells-out fold (0-4; regime R2)")
    ap.add_argument("--train-start", default=None, help="explicit R3 training start override")
    ap.add_argument("--run", default=None, help="results sub-folder name")
    ap.add_argument("--seeds", type=int, nargs="*", default=list(range(10)))
    ap.add_argument("--epochs", type=int, default=500, help="fixed training epochs (no early stopping)")
    ap.add_argument("--lr", type=float, default=1e-2)
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--lam-shape", type=float, default=0.1, help="penalty on kernel/bucket spread")
    ap.add_argument("--lam-gain", type=float, default=0.01, help="penalty on gain spread (< lam-shape)")
    ap.add_argument("--lam-delta", type=float, default=0.1, help="stage-B ridge on per-well delta")
    ap.add_argument("--lam-res", type=float, default=None, help="ridge on residual MLP (default: lam-shape)")
    ap.add_argument("--stage", choices=["A", "B"], default="B", help="A: delta=0; B: delta with ridge")
    ap.add_argument("--signs", choices=list(SIGN_SETS), default="gate3")
    ap.add_argument("--sign-ref", choices=["gate3", "structure"], default=None)
    ap.add_argument("--soft", type=float, default=None, help="RQ2 soft sign penalty weight")
    ap.add_argument("--soft-stresses", nargs="+", default=None, help="penalise only these free stresses")
    ap.add_argument("--residual", choices=["none", "bounded"], default="none")
    ap.add_argument("--pumping-reconstruction", type=int, choices=[1, 2, 3], default=1)
    ap.add_argument("--kernel-weeks", type=int, default=KERNEL_WEEKS)
    ap.add_argument("--hidden", type=int, default=32)
    ap.add_argument("--heads", type=int, default=2)
    ap.add_argument("--dropout", type=float, default=0.1)
    ap.add_argument("--n-layers", type=int, default=2)
    ap.add_argument("--bucket-smooth", type=float, default=0.0)
    ap.add_argument("--wells", nargs="*", default=None, help="subset of wells (code_bss)")
    return ap


def _parser_defaults():
    ap = build_parser()
    return {
        a.dest: (list(a.default) if isinstance(a.default, list) else a.default)
        for a in ap._actions
        if a.dest != "help"
    }


def args_from_config(cfg):
    """Rebuild an ``argparse.Namespace`` from a saved ``config.json``."""
    defaults = _parser_defaults()
    values = {k: (cfg[k] if k in cfg else v) for k, v in defaults.items()}
    return argparse.Namespace(**values)


def _canonicalize_args(args, error=None):
    """Validate CLI options and resolve regime, sign, and penalty settings."""
    def fail(msg):
        if error is not None:
            error(msg)
        raise ValueError(msg)

    if args.epochs < 1:
        fail("--epochs must be >= 1")
    for flag, val in (
        ("--lam-shape", args.lam_shape),
        ("--lam-gain", args.lam_gain),
        ("--lam-delta", args.lam_delta),
    ):
        if val < 0:
            fail(f"{flag} must be >= 0")

    regime = args.regime
    fold = args.fold
    train_start = args.train_start
    if fold is not None and regime == "R1":
        regime = "R2"
    if regime == "R2" and fold is None:
        fail("--regime R2 requires --fold 0..4")
    if regime != "R2" and fold is not None:
        fail(f"--fold cannot be combined with --regime {regime}")
    if regime == "R3_f25":
        train_start = train_start or R3_STARTS["f25"]
    elif regime == "R3_f50":
        train_start = train_start or R3_STARTS["f50"]
    refit = regime == "refit"

    sign_ref = args.sign_ref or ("structure" if args.signs == "structure" else "gate3")
    soft_stresses = args.soft_stresses
    if soft_stresses is not None:
        if args.soft is None:
            fail("--soft-stresses needs --soft")
        unknown = sorted(set(soft_stresses) - set(CHANNELS))
        if unknown:
            fail(f"--soft-stresses: unknown channels {unknown}")
        built_in = [s for s in soft_stresses if SIGN_SETS[args.signs][s] != 0.0]
        if built_in:
            fail(f"--soft-stresses {built_in} already have a built-in sign under --signs {args.signs}")
    elif args.soft is not None and args.signs != "none":
        fail("--soft needs --signs none (or --soft-stresses naming free channels)")

    run = args.run or f"hgnn_{args.arm}_stage{args.stage}"
    return {
        "run": run,
        "arm": args.arm,
        "policy": args.policy,
        "regime": regime,
        "fold": fold,
        "train_start": train_start,
        "refit": refit,
        "stage": args.stage,
        "signs": args.signs,
        "sign_ref": sign_ref,
        "soft": args.soft,
        "soft_stresses": soft_stresses,
        "residual": args.residual,
        "reconstruction": args.pumping_reconstruction,
        "only": args.wells,
    }


def _export_dir(policy="main", dataset=DATASET):
    return PROCESSED / "kg" / f"export_{dataset}_{policy}"


def _build_graph_for_arm(arm, policy="main", train_start=None, dataset=DATASET):
    """Build the static ``HeteroData`` for ``arm`` (including control arms from ``load_arm``)."""
    exp_dir = _export_dir(policy, dataset)
    kind, draw = RT.parse_arm(arm)
    if draw is None and kind in ("C", "D"):
        return build_heterodata(exp_dir, arm, train_start=train_start, policy=policy)
    edges, _ = RT.load_arm(arm, policy, dataset)
    return build_heterodata(exp_dir, arm, tables={"edges": edges}, train_start=train_start, policy=policy)


def prepare(args, *, error=None, verbose=True):
    """Build inputs, static ``HeteroData``, masks, fingerprint, schema, and model kwargs."""
    def fail(msg):
        if error is not None:
            error(msg)
        raise ValueError(msg)

    config_args = args_from_config(vars(args))
    opt = _canonicalize_args(config_args, error=error)
    arm, policy = opt["arm"], opt["policy"]
    train_start = opt["train_start"]

    P = build_panel(train_start=train_start)
    P = P[P["mu"].notna()]
    if opt["only"] is not None:
        missing = sorted(set(opt["only"]) - set(P["code_bss"]))
        if missing:
            fail(f"unknown wells: {missing}")
        P = P[P["code_bss"].isin(opt["only"])]

    routed = routed_v5_inputs(arm, policy, reconstruction=opt["reconstruction"])
    river_c = constrained_wells("river", policy=policy)
    canal_c = constrained_wells("canal", policy=policy)
    data = hybrid_arrays(
        P,
        routed,
        kernel_weeks=config_args.kernel_weeks,
        river_c_wells=river_c,
        canal_c_wells=canal_c,
    )

    graph_data, graph_index = _build_graph_for_arm(arm, policy=policy, train_start=train_start)
    well_map = graph_index["well"]
    missing_graph = [c for c in data["codes"] if c not in well_map]
    if missing_graph:
        fail(f"wells missing from HeteroData graph: {missing_graph}")
    well_graph_idx = np.array([well_map[c] for c in data["codes"]], dtype=np.int64)

    train_mask, keep_wells = regime_masks(
        data["split"], data["weeks"], data["codes"], opt["fold"], train_start, refit=opt["refit"]
    )
    sd_safe = np.maximum(data["sd"], SD_FLOOR)
    res_basis = (
        R.seasonal_basis(data["weeks"], harmonics=RESIDUAL_HARMONICS)
        if opt["residual"] == "bounded"
        else None
    )
    res_bound = RESIDUAL_BOUND_SD * sd_safe[:, 0] if opt["residual"] == "bounded" else None

    inputs = (
        [f"rain_{ch}/1" for ch in RECHARGE_CHANNELS]
        + [f"ETP_{ch}/1" for ch in RECHARGE_CHANNELS]
        + [f"{k}/{STRESS_SCALE[k]:g}" for k in ("pump_gw", "pump_un", "river_c", "river", "canal_c", "canal")]
    )
    fp_extra = {
        "model": "hybrid_gnn_v2",
        "reliable_pumping_from": RELIABLE_PUMPING_FROM,
        "canal_mode": routed["canal_mode"],
        "river_constrained_wells": sorted(set(data["codes"]) & river_c),
        "canal_constrained_wells": sorted(set(data["codes"]) & canal_c),
    }
    if routed.get("export"):
        fp_extra["export_release"] = routed["export"].get("release")
        if "export_sha256" in routed["export"]:
            fp_extra["export_sha256"] = routed["export"]["export_sha256"]
    graph_hash = hashlib.sha256(
        np.ascontiguousarray(graph_data["well"].x.numpy(), dtype=np.float32).tobytes()
    ).hexdigest()[:16]
    fp_extra["graph_well_x_sha256_16"] = graph_hash

    fingerprint = run_fingerprint(config_args, inputs, fp_extra)
    schema = {
        "model": "hybrid_gnn_v2",
        "nodes": data["codes"],
        "weeks": [str(data["weeks"][0])[:10], str(data["weeks"][-1])[:10]],
        "inputs": inputs,
        "channels": list(CHANNELS),
        "signs": {ch: SIGN_SETS[opt["signs"]][ch] for ch in CHANNELS},
        "sign_ref": {ch: SIGN_SETS[opt["sign_ref"]][ch] for ch in CHANNELS},
        "arm": arm,
        "policy": policy,
        "stage": opt["stage"],
        "regime": opt["regime"],
        "reliable_pumping_from": RELIABLE_PUMPING_FROM,
        "canal_mode": routed["canal_mode"],
        "well_canal_basin": routed["well_canal_basin"],
        "groups": data["groups"],
        "group_of": data["group_of"].tolist(),
        "kernel_weeks": config_args.kernel_weeks,
        "n_slow_min": N_SLOW_MIN,
        "residual": opt["residual"],
        "export": routed.get("export"),
    }

    model_kwargs = {
        "group_of": data["group_of"],
        "n_groups": len(data["groups"]),
        "well_graph_idx": well_graph_idx,
        "gain_scale": sd_safe[:, 0],
        "channel_mask": data["channel_mask"],
        "stage": opt["stage"],
        "signs": opt["signs"],
        "sign_ref": opt["sign_ref"],
        "soft_stresses": opt["soft_stresses"],
        "kernel_weeks": config_args.kernel_weeks,
        "hidden": config_args.hidden,
        "heads": config_args.heads,
        "dropout": config_args.dropout,
        "n_layers": config_args.n_layers,
        "bucket_smooth": config_args.bucket_smooth,
        "residual": opt["residual"],
        "residual_basis": res_basis,
        "residual_bound": res_bound,
        "train_well_mask": keep_wells,
    }

    if verbose:
        cov = {ch: int(data["channel_mask"][:, i].sum()) for i, ch in enumerate(CHANNELS)}
        print(
            f"HybridGNN arm {arm} ({policy}), stage {opt['stage']}, regime {opt['regime']}: "
            f"{len(data['codes'])} wells x {len(data['weeks'])} weeks; channel coverage {cov}",
            flush=True,
        )

    return opt | {
        "P": P,
        "routed": routed,
        "data": data,
        "graph_data": graph_data,
        "graph_index": graph_index,
        "well_graph_idx": well_graph_idx,
        "train_mask": train_mask,
        "keep_wells": keep_wells,
        "inputs": inputs,
        "fp_extra": fp_extra,
        "fingerprint": fingerprint,
        "schema": schema,
        "config_args": config_args,
        "model_kwargs": model_kwargs,
    }


def _resolve_run_dir(run_dir):
    path = Path(run_dir)
    if (path / "config.json").is_file() or path.is_absolute():
        return path
    return RESULTS / run_dir


def replay(run_dir, seed, *, prep=None):
    """Rebuild a saved ``HybridGNN`` seed from ``config.json`` and ``seed_<seed>.pt``.

    Restores both model weights and the fixed ``centres`` buffer in ``eval()`` mode, and
    returns ``(net, data, graph_data)``.
    """
    folder = _resolve_run_dir(run_dir)
    cfg_path = folder / "config.json"
    if not cfg_path.is_file():
        raise FileNotFoundError(f"Missing config.json in {folder}")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    if cfg.get("dataset") is not None and cfg["dataset"] != DATASET:
        raise ValueError(
            f"{folder}: saved for dataset {cfg['dataset']!r}, active PFE_DATASET is {DATASET!r}"
        )
    if prep is None:
        prep = prepare(args_from_config(cfg), verbose=False)

    net = HybridGNN(graph_data=prep["graph_data"], **prep["model_kwargs"])
    ckpt_path = folder / f"seed_{seed}.pt"
    if not ckpt_path.is_file():
        raise FileNotFoundError(f"Missing checkpoint {ckpt_path}")
    ckpt = load_checkpoint(ckpt_path)
    net.load_state_dict(ckpt["state_dict"], strict=True)
    net.eval()
    return net, prep["data"], prep["graph_data"]


def _require_train_guard():
    if os.environ.get(ALLOW_TRAIN_ENV) != "1":
        raise SystemExit(
            f"Refusing to train HybridGNN without {ALLOW_TRAIN_ENV}=1 "
            "(training runs on Colab, not the laptop)."
        )


def main():
    ap = build_parser()
    args = ap.parse_args()
    _canonicalize_args(args, error=ap.error)
    _require_train_guard()

    prep = prepare(args, error=ap.error, verbose=True)
    P, data, graph_data = prep["P"], prep["data"], prep["graph_data"]
    run = prep["run"]
    fold = prep["fold"]
    out = RESULTS / run / (f"fold_{fold}" if fold is not None else "")
    out.mkdir(parents=True, exist_ok=True)

    fp = write_config(out, prep["config_args"], prep["inputs"], prep["fp_extra"])
    write_schema(out, prep["schema"])

    for s in args.seeds:
        path = out / f"seed_{s}.parquet"
        if cached_seed(path, fp):
            continue
        state = {}
        net, val_score, best_ep, _ = train_seed(
            s,
            data,
            graph_data,
            prep["well_graph_idx"],
            epochs=args.epochs,
            lr=args.lr,
            weight_decay=args.weight_decay,
            lam_shape=args.lam_shape,
            lam_gain=args.lam_gain,
            lam_delta=args.lam_delta,
            lam_res=args.lam_res,
            stage=prep["stage"],
            signs=prep["signs"],
            sign_ref=prep["sign_ref"],
            soft=prep["soft"],
            soft_stresses=prep["soft_stresses"],
            residual=prep["residual"],
            kernel_weeks=args.kernel_weeks,
            hidden=args.hidden,
            heads=args.heads,
            dropout=args.dropout,
            n_layers=args.n_layers,
            bucket_smooth=args.bucket_smooth,
            train_mask=prep["train_mask"],
            keep_wells=prep["keep_wells"],
            state_out=state,
            verbose=True,
        )
        pz, contrib, params = seed_outputs(net, data, graph_data)
        contrib.to_parquet(out / f"contrib_seed_{s}.parquet", index=False)
        params.to_csv(out / f"params_seed_{s}.csv", index=False)
        save_seed_model(out, s, state, val_score, best_ep, fp)
        save_seed(path, pz, data["codes"], data["weeks"], val_score, best_ep, fp)
        write_manifest(out, vars(prep["config_args"]) | {"fingerprint": fp}, [s])

    if fold is not None:
        return

    pred, n = seed_mean_predictions(out, P.assign(sd=P["sd"].clip(lower=SD_FLOOR)), args.seeds)
    pred.to_parquet(out / "predictions.parquet", index=False)
    summary = evaluate_run(run)
    core_s = summary[(summary["group"] == "all core") & (summary["variant"] == "all")]
    print(f"== {run} ({n} seeds)")
    print(core_s[["split", "n_wells", "NSE", "skill", "KGE", "RMSE"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
