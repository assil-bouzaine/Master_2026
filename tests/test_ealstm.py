"""The fused-kernel EA-LSTM equals the explicit loop over the weeks.

    python -m tests.test_ealstm

Compares outputs and parameter gradients of src.models.lstm.EALSTM (the cell assembled
into one standard LSTM call) with the loop as first written (nn.Linear for the
hidden-to-gates map, Python loop over the weeks), then times both. As in the data
(src.models.lstm.arrays), the static columns are constant along each window.
"""
import time

import torch

from src.models.lstm import EALSTM


def reference_forward(net, x):
    xd, xs = x[:, :, :-net.n_static], x[:, -1, -net.n_static:]
    i = torch.sigmoid(net.gate_i(xs))
    wx = net.w(xd)
    h = torch.zeros(x.shape[0], net.hidden, device=x.device)
    c = torch.zeros_like(h)
    for t in range(x.shape[1]):
        f, g, o = (wx[:, t] + net.u(h)).chunk(3, dim=-1)
        c = torch.sigmoid(f) * c + i * torch.tanh(g)
        h = torch.sigmoid(o) * torch.tanh(c)
    return net.head(h).squeeze(-1)


def batch(B, L, n_in, n_static, device="cpu"):
    """Random inputs whose last n_static columns are constant along the window."""
    x = torch.randn(B, L, n_in, device=device)
    x[:, :, -n_static:] = torch.randn(B, 1, n_static, device=device)
    return x


def grads(net, fn, x):
    net.zero_grad()
    fn(x).pow(2).sum().backward()
    return [p.grad.clone() for p in net.parameters()]


def test_equal_to_eager_loop(device="cpu"):
    torch.manual_seed(0)
    # training mode: cuDNN computes RNN gradients only in training mode ("cudnn RNN backward
    # can only be called in training mode", first GPU run on a Colab T4, 2026-10-24); dropout
    # 0 keeps the training-mode forward deterministic, so the comparison stays exact
    net = EALSTM(12, hidden=32, n_static=4, dropout=0.0).to(device).train()
    for L in (1, 5, 104, 156):
        x = batch(8, L, 12, 4, device)
        with torch.no_grad():
            err = (net(x) - reference_forward(net, x)).abs().max().item()
        gerr = max((a - b).abs().max().item() for a, b in
                   zip(grads(net, net, x), grads(net, lambda z: reference_forward(net, z), x)))
        assert err < 1e-5 and gerr < 1e-4, (device, L, err, gerr)
        print(f"[{device}] lookback {L:3d}: max |output diff| {err:.1e}, "
              f"max |gradient diff| {gerr:.1e}")


def time_both(n=256, L=156, hidden=64, reps=3):
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    net = EALSTM(30, hidden=hidden, n_static=8).to(dev).train()
    x = batch(n, L, 30, 8, dev)
    out = {}
    for name, fn in (("fused", net), ("loop", lambda z: reference_forward(net, z))):
        for _ in range(3):                        # warm-up (kernel selection, allocator)
            fn(x).sum().backward()
        if dev == "cuda":
            torch.cuda.synchronize()
        t0 = time.perf_counter()
        for _ in range(reps):
            fn(x).sum().backward()
        if dev == "cuda":
            torch.cuda.synchronize()
        out[name] = (time.perf_counter() - t0) / reps
    print(f"[{dev}] forward+backward, batch {n} x {L} weeks: fused {out['fused'] * 1e3:.0f} ms, "
          f"loop {out['loop'] * 1e3:.0f} ms ({out['loop'] / out['fused']:.1f}x)")


if __name__ == "__main__":
    torch.set_num_threads(2)
    test_equal_to_eager_loop()
    if torch.cuda.is_available():
        # cuDNN runs the fused cell in TF32 by default (PyTorch's default for cuDNN, as for
        # nn.LSTM); switched off here so that the check compares the assembly only
        torch.backends.cudnn.allow_tf32 = False
        test_equal_to_eager_loop("cuda")
        torch.backends.cudnn.allow_tf32 = True
    time_both()
    print("ok")
