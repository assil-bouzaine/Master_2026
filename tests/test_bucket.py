"""Checks of the monotone weekly soil bucket (src/models/bucket.py).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_bucket

1. Exact-mode PyTorch matches the pure-NumPy reference to 1e-10 (float64) on random
   positive P and ETP (N=3, C=2, T=300), and raw_to_params respects the physical bounds.
2. Monotonicity by finite differences (exact and smooth, tau = 1 mm): 200 random
   (week t0, size delta > 0) perturbations on P and 200 on ETP -> +delta on P changes R
   by >= -1e-9 everywhere and by exactly 0 before t0; +delta on ETP changes R by <= +1e-9
   everywhere and by exactly 0 before t0. Zero violations.
3. Water balance (exact mode): sum(P) = sum(R) + sum(E) + S_final - S0 when beta = 0,
   and sum(P) = sum(R) + (1 - beta) * sum(E) + (1 - beta) * (S_final - S0) for general
   bypass beta in (0, 0.9), both to 1e-8.
4. Physical limits: beta -> 1 gives R = P; with ETP = 0, beta = 0 and very large S_max,
   R matches the closed-form linear-reservoir recursion Q_t = kappa * S1_t.
5. Autograd gradients: torch.autograd.gradcheck passes on a tiny float64 example in
   smooth mode (both direct physical parameters and through raw_to_params).
6. Timing: N * C = 200, T = 1,900 weeks, one forward + backward pass in float32.
"""
import time

import numpy as np
import torch

from src.models.bucket import (
    BETA_MAX,
    BETA_MIN,
    DEFAULT_BOUNDS,
    KAPPA_MAX,
    KAPPA_MIN,
    S_MAX_MAX,
    S_MAX_MIN,
    bucket,
    bucket_reference,
    raw_to_params,
)


def _sample_params(rng, N, C, spread=2.5):
    """Draw random raw parameters and map them into the physical bounds (float64)."""
    raw = torch.from_numpy(rng.normal(0.0, spread, size=(N, C, 3)).astype(np.float64))
    return raw_to_params(raw)


def test_matches_reference():
    rng = np.random.default_rng(101)
    N, C, T = 3, 2, 300
    # Positive rain and ETP spanning dry weeks, moderate rain, and heavy storms (mm/week)
    P_np = rng.gamma(0.5, 25.0, size=(N, C, T)).astype(np.float64) + 1e-3
    ETP_np = (5.0 + rng.gamma(2.0, 12.0, size=(N, C, T))).astype(np.float64)

    raw = torch.from_numpy(rng.normal(0.0, 2.0, size=(N, C, 3)).astype(np.float64))
    s_max, kappa, beta = raw_to_params(raw)
    assert (s_max > S_MAX_MIN).all() and (s_max < S_MAX_MAX).all()
    assert (kappa > KAPPA_MIN).all() and (kappa < KAPPA_MAX).all()
    assert (beta > BETA_MIN).all() and (beta < BETA_MAX).all()

    # Check tuple and dict input containers give identical parameters
    s2, k2, b2 = raw_to_params((raw[..., 0], raw[..., 1], raw[..., 2]))
    s3, k3, b3 = raw_to_params({"s_max": raw[..., 0], "kappa": raw[..., 1], "beta": raw[..., 2]},
                               bounds=DEFAULT_BOUNDS)
    assert torch.equal(s_max, s2) and torch.equal(kappa, k2) and torch.equal(beta, b2)
    assert torch.equal(s_max, s3) and torch.equal(kappa, k3) and torch.equal(beta, b3)

    # Check default s0 (= s_max / 2) and custom s0
    P_t = torch.from_numpy(P_np)
    ETP_t = torch.from_numpy(ETP_np)
    R_torch, S_torch = bucket(P_t, ETP_t, s_max, kappa, beta, smooth=0.0)
    R_ref, S_ref = bucket_reference(P_np, ETP_np, s_max.numpy(), kappa.numpy(), beta.numpy())

    max_r = float(np.max(np.abs(R_torch.numpy() - R_ref)))
    max_s = float(np.max(np.abs(S_torch.numpy() - S_ref)))
    assert max_r < 1e-10, f"R mismatch: {max_r}"
    assert max_s < 1e-10, f"S_final mismatch: {max_s}"

    s0_custom = (0.2 * s_max).clone()
    R_t2, S_t2 = bucket(P_t, ETP_t, s_max, kappa, beta, s0=s0_custom, smooth=0.0)
    R_r2, S_r2 = bucket_reference(P_np, ETP_np, s_max.numpy(), kappa.numpy(), beta.numpy(),
                                  s0=s0_custom.numpy())
    assert float(np.max(np.abs(R_t2.numpy() - R_r2))) < 1e-10
    assert float(np.max(np.abs(S_t2.numpy() - S_r2))) < 1e-10

    print(f"  1. torch exact vs numpy reference (N={N}, C={C}, T={T}, float64): "
          f"max |dR|={max_r:.2e}, max |dS_final|={max_s:.2e}; raw_to_params bounds ok")


def test_monotonicity():
    rng = np.random.default_rng(202)
    N, C, T = 4, 2, 120
    n_perturb = 200
    tol = 1e-9

    summary = []
    for smooth in (0.0, 1.0):
        # Include dry weeks (P = 0) and storms to hit both empty-soil and overflow regimes
        P_np = np.where(rng.random((N, C, T)) < 0.35, 0.0, rng.gamma(0.6, 20.0, size=(N, C, T)))
        ETP_np = (2.0 + rng.gamma(2.0, 14.0, size=(N, C, T))).astype(np.float64)
        P_base = torch.from_numpy(P_np.astype(np.float64))
        ETP_base = torch.from_numpy(ETP_np)

        # Draw parameters spanning the full bounds (including small S_max near 10 mm)
        s_max, kappa, beta = _sample_params(rng, N, C, spread=3.5)
        with torch.no_grad():
            R_base, _ = bucket(P_base, ETP_base, s_max, kappa, beta, smooth=smooth)

        p_viol = 0
        p_causal_viol = 0
        etp_viol = 0
        etp_causal_viol = 0
        worst_p_min = float("inf")
        worst_etp_max = float("-inf")

        for _ in range(n_perturb):
            t0 = int(rng.integers(0, T))
            delta_p = float(rng.uniform(0.05, 60.0))
            P_pert = P_base.clone()
            P_pert[:, :, t0] += delta_p
            with torch.no_grad():
                R_p, _ = bucket(P_pert, ETP_base, s_max, kappa, beta, smooth=smooth)
            dR_p = R_p - R_base
            if t0 > 0 and float(dR_p[:, :, :t0].abs().max().item()) != 0.0:
                p_causal_viol += 1
            min_dR_p = float(dR_p.min().item())
            worst_p_min = min(worst_p_min, min_dR_p)
            if min_dR_p < -tol:
                p_viol += 1

            delta_e = float(rng.uniform(0.05, 60.0))
            ETP_pert = ETP_base.clone()
            ETP_pert[:, :, t0] += delta_e
            with torch.no_grad():
                R_e, _ = bucket(P_base, ETP_pert, s_max, kappa, beta, smooth=smooth)
            dR_e = R_e - R_base
            if t0 > 0 and float(dR_e[:, :, :t0].abs().max().item()) != 0.0:
                etp_causal_viol += 1
            max_dR_e = float(dR_e.max().item())
            worst_etp_max = max(worst_etp_max, max_dR_e)
            if max_dR_e > tol:
                etp_viol += 1

        assert p_viol == 0 and p_causal_viol == 0, (smooth, p_viol, p_causal_viol, worst_p_min)
        assert etp_viol == 0 and etp_causal_viol == 0, (smooth, etp_viol, etp_causal_viol, worst_etp_max)
        label = "exact" if smooth == 0.0 else f"smooth(tau={smooth:g})"
        summary.append(
            f"{label}: {n_perturb} P / {n_perturb} ETP perturbations -> "
            f"0 P viol (min dR={worst_p_min:.2e}), 0 ETP viol (max dR={worst_etp_max:.2e}), 0 causal viol"
        )

    print("  2. monotonicity (finite differences): " + "; ".join(summary))


def test_water_balance():
    rng = np.random.default_rng(303)
    N, C, T = 4, 3, 400
    P_np = rng.gamma(0.7, 18.0, size=(N, C, T)).astype(np.float64)
    ETP_np = (3.0 + rng.gamma(2.0, 10.0, size=(N, C, T))).astype(np.float64)
    s_max, kappa, beta = _sample_params(rng, N, C, spread=2.0)
    s_max_np, kappa_np, beta_np = s_max.numpy(), kappa.numpy(), beta.numpy()
    s0_np = 0.5 * s_max_np

    # (a) Pure soil bucket (beta = 0): sum(P) = sum(R) + sum(E) + S_final - S0
    zeros_beta = np.zeros_like(beta_np)
    R_ref0, S_ref0, E0 = bucket_reference(P_np, ETP_np, s_max_np, kappa_np, zeros_beta,
                                          s0=s0_np, return_evap=True)
    R_t0, S_t0 = bucket(torch.from_numpy(P_np), torch.from_numpy(ETP_np),
                        s_max, kappa, torch.zeros_like(beta), smooth=0.0)
    bal_zero = P_np.sum(axis=-1) - (R_t0.numpy().sum(axis=-1) + E0.sum(axis=-1) + S_t0.numpy() - s0_np)
    err_zero = float(np.max(np.abs(bal_zero)))
    assert err_zero < 1e-8, f"Water balance error (beta=0): {err_zero}"
    assert float(np.max(np.abs(R_t0.numpy() - R_ref0))) < 1e-10
    assert float(np.max(np.abs(S_t0.numpy() - S_ref0))) < 1e-10

    # (b) With bypass beta > 0: fraction (1 - beta) goes through the soil column and fraction beta
    # bypasses directly into recharge (no storage, no evaporation):
    #     sum(P) = sum(R) + (1 - beta) * sum(E) + (1 - beta) * (S_final - S0)
    R_ref, S_ref, E = bucket_reference(P_np, ETP_np, s_max_np, kappa_np, beta_np,
                                       s0=s0_np, return_evap=True)
    R_t, S_t = bucket(torch.from_numpy(P_np), torch.from_numpy(ETP_np),
                      s_max, kappa, beta, smooth=0.0)
    bal_bypass = P_np.sum(axis=-1) - (
        R_t.numpy().sum(axis=-1)
        + (1.0 - beta_np) * E.sum(axis=-1)
        + (1.0 - beta_np) * (S_t.numpy() - s0_np)
    )
    err_bypass = float(np.max(np.abs(bal_bypass)))
    assert err_bypass < 1e-8, f"Water balance error (beta>0): {err_bypass}"
    assert float(np.max(np.abs(R_t.numpy() - R_ref))) < 1e-10
    assert float(np.max(np.abs(S_t.numpy() - S_ref))) < 1e-10

    print(f"  3. water balance (exact mode, N={N}, C={C}, T={T}): "
          f"max |err|={err_zero:.2e} (beta=0), {err_bypass:.2e} (random beta in (0, 0.9))")


def test_limits():
    rng = np.random.default_rng(404)
    N, C, T = 3, 2, 150
    P = torch.from_numpy(rng.gamma(0.8, 15.0, size=(N, C, T)).astype(np.float64))
    ETP = torch.from_numpy((5.0 + rng.gamma(2.0, 10.0, size=(N, C, T))).astype(np.float64))
    s_max, kappa, _ = _sample_params(rng, N, C, spread=1.5)

    # Limit A: beta -> 1 gives R = P
    beta_one = torch.ones((N, C), dtype=torch.float64)
    R_one, _ = bucket(P, ETP, s_max, kappa, beta_one, smooth=0.0)
    err_b1 = float((R_one - P).abs().max().item())
    assert err_b1 < 1e-12, f"beta=1 error: {err_b1}"

    eps = 1e-6
    R_near, _ = bucket(P, ETP, s_max, kappa, torch.full((N, C), 1.0 - eps, dtype=torch.float64), smooth=0.0)
    err_bnear = float((R_near - P).abs().max().item())
    assert err_bnear < 1e-3, f"beta=1-1e-6 error: {err_bnear}"

    # Limit B: ETP = 0, beta = 0, S_max very large -> linear reservoir Q_t = kappa * (S_{t-1} + P_t)
    # Closed form: Q_t = kappa * ((1 - kappa)^t * s0 + sum_{j=0..t} (1 - kappa)^(t - j) * P_j)
    ETP_zero = torch.zeros_like(ETP)
    s_max_big = torch.full((N, C), 1e8, dtype=torch.float64)
    s0 = torch.from_numpy(rng.uniform(10.0, 100.0, size=(N, C)).astype(np.float64))
    beta_zero = torch.zeros((N, C), dtype=torch.float64)

    R_lin_exact, S_lin_exact = bucket(P, ETP_zero, s_max_big, kappa, beta_zero, s0=s0, smooth=0.0)
    R_lin_smooth, S_lin_smooth = bucket(P, ETP_zero, s_max_big, kappa, beta_zero, s0=s0, smooth=1.0)

    # Compute the analytical closed form directly (no bucket loop)
    k_np = kappa.numpy()
    r_np = 1.0 - k_np
    s0_np = s0.numpy()
    P_np = P.numpy()
    Q_closed = np.empty((N, C, T), dtype=np.float64)
    for t in range(T):
        # Powers (1 - kappa)^(t - j) for j = 0 .. t
        exponents = np.arange(t, -1, -1, dtype=np.float64)
        weights = r_np[:, :, None] ** exponents[None, None, :]
        Q_closed[:, :, t] = k_np * (
            (r_np ** t) * s0_np + np.sum(weights * P_np[:, :, : t + 1], axis=-1)
        )
    S_closed = (r_np ** T) * s0_np + np.sum(
        (r_np[:, :, None] ** np.arange(T, 0, -1, dtype=np.float64)[None, None, :]) * P_np,
        axis=-1,
    )

    err_lin_exact = float(np.max(np.abs(R_lin_exact.numpy() - Q_closed)))
    err_s_exact = float(np.max(np.abs(S_lin_exact.numpy() - S_closed)))
    err_lin_smooth = float(np.max(np.abs(R_lin_smooth.numpy() - Q_closed)))
    assert err_lin_exact < 1e-10 and err_s_exact < 1e-10, (err_lin_exact, err_s_exact)
    assert err_lin_smooth < 1e-10, err_lin_smooth

    print(f"  4. limits: beta=1 max |R-P|={err_b1:.2e} (beta=1-1e-6: {err_bnear:.2e}); "
          f"linear reservoir max |R-Q_closed|={err_lin_exact:.2e} (exact), {err_lin_smooth:.2e} (smooth)")


def test_gradcheck():
    rng = np.random.default_rng(505)
    N, C, T = 2, 2, 10
    # Mix small and heavy weekly rain so S2 crosses S_max both ways during the 10 weeks
    P = torch.from_numpy(rng.uniform(5.0, 90.0, size=(N, C, T)).astype(np.float64)).requires_grad_(True)
    ETP = torch.from_numpy(rng.uniform(2.0, 25.0, size=(N, C, T)).astype(np.float64)).requires_grad_(True)
    s_max = torch.from_numpy(rng.uniform(40.0, 120.0, size=(N, C)).astype(np.float64)).requires_grad_(True)
    kappa = torch.from_numpy(rng.uniform(0.1, 0.6, size=(N, C)).astype(np.float64)).requires_grad_(True)
    beta = torch.from_numpy(rng.uniform(0.05, 0.5, size=(N, C)).astype(np.float64)).requires_grad_(True)
    s0 = torch.from_numpy(rng.uniform(20.0, 60.0, size=(N, C)).astype(np.float64)).requires_grad_(True)

    ok_direct = torch.autograd.gradcheck(
        lambda p, e, sm, k, b, init: bucket(p, e, sm, k, b, s0=init, smooth=1.0),
        (P, ETP, s_max, kappa, beta, s0),
        eps=1e-6,
        atol=1e-5,
        rtol=1e-4,
    )
    assert ok_direct

    raw = torch.from_numpy(rng.normal(0.0, 0.7, size=(N, C, 3)).astype(np.float64)).requires_grad_(True)
    ok_raw = torch.autograd.gradcheck(
        lambda p, e, r: bucket(p, e, *raw_to_params(r), smooth=1.0),
        (P, ETP, raw),
        eps=1e-6,
        atol=1e-5,
        rtol=1e-4,
    )
    assert ok_raw
    print(f"  5. torch.autograd.gradcheck (float64, smooth=1.0, N={N}, C={C}, T={T}): "
          f"direct params and raw_to_params passed")


def test_timing():
    rng = np.random.default_rng(606)
    N, C, T = 100, 2, 1900  # N * C = 200, T = 1,900 weeks
    P = torch.from_numpy(rng.gamma(0.5, 20.0, size=(N, C, T)).astype(np.float32))
    ETP = torch.from_numpy((5.0 + rng.gamma(2.0, 10.0, size=(N, C, T))).astype(np.float32))

    times = {}
    for label, smooth in (("exact", 0.0), ("smooth", 1.0)):
        raw = torch.from_numpy(rng.normal(0.0, 1.0, size=(N, C, 3)).astype(np.float32)).requires_grad_(True)
        t0 = time.perf_counter()
        s_max, kappa, beta = raw_to_params(raw)
        R, S_final = bucket(P, ETP, s_max, kappa, beta, smooth=smooth)
        loss = R.mean() + 0.0 * S_final.mean()
        loss.backward()
        elapsed = time.perf_counter() - t0
        assert torch.isfinite(R).all() and torch.isfinite(S_final).all()
        assert raw.grad is not None and torch.isfinite(raw.grad).all()
        assert float(raw.grad.abs().sum().item()) > 0.0
        times[label] = elapsed

    print(f"  6. timing (N*C={N * C}, T={T}, float32, 1 fwd+bwd): "
          f"exact={times['exact']:.3f}s, smooth(tau=1)={times['smooth']:.3f}s")


if __name__ == "__main__":
    test_matches_reference()
    test_monotonicity()
    test_water_balance()
    test_limits()
    test_gradcheck()
    test_timing()
    print("test_bucket: all checks passed")
