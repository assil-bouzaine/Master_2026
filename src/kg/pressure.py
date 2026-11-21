"""Pressure-state summaries per well and training window, for CQ14 (Gate 3 point 15; analysis plan
§14 item 23).

    PFE_DATASET=v4 python -m src.kg.pressure     # -> data/interim/pressure_state_<dataset>.parquet

For each well of the dataset and each training window of the regimes (train: the model window to the
end of training; f25 and f50: the shorter R3 windows), it counts the measurement days with a depth to
water and those with the water above the station's measurement reference (depth below zero). The
quality filter and the windows are those of the dataset's artesian share (src/dataset/build.py,
artesian_share_train), so 100 * above / days, rounded to 0.1, is that share; tests/test_pressure.py
checks it for every well and window.

What the number means, and what it does not (docs/competency_questions.md, CQ14):
- the reference is the station's measurement reference in Hub'Eau (its repère: usually the ground or
  the top of the casing), not surveyed ground, so "above the reference" is a proxy of "above the
  ground";
- a free water table cannot stand above the ground, so a head above it shows pressure, i.e. a
  confined layer, on those days; a head below it shows nothing about confinement;
- a window without any depth value gives days = 0 and an unknown share (never 0).
The graph (src/kg/build_kg.py) records each row as a pressure-state observation; the rules derive the
confinement assessment from it, never from the geological stack alone.
"""
import argparse

import numpy as np
import pandas as pd

from src.config import DATASET, DATASET_DIR, INTERIM, R3_STARTS

WINDOWS = ("train", "f25", "f50")


def windows():
    """name -> (start, end) dates of the training windows, as the dataset builder uses them."""
    from src.dataset import build as B
    return {"train": (pd.Timestamp(B.MODEL_START), pd.Timestamp(B.TRAIN_END)),
            "f25": (pd.Timestamp(R3_STARTS["f25"]), pd.Timestamp(B.TRAIN_END)),
            "f50": (pd.Timestamp(R3_STARTS["f50"]), pd.Timestamp(B.TRAIN_END))}


def day_counts(code, start, end):
    """(days with a depth to water, days with the water above the reference) for one well, with the
    dataset's quality filter; (0, 0) when the station has no series file."""
    from src.dataset import build as B
    f = B.CHRON / f"{B.safe_name(code)}.parquet"
    if not f.exists():
        return 0, 0
    df = pd.read_parquet(f, columns=["date_mesure", "profondeur_nappe", "qualification"])
    if B.CFG.get("drop_bad_quality"):
        df = df[~df["qualification"].isin(B.BAD_QUALITY)]
    df["date_mesure"] = pd.to_datetime(df["date_mesure"])
    df = df[df["date_mesure"].between(start, end)].dropna(subset=["profondeur_nappe"])
    return int(len(df)), int((df["profondeur_nappe"] < 0).sum())


def summaries(codes=None):
    """One row per well and window: days, days above the reference, the share in percent (NaN when
    days = 0), the window's dates."""
    if codes is None:
        codes = pd.read_parquet(DATASET_DIR / "wells.parquet", columns=["code_bss"])["code_bss"].tolist()
    rows = []
    for name, (start, end) in windows().items():
        for c in codes:
            days, above = day_counts(c, start, end)
            rows.append({"code_bss": c, "window": name, "start": start, "end": end, "days": days,
                         "days_above": above,
                         "share_pct": round(100 * above / days, 1) if days else np.nan})
    return pd.DataFrame(rows)


def out_path(dataset=DATASET):
    return INTERIM / f"pressure_state_{dataset}.parquet"


def main():
    argparse.ArgumentParser(description=__doc__.split("\n\n")[0]).parse_args()
    t = summaries()
    t.to_parquet(out_path(), index=False)
    pos = t[t["share_pct"] > 0]
    print(f"{len(t)} well-window rows; head above the reference on some days: "
          + ", ".join(f"{w} {int((pos['window'] == w).sum())} wells" for w in WINDOWS)
          + f"; windows without a depth value: {int((t['days'] == 0).sum())}")
    print(f"-> {out_path()}")


if __name__ == "__main__":
    main()
