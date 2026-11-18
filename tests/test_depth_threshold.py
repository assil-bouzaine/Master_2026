"""Check the per-regime well-link depth threshold without fitting a model.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_depth_threshold

The synthetic heads give known correlations and make held-out data easy to
perturb. The real R1 check compares the export's pair counts with plan item 15.
"""
import json
from itertools import combinations, product

import numpy as np
import pandas as pd

from src.config import DATASET_DIR
from src.models import depth_threshold as T


def fixture(tie=False):
    codes = list("ABCDEFGHIJKLMN")
    depths = dict(zip(codes, [0, 1, 2, 3, 4, 17, 18, 20, 47, 48, 49, 50, 46, 47]))
    close, middle, far = codes[:5], codes[5:8], codes[8:]
    wells = pd.DataFrame({"code_bss": codes, "fold": np.arange(len(codes)) % 5})
    rows = []
    for a, b in [*combinations(close, 2), *product(close, middle + far), (far[0], far[1])]:
        depth = None if (a, b) == tuple(far[:2]) else abs(depths[a] - depths[b])
        rows.extend([("well_link", a, b, depth), ("well_link", b, a, depth)])
    rows.append(("recharge", "cell", codes[0], None))
    edges = pd.DataFrame(rows, columns=["relation", "src", "dst", "depth_diff_m"])

    weeks = pd.date_range("2014-10-05", periods=300, freq="W-SUN")
    rng = np.random.default_rng(28)
    common = rng.normal(size=len(weeks))
    seasonal = 4 * np.cos(2 * np.pi * np.arange(len(weeks)) / 52)
    heads = []
    for i, code in enumerate(codes):
        noise = rng.normal(size=len(weeks))
        anomaly = common + 0.08 * noise if code in close or (tie and code in middle) else noise
        heads.append(pd.DataFrame({"code_bss": code, "week": weeks, "head": 40 + i + seasonal + anomaly}))
    return edges, pd.concat(heads, ignore_index=True), wells


def records_by_threshold(record):
    return {row["threshold"]: row for row in record["candidates"]}


def test_choice():
    edges, heads, wells = fixture()
    record = T.choose_threshold(edges=edges, heads=heads, wells=wells)
    candidates = records_by_threshold(record)
    assert record["choice"] == 10.0, record
    assert candidates[10.0]["qualifying_pairs"] == 10 and candidates[10.0]["eligible"]
    assert candidates[10.0]["median_correlation"] > 0.95

    _, tied_heads, _ = fixture(tie=True)
    record = T.choose_threshold(edges=edges, heads=tied_heads, wells=wells)
    candidates = records_by_threshold(record)
    assert abs(candidates[10.0]["median_correlation"] - candidates[20.0]["median_correlation"]) <= 0.02
    assert record["choice"] == 20.0 and "loosest" in record["reason"], record

    # Each of A and B has enough heads, but on opposite sides of the date.
    split = heads["week"] < "2017-06-01"
    excluded = ((heads["code_bss"] == "A") & ~split) | ((heads["code_bss"] == "B") & split)
    short_overlap = heads.copy()
    short_overlap.loc[excluded, "head"] = np.nan
    record = T.choose_threshold(edges=edges, heads=short_overlap, wells=wells)
    narrow = records_by_threshold(record)[10.0]
    assert narrow["kept_pairs"] == 10 and narrow["qualifying_pairs"] == 9
    assert not narrow["eligible"] and record["choice"] != 10.0
    record = T.choose_threshold(edges=T.kept_links(edges, 10.0), heads=short_overlap, wells=wells)
    assert record["choice"] is None and "at least 10" in record["reason"]

    weeks = heads["week"].drop_duplicates().sort_values().tolist()
    excluded = ((heads["code_bss"] == "A") & heads["week"].ge(weeks[140])) | (
        (heads["code_bss"] == "B") & heads["week"].lt(weeks[36]))
    exact_overlap = heads.loc[~excluded]
    record = T.choose_threshold(edges=edges, heads=exact_overlap, wells=wells)
    narrow = records_by_threshold(record)[10.0]
    assert narrow["qualifying_pairs"] == 10 and narrow["min_shared_weeks"] == 104

    record = T.choose_threshold(edges=edges, heads=heads.assign(head=1.0), wells=wells)
    narrow = records_by_threshold(record)[10.0]
    assert narrow["eligible"] and narrow["undefined_correlations"] == 10
    assert record["choice"] is None and "defined median" in record["reason"]
    print("  1. Synthetic heads select 10 m, then 20 m on a tie. Nine qualifying pairs are ineligible.")


def test_anomaly():
    # 2016-01-03 is ISO week 53. It uses the same mean as the two week-52 values.
    heads = pd.DataFrame({"code_bss": "A",
                          "week": pd.to_datetime(["2013-12-29", "2014-12-28", "2015-01-04", "2015-12-27",
                                                  "2016-01-03", "2016-01-10", "2016-12-25"]),
                          "head": [510.0, 2.0, 8.0, 5.0, 11.0, 21.0, -500.0]})
    allowed = T._allowed_heads(heads, {"A"}, "2014-12-28", "2016-01-10", None)
    actual = T._head_anomalies(allowed)
    np.testing.assert_allclose(actual["A"], [-4.0, -6.5, -1.0, 5.0, 6.5], rtol=0, atol=1e-12)

    mask = heads.loc[heads["week"].eq("2015-12-27"), T.HEAD_KEYS]
    allowed = T._allowed_heads(heads, {"A"}, "2014-12-28", "2016-01-10", mask)
    actual = T._head_anomalies(allowed)
    np.testing.assert_allclose(actual["A"], [-4.5, -6.5, 4.5, 6.5], rtol=0, atol=1e-12)
    print("  2. The hand calculation matches the raw ISO-week means, including week 53 and a masked row.")


def test_leakage(edges, heads, wells):
    splits = json.loads((DATASET_DIR / "splits.json").read_text())
    train_end = splits["train"][1]
    fold = 1
    held = wells.loc[wells["fold"].eq(fold), "code_bss"].iloc[0]
    start = splits["r3_starts"]["f25"]
    cases = [
        ({"regime": "R2", "fold": fold}, heads["code_bss"].eq(held)),
        ({"regime": "R1"}, heads["week"].gt(train_end)),
        ({"regime": "R3", "train_start": start}, heads["week"].lt(start)),
    ]
    rng = np.random.default_rng(83)
    for kwargs, excluded in cases:
        assert excluded.any()
        original = T.choose_threshold(**kwargs, edges=edges, heads=heads, wells=wells)
        changed = heads.copy()
        changed.loc[excluded, "head"] = rng.normal(0, 1e6, size=excluded.sum())
        assert T.choose_threshold(**kwargs, edges=edges, heads=changed, wells=wells) == original, kwargs
    temporal = T.choose_threshold(edges=edges, heads=heads, wells=wells)
    refit = T.choose_threshold("refit", edges=edges, heads=heads, wells=wells)
    assert refit == {**temporal, "regime": "refit"}
    print("  3. Perturbing excluded heads leaves the R1, R2 and R3 records identical. The refit uses R1 support.")


def test_missing_depth(edges, heads, wells):
    record = T.choose_threshold(edges=edges, heads=heads, wells=wells)
    candidates = records_by_threshold(record)
    for threshold in (10.0, 20.0, 50.0):
        assert candidates[threshold]["missing_depth_excluded"] == 1
    assert candidates[None]["missing_depth_excluded"] == 0
    assert candidates[None]["kept_pairs"] == candidates[50.0]["kept_pairs"] + 1
    assert candidates[None]["qualifying_pairs"] == candidates[50.0]["qualifying_pairs"] + 1
    print("  4. The missing-depth pair only contributes to the no-limit candidate.")


def test_links(edges):
    for threshold, want in zip(T.CANDIDATES, (10, 25, 55, 56)):
        actual = T.kept_links(edges, threshold)
        directed = set(actual[["src", "dst"]].itertuples(index=False, name=None))
        assert actual["relation"].eq("well_link").all()
        assert directed == {(b, a) for a, b in directed}
        assert len(actual) == len(directed) == 2 * want, (threshold, len(actual))
        if threshold is not None:
            assert actual["depth_diff_m"].le(threshold).all()
    print("  5. Each filter returns both directions of every kept pair, including exactly-at-limit edges.")


def test_real():
    record = T.choose_threshold()
    print("  6. v4 main R1 record")
    print(json.dumps(record, allow_nan=False))
    candidates = record["candidates"]
    assert [row["kept_pairs"] for row in candidates] == [0, 2, 13, 47]
    assert candidates[0]["missing_depth_excluded"] == 5
    assert candidates[-1]["kept_pairs"] - candidates[0]["missing_depth_excluded"] == 42


def main():
    edges, heads, wells = fixture()
    test_choice()
    test_anomaly()
    test_leakage(edges, heads, wells)
    test_missing_depth(edges, heads, wells)
    test_links(edges)
    test_real()
    print("test_depth_threshold: all checks passed")


if __name__ == "__main__":
    main()
