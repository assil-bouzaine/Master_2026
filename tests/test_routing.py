"""Checks of the routed inputs (src/models/routing.py).

    PFE_DATASET=v4 python -m tests.test_routing

1. Baseline edges reproduce the feature panel: with each well's own SAFRAN cell, the groundwater
   facilities within 3 km (weight 1) and the canal for every well, the routed rain, ETP, PE,
   pumping and canal series equal the panel's columns (the inputs of rungs 1-2 and of the
   baselines). The routing code and the panel code are separate, so this is a check of both.
2. Arms C and D (the export): shapes, no missing value, non-negative volumes; a well without an
   edge for a relation has zeros and its flag off; coverage = the export's manifest; arm C has no
   unattributed input; arm D's routed plus unattributed pumping equals the distance-weighted sum
   over every groundwater facility within 5 km (nothing lost, nothing counted twice).
3. A hand-made case: two cells with weights 1 and 3 give the 1:3 weighted mean; two facilities
   with weights 0.5 and 2 give that weighted sum.
"""
import numpy as np
import pandas as pd

from src.config import DATASET_DIR
from src.kg import export as E
from src.models.evaluate import RESULTS
from src.models.routing import coverage, load_edges, routed_inputs

EDGE = E.EDGE_COLS


def edge_table(rows):
    return pd.DataFrame([E.edge(*r) for r in rows], columns=EDGE)


def test_baseline():
    wells, fac, _, _ = E.tables()
    d = E._dist(wells, fac)
    rows = [("recharge", "weather_cell", c, w, 1.0) for w, c in zip(wells["code_bss"], wells["cell_id"])]
    rows += [("canal", "canal", E.CANAL, w, 1.0) for w in wells["code_bss"]]
    # the panel selects facilities with "contains" on a 3 km buffer polygon (src/dataset/load.py),
    # whose 64 sides lie up to 3.6 m inside the circle: 3 wells have a facility at 2,999.3-2,999.9 m
    # that the panel leaves out (found here on 2026-11-10). Same predicate, so the check is exact.
    from shapely.geometry import Point
    pts = [Point(x, y) for x, y in zip(fac["x93"], fac["y93"])]
    edge_cases = 0
    for i, (x, y) in enumerate(zip(wells["x93"], wells["y93"])):
        buf = Point(x, y).buffer(3000.0)
        for j in np.where(d[i] <= 3000.0)[0]:
            if buf.contains(pts[j]):
                rows.append(("pumping", "facility", fac["code_ouvrage"].iloc[j], wells["code_bss"].iloc[i], 1.0, d[i, j]))
            else:
                edge_cases += 1
    R = routed_inputs(edges=edge_table(rows))
    P = pd.read_parquet(RESULTS / "_cache" / "panel.parquet",
                        columns=["code_bss", "week", "rain", "ETP", "PE", "pump_gw", "canal"])
    worst = {}
    for v in ("rain", "ETP", "PE", "pump_gw", "canal"):
        want = P.pivot(index="code_bss", columns="week", values=v).reindex(index=R["codes"], columns=R["weeks"])
        diff = np.abs(R[v] - want.to_numpy())
        scale = max(1.0, float(np.nanmax(np.abs(want.to_numpy()))))
        worst[v] = float(np.nanmax(diff)) / scale
        assert worst[v] < 1e-6, (v, worst[v])
    print(f"  1. baseline edges (own cell, facilities within 3 km, canal) reproduce the panel's rain, ETP, PE, "
          f"pumping and canal columns for {len(R['codes'])} wells x {len(R['weeks'])} weeks "
          f"(largest relative difference {max(worst.values()):.1e}); {edge_cases} facility-well pairs lie within "
          f"3 km but outside the panel's buffer polygon")


def test_arms():
    wells = pd.read_parquet(DATASET_DIR / "wells.parquet")
    core = wells["core"].to_numpy()
    out = {}
    for arm in ("C", "D"):
        R = routed_inputs(arm)
        edges, meta = load_edges(arm)
        N, T = len(R["codes"]), len(R["weeks"])
        for v in ("rain", "ETP", "PE", "pump_gw", "pump_un", "river", "canal"):
            assert R[v].shape == (N, T) and np.isfinite(R[v]).all(), (arm, v)
        assert (R["pump_gw"] >= 0).all() and (R["pump_un"] >= 0).all() and (R["canal"] >= 0).all()
        for rel, vars_ in (("recharge", ("rain", "ETP", "PE")), ("pumping", ("pump_gw",)),
                           ("pumping_unattributed", ("pump_un",)), ("river", ("river",)), ("canal", ("canal",))):
            off = ~R["has_" + rel]
            assert all(np.abs(R[v][off]).max(initial=0.0) == 0.0 for v in vars_), (arm, rel)
            want = meta["arms"][arm].get(rel, {"wells": 0, "core_wells": 0})
            got = coverage(R, core)[rel]
            assert (got["wells"], got["core_wells"]) == (want["wells"], want["core_wells"]), (arm, rel, got, want)
        out[arm] = R
    assert not out["C"]["has_pumping_unattributed"].any()
    # arm D: routed + unattributed = every groundwater facility within 5 km, distance-weighted
    t_wells, t_fac, _, _ = E.tables()
    d = E._dist(t_wells, t_fac)
    rows = [("pumping", "facility", t_fac["code_ouvrage"].iloc[j], t_wells["code_bss"].iloc[i],
             np.exp(-d[i, j] / E.PUMP_DECAY_M), d[i, j])
            for i in range(len(t_wells)) for j in np.where(d[i] <= E.D_RADIUS_M)[0]]
    allnear = routed_inputs(edges=edge_table(rows))
    total = out["D"]["pump_gw"] + out["D"]["pump_un"]
    # the graph's facility points are rounded to 0.1 m: its distances differ from the dataset's by
    # at most 0.08 m, the weights by about 1e-5
    assert np.allclose(total, allnear["pump_gw"], rtol=1e-4, atol=1e-6)
    cov = {a: coverage(out[a], core) for a in out}
    print("  2. arms C and D: finite series, zeros where a well has no edge, coverage = the export's manifest; "
          "arm D's routed + unattributed pumping = every groundwater facility within 5 km. Core wells with "
          "each relation, C / D: " + ", ".join(
              f"{rel} {cov['C'][rel]['core_wells']} / {cov['D'][rel]['core_wells']}" for rel in cov["D"]))


def test_weights():
    wells, fac, _, cells = E.tables()
    w = wells["code_bss"].iloc[0]
    c1, c2 = cells["cell_id"].iloc[0], cells["cell_id"].iloc[1]
    f1, f2 = fac["code_ouvrage"].iloc[0], fac["code_ouvrage"].iloc[1]
    single = {}
    for name, rows in (("c1", [("recharge", "weather_cell", c1, w, 1.0)]), ("c2", [("recharge", "weather_cell", c2, w, 1.0)]),
                       ("f1", [("pumping", "facility", f1, w, 1.0)]), ("f2", [("pumping", "facility", f2, w, 1.0)]),
                       ("mix", [("recharge", "weather_cell", c1, w, 1.0), ("recharge", "weather_cell", c2, w, 3.0),
                                ("pumping", "facility", f1, w, 0.5), ("pumping", "facility", f2, w, 2.0)])):
        single[name] = routed_inputs(edges=edge_table(rows), codes=[w])
    assert np.allclose(single["mix"]["rain"], 0.25 * single["c1"]["rain"] + 0.75 * single["c2"]["rain"])
    assert np.allclose(single["mix"]["pump_gw"], 0.5 * single["f1"]["pump_gw"] + 2.0 * single["f2"]["pump_gw"])
    print("  3. hand-made weights: cells 1 and 3 give the 1:3 mean; facilities 0.5 and 2 give that weighted sum")


if __name__ == "__main__":
    test_baseline()
    test_arms()
    test_weights()
    print("test_routing: all checks passed")
