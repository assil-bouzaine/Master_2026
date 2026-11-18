"""Checks of the declared rung-3 facts (analysis plan §14 item 18; Gate 3 point 2).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_statics

Check well order, independent anchors, training-window isolation, missing flags and seeded
controls. These checks read the dataset and inject changes in memory. They fit no model and
write no data. A small artificial example makes the annual denominator and raw volumes explicit.
"""
import json
from functools import lru_cache

import numpy as np
import pandas as pd

from src.config import DATASET_DIR
from src.models import statics as S
from src.models.routing import load_edges

ANCHORS = ("10906X0039/C2-1", "10964X0119/NYLS-1")
FLAGS = ("depth_missing", "stack_missing", "pump_none", "river_on_outcrop", "river_over_cover",
         "river_lateral", "canal")


@lru_cache(maxsize=1)
def inputs():
    tables = {name: pd.read_parquet(DATASET_DIR / f"{name}.parquet")
              for name in ("wells", "pumping_weekly", "pumping_points")}
    tables["edges"] = load_edges("D")[0]
    return tables, json.loads((DATASET_DIR / "splits.json").read_text())


def declared_rows(tables, splits, train_start=None):
    """Independent oracle: filter weekly rows first, then sum each well's linked rows."""
    pumping, points = tables["pumping_weekly"], tables["pumping_points"]
    facilities = set(points.loc[points["source"] == "groundwater", "code_ouvrage"])
    start, end = train_start or splits["train"][0], splits["train"][1]
    rows = pumping.loc[pumping["code_ouvrage"].isin(facilities) & (~pumping["imputed"])
                       & (pumping["week"] >= pd.Timestamp(start))
                       & (pumping["week"] <= pd.Timestamp(end))]
    return rows, rows["week"].dt.year.nunique()


def anchor_pumping(rows, n_years, edges, code):
    totals = []
    for relation in ("pumping", "pumping_unattributed"):
        facilities = set(edges.loc[(edges["dst"] == code) & (edges["relation"] == relation), "src"])
        totals.append(rows.loc[rows["code_ouvrage"].isin(facilities), "volume_m3"].sum() / n_years)
    return totals


def test_shape():
    tables, _ = inputs()
    expected_a = ["log_depth", "depth_missing", "altitude", "stack_pos", "stack_missing", "artesian"]
    expected_b = expected_a + ["pump_attr_share", "pump_none", "log_pump_attr", "n_recharge_cells",
                               "river_on_outcrop", "river_over_cover", "river_lateral", "canal"]
    assert S.FEATURES == {"A": expected_a, "B": expected_b}
    assert len(tables["wells"]) == 65
    expected_index = pd.Index(tables["wells"]["code_bss"], name="code_bss")
    for features in ("A", "B"):
        actual = S.static_table(features)
        assert actual.shape == (65, len(S.FEATURES[features]))
        pd.testing.assert_index_equal(actual.index, expected_index)
        assert list(actual.columns) == S.FEATURES[features]
        pd.testing.assert_frame_equal(actual, S.static_table(features, tables=tables))
    with_wells_only = S.static_table("A", tables={"wells": tables["wells"]})
    pd.testing.assert_frame_equal(with_wells_only, S.static_table("A", tables=tables))
    print("  1. A (65 x 6), B (65 x 14), dataset well order, exact columns and table injection")


def test_anchors():
    tables, splits = inputs()
    actual = S.static_table("B", tables=tables)
    rows, n_years = declared_rows(tables, splits)
    assert actual.attrs["declared_years"] == n_years
    wells, edges = tables["wells"].set_index("code_bss"), tables["edges"]
    for code in ANCHORS:
        well = wells.loc[code]
        local = edges.loc[edges["dst"] == code]
        river_tokens = {token for value in local.loc[local["relation"] == "river", "association_types"]
                        if isinstance(value, str) for token in value.split()}
        attributed, unattributed = anchor_pumping(rows, n_years, edges, code)
        expected = {"log_depth": np.log(well["profondeur_investigation"]),
                    "altitude": pd.to_numeric(well["altitude_station"]),
                    "stack_pos": well["pos_in_stack"],
                    "n_recharge_cells": int((local["relation"] == "recharge").sum()),
                    "river_on_outcrop": int("OnOutcrop" in river_tokens),
                    "river_over_cover": int("OverCover" in river_tokens),
                    "river_lateral": int("DocumentedLateral" in river_tokens),
                    "canal": int((local["relation"] == "canal").any()),
                    "pump_attr_share": attributed / (attributed + unattributed),
                    "log_pump_attr": np.log1p(attributed / 1000)}
        for column, value in expected.items():
            np.testing.assert_allclose(actual.loc[code, column], value, rtol=1e-12, atol=1e-12)
        print(f"  2. {code}: independent anchors {expected}")
    assert actual.loc[ANCHORS[0], "canal"] == 1


def test_leakage():
    tables, splits = inputs()
    pumping, points = tables["pumping_weekly"], tables["pumping_points"]
    modified = pumping.copy()
    groundwater = points.loc[points["source"] == "groundwater", "code_ouvrage"]
    excluded = ((modified["week"] > pd.Timestamp(splits["train"][1])) | modified["imputed"]
                | ~modified["code_ouvrage"].isin(groundwater))
    modified.loc[excluded, "volume_m3"] *= 1000
    for start in (None, *splits["r3_starts"].values()):
        window = {value: name for name, value in splits["r3_starts"].items()}.get(start)
        selected = f"pct_days_artesian_{window}" if window else "pct_days_artesian"
        wells = tables["wells"].copy()
        unused = [column for column in wells if column.startswith("pct_days_artesian") and column != selected]
        wells[unused] = 99.0
        injected = tables | {"wells": wells, "pumping_weekly": modified}
        for features in ("A", "B"):
            before = S.static_table(features, start, tables=tables)
            after = S.static_table(features, start, tables=injected)
            pd.testing.assert_frame_equal(before, after)
            assert before.attrs == after.attrs
    weighted = tables["edges"].copy()
    weighted["weight"] *= 1000
    pd.testing.assert_frame_equal(S.static_table(tables=tables),
                                  S.static_table(tables=tables | {"edges": weighted}))
    print("  3. future, imputed and surface volumes x1000 and unused artesian shares =99: no change")


def test_windows():
    tables, splits = inputs()
    for window, start in splits["r3_starts"].items():
        actual = S.static_table("B", start, tables=tables)
        np.testing.assert_allclose(actual["artesian"], tables["wells"][f"pct_days_artesian_{window}"],
                                   equal_nan=True)
        rows, n_years = declared_rows(tables, splits, start)
        assert actual.attrs["declared_years"] == n_years
        assert actual.attrs["declared_calendar_years"] == sorted(rows["week"].dt.year.unique())
        for code in ANCHORS:
            attributed, unattributed = anchor_pumping(rows, n_years, tables["edges"], code)
            np.testing.assert_allclose(actual.loc[code, "pump_attr_share"], attributed / (attributed + unattributed))
            np.testing.assert_allclose(actual.loc[code, "log_pump_attr"], np.log1p(attributed / 1000))
        huge = rows.iloc[0].to_dict()
        huge.update(week=pd.Timestamp(start) - pd.Timedelta(days=1), volume_m3=1e18)
        pumping = pd.concat([tables["pumping_weekly"], pd.DataFrame([huge])], ignore_index=True)
        after = S.static_table("B", start, tables=tables | {"pumping_weekly": pumping})
        pd.testing.assert_frame_equal(actual, after)
        assert actual.attrs == after.attrs
        print(f"  4. {window}: {start}, {n_years} declared years, matching artesian column; pre-window 1e18 ignored")
    try:
        S.static_table(train_start="not-an-R3-start", tables=tables)
    except ValueError:
        pass
    else:
        raise AssertionError("An undeclared R3 start must be refused")


def test_flags_and_declared_years():
    tables, splits = inputs()
    for start in (None, *splits["r3_starts"].values()):
        actual = S.static_table(train_start=start, tables=tables)
        for column, flag in (("log_depth", "depth_missing"), ("stack_pos", "stack_missing"),
                             ("pump_attr_share", "pump_none")):
            np.testing.assert_array_equal(actual[column].isna().to_numpy(), actual[flag].to_numpy().astype(bool))
        assert actual["pump_attr_share"].dropna().between(0, 1).all()
        assert all(set(actual[flag].unique()) <= {0, 1} for flag in FLAGS)

    # Artificial rows use known facility and well IDs, but the volumes below are test inputs.
    wells = tables["wells"].iloc[:2].copy()
    codes = wells["code_bss"].tolist()
    points = tables["pumping_points"]
    facilities = points.loc[points["source"] == "groundwater", "code_ouvrage"].iloc[:3].tolist()
    surface = points.loc[points["source"] == "surface", "code_ouvrage"].iloc[0]
    first_year = pd.Timestamp(splits["train"][0]).year
    dates = [pd.Timestamp(year=first_year + offset, month=6, day=1) for offset in range(4)]
    records = [(facilities[0], dates[0], 1000.0, False), (facilities[1], dates[0], 3000.0, False),
               (facilities[2], dates[1], 0.0, False), (surface, dates[2], 1e12, False),
               (facilities[0], dates[3], 1e12, True),
               (facilities[0], pd.Timestamp(splits["train"][0]) - pd.Timedelta(days=1), 1e12, False),
               (facilities[0], pd.Timestamp(splits["train"][1]) + pd.Timedelta(days=1), 1e12, False)]
    pumping = pd.DataFrame([{"code_ouvrage": facility, "week": date, "volume_m3": volume,
                             "imputed": imputed, "usage": "drinking water", "imputation": ""}
                            for facility, date, volume, imputed in records])
    edges = pd.DataFrame([
        {"relation": "pumping", "src": facilities[0], "dst": codes[0], "weight": 0.1, "association_types": None},
        {"relation": "pumping", "src": facilities[0], "dst": codes[0], "weight": 0.1, "association_types": None},
        {"relation": "pumping_unattributed", "src": facilities[1], "dst": codes[0], "weight": 0.9,
         "association_types": None},
        {"relation": "river", "src": "fixture", "dst": codes[0], "weight": 1.0,
         "association_types": "OnOutcrop OverCover DocumentedLateral"},
        {"relation": "river", "src": "fixture", "dst": codes[1], "weight": 1.0,
         "association_types": "OtherOnOutcrop"},
        {"relation": "canal", "src": "fixture", "dst": codes[0], "weight": 1.0, "association_types": None}])
    injected = {"wells": wells, "pumping_points": points, "pumping_weekly": pumping, "edges": edges}
    actual = S.static_table(tables=injected)
    assert actual.attrs["declared_years"] == 2  # includes the unlinked facility's zero-volume year
    np.testing.assert_allclose(actual.loc[codes[0], "pump_attr_share"], 0.25)
    np.testing.assert_allclose(actual.loc[codes[0], "log_pump_attr"], np.log1p(0.5))
    assert actual.loc[codes[0], ["river_on_outcrop", "river_over_cover", "river_lateral", "canal"]].eq(1).all()
    assert actual.loc[codes[1], ["river_on_outcrop", "river_over_cover", "river_lateral", "canal"]].eq(0).all()
    assert actual["n_recharge_cells"].eq(0).all()
    assert actual.loc[codes[1], "pump_none"] == 1 and pd.isna(actual.loc[codes[1], "pump_attr_share"])
    pumping = pumping.copy()
    pumping["imputed"] = True
    empty = S.static_table(tables=injected | {"pumping_weekly": pumping})
    assert empty.attrs["declared_years"] == 0 and empty["pump_none"].eq(1).all()
    assert empty["pump_attr_share"].isna().all() and empty["log_pump_attr"].eq(0).all()
    print("  5. missing flags, raw unweighted volumes, global declared years, exact tokens and no declarations")


def test_standardise_and_controls():
    tables, _ = inputs()
    for features in ("A", "B"):
        raw = S.static_table(features, tables=tables)
        original = raw.copy(deep=True)
        Z, names, stats = S.standardise(raw)
        again, again_names, again_stats = S.standardise(raw)
        assert Z.shape == raw.shape and Z.dtype == np.float32 and np.isfinite(Z).all()
        assert names == list(raw.columns) == again_names and stats == again_stats
        np.testing.assert_array_equal(Z, again)
        pd.testing.assert_frame_equal(raw, original)
        assert (Z[raw.isna().to_numpy()] == 0).all()
        unknown_altitude = raw.index.get_loc("10915X0395/PZ")
        altitude = names.index("altitude")
        known_altitudes = raw["altitude"].notna().to_numpy()
        assert pd.isna(raw.iloc[unknown_altitude]["altitude"]) and known_altitudes.sum() == 64
        assert Z[unknown_altitude, altitude] == 0
        np.testing.assert_allclose(Z[known_altitudes, altitude].mean(), 0, atol=1e-6)
        np.testing.assert_allclose(Z[known_altitudes, altitude].std(ddof=0), 1, atol=1e-6)
        for column in names:
            j = names.index(column)
            if column in FLAGS:
                np.testing.assert_array_equal(Z[:, j], raw[column].to_numpy())
                assert stats["mean"][column] == 0 and stats["sd"][column] == 1
            else:
                keep = raw[column].notna().to_numpy()
                np.testing.assert_allclose(Z[keep, j].mean(), 0, atol=1e-6)
                if raw[column].std(ddof=0) > 0:
                    np.testing.assert_allclose(Z[keep, j].std(ddof=0), 1, atol=1e-6)
                np.testing.assert_allclose(stats["mean"][column], raw[column].mean())
        json.dumps(stats, allow_nan=False)
        tags = S.name_tags(*Z.shape, seed=12)
        assert tags.shape == Z.shape and tags.dtype == np.float32
        np.testing.assert_array_equal(tags, S.name_tags(*Z.shape, seed=12))
        assert not np.array_equal(tags, S.name_tags(*Z.shape, seed=13))
        permuted = S.shuffled(Z, 12)
        assert permuted.dtype == np.float32 and permuted.shape == Z.shape
        np.testing.assert_array_equal(permuted, S.shuffled(Z, 12))
        assert not np.array_equal(permuted, S.shuffled(Z, 13))
        assert sorted(map(tuple, permuted.tolist())) == sorted(map(tuple, Z.tolist()))
        np.testing.assert_array_equal(Z, again)
        degenerate = raw.iloc[:3].copy()
        degenerate["altitude"], degenerate["artesian"] = 42.0, np.nan
        empty_Z, empty_names, empty_stats = S.standardise(degenerate)
        for column in ("altitude", "artesian"):
            assert (empty_Z[:, empty_names.index(column)] == 0).all()
            assert empty_stats["sd"][column] == 1
    print("  6. standardisation within 1e-6, altitude sentinel, missing values, JSON stats and seeded controls")


if __name__ == "__main__":
    test_shape()
    test_anchors()
    test_leakage()
    test_windows()
    test_flags_and_declared_years()
    test_standardise_and_controls()
    print("test_statics: all checks passed")
