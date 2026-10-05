"""Summarise BNPE abstraction volumes by usage x water source, plain vs département.

    python -m src.analysis.bnpe_profile

Water source comes from the point's code_type_milieu (CONT = surface,
SOUT = groundwater). code_bdlisa is NOT used: it is null for every point.
"Inside the plain" uses the ouvrage coordinates from the chroniques table
(the points table has none) and the same bbox as the piezometers.

Outputs: data/interim/bnpe_annual.csv        year x usage x source, plain and dept (m3)
         data/interim/bnpe_cumulative.csv    cumulative over all years (Mm3)
         reports/figures/bnpe_plain_annual.png
"""
import matplotlib.pyplot as plt
import pandas as pd

from src.analysis.piezo_profile import PLAIN_BBOX
from src.config import DEPARTEMENT, FIGURES, INTERIM, RAW

BNPE = RAW / "hubeau_bnpe"
SOURCE = {"CONT": "surface", "SOUT": "groundwater"}
USAGE = {"IRR": "irrigation", "AEP": "drinking water", "CAN": "canals",
         "IND": "industry", "BAR": "hydropower (turbined)", "ENE": "energy"}


def load():
    pts = pd.read_parquet(BNPE / f"points_prelevement_{DEPARTEMENT}.parquet")
    vol = pd.read_parquet(BNPE / f"chroniques_{DEPARTEMENT}.parquet")
    assert pts.groupby("code_ouvrage")["code_type_milieu"].nunique().max() == 1, \
        "an ouvrage has points in both surface and groundwater: source is ambiguous"
    d = vol.merge(pts[["code_ouvrage", "code_type_milieu"]].drop_duplicates(),
                  on="code_ouvrage", how="left")
    n_missing = d["code_type_milieu"].isna().sum()
    if n_missing:
        print(f"note: {n_missing} volume rows have no matching point (source unknown), dropped")
        d = d.dropna(subset=["code_type_milieu"])
    lon0, lat0, lon1, lat1 = PLAIN_BBOX
    d["plain"] = d["longitude"].between(lon0, lon1) & d["latitude"].between(lat0, lat1)
    d["source"] = d["code_type_milieu"].map(SOURCE)
    d["usage"] = d["code_usage"].map(USAGE).fillna(d["code_usage"])
    return d


def main():
    d = load()
    years = f"{d.annee.min()}-{d.annee.max()}"

    annual = (pd.concat([d[d.plain].assign(zone="plain"), d.assign(zone="departement")])
                .groupby(["zone", "annee", "usage", "source"])
                .agg(volume_m3=("volume", "sum"), n_ouvrages=("code_ouvrage", "nunique"))
                .reset_index())
    annual.to_csv(INTERIM / "bnpe_annual.csv", index=False)

    cum = (annual.groupby(["zone", "usage", "source"])["volume_m3"].sum().div(1e6).round(0)
                 .unstack("source").fillna(0))
    cum.to_csv(INTERIM / "bnpe_cumulative.csv")

    print(f"cumulative abstraction {years} (Mm3), by usage x water source")
    for zone in ("plain", "departement"):
        t = cum.loc[zone].copy()
        t["groundwater_share_%"] = (100 * t["groundwater"] / (t["groundwater"] + t["surface"])).round(0)
        print(f"\n[{zone}]\n{t.to_string()}")

    p = cum.loc["plain"]
    irr_s, irr_g = p.loc["irrigation", "surface"], p.loc["irrigation", "groundwater"]
    can_s = p.loc["canals", "surface"]
    print(f"\nplain irrigation: {100 * irr_s / (irr_s + irr_g):.0f}% surface water "
          f"({100 * (irr_s + can_s) / (irr_s + can_s + irr_g):.0f}% if canal intakes count as irrigation)")
    dw = p.loc["drinking water"]
    print(f"plain drinking water: {100 * dw.groundwater / dw.sum():.0f}% groundwater")
    print("note: hydropower water is turbined and returned to the river at once (not consumptive)")

    # --- Figure: plain, annual volumes and number of reporting ouvrages ---
    a = annual[(annual.zone == "plain") & annual.usage.isin(["irrigation", "drinking water", "canals"])]
    series = {
        ("canals", "surface"): ("#9db4c0", "-"),
        ("irrigation", "surface"): ("#2f6690", "-"),
        ("irrigation", "groundwater"): ("#d1495b", "-"),
        ("drinking water", "groundwater"): ("#edae49", "-"),
    }
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(9, 7), sharex=True,
                                  gridspec_kw={"height_ratios": [2, 1]})
    for (u, s), (col, ls) in series.items():
        v = a[(a.usage == u) & (a.source == s)].set_index("annee")
        ax.plot(v.index, v.volume_m3 / 1e6, ls, color=col, marker="o", ms=4, label=f"{u}, {s}")
        if (u, s) == ("irrigation", "groundwater"):
            ax2.bar(v.index, v.n_ouvrages, color=col, alpha=0.8)
    ax.set_ylabel("volume (Mm³ / year)")
    ax.set_title("BNPE declared abstraction, Roussillon plain")
    ax.legend(fontsize=8, loc="center left")
    ax.grid(alpha=0.3)
    last = int(d.annee.max())
    ax.axvspan(last - 0.5, last + 0.5, color="grey", alpha=0.15)
    ax.text(last, ax.get_ylim()[1] * 0.95, "under-\nreported?", ha="center", va="top", fontsize=7)
    ax2.set_ylabel("boreholes declaring\ngroundwater irrigation", fontsize=8)
    ax2.set_xlabel("year")
    ax2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIGURES / "bnpe_plain_annual.png", dpi=150)
    print(f"\nfigure -> {FIGURES / 'bnpe_plain_annual.png'}")


if __name__ == "__main__":
    main()
