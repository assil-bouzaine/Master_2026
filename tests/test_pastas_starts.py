"""Starting values of the Pastas stability check (src.models.pastas_baseline.perturb).

    python -m tests.test_pastas_starts

No model is solved (no fitting on the laptop): a pastas_seasonal_canal model is built on
synthetic series and only its initial values are drawn. Checks that every drawn value
stays inside the bounds, that the draws change with the start and with the well, and that
the same (start, well) gives the same values.
"""
import numpy as np
import pandas as pd

from src.models.pastas_baseline import build_model, perturb


def model():
    days = pd.date_range("2005-01-01", "2019-12-31", freq="D")
    rng = np.random.default_rng(0)
    prec = pd.Series(rng.gamma(0.3, 0.005, len(days)), days)          # m/d
    evap = pd.Series(0.002 + 0.001 * np.sin(np.arange(len(days)) / 58.0), days)
    pump = pd.Series(1000.0 + 500.0 * rng.random(len(days)), days)     # m3/d
    canal = pd.Series(0.1 * rng.random(len(days)), days)
    weeks = pd.date_range("2012-01-01", "2019-12-31", freq="W-SUN")
    obs = pd.Series(50.0 + rng.normal(0.0, 1.0, len(weeks)), weeks)
    return build_model("X", "pastas_seasonal_canal", obs, prec, evap, pump, canal, False), obs


def drawn(start, code="X"):
    ml, obs = model()
    perturb(ml, code, start, obs)
    return ml.parameters


def test_bounds_and_reproducibility():
    default = model()[0].parameters
    a = drawn(1)
    vary = default["vary"].astype(bool)
    for name in default.index[vary]:
        lo, hi, x = default.loc[name, "pmin"], default.loc[name, "pmax"], a.loc[name, "initial"]
        assert (pd.isna(lo) or x > lo) and (pd.isna(hi) or x < hi), (name, lo, x, hi)
    assert (a["initial"] == drawn(1)["initial"]).all(), "same start and well, other values"
    assert not (a["initial"][vary] == default["initial"][vary]).all(), "start 1 changed nothing"
    assert not (a["initial"][vary] == drawn(2)["initial"][vary]).all(), "starts 1 and 2 equal"
    assert not (a["initial"][vary] == drawn(1, "Y")["initial"][vary]).all(), "wells X and Y equal"
    assert (a.loc[~vary, "initial"] == default.loc[~vary, "initial"]).all(), "fixed value moved"
    moved = (a["initial"][vary] != default["initial"][vary]).sum()
    print(f"start 1: {moved} of {vary.sum()} free parameters drawn, all inside their bounds")


if __name__ == "__main__":
    test_bounds_and_reproducibility()
    print("ok")
