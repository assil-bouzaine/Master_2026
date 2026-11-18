"""Check the Phase 4 report with hand-made effects and saved development runs.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_arms_report
"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
import pandas as pd

from src.analysis import arms_report as A, ladder_report, stats
from src.models.evaluate import RESULTS


def test_classification():
    band = A.union_band((-0.025, 0.01), (-0.015, 0.02))
    assert band == ((-0.025, 0.02),)
    assert A.classify(-0.06, (-0.08, -0.03), band, 0.01) == A.DETECTED
    assert A.classify(0.03, (0.01, 0.04), band, 0.01) == A.SMALL
    assert A.classify(0.005, (-0.01, 0.02), band, 0.8) == A.NO_EFFECT
    assert A.classify(0.03, (-0.03, 0.08), band, 0.2) == A.UNDECIDED
    assert A.classify(0.06, (0, 0.08), band, 0.01) == A.UNDECIDED
    assert A.classify(0.02, (0.01, 0.07), band, 0.01) == A.UNDECIDED
    assert A.classify(0.05, (0.01, 0.07), band, 0.01) == A.DETECTED
    assert A.classify(0.08, (0.05, 0.12), band, 0.05) == A.UNDECIDED
    assert A.classify(0.01, (-0.05, 0.05), band, 0.8) == A.UNDECIDED
    assert A.classify(0.08, (0.05, 0.12), None, 0.01) == A.UNDECIDED
    assert A.classify(0.08, (0.05, np.nan), band, 0.01) == A.UNDECIDED
    disjoint = A.union_band((-0.06, -0.04), (0.1, 0.15))
    assert A.classify(0.08, (0.02, 0.09), disjoint, 0.01) == A.DETECTED
    print("  1. All four classifications and the exact interval, band, alpha and effect boundaries agree.")


def table(marker):
    return pd.DataFrame([{"code_bss": "w", "task": "simulation", "split": "test_drought", "variant": "all",
                          "core": True, "NSE": 0.5, "skill": 0.5, "KGE": 0.3, "RMSE": 0.6}]).assign(run=marker)


class MemoryRuns:
    wells = None

    def metrics(self, run, regime):
        return None if run == "B_r2_lwo" else table(run)

    def band(self, run, regime, metrics):
        return (-0.01, 0.01), 10

    def coverage(self, run, regime):
        return "pumping 10"


def test_holm_and_missing():
    config = {"smallest_effect": 0.05, "alpha": 0.05, "regimes": ["", "_lwo"], "reconstructions": [1, 2],
              "families": {"family 1": [{"name": name, "a": name + "_r1", "b": "ref_r1", "coverage": name == "A"}
                                        for name in "AB"],
                           "family 2": [{"name": name, "a": name + "_r1", "b": "ref_r1"} for name in "CD"]},
              "controls": [], "exploratory": []}
    p = {"A": 0.01, "B": 0.04, "C": 0.02, "D": 0.03}

    def contrast(ma, mb, wells):
        name = ma["run"].iloc[0]
        return {A.EFFECT: -0.09, "interval": (-0.15, -0.03), "p_cluster": p[name[0]] + (0.01 if "_r2" in name else 0),
                "share of wells a better": 0.7, "support mismatch": 0}

    with patch.object(A.ladder, "contrast", side_effect=contrast), patch.object(A.stats, "paired") as paired:
        report = A.compute(config, MemoryRuns())
    assert all(call.kwargs["strict"] for call in paired.call_args_list)
    assert paired.call_count == 15
    assert report["missing"] == ["B_r2_lwo"]
    for family, names in (("family 1", "AB"), ("family 2", "CD")):
        for regime in config["regimes"]:
            for recon in config["reconstructions"]:
                rows = [r for r in report["families"] if (r["family"], r["regime"], r["reconstruction"])
                        == (family, regime, recon)]
                want_names = "A" if (family, regime, recon) == ("family 1", "_lwo", 2) else names
                assert "".join(row["name"] for row in rows) == want_names
                np.testing.assert_array_equal([row["p_holm"] for row in rows],
                                              stats.holm([p[name] + (0.01 if recon == 2 else 0) for name in want_names]))
    rendered = A.render(config, report)
    assert all(word in rendered for word in ("confirmatory", "robustness", "pumping 10", "B_r2_lwo"))
    print("  2. Holm matches the independent family/cell calls and drops the one listed missing run.")


def test_draws():
    rows = [{A.EFFECT: d, "band_a": (-0.04, 0.04)} for d in (-0.15, 0.05, -0.04)]
    stats_ = A.aggregate_draws(rows)
    assert stats_["n"] == 3 and stats_["range"] == (-0.15, 0.05)
    np.testing.assert_allclose([stats_["median"], stats_["width"], stats_["ratio"]], [-0.04, 0.08, 2.5])
    assert A.aggregate_draws(rows[:1])["ratio"] == 0
    assert np.isnan(A.aggregate_draws([{A.EFFECT: 0.2, "band_a": (0.0, 0.0)}])["ratio"])
    print("  3. The draw median, range and ratio to D's band agree with the hand calculation.")


def test_reconstructions():
    rows = [{"reconstruction": r, "classification": label, A.EFFECT: effect}
            for r, label, effect in [(1, A.DETECTED, -0.07), (2, A.SMALL, -0.04), (3, A.DETECTED, -0.09)]]
    assert A.reconstruction_agreement(rows, [1, 2, 3]).startswith("Yes.")
    disagree = A.reconstruction_agreement([*rows[:2], rows[2] | {A.EFFECT: 0.09}], [1, 2, 3])
    assert disagree.startswith("Depends") and "(3)" in disagree and "favours b" in disagree
    assert A.reconstruction_agreement(rows[:2], [1, 2, 3]) == "Incomplete. Missing 3"
    same_class = [row | {"classification": A.NO_EFFECT} for row in rows]
    assert A.reconstruction_agreement(same_class, [1, 2, 3]).startswith("Yes.")
    print("  4. Reconstruction agreement follows detection direction or the shared non-detected class.")


def test_soft_selection():
    class SoftRuns:
        def __init__(self):
            self.calls = []

        def metrics(self, run, regime):
            self.calls.append((run, regime))
            if "100" in run:
                return None
            validation = 0.6 if "soft1_" in run else 0.8
            return pd.concat([table(run).assign(NSE=1 - validation),
                              table(run).assign(split="validation", NSE=validation)])

    runs, missing = SoftRuns(), set()
    template = "p4_B4_D_soft{best}_r1"
    picked, scores = A._select_soft(runs, template, 2, [1, 10], missing)
    assert picked == 10 and len(scores) == 2 and not missing
    assert runs.calls == [("p4_B4_D_soft1_r2", ""), ("p4_B4_D_soft10_r2", "")]
    picked, _ = A._select_soft(runs, template, 2, [1, 10, 100], missing)
    assert picked is None and missing == {"p4_B4_D_soft100_r2"}
    print("  5a. The soft setting uses core R1 validation, and an incomplete grid stays pending.")


def test_seed_layout():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        runs = A.SavedRuns(root)
        runs.splits = {"leave_wells_out": {"n_folds": 2, "fold_of_well": {"A": 0, "B": 1}}}
        cache = root / "_cache"
        cache.mkdir()
        scale = pd.DataFrame({"code_bss": ["A", "B"], "mu": [10.0, 20.0], "sd": [2.0, 3.0]})
        scale.to_parquet(cache / "panel.parquet", index=False)
        scale.assign(mu=[30.0, 40.0]).to_parquet(cache / "panel_f25.parquet", index=False)
        z = pd.DataFrame({"code_bss": ["A", "B"], "week": pd.Timestamp("2024-01-07"), "z": 1.0})
        for fold in (0, 1):
            out = root / "toy_lwo" / f"fold_{fold}"
            out.mkdir(parents=True)
            z.assign(z=fold + 1.0).to_parquet(out / "seed_0.parquet", index=False)
            (out / "schema.json").write_text(json.dumps({"wells_with_relation": {"pumping": {"wells": 2 - fold}}}))
        out = root / "toy_f25"
        out.mkdir()
        z.to_parquet(out / "seed_0.parquet", index=False)
        assert runs.frames("toy_lwo", "_lwo")[0].set_index("code_bss")["pred"].to_dict() == {"A": 12, "B": 26}
        with patch.object(A, "score", side_effect=lambda pred: pred):
            assert runs.metrics("toy_lwo", "_lwo").set_index("code_bss")["pred"].to_dict() == {"A": 12, "B": 26}
        assert runs.frames("toy_f25", "_f25")[0].set_index("code_bss")["pred"].to_dict() == {"A": 32, "B": 43}
        assert runs.coverage("toy_lwo", "_lwo") == "fold 0: pumping 2<br>fold 1: pumping 1"
    print("  5b. R2 pools held-out wells once and R3 reads the shortened-window scale.")


def test_smoke():
    config = json.loads(A.DEV_CONFIG.read_text())
    runs = A.SavedRuns()
    report = A.compute(config, runs)
    assert not report["missing"] and len(report["families"]) == 2
    row = report["families"][0]
    ma, mb = [pd.read_csv(RESULTS / name / "metrics_per_well.csv") for name in (row["a"], row["b"])]
    expected = ladder_report.contrast(ma, mb, runs.wells)
    for key, value in expected.items():
        np.testing.assert_allclose(row[key], value, rtol=0, atol=1e-12)
    wrong = ma.copy()
    index = wrong.index[wrong["split"].eq("test_drought") & wrong["variant"].eq("all") & wrong["core"]][0]
    code = wrong.at[index, "code_bss"]
    wrong.at[index, "support"] = "different weeks"
    with patch.object(runs, "metrics", side_effect=[wrong, mb]):
        try:
            A._compare(runs, config["families"]["dev"][0], row["a"], row["b"], "", 1, set(), family="dev")
        except ValueError as error:
            assert row["a"] in str(error) and code in str(error)
        else:
            raise AssertionError("strict support accepted different well-weeks")
    assert row["starts_a"] == row["starts_b"] == 10 and row["union"] is not None
    assert report["controls"][0]["n"] == 2
    text = A.render(config, report, development=True)
    # Exercise the CLI's development path using the same computed result.
    with patch.object(A, "compute", return_value=report):
        A.main(["--config", str(A.DEV_CONFIG)])
    assert (RESULTS / "_arms_dev.md").read_text() == text
    assert "Development only" in text and "confirmatory" not in text
    print(f"  5c. Development report matches ladder_report.contrast (median {row[A.EFFECT]:.6f}).")


def main():
    test_classification()
    test_holm_and_missing()
    test_draws()
    test_reconstructions()
    test_soft_selection()
    test_seed_layout()
    test_smoke()
    print("test_arms_report: all checks passed")


if __name__ == "__main__":
    main()
