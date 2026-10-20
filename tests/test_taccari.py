"""The strided TaccariNet equals the full causal dilated stack at the last week.

    python -m tests.test_taccari

src.models.taccari evaluates each gated TCN layer only at the positions the next layer
reads (stride 2 on a grid of step 2^k). This test keeps the full computation (every layer
at every week, zeros before the window start) as the reference and checks that both give
the same output, in eval mode, for several window lengths; then times both.
"""
import time

import torch
import torch.nn.functional as Fn

from src.models.taccari import TaccariNet


def reference_forward(net, x):
    """The full computation: each layer at every week, causal zero padding."""
    h = net.inp(x)
    for tcn, mix, norm in zip(net.tcn, net.mix, net.norm):
        B, N, L, C = h.shape
        pad = (tcn.f.kernel_size[0] - 1) * tcn.f.dilation[0]
        z = Fn.pad(h.reshape(B * N, L, C).transpose(1, 2), (pad, 0))
        y = torch.tanh(tcn.f(z)) * torch.sigmoid(tcn.g(z))     # the module's own dilation
        h = norm(net.drop(mix(y.transpose(1, 2).reshape(B, N, L, C), net.A)) + h)
    return net.out(h[:, :, -1]).squeeze(-1)


def make_net(n_nodes=12, n_in=5, hidden=16, seed=0):
    g = torch.Generator().manual_seed(seed)
    A = torch.rand(n_nodes, n_nodes, generator=g) * (torch.rand(n_nodes, n_nodes, generator=g) < 0.3)
    A = A + torch.eye(n_nodes)
    torch.manual_seed(seed)
    return TaccariNet(n_in, A / A.sum(1, keepdim=True), hidden=hidden, dropout=0.3).eval()


def test_equal_to_full_stack():
    net = make_net()
    for L in (1, 2, 3, 7, 52, 104, 127, 128, 156):
        x = torch.randn(3, 12, L, 5)
        with torch.no_grad():
            fast, full = net(x), reference_forward(net, x)
        err = (fast - full).abs().max().item()
        assert fast.shape == full.shape == (3, 12), (L, fast.shape)
        assert err < 1e-5, f"lookback {L}: max difference {err:.2e}"
        print(f"lookback {L:3d}: max |fast - full| = {err:.1e}")


def test_trains():
    net = make_net().train()
    loss = net(torch.randn(2, 12, 104, 5)).pow(2).mean()
    loss.backward()
    assert all(p.grad is not None for p in net.parameters() if p.requires_grad)


def time_both(n_nodes=60, batch=4, L=104, hidden=32, reps=3):
    net = make_net(n_nodes=n_nodes, hidden=hidden).train()
    x = torch.randn(batch, n_nodes, L, 5)
    out = {}
    for name, fn in (("strided", net), ("full", lambda z: reference_forward(net, z))):
        fn(x).sum().backward()                    # warm-up
        t0 = time.perf_counter()
        for _ in range(reps):
            fn(x).sum().backward()
        out[name] = (time.perf_counter() - t0) / reps
    print(f"forward+backward, {n_nodes} nodes x {L} weeks x batch {batch}: strided "
          f"{out['strided'] * 1e3:.0f} ms, full {out['full'] * 1e3:.0f} ms "
          f"({out['full'] / out['strided']:.1f}x)")


if __name__ == "__main__":
    torch.set_num_threads(2)
    test_equal_to_full_stack()
    test_trains()
    time_both()
    print("ok")
