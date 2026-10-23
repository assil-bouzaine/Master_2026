"""The cluster sign-flip test and the Holm adjustment of src.analysis.stats.

    python -m tests.test_stats

1. Exact mode equals a brute-force reference (every sign pattern, written with itertools).
2. A set of clusters with mirror images gives p = 1.
3. One dominant cluster of 20 positive wells plus 6 small clusters around zero: the
   per-well Wilcoxon calls it highly significant, the cluster test gives p = 1 (whatever
   the signs of the small clusters, the median is +-0.5). This is why the plan switched.
4. Monte Carlo mode (more than EXACT_MAX_CLUSTERS clusters) stays within 0.01 of the
   exact value.
5. Holm matches a hand computation.
"""
import itertools

import numpy as np
from scipy.stats import wilcoxon

from src.analysis.stats import EXACT_MAX_CLUSTERS, holm, sign_flip_p


def reference_p(groups):
    obs = abs(np.median(np.concatenate(groups)))
    hits = total = 0
    for signs in itertools.product((1, -1), repeat=len(groups)):
        t = np.median(np.concatenate([s * g for s, g in zip(signs, groups)]))
        hits += abs(t) >= obs - 1e-12
        total += 1
    return hits / total


def exact_vectorised(groups):
    k = len(groups)
    d = np.concatenate(groups)
    owner = np.repeat(np.arange(k), [len(g) for g in groups])
    signs = 1 - 2 * ((np.arange(2 ** k)[:, None] >> np.arange(k)[None]) & 1)
    t = np.median(signs[:, owner] * d[None], axis=1)
    return float(np.mean(np.abs(t) >= abs(np.median(d)) - 1e-12))


def main():
    rng = np.random.default_rng(0)

    for k in (3, 6, 9):  # 1. exact mode = brute force
        groups = [rng.normal(0.3, 1.0, size=rng.integers(1, 5)) for _ in range(k)]
        assert abs(sign_flip_p(groups) - reference_p(groups)) < 1e-12, k

    half = [rng.normal(size=3) for _ in range(6)]  # 2. mirrored clusters
    assert sign_flip_p(half + [-g for g in half]) == 1.0

    small = (-0.4, 0.3, -0.2, 0.1, -0.3, 0.2)  # 3. one dominant cluster
    groups = [np.full(20, 0.5)] + [np.array([x]) for x in small]
    d = np.concatenate(groups)
    assert wilcoxon(d).pvalue < 0.01, "the per-well test should look significant here"
    assert sign_flip_p(groups) == 1.0

    k = EXACT_MAX_CLUSTERS + 2  # 4. Monte Carlo vs exact (2^18 patterns, vectorised)
    groups = [rng.normal(0.25, 1.0, size=rng.integers(1, 4)) for _ in range(k)]
    exact, mc = exact_vectorised(groups), sign_flip_p(groups)
    assert abs(exact - mc) < 0.01, (exact, mc)

    adj = holm([0.01, 0.04, 0.03])  # 5. Holm: 0.01*3; max(0.03*2, 0.03); max(0.04, 0.06)
    assert np.allclose(adj, [0.03, 0.06, 0.06]), adj
    print(f"test_stats: all checks passed (Monte Carlo {mc:.4f} vs exact {exact:.4f})")


if __name__ == "__main__":
    main()
