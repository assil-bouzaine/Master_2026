"""LU-6, first version: two land-use-to-water examples answered from the knowledge graph.

    PFE_DATASET=v4 python -m src.analysis.lu6_example      # -> docs/lu6_example.md

The Codex review of 2026-10-25 asked for "one complete, inspectable example" of the subject's
chain (dated land use -> water demand and supported pathways -> model -> groundwater -> an
explanation). This report follows the chain for an alluvium well (MILLAS C2-1, recent alluvium
of the Têt) and a Pliocene well (PONTEILLA NYLS-1), with the stored competency-question queries
of tests/cq/ (task 12.7) and their answer status, so every statement cites the query it comes
from, and every gap is a status, not a silence. The model step is the pre-registered land-use
test (LU-4, results/<dataset>/land_use_test.csv); an explanation of a model output (CQ10) and the
satellite rule (CQ15) do not exist yet and are listed as such. Rivers and canals (CQ5, CQ6) since
2026-11-06.
"""
import re
from datetime import date
from urllib.parse import unquote

import pandas as pd
from rdflib import URIRef

from src.config import DATASET, RESULTS_DIR, ROOT
from src.kg.build_kg import D, git_version
from src.kg.cq import ask, iris, kg_store, local, one

OUT = ROOT / "docs" / "lu6_example.md"
WELLS = {"10906X0039/C2-1": "an alluvium well near the Têt",
         "10964X0119/NYLS-1": "a Pliocene well in the drinking-water fields south of Perpignan"}
YEARS = range(2015, 2026)
RADIUS = 5000.0
MAIN = URIRef(f"{D}policy/main")
# short citations of the documents of data/raw/documents/documents.json (src.ingest.documents)
CITE = {"brgm-rp-71486-fr": "BRGM/RP-71486-FR", "sierm-frdg351": "FRDG351 sheet, 2021",
        "sierm-frdg243": "FRDG243 sheet, 2021", "smnpr-fonctionnement-des-nappes": "SMNPR"}
SIGN = {"PositiveResponse": "non-decreasing", "NegativeResponse": "non-increasing",
        "UnknownResponse": "unknown or conditional"}


def ha(x):
    return f"{x:,.0f}"


def share(w):
    return f"{w:.2f}" if w >= 0.005 else "<0.01"


def words(name):
    """A concept's local name in words: CanalReturnFlow -> canal return flow."""
    return re.sub(r"(?<!^)(?=[A-Z])", " ", name).lower()


def section(s, code, what, pz, lines):
    w = pz[code]
    lines.append(f"## {code}: {what}\n")

    # 1. the well and its unit (CQ1, CQ3)
    a = ask(s, "cq01_assignments", W=w)
    st1 = one(s, "cq01_status", W=w)
    stack = ask(s, "cq01_stack", W=w)
    unit = next((r["unitCode"] for r in a if r["unitCode"]), None)
    lines.append("### 1. The well and what it monitors (CQ1, CQ3)\n")
    for r in a:
        if r["unitCode"]:
            lines.append(f"- Recorded unit **{r['unitCode']}** ({local(r['confidence']).lower()}, "
                         f"{local(r['evidenceKind'])}, source record `{unquote(local(r['source']))}`)")
        else:
            lines.append(f"- No unit: {r['unknownReason']}")
    depth = a[0]["investigationDepthM"] if a else None
    lines.append(f"- Investigation depth: {f'{depth:g} m' if depth is not None else 'not recorded'} "
                 "(not a screened interval; no screen is recorded)")
    if stack:
        lines.append(f"- Mapped stack under the well (BD LISA polygon {stack[0]['polygonCode']}): "
                     + " > ".join(r["unitCode"] for r in stack))
    rel = [r for r in ask(s, "cq03_relations", U=URIRef(f"{D}unit/{unit}"))
           if stack and r["polygonCode"] == stack[0]["polygonCode"]] if unit else []
    for r in rel:
        lines.append(f"- In that polygon: {r['upperCode']} above {r['lowerCode']} "
                     f"({'direct contact' if local(r['kind']) == 'DirectContact' else 'with ' + r['intervening'] + ' between'}); "
                     "geological order, not a hydraulic connection")
    lines.append(f"- Status: {st1['status']}: {st1['reason']}\n")

    # 2. land use within 3 km (CQ7)
    lines.append("### 2. Dated land use within 3 km, and its potential irrigation demand (CQ7)\n")
    lines.append("| RPG year | area observed (ha) | classes usually irrigated (ha) | vines (ha) | "
                 "potential demand, main (m³) | category |")
    lines.append("|---|---:|---:|---:|---:|---|")
    last = None
    for y in YEARS:
        cls = ask(s, "cq07_classes", W=w, year=y)
        if not cls:
            continue
        usual = sum(r["areaHa"] for r in cls if local(r["irrigationAssumption"]) == "UsuallyIrrigated")
        vine = sum(r["areaHa"] for r in cls if r["class"] == "vine")
        dem = {local(r["property"]): r for r in ask(s, "cq07_demand", W=w, year=y)}
        m = dem.get("PotentialIrrigationDemandMain", {})
        cat = {"HighIrrigationDemand": "high", "BelowHighIrrigationDemand": "below high"}.get(
            local(m.get("category")), "none")
        lines.append(f"| {y} | {ha(sum(r['areaHa'] for r in cls))} | {ha(usual)} | {ha(vine)} | "
                     f"{m.get('demandM3', float('nan')):,.0f} | {cat} |")
        last = (y, cls, m)
    y, cls, m = last
    top = sorted(cls, key=lambda r: -r["areaHa"])[:5]
    lines.append(f"\nLargest classes in {y}: " + ", ".join(
        f"{r['class'].replace('_', ' ')} {ha(r['areaHa'])} ha ({local(r['irrigationAssumption']) or 'no assumption'})"
        for r in top) + ".")
    if m:
        lines.append(f"The {y} category compares the main estimate with {m['thresholdM3']:,.0f} m³, the upper "
                     "tercile of the training years 2015–2019 over the 65 zones: relative to these zones, "
                     "not an agronomic norm. The demand is a potential requirement (FAO-56 Kc × ETP − rain on "
                     "the clipped crop areas), never metered irrigation.")
    st7 = one(s, "cq07_status", W=w, year=y)
    lines.append(f"\nStatus: {st7['status']}: {st7['reason']} ({st7['unalignedCodes']} of {st7['codes']} codes).\n")

    # 3. water: pumping that may reach the well (CQ2, CQ8)
    lines.append(f"### 3. Groundwater abstraction that may reach the well (CQ2, CQ8), within {RADIUS / 1000:g} km\n")
    cand = ask(s, "cq02_candidates", W=w, r=RADIUS, policy=MAIN)
    unres = ask(s, "cq02_unresolved", W=w, r=RADIUS)
    exact = [r for r in cand if local(r["resolution"]) == "ExactUnitResolution"]
    group = [r for r in cand if local(r["resolution"]) != "ExactUnitResolution"]
    by_conf = pd.Series([local(r["confidence"]).lower() for r in exact]).value_counts().to_dict()
    uses = pd.Series([u for r in cand for u in (r["uses"] or "").split()]).value_counts().to_dict()
    lines.append(f"- {len(exact)} facility candidates at the well's exact unit "
                 f"({', '.join(f'{n} {c}' for c, n in by_conf.items()) or 'none'}), {len(group)} at unit-group "
                 f"level only; the main policy accepts {sum(r['selected'] for r in cand)} of them.")
    if uses:
        lines.append("- Uses declared, with the number of these facilities that declared each at least once: " + ", ".join(
            f"{u.replace('Use', '').replace('DrinkingWater', 'drinking water').replace('NotRecorded', 'not recorded').lower()} ({n})"
            for u, n in uses.items()) + ".")
    lines.append(f"- {len(unres)} nearby facilities have no candidate unit (unresolved, never zero, never attributed).")
    inf = ask(s, "cq08_influences", W=w, policy=MAIN)
    pump = [r for r in inf if local(r["mechanism"]) == "PumpingDrawdown"]
    elig = [r for r in pump if local(r["eligibility"]) == "EligibleConstraint"]
    acc = [r for r in elig if r["selected"]]
    lines.append(f"- Pumping influences derived by the rules: {len(pump)} paths, {len(elig)} with the "
                 f"non-increasing sign of pumping drawdown (exact unit), {len(acc)} of these accepted by the "
                 f"main policy; {len(pump) - len(elig)} group-level paths carry no sign.")
    if acc:
        lines.append(f"  Their stated condition: \"{acc[0]['conditions']}\"")
    st2 = one(s, "cq02_status", W=w, r=RADIUS)
    lines.append(f"- Status CQ2: {st2['status']}.\n")

    # 4. recharge proxies (CQ4, CQ8)
    lines.append("### 4. Rain over the outcrop of the well's unit: recharge proxies (CQ4, CQ8)\n")
    rech = [r for r in inf if local(r["mechanism"]) == "DiffuseRecharge"]
    near = sorted((r for r in rech if "/outcrop-zone/" in r["extent"]), key=lambda r: -r["cellWeight"])
    wide = [r for r in rech if "/outcrop-zone/" not in r["extent"]]
    zone = iris(s, "SELECT ?c ?z WHERE { ?z a lulcw:OutcropSearchZone ; lulcw:zoneOf/lulcw:bssCode ?c }")[code]
    cov = ask(s, "cq04_coverage", U=URIRef(f"{D}unit/{unit}"), S=zone) if unit else []
    if near:
        lines.append(f"- {len(near)} SAFRAN cells hold the outcrop of {unit} mapped within {RADIUS / 1000:g} km "
                     f"of the well ({cov[0]['outcropAreaM2'] / 1e6:.2f} km², {cov[0]['unitShareInS']:.0%} of the "
                     "unit's mapped outcrop); their shares: "
                     + ", ".join(f"{r['driverCode']} {share(r['cellWeight'])}" for r in near) + ".")
    else:
        lines.append(f"- No outcrop of {unit} is mapped within {RADIUS / 1000:g} km of the well: no recharge proxy "
                     "in the main runs (not zero recharge).")
    lines.append(f"- The unit-wide sensitivity gives the well {len(wide)} cells (every well of {unit} the same).")
    if rech:
        r = rech[0]
        lines.append(f"- Each proxy is the cell's weekly {words(local(r['driverVariable']))} standing in for "
                     f"{words(local(r['proxyFor']))}, with a non-decreasing response, eligible to constrain a "
                     "model (whether recharge signs do is settled at Gate 3). Not represented: "
                     + ", ".join(words(m) for m in sorted(r["omittedPathways"].split())) + ".")
    st8 = one(s, "cq08_status", W=w)
    lines.append(f"- Status CQ8: {st8['status']} (recharge proxies: {st8['recharge']}): {st8['reason']}.\n")

    # 5. rivers and canals (CQ5, CQ6, CQ8)
    lines.append("### 5. Rivers and canals near the well (CQ5, CQ6, CQ8)\n")
    rz = iris(s, "SELECT ?c ?z WHERE { ?z a lulcw:ReachSearchZone ; lulcw:zoneOf/lulcw:bssCode ?c }")[code]
    U = URIRef(f"{D}unit/{unit}") if unit else None
    assoc = [r for r in ask(s, "cq05_associations", S=rz) if r["unitCode"] == unit]
    kind = {"OnOutcrop": f"on the outcrop of {unit}", "OverCover": f"over the units covering {unit}",
            "DocumentedLateral": f"beside {unit}, with a documented exchange"}
    for r in assoc:
        km = r["lengthOnOutcropM"] or r["lengthOverCoverM"]
        lines.append(f"- {r['watercourseName']} ({r['watercourseCode']}) runs {kind[r['type']]}"
                     + (f" for {km / 1000:.1f} km" if km else "")
                     + (f" (cover: {r['coverUnits']})" if r["coverUnits"] else "")
                     + f" within {RADIUS / 1000:g} km of the well; {r['statements']} statement(s) apply.")
    if not assoc:
        lines.append(f"- No searched watercourse runs on, over or documentedly beside {unit} within "
                     f"{RADIUS / 1000:g} km of the well.")
    if U is not None:
        st5 = one(s, "cq05_status", U=U, S=rz)
        lines.append(f"- Status CQ5: {st5['status']}: {st5['reason']}.")
        stm = ask(s, "cq05_statements", S=rz, U=U)
        for r in [r for r in stm if r["applies"]]:
            flux = f", {r['fluxM3s']:g} m³/s" if r["fluxM3s"] else ""
            lines.append(f"  - {r['section']}: {words(r['direction'])} ({words(r['hedging'])}; {r['state']}{flux}; "
                         f"{CITE.get(r['documentKey'], r['documentKey'])}, p. {r['page']}).")
        rest = [r for r in stm if not r["applies"]]
        if rest:
            lines.append(f"  - {len(rest)} more statement(s) about {unit} listed but not applied (their stretch is "
                         "not delimited, or no association of the unit meets their section).")
    gname = {r["gaugeCode"]: r["gaugeName"] for r in ask(s, "cq05_gauges", S=rz)}
    for r in [r for r in inf if local(r["mechanism"]) == "RiverExchange"]:
        lines.append(f"- River influence (arm D): gauge {r['driverCode']} ({gname.get(r['driverCode'], '')}), "
                     f"{words(r['associationType'])}, response {SIGN[local(r['responseSign'])]}, "
                     f"{words(local(r['eligibility']))}: {r['eligibilityReason']}")
    lines.append(f"- Status CQ8 (rivers): {st8['river']}: {st8['riverReason']}.")
    if U is not None:
        st6 = one(s, "cq06_status", U=U, S=rz)
        chain = ask(s, "cq06_chain", S=rz, U=U)
        if chain:
            names = (chain[0]["canals"] or "").split(" | ")
            lines.append(f"- Canals run {chain[0]['lengthOnOutcropM'] / 1000:.1f} km on the outcrop of {unit} within "
                         f"{RADIUS / 1000:g} km (" + ", ".join(names[:4]) + (", ..." if len(names) > 4 else "")
                         + f"); command area: {chain[0]['commandArea']}.")
            for r in [r for r in chain if r["statement"]]:
                flux = f", {r['fluxM3s']:g} m³/s" if r["fluxM3s"] else ""
                lines.append(f"  - {local(r['statement'])}: {words(r['direction'])} ({words(r['hedging'])}{flux}; "
                             f"{CITE.get(r['documentKey'], r['documentKey'])}, p. {r['page']}).")
        lines.append(f"- Status CQ6: {st6['status']}: {st6['reason']}.")
    for r in [r for r in inf if local(r["mechanism"]) == "CanalReturnFlow"]:
        lines.append(f"- Canal influence (arm D): the plain's canal intakes, response {SIGN[local(r['responseSign'])]}, "
                     f"{words(local(r['eligibility']))}.")
    lines.append(f"- Status CQ8 (canals): {st8['canal']}: {st8['canalReason']}.\n")
    return unit


def main():
    s = kg_store()
    pz = iris(s, "SELECT ?c ?w WHERE { ?w a lulcw:Piezometer ; lulcw:bssCode ?c }")
    lines = ["# Land use to water: two worked examples answered from the knowledge graph (generated)\n",
             f"Generated by `src/analysis/lu6_example.py` on {date.today().isoformat()} from the knowledge "
             f"graph of dataset {DATASET} (code {git_version(('src/kg', 'ontology', 'tests/cq'))}); do not edit by "
             "hand. LU-6, first version (step 12d note). Each statement is the answer of a stored "
             "competency-question query (`tests/cq/`), with its status; a gap is reported as a status, "
             "never as a silence.\n",
             "The chain of the subject: dated land use → water demand and supported pathways → model → "
             "groundwater → explanation. Sections 1–5 answer it from the graph for each well; section 6 "
             "is the model step; section 7 lists what cannot be answered yet.\n"]
    units = {}
    for code, what in WELLS.items():
        units[code] = section(s, code, what, pz, lines)

    # the unit's accounting for the plain (CQ12), last complete year of declarations
    ext = URIRef(f"{D}extent/plain-box-margin")
    lines.append("## Both units: declared abstraction attributed to them in the plain (CQ12)\n")
    lines.append("Each facility's declared volume goes once to its best-ranked attribution that the "
                 "main policy selects; the rest stays unresolved. 2024, facilities of the plain "
                 "(plain box + about 3 km):\n")
    acc = ask(s, "cq12_accounting", year=2024, extent=ext, policy=MAIN)
    decl = sum(r["volumeM3"] for r in ask(s, "cq12_declared", year=2024, extent=ext))
    lines.append("| use | to 671AA00 (Pliocene) | to 718BP02 (Têt alluvium) | to a unit group only | unresolved |")
    lines.append("|---|---:|---:|---:|---:|")
    for use in sorted({r["use"] for r in acc}):
        rows = [r for r in acc if r["use"] == use]
        get = lambda f: sum(r["volumeM3"] for r in rows if f(r)) / 1e6  # noqa: E731
        lines.append(f"| {use.replace('Use', '')} | {get(lambda r: r['targetCode'] == '671AA00'):.2f} | "
                     f"{get(lambda r: r['targetCode'] == '718BP02'):.2f} | "
                     f"{get(lambda r: r['allocation'] == 'unit group'):.2f} | "
                     f"{get(lambda r: r['allocation'] == 'unresolved'):.2f} |")
    lines.append(f"\nIn Mm³; declared total {decl / 1e6:.1f} Mm³. Declared withdrawals of facilities in the "
                 "extent, not consumption nor all abstraction from a unit.\n")

    # 6. the model step (LU-4)
    lines.append("## 6. Does a model use this land use? (LU-4, pre-registered)\n")
    t = pd.read_csv(RESULTS_DIR / "land_use_test.csv")
    main_rows = t[(t["kind"] == "main")]
    for _, r in main_rows.iterrows():
        lines.append(f"- {r['model']}, {r['metric']}: median paired difference {r['median_diff']:+.3f} "
                     f"[{r['ci_lo']:+.3f}, {r['ci_hi']:+.3f}], p (Holm) {r['p_holm']:.2f}")
    lines.append("\nThe crop-thirst index of section 2, as a model input, adds no detectable information to "
                 "the drought-phase simulation of the 33 core wells (with and without the feature, "
                 "trained on the same machine). The alluvium wells, where crops and canals should matter "
                 "most, are too few among the core wells for a group test (step 12d note).\n")

    # 7. what cannot be answered yet
    lines.append("## 7. What the graph cannot say yet\n")
    lines.append("- **Whether a parcel is irrigated, and from which water** (CQ15): the satellite rule "
                 "needs the Earth Engine login (task 12.10); 84 % of the plain's declared irrigation water is "
                 "surface water (mostly the Têt and Agly canals), so most crop demand never reaches a "
                 "borehole.")
    lines.append("- **Which fields a canal serves, and how much of its water reaches a unit** (CQ6): no "
                 "command-area map exists for the plain, so the canal link of section 5 is a documented "
                 "pathway, never a local return amount.")
    lines.append("- **Lateral inflow and vertical leakage** are not `lulcw:Influence` records: CQ8 is partial "
                 "for every well. Rain over the outcrop (section 4) and a gauge's discharge (section 5) are "
                 "proxies: for the Pliocene the sources name other pathways as the main ones (the Têt and its "
                 "alluvium upstream, the Corbières karst and the border massifs, leakage from the Quaternary).")
    lines.append("- **Irrigation pumping by unit:** the main policy places no irrigation volume in a unit "
                 "(`docs/pump_coverage.md`); farm-borehole effects come only from the all-links sensitivity.")
    lines.append("- **An explanation of a model output** (CQ10): needs the Phase 4 model and its contributions.")
    lines.append("- **Shared vocabularies for the crops** (RPG → AGROVOC, task 12.9): CQ7 is partial until then.")
    OUT.write_text("\n".join(lines) + "\n")
    print(f"-> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
