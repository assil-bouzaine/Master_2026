"""Checks of the pressure-state summaries of CQ14 (src/kg/pressure.py).

    PFE_DATASET=v4 python -m tests.test_pressure

1. For every well of the dataset and every training window (train, f25, f50), the share of days with
   the water above the measurement reference equals the dataset's artesian share column
   (wells.parquet: pct_days_artesian, _f25, _f50), NaN where the dataset has none.
2. Counts are consistent: 0 <= days above <= days; a window without a depth value has days = 0 and an
   unknown share, never 0; the windows' dates are the dataset's.
"""
import numpy as np
import pandas as pd

from src.config import DATASET_DIR, R3_STARTS
from src.kg import pressure as Pr

COLUMN = {"train": "pct_days_artesian", "f25": "pct_days_artesian_f25", "f50": "pct_days_artesian_f50"}


def test_against_dataset(t):
    wells = pd.read_parquet(DATASET_DIR / "wells.parquet").set_index("code_bss")
    n = 0
    for w, col in COLUMN.items():
        got = t[t["window"] == w].set_index("code_bss")["share_pct"].reindex(wells.index)
        want = pd.to_numeric(wells[col], errors="coerce")
        both_nan = got.isna() & want.isna()
        same = np.isclose(got.fillna(-1), want.fillna(-1), rtol=0, atol=1e-9) | both_nan
        assert same.all(), (w, got[~same].head(), want[~same].head())
        n += len(got)
    print(f"  1. {n} well-window shares = the dataset's artesian columns "
          f"({int((t['share_pct'] > 0).sum())} positive)")


def test_counts(t):
    assert ((0 <= t["days_above"]) & (t["days_above"] <= t["days"])).all()
    assert t.loc[t["days"] == 0, "share_pct"].isna().all() and t.loc[t["days"] > 0, "share_pct"].notna().all()
    win = Pr.windows()
    assert win["f25"][0] == pd.Timestamp(R3_STARTS["f25"]) and win["f50"][0] == pd.Timestamp(R3_STARTS["f50"])
    assert len({e for _, e in win.values()}) == 1, "every window ends with the training period"
    for w, (s, e) in win.items():
        rows = t[t["window"] == w]
        assert (rows["start"] == s).all() and (rows["end"] == e).all(), w
    print(f"  2. counts consistent; {int((t['days'] == 0).sum())} well-windows without a depth value "
          f"(share unknown, not 0); windows {', '.join(f'{k} {s.date()}' for k, (s, _) in win.items())}")


def main():
    t = Pr.summaries()
    test_against_dataset(t)
    test_counts(t)
    print("test_pressure: all checks passed")


if __name__ == "__main__":
    main()
