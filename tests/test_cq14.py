"""Check cover, confinement and pressure state at a well (analysis plan §14, item 23).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_cq14

The fixture checks the rules and both CQ14 queries. Negative controls check that SHACL catches
inconsistent values and missing rule outputs. The data checks compare the validated release with
the BD LISA stacks and pressure summaries for the v4 wells.
"""
from collections import Counter
from unittest.mock import patch

import geopandas as gpd
import pandas as pd
import pyogrio
import pyoxigraph as ox
import rdflib
from rdflib import Literal
from rdflib.namespace import RDF, XSD

from src.analysis.bdlisa_profile import GPKG
from src.config import CRS_L93, DATASET, DATASET_DIR, INTERIM
from src.kg import pressure, release
from src.kg.apply_rules import RULES, SHAPES, check, ontology_network, rule_records, run_rules
from src.kg.build_kg import KG as FactGraph, pressure_states
from src.kg.cq import ask, one
from tests.test_cq import to_store
from tests.test_kg_rules import GEO, KG, L, PROV, SOSA, Fixture, d, l93, rows, store_of, violations


def build_fixture():
    fx = Fixture()
    # The recharge rule record refers to this extent even when there are no forcing records.
    fx.g.add((d("extent/forcing-cells"), RDF.type, GEO.Feature))
    surface, buried, elsewhere = (fx.unit(code) for code in "ABC")
    polygon = fx.polygon(1, [surface, buried])
    fx.polygon(2, [elsewhere])
    first_candidates = {"covered": buried, "outcrop": surface, "windows": surface,
                        "no-depth": buried, "no-unit": None, "off-stack": elsewhere,
                        "two-candidates": buried, "no-summary": surface}
    for i, (key, unit) in enumerate(first_candidates.items()):
        well = fx.well(key, 100 + i, 50, unit, L.Confident, depth=50)
        fx.g.add((well, L.locatedInPolygon, polygon))
    fx.attribution("piezometer/two-candidates", d("piezometer/two-candidates"),
                   L.MonitoringRole, surface, conf=L.Probable, rank=2)

    # The pressure writer builds the same observations, intervals and provenance as in the release.
    # Replace only its source counts so the fixture needs no Hub'Eau files.
    counts = [(key, "train", 7, 0) for key in ("covered", "outcrop", "no-unit", "off-stack")]
    counts += [("two-candidates", "train", 7, 2), ("no-depth", "train", 0, 0),
               ("windows", "train", 8, 3), ("windows", "f25", 0, 0), ("windows", "f50", 5, 1)]
    table = pd.DataFrame([{"code_bss": key, "window": win, "days": days, "days_above": above,
                           "share_pct": round(100 * above / days, 1) if days else None}
                          for key, win, days, above in counts])
    wells = pd.DataFrame({"code_bss": list(first_candidates), "bss_id": None})
    kg = FactGraph()
    kg.g = fx.g
    with patch.object(pressure, "summaries", return_value=table):
        pressure_states(kg, {"hubeau-piezo-chronicles": fx.rel}, wells)
    return fx.g


def check_setting(g, key, rank, unit, position):
    well, attribution = d(f"piezometer/{key}"), d(f"attribution/piezometer/{key}/{rank}")
    settings = list(g.subjects(L.settingAttribution, attribution))
    assert len(settings) == 1, (key, rank, settings)
    setting = settings[0]
    assert (setting, RDF.type, L.HydrogeologicalSetting) in g, setting
    cover, covering = {None: (L.CoverUnknown, set()), 1: (L.Outcropping, set()),
                       2: (L.Covered, {d("unit/A")})}[position]
    expected = {L.settingOf: well, L.settingUnit: d(f"unit/{unit}") if unit else None,
                L.settingPolygon: d("polygon/1"), L.coverStatus: cover,
                L.stackPosition: Literal(position) if position is not None else None}
    for prop, value in expected.items():
        assert g.value(setting, prop, any=False) == value, (setting, prop, value)
    assert set(g.objects(setting, L.coveringUnit)) == covering, setting
    return setting, cover, "A" if covering else None


def check_window(g, store, key, window, candidates, days, above, share, status, reason=None):
    well = d(f"piezometer/{key}")
    summary = d(f"pressure-state/{key}/{window}")
    state = L.ConfinedState if above else L.ConfinementUnknown
    confidence = L.Probable if above else None
    params = {"W": well, "window": ox.Literal(window)}
    rows = ask(store, "cq14_setting", **params)
    assert [r["rank"] for r in rows] == list(range(1, len(candidates) + 1)), (key, window, rows)
    for rank, ((unit, position), row) in enumerate(zip(candidates, rows), start=1):
        setting, cover, covering = check_setting(g, key, rank, unit, position)
        assessments = [c for c in g.subjects(L.assessedSetting, setting)
                       if (c, L.assessmentWindow, Literal(window)) in g]
        assert len(assessments) == 1, (key, rank, window, assessments)
        assessment = assessments[0]
        assert (assessment, RDF.type, L.ConfinementAssessment) in g, assessment
        assert g.value(assessment, L.confinementState, any=False) == state, assessment
        assert g.value(assessment, L.confidence, any=False) == confidence, assessment
        assert set(g.objects(assessment, PROV.wasDerivedFrom)) == {setting, summary}, assessment

        cover_reason = str(g.value(setting, L.assessmentReason, any=False))
        confinement_reason = str(g.value(assessment, L.assessmentReason, any=False))
        if reason:
            assert reason in confinement_reason, confinement_reason
        if position == 2:
            assert "Mapped cover is not confinement" in cover_reason, cover_reason
        expected = {"W": str(well), "window": window, "rank": rank, "unitCode": unit,
                    "coverStatus": str(cover), "stackPosition": position, "coveringUnits": covering,
                    "polygonCode": 1, "confinementState": str(state),
                    "confidence": str(confidence) if confidence else None, "daysObserved": days,
                    "daysAbove": above, "sharePct": share, "coverReason": cover_reason,
                    "confinementReason": confinement_reason}
        assert row == expected, (key, window, row, expected)

    answer = one(store, "cq14_status", **params)
    assert (answer["W"], answer["window"], answer["status"]) == (str(well), window, status), answer
    assert answer["reason"], answer


def test_fixtures(rules, shapes, net):
    facts = build_fixture()
    records = rule_records(rules, "test", facts)
    added = run_rules(facts, rules, records)
    g = facts + records + added
    store = to_store(g)

    check_window(g, store, "covered", "train", [("B", 2)], 7, 0, 0.0, "supported",
                 "mapped cover does not establish confinement")
    check_window(g, store, "outcrop", "train", [("A", 1)], 7, 0, 0.0, "supported",
                 "an outcropping multilayer unit may hold confined horizons")
    check_window(g, store, "no-depth", "train", [("B", 2)], 0, 0, None, "partial",
                 "No depth to water in the window")
    check_window(g, store, "no-unit", "train", [(None, None)], 7, 0, 0.0, "partial")
    check_window(g, store, "off-stack", "train", [("C", None)], 7, 0, 0.0, "partial")
    check_window(g, store, "two-candidates", "train", [("B", 2), ("A", 1)], 7, 2, 28.6, "supported",
                 "above the station's measurement reference on 2 of 7 days")
    check_window(g, store, "windows", "train", [("A", 1)], 8, 3, 37.5, "supported")
    check_window(g, store, "windows", "f25", [("A", 1)], 0, 0, None, "partial")
    check_window(g, store, "windows", "f50", [("A", 1)], 5, 1, 20.0, "supported")

    for well, window, status, reason in (
            (d("polygon/1"), "train", "not_applicable", "not a piezometer"),
            (d("piezometer/no-summary"), "train", "unknown", "no pressure summary"),
            (d("piezometer/covered"), "f25", "unknown", "no pressure summary")):
        params = {"W": well, "window": ox.Literal(window)}
        assert not ask(store, "cq14_setting", **params), params
        answer = one(store, "cq14_status", **params)
        assert answer["status"] == status and reason in answer["reason"], answer
    check_setting(g, "no-summary", 1, "A", 1)
    assert len(set(g.subjects(RDF.type, L.HydrogeologicalSetting))) == 9
    assert len(set(g.subjects(RDF.type, L.ConfinementAssessment))) == 10

    conforms, _, results = check(g, shapes, net)
    assert conforms and violations(results) == 0, results
    print(f"  1. fixture: CQ14 rule outputs and both queries pass; {len(added)} derived triples; no violation")
    return g


def test_negative_controls(g, shapes, net):
    positive = d("pressure-state/windows/train")
    empty = d("pressure-state/no-depth/train")
    covered = d("setting/covered/1")
    off_stack = d("setting/off-stack/1")
    confined = d("confinement/windows/1/train")
    unknown = d("confinement/covered/1/train")
    counts_message = "a pressure summary's counts and share disagree"
    cases = {
        "share disagrees with counts": (
            [(positive, SOSA.hasSimpleResult, Literal(50.0, datatype=XSD.double))],
            [(positive, SOSA.hasSimpleResult, Literal(37.5, datatype=XSD.double))],
            "PressureStateSummaryShape", counts_message),
        "share with zero days": (
            [(empty, SOSA.hasSimpleResult, Literal(0.0, datatype=XSD.double))], [],
            "PressureStateSummaryShape", counts_message),
        "more days above than observed": (
            [(empty, L.daysAboveReference, Literal(1))], [(empty, L.daysAboveReference, Literal(0))],
            "PressureStateSummaryShape", counts_message),
        "outcropping at order 2": (
            [(covered, L.coverStatus, L.Outcropping)], [(covered, L.coverStatus, L.Covered)],
            "HydrogeologicalSettingShape", "cover status disagrees with its stack position"),
        "setting unit differs from candidate": (
            [(off_stack, L.settingUnit, d("unit/A"))], [(off_stack, L.settingUnit, d("unit/C"))],
            "HydrogeologicalSettingShape", "unit is not the candidate unit of its attribution"),
        "confined without positive pressure evidence": (
            [(unknown, L.confinementState, L.ConfinedState), (unknown, L.confidence, L.Probable)],
            [(unknown, L.confinementState, L.ConfinementUnknown)],
            "ConfinementAssessmentShape", "rests on no pressure summary of its own well and window"),
        "unconfined state": (
            [(unknown, L.confinementState, L.UnconfinedState)], [(unknown, L.confinementState, L.ConfinementUnknown)],
            "ConfinementAssessmentShape", "an unconfined or semi-confined state"),
        "confined without confidence": (
            [], [(confined, L.confidence, L.Probable)],
            "ConfinementAssessmentShape", "a confined state without its confidence"),
        "monitoring attribution without setting": (
            [], list(g.triples((d("setting/no-summary/1"), None, None))),
            "Cq14CompletenessShape", "a monitoring attribution without exactly one hydrogeological setting"),
        "setting without assessment for a window with a summary": (
            [], list(g.triples((unknown, None, None))),
            "Cq14CompletenessShape", "a setting without exactly one confinement assessment"),
    }
    for name, (add, remove, shape, message) in cases.items():
        assert all(t in g for t in remove) and all(t not in g for t in add), name
        bad = rdflib.Graph()
        for t in g:
            bad.add(t)
        for t in remove:
            bad.remove(t)
        for t in add:
            bad.add(t)
        conforms, _, results = check(bad, shapes, net)
        assert not conforms and violations(results, shape, message) > 0, (name, results)
    print(f"  2. negative controls: all {len(cases)} errors raised their expected SHACL violations")


def station_stacks(wells):
    path = INTERIM / "bdlisa_station_stacks.csv"
    csv = pd.read_csv(path)
    print(f"     {path.name} columns {csv.columns.tolist()}")
    print(f"     sample {csv.iloc[0].to_dict()}")
    assert csv["code_bss"].is_unique
    csv = csv.set_index("code_bss")
    stacks = {}
    for c in csv.index.intersection(wells.index):
        row = csv.loc[c]
        recorded_unit = row.code_bdlisa if pd.notna(row.code_bdlisa) else None
        polygon = int(row.codepoly) if pd.notna(row.codepoly) else None
        units = row.stack_str.split(" > ") if pd.notna(row.stack_str) else []
        positions = {unit: i for i, unit in enumerate(units, start=1)}
        recorded_position = int(row.pos_in_stack) if pd.notna(row.pos_in_stack) else None
        assert positions.get(recorded_unit) == recorded_position, c
        dataset_unit = wells.loc[c, "code_bdlisa"]
        assert recorded_unit == (dataset_unit if pd.notna(dataset_unit) else None), c
        stacks[c] = polygon, positions

    # The CSV covers the core wells. Locate the remaining v4 stations in the same source map.
    missing = wells.loc[~wells.index.isin(csv.index)]
    print(f"     stack sources: {len(stacks)} stations in the CSV, {len(missing)} from the GeoPackage")
    if missing.empty:
        return stacks
    x, y = l93(missing["x"], missing["y"])
    points = gpd.GeoDataFrame(index=missing.index, geometry=gpd.points_from_xy(x, y), crs=CRS_L93)
    polygons = pyogrio.read_dataframe(GPKG, layer="POLYG_ELEMENTAIRES", columns=["codepoly"],
                                       bbox=tuple(points.total_bounds))
    located = gpd.sjoin(points, polygons, how="left", predicate="within")
    assert located.index.is_unique, "more than one BD LISA polygon contains a well"
    pile = pyogrio.read_dataframe(GPKG, layer="TABLE_PILE_ENTITES_NIV3", read_geometry=False)
    pile = pile[pile["CodePoly"].isin(located["codepoly"].dropna())]
    positions_by_polygon = {
        polygon: dict(zip(layers["CodeEH"], layers["OrdRelatif"]))
        for polygon, layers in pile.groupby("CodePoly")
    }
    for code, polygon in located["codepoly"].items():
        stacks[code] = (int(polygon), positions_by_polygon.get(polygon, {})) if pd.notna(polygon) else (None, {})
    return stacks


def check_released_settings(store, wells, stacks):
    attrs = rows(store, """SELECT ?a ?code ?rank ?candidate ?s ?unit ?polygon ?position ?cover WHERE {
        ?a lulcw:role lulcw:MonitoringRole ; lulcw:attributedEntity ?w ; lulcw:rank ?rank .
        ?w a lulcw:Piezometer ; lulcw:bssCode ?code .
        OPTIONAL { ?a lulcw:candidateUnit/lulcw:bdlisaCode ?candidate . }
        OPTIONAL {
            ?s a lulcw:HydrogeologicalSetting ; lulcw:settingAttribution ?a ; lulcw:settingOf ?w ;
               lulcw:coverStatus ?cover .
            OPTIONAL { ?s lulcw:settingUnit/lulcw:bdlisaCode ?unit . }
            OPTIONAL { ?s lulcw:settingPolygon/lulcw:polygonCode ?polygon . }
            OPTIONAL { ?s lulcw:stackPosition ?position . }
        }
    }""")
    assert {code for _, code, *_ in attrs} == set(wells.index), "some v4 wells lack monitoring attributions"
    assert len({a for a, *_ in attrs}) == len(attrs), "duplicate settings or values for an attribution"
    settings, counts = {}, Counter()
    for a, code, rank, candidate, setting, unit, polygon, position, cover in attrs:
        assert setting is not None and setting not in settings, (code, a, setting)
        if rank == 1:
            recorded = wells.loc[code, "code_bdlisa"]
            assert candidate == (recorded if pd.notna(recorded) else None), (code, candidate, recorded)
        want_polygon, positions = stacks[code]
        want_position = positions.get(candidate)
        want_cover = "CoverUnknown" if want_position is None else "Outcropping" if want_position == 1 else "Covered"
        assert (unit, polygon, position, cover) == (candidate, want_polygon, want_position, str(L[want_cover])), (
            code, a, (unit, polygon, position, cover), (candidate, want_polygon, want_position, want_cover))
        settings[setting] = code
        counts[want_cover] += 1
    all_settings = {s for (s,) in rows(store, "SELECT ?s WHERE { ?s a lulcw:HydrogeologicalSetting }")}
    assert set(settings) == all_settings, "some settings do not describe a monitoring attribution"
    print(f"     {len(settings)} settings for {len(wells)} wells; "
          + ", ".join(f"{cover} {counts[cover]}" for cover in ("Outcropping", "Covered", "CoverUnknown")))
    return settings


def check_released_summaries(store, well_codes):
    table = pressure.summaries()
    want = table.set_index(["code_bss", "window"], verify_integrity=True)
    expected_keys = {(code, window) for code in well_codes for window in pressure.WINDOWS}
    assert set(want.index) == expected_keys, "pressure oracle does not cover all well-window pairs"
    above_days = {}
    for code, window, days, above, share in rows(store, """SELECT ?code ?window ?days ?above ?share WHERE {
        ?ps a lulcw:PressureStateSummary ; sosa:hasFeatureOfInterest/lulcw:bssCode ?code ;
            lulcw:assessmentWindow ?window ; lulcw:daysObserved ?days ; lulcw:daysAboveReference ?above .
        OPTIONAL { ?ps sosa:hasSimpleResult ?share . }
    }"""):
        key = code, window
        assert key in want.index and key not in above_days, key
        expected = want.loc[key]
        expected_share = None if pd.isna(expected.share_pct) else expected.share_pct
        assert (days, above, share) == (expected.days, expected.days_above, expected_share), (
            key, (days, above, share), (expected.days, expected.days_above, expected_share))
        above_days[key] = above
    assert set(above_days) == expected_keys, expected_keys - set(above_days)
    print(f"     {len(above_days)} pressure summaries match the daily counts and shares to 0.1 percentage point")
    return above_days


def check_released_assessments(store, settings, above_days):
    counts, seen = Counter(), set()
    for s, window, state, confidence, code, source_window, above in rows(store, """
        SELECT ?s ?window ?state ?confidence ?code ?source_window ?above WHERE {
            ?a a lulcw:ConfinementAssessment ; lulcw:assessedSetting ?s ; lulcw:assessmentWindow ?window ;
               lulcw:confinementState ?state .
            OPTIONAL { ?a lulcw:confidence ?confidence . }
            OPTIONAL {
                ?a prov:wasDerivedFrom ?ps .
                ?ps a lulcw:PressureStateSummary ; sosa:hasFeatureOfInterest/lulcw:bssCode ?code ;
                    lulcw:assessmentWindow ?source_window ; lulcw:daysAboveReference ?above .
            }
        }
    """):
        key = s, window
        assert s in settings and key not in seen and window in pressure.WINDOWS, key
        assert (code, source_window) == (settings[s], window), (key, code, source_window)
        assert above == above_days[(code, window)], (key, above)
        expected_state = L.ConfinedState if above > 0 else L.ConfinementUnknown
        expected_confidence = str(L.Probable) if above > 0 else None
        assert (state, confidence) == (str(expected_state), expected_confidence), (key, above, state, confidence)
        seen.add(key)
        counts[(window, expected_state)] += 1
    expected = {(s, window) for s in settings for window in pressure.WINDOWS}
    assert seen == expected, expected - seen
    for window in pressure.WINDOWS:
        print(f"     {window}: {counts[(window, L.ConfinedState)]} confined, "
              f"{counts[(window, L.ConfinementUnknown)]} unknown")


def test_data(store):
    wells = pd.read_parquet(DATASET_DIR / "wells.parquet").set_index("code_bss", verify_integrity=True)
    piezometers = rows(store, "SELECT ?code WHERE { ?w a lulcw:Piezometer ; lulcw:bssCode ?code }")
    assert len(piezometers) == len(wells) == 65 and {c for (c,) in piezometers} == set(wells.index)
    settings = check_released_settings(store, wells, station_stacks(wells))
    above_days = check_released_summaries(store, wells.index)
    check_released_assessments(store, settings, above_days)


def main():
    net = ontology_network()
    rules, shapes = rdflib.Graph().parse(RULES), rdflib.Graph().parse(SHAPES)
    g = test_fixtures(rules, shapes, net)
    test_negative_controls(g, shapes, net)
    try:
        manifest = release.check()
    except release.StaleRelease as error:
        print(f"  3. data skipped ({error})")
    else:
        print(f"  3. data: validated release of {manifest['released']}")
        facts, derived = KG / f"lulcw_kg_{DATASET}.ttl", KG / f"lulcw_kg_{DATASET}_rules.ttl"
        test_data(store_of(facts, derived))
    print("test_cq14: all checks passed")


if __name__ == "__main__":
    main()
