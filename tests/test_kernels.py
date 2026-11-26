"""Toy checks of the two-component kernels (analysis plan v3 §3.4).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v5 .venv/bin/python -m tests.test_kernels

Check normalisation, mixture limits, mean-lag sampling and truncation errors,
agreement with response.py, causal convolution, and all five raw gradients.
No data files, optimisation steps, or model fits are used.
"""
import math
import time

import torch

from src.models import response
from src.models.kernels import (
    KERNEL_WEEKS,
    MEAN_FAST_MIN, MEAN_FAST_MAX,
    MEAN_SLOW_MIN, MEAN_SLOW_MAX,
    N_MIN, N_MAX, N_SLOW_MIN,
    causal_conv, gamma_weights, mixture_weights, raw_to_kernel_params,
)


def _raw(dtype, seed, shape=(4, 3, 5)):
    return 3 * torch.randn(shape, dtype=dtype, generator=torch.Generator().manual_seed(seed))


def test_weights_and_bounds():
    largest_sum_error = 0.0
    for dtype, tol in ((torch.float64, 1e-12), (torch.float32, 1e-6)):
        params = raw_to_kernel_params(_raw(dtype, 64))
        mf, nf, ms, ns, w = params
        for value, lo, hi in ((mf, MEAN_FAST_MIN, MEAN_FAST_MAX),
                              (ms, MEAN_SLOW_MIN, MEAN_SLOW_MAX),
                              (nf, N_MIN, N_MAX), (ns, N_SLOW_MIN, N_MAX), (w, 0, 1)):
            assert ((value >= lo) & (value <= hi)).all()
        assert ((w > 0) & (w < 1)).all()
        for k in (gamma_weights(mf, nf), gamma_weights(ms, ns), mixture_weights(*params)):
            assert k.shape == (4, 3, KERNEL_WEEKS) and k.dtype == dtype
            assert torch.isfinite(k).all() and (k >= 0).all()
            error = float((k.sum(-1) - 1).abs().max())
            assert error < tol, error
            largest_sum_error = max(largest_sum_error, error)

    # A zero raw value is the geometric midpoint for means and arithmetic for shapes.
    mid = raw_to_kernel_params(torch.zeros(5, dtype=torch.float64))
    expected = torch.tensor([math.sqrt(MEAN_FAST_MIN * MEAN_FAST_MAX), (N_MIN + N_MAX) / 2,
                             math.sqrt(MEAN_SLOW_MIN * MEAN_SLOW_MAX), (N_SLOW_MIN + N_MAX) / 2,
                             0.5], dtype=torch.float64)
    torch.testing.assert_close(torch.stack(mid), expected)
    assert gamma_weights(mid[0], mid[1], K=1).shape == (1,)
    print(f"  1. float64/float32 component and mixture bounds, shapes, simplex: "
          f"max sum error {largest_sum_error:.2e}")


def test_mixture_limits():
    params = raw_to_kernel_params(_raw(torch.float64, 65))
    mf, nf, ms, ns, w = params
    fast, slow = gamma_weights(mf, nf), gamma_weights(ms, ns)
    for fraction, expected in ((0.0, fast), (1.0, slow), (1e-9, fast), (1 - 1e-9, slow)):
        actual = mixture_weights(mf, nf, ms, ns, torch.full_like(w, fraction))
        torch.testing.assert_close(actual, expected, rtol=0, atol=1e-9)
    print("  2. w_slow = 0, 1 and within 1e-9 of each endpoint recover the component")


def test_mean_lags():
    """Separate grid bias from tail loss: a = mean/n is a continuous mean.

    Literal discrete bounds cannot hold for the required response.py family:
    mean=0.5, n=3 puts almost all mass at j=0. Even without truncation,
    mean=26, n=0.5 yields a discrete mean above 26. Report both effects.
    """
    for label, lo, hi, grid_tol, trunc_tol in (
            ("fast", MEAN_FAST_MIN, MEAN_FAST_MAX, 1.0, 0.04),
            ("slow", MEAN_SLOW_MIN, MEAN_SLOW_MAX, 3.0, 25.0)):
        means = torch.logspace(math.log10(lo), math.log10(hi), 17, dtype=torch.float64)[:, None]
        shapes = torch.linspace(N_MIN, N_MAX, 33, dtype=torch.float64)[None, :]
        j = torch.arange(8192, dtype=torch.float64)
        short = (gamma_weights(means, shapes) * j[:KERNEL_WEEKS]).sum(-1)
        long = (gamma_weights(means, shapes, K=len(j)) * j).sum(-1)
        grid_bias, tail_loss = long - means, long - short
        assert grid_bias.abs().max() < grid_tol
        assert tail_loss.min() >= -1e-10 and tail_loss.max() < trunc_tol
        assert (short >= lo - grid_tol - tail_loss.max() - 1e-10).all()
        assert (short <= hi + grid_tol + 1e-10).all()
        # At the maximum mean, the lowest shape gives the longest tail.
        endpoint = gamma_weights(torch.tensor(hi, dtype=torch.float64),
                                 torch.tensor(N_MIN, dtype=torch.float64), K=16384)
        endpoint_mean = (endpoint * torch.arange(16384, dtype=torch.float64)).sum()
        torch.testing.assert_close(long[-1, 0], endpoint_mean, rtol=0, atol=1e-9)
        assert abs(float(tail_loss.max() - tail_loss[-1, 0])) < 1e-9
        print(f"  3. {label}: discrete mean range {short.min():.6f}..{short.max():.6f} weeks; "
              f"grid bias {grid_bias.min():+.6f}..{grid_bias.max():+.6f}; "
              f"max truncation loss {tail_loss.max():.6f} weeks "
              f"(mean={hi:g}, n={N_MIN:g}, K={KERNEL_WEEKS})")


def test_matches_response():
    largest = 0.0
    for dtype in (torch.float32, torch.float64):
        for K in (17, KERNEL_WEEKS):
            net = response.ResponseModel([0, 1], 2, kernel_weeks=K, init_sd=0).to(dtype=dtype)
            g = torch.Generator().manual_seed(66)
            a = response.A_MIN + torch.rand((2, 3), dtype=dtype, generator=g) * (net.amax - response.A_MIN)
            n = N_MIN + torch.rand((2, 3), dtype=dtype, generator=g) * (N_MAX - N_MIN)
            actual, expected = gamma_weights(a * n, n, K), net.kernels(a, n)
            error = float((actual - expected).abs().max())
            assert error < 1e-6, error
            largest = max(largest, error)
    print(f"  4. gamma_weights(mean=a*n) vs ResponseModel.kernels: max error {largest:.2e}")


def test_convolution_and_causality():
    g = torch.Generator().manual_seed(67)
    largest, causal_error = 0.0, 0.0
    for K, T in ((1, 1), (1, 73), (17, 73), (KERNEL_WEEKS, 1), (KERNEL_WEEKS, 73)):
        S = torch.randn((2, 3, T + K - 1), generator=g)
        k = torch.rand((2, 3, K), generator=g)
        k = k / k.sum(-1, keepdim=True)
        direct, fft = causal_conv(S, k, "direct"), causal_conv(S, k)
        assert direct.shape == (2, 3, T)
        error = float((direct - fft).abs().max())
        assert error < 1e-5, error
        largest = max(largest, error)
        # An explicit lag sum checks orientation and the padded time origin.
        t = T // 2
        expected = (S[..., t:t + K].flip(-1) * k).sum(-1)
        torch.testing.assert_close(direct[..., t], expected, rtol=0, atol=1e-5)
        if T > 1:
            changed = S.clone()
            changed[..., K - 1 + t + 1] += 5
            for method in ("direct", "fft"):
                delta = causal_conv(changed, k, method) - causal_conv(S, k, method)
                before = float(delta[..., :t + 1].abs().max())
                assert before < 1e-5, (method, before)
                assert delta[..., t + 1].abs().max() > 1e-5
                causal_error = max(causal_error, before)

    # Exercise the original inline branches, using only toy stresses and no fit.
    with torch.no_grad():
        net = response.ResponseModel([0, 1], 2, kernel_weeks=KERNEL_WEEKS, init_sd=0)
        X = {key: torch.randn((2, KERNEL_WEEKS + 30), generator=g)
             for key in ("rain", "ETP", "pump_gw", "canal")}
        gain, a, n, f = net.parameters_physical()
        S, k = net.stresses(X, f), net.kernels(a, n)
        for method in ("direct", "fft"):
            net.conv = method
            expected = net.contributions(X)
            actual = gain[..., None] * causal_conv(S, k, method)
            torch.testing.assert_close(actual, expected, rtol=0, atol=1e-6)
    print(f"  5. float32 FFT/direct max error {largest:.2e}; future perturbation max "
          f"earlier change {causal_error:.2e}; explicit lag sums and response branches agree")


def test_gradients():
    g = torch.Generator().manual_seed(68)
    for dtype in (torch.float32, torch.float64):
        grads = {}
        S = torch.randn((2, 3, KERNEL_WEEKS + 72), dtype=dtype, generator=g)
        target = torch.randn((2, 3, 73), dtype=dtype, generator=g)
        for method in ("direct", "fft"):
            raw = (_raw(dtype, 69, (2, 3, 5)) / 3).requires_grad_()
            k = mixture_weights(*raw_to_kernel_params(raw))
            out = causal_conv(S, k, method)
            (out * target).sum().backward()
            assert raw.grad is not None and torch.isfinite(raw.grad).all()
            assert (raw.grad.abs() > 0).all(), "Every raw value must affect this toy loss"
            grads[method] = raw.grad
        torch.testing.assert_close(grads["direct"], grads["fft"], rtol=1e-4, atol=1e-6)
    print("  6. all five raw parameters: finite nonzero gradients through both convolutions "
          "in float32/float64; direct and FFT gradients agree")


if __name__ == "__main__":
    started = time.perf_counter()
    test_weights_and_bounds()
    test_mixture_limits()
    test_mean_lags()
    test_matches_response()
    test_convolution_and_causality()
    test_gradients()
    print(f"test_kernels: all checks passed ({time.perf_counter() - started:.2f}s)")
