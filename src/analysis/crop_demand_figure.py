"""Figure of the crop-demand index (LU-3).

    PFE_DATASET=v4 python -m src.analysis.crop_demand_figure

Top: irrigable crop area inside the 3 km buffers of the 65 wells, by class and RPG
edition (clipped hectares; overlapping buffers count twice). Bottom: yearly potential
demand summed over the wells, split by irrigation assumption, with the backfilled years
(before the first RPG edition) hatched.

Inputs : data/interim/crop_area_3km.parquet, data/interim/crop_demand_weekly_<dataset>.parquet
Output : reports/figures/crop_demand_index.png
"""
import matplotlib.pyplot as plt
import pandas as pd

from src.config import DATASET, FIGURES, INTERIM
from src.dataset.crop_demand import AREA_OUT, WIDE, code_to_class, load_classes


def main():
    classes = load_classes()
    irrigable = [c for c in classes.index if classes.loc[c, "irrigation_assumption"] in WIDE]
    a = pd.read_parquet(AREA_OUT)
    a["crop_class"] = code_to_class(a["CODE_CULTU"].to_numpy(), a["CODE_GROUP"].to_numpy(),
                                    classes).to_numpy()
    area = (a[a["crop_class"].isin(irrigable)]
            .pivot_table(index="rpg_year", columns="crop_class", values="ha", aggfunc="sum")
            .fillna(0.0))
    area = area[area.sum().sort_values(ascending=False).index]
    d = pd.read_parquet(INTERIM / f"crop_demand_weekly_{DATASET}.parquet")
    d = d[d["week"].dt.year >= 2005]
    yr = d.assign(year=d["week"].dt.year).groupby("year").agg(
        usually=("demand_usually_m3", "sum"), partly=("demand_partly_m3", "sum"),
        backfill=("rpg_backfill", "all"))
    last = d["week"].max()

    fig, (ax0, ax1) = plt.subplots(2, 1, figsize=(10, 8))
    area.plot.bar(stacked=True, ax=ax0, width=0.7, colormap="tab20")
    ax0.set_ylabel("clipped area within 3 km (ha)")
    ax0.set_xlabel("RPG edition")
    ax0.set_title("Crop classes around the 65 wells (main index: orchards, vegetables, artichoke, "
                  "maize, citrus;\nvines, olives, nuts and fodder only in the sensitivity)", fontsize=10)
    ax0.set_ylim(0, area.sum(axis=1).max() * 1.35)
    ax0.legend(ncol=5, fontsize=8, loc="upper left")
    ax0.tick_params(axis="x", rotation=0)

    x = yr.index
    ax1.bar(x, yr["usually"] / 1e6, color="#2f6690", label="main index: usually irrigated classes")
    ax1.bar(x, yr["partly"] / 1e6, bottom=yr["usually"] / 1e6, color="#9db4c0",
            label="sensitivity adds the partly irrigated classes (vines, olives, nuts, fodder)")
    bf = yr[yr["backfill"]]
    ax1.bar(bf.index, (bf["usually"] + bf["partly"]) / 1e6, fill=False, hatch="//",
            edgecolor="0.4", linewidth=0, label="crop mix backfilled from the first edition")
    ax1.set_ylabel("potential demand (Mm³/year, summed over wells)")
    ax1.set_title(f"Potential crop irrigation demand, FAO-56 Kc × ETP − rain "
                  f"({last.year} until {last:%d %b})")
    ax1.legend(fontsize=8)
    ax1.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    out = FIGURES / "crop_demand_index.png"
    fig.savefig(out, dpi=150)
    print(f"figure -> {out}")


if __name__ == "__main__":
    main()
