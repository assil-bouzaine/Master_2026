"""Checks of the twin map's reading (src/analysis/twin_report.reading), on hand-made tables only.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 python -m tests.test_twin_report

The rules were fixed in analysis plan §14 item 19 point 10 before any world was read; the code that
applies them is tested here on invented numbers, never on the grid's worlds, so that no real result
shaped it.
1. (a) A cell pays only when its median D / C is at most -0.05 and its 97.5 % quantile is below 0.
2. (c) Where D beats C, "right reasons" needs D's pumping recovery to beat C's.
3. (d) The verdict on the bracket cells follows (a).
4. (e) The protocol with the better pumping recovery in most cells is recommended unless it loses
   more than 0.05 drought NSE; otherwise no recommendation.
5. (f) The RQ2 table appears when hard and soft/none settings exist for the base cell, and reads
   twin_rq2 alone when it holds all three settings (score 5 per well).
Added 2026-11-20 (astra review points 5, 6 and 10), on invented numbers too:
6. No verdict on incomplete grids: a cell under 20 worlds is "pending"; without the four complete
   bracket cells (d) is pending, never "no bracket cell pays".
7. Protocols: worlds are paired; tied cells are counted apart; a 6-6 split or 12 ties give no
   recommendation; an unpaired cell keeps (e) pending.
8. Score 6 is a count of worlds ("4 of 20 (20%)"), not a median of 0/1 flags.
9. The loader renames the first worlds' score 5 (plain-wide) and stops on a cell whose worlds were
   made with different settings.
10. Slice F's scores, grid thresholds, pilot rule and paired comparison (item 23) are read from
    hand-made world files. The section is omitted when the selected runs have no F cell.
"""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from src.analysis import twin_report as TR
from src.analysis.twin_report import count, reading


def world_rows(cell, setting, d_over_c, rec_d, rec_c, nse_d, n=20, spread=0.01, seed=0, run="twin_map", **extra):
    # deterministic worlds: D / C spread evenly around its median (97.5 % quantile ≈ median + 1.9 spread)
    offsets = spread * np.linspace(-2.0, 2.0, n)
    e, u = cell
    rows = []
    for w in range(n):
        rows.append({"run": run, "cell": f"e{e:g}_u{u:g}_p0.3_n0.25_rec_base", "world": w,
                     "setting": setting, "dial_eps": e, "dial_u": u, "dial_pi": 0.3, "dial_nu": 0.25,
                     "dial_timing": "reconstructed", "dial_variant": np.nan,
                     "log_rmse_D_over_C": d_over_c + offsets[w],
                     "log_rmse_D_over_T": 0.01, "recovery_pumping_D": rec_d, "recovery_pumping_C": rec_c,
                     "nse_drought_D": nse_d, **extra})
    return rows


def grid(d_over_c=lambda e, u: -0.1, rec=(0.2, 0.3), nse=0.6, setting="free", spread=0.01, n=lambda e, u: 20):
    rows = []
    for e in (0.0, 0.1, 0.25, 0.5):
        for u in (0.0, 0.3, 0.6):
            r = rec(e, u) if callable(rec) else rec
            rows += world_rows((e, u), setting, d_over_c(e, u), *r, nse, spread=spread, n=n(e, u),
                               seed=int(100 * e + 10 * u))
    return rows


def test_pays_and_reasons():
    # pays everywhere at -0.1 with a narrow spread; at -0.04 nowhere; a wide spread breaks (a)
    text = reading(pd.DataFrame(grid()))
    assert text.count("| yes |") == 12 and "right reasons" in text and "at least one bracket cell pays" in text
    text = reading(pd.DataFrame(grid(d_over_c=lambda e, u: -0.04)))
    assert "| yes |" not in text and "no bracket cell pays" in text
    text = reading(pd.DataFrame(grid(d_over_c=lambda e, u: -0.06, spread=0.05)))
    assert "| yes |" not in text, "a 97.5 % quantile above 0 must not pay"
    # D beats C but recovers pumping worse: other reasons
    text = reading(pd.DataFrame(grid(rec=(0.4, 0.3))))
    assert "D more accurate for other reasons" in text and "right reasons |" not in text
    # gains that shrink with eps and u (pumping knowledge) show up along the dials
    text = reading(pd.DataFrame(grid(d_over_c=lambda e, u: -0.2 + 0.3 * e + 0.2 * u)))
    assert "D / C along eps (median over u): 0: -0.140" in text, text


def test_protocols():
    a = grid(setting="free", rec=(0.20, 0.3), nse=0.60)
    b = grid(setting="pooled_l0.1_fixed3000", rec=(0.25, 0.3), nse=0.62)
    text = reading(pd.DataFrame(a + b))
    assert "Recommendation for Gate 3 point 1: **free**" in text, text
    b = grid(setting="pooled_l0.1_fixed3000", rec=(0.25, 0.3), nse=0.70)   # free loses 0.10 NSE
    text = reading(pd.DataFrame(a + b))
    assert "no recommendation by this rule" in text


def test_rq2_table():
    rows = grid()
    for setting in ("free_none", "free_soft1"):
        rows += world_rows((0.1, 0.3), setting, -0.05, 0.2, 0.3, 0.6, violation_rate_D=0.2,
                           intervention_well_sign_D=0.8)
    text = reading(pd.DataFrame(rows))
    assert "(f) RQ2" in text and "free_soft1" in text and "free_none" in text
    # twin_rq2 with all three settings: (f) reads it alone (the grid's "free" rows are left out)
    for setting in ("free", "free_none", "free_soft1"):
        rows += world_rows((0.1, 0.3), setting, -0.05, 0.2, 0.3, 0.6, run="twin_rq2",
                           violation_rate_D=0.0, intervention_well_sign_D=0.9)
    text = reading(pd.DataFrame(rows))
    f = text.split("(f) RQ2")[1]
    assert "| twin_rq2 |" in f and "| twin_map |" not in f and "| 20 | 0.900 [0.900, 0.900] |" in f, f


def test_incomplete_grid():
    # two cells outside the bracket only: (d) is pending, never "no bracket cell pays"
    rows = [r for r in grid(d_over_c=lambda e, u: -0.04) if (r["dial_eps"], r["dial_u"]) in {(0.0, 0.0), (0.5, 0.6)}]
    text = reading(pd.DataFrame(rows))
    assert "no bracket cell pays" not in text and "pending: 0 of 4 bracket cells complete" in text, text
    # a bracket cell with 19 worlds: its verdict and (d) wait
    text = reading(pd.DataFrame(grid(d_over_c=lambda e, u: -0.04, n=lambda e, u: 19 if (e, u) == (0.1, 0.3) else 20)))
    assert "pending (19 of 20 worlds)" in text and "pending: 3 of 4 bracket cells complete" in text, text
    # ... but a complete bracket cell that pays is reported at once
    text = reading(pd.DataFrame(grid(d_over_c=lambda e, u: -0.1 if (e, u) == (0.25, 0.6) else -0.04,
                                     n=lambda e, u: 19 if (e, u) == (0.1, 0.3) else 20)))
    assert "at least one bracket cell pays" in text


def test_protocol_ties_and_splits():
    a = grid(setting="free", rec=(0.25, 0.3), nse=0.60)
    b = grid(setting="pooled_l0.1_fixed3000", rec=(0.25, 0.3), nse=0.60)        # identical: 12 ties
    text = reading(pd.DataFrame(a + b))
    assert "tied in 12" in text and "no recommendation by this rule" in text and "**free**" not in text, text
    six = lambda e, u: (0.20, 0.3) if e < 0.2 else (0.30, 0.3)                  # noqa: E731 free wins 6 cells
    b = grid(setting="pooled_l0.1_fixed3000", rec=(0.25, 0.3), nse=0.60)
    text = reading(pd.DataFrame(grid(setting="free", rec=six, nse=0.60) + b))
    assert "free in 6 cells, pooled_l0.1_fixed3000 in 6" in text and "strict majority" in text, text
    # one cell where free has 19 worlds: the comparison waits
    a = grid(setting="free", rec=(0.20, 0.3), nse=0.60, n=lambda e, u: 19 if (e, u) == (0.5, 0.0) else 20)
    text = reading(pd.DataFrame(a + b))
    assert "Pending: 12 of 12 cells compared, 1 with fewer than 20 paired worlds" in text, text


def test_score6_count():
    flags = pd.Series([1.0] * 4 + [0.0] * 16 + [np.nan] * 2)
    assert count(flags) == "4 of 20 (20%)", count(flags)
    assert count(pd.Series([np.nan])) == "—"


def test_loader():
    s = {"intervention_rel_error_D": 0.3, "intervention_sign_D": 0.9, "nse_drought_D": 0.5}
    assert TR._plain_wide(s) == {"intervention_plain_rel_error_D": 0.3, "intervention_plain_sign_D": 0.9,
                                 "nse_drought_D": 0.5}
    config = {"dials": {"eps": 0.1}, "fits": ["free"], "arms": ["C", "D", "T"], "starts": [0, 1], "steps": 4000,
              "export_release": "r1", "policy": "main", "kernel_weeks": 260, "conv": "fft"}
    old = TR.RESULTS
    with tempfile.TemporaryDirectory() as tmp:
        cell = Path(tmp) / "twin_x" / "e0.1_cell"
        cell.mkdir(parents=True)
        rec = {"world": 0, "dials": {"eps": 0.1}, "realised": {}, "config": config,
               "fits": {"free": {"intervention_rel_error_D": 0.3, "nse_drought_D": 0.5, "nse_drought_T": 0.6,
                                 "recovery_pumping_D": 0.2}}}
        (cell / "world_0.json").write_text(json.dumps(rec))
        TR.RESULTS = Path(tmp)
        try:
            df = TR.load(["twin_x"])
            assert "intervention_plain_rel_error_D" in df and "intervention_rel_error_D" not in df
            (cell / "world_1.json").write_text(json.dumps(rec | {"world": 1, "config": config | {"steps": 3000}}))
            try:
                TR.load(["twin_x"])
            except SystemExit as err:
                assert "must not mix" in str(err)
            else:
                raise AssertionError("a cell mixing settings must stop the report")
        finally:
            TR.RESULTS = old



def test_seed_flag():
    """Shortcut test 2's flag (analysis plan item 22): τ = the 95 % quantile of the grid's seed
    disagreement per arm and setting; detection and false alarms counted per slice cell."""
    rows = []
    for k in range(240):                           # grid: values 0.000 ... 0.239 for arm D, twice for C
        rows.append({"run": "twin_map", "cell": f"g{k % 12}", "world": k, "setting": "free",
                     "seed_disagreement_pumping_D": k / 1000, "seed_disagreement_pumping_C": 2 * k / 1000,
                     "wrong_reasons_D": 0.0, "wrong_reasons_C": 0.0})
    tau = TR.seed_thresholds(pd.DataFrame(rows))
    assert abs(tau[("D", "free")][0] - np.quantile(np.arange(240) / 1000, 0.95)) < 1e-12, tau
    assert tau[("D", "free")][1] == 240 and abs(tau[("C", "free")][0] - 2 * tau[("D", "free")][0]) < 1e-12
    t = tau[("D", "free")][0]                      # 0.22705
    # slice O: 6 worlds with wrong reasons (4 above τ), 14 without (2 above τ)
    for w in range(20):
        wrong = w < 6
        above = (w < 4) or (6 <= w < 8)
        rows.append({"run": "twin_slices", "cell": "sliceO", "world": w, "setting": "free",
                     "seed_disagreement_pumping_D": t + 0.01 if above else t - 0.01,
                     "seed_disagreement_pumping_C": np.nan,
                     "wrong_reasons_D": float(wrong), "wrong_reasons_C": np.nan})
    # slice S: 2 worlds with wrong reasons (both flagged), nothing else -> not estimable
    for w in range(2):
        rows.append({"run": "twin_slices", "cell": "sliceS", "world": w, "setting": "free",
                     "seed_disagreement_pumping_D": t + 0.5, "seed_disagreement_pumping_C": np.nan,
                     "wrong_reasons_D": 1.0, "wrong_reasons_C": np.nan})
    df = pd.DataFrame(rows)
    text = TR.test2_rates(df, TR.seed_thresholds(df))
    line = {tuple(c.strip() for c in r.split("|")[1:5]): r for r in text.splitlines()[2:]}
    o = line[("twin_slices", "sliceO", "free", "D")]
    assert "| 4 of 6 (67%) | 2 of 14 (14%) |" in o, o
    s = line[("twin_slices", "sliceS", "free", "D")]
    assert "| 2 of 2 (not estimable) | 0 of 0 |" in s, s
    g = line[("twin_map", "g0", "free", "D")]      # the grid's own cell: no positive case
    assert "no positive case" in g, g
    assert ("twin_slices", "sliceO", "free", "C") not in line   # C has no evaluable world there
    # the grid's false alarms are 5 % by construction (12 of 240 above the 95 % quantile)
    grid = df[df["run"] == "twin_map"]
    assert int((grid["seed_disagreement_pumping_D"] > t).sum()) == 12
    assert "interim" not in TR.test2_section(df)
    assert "interim: 120 of 240" in TR.test2_section(df[df["world"] < 120])


def _shortcut_fit(recovery_d, nse_d, disagreement, *, recovery_c=0.4, recovery_t=0.4):
    scores = {"wells": 3, "log_rmse_D_over_C": -0.05, "log_rmse_T_over_C": -0.06,
              "log_rmse_D_over_T": 0.01}
    for a, rec, nse, sd, error, sign in zip(
        ("C", "D", "T"), (recovery_c, recovery_d, recovery_t), (0.7, nse_d, 0.75),
        disagreement, (0.8, 0.6, 0.4), (0.7, 0.8, 0.9),
    ):
        scores.update({f"recovery_pumping_{a}": rec, f"nse_drought_{a}": nse,
                       f"seed_disagreement_pumping_{a}": sd, f"intervention_well_rel_error_{a}": error,
                       f"intervention_well_sign_{a}": sign, f"intervention_plain_rel_error_{a}": 0.99})
    return scores


def _write_shortcut_world(root, run, seed, fits, *, variant=None, eps=0.1, realised=None):
    dials = {"eps": eps, "u": 0.3, "pi": 0.3, "nu": 0.25, "timing": "reconstructed", "variant": variant}
    cell = root / run / f"e{eps:g}_u0.3_p0.3_n0.25_rec_{variant or 'base'}"
    cell.mkdir(parents=True, exist_ok=True)
    config = {"dials": dials, "fits": ["free", "pooled:0.1:3000"], "arms": ["C", "D", "T"],
              "starts": [0, 1], "steps": 4000, "export_release": "test", "policy": "main",
              "kernel_weeks": 312, "conv": "fft"}
    protocols = ("free", "pooled_l0.1_fixed3000")
    rec = {"world": seed, "dials": dials, "realised": realised or {}, "config": config,
           "fits": dict(zip(protocols, fits)), "per_well": {p: {"code_bss": ["A", "B", "C"]} for p in protocols},
           "scores_version": 2}
    (cell / f"world_{seed}.json").write_text(json.dumps(rec))


def _write_shortcut_pilot(root, positives):
    for seed in range(900, 903):
        fits = [_shortcut_fit(0.6 if positives and seed in seeds else 0.4, 0.72, (0.2, 0.2, 0.2), recovery_t=0.7)
                for seeds in ((900,), (900, 901))]
        _write_shortcut_world(root, "twin_shortcut_pilot", seed, fits, variant="F1")


def _render_twin(root, *runs):
    out = root / "report.md"
    with patch.multiple(TR, RESULTS=root, OUT=out), patch("sys.argv", ["twin_report", *runs]):
        TR.main()
    return out.read_text()


def test_shortcut_section():
    heading = "## Slice F: the planted shortcut (analysis plan §14 item 23)"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # Base seeds 0, 2 and 4 match F. Seed 19 is grid-only. The other cell contributes to τ.
        for seed, rec, nse, pooled_rec, sd in [(0, 0.1, 0.83, 0.3, 0.1), (2, 0.2, 0.70, 0.1, 0.2),
                                                (4, 0.49, 0.75, 0.2, 0.3), (19, 0.2, 0.90, 0.2, 0.4),
                                                (1, 0.1, 0.90, 0.1, 0.5)]:
            disagreement = (sd, sd + 0.1, sd + 0.2)
            fits = (_shortcut_fit(rec, nse, disagreement),
                    _shortcut_fit(pooled_rec, 0.62, tuple(2 * v for v in disagreement)))
            _write_shortcut_world(root, "twin_map", seed, fits, eps=0.25 if seed == 1 else 0.1)
        _write_shortcut_pilot(root, positives=True)
        rec = (0.6, 0.7, 0.8, 0.9, 1.0, 0.2, 0.3)
        nse = (0.72, 0.75, 0.77, 0.76, 0.71, 0.55, 0.81)
        for seed, (rec_d, nse_d) in enumerate(zip(rec, nse)):
            flag = 2.0 if seed in (0, 1, 2, 3, 5) else 0.0
            fits = (_shortcut_fit(rec_d, nse_d, (flag, flag, flag), recovery_c=0.55 if seed == 0 else 0.4,
                                  recovery_t=0.8 if seed == 2 else 0.4),
                    _shortcut_fit(0.6 if seed in (0, 5) else 0.35, 0.72, (flag, flag, flag)))
            realised = {"far_explained_median_core": 0.1 + seed * 0.01, "far_facilities_median_core": 20 + seed,
                        "far_local_pumping_corr_median_core": 0.8 + seed * 0.01, "core_with_far": 30 + seed % 3}
            _write_shortcut_world(root, "twin_shortcut", seed, fits, variant="F1", realised=realised)

        report = _render_twin(root, "twin_map", "twin_shortcut_pilot", "twin_shortcut")
        assert heading in report
        text = report.split(heading, 1)[1]
        assert "e0.1_u0.3_p0.3_n0.25_rec_F1 (φ = 1)" in text
        assert "| free | 7 | D | 5 of 7 | 0.700 [0.215, 0.985] | 0.750 | 0.600 | 0.800 |" in text
        assert "| free | 7 | C | 1 of 7 |" in text and "| free | 7 | T | 1 of 7 |" in text
        assert "| 0.130 | 23.000 | 0.830 | 31.000 |" in text
        assert "| free | C | 0.480 | 7 | 1 | 1 of 1 (not estimable) | 4 of 6 (67%) |" in text
        assert "| free | D | 0.580 | 7 | 5 | 4 of 5 (80%) | 1 of 2 (50%) |" in text
        assert "| free | T | 0.680 | 7 | 1 | 1 of 1 (not estimable) | 4 of 6 (67%) |" in text
        assert "| pooled_l0.1_fixed3000 | D | 1.160 | 7 | 2 | 2 of 2 (not estimable) | 3 of 5 (60%) |" in text
        assert "pilot has 2 worlds with wrong reasons for arm D (protocol free: 1, pooled_l0.1_fixed3000: 2): " \
               "the 20 worlds use φ = 1.0." in text
        assert "| e0.1_u0.3_p0.3_n0.25_rec_F1 | free | 3 | +0.510 | -0.040 |" in text
        assert "| e0.1_u0.3_p0.3_n0.25_rec_F1 | pooled_l0.1_fixed3000 | 3 | +0.250 | +0.100 |" in text
        assert heading not in _render_twin(root, "twin_map")


def test_shortcut_pilot_without_positives():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_shortcut_pilot(root, positives=False)
        fit = _shortcut_fit(0.4, 0.72, (0.1, 0.2, 0.3))
        _write_shortcut_world(root, "twin_map", 0, (fit, fit))
        fit = _shortcut_fit(0.7, 0.72, (0.3, 0.3, 0.3))
        _write_shortcut_world(root, "twin_shortcut", 0, (fit, fit), variant="F2")
        with patch.object(TR, "RESULTS", root):
            df = TR.load()
        text = TR.shortcut_section(df)
        assert "| free | 3 | D | 0 of 3 |" in text
        assert "| free | D | 0.200 | 3 | 0 | no positive case | 0 of 3 (0%) |" in text
        assert "pilot has no worlds with wrong reasons for arm D (protocol free: 0, pooled_l0.1_fixed3000: 0): " \
               "by the rule, the 20 worlds use φ = 2.0." in text
        assert "e0.1_u0.3_p0.3_n0.25_rec_F2 (φ = 2)" in text
        assert "pilot choice is pending" in TR.shortcut_section(df[df["world"] != 902])
        assert "The pilot has" not in TR.shortcut_section(df[df["run"] != "twin_shortcut_pilot"])


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all twin-reading checks passed")
