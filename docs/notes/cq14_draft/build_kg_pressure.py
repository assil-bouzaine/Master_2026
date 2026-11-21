# Draft (2026-11-21, Claude): to paste into src/kg/build_kg.py after T34's release is committed.
# 1. RELEASES gets the chronicles:
#    "hubeau-piezo-chronicles": ("Hub'Eau niveaux_nappes daily chronicles of the département 66 "
#                                "stations", "2026-10-05",
#                                "https://hubeau.eaufrance.fr/api/v1/niveaux_nappes/chroniques"),
# 2. `from src.kg import pressure` next to the other src.kg imports.
# 3. main(): `n_pressure = pressure_states(kg, rel, wells)` after `piezometers(...)`, and
#    "pressure_state_summaries": n_pressure in the summary.


# ----------------------------------------------------------------------------- CQ14 pressure states
def pressure_states(kg, rel, wells):
    """CQ14 (Gate 3 point 15; analysis plan §14 item 23): one lulcw:PressureStateSummary, a SOSA
    observation, per well and training window (train, f25, f50): the days of the window with a depth
    to water, the days with the water above the station's measurement reference, and their share in
    percent (src/kg/pressure.py, equal to the dataset's artesian share). A window without any depth
    value gets days = 0 and no result: unknown, never 0. The rules (order 66) derive the
    confinement assessment from these summaries, never from the geological stack alone."""
    release = rel["hubeau-piezo-chronicles"]
    intervals = {}
    for name, (start, end) in pressure.windows().items():
        iv = kg.node(iri("interval", "training-window", name), TIME.ProperInterval)
        stop = (end + pd.Timedelta(days=1)).date().isoformat()      # the day after the last one
        for p, day in ((TIME.hasBeginning, start.date().isoformat()), (TIME.hasEnd, stop)):
            inst = kg.node(iri("instant", day), TIME.Instant)
            kg.add(inst, TIME.inXSDDate, Literal(day, datatype=XSD.date))
            kg.add(iv, p, inst)
        kg.add(iv, RDFS.comment, Literal(
            f"training window {name}: measurement days {start.date()} to {end.date()}, start "
            "inclusive, end exclusive", lang="en"))
        intervals[name] = iv
    keys = {w.code_bss: (w.bss_id if isinstance(w.bss_id, str) and w.bss_id else w.code_bss)
            for w in wells.itertuples(index=False)}
    table = pressure.summaries(list(keys))
    for r in table.itertuples(index=False):
        key = keys[r.code_bss]
        o = kg.node(iri("pressure-state", key, r.window), L.PressureStateSummary)
        kg.add(o, SOSA.hasFeatureOfInterest, iri("piezometer", key))
        kg.add(o, SOSA.observedProperty, L.HeadAboveReferenceShare)
        kg.add(o, SOSA.usedProcedure, L.HeadAboveReferenceCount)
        kg.add(o, SOSA.phenomenonTime, intervals[r.window])
        kg.add(o, L.assessmentWindow, Literal(r.window))
        kg.add(o, L.daysObserved, Literal(int(r.days), datatype=XSD.integer))
        kg.add(o, L.daysAboveReference, Literal(int(r.days_above), datatype=XSD.integer))
        if r.days:
            kg.add(o, SOSA.hasSimpleResult, dbl(r.share_pct))
        kg.add(o, PROV.wasDerivedFrom, record(kg, "hubeau-piezo-chronicle", r.code_bss, release))
    return len(table)
