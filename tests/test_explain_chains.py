"""Checks of the knowledge-graph explanation chains (src/explain/chains.py, Phase 5, CQ10).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_explain_chains

1. Anchor wells (``10906X0039/C2-1`` alluvium with canal/river/pumping, ``10964X0119/NYLS-1``
   Pliocene) and wells without pumping edges (core well ``10904X0104/PIEZO`` with 0 attributed
   pumping and multi-path river; ``BSS003IGLM/X`` with 0 pumping edges of any kind):
   ``check_against_export`` passes for every relation, for arm D (main, confident-only,
   all-links) and arm C (with ``influence`` empty and ``path == "distance rule"``).
2. Every core well (all 33): ``check_against_export`` passes; prints counts per relation and
   per-well timing after the store is loaded once (asserts well under 1 s per well).
3. Graph existence & targeting (SPARQL ``ASK`` queries): every returned driver IRI and ``via_iri``
   exists in the graph, and every returned ``influence`` IRI is a ``lulcw:Influence`` that targets
   the well, references its driver entity, and is selected under the policy.
4. Declared 2024 facility volumes: for two facilities, ``annual_volume_m3`` matches both the BNPE
   source table (``src.analysis.bnpe_profile.load(BNPE_SNAPSHOT)``) and the graph's
   ``lulcw:AnnualAbstractionRecord``, with ``record_kind == "declared"``; missing declarations
   stay absent (``NaN`` / ``None``), never zero.
5. CLI smoke test for arm D and arm C.
"""
from __future__ import annotations

import io
import time
from contextlib import redirect_stdout

import numpy as np
import pandas as pd

from src.analysis.bnpe_profile import load as load_bnpe
from src.config import DATASET_DIR
from src.explain.chains import (
    COLUMNS,
    REPORT_GROUP_ORDER,
    cached_store,
    chains,
    check_against_export,
    main as chains_main,
)
from src.kg.build_kg import BNPE_SNAPSHOT
from src.kg.cq import iris

ANCHOR_ALLUVIUM = "10906X0039/C2-1"
ANCHOR_PLIOCENE = "10964X0119/NYLS-1"
NO_ATTR_PUMP_CORE = "10904X0104/PIEZO"   # core well: 0 pumping_attributed, 2 river paths
NO_ANY_PUMP_WELL = "BSS003IGLM/X"        # dataset well: 0 pumping_attributed and 0 pumping_unattributed


def test_anchors_and_arm_c():
    # Anchor wells + no-pumping wells in arm D (main policy)
    for well in (ANCHOR_ALLUVIUM, ANCHOR_PLIOCENE, NO_ATTR_PUMP_CORE, NO_ANY_PUMP_WELL):
        res = check_against_export(well, policy="main", arm="D")
        df = chains(well, policy="main", arm="D", year=2024)
        assert tuple(df.columns) == COLUMNS
        assert set(df["report_group"]).issubset(set(REPORT_GROUP_ORDER))
        if well == ANCHOR_ALLUVIUM:
            assert res["counts"]["canal"] == 1
            assert res["counts"]["river"] == 1
            assert res["counts"]["pumping_attributed"] > 0
            assert res["counts"]["recharge"] > 0
        elif well == ANCHOR_PLIOCENE:
            assert res["counts"]["pumping_attributed"] > 0
            assert res["counts"]["recharge"] > 0
            assert res["counts"]["canal"] == 0
        elif well == NO_ATTR_PUMP_CORE:
            assert res["counts"]["pumping_attributed"] == 0
            # Multi-path river gauge (OnOutcrop + OverCover -> 2 influence rows, 1 unique gauge)
            assert res["counts"]["river"] == 1
            assert int((df["report_group"] == "river").sum()) == 2
        elif well == NO_ANY_PUMP_WELL:
            assert res["counts"]["pumping_attributed"] == 0
            assert res["counts"]["pumping_unattributed"] == 0

    # Sensitivity policies on anchor alluvium (all-links exercises multi-path pumping)
    for pol in ("confident-only", "all-links"):
        res_p = check_against_export(ANCHOR_ALLUVIUM, policy=pol, arm="D")
        assert res_p["counts"]["recharge"] > 0

    # Arm C (distance rules): influence empty, path == "distance rule", matches edges_C
    for well in (ANCHOR_ALLUVIUM, ANCHOR_PLIOCENE):
        res_c = check_against_export(well, policy="main", arm="C")
        df_c = chains(well, policy="main", arm="C", year=2024)
        assert tuple(df_c.columns) == COLUMNS
        assert not df_c.empty
        assert df_c["influence"].isna().all(), f"{well}: arm C must have empty influence"
        assert (df_c["path"] == "distance rule").all(), f"{well}: arm C must have path='distance rule'"
        assert not df_c["selected"].any() and not df_c["constrained"].any()
        assert res_c["counts"]["recharge"] == 1
        assert res_c["counts"]["river"] == 2
        assert res_c["counts"]["pumping_unattributed"] == 0

    print(
        f"  1. anchor wells ({ANCHOR_ALLUVIUM}, {ANCHOR_PLIOCENE}), no-attributed-pumping core well "
        f"({NO_ATTR_PUMP_CORE}), and no-pumping well ({NO_ANY_PUMP_WELL}): export equivalence passes "
        f"across arm D (main, confident-only, all-links) and arm C (path='distance rule', influence empty)"
    )


def test_all_core_wells():
    wells_df = pd.read_parquet(DATASET_DIR / "wells.parquet")
    core_wells = sorted(wells_df.loc[wells_df["core"], "code_bss"].tolist())
    assert len(core_wells) == 33, f"expected 33 core wells, got {len(core_wells)}"

    # Ensure the store and index are warmed up before timing per-well calls.
    store = cached_store()
    _ = chains(core_wells[0], policy="main", arm="D", store=store)

    totals = {grp: 0 for grp in REPORT_GROUP_ORDER}
    wells_with = {grp: 0 for grp in REPORT_GROUP_ORDER}
    total_rows = 0
    max_w_diff = 0.0
    per_well_times: list[float] = []

    t_all = time.perf_counter()
    for well in core_wells:
        t0 = time.perf_counter()
        summary = check_against_export(well, policy="main", arm="D", store=store)
        per_well_times.append(time.perf_counter() - t0)
        total_rows += summary["n_rows"]
        max_w_diff = max(max_w_diff, summary["max_recharge_weight_diff"])
        for grp in REPORT_GROUP_ORDER:
            n = summary["counts"][grp]
            totals[grp] += n
            if n > 0:
                wells_with[grp] += 1
    elapsed = time.perf_counter() - t_all
    mean_s = float(np.mean(per_well_times))
    max_s = float(np.max(per_well_times))
    assert max_s < 1.0, f"slowest core well took {max_s:.3f}s (must be < 1.0s)"

    counts_str = ", ".join(
        f"{grp}: {totals[grp]} edges ({wells_with[grp]}/33 wells)" for grp in REPORT_GROUP_ORDER
    )
    print(
        f"  2. all {len(core_wells)} core wells pass check_against_export in {elapsed:.2f}s "
        f"(mean {mean_s * 1000:.1f} ms/well, max {max_s * 1000:.1f} ms/well; "
        f"max recharge weight diff {max_w_diff:.2e}; {total_rows} chain rows). "
        f"Counts: {counts_str}"
    )


def test_iris_exist_and_target_well():
    store = cached_store()
    pz_map = iris(store, "SELECT ?c ?w WHERE { ?w a lulcw:Piezometer ; lulcw:bssCode ?c }")
    policy_iri = "https://w3id.org/lulcw/data/policy/main"

    n_inf = 0
    n_drv = 0
    n_via = 0
    checked_wells = (ANCHOR_ALLUVIUM, ANCHOR_PLIOCENE, NO_ATTR_PUMP_CORE)
    for well in checked_wells:
        well_iri = pz_map[well].value
        df = chains(well, policy="main", arm="D", year=2024, store=store)
        for row in df.itertuples(index=False):
            assert isinstance(row.driver_iri, str) and row.driver_iri.startswith("https://"), (well, row)
            ok_drv = bool(store.query(f"ASK {{ <{row.driver_iri}> ?p ?o }}"))
            assert ok_drv, f"driver IRI missing from graph: {row.driver_iri}"
            n_drv += 1

            if pd.notna(row.influence):
                q_inf = (
                    "PREFIX lulcw: <https://w3id.org/lulcw#> "
                    f"ASK {{ <{row.influence}> a lulcw:Influence ; "
                    f"lulcw:targetEntity <{well_iri}> ; "
                    f"lulcw:driverEntity <{row.driver_iri}> ; "
                    f"lulcw:selectedUnder <{policy_iri}> . }}"
                )
                assert bool(store.query(q_inf)), (
                    f"influence {row.influence} failed ASK for well {well} ({well_iri})"
                )
                n_inf += 1

            if pd.notna(row.via_iri):
                assert bool(store.query(f"ASK {{ <{row.via_iri}> ?p ?o }}")), (
                    f"via IRI missing from graph: {row.via_iri}"
                )
                n_via += 1

    print(
        f"  3. SPARQL ASK checks on {len(checked_wells)} wells: all {n_drv} driver IRIs, "
        f"{n_inf} influence IRIs (typed, targeting the well, matching driver, selectedUnder main), "
        f"and {n_via} via IRIs exist in the graph"
    )


def test_declared_2024_volumes():
    bnpe = load_bnpe(BNPE_SNAPSHOT)
    gw24 = bnpe[(bnpe["source"] == "groundwater") & (bnpe["annee"] == 2024)]
    print(f"     BNPE source table columns ({len(bnpe.columns)}): {list(bnpe.columns)}")

    store = cached_store()
    df_c2 = chains(ANCHOR_ALLUVIUM, policy="main", arm="D", year=2024, store=store)
    df_nyls = chains(ANCHOR_PLIOCENE, policy="main", arm="D", year=2024, store=store)

    # Pick one attributed facility with a 2024 declaration from each anchor well.
    f1_row = df_c2[(df_c2["report_group"] == "pumping_attributed") & df_c2["annual_volume_m3"].notna()].iloc[0]
    f2_row = df_nyls[(df_nyls["report_group"] == "pumping_attributed") & df_nyls["annual_volume_m3"].notna()].iloc[0]
    assert f1_row["driver_code"] != f2_row["driver_code"]

    checked = []
    for row in (f1_row, f2_row):
        code = row["driver_code"]
        src_vol = float(gw24.loc[gw24["code_ouvrage"] == code, "volume"].sum())
        assert abs(float(row["annual_volume_m3"]) - src_vol) < 1e-6, (
            code, row["annual_volume_m3"], src_vol
        )
        assert row["record_kind"] == "declared", (code, row["record_kind"])
        assert int(row["volume_year"]) == 2024

        # Cross-check directly against the graph's AnnualAbstractionRecord via SPARQL.
        q = (
            "PREFIX lulcw: <https://w3id.org/lulcw#> "
            "PREFIX sosa: <http://www.w3.org/ns/sosa/> "
            "SELECT (SUM(?v) AS ?tot) WHERE { "
            f'?f lulcw:bnpeCode "{code}" . '
            "?o a lulcw:AnnualAbstractionRecord ; sosa:hasFeatureOfInterest ?f ; "
            "sosa:phenomenonTime <https://w3id.org/lulcw/data/interval/year/2024> ; "
            "sosa:hasSimpleResult ?v . }"
        )
        kg_vol = float(list(store.query(q))[0]["tot"].value)
        assert abs(kg_vol - src_vol) < 1e-6, (code, kg_vol, src_vol)
        checked.append(f"{code}={src_vol:,.0f} m3 ({row['water_use']}, {row['record_kind']})")

    # Missing 2024 declaration stays absent (NaN / None), never zero.
    missing = df_c2[(df_c2["report_group"] == "pumping_attributed") & df_c2["annual_volume_m3"].isna()]
    assert not missing.empty, "expected at least one C2-1 facility without a 2024 BNPE declaration"
    m_code = missing.iloc[0]["driver_code"]
    assert gw24[gw24["code_ouvrage"] == m_code].empty
    assert pd.isna(missing.iloc[0]["annual_volume_m3"]) and pd.isna(missing.iloc[0]["record_kind"])

    # year=None leaves volume and record_kind absent for every row.
    df_none = chains(ANCHOR_ALLUVIUM, policy="main", arm="D", year=None, store=store)
    assert df_none["annual_volume_m3"].isna().all()
    assert df_none["record_kind"].isna().all()

    print(
        f"  4. declared 2024 volumes equal BNPE snapshot ({BNPE_SNAPSHOT}) and KG records: "
        + "; ".join(checked)
        + f"; missing declaration ({m_code}) stays NaN/None (never 0)"
    )


def test_cli():
    for argv, expected in (
        ([ANCHOR_ALLUVIUM, "--policy", "main", "--arm", "D", "--year", "2024", "--check"], "Export equivalence check: PASS"),
        ([ANCHOR_ALLUVIUM, "--arm", "C", "--year", "2024"], "distance rule"),
    ):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = chains_main(argv)
        out = buf.getvalue()
        assert rc == 0 and expected in out, (argv, rc, out[:200])
    print("  5. CLI smoke tests pass for arm D (--year 2024 --check) and arm C")


def main():
    test_anchors_and_arm_c()
    test_all_core_wells()
    test_iris_exist_and_target_well()
    test_declared_2024_volumes()
    test_cli()
    print("test_explain_chains: all checks passed")


if __name__ == "__main__":
    main()
