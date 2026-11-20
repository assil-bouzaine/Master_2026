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
from src.models.response import SD_FLOOR


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


class MemoryRuns(A.SavedRuns):
    wells = None

    def __init__(self, missing="B_r2_lwo"):
        super().__init__()
        self.missing = missing

    def metrics(self, run, regime):
        return None if run == self.missing else table(run)

    def band(self, run, regime, metrics):
        return (-0.01, 0.01), tuple(range(10))

    def coverage(self, run, regime):
        return "pumping 10"


def test_holm_and_missing():
    config = {"smallest_effect": 0.05, "alpha": 0.05, "regimes": ["", "_lwo"], "reconstructions": [1, 2],
              "families": {"family 1": [{"name": name, "a": name + "_r1", "b": "ref_r1", "coverage": name == "A"}
                                        for name in "AB"],
                           "family 2": [{"name": name, "a": name + "_r1", "b": "ref_r1"} for name in "CD"]},
              "controls": [], "exploratory": []}
    p = {"A": 0.02, "B": 0.39, "C": 0.02, "D": 0.03}

    def contrast(ma, mb, wells):
        name = ma["run"].iloc[0]
        return {A.EFFECT: -0.09, "interval": (-0.15, -0.03), "p_cluster": p[name[0]] + (0.01 if "_r2" in name else 0),
                "share of wells a better": 0.7, "support mismatch": 0}

    with patch.object(A.ladder, "contrast", side_effect=contrast), patch.object(A.stats, "paired") as paired:
        report = A.compute(config, MemoryRuns())
        assert all(call.kwargs["strict"] for call in paired.call_args_list)
        assert paired.call_count == 15
        complete = A.compute(config, MemoryRuns(missing=None))
    assert report["missing"] == ["B_r2_lwo"]
    for family, names in (("family 1", "AB"), ("family 2", "CD")):
        for regime in config["regimes"]:
            for recon in config["reconstructions"]:
                rows = [r for r in report["families"] if (r["family"], r["regime"], r["reconstruction"])
                        == (family, regime, recon)]
                assert "".join(row["name"] for row in rows) == names
                if (family, regime, recon) == ("family 1", "_lwo", 2):
                    available, missing = rows
                    np.testing.assert_allclose(available["p_cluster"], 0.030)
                    assert A.classify(available[A.EFFECT], available["interval"], available["union"],
                                      available["p_cluster"]) == A.DETECTED
                    assert all(row["classification"] is None and row["p_holm"] is None for row in rows)
                    assert all(row["pending"] == "pending: family incomplete, 1 of 2 tests" for row in rows)
                    assert missing["p_cluster"] is None and missing["p_holm_interim"] is None
                    np.testing.assert_allclose(available["p_holm_interim"], stats.holm([0.030, 1])[0])
                    continue
                np.testing.assert_array_equal([row["p_holm"] for row in rows],
                                              stats.holm([p[name] + (0.01 if recon == 2 else 0) for name in names]))
    done_a, done_b = [r for r in complete["families"] if (r["family"], r["regime"], r["reconstruction"])
                      == ("family 1", "_lwo", 2)]
    np.testing.assert_allclose([done_a["p_holm"], done_b["p_cluster"]], [0.060, 0.40])
    assert done_a["classification"] == A.UNDECIDED and done_a["p_holm_interim"] is None
    rendered = A.render(config, report)
    assert all(word in rendered for word in ("confirmatory", "robustness", "pumping 10", "B_r2_lwo"))
    assert "0.06<br>interim (family incomplete)" in rendered
    assert "pending: family incomplete, 1 of 2 tests" in rendered
    print("  2. A raw p of 0.030 gives interim Holm p 0.060 while pending, then final p 0.060 and undecided.")


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
    assert A.reconstruction_agreement(rows[:2], [1, 2, 3]).startswith("Pending.")
    pending = rows[2] | {"classification": None, "pending": "pending: family incomplete, 1 of 2 tests"}
    assert A.reconstruction_agreement([*rows[:2], pending], [1, 2, 3]).startswith("Pending.")
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


def write_seeds(folder, data, offset=0):
    folder.mkdir(parents=True)
    for seed in range(10):
        data.assign(z=offset + float(seed)).to_parquet(folder / f"seed_{seed}.parquet", index=False)


def test_declared_seeds():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        cache = root / "_cache"
        cache.mkdir()
        pd.DataFrame({"code_bss": ["A", "B"], "mu": [10.0, 20.0], "sd": [1e-13, 2.0]}).to_parquet(
            cache / "panel.parquet", index=False)
        weeks = pd.date_range("2024-01-07", periods=26, freq="W-SUN")
        data = pd.MultiIndex.from_product([["A", "B"], weeks], names=["code_bss", "week"]).to_frame(index=False)
        run, reference = "p4_fixture", "p4_reference"
        write_seeds(root / run, data)
        write_seeds(root / reference, data, offset=1)
        stale = data.assign(pred=data["code_bss"].map({"A": 10.0, "B": 20.0}), task="simulation", horizon=0)
        stale.to_parquet(root / run / "predictions.parquet", index=False)
        (root / run / "metrics_per_well.csv").write_text("stale\n")

        runs = A.SavedRuns(root)
        assert runs.seed_frames(root / run, "")[1].iloc[0]["pred"] == 10.0 + SD_FLOOR
        with patch.object(A, "score", side_effect=lambda pred: pred) as score:
            prediction = runs.metrics(run, "")
        score.assert_called_once()
        np.testing.assert_allclose(prediction.loc[prediction["code_bss"] == "A", "pred"], 10.0 + SD_FLOOR * 4.5)
        np.testing.assert_allclose(prediction.loc[prediction["code_bss"] == "B", "pred"], 29.0)
        assert (prediction["pred"].to_numpy() != stale["pred"].to_numpy()).all()
        assert runs.aggregate_seeds[run, ""] == tuple(range(10))

        spec = {"name": "fixture vs reference", "a": run, "b": reference}
        config = {"smallest_effect": 0.05, "alpha": 0.05, "regimes": [""], "reconstructions": [1],
                  "families": {"fixture": [spec]}, "exploratory": [spec], "controls": [spec]}
        effects = {A.EFFECT: -0.09, "interval": (-0.15, -0.03), "p_cluster": 0.03,
                   "share of wells a better": 0.7, "support mismatch": 0}
        runs = A.SavedRuns(root)
        runs.observed = pd.DataFrame({"A": 1.0}, index=weeks)
        bands = []

        def band(frames, obs, wells, rng):
            bands.append(tuple(sorted(frames)))
            return -0.01, 0.01, 0.01

        with (patch.object(A, "score", return_value=table(run).assign(code_bss="A")),
              patch.object(A.stats, "paired"), patch.object(A.ladder, "contrast", return_value=effects),
              patch.object(A.ladder, "band", side_effect=band)):
            report = A.compute(config, runs)
            for row in [*report["families"], *report["exploratory"], *report["controls"][0]["rows"]]:
                for arm in ("a", "b"):
                    assert row[f"aggregate_seeds_{arm}"] == row[f"band_seeds_{arm}"] == tuple(range(10))
            assert bands == [tuple(range(10))] * 2
            assert report["families"][0]["classification"] == A.DETECTED
            with patch.object(runs, "band", return_value=((-0.01, 0.01), tuple(range(1, 11)))):
                try:
                    A.compute(config, runs)
                except AssertionError as error:
                    assert "declared seed IDs" in str(error)
                else:
                    raise AssertionError("Classification accepted different band seeds")

        seed_7 = root / run / "seed_7.parquet"
        seed = pd.read_parquet(seed_7)
        seed_7.unlink()
        with patch.object(A, "score", return_value=table(reference)) as score:
            report = A.compute(config, A.SavedRuns(root))
        score.assert_called_once()  # Only the complete reference was scored.
        assert set(report["pending"][run][run]) == {f"seed_{s}" for s in range(10) if s != 7}
        assert report["families"][0]["classification"] is None
        assert not report["exploratory"] and report["controls"][0]["n"] == 0
        assert f"`{run}` · seeds found: seed_0" in A.render(config, report)
        seed.to_parquet(seed_7, index=False)
        seed.to_parquet(root / run / "seed_10.parquet", index=False)
        runs = A.SavedRuns(root)
        with patch.object(A, "score") as score:
            assert runs.metrics(run, "") is None
        score.assert_not_called()
        assert "seed_10" in runs.pending[run][run]

        folded = "p4_fixture_lwo"
        for fold in (0, 1):
            write_seeds(root / folded / f"fold_{fold}", data, offset=fold)
        splits = {"leave_wells_out": {"n_folds": 2, "fold_of_well": {"A": 0, "B": 1}}}
        runs = A.SavedRuns(root)
        runs.splits = splits
        with patch.object(A, "score", side_effect=lambda pred: pred):
            prediction = runs.metrics(folded, "_lwo")
        np.testing.assert_allclose(prediction.loc[prediction["code_bss"] == "A", "pred"], 10.0 + SD_FLOOR * 4.5)
        np.testing.assert_allclose(prediction.loc[prediction["code_bss"] == "B", "pred"], 31.0)
        fold_1 = root / folded / "fold_1"
        (fold_1 / "seed_7.parquet").rename(fold_1 / "seed_10.parquet")
        runs = A.SavedRuns(root)
        runs.splits = splits
        with patch.object(A, "score") as score:
            assert runs.metrics(folded, "_lwo") is None
        score.assert_not_called()
        assert "seed_7" in runs.pending[folded]["fold_0"]
        assert "seed_7" not in runs.pending[folded]["fold_1"] and "seed_10" in runs.pending[folded]["fold_1"]
    print("  5c. Phase 4 checks the exact seeds per fold, ignores stale aggregates and decodes with SD_FLOOR.")


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
    with (TemporaryDirectory() as tmp, patch.object(A, "RESULTS", Path(tmp)),
          patch.object(A, "compute", return_value=report)):
        A.main(["--config", str(A.DEV_CONFIG)])
        assert (Path(tmp) / "_arms_dev.md").read_text() == text
    assert "Development only" in text and "confirmatory" not in text
    print(f"  5d. Development report matches ladder_report.contrast (median {row[A.EFFECT]:.6f}).")


def main():
    test_classification()
    test_holm_and_missing()
    test_draws()
    test_reconstructions()
    test_soft_selection()
    test_seed_layout()
    test_declared_seeds()
    test_smoke()
    print("test_arms_report: all checks passed")


if __name__ == "__main__":
    main()
