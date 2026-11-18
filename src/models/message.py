"""Message passing over the well links of a graph arm (ladder rung 5), for the response model.

    from src.models.message import well_adjacency, propagate
    A, has_link = well_adjacency(edges, codes)        # the arm's well_link rows, row-normalised
    Zm = propagate(Z, A, has_link, hops=1)            # [Z, A Z, has_link] -> --statics input of rung 5

Rung 3 (`src/models/response.py --statics`) maps each well's own standardised facts z_i to its
response parameters. Rung 5 lets a well also see the facts of the wells it is linked to: one layer
of mean aggregation, as in GraphSAGE (Hamilton et al. 2017, arXiv:1706.02216), over the arm's
`well_link` edges with their weights,

    m_i = sum_j w_ij z_j / sum_j w_ij        (0 for a well without a link)
    h_i = [z_i, m_i, has_link_i]             -> the static map f of rung 3 -> parameters

The first layer of such a network aggregates the raw facts, which never change during training, so
the aggregation is computed once here and the model's map f learns how much of z_i and of m_i to
use (a linear f gives a one-layer linear graph network; `--static-net mlp16` an MLP on the
aggregated features). With hops = 2 the neighbours of the neighbours are added (A²Z). Nothing here
sees a stress, so the signs of the responses still hold by construction (analysis plan §10,
condition 1), and the arms differ only in their links: arm C's three nearest wells, arm D's same-unit
links within 5 km kept by the per-regime depth threshold (analysis plan §14 items 14-15), or a
control's links (item 20). Held-out wells of the leave-wells-out folds stay as nodes: their facts
are known, only their heads are not (analysis plan §4, R2, transductive).

Message passing over 47 links in a model without head inputs can only share information about
parameters between neighbours (fable_review.md §6.1); it is the ladder's secondary D vs C contrast,
after routing (rung 4).
"""
import numpy as np
import pandas as pd


def well_adjacency(edges, codes, relation="well_link"):
    """Row-normalised (N, N) weights of the arm's well links between the wells `codes` (rows =
    receiving well, columns = sending well) and a (N,) 0/1 flag of wells with at least one link.
    Links to wells outside `codes` are ignored; a self-link is an error."""
    codes = list(codes)
    row = {c: i for i, c in enumerate(codes)}
    e = edges[edges["relation"] == relation]
    if (e["src"] == e["dst"]).any():
        raise ValueError("a well link from a well to itself")
    W = np.zeros((len(codes), len(codes)))
    for s, d, w in zip(e["src"], e["dst"], e["weight"]):
        if s in row and d in row:
            if not (np.isfinite(w) and w > 0):
                raise ValueError(f"well link {s} -> {d} has weight {w}")
            W[row[d], row[s]] += w
    tot = W.sum(1, keepdims=True)
    has_link = (tot[:, 0] > 0).astype(np.float32)
    A = np.divide(W, tot, out=np.zeros_like(W), where=tot > 0)
    return A.astype(np.float32), has_link


def propagate(Z, A, has_link, hops=1):
    """[Z, A Z, ..., A^hops Z, has_link]: the rung-5 input of the static map, float32."""
    if hops < 1:
        raise ValueError("hops must be at least 1 (hops = 0 is rung 3)")
    Z = np.asarray(Z, dtype=np.float32)
    if A.shape != (len(Z), len(Z)) or len(has_link) != len(Z):
        raise ValueError("Z, A and has_link must describe the same wells")
    parts, cur = [Z], Z
    for _ in range(hops):
        cur = A @ cur
        parts.append(cur)
    parts.append(np.asarray(has_link, dtype=np.float32)[:, None])
    return np.concatenate(parts, axis=1).astype(np.float32)


def feature_names(names, hops=1):
    """Column names of propagate()'s output, for the run's schema."""
    out = list(names)
    for k in range(1, hops + 1):
        out += [f"nbr{k}:{n}" for n in names]
    return out + ["has_link"]


def link_summary(edges, codes, relation="well_link"):
    """Per well: number of links and sum of weights (for the run's schema and reports)."""
    A, has = well_adjacency(edges, codes, relation)
    e = edges[(edges["relation"] == relation) & edges["dst"].isin(codes) & edges["src"].isin(codes)]
    n = e.groupby("dst").size().reindex(codes, fill_value=0)
    return pd.DataFrame({"code_bss": list(codes), "links": n.to_numpy(), "has_link": has.astype(int)})
