"""The land-use input snapshot is complete and current before the LU-4 runs are packaged.

    PFE_DATASET=v4 python -m tests.test_land_use_inputs

Asked by the second Codex review of 2026-10-25 (Spec 2, Standards P1): "make its completion
verifiable through an edition/lag inventory, current schemas, generated panels and passing
checks before packaging", and never let cached seeds of other land-use inputs be reused.

1. Fingerprints (synthetic): an LSTM run without --land-use keeps the fingerprint it had
   before the option existed (resumes of older runs are not refused); land-use runs with
   different input content get different fingerprints; a run folder made with other
   land-use content stops instead of reusing its cached seeds.
2. The snapshot (data are not in git; skipped when absent): RPG editions 2015-2025 all
   clipped and all in the area cache; each year 2015-2025 uses its own edition, earlier
   years the 2015 one (backfill), 2026 the 2025 one; the index file has the current
   columns; the frozen variant equals the main index in its own edition year.
3. The panels: every land-use panel exists with its identity record; the record matches
   the panel content, the current index file and the current crop-class table; its
   land-use columns are exactly the ones the current index gives; its other columns equal
   the base panel.
"""
import argparse
import hashlib
import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import DATASET, INTERIM
from src.dataset.crop_demand import AREA_META, CLASSES, FROZEN_EDITION, rpg_years
from src.models import lstm
from src.models.features import (LAND_USE, LU_COLS, build_panel, land_use_content_sha,
                                  land_use_identity, lu_cache_path)

EDITIONS = list(range(2015, 2026))
DEMAND = INTERIM / f"crop_demand_weekly_{DATASET}.parquet"


def sha16(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def check_fingerprints():
    base = dict(seeds=[0], epochs=60, run="x", arch="lstm", lookback=104, hidden=128, dropout=0.3,
                lr=1e-3, fold=None, train_start=None, refit_from=None)
    inputs = ["rain", "ETP"]
    before = lstm.run_fingerprint(argparse.Namespace(**base), inputs)  # no land_use option yet
    now = lstm.run_fingerprint(argparse.Namespace(**base, land_use=None), inputs)
    assert before == now, "an unset --land-use changed the fingerprint of older runs"
    lu = argparse.Namespace(**base, land_use="on")
    fa = lstm.run_fingerprint(lu, inputs, {"land_use_sha256_16": "a" * 16})
    fb = lstm.run_fingerprint(lu, inputs, {"land_use_sha256_16": "b" * 16})
    assert fa != fb, "other land-use content must give another fingerprint"
    none = lstm.run_fingerprint(argparse.Namespace(**base, land_use="none"), inputs)
    assert none != before, "the same-machine control must not share the run without land use"
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        lstm.write_config(out, lu, inputs, {"land_use_sha256_16": "a" * 16})
        try:
            lstm.write_config(out, lu, inputs, {"land_use_sha256_16": "b" * 16})
        except SystemExit:
            pass
        else:
            raise AssertionError("a folder made with other land-use content was reused")


def check_snapshot():
    if not DEMAND.exists():
        print(f"  {DEMAND.name} absent: snapshot checks skipped")
        return False
    assert rpg_years() == EDITIONS, f"clipped editions {rpg_years()}, expected {EDITIONS}"
    cached = sorted(int(y) for y in json.loads(AREA_META.read_text())["inputs"])
    assert cached == EDITIONS, f"area cache built from {cached}"
    d = pd.read_parquet(DEMAND)
    need = {"demand_main_m3", "demand_main_placebo_m3", "demand_wide_m3", "demand_main_frozen_m3",
            "rpg_year_used", "rpg_lag_years", "rpg_backfill"}
    assert need <= set(d.columns), f"missing columns {sorted(need - set(d.columns))}"
    y = d["week"].dt.year
    inside = y.between(EDITIONS[0], EDITIONS[-1])
    assert (d.loc[inside, "rpg_lag_years"] == 0).all(), "a year 2015-2025 does not use its own edition"
    assert (d.loc[y < EDITIONS[0], "rpg_year_used"] == EDITIONS[0]).all() and d.loc[y < EDITIONS[0], "rpg_backfill"].all()
    assert (d.loc[y > EDITIONS[-1], "rpg_year_used"] == EDITIONS[-1]).all()
    fz = y == FROZEN_EDITION
    assert np.allclose(d.loc[fz, "demand_main_frozen_m3"], d.loc[fz, "demand_main_m3"])
    lags = d.assign(year=y).groupby("year")["rpg_year_used"].first()
    print(f"  editions {EDITIONS[0]}-{EDITIONS[-1]} all used for their own year; backfill to "
          f"{int(y.min())}; {int(y.max())} uses {int(lags.iloc[-1])}")
    return True


def check_panels():
    d = pd.read_parquet(DEMAND).sort_values(["code_bss", "week"])
    base = build_panel()
    for v, col in LAND_USE.items():
        cache = lu_cache_path(v)
        assert cache.exists() and cache.with_suffix(".json").exists(), f"{cache.name} or its record missing"
        rec = land_use_identity(v)  # recomputes the content hash and compares it
        assert rec["source"]["sha256_16"] == sha16(DEMAND), f"{v}: built from another index file"
        assert rec["crop_classes"]["sha256_16"] == sha16(CLASSES), f"{v}: built with another class table"
        assert rec["rpg_editions"] == EDITIONS, f"{v}: built from editions {rec['rpg_editions']}"
        P = pd.read_parquet(cache)
        x = d[["code_bss", "week", col]].rename(columns={col: "crop_demand"})
        x["crop_demand"] = x["crop_demand"] / 1e3
        for k in (4, 13, 52):
            x[f"crop_demand_m{k}"] = x.groupby("code_bss")["crop_demand"].transform(
                lambda s: s.rolling(k, min_periods=1).mean())
        m = P[["code_bss", "week"] + LU_COLS].merge(x, on=["code_bss", "week"], suffixes=("", "_now"))
        assert len(m) == len(P), f"{v}: panel rows without an index value"
        for c in LU_COLS:
            assert np.allclose(m[c], m[f"{c}_now"]), f"{v}: {c} differs from the current index"
        assert P[base.columns].equals(base), f"{v}: base columns differ from the base panel"
        assert land_use_content_sha(P) == rec["content_sha256_16"]
    print(f"  {len(LAND_USE)} land-use panels current, records match ({', '.join(LAND_USE)})")


def main():
    check_fingerprints()
    print("fingerprint checks passed")
    if check_snapshot():
        check_panels()
    print("test_land_use_inputs: OK")


if __name__ == "__main__":
    main()
