"""Paired comparisons of two runs over wells, with spatially clustered uncertainty.

    from src.analysis.stats import paired, holm
    paired(metrics_a, metrics_b, split="test_drought")   # metrics_per_well.csv tables

Wells are not independent samples: nested piezometers share a site, neighbours
share an aquifer and its pumping. A per-well test then overstates the evidence.
docs/analysis_plan.md therefore fixes, for every comparison:
- clusters = cells of a CLUSTER_KM grid in Lambert-93 (wells within ~10 km tend
  to share a cell); the 95 % interval of the median paired difference comes from
  a cluster bootstrap (resample cells with replacement, keep their wells)
- the p-value of a cluster sign-flip permutation test (analysis plan v2,
  2026-10-23): under "no difference", the differences of a cluster are as likely
  to have the opposite sign, so the signs are flipped cluster by cluster, never
  well by well; statistic = the median paired difference. Exact (every sign
  pattern) up to EXACT_MAX_CLUSTERS clusters, Monte Carlo above. With 14 clusters
  the smallest possible two-sided p is 2 / 2^14 = 0.0001.
- the paired Wilcoxon signed-rank p-value (per well, so it treats the wells as
  independent), still reported next to it for comparison with v1-v3
- Holm's step-down adjustment across the comparisons of one table (of p_cluster
  from v2 of the plan)
- a sensitivity of the cluster inference, fixed on 2026-10-24 before any Phase 4 result
  (third review, docs/review_codex_2026-10-24.md §7; analysis plan §6): the interval and
  p_cluster under grids of SENS_KM km with their origin at 0 or shifted by half a cell, and
  leave-one-cluster-out medians on the primary grid. The primary test stays the 10 km grid
  at origin 0; the sensitivity is reported next to it, never used to pick a grid.
"""
import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

from src.config import CRS_L93, CRS_WGS84

CLUSTER_KM = 10.0
SENS_KM = (5.0, 10.0, 20.0)
SENS_SHIFTS = (0.0, 0.5)  # grid origin shift, in cells (x and y)
N_BOOT = 4000
EXACT_MAX_CLUSTERS = 16   # 2^16 = 65,536 sign patterns
N_FLIP = 20000            # Monte Carlo sign patterns above that


def sign_flip_p(groups, seed=2026):
    """Two-sided p-value of the cluster sign-flip test for the median difference.
    groups: list of arrays, the paired differences of each cluster's wells."""
    k = len(groups)
    d = np.concatenate(groups)
    owner = np.repeat(np.arange(k), [len(g) for g in groups])
    if k <= EXACT_MAX_CLUSTERS:
        signs = 1 - 2 * ((np.arange(2 ** k)[:, None] >> np.arange(k)[None]) & 1)
    else:
        signs = np.random.default_rng(seed).choice([-1, 1], size=(N_FLIP, k))
    t = np.median(signs[:, owner] * d[None], axis=1)
    obs = np.median(d)
    # the identity pattern is among the exact patterns; count it once in Monte Carlo
    hits = np.sum(np.abs(t) >= np.abs(obs) - 1e-12)
    return float(hits / len(t)) if k <= EXACT_MAX_CLUSTERS else float((hits + 1) / (len(t) + 1))


def clusters(wells, km=CLUSTER_KM, shift=0.0):
    """Grid-cell id per well (index code_bss); `shift` moves the grid origin by that many
    cells in x and y."""
    g = gpd.GeoSeries(gpd.points_from_xy(wells["x"], wells["y"]), crs=CRS_WGS84).to_crs(CRS_L93)
    k = km * 1000
    cell = (np.floor(g.x / k - shift).astype(int).astype(str) + "_"
            + np.floor(g.y / k - shift).astype(int).astype(str))
    return pd.Series(cell.values, index=wells["code_bss"].values, name="cluster")


def _groups(diff, wells, km=CLUSTER_KM, shift=0.0):
    """The paired differences of each cluster (list of arrays) and the cluster of each well."""
    cl = clusters(wells.set_index("code_bss").loc[diff.index].reset_index(), km, shift)
    cl = cl.loc[diff.index]
    return [g.to_numpy() for _, g in diff.groupby(cl.to_numpy())], cl


def _boot_ci(groups, seed):
    rng = np.random.default_rng(seed)
    meds = np.empty(N_BOOT)
    for i in range(N_BOOT):
        pick = rng.integers(0, len(groups), len(groups))
        meds[i] = np.median(np.concatenate([groups[k] for k in pick]))
    return np.percentile(meds, [2.5, 97.5])


def _select(m, task, horizon, split, variant, metric, core_only):
    s = m[(m["task"] == task) & (m["horizon"] == horizon) & (m["split"] == split)
          & (m["variant"] == variant)]
    if core_only:
        s = s[s["core"]]
    return s.set_index("code_bss")[metric]


def paired(ma, mb, wells, split="test_drought", metric="NSE", task="simulation", horizon=0,
           variant="all", core_only=True, seed=2026, strict=False):
    """Compare run a with run b well by well. Positive differences mean a is better
    (for error metrics such as RMSE, pass the negated metric or read the sign).
    Paired support (third review, docs/review_codex_2026-10-24.md §7; exact from 2026-10-27,
    Codex review of 2026-10-26 §2): each run is scored on its own available weeks. A well whose
    scored weeks differ between the runs is counted in `support_mismatch`: compared on the
    `support` digests of src.models.evaluate (`support_check` = "exact"), or on n_weeks for tables
    scored before the digest existed ("n_weeks", which misses equal counts on different weeks).
    Wells scored in one run only (MIN_WEEKS, missing predictions) are counted in n_wells_only_a /
    n_wells_only_b and left out of the comparison. strict=True (primary contrasts) refuses any of
    these, and tables without digests: a primary contrast compares the same well-weeks."""
    a = _select(ma, task, horizon, split, variant, metric, core_only)
    b = _select(mb, task, horizon, split, variant, metric, core_only)
    j = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    rows_a = set(_select(ma, task, horizon, split, variant, "n_weeks", core_only).dropna().index)
    rows_b = set(_select(mb, task, horizon, split, variant, "n_weeks", core_only).dropna().index)
    exact = "support" in ma.columns and "support" in mb.columns
    key = "support" if exact else "n_weeks"
    ka = _select(ma, task, horizon, split, variant, key, core_only).reindex(j.index)
    kb = _select(mb, task, horizon, split, variant, key, core_only).reindex(j.index)
    mismatch = sorted(j.index[ka.to_numpy() != kb.to_numpy()])
    only_a, only_b = sorted(rows_a - rows_b), sorted(rows_b - rows_a)
    if strict and not exact:
        raise ValueError(f"{split}: exact support unknown (no `support` column); rescore the runs "
                         "with python -m src.models.evaluate")
    if strict and (mismatch or only_a or only_b):
        raise ValueError(f"{split}: scored on different well-weeks in the two runs: different weeks "
                         f"{mismatch}, scored in a only {only_a}, in b only {only_b}")
    out = {"n_wells": len(j), "median_a": j["a"].median(), "median_b": j["b"].median(),
           "support_mismatch": len(mismatch), "support_check": "exact" if exact else "n_weeks",
           "n_wells_only_a": len(only_a), "n_wells_only_b": len(only_b)}
    if len(j) < 5:
        return out | {"median_diff": np.nan, "ci_lo": np.nan, "ci_hi": np.nan,
                      "share_a_better": np.nan, "p_wilcoxon": np.nan, "p_cluster": np.nan}
    diff = j["a"] - j["b"]
    groups, _ = _groups(diff, wells)
    lo, hi = _boot_ci(groups, seed)
    p = wilcoxon(j["a"], j["b"]).pvalue if (diff != 0).any() else 1.0
    pc = sign_flip_p(groups, seed) if (diff != 0).any() else 1.0
    return out | {"median_diff": float(diff.median()), "ci_lo": float(lo), "ci_hi": float(hi),
                  "share_a_better": float((diff > 0).mean()), "p_wilcoxon": float(p),
                  "p_cluster": pc, "n_clusters": len(groups)}


def cluster_sensitivity(ma, mb, wells, split="test_drought", metric="NSE", task="simulation",
                        horizon=0, variant="all", core_only=True, seed=2026):
    """The cluster inference of paired() under other grids, and leave-one-cluster-out.
    Returns (grids, loco): one row per grid size x origin shift (interval, p_cluster), and
    one row per cluster of the primary grid (median difference without its wells)."""
    a = _select(ma, task, horizon, split, variant, metric, core_only)
    b = _select(mb, task, horizon, split, variant, metric, core_only)
    j = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    diff = j["a"] - j["b"]
    grids, loco = [], []
    if len(diff) < 5 or not (diff != 0).any():
        return pd.DataFrame(grids), pd.DataFrame(loco)
    for km in SENS_KM:
        for shift in SENS_SHIFTS:
            groups, _ = _groups(diff, wells, km, shift)
            lo, hi = _boot_ci(groups, seed)
            grids.append({"km": km, "shift": shift, "primary": km == CLUSTER_KM and shift == 0,
                          "n_clusters": len(groups), "median_diff": float(diff.median()),
                          "ci_lo": float(lo), "ci_hi": float(hi),
                          "p_cluster": sign_flip_p(groups, seed)})
    _, cl = _groups(diff, wells)
    for c in sorted(cl.unique()):
        keep = cl != c
        loco.append({"left_out": c, "n_wells_out": int((~keep).sum()),
                     "median_diff": float(diff[keep.to_numpy()].median())})
    return pd.DataFrame(grids), pd.DataFrame(loco)


def holm(p):
    """Holm step-down adjusted p-values (same order as the input)."""
    p = np.asarray(p, dtype=float)
    adj = np.full(len(p), np.nan)
    ok = ~np.isnan(p)
    idx = np.where(ok)[0][np.argsort(p[ok])]
    m, running = len(idx), 0.0
    for rank, i in enumerate(idx):
        running = max(running, (m - rank) * p[i])
        adj[i] = min(1.0, running)
    return adj
