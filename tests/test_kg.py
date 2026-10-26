"""Regression checks of the knowledge graph against its source tables (task 12.5).

    PFE_DATASET=v4 python -m src.kg.build_kg && PFE_DATASET=v4 python -m tests.test_kg

The graph is queried with SPARQL (pyoxigraph); every expected value is computed here again
from the source tables with pandas, not taken from the builder (docs/competency_questions.md
§6, "data-backed regression"):
1. Every class and property the graph uses is declared in the ontology network, and every
   concept it points to is declared in lulcw.ttl (catches typos in the builder).
2. Piezometers = the wells of the dataset, each with one station and one head series; a
   missing investigation depth stays missing (never 0) and the well stays in the graph.
3. CQ1 acceptance: W1 (NYLS-1) has its recorded 97 m depth and unit 671AA00; W2 (C2-1) lies in
   a polygon whose stack is 718BP02 > 671AA00; no screen depth comes from an investigation
   depth. One monitoring attribution per well: the recorded unit, or an explicit unknown.
4. Facilities = the groundwater ouvrages of the BNPE snapshot, each with at least one
   abstraction attribution (unknown allowed); the exact units and the best confidence per
   candidate equal the table of task 12.3.
5. CQ2 acceptance: group-level evidence never passes an exact-unit filter (no exact flag_true
   candidate is probable); a probable rule-based candidate is measured on its use.
6. Annual records: the declared volume per year and use equals the BNPE snapshot, in total
   and inside the plain's facility extent (CQ12's denominator); one result per record.
7. The typing rule never gives a unit two disjoint types; the BD LISA stacks are kept whole.
8. Negative controls: an undeclared property and an exact-unit link upgraded to probable,
   inserted on purpose, make checks 1 and 5 fail.
9. Text: no literal holds a control character (an encoding error; a deliberate U+0085 is
   caught), and the two RPG code tables give every code they share the same label.
"""
import json
import re
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
import pyoxigraph as ox
import rdflib
from rdflib.namespace import OWL, RDF, RDFS

from src.config import DATASET, DATASET_DIR, INTERIM, PROCESSED, RAW, ROOT

KG_FILE = PROCESSED / "kg" / f"lulcw_kg_{DATASET}.ttl"
PRE = """PREFIX lulcw: <https://w3id.org/lulcw#> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX sosa: <http://www.w3.org/ns/sosa/> PREFIX geo: <http://www.opengis.net/ont/geosparql#>
PREFIX time: <http://www.w3.org/2006/time#> BASE <https://w3id.org/lulcw/data/>
"""
L = "https://w3id.org/lulcw#"
BUILTIN = (str(RDF), str(RDFS), str(OWL))
W1, W2 = "10964X0119/NYLS-1", "10906X0039/C2-1"


def rows(store, query):
    """SPARQL SELECT -> DataFrame of plain Python values (IRIs as strings)."""
    res = store.query(PRE + query)
    names = [v.value for v in res.variables]
    out = []
    for r in res:
        vals = []
        for v in r:
            if v is None:
                vals.append(None)
            elif isinstance(v, ox.Literal):
                dt = v.datatype.value if v.datatype else ""
                vals.append(float(v.value) if dt.endswith(("double", "decimal", "integer"))
                            else v.value)
            else:
                vals.append(v.value)
        out.append(vals)
    return pd.DataFrame(out, columns=names)


def network():
    """The ontology network (lulcw-meta and its imports) through the catalog."""
    onto = ROOT / "ontology"
    cat = {u.get("name"): onto / u.get("uri")
           for u in ET.parse(onto / "catalog-v001.xml").getroot().iter() if u.tag.endswith("uri")}
    return rdflib.Graph().parse(cat["https://w3id.org/lulcw/meta"]) + sum(
        (rdflib.Graph().parse(f) for k, f in cat.items() if k != "https://w3id.org/lulcw/meta"),
        rdflib.Graph())


def test_declared(store, net):
    declared = {str(s) for s in net.subjects(RDF.type, None)}
    preds = set(rows(store, "SELECT DISTINCT ?p WHERE { ?s ?p ?o }")["p"])
    classes = set(rows(store, "SELECT DISTINCT ?c WHERE { ?s a ?c }")["c"])
    used = {x for x in preds | classes if not x.startswith(BUILTIN)}
    missing = sorted(used - declared)
    assert not missing, f"classes or properties not declared in the network: {missing}"
    concepts = set(rows(store, """SELECT DISTINCT ?o WHERE { ?s ?p ?o .
        FILTER(isIRI(?o) && STRSTARTS(STR(?o), "https://w3id.org/lulcw#")) }""")["o"])
    missing = sorted(concepts - declared)
    assert not missing, f"lulcw values not declared in lulcw.ttl: {missing}"
    print(f"  1. {len(used)} classes and properties and {len(concepts)} lulcw values, all declared")


def test_piezometers(store, wells):
    p = rows(store, """SELECT ?bss ?depth (COUNT(DISTINCT ?st) AS ?n_st) (COUNT(DISTINCT ?se) AS ?n_se)
        WHERE { ?w a lulcw:Piezometer ; lulcw:bssCode ?bss . OPTIONAL { ?w lulcw:investigationDepthM ?depth }
                OPTIONAL { ?st lulcw:hostedBy ?w . OPTIONAL { ?st lulcw:hasObservationSeries ?se } } }
        GROUP BY ?bss ?depth""")
    assert sorted(p["bss"]) == sorted(wells["code_bss"]), "piezometers differ from the dataset's wells"
    assert (p["n_st"] == 1).all() and (p["n_se"] == 1).all(), "a well without one station and one series"
    depth = wells.set_index("code_bss")["profondeur_investigation"]
    got = p.set_index("bss")["depth"].astype(float).reindex(depth.index)
    assert got.isna().equals(depth.isna()), "a missing depth was filled, or a depth was lost"
    assert np.allclose(got.dropna(), depth.dropna()), "an investigation depth differs"
    print(f"  2. {len(p)} piezometers = the wells of dataset {DATASET}, one station and one series "
          f"each; {int(depth.isna().sum())} without investigation depth stay without one")


def test_cq1(store, wells):
    w1 = rows(store, f"""SELECT ?depth ?unit ?conf WHERE {{ ?w lulcw:bssCode "{W1}" ;
        lulcw:investigationDepthM ?depth . ?a lulcw:attributedEntity ?w ; lulcw:role lulcw:MonitoringRole ;
        lulcw:candidateUnit/lulcw:bdlisaCode ?unit ; lulcw:confidence ?conf }}""")
    assert len(w1) == 1 and w1.iloc[0]["depth"] == 97.0 and w1.iloc[0]["unit"] == "671AA00", w1
    w2 = rows(store, f"""SELECT ?order ?unit WHERE {{ ?w lulcw:bssCode "{W2}" ; lulcw:locatedInPolygon ?p .
        ?p lulcw:hasStackLayer ?l . ?l lulcw:layerOrder ?order ; lulcw:layerUnit/lulcw:bdlisaCode ?unit }}
        ORDER BY ?order""")
    assert list(w2["unit"]) == ["718BP02", "671AA00"], w2
    screens = rows(store, "SELECT ?s WHERE { ?s lulcw:screenTopDepthM|lulcw:screenBottomDepthM ?d }")
    assert screens.empty, "a screen depth appeared without a construction record"
    a = rows(store, """SELECT ?bss (COUNT(?a) AS ?n) (SAMPLE(?code) AS ?unit) (SAMPLE(?why) AS ?reason)
        WHERE { ?a lulcw:role lulcw:MonitoringRole ; lulcw:attributedEntity/lulcw:bssCode ?bss .
                OPTIONAL { ?a lulcw:candidateUnit/lulcw:bdlisaCode ?code }
                OPTIONAL { ?a lulcw:unknownReason ?why } } GROUP BY ?bss""").set_index("bss")
    assert (a["n"] == 1).all(), "a well with several monitoring attributions"
    rec = wells.set_index("code_bss")["code_bdlisa"]
    assert a["unit"].reindex(rec.index).isna().equals(rec.isna()), "unknown iff no recorded unit"
    assert (a["unit"].reindex(rec.index).dropna() == rec.dropna()).all(), "a recorded unit differs"
    assert a.loc[a["unit"].isna(), "reason"].notna().all(), "an unknown without its reason"
    print(f"  3. CQ1: W1 97 m in 671AA00, W2 stack 718BP02 > 671AA00, no screen depths; "
          f"{int(rec.notna().sum())} recorded units, {int(rec.isna().sum())} explicit unknowns")


def test_facilities(store):
    pts = pd.read_parquet(RAW / "hubeau_bnpe" / "2026-10-20" / "points_prelevement_66.parquet")
    vol = pd.read_parquet(RAW / "hubeau_bnpe" / "2026-10-20" / "chroniques_66.parquet")
    gw_codes = set(pts.loc[pts["code_type_milieu"] == "SOUT", "code_ouvrage"]) & set(vol["code_ouvrage"])
    f = rows(store, """SELECT ?code (COUNT(?a) AS ?n) WHERE { ?f a lulcw:AbstractionFacility ;
        lulcw:bnpeCode ?code . OPTIONAL { ?a lulcw:attributedEntity ?f ; lulcw:role lulcw:AbstractionRole } }
        GROUP BY ?code""")
    assert set(f["code"]) == gw_codes, "facilities differ from the groundwater ouvrages of the snapshot"
    assert (f["n"] >= 1).all(), "a facility without an abstraction attribution"

    t = pd.read_parquet(INTERIM / "pump_unit_attribution.parquet")
    k = rows(store, """SELECT ?code ?rank ?unit ?group ?conf ?rule WHERE {
        ?a lulcw:role lulcw:AbstractionRole ; lulcw:attributedEntity/lulcw:bnpeCode ?code ; lulcw:rank ?rank ;
           lulcw:derivationRule ?rule .
        OPTIONAL { ?a lulcw:candidateUnit/lulcw:bdlisaCode ?unit } OPTIONAL { ?a lulcw:candidateGroup ?group }
        OPTIONAL { ?a lulcw:confidence ?c } BIND(LCASE(STRAFTER(STR(?c), "#")) AS ?conf) }""")
    k["rank"] = k["rank"].astype(int)
    absent = gw_codes - set(t["code_ouvrage"])
    extra = k[k["code"].isin(absent)]
    assert len(extra) == len(absent) and extra["unit"].isna().all() and extra["group"].isna().all()
    k = k[~k["code"].isin(absent)]
    exact = k[k["group"].isna()].set_index(["code", "rank"])
    tt = t.set_index(["code_ouvrage", "rank"])
    assert exact.index.sort_values().equals(tt.index.sort_values()), "candidates differ from task 12.3"
    assert (exact["unit"].reindex(tt.index).fillna("-") == tt["unit"].fillna("-")).all(), "a unit differs"
    order = {"": 0, "possible": 1, "probable": 2, "confident": 3}
    best = k.assign(o=k["conf"].fillna("").map(order)).groupby(["code", "rank"])["o"].max()
    want = tt["confidence"].replace("unknown", "").map(order)
    assert (best.reindex(want.index) == want).all(), "best confidence per candidate differs from 12.3"
    split = k[k["group"].notna()]
    print(f"  4. {len(f)} facilities = groundwater ouvrages of the snapshot ({len(absent)} absent from "
          f"dataset {DATASET}: explicit unknowns); units and best confidences = task 12.3; "
          f"{len(split)} candidates also stated at group level")


def exact_flag_true_probable(store):
    return rows(store, """SELECT ?a WHERE { ?a lulcw:derivationRule <rule/pump-flag-true> ;
        lulcw:resolution lulcw:ExactUnitResolution ; lulcw:confidence lulcw:Probable }""")


def test_cq2(store):
    bad = exact_flag_true_probable(store)
    assert bad.empty, f"exact-unit flag_true candidates passed as probable: {len(bad)}"
    m = rows(store, """SELECT ?a ?use WHERE { ?a lulcw:confidence lulcw:Probable ;
        lulcw:derivationRule ?r . ?e lulcw:evaluatedRule ?r .
        OPTIONAL { ?a lulcw:applicableUse ?use . ?e lulcw:applicableUse ?use } }""")
    assert m["use"].notna().all(), "a probable rule-based candidate without a measured use"
    print(f"  5. CQ2: no exact-unit flag_true candidate is probable; {m['a'].nunique()} probable "
          "rule-based candidates, each measured on its use")


def test_negative_controls(store, net):
    """The checks can fail: a typo property and an upgraded exact-unit link are caught."""
    typo = ox.Quad(ox.NamedNode("https://w3id.org/lulcw/data/x"), ox.NamedNode(L + "investigationDepth"),
                   ox.Literal("1"), ox.DefaultGraph())
    store.add(typo)
    try:
        test_declared(store, net)
        caught_typo = False
    except AssertionError:
        caught_typo = True
    store.remove(typo)
    a = rows(store, """SELECT ?a WHERE { ?a lulcw:derivationRule <rule/pump-flag-true> ;
        lulcw:resolution lulcw:ExactUnitResolution ; lulcw:confidence lulcw:Possible } LIMIT 1""")["a"][0]
    conf = ox.NamedNode(L + "confidence")
    old = ox.Quad(ox.NamedNode(a), conf, ox.NamedNode(L + "Possible"), ox.DefaultGraph())
    new = ox.Quad(ox.NamedNode(a), conf, ox.NamedNode(L + "Probable"), ox.DefaultGraph())
    store.remove(old)
    store.add(new)
    caught_upgrade = len(exact_flag_true_probable(store)) == 1
    store.remove(new)
    store.add(old)
    assert caught_typo and caught_upgrade, (caught_typo, caught_upgrade)
    print("  8. negative controls: an undeclared property and an exact flag_true link upgraded to "
          "probable are both caught")


CONTROL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def control_literals(store):
    return [(q.subject.value, q.object.value) for q in store.quads_for_pattern(None, None, None)
            if isinstance(q.object, ox.Literal) and CONTROL.search(q.object.value)]


def test_text(store):
    """No literal holds a C0/C1 control character, and the RPG code tables agree."""
    from src.kg.landuse import NOMENCLATURE
    bad = control_literals(store)
    assert not bad, f"{len(bad)} literals with control characters, e.g. {bad[:3]}"
    probe = ox.Quad(ox.NamedNode("https://w3id.org/lulcw/data/x"), ox.NamedNode(str(RDFS.label)),
                    ox.Literal("légumineuses, \x85)", language="fr"), ox.DefaultGraph())
    store.add(probe)
    caught = len(control_literals(store)) == 1
    store.remove(probe)
    assert caught, "a label with U+0085 was not caught"
    t = {y: pd.read_csv(RAW / "rpg" / "docs" / f, sep=None, engine="python", encoding=enc)
         .set_index("CODE_CULTURE")["LIBELLE_CULTURE"] for y, (f, enc) in NOMENCLATURE.items()}
    common = t[2023].index.intersection(t[2024].index)
    differ = common[t[2023][common] != t[2024][common]]
    assert len(common) > 100 and differ.empty, f"labels differ between the RPG tables: {list(differ)}"
    print(f"  9. text: no control character in any literal (a U+0085 probe is caught); the 2023 and "
          f"2024 RPG tables agree on all {len(common)} shared codes")


def test_records(store):
    d = pd.read_parquet(RAW / "hubeau_bnpe" / "2026-10-20" / "chroniques_66.parquet")
    pts = pd.read_parquet(RAW / "hubeau_bnpe" / "2026-10-20" / "points_prelevement_66.parquet")
    d = d[d["code_ouvrage"].isin(pts.loc[pts["code_type_milieu"] == "SOUT", "code_ouvrage"])]
    want = d.assign(u=d["code_usage"].fillna("none")).groupby(["annee", "u"])["volume"].sum()
    r = rows(store, """SELECT ?year ?u (SUM(?v) AS ?vol) (COUNT(?o) AS ?n) WHERE {
        ?o a lulcw:AnnualAbstractionRecord ; sosa:hasSimpleResult ?v ;
           sosa:phenomenonTime/time:hasBeginning/time:inXSDDate ?d .
        OPTIONAL { ?o lulcw:waterUse ?use } BIND(YEAR(?d) AS ?year)
        BIND(COALESCE(STRAFTER(STR(?use), "#"), "none") AS ?u) } GROUP BY ?year ?u""")
    code = {"DrinkingWaterUse": "AEP", "IrrigationUse": "IRR", "IndustryUse": "IND",
            "CanalSupplyUse": "CAN", "EnergyUse": "ENE", "none": "none"}
    got = r.assign(u=r["u"].map(code), year=r["year"].astype(int)).set_index(["year", "u"])["vol"]
    assert int(r["n"].sum()) == len(d), "record count differs from the snapshot"
    assert np.allclose(got.reindex(want.index), want, rtol=1e-12), "a declared volume differs"
    one = rows(store, """SELECT ?o (COUNT(?v) AS ?n) WHERE { ?o a lulcw:AnnualAbstractionRecord ;
        sosa:hasSimpleResult ?v } GROUP BY ?o HAVING (COUNT(?v) != 1)""")
    assert one.empty, "a record with several results"
    lon0, lat0, lon1, lat1 = 2.55 - 0.04, 42.50 - 0.04, 3.06 + 0.04, 42.88 + 0.04
    plain = d[d["longitude"].between(lon0, lon1) & d["latitude"].between(lat0, lat1)]
    v = rows(store, """SELECT (SUM(?v) AS ?vol) WHERE { ?o a lulcw:AnnualAbstractionRecord ;
        sosa:hasSimpleResult ?v ; sosa:hasFeatureOfInterest ?f .
        ?f geo:sfWithin <extent/plain-box-margin> }""")["vol"].iloc[0]
    assert np.isclose(v, plain["volume"].sum(), rtol=1e-12), "plain extent total differs"
    print(f"  6. {len(d)} annual records; volumes per year and use = the snapshot; plain extent "
          f"{v / 1e6:.1f} Mm3 over {d['annee'].min()}-{d['annee'].max()}")


def test_units(store):
    clash = rows(store, """SELECT ?u WHERE { ?u a ?c1 , ?c2 .
        VALUES ?c1 { lulcw:AlluvialAquifer lulcw:MultilayerAquiferSystem lulcw:KarstAquifer lulcw:ConfiningUnit }
        VALUES ?c2 { lulcw:AlluvialAquifer lulcw:MultilayerAquiferSystem lulcw:KarstAquifer lulcw:ConfiningUnit }
        FILTER(?c1 != ?c2) }""")
    assert clash.empty, f"units with two disjoint types: {clash}"
    t = rows(store, """SELECT ?code ?c WHERE { ?u lulcw:bdlisaCode ?code ; a ?c }""")
    t = t.set_index("code")["c"].str.split("#").str[-1]
    for code, cls in (("671AA00", "MultilayerAquiferSystem"), ("671AB01", "AlluvialAquifer"),
                      ("718BP02", "AlluvialAquifer"), ("681AM00", "KarstAquifer"),
                      ("679AB00", "ConfiningUnit")):
        assert t.get(code) == cls, f"{code}: {t.get(code)} instead of {cls}"
    s = rows(store, """SELECT ?p (COUNT(?l) AS ?n) (MIN(?o) AS ?lo) (MAX(?o) AS ?hi) WHERE {
        ?p lulcw:hasStackLayer ?l . ?l lulcw:layerOrder ?o } GROUP BY ?p""")
    assert ((s["lo"] == 1) & (s["hi"] == s["n"])).all(), "a stack with missing orders"
    wkt = rows(store, "SELECT ?w WHERE { ?g geo:asWKT ?w }")["w"]
    assert wkt.str.startswith("<http://www.opengis.net/def/crs/EPSG/0/2154> ").all()
    xy = wkt[wkt.str.contains("POINT")].str.extract(r"POINT\(([\d.]+) ([\d.]+)\)").astype(float)
    assert xy[0].between(5.5e5, 7.5e5).all() and xy[1].between(6.0e6, 6.3e6).all(), "a point off dept 66"
    print(f"  7. {len(t)} units typed by the written rule, none twice; {len(s)} stacks complete; "
          f"{len(wkt)} geometries in EPSG:2154")


def main():
    if not KG_FILE.exists():
        print(f"{KG_FILE.relative_to(ROOT)} not built here, skipped (python -m src.kg.build_kg)")
        return
    store = ox.Store()
    store.bulk_load(path=str(KG_FILE), format=ox.RdfFormat.TURTLE)
    wells = pd.read_parquet(DATASET_DIR / "wells.parquet")
    net = network()
    test_declared(store, net)
    test_piezometers(store, wells)
    test_cq1(store, wells)
    test_facilities(store)
    test_cq2(store)
    test_records(store)
    test_units(store)
    test_negative_controls(store, net)
    test_text(store)
    summary = json.loads((KG_FILE.parent / f"lulcw_kg_{DATASET}_summary.json").read_text())
    print(f"test_kg: all checks passed ({summary['triples']} triples, built {summary['built']}, "
          f"code {summary['code_version']})")


if __name__ == "__main__":
    main()
