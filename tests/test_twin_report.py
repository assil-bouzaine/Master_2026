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
5. (f) The RQ2 table appears when hard and soft/none settings exist for the base cell.
"""
import numpy as np
import pandas as pd

from src.analysis.twin_report import reading


def world_rows(cell, setting, d_over_c, rec_d, rec_c, nse_d, n=20, spread=0.01, seed=0, **extra):
    # deterministic worlds: D / C spread evenly around its median (97.5 % quantile ≈ median + 1.9 spread)
    offsets = spread * np.linspace(-2.0, 2.0, n)
    e, u = cell
    rows = []
    for w in range(n):
        rows.append({"run": "twin_map", "cell": f"e{e:g}_u{u:g}_p0.3_n0.25_rec_base", "world": w,
                     "setting": setting, "dial_eps": e, "dial_u": u, "dial_pi": 0.3, "dial_nu": 0.25,
                     "dial_timing": "reconstructed", "dial_variant": np.nan,
                     "log_rmse_D_over_C": d_over_c + offsets[w],
                     "log_rmse_D_over_T": 0.01, "recovery_pumping_D": rec_d, "recovery_pumping_C": rec_c,
                     "nse_drought_D": nse_d, **extra})
    return rows


def grid(d_over_c=lambda e, u: -0.1, rec=(0.2, 0.3), nse=0.6, setting="free", spread=0.01):
    rows = []
    for e in (0.0, 0.1, 0.25, 0.5):
        for u in (0.0, 0.3, 0.6):
            rows += world_rows((e, u), setting, d_over_c(e, u), *rec, nse, spread=spread,
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
                           intervention_sign_D=0.8)
    text = reading(pd.DataFrame(rows))
    assert "(f) RQ2" in text and "free_soft1" in text and "free_none" in text


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all twin-reading checks passed")
