"""The TorchScript EA-LSTM recurrence equals the original eager loop.

    python -m tests.test_ealstm

Compares outputs and parameter gradients of src.models.lstm.EALSTM with the loop as first
written (nn.Linear for the hidden-to-gates map, Python loop over the weeks), then times
both.
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


def grads(net, fn, x):
    net.zero_grad()
    fn(x).pow(2).sum().backward()
    return [p.grad.clone() for p in net.parameters()]


def test_equal_to_eager_loop():
    torch.manual_seed(0)
    net = EALSTM(12, hidden=32, n_static=4).eval()
    for L in (1, 5, 104, 156):
        x = torch.randn(8, L, 12)
        with torch.no_grad():
            err = (net(x) - reference_forward(net, x)).abs().max().item()
        gerr = max((a - b).abs().max().item() for a, b in
                   zip(grads(net, net, x), grads(net, lambda z: reference_forward(net, z), x)))
        assert err < 1e-5 and gerr < 1e-4, (L, err, gerr)
        print(f"lookback {L:3d}: max |output diff| {err:.1e}, max |gradient diff| {gerr:.1e}")


def time_both(batch=256, L=156, hidden=64, reps=3):
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    net = EALSTM(30, hidden=hidden, n_static=8).to(dev).train()
    x = torch.randn(batch, L, 30, device=dev)
    out = {}
    for name, fn in (("script", net), ("eager", lambda z: reference_forward(net, z))):
        for _ in range(3):                        # TorchScript profiles on the first runs
            fn(x).sum().backward()
        if dev == "cuda":
            torch.cuda.synchronize()
        t0 = time.perf_counter()
        for _ in range(reps):
            fn(x).sum().backward()
        if dev == "cuda":
            torch.cuda.synchronize()
        out[name] = (time.perf_counter() - t0) / reps
    print(f"[{dev}] forward+backward, batch {batch} x {L} weeks: script {out['script'] * 1e3:.0f} ms, "
          f"eager {out['eager'] * 1e3:.0f} ms ({out['eager'] / out['script']:.1f}x)")


if __name__ == "__main__":
    torch.set_num_threads(2)
    test_equal_to_eager_loop()
    time_both()
    print("ok")
