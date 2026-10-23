"""Invariants of the pump -> unit attribution table (task 12.3).

    PFE_DATASET=v4 python -m src.kg.pump_attribution && python -m tests.test_pump_attribution

Every groundwater ouvrage has exactly one main candidate (rank 1); confidences come from
the declared set; an unknown candidate has no unit; a depth-overridden record keeps the
recorded unit as a "possible" alternative; a rule judged "probable" never covers a use it
was not evaluated on.
"""
import json

import pandas as pd

from src.config import INTERIM

CONFIDENCE = {"confident", "probable", "possible", "unknown"}


def main():
    f = INTERIM / "pump_unit_attribution.parquet"
    if not f.exists():
        print("pump_unit_attribution.parquet not built here, skipped")
        return
    a = pd.read_parquet(f)
    ev = pd.read_parquet(INTERIM / "pump_unit_evidence.parquet")
    report = json.loads((INTERIM / "pump_unit_attribution_eval.json").read_text())
    main_rows = a[a["rank"] == 1]
    assert main_rows["code_ouvrage"].is_unique, "an ouvrage with two main candidates"
    assert set(main_rows["code_ouvrage"]) == set(ev["code_ouvrage"]), "an ouvrage is missing"
    assert set(a["confidence"]) <= CONFIDENCE, set(a["confidence"])
    unknown = a["confidence"] == "unknown"
    assert a.loc[unknown, "unit"].isna().all() and a.loc[~unknown, "unit"].notna().all()
    over = a.loc[a["rule"] == "record_depth", "code_ouvrage"]
    alt = a[(a["rank"] == 2) & a["code_ouvrage"].isin(over)]
    assert len(alt) == len(over) and (alt["confidence"] == "possible").all()
    use = ev.set_index("code_ouvrage")["usage_main"]
    for rule, r in report["rules"].items():
        prob = main_rows[(main_rows["rule"] == rule) & (main_rows["confidence"] == "probable")]
        assert prob["code_ouvrage"].map(use).isin(r["by_use"]).all(), rule
    print(f"test_pump_attribution: all checks passed ({len(main_rows)} ouvrages)")


if __name__ == "__main__":
    main()
