"""Land-use facts of the knowledge graph (task 12.6, land-use part; CQ7), added by src.kg.build_kg.

From the land-use thread of step 12d (docs/notes/step12d_land_use.md, src/dataset/crop_demand.py):
  crop codes    every RPG crop code found in the well zones, with its official label and crop
                group, as SKOS concepts of the RPG crop-code scheme
  crop classes  the harmonised classes of configs/lu_crop_classes.csv with their FAO-56 single
                crop coefficients and stages and their irrigation assumption (backed by the 2020
                agricultural census); which class a code belongs to is derived by a SHACL-AF rule
                (ontology/rules/lulcw-rules.ttl), from the group numbers and code overrides
                stated here
  zones         one crop demand zone per piezometer (radius BUFFER_M)
  crop areas    the clipped area of every crop code in every zone and RPG edition 2015-2025, one
                SOSA observation each, for its own year
  demand        the potential irrigation demand of each zone and calendar year 2015-2025, main
                and wide class sets, summed from the weekly index; the week that straddles
                1 January is split by days, so a year never counts 53 weeks. Years before 2015
                use the 2015 edition (backfill) and 2026 is incomplete: neither is stated as an
                observation of its year.
The high-demand threshold is a parameter of its rule, computed by src.kg.apply_rules from these
estimates (training years only).
"""
import pandas as pd
from rdflib import Literal
from rdflib.namespace import RDF, RDFS, SKOS, XSD

from src.config import DATASET, INTERIM, RAW, ROOT
from src.dataset.crop_demand import AREA_OUT, BUFFER_M, CLASSES, load_classes

EDITIONS = range(2015, 2026)
DEMAND = INTERIM / f"crop_demand_weekly_{DATASET}.parquet"
# the 2023 table is Windows-1252: read as latin-1, its ’ and … (0x92, 0x85) become C1 controls
NOMENCLATURE = {2023: ("REF_CULTURES_GROUPES_CULTURES_2023.csv", "cp1252"),
                2024: ("REF_CULTURES_GROUPES_CULTURES_2024.csv", "utf-8")}
ARCHIVES = {   # RPG editions of region R76 (IGN Géoplateforme), as logged in data/README.md
    2015: "RPG_2-0__SHP_LAMB93_R76-2015_2015-01-01", 2016: "RPG_2-0__SHP_LAMB93_R76-2016_2016-01-01",
    2017: "RPG_2-0__SHP_LAMB93_R76-2017_2017-01-01", 2018: "RPG_2-0__SHP_LAMB93_R76-2018_2018-01-15",
    2019: "RPG_2-0_SHP_LAMB93_R76-2019", 2020: "RPG_2-0__SHP_LAMB93_R76_2020-01-01",
    2021: "RPG_2-0__SHP_LAMB93_R76_2021-01-01", 2022: "RPG_2-0__SHP_LAMB93_R76_2022-01-01",
    2023: "RPG_2-2__SHP_LAMB93_R76_2023-01-01", 2024: "RPG_4-0__GPKG_LAMB93_R76_2024-01-01",
    2025: "RPG_4-0__GPKG_LAMB93_R76_2025-01-01"}
AGRESTE = {
    "agreste-ra2020-66-etudes": ("DRAAF Occitanie, Agreste Études no 9: 2020 agricultural census, "
                                 "Pyrénées-Orientales (July 2022)",
                                 "https://draaf.occitanie.agriculture.gouv.fr/IMG/pdf/agreste_etudes_ra20_po_19072022.pdf"),
    "agreste-ra2020-66-irrigation": ("DRAAF Occitanie, Agreste Essentiel: irrigating farms in the "
                                     "2020 census, Pyrénées-Orientales (January 2024)",
                                     "https://draaf.occitanie.agriculture.gouv.fr/IMG/pdf/essentiel_typoirri_0124_dep66-pyrenees-orientales_v24c.pdf"),
}
FAO56 = ("FAO Irrigation and Drainage Paper 56 (Allen, Pereira, Raes and Smith, 1998), crop "
         "evapotranspiration: Table 11 (growth stages) and Table 12 (single crop coefficients)",
         "https://www.fao.org/4/X0490E/x0490e0b.htm")
ASSUMPTION = {"usually": "UsuallyIrrigated", "partly": "PartlyIrrigated", "rainfed": "Rainfed",
              "none": "NotCropped"}
UNMAPPED = "unmapped"


def nomenclature():
    """Crop code -> (official label, year of the table it comes from): the 2023 table, else 2024."""
    out = {}
    for year in sorted(NOMENCLATURE, reverse=True):
        f, enc = NOMENCLATURE[year]
        t = pd.read_csv(RAW / "rpg" / "docs" / f, sep=None, engine="python", encoding=enc)
        out.update({c: (lab, year) for c, lab in zip(t["CODE_CULTURE"], t["LIBELLE_CULTURE"])})
    return out


def calendar_year_totals(d, columns):
    """Weekly sums (weeks Monday-Sunday labelled by the Sunday) -> calendar-year sums; a week
    across 1 January is split by its days in each year (the Sunday's day of year, at most 7)."""
    end = d["week"]
    share = end.dt.dayofyear.clip(upper=7) / 7.0
    a = d[columns].mul(share, axis=0).assign(code_bss=d["code_bss"], year=end.dt.year)
    b = d[columns].mul(1 - share, axis=0).assign(code_bss=d["code_bss"], year=end.dt.year - 1)
    return pd.concat([a, b]).groupby(["code_bss", "year"])[columns].sum().reset_index()


def add(kg, rel, wells, versions):
    """Add the land-use facts to the graph of src.kg.build_kg; returns counts for its summary."""
    from src.kg.build_kg import L, PROV, SOSA, TIME, dbl, file_date, iri, record

    # releases and provenance
    for y in EDITIONS:
        r = kg.node(iri("release", f"rpg-{y}-r76"), L.DataRelease,
                    f"RPG (land-parcel register) {y}, region R76, IGN Géoplateforme", "en")
        kg.add(r, L.retrievalDate, Literal("2026-10-25", datatype=XSD.date))
        kg.add(r, RDFS.comment, Literal(
            f"Archive {ARCHIVES[y]} (https://data.geopf.fr/telechargement/download/RPG/), clipped to "
            "the département extent; raw archive deleted after the clip (data/README.md)", lang="en"))
        rel[f"rpg-{y}"] = r
    for y, (f, _) in NOMENCLATURE.items():
        r = kg.node(iri("release", f"rpg-nomenclature-{y}"), L.DataRelease,
                    f"RPG crop codes and crop groups, {y} table", "en")
        kg.add(r, L.retrievalDate, Literal(file_date(RAW / "rpg" / "docs" / f), datatype=XSD.date))
        kg.add(r, RDFS.comment, Literal(f"Stored in data/raw/rpg/docs/{f}", lang="en"))
        rel[f"rpg-nomenclature-{y}"] = r
    for key, (label, url) in AGRESTE.items():
        r = kg.node(iri("release", key), L.DataRelease, label, "en")
        kg.add(r, L.retrievalDate, Literal("2026-10-25", datatype=XSD.date))
        kg.add(r, RDFS.comment, Literal(f"Source: {url}", lang="en"))
        rel[key] = r
    r = kg.node(iri("release", "fao-56"), L.DataRelease, FAO56[0], "en")
    kg.add(r, RDFS.comment, Literal(f"Source: {FAO56[1]} (checked 2026-10-25)", lang="en"))
    rel["fao-56"] = r
    for key, label, path in (
            ("crop-classes", "harmonised crop classes with FAO-56 parameters and irrigation "
             "assumptions (configs/lu_crop_classes.csv)", CLASSES),
            ("crop-area-3km", "clipped crop areas per well zone and RPG edition (task LU-3)", AREA_OUT),
            (f"crop-demand-{DATASET}", "weekly potential irrigation demand per well zone (task LU-3)",
             DEMAND)):
        r = kg.node(iri("release", key), L.DataRelease, label, "en")
        kg.add(r, L.releaseDate, Literal(file_date(path), datatype=XSD.date))
        kg.add(r, RDFS.comment, Literal(f"Stored in {path.relative_to(ROOT)}", lang="en"))
        rel[key] = r
    exe = kg.node(iri("execution", "crop-demand"), L.RuleExecution,
                  "crop areas and potential irrigation demand (src/dataset/crop_demand.py)", "en")
    kg.add(exe, L.codeVersion, Literal(versions["crop"]))
    for k in [f"rpg-{y}" for y in EDITIONS] + ["crop-classes", "fao-56", f"dataset-{DATASET}"]:
        kg.add(exe, PROV.used, rel[k])
    for k in ("crop-area-3km", f"crop-demand-{DATASET}"):
        kg.add(rel[k], PROV.wasGeneratedBy, exe)

    # crop codes
    areas = pd.read_parquet(AREA_OUT)
    labels = nomenclature()
    scheme = kg.node(iri("crop-code-scheme", "rpg"), SKOS.ConceptScheme, "RPG crop codes", "en")
    kg.add(scheme, RDFS.label, Literal("codes cultures du RPG", lang="fr"))
    groups = areas.groupby("CODE_CULTU")["CODE_GROUP"].agg(lambda s: sorted(set(s.dropna().astype(int))))
    assert (groups.str.len() == 1).all(), "a crop code changes group between editions"
    code_node = {}
    for code, g in groups.items():
        c = kg.node(iri("crop-code", code), L.CropCode)
        kg.add(c, SKOS.inScheme, scheme)
        kg.add(c, SKOS.notation, Literal(code))
        label, table = labels[code]
        kg.add(c, SKOS.prefLabel, Literal(label, lang="fr"))
        kg.add(c, L.rpgGroupCode, Literal(g[0], datatype=XSD.integer))
        kg.add(c, PROV.wasDerivedFrom, record(kg, "rpg-crop-code", code, rel[f"rpg-nomenclature-{table}"]))
        code_node[code] = c

    # crop classes
    classes = load_classes()
    cscheme = kg.node(iri("crop-class-scheme", "lulcw"), SKOS.ConceptScheme,
                      "harmonised crop classes of the LULC-Water project", "en")
    kg.add(cscheme, RDFS.label, Literal("classes de cultures harmonisées du projet LULC-Water", lang="fr"))
    for name, r in classes.iterrows():
        c = kg.node(iri("crop-class", name), L.CropClass)
        kg.add(c, SKOS.inScheme, cscheme)
        kg.add(c, SKOS.notation, Literal(name))
        kg.add(c, SKOS.prefLabel, Literal(name.replace("_", " "), lang="en"))
        for g in r["rpg_groups"].split():
            kg.add(c, L.rpgGroupCode, Literal(int(g), datatype=XSD.integer))
        for o in r["code_overrides"].split():
            kg.add(c, L.overrideCode, Literal(o))
        kg.add(c, L.irrigationAssumption, getattr(L, ASSUMPTION[r["irrigation_assumption"]]))
        if r["kc_ini"]:
            for p, col in ((L.kcInitial, "kc_ini"), (L.kcMid, "kc_mid"), (L.kcEnd, "kc_end")):
                kg.add(c, p, dbl(float(r[col])))
            for p, col in ((L.initialStageDays, "l_ini"), (L.developmentStageDays, "l_dev"),
                           (L.midSeasonStageDays, "l_mid"), (L.lateSeasonStageDays, "l_late"),
                           (L.plantingMonth, "plant_month")):
                kg.add(c, p, Literal(int(r[col]), datatype=XSD.integer))
            kg.add(c, L.perennial, Literal(r["perennial"] == "yes", datatype=XSD.boolean))
            kg.add(c, RDFS.comment, Literal(
                f"FAO-56 Table 12 row: {r['fao56_crop_kc_table12']}; Table 11 row: "
                f"{r['fao56_stages_table11']}", lang="en"))
            kg.add(c, PROV.wasDerivedFrom, rel["fao-56"])
        kg.add(c, PROV.wasDerivedFrom, rel["crop-classes"])
        for key in AGRESTE:
            kg.add(c, PROV.wasDerivedFrom, rel[key])
    u = kg.node(iri("crop-class", UNMAPPED), L.CropClass)
    kg.add(u, SKOS.inScheme, cscheme)
    kg.add(u, SKOS.notation, Literal(UNMAPPED))
    kg.add(u, SKOS.prefLabel, Literal("unmapped", lang="en"))
    kg.add(u, RDFS.comment, Literal("The crop codes that the class-mapping rule assigns to no class: "
                                    "their area stays in every total as unmapped area.", lang="en"))

    # zones, year intervals, procedures
    zone = {}
    for _, w in wells.iterrows():
        key = w["bss_id"] if isinstance(w["bss_id"], str) and w["bss_id"] else w["code_bss"]
        z = kg.node(iri("zone", key), L.CropDemandZone)
        kg.add(z, L.zoneOf, iri("piezometer", key))
        kg.add(z, L.zoneRadiusM, dbl(float(BUFFER_M)))
        kg.add(z, RDFS.comment, Literal(f"The area within {BUFFER_M} m of the piezometer (Lambert-93)",
                                        lang="en"))
        zone[w["code_bss"]] = (z, key)
    years = {}
    for y in EDITIONS:
        iv = kg.node(iri("interval", "year", y), TIME.ProperInterval)
        for p, day in ((TIME.hasBeginning, f"{y}-01-01"), (TIME.hasEnd, f"{y + 1}-01-01")):
            inst = kg.node(iri("instant", day), TIME.Instant)
            kg.add(inst, TIME.inXSDDate, Literal(day, datatype=XSD.date))
            kg.add(iv, p, inst)
        kg.add(iv, RDFS.comment, Literal(f"calendar year {y}, start inclusive, end exclusive", lang="en"))
        years[y] = iv
    clip = kg.node(iri("procedure", "clipped-crop-area"), SOSA.Procedure,
                   "parcels clipped at the zone boundary", "en")
    kg.add(clip, RDFS.comment, Literal(
        "Intersection of the RPG parcels of the edition with the circle of the zone (Lambert-93, "
        "geopandas overlay), summed by crop code, in hectares (src/dataset/crop_demand.py).", lang="en"))
    fao = kg.node(iri("procedure", "fao56-potential-demand"), SOSA.Procedure,
                  "FAO-56 potential irrigation demand", "en")
    kg.add(fao, RDFS.comment, Literal(
        "For each week (Monday-Sunday): clipped area (ha) x max(0, Kc x the week's SAFRAN reference "
        "evapotranspiration - its SAFRAN rainfall, mm) x 10, Kc the week's mean of the class's "
        "FAO-56 four-stage curve; summed per calendar year, the week across 1 January split by "
        "days; m³. Main: classes usually irrigated; wide: usually or partly irrigated "
        "(src/dataset/crop_demand.py).", lang="en"))

    # crop area observations (each edition for its own year)
    n_area = 0
    for r in areas.itertuples(index=False):
        y = int(r.rpg_year)
        z, key = zone[r.code_bss]
        o = kg.node(iri("crop-area", key, y, r.CODE_CULTU), L.CropAreaObservation)
        kg.add(o, SOSA.hasFeatureOfInterest, z)
        kg.add(o, SOSA.observedProperty, L.ClippedCropArea)
        kg.add(o, SOSA.hasSimpleResult, dbl(r.ha, 6))
        kg.add(o, SOSA.phenomenonTime, years[y])
        kg.add(o, SOSA.usedProcedure, clip)
        kg.add(o, L.cropCode, code_node[r.CODE_CULTU])
        kg.add(o, L.rpgEdition, Literal(y, datatype=XSD.integer))
        kg.add(o, L.inRelease, rel["crop-area-3km"])
        kg.add(o, PROV.wasDerivedFrom, rel[f"rpg-{y}"])
        n_area += 1

    # demand estimates, calendar years 2015-2025
    d = pd.read_parquet(DEMAND, columns=["code_bss", "week", "demand_main_m3", "demand_wide_m3",
                                         "rpg_year_used"])
    tot = calendar_year_totals(d, ["demand_main_m3", "demand_wide_m3"])
    tot = tot[tot["year"].isin(EDITIONS)]
    n_dem = 0
    for r in tot.itertuples(index=False):
        z, key = zone[r.code_bss]
        for name, prop, v in (("main", L.PotentialIrrigationDemandMain, r.demand_main_m3),
                              ("wide", L.PotentialIrrigationDemandWide, r.demand_wide_m3)):
            o = kg.node(iri("crop-demand", key, int(r.year), name), L.CropDemandEstimate)
            kg.add(o, SOSA.hasFeatureOfInterest, z)
            kg.add(o, SOSA.observedProperty, prop)
            kg.add(o, SOSA.hasSimpleResult, dbl(v, 1))
            kg.add(o, SOSA.phenomenonTime, years[int(r.year)])
            kg.add(o, SOSA.usedProcedure, fao)
            kg.add(o, L.rpgEdition, Literal(int(r.year), datatype=XSD.integer))
            kg.add(o, L.inRelease, rel[f"crop-demand-{DATASET}"])
            n_dem += 1
    return {"crop_codes": len(code_node), "crop_classes": len(classes) + 1, "zones": len(zone),
            "crop_area_observations": n_area, "demand_estimates": n_dem}
