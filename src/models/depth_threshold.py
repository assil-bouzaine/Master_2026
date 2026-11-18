"""Choose the depth threshold for arm D's well links (analysis plan §4 and §14 items 14–15).

For each candidate (10 m, 20 m, 50 m or no limit), take the median correlation of
the kept pairs' weekly head anomalies. An anomaly subtracts that well's mean for
the same clipped ISO week. Each pair needs 104 shared observed weeks, and each
candidate needs 10 qualifying pairs. Prefer the looser limit within 0.02 of the
best median. A pair with missing depth is kept only with no limit.

The choice uses target data. Filter the heads before making the weekly means or
correlating any pair. R1 and the refit use training weeks, R2 also leaves out
its fold's wells, and R3 uses only the shortened training window.

    PFE_DATASET=v4 python -m src.models.depth_threshold

Print the records and save them to results/v4/_depth_threshold/records.json.
"""
import json

import numpy as np
import pandas as pd

from src.config import DATASET, DATASET_DIR, RESULTS_DIR
from src.dataset.placeholders import load_mask
from src.models.routing import load_edges

CANDIDATES = (10.0, 20.0, 50.0, None)
MIN_PAIRS, MIN_SHARED_WEEKS, TIE = 10, 104, 0.02
HEAD_KEYS = ["code_bss", "week"]


def kept_links(edges, choice):
    """Keep only D's well-link rows within the chosen limit, in both directions."""
    links = edges.loc[edges["relation"] == "well_link"]
    if choice is not None:
        links = links.loc[links["depth_diff_m"] <= choice]
    return links.copy()


def _regime_support(regime, fold, train_start, wells, splits):
    """Return the allowed well codes and the inclusive date bounds for heads."""
    if regime not in ("R1", "R2", "R3", "refit"):
        raise ValueError(f"unknown depth-threshold regime: {regime}")
    if regime == "R2":
        if fold not in range(splits["leave_wells_out"]["n_folds"]):
            raise ValueError("R2 requires a valid held-out fold")
        wells = wells.loc[wells["fold"] != fold]
    elif fold is not None:
        raise ValueError("a held-out fold applies only to R2")

    start, end = splits["train"]
    if regime == "R3":
        if train_start is None:
            raise ValueError("R3 requires a training window start")
        start = pd.Timestamp(train_start).date().isoformat()
        if start not in splits["r3_starts"].values():
            raise ValueError(f"unknown R3 training window start: {start}")
    elif train_start is not None:
        raise ValueError("a shortened training window applies only to R3")
    return set(wells["code_bss"]), start, end


def _allowed_heads(heads, codes, start, end, mask):
    heads = heads.loc[heads["code_bss"].isin(codes), [*HEAD_KEYS, "head"]].copy()
    heads["week"] = pd.to_datetime(heads["week"])
    heads = heads.loc[heads["week"].between(start, end)].astype({"head": float})
    heads = heads.loc[np.isfinite(heads["head"])]
    if mask is not None:
        flagged = pd.MultiIndex.from_frame(heads[HEAD_KEYS]).isin(pd.MultiIndex.from_frame(mask[HEAD_KEYS]))
        heads = heads.loc[~flagged]
    return heads


def _head_anomalies(heads):
    """Subtract the raw weekly means from the already filtered heads."""
    # Use the ISO week convention of naive.climatology. Here the means are unsmoothed.
    woy = heads["week"].dt.isocalendar().week.clip(upper=52).astype(int)
    mean = heads["head"].groupby([heads["code_bss"], woy]).transform("mean")
    return heads.assign(anomaly=heads["head"] - mean).pivot(index="week", columns="code_bss", values="anomaly")


def _pair_statistics(links, anomalies):
    """Calculate a Pearson correlation once per unordered pair with enough shared heads."""
    depths = {}
    for src, dst, depth in links[["src", "dst", "depth_diff_m"]].itertuples(index=False, name=None):
        depths[tuple(sorted((src, dst)))] = depth
    pairs = []
    for (a, b), depth in sorted(depths.items()):
        n, correlation = 0, None
        if a in anomalies and b in anomalies:
            shared = anomalies[[a, b]].dropna()
            n = len(shared)
            if n >= MIN_SHARED_WEEKS and shared[a].nunique() > 1 and shared[b].nunique() > 1:
                value = shared[a].corr(shared[b])
                if np.isfinite(value):
                    correlation = float(value)
        pairs.append((a, b, depth, n, correlation))
    return pairs


def _candidate(pairs, threshold):
    kept = pairs if threshold is None else [pair for pair in pairs if pd.notna(pair[2]) and pair[2] <= threshold]
    qualifying = [pair for pair in kept if pair[3] >= MIN_SHARED_WEEKS]
    weeks = [n for _, _, _, n, _ in qualifying]
    correlations = [corr for _, _, _, _, corr in qualifying if corr is not None]
    return {"threshold": threshold, "kept_pairs": len(kept),
            "missing_depth_excluded": int(sum(pd.isna(depth) for _, _, depth, _, _ in pairs))
            if threshold is not None else 0,
            "qualifying_pairs": len(qualifying),
            "qualifying_pair_weeks": [{"src": a, "dst": b, "shared_weeks": n} for a, b, _, n, _ in qualifying],
            "min_shared_weeks": min(weeks, default=None),
            "median_shared_weeks": float(np.median(weeks)) if weeks else None,
            "undefined_correlations": len(qualifying) - len(correlations),
            "median_correlation": float(np.median(correlations)) if correlations else None,
            "eligible": len(qualifying) >= MIN_PAIRS}


def _choice(candidates):
    eligible = [record for record in candidates if record["eligible"]]
    scored = [record for record in eligible if record["median_correlation"] is not None]
    if not eligible:
        return None, f"no candidate has at least {MIN_PAIRS} qualifying pairs"
    if not scored:
        return None, "no eligible candidate has a defined median Pearson correlation"
    best = max(record["median_correlation"] for record in scored)
    tied = [record for record in scored if record["median_correlation"] >= best - TIE]
    reason = (f"loosest eligible threshold within {TIE:.2f} of the best median"
              if len(tied) > 1 else "highest median correlation among eligible candidates")
    return tied[-1]["threshold"], reason


def choose_threshold(regime="R1", fold=None, train_start=None, edges=None, heads=None, wells=None):
    """Choose a limit from the requested regime's heads and return its audit record."""
    splits = json.loads((DATASET_DIR / "splits.json").read_text())
    if wells is None:
        wells = pd.read_parquet(DATASET_DIR / "wells.parquet", columns=["code_bss", "fold"])
    codes, start, end = _regime_support(regime, fold, train_start, wells, splits)
    if edges is None:
        edges, _ = load_edges("D")
    if heads is None:
        heads = pd.read_parquet(DATASET_DIR / "heads_weekly.parquet", columns=[*HEAD_KEYS, "head"])
    mask = load_mask() if DATASET >= "v4" else None
    if DATASET >= "v4" and mask is None:
        raise FileNotFoundError("placeholder_weeks.parquet is missing from the dataset")
    allowed = _allowed_heads(heads, codes, start, end, mask)
    pairs = _pair_statistics(kept_links(edges, None), _head_anomalies(allowed))
    candidates = [_candidate(pairs, threshold) for threshold in CANDIDATES]
    choice, reason = _choice(candidates)
    return {"regime": regime, "fold": int(fold) if fold is not None else None,
            "train_start": start, "allowed_wells": len(codes), "allowed_weeks": [start, end],
            "candidates": candidates, "choice": choice, "reason": reason}


def main():
    splits = json.loads((DATASET_DIR / "splits.json").read_text())
    records = [choose_threshold()]
    records.extend(choose_threshold("R2", fold=k) for k in range(splits["leave_wells_out"]["n_folds"]))
    records.extend(choose_threshold("R3", train_start=start) for start in splits["r3_starts"].values())
    content = json.dumps(records, indent=2, allow_nan=False)
    output = RESULTS_DIR / "_depth_threshold" / "records.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content + "\n")
    print(content)
    print(f"-> {output}")


if __name__ == "__main__":
    main()
