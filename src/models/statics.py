"""Declared well facts for ladder rung 3 (analysis plan §14 item 18; Gate 3 point 2).

The sets are declared before any real-data rung-3 result exists. Set A uses dataset facts:
log_depth is the natural log of investigation depth, altitude is the station altitude in metres,
stack_pos is the unit's position in the stack, and artesian is the training window's artesian
share. depth_missing and stack_missing mark unknown depth and stack position.
An altitude of -999 is the source's unknown code and is treated as NaN.

Set B adds knowledge as information (arm B): pump_attr_share is the attributed fraction of
nearby declared groundwater pumping; pump_none marks a zero total; log_pump_attr is
log1p(attributed annual m3 / 1000); n_recharge_cells counts recharge edges. river_on_outcrop,
river_over_cover and river_lateral mark the export's river-association tokens; canal marks a
canal edge. Pump volumes are raw sums over linked facilities, without distance weights.

Only non-imputed groundwater rows inside [training start, training end] enter the pumping
features. Divide by the number of calendar years with any such row, including partial years.
R3 uses the shared R3_STARTS mapping and the matching artesian-share column, like build_panel.
Unknown raw values stay NaN; standardise replaces their standardized values with zero.
The seeded name-tag control follows Heudorfer et al. 2024, doi:10.5194/hess-28-525-2024.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m src.models.statics --features B
"""
import argparse
import json

import numpy as np
import pandas as pd

from src.config import DATASET_DIR, R3_STARTS
from src.models.routing import load_edges

FEATURES = {"A": ["log_depth", "depth_missing", "altitude", "stack_pos", "stack_missing", "artesian"]}
FEATURES["B"] = FEATURES["A"] + ["pump_attr_share", "pump_none", "log_pump_attr", "n_recharge_cells",
                                     "river_on_outcrop", "river_over_cover", "river_lateral", "canal"]
FLAGS = ("depth_missing", "stack_missing", "pump_none", "river_on_outcrop", "river_over_cover",
         "river_lateral", "canal")
RIVER_TOKENS = {"river_on_outcrop": "OnOutcrop", "river_over_cover": "OverCover",
                "river_lateral": "DocumentedLateral"}


def training_window(train_start):
    splits = json.loads((DATASET_DIR / "splits.json").read_text())
    window = None
    if train_start is not None:
        window = {value: name for name, value in R3_STARTS.items()}.get(train_start)
        if window is None:
            raise ValueError(f"train_start {train_start} is not an R3 window {R3_STARTS}")
    return pd.Timestamp(train_start or splits["train"][0]), pd.Timestamp(splits["train"][1]), window


def declared_volumes(pumping_weekly, pumping_points, start, end):
    """Annual facility volumes, using the same declared-year denominator for every well."""
    groundwater = pumping_points.loc[pumping_points["source"] == "groundwater", "code_ouvrage"]
    weeks = pd.to_datetime(pumping_weekly["week"])
    keep = (pumping_weekly["imputed"].eq(False) & pumping_weekly["code_ouvrage"].isin(groundwater)
            & weeks.between(start, end))
    declared = pumping_weekly.loc[keep]
    years = sorted(int(year) for year in weeks.loc[keep].dt.year.unique())
    if not years:
        return pd.Series(dtype=float), years
    annual = declared.groupby("code_ouvrage")["volume_m3"].sum() / len(years)
    return annual, years


def linked_volumes(edges, relation, annual, codes):
    """A facility contributes once per well, even if an input repeats an evidence edge."""
    links = edges.loc[edges["relation"] == relation, ["src", "dst"]].drop_duplicates()
    volumes = links["src"].map(annual).fillna(0.0)
    return volumes.groupby(links["dst"]).sum().reindex(codes, fill_value=0.0)


def static_table(features="B", train_start=None, policy="main", tables=None):
    """Raw declared columns in dataset well order. Injection tables are never modified.

    B's attrs include declared_years (a count) and declared_calendar_years (the actual years).
    With no declared year, pumping totals are zero, pump_none is one and the share is unknown.
    A reads only wells and split metadata; it does not require an export or pumping tables.
    """
    if features not in FEATURES:
        raise ValueError(f"features must be one of {list(FEATURES)}, got {features!r}")
    start, end, window = training_window(train_start)
    wells = (pd.read_parquet(DATASET_DIR / "wells.parquet") if tables is None else tables["wells"])
    wells = wells.set_index("code_bss")
    depth = pd.to_numeric(wells["profondeur_investigation"], errors="coerce")
    stack = pd.to_numeric(wells["pos_in_stack"], errors="coerce")
    artesian_column = f"pct_days_artesian_{window}" if window else "pct_days_artesian"
    out = pd.DataFrame(index=wells.index)
    out["log_depth"] = np.log(depth)
    out["depth_missing"] = depth.isna().astype("uint8")
    out["altitude"] = pd.to_numeric(wells["altitude_station"], errors="coerce").replace(-999, np.nan)
    out["stack_pos"] = stack
    out["stack_missing"] = stack.isna().astype("uint8")
    out["artesian"] = pd.to_numeric(wells[artesian_column], errors="coerce")
    out.attrs = {"train_start": start.date().isoformat(), "train_end": end.date().isoformat(),
                 "artesian_column": artesian_column}
    if features == "B":
        if tables is None:
            pumping = pd.read_parquet(DATASET_DIR / "pumping_weekly.parquet")
            points = pd.read_parquet(DATASET_DIR / "pumping_points.parquet")
            edges, _ = load_edges("D", policy)
        else:
            pumping, points, edges = (tables[key] for key in ("pumping_weekly", "pumping_points", "edges"))
        annual, years = declared_volumes(pumping, points, start, end)
        attributed = linked_volumes(edges, "pumping", annual, out.index)
        unattributed = linked_volumes(edges, "pumping_unattributed", annual, out.index)
        total = attributed + unattributed
        out["pump_attr_share"] = attributed / total.where(total != 0)
        out["pump_none"] = total.eq(0).astype("uint8")
        out["log_pump_attr"] = np.log1p(attributed / 1000)
        recharge = edges.loc[edges["relation"] == "recharge"].groupby("dst").size()
        out["n_recharge_cells"] = recharge.reindex(out.index, fill_value=0)
        river = edges.loc[edges["relation"] == "river"]
        tokens = river["association_types"].fillna("").str.split()
        for column, token in RIVER_TOKENS.items():
            destinations = river.loc[tokens.map(lambda values: token in values), "dst"]
            out[column] = out.index.isin(destinations).astype("uint8")
        out["canal"] = out.index.isin(edges.loc[edges["relation"] == "canal", "dst"]).astype("uint8")
        out.attrs.update(declared_years=len(years), declared_calendar_years=years)
    return out[FEATURES[features]]


def standardise(df):
    """Return float32 values, ordered names and JSON-ready {'mean': ..., 'sd': ...} stats.

    Use population sd (ddof=0) over the supplied wells with known values. Constant and wholly
    missing columns use sd=1; wholly missing columns use mean=0. Flags use mean=0 and sd=1
    so their values stay unchanged. NaN standardized values become zero.
    """
    names = list(df.columns)
    values = df.astype(float)
    continuous = [name for name in names if name not in FLAGS]
    means = pd.Series(0.0, index=names)
    sds = pd.Series(1.0, index=names)
    means.loc[continuous] = values[continuous].mean().fillna(0.0)
    sds.loc[continuous] = values[continuous].std(ddof=0).replace(0.0, 1.0).fillna(1.0)
    Z = ((values - means) / sds).fillna(0.0).to_numpy(dtype=np.float32)
    return Z, names, {"mean": means.to_dict(), "sd": sds.to_dict()}


def name_tags(n_wells, n_features, seed):
    """Random normal identifiers with the same width as the declared feature table."""
    return np.random.default_rng(seed).normal(size=(n_wells, n_features)).astype(np.float32)


def shuffled(Z, seed):
    """Assign the complete fact rows to other wells, preserving every row's column values."""
    return np.asarray(Z)[np.random.default_rng(seed).permutation(len(Z))].copy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", choices=list(FEATURES), default="B")
    parser.add_argument("--train-start", choices=list(R3_STARTS.values()))
    args = parser.parse_args()
    table = static_table(args.features, args.train_start)
    print(table.round(4).to_string())
    print("\nWindow metadata:", table.attrs)
    print("\nDescribe:\n" + table.describe().round(6).to_string())


if __name__ == "__main__":
    main()
