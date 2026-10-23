"""Knowledge-graph pre-check: do the relations the knowledge graph would encode explain how
wells co-vary, beyond distance and the regional signal?

    python -m src.analysis.kg_precheck            # dataset from PFE_DATASET (default v3)

Why (docs/feedback.md section 5.1): a graph built from the knowledge graph can only beat a
distance graph (RQ1) if its relations carry information distance does not. This checks it
on the data before Phase 3, as the head-ordering check did for the vertical constraint.

Data: weekly head anomalies (z minus the well's training climatology), training and
validation weeks only (the test period is not looked at). For every pair of wells with
>= MIN_COMMON common weeks:
    r_raw       correlation of the anomalies
    r_partial   correlation after removing the regional signal (plain-wide median anomaly,
                fitted per well on the same weeks)
Pair attributes: distance (km), same BD LISA entity, same aquifer group, investigation-depth
difference (m), same Pliocene depth class (DEPTH_CLASSES), nested (< 200 m apart),
pumping-neighbourhood similarity (cosine similarity of the volumes of the groundwater
abstraction points within PUMP_KM of each well).

Model: r_partial ~ log(distance) + attributes, ordinary least squares. Pairs share wells,
so the p-values come from a QAP permutation test (the well labels of an attribute are
permuted, the pair attribute rebuilt, the coefficient refitted; N_PERM times).

Outputs: docs/kg_precheck.md (tables), reports/figures/kg_precheck_pairs.png
"""
import itertools

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.config import CRS_L93, CRS_WGS84, DATASET, FIGURES, ROOT
from src.dataset.pumping import seasonal_drinking_water
from src.models.evaluate import DS
from src.models.features import build_panel

MIN_COMMON = 104
PUMP_KM = 5.0
DEPTH_CLASSES = (0, 60, 150, 1e4)     # Pliocene investigation-depth classes (m): shallow / mid / deep
N_PERM = 999
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e5e4df", "#fcfcfb"
C1, C2 = "#2a78d6", "#eb6834"


def anomalies():
    P = build_panel()
    P = P[P["split"].isin(["train", "validation"])]
    A = P.pivot_table(index="week", columns="code_bss", values="anom")
    regional = A.median(axis=1)
    resid = {}
    for c in A.columns:
        m = A[c].notna() & regional.notna()
        if m.sum() < MIN_COMMON:
            continue
        b = np.polyfit(regional[m], A.loc[m, c], 1)
        resid[c] = A[c] - np.polyval(b, regional)
    return A, pd.DataFrame(resid)


def pump_vectors(wells):
    pw = pd.read_parquet(DS / "pumping_weekly.parquet")
    pts = pd.read_parquet(DS / "pumping_points.parquet")
    g = pts[pts["source"] == "groundwater"]
    vol = (seasonal_drinking_water(pw, pts).groupby("code_ouvrage")["volume_m3"].mean()
           .reindex(g["code_ouvrage"]).fillna(0).to_numpy())
    gp = gpd.GeoSeries(gpd.points_from_xy(g["longitude"], g["latitude"]), crs=CRS_WGS84).to_crs(CRS_L93)
    out = {}
    for code, x, y in zip(wells["code_bss"], wells["X"], wells["Y"]):
        d = np.hypot(gp.x.to_numpy() - x, gp.y.to_numpy() - y)
        out[code] = np.where(d <= PUMP_KM * 1000, vol, 0.0)
    return out


def pair_table(A, R, wells, pumps):
    w = wells.set_index("code_bss")
    rows = []
    codes = sorted(set(A.columns) & set(w.index))
    sims = {a: {} for a in codes}
    for a in codes:
        for b in codes:
            pa, pb = pumps[a], pumps[b]
            den = np.linalg.norm(pa) * np.linalg.norm(pb)
            sims[a][b] = float(pa @ pb / den) if den > 0 else 0.0
    for a, b in itertools.combinations(codes, 2):
        m = A[a].notna() & A[b].notna()
        if m.sum() < MIN_COMMON:
            continue
        r_raw = np.corrcoef(A.loc[m, a], A.loc[m, b])[0, 1]
        mr = R[a].notna() & R[b].notna() if a in R and b in R else None
        r_par = np.corrcoef(R.loc[mr, a], R.loc[mr, b])[0, 1] if mr is not None else np.nan
        rows.append({"a": a, "b": b, "n_weeks": int(m.sum()), "r_raw": r_raw, "r_partial": r_par,
                     "dist_km": np.hypot(w.loc[a, "X"] - w.loc[b, "X"], w.loc[a, "Y"] - w.loc[b, "Y"]) / 1000,
                     "pump_sim": sims[a][b]})
    D = pd.DataFrame(rows)
    D.attrs["pump_sims"] = sims
    return D


def knn_mixing(wells, k=3):
    """How often the k nearest wells (the distance graph's edges) share the BD LISA entity."""
    xy = wells[["X", "Y"]].to_numpy()
    d = np.hypot(xy[:, None, 0] - xy[None, :, 0], xy[:, None, 1] - xy[None, :, 1])
    ent = wells["code_bdlisa"].to_numpy()
    same = [ent[j] == ent[i] for i in range(len(wells)) for j in np.argsort(d[i])[1:k + 1]]
    return float(np.mean(same)), len(same)


def attributes(D, w):
    """Pair attributes built from per-well labels (rebuilt for each permutation)."""
    ent, grp, dep, dcl = (w["code_bdlisa"], w["group"], w["profondeur_investigation"],
                          w["depth_class"])
    return pd.DataFrame({
        "log_dist": np.log(D["dist_km"].clip(lower=0.1)),
        "same_entity": (D["a"].map(ent) == D["b"].map(ent)).astype(float),
        "same_group": (D["a"].map(grp) == D["b"].map(grp)).astype(float),
        "depth_diff_100m": (D["a"].map(dep) - D["b"].map(dep)).abs() / 100,
        "same_plio_depth_class": ((D["a"].map(dcl) == D["b"].map(dcl))
                                  & (D["a"].map(grp) == "Pliocene multilayer")
                                  & (D["b"].map(grp) == "Pliocene multilayer")).astype(float),
        "nested": (D["dist_km"] < 0.2).astype(float),
        "pump_sim": D["pump_sim"],
        # the entity effect is local: same entity AND within 5 km
        "same_entity_x_near5km": ((D["a"].map(ent) == D["b"].map(ent))
                                  & (D["dist_km"] <= 5)).astype(float),
        "near5km": (D["dist_km"] <= 5).astype(float),
    })


def ols(y, X):
    Xc = np.c_[np.ones(len(X)), X.to_numpy()]
    ok = np.isfinite(y) & np.isfinite(Xc).all(axis=1)
    return np.linalg.lstsq(Xc[ok], y[ok], rcond=None)[0][1:]


def qap(D, w, target, sims, n_perm=N_PERM, seed=2026):
    """Coefficients and QAP p-values (two-sided) for each label-based attribute."""
    X = attributes(D, w)
    y = D[target].to_numpy()
    beta = pd.Series(ols(y, X), index=X.columns)
    rng = np.random.default_rng(seed)
    perm_cols = {"same_entity": ["code_bdlisa"], "same_group": ["group"],
                 "same_entity_x_near5km": ["code_bdlisa"],
                 "depth_diff_100m": ["profondeur_investigation"],
                 "same_plio_depth_class": ["depth_class"]}
    pvals = {}
    for col, labels in perm_cols.items():
        null = []
        for _ in range(n_perm):
            wp = w.copy()
            idx = rng.permutation(len(wp))
            for lab in labels:
                wp[lab] = wp[lab].to_numpy()[idx]
            null.append(ols(y, attributes(D, wp))[list(X.columns).index(col)])
        null = np.abs(np.array(null))
        pvals[col] = (1 + (null >= abs(beta[col])).sum()) / (n_perm + 1)
    # pumping similarity: permute which well owns which pumping neighbourhood
    codes = sorted(sims)
    null = []
    for _ in range(n_perm):
        perm = dict(zip(codes, rng.permutation(codes)))
        Dp = D.copy()
        Dp["pump_sim"] = [sims[perm[a]][perm[b]] for a, b in zip(D["a"], D["b"])]
        null.append(ols(y, attributes(Dp, w))[list(X.columns).index("pump_sim")])
    null = np.abs(np.array(null))
    pvals["pump_sim"] = (1 + (null >= abs(beta["pump_sim"])).sum()) / (n_perm + 1)
    return beta, pd.Series(pvals)


def plot(D, out):
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8), facecolor=SURF, sharey=True)
    for ax, col, title in ((axes[0], "r_raw", "Raw anomaly correlation"),
                           (axes[1], "r_partial", "After removing the regional signal")):
        for same, colr, lab in ((False, C1, "different BD LISA entity"), (True, C2, "same entity")):
            d = D[D["same_entity"] == same]
            ax.scatter(d["dist_km"], d[col], s=8, alpha=0.45, color=colr, label=lab, linewidths=0)
            bins = pd.cut(d["dist_km"], [0, 2, 5, 10, 20, 40, 80])
            med = d.groupby(bins, observed=True)[col].median()
            ax.plot([i.mid for i in med.index], med.values, color=colr, linewidth=2)
        ax.set_xscale("log")
        ax.set_title(title, fontsize=9, loc="left", color=INK)
        ax.set_xlabel("distance between wells (km, log scale)", fontsize=8, color=INK2)
        ax.axhline(0, color=INK2, linewidth=0.6)
        ax.set_facecolor(SURF)
        ax.grid(color=GRID, linewidth=0.5)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    axes[0].set_ylabel("correlation of weekly anomalies", fontsize=8, color=INK2)
    hd, lb = axes[0].get_legend_handles_labels()
    fig.legend(hd, lb, loc="lower center", ncol=2, fontsize=8, frameon=False)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(out, dpi=200)
    plt.close(fig)


def main():
    wells = pd.read_parquet(DS / "wells.parquet")
    g = gpd.GeoSeries(gpd.points_from_xy(wells["x"], wells["y"]), crs=CRS_WGS84).to_crs(CRS_L93)
    wells["X"], wells["Y"] = g.x.to_numpy(), g.y.to_numpy()
    wells["profondeur_investigation"] = pd.to_numeric(wells["profondeur_investigation"],
                                                      errors="coerce")
    wells["depth_class"] = pd.cut(wells["profondeur_investigation"], DEPTH_CLASSES,
                                  labels=["shallow", "mid", "deep"]).astype(str)
    A, R = anomalies()
    D = pair_table(A, R, wells, pump_vectors(wells))
    sims = D.attrs["pump_sims"]
    D = D.join(attributes(D, wells.set_index("code_bss"))[["same_entity"]].astype(bool))
    w = wells.set_index("code_bss")
    res = {}
    for target in ("r_raw", "r_partial"):
        beta, p = qap(D, w, target, sims)
        res[target] = pd.DataFrame({"coefficient": beta, "QAP p": p})
    plio = D[(D["a"].map(w["group"]) == "Pliocene multilayer")
             & (D["b"].map(w["group"]) == "Pliocene multilayer")]
    bins = pd.cut(D["dist_km"], [0, 5, 10, 20, 40, 200])
    tab = D.groupby([bins, "same_entity"], observed=True)["r_partial"].agg(["median", "count"]).unstack()
    share_same, n_edges = knn_mixing(wells[wells["code_bss"].isin(A.columns)])
    out_fig = FIGURES / f"kg_precheck_pairs_{DATASET}.png"
    plot(D, out_fig)
    md = ROOT / "docs" / "kg_precheck.md"
    md.write_text(
        "# Knowledge-graph pre-check (generated by `python -m src.analysis.kg_precheck`)\n\n"
        f"Dataset {DATASET}; weekly head anomalies, training + validation weeks only; "
        f"{len(D)} well pairs with >= {MIN_COMMON} common weeks; "
        f"{len(plio)} Pliocene–Pliocene pairs. `r_partial` = correlation after removing the "
        "plain-wide median anomaly. QAP permutation p-values (labels permuted across wells, "
        f"{N_PERM} permutations): pairs share wells, so ordinary p-values would be too small.\n\n"
        "## Regression of the raw correlation\n\n" + res["r_raw"].round(3).to_markdown() +
        "\n\n## Regression of the partial correlation (regional signal removed)\n\n"
        + res["r_partial"].round(3).to_markdown() +
        "\n\n## Median partial correlation by distance and entity\n\n"
        + tab.round(2).to_markdown() +
        f"\n\nDistance graph (3 nearest wells): {100 * share_same:.0f} % of its {n_edges} "
        "edges join wells of the same BD LISA entity.\n"
        f"\nFigure: `reports/figures/{out_fig.name}`.\n", encoding="utf-8")
    print(f"3-NN edges within the same entity: {100 * share_same:.0f} % of {n_edges}")
    print(res["r_raw"].round(3).to_string())
    print(res["r_partial"].round(3).to_string())
    print(tab.round(2).to_string())
    print("->", md, "\n->", out_fig)


if __name__ == "__main__":
    main()
