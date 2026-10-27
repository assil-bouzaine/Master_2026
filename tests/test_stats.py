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
6. Paired support: a well scored on different numbers of weeks by the two runs is counted,
   and strict mode refuses the pair (third review, docs/review_codex_2026-10-24.md §7). Exact
   support (Codex review of 2026-10-26, §2): six wells lose their first scored week in one run
   and their last in the other, so the counts agree but 12 well-weeks differ; the support
   digests of src.models.evaluate catch all six wells and strict mode refuses; the same
   predictions give the same digests; a well scored in one run only is counted and refused;
   strict mode refuses tables without digests.
7. Cluster sensitivity: its primary grid reproduces paired() exactly, a shifted origin
   regroups wells, and leave-one-cluster-out gives one row per cluster.
"""
import itertools

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

from src.analysis.stats import (EXACT_MAX_CLUSTERS, SENS_KM, SENS_SHIFTS, cluster_sensitivity,
                                clusters, holm, paired, sign_flip_p)
from src.models.evaluate import support_hash


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

    codes = [f"W{i}" for i in range(6)]  # 6. paired support
    wells = pd.DataFrame({"code_bss": codes, "x": 2.6 + 0.1 * np.arange(6), "y": 42.6})
    def table(nse, n_weeks):
        return pd.DataFrame({"code_bss": codes, "task": "simulation", "horizon": 0,
                             "split": "test_drought", "variant": "all", "core": True,
                             "NSE": nse, "n_weeks": n_weeks})
    ma = table(np.linspace(0.1, 0.6, 6), [100] * 6)
    mb = table(np.linspace(0.0, 0.5, 6), [100] * 5 + [90])
    assert paired(ma, mb, wells)["support_mismatch"] == 1
    assert paired(ma, ma, wells)["support_mismatch"] == 0
    try:
        paired(ma, mb, wells, strict=True)
        raise AssertionError("strict mode accepted different scored weeks")
    except ValueError:
        pass
    # exact support: equal counts on different weeks (the counterexample of the Codex review)
    weeks = pd.date_range("2022-05-01", periods=60, freq="W-SUN")
    def scored(drop):    # metrics tables scored by src.models.evaluate.score on the kept weeks
        rows = []
        for i, c in enumerate(codes):
            w = weeks.delete(drop)
            rows.append({"code_bss": c, "task": "simulation", "horizon": 0, "split": "test_drought",
                         "variant": "all", "core": True, "NSE": 0.1 * i, "n_weeks": len(w),
                         "support": support_hash(pd.Series(w))})
        return pd.DataFrame(rows)
    first, last = scored(0), scored(-1)
    assert (first["n_weeks"] == last["n_weeks"]).all()               # counts agree ...
    r = paired(first, last.assign(NSE=last["NSE"] - 0.05), wells)
    assert r["support_mismatch"] == 6 and r["support_check"] == "exact", r   # ... the weeks do not
    assert paired(first, scored(0), wells, strict=True)["support_mismatch"] == 0   # same weeks: same digest
    for bad in (last, first.iloc[:5], first.drop(columns="support")):
        try:
            paired(first, bad, wells, strict=True)
            raise AssertionError("strict mode accepted a different or unknown support")
        except ValueError:
            pass
    r = paired(first, first.iloc[:5], wells)
    assert (r["n_wells_only_a"], r["n_wells_only_b"], r["n_wells"]) == (1, 0, 5), r
    assert paired(ma, mb, wells)["support_check"] == "n_weeks"       # legacy tables: counts only
    rng = np.random.default_rng(7)  # 7. cluster sensitivity: 24 wells over ~40 x 40 km
    codes = [f"S{i}" for i in range(24)]
    wells = pd.DataFrame({"code_bss": codes, "x": 2.60 + 0.45 * rng.random(24),
                          "y": 42.50 + 0.35 * rng.random(24)})
    def tab(nse):
        return pd.DataFrame({"code_bss": codes, "task": "simulation", "horizon": 0,
                             "split": "test_drought", "variant": "all", "core": True,
                             "NSE": nse, "n_weeks": 100})
    ma, mb = tab(rng.normal(0.2, 0.3, 24)), tab(rng.normal(0.0, 0.3, 24))
    ref = paired(ma, mb, wells)
    grids, loco = cluster_sensitivity(ma, mb, wells)
    prim = grids[grids["primary"]].iloc[0]
    assert len(grids) == len(SENS_KM) * len(SENS_SHIFTS) and grids["primary"].sum() == 1
    assert prim["n_clusters"] == ref["n_clusters"] and prim["p_cluster"] == ref["p_cluster"]
    assert np.isclose(prim["ci_lo"], ref["ci_lo"]) and np.isclose(prim["ci_hi"], ref["ci_hi"])
    moved = (clusters(wells) != clusters(wells, shift=0.5)).sum()
    assert moved > 0, "a shifted origin regrouped no well"
    assert len(loco) == ref["n_clusters"] and loco["n_wells_out"].sum() == 24
    print(f"test_stats: all checks passed (Monte Carlo {mc:.4f} vs exact {exact:.4f})")


if __name__ == "__main__":
    main()
