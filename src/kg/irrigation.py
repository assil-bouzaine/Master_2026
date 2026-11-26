"""CQ15 Sentinel-2 probable-irrigation facts of the knowledge graph, added by src.kg.build_kg (v5 only).

Implements CQ15 (docs/competency_questions.md §CQ15; subject objective SO2; v5 plan R2.2):
the probable-irrigation rule itself lives as a SHACL-AF rule in ``ontology/rules/lulcw-rules.ttl``,
while this module instantiates only the source observations, rule parameters and aggregate
evaluations produced by T76 (``src/dataset/irrigation_s2.py``):

  rule and evaluation   one ``lulcw:DerivationRule`` individual reading its frozen thresholds and
                        training editions from ``irrigation_s2_rule.json`` (never hard-coded), its
                        version from the SHA-256 of the rule inputs, its ``lulcw:ruleValidity`` from
                        ``validation_2020.verdict``, and one ``lulcw:RuleEvaluation`` per 2020
                        Agreste census benchmark group (orchards, vines, market gardening).
  all 65 wells (small)  the 650 rows of ``irrigation_s2_wells.parquet`` (65 crop demand zones x
                        9 editions 2017-2025 + the 2017-2019 training summary) as SOSA observations
                        of ``lulcw:ProbablyIrrigatedShare`` with ``lulcw:classifiedAreaM2`` and
                        ``lulcw:classifiedFraction``. Rows with zero classified area omit
                        ``sosa:hasSimpleResult`` (unknown/not applicable, never zero).
  LU-6 parcel scope     bounded to the two LU-6 example wells' 3 km zones only: MILLAS C2-1
                        (``10906X0039/C2-1``) and PONTEILLA NYLS-1 (``10964X0119/NYLS-1``), across
                        all nine editions 2017-2025. Reuses T76's buffer (``well_buffers``) and
                        Lambert-93 intersection clipping (``gpd.overlay``) to emit each parcel's
                        ``lulcw:RegisteredParcel``, its ``lulcw:ParcelZoneOverlap``, its summer
                        Sentinel-2 ``lulcw:SatelliteIndexObservation`` (``lulcw:SummerNDVI`` with
                        ``lulcw:validPixelCount`` and ``lulcw:meanClearAcquisitions``), and each
                        needed SAFRAN weather cell's ``lulcw:SummerSoilWetness`` observation per
                        season. Parcel-season ``lulcw:IrrigationClassification`` nodes are never
                        written here: the SHACL-AF rule derives them inside the graph.

All floating-point values are written as exact ``xsd:double`` literals (``ExactTurtle``).
"""
import hashlib
import json

import geopandas as gpd
import pandas as pd
from rdflib import Literal, URIRef
from rdflib.namespace import RDFS, XSD

from src.config import CRS_L93, DATASET, DATASET_DIR, INTERIM, ROOT
from src.dataset.crop_demand import well_buffers
from src.dataset.irrigation_s2 import summer_swi

LU6_WELLS = ("10906X0039/C2-1", "10964X0119/NYLS-1")
RULE_IRI_PATH = ("rule", "probable-irrigation")
RULE_SHACL_SEE_ALSO = URIRef("https://w3id.org/lulcw/rules#probableIrrigation")


def rule_version_from_inputs(inputs_sha256: dict) -> str:
    """Deterministic rule version derived from the SHA-256 map of irrigation_s2_rule.json."""
    payload = json.dumps(inputs_sha256, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "s2-otsu-" + hashlib.sha256(payload).hexdigest()[:12]


def lu6_overlaps_by_year(wells: pd.DataFrame, parcels_df: pd.DataFrame, years: list[int]) -> pd.DataFrame:
    """Clipped parcel areas (m²) inside the two LU-6 wells' 3 km zones, reusing T76's buffer and overlay."""
    lu6 = wells[wells["code_bss"].isin(LU6_WELLS)].copy()
    if len(lu6) != len(LU6_WELLS):
        missing = sorted(set(LU6_WELLS) - set(lu6["code_bss"]))
        raise ValueError(f"LU-6 wells missing from wells.parquet: {missing}")
    buffers = well_buffers(lu6)[["code_bss", "geometry"]].to_crs(CRS_L93)

    parts = []
    for y in years:
        pids_y = set(parcels_df.loc[parcels_df["year"] == y, "ID_PARCEL"].astype(str))
        rpg = gpd.read_parquet(INTERIM / f"rpg_dept_{y}.parquet", columns=["ID_PARCEL", "geometry"]).to_crs(CRS_L93)
        rpg["ID_PARCEL"] = rpg["ID_PARCEL"].astype(str)
        rpg = rpg[rpg["ID_PARCEL"].isin(pids_y)].copy()
        rpg["geometry"] = rpg.geometry.make_valid()
        ov = gpd.overlay(rpg, buffers, how="intersection", keep_geom_type=True)
        ov["overlap_area_m2"] = ov.area
        agg = (
            ov[ov["overlap_area_m2"] > 0.0]
            .groupby(["code_bss", "ID_PARCEL"], as_index=False)["overlap_area_m2"]
            .sum()
        )
        agg.insert(0, "year", int(y))
        parts.append(agg)
    return pd.concat(parts, ignore_index=True)


def add(kg, rel, wells, versions):
    """Add CQ15 remote-sensing facts to the graph of src.kg.build_kg (v5 only); returns summary counts."""
    from src.kg.build_kg import L, PROV, SOSA, TIME, dbl, file_date, iri, producing_commit

    rule_path = DATASET_DIR / "irrigation_s2_rule.json"
    wells_s2_path = DATASET_DIR / "irrigation_s2_wells.parquet"
    parcels_path = INTERIM / f"irrigation_s2_parcels_{DATASET}.parquet"
    forcing_path = DATASET_DIR / "forcing_weekly.parquet"

    rule_meta = json.loads(rule_path.read_text(encoding="utf-8"))
    wells_s2 = pd.read_parquet(wells_s2_path)
    parcels = pd.read_parquet(parcels_path)
    parcels["ID_PARCEL"] = parcels["ID_PARCEL"].astype(str)

    before = len(kg.g)
    editions = [int(y) for y in rule_meta["editions"]]
    train_editions = [int(y) for y in rule_meta["train_editions"]]
    s2_snap_rel = rule_meta["s2_snapshot"]
    s2_release_json = ROOT / s2_snap_rel / "release.json"
    s2_snap_date = s2_snap_rel.rsplit("/", 1)[-1]

    # Data releases and execution
    r_s2 = kg.node(
        iri("release", f"gee-s2-{s2_snap_date}"),
        L.DataRelease,
        f"Sentinel-2 L2A (COPERNICUS/S2_SR_HARMONIZED) seasonal parcel summaries ({s2_snap_date})",
        "en",
    )
    kg.add(r_s2, L.retrievalDate, Literal(s2_snap_date, datatype=XSD.date))
    kg.add(r_s2, RDFS.comment, Literal(
        f"Google Earth Engine pull (src/ingest/gee_s2.py): COPERNICUS/S2_SR_HARMONIZED, "
        f"summer = July-August, SCL cloud mask keeping classes 4/5/6, 10 m reduceRegions; "
        f"manifest in {s2_release_json.relative_to(ROOT)}.",
        lang="en",
    ))
    rel["gee-s2"] = r_s2

    r_rule = kg.node(
        iri("release", f"irrigation-s2-rule-{DATASET}"),
        L.DataRelease,
        f"CQ15 probable-irrigation frozen rule and 2020 census evaluation (dataset {DATASET})",
        "en",
    )
    kg.add(r_rule, L.releaseDate, Literal(file_date(rule_path), datatype=XSD.date))
    kg.add(r_rule, RDFS.comment, Literal(f"Stored in {rule_path.relative_to(ROOT)}", lang="en"))
    rel["irrigation-s2-rule"] = r_rule

    r_wells = kg.node(
        iri("release", f"irrigation-s2-wells-{DATASET}"),
        L.DataRelease,
        f"CQ15 per-well clipped probably-irrigated shares (dataset {DATASET})",
        "en",
    )
    kg.add(r_wells, L.releaseDate, Literal(file_date(wells_s2_path), datatype=XSD.date))
    kg.add(r_wells, RDFS.comment, Literal(f"Stored in {wells_s2_path.relative_to(ROOT)}", lang="en"))
    rel["irrigation-s2-wells"] = r_wells

    s2_code_ver = producing_commit(rule_path, "src/dataset/irrigation_s2.py")
    exe = kg.node(
        iri("execution", f"irrigation-s2-{DATASET}"),
        L.RuleExecution,
        f"CQ15 probable-irrigation threshold calibration, validation and per-well clipping ({DATASET})",
        "en",
    )
    kg.add(exe, L.codeVersion, Literal(s2_code_ver))
    kg.add(exe, PROV.used, r_s2)
    kg.add(exe, PROV.used, rel[f"dataset-{DATASET}"])
    kg.add(exe, PROV.used, rel["sim2-grid"])
    for y in editions:
        if f"rpg-{y}" in rel:
            kg.add(exe, PROV.used, rel[f"rpg-{y}"])
    kg.add(r_rule, PROV.wasGeneratedBy, exe)
    kg.add(r_wells, PROV.wasGeneratedBy, exe)

    # Procedures
    proc_ndvi = kg.node(
        iri("procedure", "s2-summer-ndvi"),
        SOSA.Procedure,
        "Sentinel-2 summer NDVI parcel summary (July-August)",
        "en",
    )
    kg.add(proc_ndvi, RDFS.comment, Literal(
        "Per-pixel seasonal median of NDVI = (B8 - B4) / (B8 + B4) over clear-sky Sentinel-2 L2A "
        "(COPERNICUS/S2_SR_HARMONIZED, SCL 4/5/6) acquisitions in July-August, averaged over valid "
        "10 m pixels inside each parcel (src/ingest/gee_s2.py).",
        lang="en",
    ))
    proc_swi = kg.node(
        iri("procedure", "sim2-summer-swi"),
        SOSA.Procedure,
        "SIM2 summer soil wetness index (July-August mean)",
        "en",
    )
    kg.add(proc_swi, RDFS.comment, Literal(
        "Mean of weekly SIM2/SAFRAN-ISBA soil wetness index (SWI) over July and August weeks "
        "for one 8 km weather cell (src/dataset/irrigation_s2.py summer_swi).",
        lang="en",
    ))
    proc_share = kg.node(
        iri("procedure", "well-clipped-irrigation-share"),
        SOSA.Procedure,
        "Clipped probably-irrigated share inside a 3 km crop demand zone",
        "en",
    )
    kg.add(proc_share, RDFS.comment, Literal(
        "Clipped area of rule-positive parcels divided by clipped area of classified (positive + "
        "negative) parcels inside each well's 3 km buffer (Lambert-93, src/dataset/irrigation_s2.py). "
        "Training-window rows ('train') are the arithmetic mean of the 2017-2019 annual values.",
        lang="en",
    ))

    # Probable-irrigation DerivationRule individual (parameters read from irrigation_s2_rule.json)
    validity_map = {"aggregate-consistent": L.ValidatedRule, "heuristic": L.HeuristicRule}
    verdict = rule_meta["validation_2020"]["verdict"]
    if verdict not in validity_map:
        raise ValueError(f"Unknown validation_2020 verdict: {verdict!r}")
    rule_ver = rule_version_from_inputs(rule_meta["inputs_sha256"])
    rule_node = kg.node(
        iri(*RULE_IRI_PATH),
        L.DerivationRule,
        "probable irrigation from Sentinel-2 summer NDVI and SIM2 soil wetness",
        "en",
    )
    kg.add(rule_node, RDFS.seeAlso, RULE_SHACL_SEE_ALSO)
    kg.add(rule_node, L.ruleVersion, Literal(rule_ver))
    kg.add(rule_node, L.ndviThreshold, dbl(rule_meta["TAU"]))
    kg.add(rule_node, L.minValidPixels, Literal(int(rule_meta["MIN_PX"]), datatype=XSD.integer))
    kg.add(rule_node, L.minMeanClearAcquisitions, dbl(rule_meta["MIN_OBS"]))
    kg.add(rule_node, L.maxSoilWetness, dbl(rule_meta["SWI_DRY"]))
    for y in train_editions:
        kg.add(rule_node, L.trainingEdition, Literal(int(y), datatype=XSD.integer))
    kg.add(rule_node, L.ruleValidity, validity_map[verdict])
    kg.add(rule_node, PROV.wasDerivedFrom, r_rule)
    kg.add(rule_node, RDFS.comment, Literal(
        f"CQ15 probable-irrigation rule (Otsu NDVI threshold frozen on training editions "
        f"{train_editions[0]}-{train_editions[-1]}): insufficient satellite data when valid pixels < "
        f"{rule_meta['MIN_PX']}, mean clear acquisitions < {rule_meta['MIN_OBS']}, or NDVI/SWI missing; "
        f"wet season (not applicable) when cell SWI_JA > {rule_meta['SWI_DRY']}; probably irrigated when "
        f"summer NDVI >= {rule_meta['TAU']}, else not probably irrigated. Aggregate 2020 Agreste census "
        f"verdict: {verdict}. A vegetation-activity hypothesis under dry regional conditions, never an "
        f"irrigation record or a parcel-to-source link.",
        lang="en",
    ))

    # 2020 Agreste census evaluations (one RuleEvaluation per benchmark RPG group)
    n_evals = 0
    for grp_key, g in sorted(rule_meta["validation_2020"]["groups"].items(), key=lambda kv: int(kv[0])):
        ev_node = kg.node(
            iri("evaluation", "probable-irrigation", f"rpg-group-{grp_key}"),
            L.RuleEvaluation,
            g["name"],
            "en",
        )
        kg.add(ev_node, L.evaluatedRule, rule_node)
        kg.add(ev_node, L.rpgGroupCode, Literal(int(g["group"]), datatype=XSD.integer))
        kg.add(ev_node, L.seasonYear, Literal(2020, datatype=XSD.integer))
        kg.add(ev_node, L.evaluatedShare, dbl(g["share_positive"]))
        kg.add(ev_node, L.referenceRangeLow, dbl(g["census_low"]))
        if g["census_high"] is not None:
            kg.add(ev_node, L.referenceRangeHigh, dbl(g["census_high"]))
        kg.add(ev_node, L.withinReferenceRange, Literal(bool(g["in_range"]), datatype=XSD.boolean))
        kg.add(ev_node, PROV.wasDerivedFrom, r_rule)
        for ak in ("agreste-ra2020-66-irrigation", "agreste-ra2020-66-etudes"):
            if ak in rel:
                kg.add(ev_node, PROV.wasDerivedFrom, rel[ak])
        kg.add(ev_node, PROV.wasGeneratedBy, exe)
        rng_txt = (
            f"[{g['census_low']:.4f} ({g['low_expr']}), {g['census_high']:.4f} ({g['high_expr']})]"
            if g["census_high"] is not None
            else f">= {g['census_low']:.4f} ({g['low_expr']}; no upper bound below 1)"
        )
        kg.add(ev_node, RDFS.comment, Literal(
            f"Dept 66 RA2020 aggregate census check for {g['name']}: rule positive share "
            f"{g['share_positive']:.4f} ({g['area_positive_ha']} / {g['area_classified_ha']} ha classified) "
            f"vs census plausible range {rng_txt}; in_range={g['in_range']}. Farm-type typology covers "
            f"73 % of dept 66 irrigated SAU (aggregate plausibility check, not parcel-level precision/recall).",
            lang="en",
        ))
        n_evals += 1

    # Summer time intervals (July-August, start inclusive, end exclusive) + training-window summary interval
    summer_iv = {}
    for y in editions:
        iv = kg.node(iri("interval", "summer", y), TIME.ProperInterval)
        for p, day in ((TIME.hasBeginning, f"{y}-07-01"), (TIME.hasEnd, f"{y}-09-01")):
            inst = kg.node(iri("instant", day), TIME.Instant)
            kg.add(inst, TIME.inXSDDate, Literal(day, datatype=XSD.date))
            kg.add(iv, p, inst)
        kg.add(iv, RDFS.comment, Literal(f"summer season (July-August) {y}, start inclusive, end exclusive", lang="en"))
        summer_iv[y] = iv

    iv_train = kg.node(iri("interval", f"summer-train-{train_editions[0]}-{train_editions[-1]}"), TIME.ProperInterval)
    for p, day in ((TIME.hasBeginning, f"{train_editions[0]}-07-01"), (TIME.hasEnd, f"{train_editions[-1]}-09-01")):
        inst = kg.node(iri("instant", day), TIME.Instant)
        kg.add(inst, TIME.inXSDDate, Literal(day, datatype=XSD.date))
        kg.add(iv_train, p, inst)
    kg.add(iv_train, RDFS.comment, Literal(
        f"training summers {train_editions[0]}-{train_editions[-1]} (mean of annual July-August zone shares)",
        lang="en",
    ))

    # Well code -> zone key (matches build_kg.py / landuse.py)
    key_of = {
        w["code_bss"]: (w["bss_id"] if isinstance(w["bss_id"], str) and w["bss_id"] else w["code_bss"])
        for _, w in wells.iterrows()
    }

    # All 650 zone-season share observations (65 wells x 9 editions + 'train')
    n_shares = 0
    n_shares_unbound = 0
    for r in wells_s2.itertuples(index=False):
        key = key_of[r.code_bss]
        yr_str = str(r.year)
        obs = kg.node(iri("irrigation-share", key, yr_str), SOSA.Observation)
        kg.add(obs, SOSA.hasFeatureOfInterest, iri("zone", key))
        kg.add(obs, SOSA.observedProperty, L.ProbablyIrrigatedShare)
        kg.add(obs, SOSA.usedProcedure, proc_share)
        if yr_str == "train":
            kg.add(obs, SOSA.phenomenonTime, iv_train)
            kg.add(obs, L.assessmentWindow, Literal("train"))
        else:
            y = int(yr_str)
            kg.add(obs, SOSA.phenomenonTime, summer_iv[y])
            kg.add(obs, L.seasonYear, Literal(y, datatype=XSD.integer))
        kg.add(obs, L.classifiedAreaM2, dbl(float(r.area_classified_ha) * 1e4))
        if pd.notna(r.coverage):
            kg.add(obs, L.classifiedFraction, dbl(float(r.coverage)))
        if pd.notna(r.share_positive):
            kg.add(obs, SOSA.hasSimpleResult, dbl(float(r.share_positive)))
        else:
            n_shares_unbound += 1
            kg.add(obs, RDFS.comment, Literal(
                "No classified parcel area in this zone and season (all clipped area had insufficient "
                "satellite data or wet regional soil conditions): share left unbound, never zero.",
                lang="en",
            ))
        kg.add(obs, L.derivationRule, rule_node)
        kg.add(obs, L.inRelease, r_wells)
        kg.add(obs, PROV.wasGeneratedBy, exe)
        n_shares += 1

    # Parcel-level facts for the two LU-6 zones only (all nine editions 2017-2025)
    overlaps = lu6_overlaps_by_year(wells, parcels, editions)
    lu6_keys = set(zip(overlaps["year"].astype(int), overlaps["ID_PARCEL"].astype(str)))
    p_idx = parcels.set_index(["year", "ID_PARCEL"])
    lu6_parcels = p_idx.loc[p_idx.index.isin(lu6_keys)].reset_index()

    # Cross-check SWI_JA against T76's summer_swi(forcing)
    forcing = pd.read_parquet(forcing_path, columns=["cell_id", "week", "SWI"])
    swi_table = summer_swi(forcing).set_index(["cell_id", "year"])["SWI_JA"]

    needed_cells = set()
    n_parcels = 0
    n_ndvi = 0
    for r in lu6_parcels.itertuples(index=False):
        y = int(r.year)
        pid = str(r.ID_PARCEL)
        cid = str(r.cell_id)
        needed_cells.add((cid, y))

        p_node = kg.node(iri("parcel", y, pid), L.RegisteredParcel)
        kg.add(p_node, L.sourceIdentifier, Literal(pid))
        kg.add(p_node, L.rpgEdition, Literal(y, datatype=XSD.integer))
        kg.add(p_node, L.cropCode, iri("crop-code", r.CODE_CULTU))
        kg.add(p_node, L.parcelAreaM2, dbl(float(r.area_m2)))
        kg.add(p_node, L.matchedWeatherCell, iri("weather-cell", cid))
        kg.add(p_node, L.inRelease, rel[f"rpg-{y}"])
        n_parcels += 1

        ndvi_obs = kg.node(iri("ndvi", y, pid), L.SatelliteIndexObservation)
        kg.add(ndvi_obs, SOSA.hasFeatureOfInterest, p_node)
        kg.add(ndvi_obs, SOSA.observedProperty, L.SummerNDVI)
        kg.add(ndvi_obs, SOSA.phenomenonTime, summer_iv[y])
        kg.add(ndvi_obs, SOSA.usedProcedure, proc_ndvi)
        kg.add(ndvi_obs, L.seasonYear, Literal(y, datatype=XSD.integer))
        kg.add(ndvi_obs, L.validPixelCount, Literal(int(r.n_px_summer), datatype=XSD.integer))
        if pd.notna(r.nobs_summer):
            kg.add(ndvi_obs, L.meanClearAcquisitions, dbl(float(r.nobs_summer)))
        if pd.notna(r.ndvi_summer):
            kg.add(ndvi_obs, SOSA.hasSimpleResult, dbl(float(r.ndvi_summer)))
        kg.add(ndvi_obs, L.inRelease, r_s2)
        n_ndvi += 1

    n_overlaps = 0
    for r in overlaps.itertuples(index=False):
        y = int(r.year)
        pid = str(r.ID_PARCEL)
        key = key_of[r.code_bss]
        ov_node = kg.node(iri("parcel-zone-overlap", key, y, pid), L.ParcelZoneOverlap)
        kg.add(ov_node, L.overlapParcel, iri("parcel", y, pid))
        kg.add(ov_node, L.overlapZone, iri("zone", key))
        kg.add(ov_node, L.overlapAreaM2, dbl(float(r.overlap_area_m2)))
        kg.add(ov_node, PROV.wasGeneratedBy, exe)
        n_overlaps += 1

    n_swi = 0
    for cid, y in sorted(needed_cells):
        swi_val = swi_table.get((cid, y))
        swi_obs = kg.node(iri("summer-swi", cid, y), SOSA.Observation)
        kg.add(swi_obs, SOSA.hasFeatureOfInterest, iri("weather-cell", cid))
        kg.add(swi_obs, SOSA.observedProperty, L.SummerSoilWetness)
        kg.add(swi_obs, SOSA.phenomenonTime, summer_iv[y])
        kg.add(swi_obs, SOSA.usedProcedure, proc_swi)
        kg.add(swi_obs, L.seasonYear, Literal(int(y), datatype=XSD.integer))
        if swi_val is not None and pd.notna(swi_val):
            kg.add(swi_obs, SOSA.hasSimpleResult, dbl(float(swi_val)))
        kg.add(swi_obs, L.inRelease, rel[f"dataset-{DATASET}"])
        n_swi += 1

    triples_added = len(kg.g) - before
    per_zone = overlaps.groupby("code_bss").size().to_dict()
    print(
        f"irrigation_s2 (CQ15): added {triples_added} triples "
        f"({n_shares} zone shares, {n_parcels} LU-6 parcels, {n_overlaps} overlaps, "
        f"{n_ndvi} NDVI obs, {n_swi} SWI obs, {n_evals} census evaluations; rule {rule_ver}, {verdict})"
    )
    return {
        "rule_version": rule_ver,
        "verdict": verdict,
        "census_evaluations": n_evals,
        "zone_share_observations": n_shares,
        "zone_shares_unbound": n_shares_unbound,
        "lu6_wells": list(LU6_WELLS),
        "lu6_parcels": n_parcels,
        "lu6_overlaps": n_overlaps,
        "lu6_overlaps_by_well": {k: int(v) for k, v in per_zone.items()},
        "ndvi_observations": n_ndvi,
        "swi_observations": n_swi,
        "triples_added": triples_added,
    }
