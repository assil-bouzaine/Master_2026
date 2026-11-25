"""Fast and slow groundwater responses for analysis plan v3 §3.4.

Each driver mixes two non-negative Gamma kernels with unit total weight. This
allows both a quick response and a long memory without changing the gain's
meaning. Causal convolution follows response.py, with FFT and direct methods.
"""
import math

import torch
import torch.nn.functional as Fn

from src.models.response import N_MIN, N_MAX

KERNEL_WEEKS = 416          # eight years of weekly memory
MEAN_FAST_MIN, MEAN_FAST_MAX = 0.5, 26.0
MEAN_SLOW_MIN, MEAN_SLOW_MAX = 13.0, 104.0


def gamma_weights(mean, n, K=KERNEL_WEEKS):
    """Return weights (..., K) for positive mean and shape tensors, in weeks.

    ``mean`` is the continuous Gamma mean, so its scale is ``mean / n``.
    As in response.py, sample at j + 0.5 and assign that weight to lag j.
    The discrete mean therefore differs from ``mean`` through sampling and
    truncation. Inputs broadcast; their dtype and device are preserved.
    """
    if not isinstance(K, int) or K < 1:
        raise ValueError("K must be a positive integer")
    mean, n = torch.broadcast_tensors(mean, n)
    lag = torch.arange(K, dtype=mean.dtype, device=mean.device) + 0.5
    a = mean / n
    logk = (n[..., None] - 1) * torch.log(lag) - lag / a[..., None]
    return torch.softmax(logk, dim=-1)


def mixture_weights(mean_fast, n_fast, mean_slow, n_slow, w_slow, K=KERNEL_WEEKS):
    """Mix fast and slow weights; w_slow must be between zero and one."""
    fast = gamma_weights(mean_fast, n_fast, K)
    slow = gamma_weights(mean_slow, n_slow, K)
    return (1 - w_slow[..., None]) * fast + w_slow[..., None] * slow


def raw_to_kernel_params(raw):
    """Map (..., 5) raw values to (mean_fast, n_fast, mean_slow, n_slow, w_slow).

    Means span their bounds on a log scale; shapes span the response.py bounds
    linearly. The slow fraction uses a sigmoid. All operations keep autograd.
    """
    if raw.ndim < 1 or raw.shape[-1] != 5:
        raise ValueError("raw must have shape (..., 5)")
    mf, nf, ms, ns, w = torch.sigmoid(raw).unbind(-1)
    mean_fast = torch.exp(math.log(MEAN_FAST_MIN)
                          + mf * math.log(MEAN_FAST_MAX / MEAN_FAST_MIN))
    mean_slow = torch.exp(math.log(MEAN_SLOW_MIN)
                          + ms * math.log(MEAN_SLOW_MAX / MEAN_SLOW_MIN))
    n_fast = N_MIN + nf * (N_MAX - N_MIN)
    n_slow = N_MIN + ns * (N_MAX - N_MIN)
    return mean_fast, n_fast, mean_slow, n_slow, w


def causal_conv(S, k, method="fft"):
    """Convolve S (N, R, T + K - 1) with k (N, R, K), returning (N, R, T).

    The caller supplies K - 1 weeks of history on the left (zeros if no history
    is available). Output week t uses S[..., K - 1 + t - j] at each lag j.
    FFT uses zero padding for linear convolution; direct is the reference.
    """
    if method not in ("fft", "direct"):
        raise ValueError(f"Unknown convolution method: {method!r}")
    if S.ndim != 3 or k.ndim != 3 or S.shape[:2] != k.shape[:2]:
        raise ValueError("S and k must be (N, R, length) with matching N and R")
    N, R, L = S.shape
    K = k.shape[-1]
    if K < 1 or L < K:
        raise ValueError("S must contain at least K weeks and K must be positive")
    if method == "fft":
        nfft = 1 << (L + K - 2).bit_length()
        return torch.fft.irfft(torch.fft.rfft(S, nfft) * torch.fft.rfft(k, nfft),
                               nfft)[..., K - 1:L]
    w = k.flip(-1).reshape(N * R, 1, K)
    return Fn.conv1d(S.reshape(1, N * R, L), w, groups=N * R).reshape(N, R, L - K + 1)
