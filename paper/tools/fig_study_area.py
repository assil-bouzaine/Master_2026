"""Draw Figure 1 of the paper, the Roussillon study area.

BD LISA gives the outcropping polygons. The KG's typing rule colours them and
the well units (analysis plan section 14, item 14). The v4 graph export supplies
wells, gauges and abstraction facilities. BD TOPO supplies rivers and canals,
and Natural Earth supplies the coast and the locator inset. All inputs are local.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python paper/tools/fig_study_area.py [--out DIR]
"""
import argparse
from pathlib import Path
import sys

import geopandas as gpd
import matplotlib
import pandas as pd
from shapely import get_parts, line_merge
from shapely.geometry import box

matplotlib.use("Agg")
import matplotlib.patheffects as effects
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgb
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.analysis.bdlisa_profile import stacks_of
from src.config import CRS_L93, CRS_WGS84, PROCESSED, RAW, ROOT
from src.kg.build_kg import L, load_bdlisa, unit_class

NODES = PROCESSED / "kg" / "export_v4_main" / "nodes.parquet"
HYDRO = RAW / "bdtopo_hydro" / "2026-11-06"
COUNTRIES = RAW / "naturalearth" / "ne_10m_admin_0_countries.zip"
OUT = ROOT / "paper" / "figures"
MARGIN_M = 3000
RIVER_IMPORTANCE_MAX = 5
RIVER_LENGTH_MIN_M = 15_000
RIVER_NAMES = {"tet": "Têt", "agly": "Agly", "tech": "Tech", "reart": "Réart"}
UNIT_STYLE = {
    L.AlluvialAquifer: ("Alluvial aquifer", "#009e73"),
    L.MultilayerAquiferSystem: ("Multilayer aquifer system", "#d55e00"),
    L.KarstAquifer: ("Karst aquifer", "#0072b2"),
    L.ConfiningUnit: ("Confining unit", "#cc79a7"),
    L.HydrogeologicalUnit: ("Other hydrogeological unit", "#e69f00"),
}
INK = "#25313b"
LAND = "#f3f3f1"
SEA = "#e5f0f5"
RIVER = "#23668f"
CANAL = "#365d69"
FACILITY = "#5b6268"
UNCLASSIFIED = "#43474d"
CANAL_DASH = (0, (3, 1.8))
PLAIN_DASH = (0, (4, 2.5))
TEXT_HALO = [effects.withStroke(linewidth=2.1, foreground="white")]


def pale(colour):
    """Make a lighter fill in the same hue as the well symbol."""
    return tuple(0.72 + 0.28 * channel for channel in to_rgb(colour))


def read_countries():
    """Read the western Mediterranean from the local Natural Earth archive."""
    countries = gpd.read_file(f"zip://{COUNTRIES}", columns=["NAME"])
    return countries.clip(box(-12, 33, 14, 53)).to_crs(CRS_L93)


def outcrops_and_well_classes(wells, extent, land):
    tme, pile, polygons, plain = load_bdlisa(wells.geometry, aoi=extent)
    polygons = polygons.loc[polygons.intersects(extent)].copy()
    # The source has some invalid rings. Clip the repaired shapes at the coastline.
    polygons.geometry = polygons.geometry.make_valid().intersection(land)
    polygons = polygons.loc[polygons.area.gt(0)].copy()
    stacks = stacks_of(pile, polygons["codepoly"])
    top = polygons["codepoly"].map(lambda code: stacks[code][0])
    codes = set(top) | set(wells["unit"].dropna())
    classes = {code: unit_class(code, tme.loc[code] if code in tme.index else None) for code in codes}
    polygons["unit_class"] = top.map(classes)
    return polygons, wells["unit"].map(classes), plain


def clip_lines(lines, extent):
    visible = lines.loc[lines.intersects(extent)].copy()
    visible.geometry = visible.geometry.intersection(extent)
    return visible.loc[visible.length.gt(0)].copy()


def read_waterways(extent):
    rivers = gpd.read_parquet(HYDRO / "cours_d_eau.parquet",
                             columns=["toponyme", "importance", "geometry"]).to_crs(CRS_L93)
    rivers = clip_lines(rivers, extent)
    print("BD TOPO importance counts in the map extent",
          rivers["importance"].value_counts(dropna=False).sort_index().to_dict(), flush=True)
    names = rivers["toponyme"].str.strip().str.lower().str.replace("’", "'", regex=False)
    names = names.str.normalize("NFKD").str.encode("ascii", errors="ignore").str.decode("ascii")
    rivers["label"] = names.str.replace(r"^(?:l'|la |le |el )", "", regex=True).map(RIVER_NAMES)
    # Rank 5 contains many small streams. Keep long visible reaches and the four named rivers.
    main = rivers.length.ge(RIVER_LENGTH_MIN_M) | rivers["label"].notna()
    is_canal = names.str.startswith("canal ", na=False)
    rivers = rivers.loc[pd.to_numeric(rivers["importance"], errors="coerce").le(RIVER_IMPORTANCE_MAX)
                        & main & ~is_canal]
    names_kept = sorted(set(rivers["toponyme"].dropna().str.strip()) - {""}, key=str.casefold)
    print("Watercourse names kept", ", ".join(names_kept), flush=True)
    canals = gpd.read_parquet(HYDRO / "troncon_hydrographique.parquet", columns=["nature", "geometry"])
    canals = clip_lines(canals.loc[canals["nature"] == "Canal"].to_crs(CRS_L93), extent)
    return rivers, canals


def draw_waterways(ax, rivers, canals):
    if not canals.empty:
        canals.plot(ax=ax, color=CANAL, linewidth=0.55, linestyle=CANAL_DASH, alpha=0.82, zorder=3)
    major = rivers.loc[rivers["label"].notna()]
    context = rivers.loc[rivers["label"].isna()]
    if not context.empty:
        context.plot(ax=ax, color=RIVER, linewidth=0.45, alpha=0.68, zorder=4)
    if not major.empty:
        major.plot(ax=ax, color=RIVER, linewidth=0.85, zorder=4)
    label_fractions = {"Agly": 0.52, "Têt": 0.50, "Tech": 0.48, "Réart": 0.76}
    for name, reaches in major.groupby("label"):
        trunk = max(get_parts(line_merge(reaches.geometry.union_all())), key=lambda line: line.length)
        point = trunk.interpolate(label_fractions[name], normalized=True)
        ax.annotate(name, (point.x, point.y), xytext=(0, 3), textcoords="offset points",
                    ha="center", va="bottom", color=RIVER, fontsize=7.5,
                    fontstyle="italic", path_effects=TEXT_HALO, zorder=5)


def draw_points(ax, wells, gauges, facilities):
    ax.scatter(facilities["x93"], facilities["y93"], s=1.6, color=FACILITY,
               linewidths=0, alpha=0.54, zorder=6)
    ax.scatter(gauges["x93"], gauges["y93"], s=31, marker="^", color=INK,
               linewidths=0.65, edgecolors="white", zorder=8)
    colours = wells["unit_class"].map({kind: style[1] for kind, style in UNIT_STYLE.items()})
    colours = colours.fillna(UNCLASSIFIED)
    core = wells["core"].eq(True)
    ax.scatter(wells.loc[~core, "x93"], wells.loc[~core, "y93"], s=18,
               facecolors="none", edgecolors=colours[~core], linewidths=0.88, zorder=9)
    ax.scatter(wells.loc[core, "x93"], wells.loc[core, "y93"], s=23,
               c=colours[core], edgecolors=INK, linewidths=0.45, zorder=10)


def draw_map_furniture(ax, plain, extent):
    west, south, east, north = extent.bounds
    dx, dy = east - west, north - south
    x, y = plain.exterior.coords.xy
    ax.plot(x, y, color=INK, linestyle=PLAIN_DASH, linewidth=0.9, zorder=7)
    ax.annotate("plain", plain.exterior.coords[3], xytext=(4, 5), textcoords="offset points",
                va="bottom", color=INK, fontsize=7.5, path_effects=TEXT_HALO, zorder=7)
    x0, y0 = east - 0.038 * dx - 10_000, south + 0.045 * dy
    ax.hlines(y0, x0, x0 + 10_000, color=INK, linewidth=1.1, zorder=7)
    ax.vlines([x0, x0 + 10_000], y0 - 280, y0 + 280, color=INK, linewidth=0.85, zorder=7)
    ax.annotate("10 km", (x0 + 5000, y0), xytext=(0, 3), textcoords="offset points",
                ha="center", va="bottom", color=INK, fontsize=7.5, path_effects=TEXT_HALO, zorder=7)
    x, y = east - 0.038 * dx, north - 0.075 * dy
    ax.annotate("", xy=(x, y), xytext=(x, y - 0.045 * dy),
                arrowprops={"arrowstyle": "-|>", "color": INK, "lw": 1, "mutation_scale": 9}, zorder=7)
    ax.annotate("N", (x, y), xytext=(0, 2), textcoords="offset points", ha="center",
                va="bottom", color=INK, fontsize=8, path_effects=TEXT_HALO, zorder=7)


def draw_inset(ax, countries, extent):
    locator = ax.inset_axes([0.014, 0.653, 0.236, 0.329])
    locator.set_facecolor(SEA)
    countries.plot(ax=locator, color=LAND, edgecolor="#9aa4a7", linewidth=0.34, zorder=1)
    west, south, east, north = extent.bounds
    locator.add_patch(Rectangle((west, south), east - west, north - south,
                                fill=False, edgecolor="#a32924", linewidth=1.0, zorder=3))
    anchors = gpd.GeoSeries(gpd.points_from_xy([2.0, -3.7], [46.5, 40.0]), crs=CRS_WGS84).to_crs(CRS_L93)
    for name, point in zip(("France", "Spain"), anchors):
        locator.text(point.x, point.y, name, ha="center", va="center", color=INK, fontsize=7, zorder=2)
    xmin, ymin, xmax, ymax = countries.total_bounds
    locator.set(xlim=(xmin, xmax), ylim=(ymin, ymax), aspect="equal",
                xlabel="", ylabel="", xticks=[], yticks=[])
    for spine in locator.spines.values():
        spine.set(color="#87949b", linewidth=0.55)


def draw_legend(ax):
    units = [Patch(facecolor=pale(colour), edgecolor=colour, linewidth=0.65, label=label)
             for label, colour in UNIT_STYLE.values()]
    symbols = [
        Line2D([], [], marker="o", markerfacecolor=INK, color=INK, linestyle="none",
               markersize=4.4, label="Core well"),
        Line2D([], [], marker="o", markerfacecolor="none", color=INK, linestyle="none",
               markersize=4.2, label="Other well"),
        Line2D([], [], marker="^", color=INK, linestyle="none", markersize=4.7, label="River gauge"),
        Line2D([], [], marker=".", color=FACILITY, linestyle="none", markersize=3.8,
               label="Abstraction facility"),
        Line2D([], [], color=RIVER, linewidth=0.85, label="River"),
        Line2D([], [], color=CANAL, linestyle=CANAL_DASH, linewidth=0.7, label="Canal"),
        Line2D([], [], color=INK, linestyle=PLAIN_DASH, linewidth=0.9, label="Plain extent"),
    ]
    layout = {"loc": "center left", "mode": "expand", "frameon": False, "fontsize": 7.4,
              "handlelength": 1.7, "handletextpad": 0.45, "borderaxespad": 0, "labelcolor": INK}
    unit_legend = ax.legend(handles=units, ncols=len(units), bbox_to_anchor=(0, 0.59, 1, 0.32), **layout)
    ax.add_artist(unit_legend)
    ax.legend(handles=symbols, ncols=len(symbols), bbox_to_anchor=(0, 0.07, 1, 0.32), **layout)
    ax.set_axis_off()


def figure_axes(extent):
    """Fit the well-based map and legend inside the paper's double-column size."""
    width, pad, legend = 190, 1.6, 16
    west, south, east, north = extent.bounds
    aspect = (east - west) / (north - south)
    map_width = min(width - 2 * pad, (170 - legend - 2 * pad) * aspect)
    map_height = map_width / aspect
    height = map_height + legend + 2 * pad
    fig = plt.figure(figsize=(width / 25.4, height / 25.4), facecolor="white")
    ax = fig.add_axes([(width - map_width) / (2 * width), (legend + pad) / height,
                       map_width / width, map_height / height], facecolor=SEA)
    key = fig.add_axes([pad / width, pad / height, (width - 2 * pad) / width, legend / height])
    return fig, ax, key


def draw_study_area(out=OUT):
    """Write the PDF and 200 dpi PNG. Return counts for the features drawn."""
    nodes = pd.read_parquet(NODES)
    nodes = gpd.GeoDataFrame(nodes, geometry=gpd.points_from_xy(nodes["x93"], nodes["y93"]), crs=CRS_L93)
    wells = nodes.loc[nodes["type"] == "well"].copy()
    west, south, east, north = wells.total_bounds
    extent = box(west - MARGIN_M, south - MARGIN_M, east + MARGIN_M, north + MARGIN_M)
    visible = nodes.loc[nodes.intersects(extent)]
    gauges = visible.loc[visible["type"] == "gauge"]
    facilities = visible.loc[visible["type"] == "facility"]
    countries = read_countries()
    land = countries.geometry.loc[countries.intersects(extent)].make_valid().union_all().intersection(extent)
    polygons, wells["unit_class"], plain = outcrops_and_well_classes(wells, extent, land)
    rivers, canals = read_waterways(extent)

    fig, ax, key = figure_axes(extent)
    gpd.GeoSeries([land], crs=CRS_L93).plot(ax=ax, color=LAND, zorder=1)
    for kind, (_, colour) in UNIT_STYLE.items():
        layer = polygons.loc[polygons["unit_class"] == kind]
        if not layer.empty:
            layer.plot(ax=ax, color=pale(colour), linewidth=0.18, edgecolor="#fcfcfb", zorder=2)
    draw_waterways(ax, rivers, canals)
    draw_points(ax, wells, gauges, facilities)
    draw_map_furniture(ax, plain, extent)
    draw_inset(ax, countries, extent)
    draw_legend(key)
    west, south, east, north = extent.bounds
    ax.set(xlim=(west, east), ylim=(south, north), aspect="equal",
           xlabel="", ylabel="", xticks=[], yticks=[])
    for spine in ax.spines.values():
        spine.set(color="#87949b", linewidth=0.55)

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    with matplotlib.rc_context({"pdf.fonttype": 42}):
        fig.savefig(out / "study_area.pdf", metadata={"Title": "Roussillon study area", "CreationDate": None})
        fig.savefig(out / "study_area.png", dpi=200)
    plt.close(fig)
    counts = polygons["unit_class"].value_counts()
    return {"wells": len(wells), "core_wells": int(wells["core"].eq(True).sum()),
            "gauges": len(gauges), "facilities": len(facilities),
            "polygons_per_class": {str(kind).removeprefix(str(L)): int(counts.get(kind, 0))
                                   for kind in UNIT_STYLE},
            "rivers_kept": len(rivers), "canal_pieces": len(canals),
            "wells_without_class": int(wells["unit_class"].isna().sum())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT, help="directory for the PDF and PNG")
    args = parser.parse_args()
    print("Study-area counts", draw_study_area(args.out))


if __name__ == "__main__":
    main()
