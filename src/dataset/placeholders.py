"""Suspect placeholder values in the head records: long runs of a depth of exactly 0.00 m.

    PFE_DATASET=v4 python -m src.dataset.placeholders      # -> <dataset>/placeholder_weeks.parquet

Found on 2026-10-24 while picking representative hydrographs by rule (third review §7):
CORNEILLA PD5 (10971X0155/PD5, core, Pliocene, 153 m deep) reports a depth to water of
exactly 0.00 m on 413 consecutive days (30 Nov 2022 - 15 Jan 2024), "Valeur mesurée",
"Donnée contrôlée niveau 2", qualified "Correcte" by its producer (SMNPR), during the drought;
the head is then the station altitude, 11.77 m NGF, against ~7.9 m before and 10.1 m after.
Wells that do flow record it as a negative depth (F: 2,011 days, S: 3,033, FAITOU: 5,208),
and PD5 never does: 0.00 is a default value here, not a measured head and not an artesian
cap. The producer's qualification does not catch it, so the v4 quality filter ("Incorrecte"
dropped) cannot either.

Rule (decided by Assil on 2026-10-24, docs/analysis_plan.md §13): a run of records with a
depth of exactly 0 (consecutive records, no gap above MAX_GAP_DAYS) spanning at least
MIN_RUN_DAYS days is a suspect placeholder; every week (W-SUN label) holding one of its days
leaves every scored variant (src.models.evaluate, dataset v4 on; the v3 report is unchanged).
The rule was written after the test period was seen, so the v4 primary table is also shown
without it (variant "all_unmasked"). Short runs (a few days at the surface) are kept: they
can be real. Model inputs never contain heads (simulation), and no flagged week falls in the
training or validation periods (checked below), so no model needs re-training.
"""
import json

import pandas as pd

from src.config import DATASET_DIR

MIN_RUN_DAYS = 28
MAX_GAP_DAYS = 7
WEEK = "W-SUN"
OUT = DATASET_DIR / "placeholder_weeks.parquet"


def runs_of_zero_depth(d):
    """Runs of records with depth == 0: DataFrame (start, end, n_records, span_days)."""
    d = d.dropna(subset=["profondeur_nappe"]).sort_values("date_mesure")
    zero = d["profondeur_nappe"].eq(0).to_numpy()
    t = d["date_mesure"].to_numpy()
    rows, start, prev, n = [], None, None, 0
    for z, day in zip(zero, t):
        if z and start is not None and (day - prev) / pd.Timedelta(days=1) <= MAX_GAP_DAYS:
            prev, n = day, n + 1
            continue
        if start is not None:
            rows.append((start, prev, n))
            start = None
        if z:
            start, prev, n = day, day, 1
    if start is not None:
        rows.append((start, prev, n))
    r = pd.DataFrame(rows, columns=["start", "end", "n_records"])
    r["span_days"] = ((pd.to_datetime(r["end"]) - pd.to_datetime(r["start"])).dt.days + 1
                      if len(r) else pd.Series(dtype=int))
    return r


def placeholder_weeks(codes):
    """(code_bss, week) of every week touched by a run of >= MIN_RUN_DAYS days."""
    # imported here: src.models.evaluate imports this module on machines without the raw
    # data or the download stack (Kaggle, Colab), and only needs load_mask()
    from src.ingest.hubeau_piezo import CHRON, safe_name
    weeks, log = [], []
    for code in codes:
        f = CHRON / f"{safe_name(code)}.parquet"
        if not f.exists():
            continue
        d = pd.read_parquet(f, columns=["date_mesure", "profondeur_nappe"])
        d["date_mesure"] = pd.to_datetime(d["date_mesure"])
        r = runs_of_zero_depth(d)
        for _, run in r[r["span_days"] >= MIN_RUN_DAYS].iterrows():
            days = pd.date_range(run["start"], run["end"], freq="D")
            wk = pd.Series(days).dt.to_period(WEEK).dt.end_time.dt.normalize().unique()
            weeks += [(code, w) for w in wk]
            log.append({"code_bss": code, "start": run["start"].date(), "end": run["end"].date(),
                        "days": int(run["span_days"]), "weeks": len(wk)})
    out = pd.DataFrame(weeks, columns=["code_bss", "week"]).drop_duplicates()
    out["week"] = pd.to_datetime(out["week"])
    return out.sort_values(["code_bss", "week"]).reset_index(drop=True), pd.DataFrame(log)


def load_mask():
    """The flagged (code_bss, week) pairs of the current dataset; None if absent."""
    return pd.read_parquet(OUT) if OUT.exists() else None


def main():
    wells = pd.read_parquet(DATASET_DIR / "wells.parquet")
    mask, log = placeholder_weeks(wells["code_bss"])
    splits = json.loads((DATASET_DIR / "splits.json").read_text())
    before_test = mask["week"] < pd.Timestamp(splits["test"][0])
    assert not before_test.any(), ("a flagged week falls before the test period: the models "
                                   f"trained on it\n{mask[before_test]}")
    mask.to_parquet(OUT, index=False)
    core = set(wells.loc[wells["core"], "code_bss"])
    print(f"runs of >= {MIN_RUN_DAYS} days at a depth of exactly 0.00 m:")
    print(log.assign(core=log["code_bss"].isin(core)).to_string(index=False) if len(log) else "  none")
    print(f"{len(mask)} well-weeks flagged ({mask['code_bss'].isin(core).sum()} in core wells), "
          f"none before the test period -> {OUT}")


if __name__ == "__main__":
    main()
