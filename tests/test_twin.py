"""Checks of the semi-synthetic twin's generator (src/models/twin.py).

    PFE_DATASET=v4 python -m tests.test_twin       (about 3 minutes; the learner runs 20 steps only)

1. Model class: for parameters set by hand, the generator's contributions equal the response
   model's (same kernels, same recharge stress, same causal convolution), so a base world lies
   inside the learner's model class and only variants O and S leave it.
2. One base world on the real wells: head = level + contributions + noise on the weeks with a real
   head, missing elsewhere (the real pattern); each contribution's training variance = its share x
   the real well's training variance; gains signed as the design states; noise variance = nu x the
   noise-free variance.
3. Graphs: arms C and D are the export's tables; with eps = 0 and u = 0 arm D's attributed pumping
   input equals the truth's exactly; the truth's recharge, river and canal edges are D's plus the
   own cell where D has no recharge (C's in variant G); the realised u reaches the dial and stops at
   the first pair that does; truths are nested in eps and in u for one world seed; the realised eps
   is unbiased (mean of 30 seeds).
4. Variants: S (pumping response delayed by exactly the dead time; thresholded recharge never
   negative), I (declared years untouched, imputed years changed, factor of mean one), O (only the
   omitted group, 0.15 of its noise-free variance), timing "independent" (annual totals kept, one
   calendar profile, no volume lost for facilities without training volume).
5. The same seed and dials give the same world; another seed another one.
6. End to end through run_cell: three arms fitted for 20 steps from two starts, hard and soft
   (RQ2), scored, written (every score present and finite; under hard no gain violates its sign).
   This checks the code path, not the learner. And the learner-setting specs parse as documented.
   A resumed cell with other settings stops instead of mixing worlds; the fitted weights are saved
   beside each world (astra review points 10 and 1, 2026-11-20).
7. Score 5 per well (the plan's definition; astra review point 1): on two hand-made wells with
   disjoint true facilities and a cross-link in the arm, a well's input moves only through its own
   true facilities; the old plain-wide cut also moves it through the other well's. On a real world
   the truth's per-well cut equals its plain-wide cut (a well feels only its own true facilities).
8. Parallel manifest writers keep every world and session record (astra review point 14).
"""
import json
import shutil

import numpy as np
import pandas as pd
import torch

from src.models import response as R
from src.models import twin as W

_BASE = {}


def base():
    if not _BASE:
        _BASE.update(W.load_base())
    return _BASE


def _logit(p):
    return np.log(p / (1 - p))


def test_model_class():
    N, T, K = 4, 150, 40
    rng = np.random.default_rng(0)
    L = T + K - 1
    X = {"rain": rng.gamma(0.4, 3.0, (N, L)), "ETP": 1.5 + rng.random((N, L)), "PE": rng.random((N, L)),
         "pump_gw": rng.random((N, L)), "pump_un": np.zeros((N, L)), "river": 1 + rng.random((N, L)),
         "canal": rng.random((N, L))}
    X = {k: torch.from_numpy(v.astype(np.float32)) for k, v in X.items()}
    a, n = rng.uniform(1, 15, (N, 4)), rng.uniform(1, 2.5, (N, 4))
    f = rng.uniform(0.4, 1.0, N)
    gain = np.array([0.3, -0.2, 0.1, 0.05]) * rng.uniform(0.5, 2, (N, 4))
    net = R.ResponseModel(np.zeros(N, dtype=int), 1, "free", kernel_weeks=K, pumping="arm")
    idx = [net.names.index(s) for s in W.TRUTH]
    Rn = len(net.names)
    raw = np.zeros((N, 3 * Rn + 1))
    for s, r in enumerate(idx):
        raw[:, r] = np.log(np.expm1(np.abs(gain[:, s])))                     # softplus^-1
        raw[:, Rn + r] = _logit((np.log(a[:, s]) - np.log(R.A_MIN)) / (np.log(net.amax) - np.log(R.A_MIN)))
        raw[:, 2 * Rn + r] = _logit((n[:, s] - R.N_MIN) / (R.N_MAX - R.N_MIN))
    raw[:, 3 * Rn] = _logit(f / R.F_MAX)
    with torch.no_grad():
        net.group_mean.zero_()
        net.delta.copy_(torch.from_numpy(raw))
        c_net = net.contributions(X).numpy()[:, idx]
    c_gen = W.truth_contributions(X, a, n, f, K, gain=gain)
    err = np.abs(c_net - c_gen).max() / np.abs(c_gen).max()
    assert err < 1e-5, err
    print(f"  1. the generator's contributions = the response model's for the same parameters "
          f"(relative difference {err:.1e}): a base world lies in the learner's model class")


def test_world():
    b = base()
    w = W.make_world(b, 0, **W.BASE)
    tr = b["train"]
    real = R.panel_arrays(b["P"], b["K"])
    assert np.array_equal(np.isnan(w["head"]), np.isnan(real["head"]))
    total = w["level"][:, None] + sum(w["contrib"].values()) + w["omitted"] + w["noise"]
    ok = np.isfinite(w["head"])
    assert np.allclose(w["head"][ok], total[ok], rtol=0, atol=1e-9)
    sd_real = np.maximum(real["sd"][:, 0], R.SD_FLOOR)
    for r, s in enumerate(W.TRUTH):
        want = np.sqrt(w["params"]["share"][:, r]) * sd_real
        assert np.allclose(w["contrib"][s][:, tr].std(1), want, rtol=1e-6, atol=1e-12), s
    g = w["params"]["gain"]
    assert (g[:, 0] >= 0).all() and (g[:, 1] <= 0).all() and (g[:, 2] >= 0).all() and (g[:, 3] >= 0).all()
    assert (w["contrib"]["pumping"] <= 0).all()
    sh = w["params"]["share"]
    assert np.allclose(sh[sh[:, 1] > 0, 1], W.BASE["pi"]) and (sh[:, 0] >= W.MIN_RECHARGE_SHARE).all()
    ratio = w["noise"][:, tr].var(1) / w["clean"][:, tr].var(1)
    assert np.allclose(ratio, W.BASE["nu"])
    print(f"  2. a base world: {ok.sum():,} synthetic heads on the real observed weeks; contribution "
          f"variances = share x real variance; signs as designed; noise / signal variance "
          f"{np.median(ratio):.2f}; realised: {w['realised']}")


def test_graphs():
    b = base()
    ed = b["ed"]
    w = W.make_world(b, 1, **dict(W.BASE, eps=0.0, u=0.0))
    assert w["edges"]["C"] is b["ec"] and w["edges"]["D"] is b["ed"]
    rt, rd, rc = w["routed"]["truth"], w["routed"]["D"], w["routed"]["C"]
    tr_p = w["edges"]["truth"][w["edges"]["truth"]["relation"] == "pumping"]
    d_p = ed[ed["relation"] == "pumping"]
    assert set(zip(tr_p["src"], tr_p["dst"])) == set(zip(d_p["src"], d_p["dst"])) and len(tr_p) == len(d_p)
    # the same pairs; the two matrix products sum over different facility lists (BLAS order): 1e-16
    assert np.allclose(rt["pump_gw"], rd["pump_gw"], rtol=1e-12, atol=1e-12)
    has_d = rd["has_recharge"]
    assert np.allclose(rt["rain"][has_d], rd["rain"][has_d]) and np.allclose(rt["rain"][~has_d], rc["rain"][~has_d])
    assert np.array_equal(rt["river"], rd["river"]) and np.array_equal(rt["canal"], rd["canal"])
    g = W.make_world(b, 1, **dict(W.BASE, variant="G"))
    for v in ("rain", "ETP", "river", "canal"):
        assert np.allclose(g["routed"]["truth"][v], g["routed"]["C"][v]), v
    # realised u and nesting
    mean_vol = b["vol"].loc[b["weeks"][b["train"]]].mean()
    A, U = ed[ed["relation"] == "pumping"], ed[ed["relation"] == "pumping_unattributed"]
    attributed = set(zip(A["src"], A["dst"]))
    truth = {}
    for eps, u in ((0.0, 0.3), (0.0, 0.6), (0.1, 0.3), (0.25, 0.3)):
        tp, rec = W.pumping_graphs(b, eps, u, 7)
        truth[(eps, u)] = (set(zip(tp["src"], tp["dst"])), rec)
    assert truth[(0.0, 0.3)][0] <= truth[(0.0, 0.6)][0]
    assert attributed - truth[(0.1, 0.3)][0] <= attributed - truth[(0.25, 0.3)][0]
    assert attributed <= truth[(0.0, 0.3)][0]
    checked = 0
    for i, r in truth[(0.0, 0.3)][1].iterrows():
        target = 0.3 / 0.7 * r["v_attributed_true"]
        if r["v_attributed_true"] > 0 and r["v_unattributed"] >= target:
            un = U[U["dst"] == r["code_bss"]]
            vu = (un["weight"] * un["src"].map(mean_vol).fillna(0.0)).to_numpy()
            cum = np.cumsum(vu[W._gen(7, "u", i).permutation(len(un))])
            k = int(r["true_extra"])
            assert r["u_realised"] >= 0.3 - 1e-9 and cum[k - 1] >= target - 1e-9 and (k == 1 or cum[k - 2] < target)
            checked += 1
    recs = [W.pumping_graphs(b, 0.25, 0.3, s)[1] for s in range(30)]
    eps_real = np.mean([x["false_attributed"].sum() / x["attributed"].sum() for x in recs])
    assert abs(eps_real - 0.25) < 0.01, eps_real
    print(f"  3. arms C and D = the export's tables; eps = u = 0: arm D's pumping = the truth's; other "
          f"relations D's (+ own cell; C's in variant G); u reached and minimal in {checked} wells; "
          f"truths nested in eps and u; realised eps {eps_real:.3f} for 0.25 (30 seeds)")


def test_variants():
    b = base()
    tr = b["train"]
    w0 = W.make_world(b, 2, **W.BASE)
    data = R.panel_arrays(b["P"], b["K"], w0["routed"]["truth"])
    X = {k: torch.from_numpy(v) for k, v in data["X"].items()}
    p = w0["params"]
    c0 = W.truth_contributions(X, p["a"], p["n"], p["f"], b["K"])
    cS = W.truth_contributions(X, p["a"], p["n"], p["f"], b["K"], "S", tr)
    d = W.DEAD_WEEKS
    assert np.array_equal(cS[:, 1, d:], c0[:, 1, :-d])
    assert (cS[:, 0] >= 0).all() and (c0[:, 0] < 0).any()
    wS = W.make_world(b, 2, **dict(W.BASE, variant="S"))
    assert np.array_equal(wS["params"]["a"], p["a"]) and np.array_equal(wS["params"]["n"], p["n"])
    # I: hidden variation in the imputed years only
    imp = W.imputed_years(b["weeks"])
    assert set(range(2005, 2012)) <= set(imp) and not set(range(2012, 2020)) & set(imp)
    wI = W.make_world(b, 2, **dict(W.BASE, variant="I"))
    yrs = wI["vol"].index.year
    dec = ~np.isin(yrs, imp)
    assert np.array_equal(wI["vol_truth"].to_numpy()[dec], wI["vol"].to_numpy()[dec])
    assert not np.allclose(wI["vol_truth"].to_numpy()[~dec], wI["vol"].to_numpy()[~dec])
    tp, Tp = wI["routed"]["truth"]["pump_gw"], wI["routed"]["T"]["pump_gw"]
    assert np.allclose(tp[:, dec], Tp[:, dec]) and not np.allclose(tp[:, ~dec], Tp[:, ~dec])
    idx = pd.date_range("2010-01-03", "2021-12-26", freq="W-SUN")
    rng = np.random.default_rng(0)
    vol = pd.DataFrame(np.ones((len(idx), 4000)) * rng.uniform(1, 2, 4000), index=idx)
    for y in range(2012, 2020):
        vol.loc[idx.year == y] *= rng.lognormal(0, 0.4, 4000)
    out = W.hidden_variation(vol, [2010, 2011, 2020, 2021], list(range(2012, 2020)), np.random.default_rng(1))
    factor = (out.loc[idx.year == 2010].sum() / vol.loc[idx.year == 2010].sum()).mean()
    assert abs(factor - 1) < 0.02, factor
    # O: an omitted driver in one group
    wO = W.make_world(b, 2, **dict(W.BASE, variant="O"))
    in_g = wO["group_of"] == wO["groups"].index(W.OMITTED_GROUP)
    assert (wO["omitted"][~in_g] == 0).all() and (wO["omitted"][in_g] != 0).all()
    clean = sum(wO["contrib"].values())
    assert np.allclose(wO["omitted"][in_g][:, tr].var(1) / clean[in_g][:, tr].var(1), W.OMITTED_SHARE)
    # timing "independent"
    v = b["vol"]
    cal = W.calendar_volumes(v, tr)
    y = v.index.year
    a0, a1 = v.groupby(y).sum().to_numpy(), cal.groupby(y).sum().to_numpy()
    assert np.allclose(a1[a0 > 0], a0[a0 > 0], rtol=1e-9) and (a1[a0 <= 0] == 0).all()
    woy = np.minimum(v.index.isocalendar().week.to_numpy(), 52)
    seqs = {yr: tuple(woy[y == yr]) for yr in range(2006, 2019)}
    y1, y2 = next((p, q) for p in seqs for q in seqs if p < q and seqs[p] == seqs[q])
    tot = cal.groupby(y).sum()
    both = ((tot.loc[y1] > 0) & (tot.loc[y2] > 0)).to_numpy()
    s1 = (cal.loc[y == y1] / tot.loc[y1]).to_numpy()[:, both]
    s2 = (cal.loc[y == y2] / tot.loc[y2]).to_numpy()[:, both]
    assert np.allclose(s1, s2)
    wT = W.make_world(b, 2, **dict(W.BASE, timing="independent"))
    assert wT["vol"] is not b["vol"] and np.allclose(wT["vol"].to_numpy(), cal.to_numpy())
    print(f"  4. variants: S (dead time {d} weeks exactly, recharge >= 0), I (only {len(imp)} imputed years "
          f"changed, mean factor {factor:.3f}), O (group '{W.OMITTED_GROUP}', share {W.OMITTED_SHARE}), "
          f"timing independent (annual totals kept, one profile: {y1} = {y2})")


def test_reproducible():
    b = base()
    a, a2, c = (W.make_world(b, s, **W.BASE) for s in (3, 3, 4))
    assert np.array_equal(a["head"], a2["head"], equal_nan=True)
    assert not np.allclose(a["head"], c["head"], equal_nan=True)
    print("  5. same seed and dials -> the same world; another seed -> another")


def test_parse_fit():
    assert W.parse_fit("free") == ("free", "free", 0.0, None, "structure", None)
    assert W.parse_fit("pooled:0.1:3000") == ("pooled_l0.1_fixed3000", "pooled", 0.1, 3000, "structure", None)
    assert W.parse_fit("free+none") == ("free_none", "free", 0.0, None, "none", None)
    assert W.parse_fit("pooled:0.01+soft1") == ("pooled_l0.01_soft1", "pooled", 0.01, None, "none", 1.0)
    for bad in ("pooled", "free+soft0", "free+sof1", "lstm"):
        try:
            W.parse_fit(bad)
        except ValueError:
            continue
        raise AssertionError(bad)


def test_end_to_end():
    b = base()
    run = "_test_twin"
    folder = W.RESULTS / run
    assert not folder.exists(), f"{folder} exists: remove it first"
    try:
        W.run_cell(b, W.BASE, [5], run, fits=("free:0:20", "free:0:20+soft1"), starts=(0, 1), steps=20)
        rec = json.loads((folder / W.cell_tag(W.BASE) / "world_5.json").read_text())
        s, soft = rec["fits"]["free_fixed20"], rec["fits"]["free_fixed20_soft1"]
        assert all(s[f"violation_rate_{a}"] == 0.0 for a in W.ARMS)
        assert all(soft[f"violation_rate_{a}"] is not None for a in W.ARMS)
        for k in ("log_rmse_D_over_C", "log_rmse_T_over_C", "log_rmse_D_over_T", "nse_drought_D",
                  "recovery_pumping_T", "recovery_recharge_C", "pumping_right_D",
                  "seed_disagreement_pumping_C", "intervention_well_rel_error_T", "intervention_well_sign_D",
                  "intervention_plain_rel_error_C", "intervention_plain_sign_D", "lag_error_recharge_wk_C"):
            assert s[k] is not None and np.isfinite(s[k]), k
        assert "intervention_rel_error_D" not in s and rec["scores_version"] == W.SCORES_VERSION
        # the oracle routes exactly the truth: its per-well and plain-wide cuts are the same cut
        assert np.isclose(s["intervention_well_rel_error_T"], s["intervention_plain_rel_error_T"], rtol=1e-9, atol=1e-12)
        assert len(rec["per_well"]["free_fixed20"]["code_bss"]) == s["wells"] > 0
        cell = folder / W.cell_tag(W.BASE)
        assert (cell / "manifest.json").exists()
        nets = torch.load(cell / "world_5_nets.pt", weights_only=True)
        assert set(nets["states"]) == {"free_fixed20", "free_fixed20_soft1"}
        assert all(len(nets["states"][k][a]) == 2 for k in nets["states"] for a in W.ARMS)
        # resuming the same cell with other settings must stop, not mix worlds
        try:
            W.run_cell(b, W.BASE, [5, 6], run, fits=("free:0:20", "free:0:20+soft1"), starts=(0, 1), steps=21)
        except SystemExit as err:
            assert "steps" in str(err), err
        else:
            raise AssertionError("a cell resumed with other settings must stop")
        assert not (cell / "world_6.json").exists()
        W.run_cell(b, W.BASE, [5], run, fits=("free:0:20", "free:0:20+soft1"), starts=(0, 1), steps=20)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    print(f"  6. run_cell end to end (20 steps, 2 starts, arms C, D, T): every score written, "
          f"{s['wells']} core wells scored; weights saved; a resume with other settings stops")


def test_per_well_cut():
    weeks = pd.date_range("2021-01-03", "2023-12-31", freq="W-SUN")
    codes = ["w1", "w2"]
    vol = pd.DataFrame({"f1": 1.0, "f2": 2.0, "f3": 4.0}, index=weeks)
    cols = ["relation", "src_type", "src", "dst", "weight", "distance_m"]
    edge = lambda rel, s, d, w=1.0: (rel, "facility", s, d, w, 100.0)  # noqa: E731
    truth = pd.DataFrame([edge("pumping", "f1", "w1"), edge("pumping", "f2", "w2")], columns=cols)
    # the arm links w1 to its own true facility f1 and to f2 (true for w2 only), w2 to f3 (not true)
    arm = pd.DataFrame([edge("pumping", "f1", "w1", 0.5), edge("pumping_unattributed", "f2", "w1", 0.25),
                        edge("pumping", "f3", "w2")], columns=cols)
    fac = ["f1", "f2", "f3"]
    routed = {"pump_gw": W._matrix(arm, "pumping", codes, fac) @ vol[fac].to_numpy().T,
              "pump_un": W._matrix(arm, "pumping_unattributed", codes, fac) @ vol[fac].to_numpy().T,
              "rain": np.ones((2, len(weeks)))}
    world = {"weeks": weeks, "codes": codes, "vol": vol, "edges": {"truth": truth, "C": arm},
             "routed": {"C": routed}}
    cut = W.per_well_cut(world, "C", vol)
    dr = W.drought(weeks)
    d_gw, d_un = cut["pump_gw"] - routed["pump_gw"], cut["pump_un"] - routed["pump_un"]
    assert np.allclose(d_gw[0, dr], -W.CUT * 0.5 * 1.0) and np.allclose(d_gw[0, ~dr], 0.0)
    assert np.allclose(d_un, 0.0), "f2 is true for w2 only: cutting w1's true facilities leaves it"
    assert np.allclose(d_gw[1], 0.0), "the arm does not link w2 to its true facility f2"
    assert cut["rain"] is routed["rain"] and routed["pump_gw"][0, 0] == 0.5
    # the plain-wide cut (before 2026-11-20) moved w1 through f2 as well
    plain = vol.copy()
    plain.loc[dr, ["f1", "f2"]] *= 1 - W.CUT
    plain_un = W._matrix(arm, "pumping_unattributed", codes, fac) @ plain[fac].to_numpy().T
    assert np.allclose((plain_un - routed["pump_un"])[0, dr], -W.CUT * 0.25 * 2.0)
    # on a real world the truth's per-well cut is its plain-wide cut
    b = base()
    w = W.make_world(b, 3, **W.BASE)
    tr = w["edges"]["truth"]
    v = w["vol_truth"].copy()
    v.loc[W.drought(w["weeks"]), sorted(set(tr.loc[tr["relation"] == "pumping", "src"]) & set(v.columns))] *= 1 - W.CUT
    union = W.routed_inputs(edges=tr, codes=w["codes"], weeks=w["weeks"], volumes=v)
    per_well = W.per_well_cut(w, "truth", w["vol_truth"])
    assert np.allclose(per_well["pump_gw"], union["pump_gw"], rtol=0, atol=1e-9)
    d_arm = {a: np.abs(W.per_well_cut(w, a, w["vol"])["pump_gw"] - w["routed"][a]["pump_gw"]).sum() for a in ("C", "D")}
    assert all(x > 0 for x in d_arm.values())
    print("  7. score 5 per well: a well's input moves only through its own true facilities (hand-made "
          "cross-link case); on a real world the truth's per-well cut = its plain-wide cut")


def _manifest_writer(args):
    """Ten manifest updates; every json.loads waits 20 ms, so a writer that reads the manifest
    without the lock would overwrite another's update (the race of astra review point 14)."""
    folder, k = args
    import time
    import types
    import src.models.manifest as M
    M.json = types.SimpleNamespace(loads=lambda t: (time.sleep(0.02), json.loads(t))[1], dumps=json.dumps)
    for i in range(10):
        M.write_manifest(folder, {"writer": k}, [100 * k + i])


def test_manifest_parallel():
    import multiprocessing as mp
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        with mp.get_context("spawn").Pool(4) as pool:
            pool.map(_manifest_writer, [(folder, k) for k in range(4)])
        m = json.loads((folder / "manifest.json").read_text())
        assert m["seeds_done"] == sorted(100 * k + i for k in range(4) for i in range(10)), m["seeds_done"]
        assert len(m["sessions"]) == 40
    print("  8. four parallel manifest writers x 10 records: all 40 ids and 40 sessions kept")


if __name__ == "__main__":
    for name, fn in sorted(globals().items(), key=lambda kv: kv[1].__code__.co_firstlineno
                           if callable(kv[1]) and hasattr(kv[1], "__code__") else 0):
        if name.startswith("test_"):
            fn()
    print("test_twin: all checks passed")
