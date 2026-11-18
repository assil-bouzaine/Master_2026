"""Checks of the well-link message passing of rung 5 (src/models/message.py).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 python -m tests.test_message

1. The adjacency: each linked well's weights sum to 1, an unlinked well's row is 0 and its flag 0;
   links to wells outside the run are ignored; a self-link or a non-positive weight is refused.
2. propagate() equals a hand computation on four wells, for one and two hops, and its column names
   follow its columns.
3. On the export: arm C links every well (its three nearest, symmetric), arm D links the 38 wells of
   its same-unit links; both adjacencies are well formed.
"""
import numpy as np
import pandas as pd

from src.models.message import feature_names, link_summary, propagate, well_adjacency


def toy_edges():
    rows = [("well_link", "a", "b", 1.0), ("well_link", "b", "a", 1.0),
            ("well_link", "c", "b", 3.0), ("well_link", "b", "c", 3.0),
            ("well_link", "x", "a", 5.0),                         # x is not in the run
            ("pumping", "f1", "a", 0.7)]                          # another relation
    return pd.DataFrame(rows, columns=["relation", "src", "dst", "weight"])


def test_adjacency():
    A, has = well_adjacency(toy_edges(), ["a", "b", "c", "d"])
    want = np.array([[0, 1, 0, 0], [0.25, 0, 0.75, 0], [0, 1, 0, 0], [0, 0, 0, 0]], dtype=np.float32)
    assert np.allclose(A, want) and has.tolist() == [1, 1, 1, 0], (A, has)
    bad = pd.concat([toy_edges(), pd.DataFrame([("well_link", "c", "c", 1.0)], columns=toy_edges().columns)])
    for table in (bad, toy_edges().assign(weight=[1.0, 1.0, 0.0, 3.0, 5.0, 0.7])):
        try:
            well_adjacency(table, ["a", "b", "c", "d"])
            raise AssertionError("must refuse")
        except ValueError:
            pass
    s = link_summary(toy_edges(), ["a", "b", "c", "d"])
    assert s["links"].tolist() == [1, 2, 1, 0] and s["has_link"].tolist() == [1, 1, 1, 0]


def test_propagate():
    A, has = well_adjacency(toy_edges(), ["a", "b", "c", "d"])
    Z = np.array([[1.0, 0.0], [0.0, 2.0], [4.0, 4.0], [9.0, 9.0]], dtype=np.float32)
    out = propagate(Z, A, has, hops=1)
    m = np.array([[0, 2], [3.25, 3], [0, 2], [0, 0]], dtype=np.float32)       # A Z by hand
    assert np.allclose(out, np.hstack([Z, m, has[:, None]])), out
    out2 = propagate(Z, A, has, hops=2)
    assert np.allclose(out2[:, 4:6], A @ m) and out2.shape == (4, 7)
    assert feature_names(["p", "q"], 2) == ["p", "q", "nbr1:p", "nbr1:q", "nbr2:p", "nbr2:q", "has_link"]
    try:
        propagate(Z, A, has, hops=0)
        raise AssertionError("hops = 0 is rung 3")
    except ValueError:
        pass


def test_export():
    from src.models.routing import load_edges
    wells = None
    for arm, n_linked in (("C", None), ("D", 38)):
        edges, _ = load_edges(arm)
        if wells is None:
            wells = sorted(set(edges["dst"][edges["relation"] == "well_link"]) |
                           set(load_edges("C")[0].query("relation == 'well_link'")["dst"]))
        A, has = well_adjacency(edges, wells)
        rows = A.sum(1)
        assert np.allclose(rows[has == 1], 1.0, atol=1e-6) and np.all(rows[has == 0] == 0)
        if n_linked is None:
            assert has.all(), f"arm {arm}: every well has its nearest wells"
        else:
            assert int(has.sum()) == n_linked, (arm, int(has.sum()))
        print(f"    arm {arm}: {int(has.sum())} of {len(wells)} wells linked")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all message-passing checks passed")
