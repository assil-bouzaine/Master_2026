"""Monotone weekly soil-water bucket for Hybrid-GNN v2 (analysis plan v3 §3.3).

Why this module exists
----------------------
In v4 (`src/models/response.py`), recharge entered the groundwater response as a linear
combination ``rain - f * ETP``. A linear formula cannot capture two common hydrological
behaviours in the Roussillon plain:
- a dry soil that holds the first autumn rains until storage builds up, and
- a karst conduit system that sends part of the rainfall straight down to the water table.

This module replaces that linear stress with a weekly soil bucket (one per well and
recharge channel), inspired by Pastas' FlexModel family. Given weekly rain ``P`` (mm) and
potential evapotranspiration ``ETP`` (mm), the bucket tracks soil storage ``S`` (mm,
starting from ``S0 = S_max / 2``) and outputs weekly recharge ``R`` (mm):

    S1     = S + P
    S2     = S1 * exp(-ETP / S_max)        # soil evaporation E = S1 - S2
    O      = max(S2 - S_max, 0)            # saturation overflow above capacity
    S3     = min(S2, S_max)                # water left in the soil column
    Q      = kappa * S3                    # linear-reservoir percolation
    S_next = S3 - Q
    R      = (1 - beta) * (O + Q) + beta * P

Parameters per (well, channel):
- ``s_max > 0`` (mm): soil storage capacity.
- ``kappa in (0, 1)``: fraction of stored soil water that percolates each week.
- ``beta in [0, 1)``: fast bypass fraction (e.g. open karst fissures).

Why monotonicity holds by construction
--------------------------------------
The LULC-Water ontology requires that more rain never lowers the head and higher ETP
never raises it. Every step of the bucket preserves those signs:
1. ``S1 = S + P`` grows with ``S`` and ``P``.
2. For ``S1 >= 0`` and ``s_max > 0``, ``S2 = S1 * exp(-ETP / s_max)`` grows with ``S1``
   and shrinks as ``ETP`` increases.
3. Both ``O`` and ``S3`` are non-decreasing in ``S2`` — in exact mode (``max``/``min``)
   and in smooth mode (where ``max(x, 0)`` becomes ``tau * softplus(x / tau)`` and
   ``min(x, m)`` becomes ``m - tau * softplus((m - x) / tau)``, floored at 0 so storage
   never turns negative in bone-dry weeks).
4. Because ``kappa in (0, 1)``, both ``Q = kappa * S3`` and ``S_next = (1 - kappa) * S3``
   are non-decreasing in ``S3``.
5. Because ``beta in [0, 1]``, ``R = (1 - beta) * (O + Q) + beta * P`` is non-decreasing
   in ``O``, ``Q`` and ``P``.

By induction over weeks, raising ``P`` at week ``t0`` can only raise or leave unchanged
``S`` and ``R`` at every week ``t >= t0`` (and never affects weeks ``t < t0``). Raising
``ETP`` at week ``t0`` can only lower or leave unchanged ``S`` and ``R`` at ``t >= t0``.

Water balance interpretation
----------------------------
In exact mode, the soil column (area fraction ``1 - beta``) conserves water week by week:
``P = (O + Q) + E + S_next - S``. The bypass fraction ``beta`` routes ``beta * P``
directly to recharge with zero storage and zero evaporation. Averaged over the whole
catchment area, total mass balance over ``T`` weeks is therefore:

    sum(P) = sum(R) + (1 - beta) * sum(E) + (1 - beta) * (S_final - S0)

which reduces to ``sum(P) = sum(R) + sum(E) + S_final - S0`` when ``beta = 0``.
"""
import math

import numpy as np
import torch
import torch.nn.functional as F

# Physical parameter bounds (same sigmoid parameterisation style as src/models/response.py).
S_MAX_MIN, S_MAX_MAX = 10.0, 1000.0   # mm, mapped on a log scale
KAPPA_MIN, KAPPA_MAX = 0.001, 0.9     # weekly percolation fraction
BETA_MIN, BETA_MAX = 0.0, 0.9         # fast bypass fraction

DEFAULT_BOUNDS = {
    "s_max": (S_MAX_MIN, S_MAX_MAX),
    "kappa": (KAPPA_MIN, KAPPA_MAX),
    "beta": (BETA_MIN, BETA_MAX),
}

# Softplus switches to linear above this threshold. At 40, exp(-40) ~ 4e-18 is below
# float64 machine epsilon while exp(40) ~ 2.35e17 stays well below float32 max, keeping
# smooth derivatives exact for float64 gradcheck and safe in float32.
SOFTPLUS_THRESHOLD = 40.0


def _parse_bounds(bounds):
    """Unpack and validate parameter bounds from a dict or a 3-tuple of (low, high) pairs."""
    if isinstance(bounds, dict):
        s_lo, s_hi = bounds["s_max"]
        k_lo, k_hi = bounds["kappa"]
        b_lo, b_hi = bounds["beta"]
    else:
        (s_lo, s_hi), (k_lo, k_hi), (b_lo, b_hi) = bounds
    if not (0.0 < s_lo < s_hi):
        raise ValueError(f"s_max bounds must satisfy 0 < low < high, got {(s_lo, s_hi)}")
    if not (0.0 <= k_lo < k_hi <= 1.0):
        raise ValueError(f"kappa bounds must lie in [0, 1] with low < high, got {(k_lo, k_hi)}")
    if not (0.0 <= b_lo < b_hi <= 1.0):
        raise ValueError(f"beta bounds must lie in [0, 1] with low < high, got {(b_lo, b_hi)}")
    return (float(s_lo), float(s_hi)), (float(k_lo), float(k_hi)), (float(b_lo), float(b_hi))


def raw_to_params(raw, bounds=DEFAULT_BOUNDS):
    """Map unconstrained raw tensors to bounded physical bucket parameters.

    ``raw`` may be:
    - a tensor of shape ``(..., 3)`` whose last axis is ``(s_max, kappa, beta)``,
    - a 3-tuple/list ``(raw_s_max, raw_kappa, raw_beta)`` of tensors, or
    - a dict with keys ``"s_max"``, ``"kappa"``, ``"beta"``.

    Returns ``(s_max, kappa, beta)`` where ``s_max`` is mapped on a log scale and
    ``kappa``, ``beta`` are mapped linearly through ``torch.sigmoid``.
    """
    (s_lo, s_hi), (k_lo, k_hi), (b_lo, b_hi) = _parse_bounds(bounds)
    if isinstance(raw, dict):
        raw_s, raw_k, raw_b = raw["s_max"], raw["kappa"], raw["beta"]
    elif isinstance(raw, (tuple, list)):
        if len(raw) != 3:
            raise ValueError(f"Expected 3 raw tensors (s_max, kappa, beta), got {len(raw)}")
        raw_s, raw_k, raw_b = raw
    elif isinstance(raw, torch.Tensor):
        if raw.ndim < 1 or raw.shape[-1] != 3:
            raise ValueError(f"Expected raw tensor with last dimension 3, got shape {tuple(raw.shape)}")
        raw_s, raw_k, raw_b = raw.unbind(-1)
    else:
        raise TypeError(f"Unsupported raw parameter container: {type(raw).__name__}")

    log_lo, log_hi = math.log(s_lo), math.log(s_hi)
    s_max = torch.exp(log_lo + torch.sigmoid(raw_s) * (log_hi - log_lo))
    kappa = k_lo + torch.sigmoid(raw_k) * (k_hi - k_lo)
    beta = b_lo + torch.sigmoid(raw_b) * (b_hi - b_lo)
    return s_max, kappa, beta


def _validate_shapes(P, ETP, s_max, kappa, beta, s0):
    if P.ndim != 3 or ETP.ndim != 3 or P.shape != ETP.shape:
        raise ValueError(f"P and ETP must both be 3D (N, C, T), got {tuple(P.shape)} and {tuple(ETP.shape)}")
    nc = P.shape[:2]
    for name, arr in (("s_max", s_max), ("kappa", kappa), ("beta", beta)):
        if arr.shape != nc:
            raise ValueError(f"{name} must have shape {nc}, got {tuple(arr.shape)}")
    if s0 is not None and s0.shape != nc:
        raise ValueError(f"s0 must have shape {nc}, got {tuple(s0.shape)}")


def bucket(P, ETP, s_max, kappa, beta, s0=None, smooth=0.0):
    """Run the monotone weekly soil bucket in PyTorch.

    Parameters
    ----------
    P, ETP : torch.Tensor, shape ``(N, C, T)``
        Weekly precipitation and potential evapotranspiration in mm (non-negative).
    s_max, kappa, beta : torch.Tensor, shape ``(N, C)``
        Per-(well, channel) soil capacity (mm), percolation fraction, and bypass fraction.
    s0 : torch.Tensor, shape ``(N, C)``, optional
        Initial storage in mm. Defaults to ``s_max / 2``.
    smooth : float, default ``0.0``
        Softplus temperature ``tau`` in mm. ``0.0`` uses exact ``max``/``min``;
        ``smooth > 0`` uses smooth softplus overflow and storage cap.

    Returns
    -------
    R : torch.Tensor, shape ``(N, C, T)``
        Weekly groundwater recharge in mm.
    S_final : torch.Tensor, shape ``(N, C)``
        Soil storage (mm) after the last week.
    """
    _validate_shapes(P, ETP, s_max, kappa, beta, s0)
    tau = float(smooth)
    if tau < 0.0:
        raise ValueError(f"smooth must be >= 0, got {smooth}")

    storage = 0.5 * s_max if s0 is None else s0
    if P.shape[-1] == 0:
        return torch.empty_like(P), storage

    # Precompute the weekly evaporative decay factor across all (N, C, T) in one op:
    # exp(-ETP / s_max) does not depend on storage, saving T kernel launches in the loop.
    decay = torch.exp(-ETP / s_max.unsqueeze(-1))
    p_steps = P.unbind(-1)
    d_steps = decay.unbind(-1)
    soil_out = []

    if tau == 0.0:
        for p_t, d_t in zip(p_steps, d_steps):
            s1 = storage + p_t
            s2 = s1 * d_t
            overflow = torch.clamp(s2 - s_max, min=0.0)
            s3 = torch.minimum(s2, s_max)
            q_t = kappa * s3
            storage = s3 - q_t
            soil_out.append(overflow + q_t)
    else:
        inv_tau = 1.0 / tau
        for p_t, d_t in zip(p_steps, d_steps):
            s1 = storage + p_t
            s2 = s1 * d_t
            overflow = tau * F.softplus((s2 - s_max) * inv_tau, threshold=SOFTPLUS_THRESHOLD)
            # Algebraically identical to s_max - tau * softplus((s_max - s2) / tau) because
            # softplus(u) - softplus(-u) = u, while avoiding cancellation when s_max >> s2.
            # Floor at 0: at S2 = 0, s2 - overflow = -tau * log(1 + exp(-s_max / tau)) < 0;
            # keeping S3 >= 0 ensures S_next >= 0 so S2 = S1 * exp(-ETP / s_max) stays
            # non-increasing in ETP even in dry weeks.
            s3 = torch.clamp(s2 - overflow, min=0.0)
            q_t = kappa * s3
            storage = s3 - q_t
            soil_out.append(overflow + q_t)

    soil_flux = torch.stack(soil_out, dim=-1)
    R = (1.0 - beta).unsqueeze(-1) * soil_flux + beta.unsqueeze(-1) * P
    return R, storage


def bucket_reference(P, ETP, s_max, kappa, beta, s0=None, return_evap=False):
    """Pure-NumPy exact-mode reference implementation of the soil bucket (float64).

    Used by unit tests to verify the PyTorch implementation and water balance.
    When ``return_evap=True``, returns ``(R, S_final, E)`` where ``E`` is the weekly
    soil-column evaporation ``S1 - S2`` (mm), shape ``(N, C, T)``.
    """
    P = np.asarray(P, dtype=np.float64)
    ETP = np.asarray(ETP, dtype=np.float64)
    s_max = np.asarray(s_max, dtype=np.float64)
    kappa = np.asarray(kappa, dtype=np.float64)
    beta = np.asarray(beta, dtype=np.float64)
    s0_arr = None if s0 is None else np.asarray(s0, dtype=np.float64)
    _validate_shapes(P, ETP, s_max, kappa, beta, s0_arr)

    N, C, T = P.shape
    storage = (0.5 * s_max).copy() if s0_arr is None else s0_arr.copy()
    R = np.empty((N, C, T), dtype=np.float64)
    E = np.empty((N, C, T), dtype=np.float64) if return_evap else None

    for t in range(T):
        p_t = P[:, :, t]
        etp_t = ETP[:, :, t]
        s1 = storage + p_t
        s2 = s1 * np.exp(-etp_t / s_max)
        if return_evap:
            E[:, :, t] = s1 - s2
        overflow = np.maximum(s2 - s_max, 0.0)
        s3 = np.minimum(s2, s_max)
        q_t = kappa * s3
        storage = s3 - q_t
        R[:, :, t] = (1.0 - beta) * (overflow + q_t) + beta * p_t

    if return_evap:
        return R, storage, E
    return R, storage
