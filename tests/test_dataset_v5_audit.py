"""Small exact checks for the dataset v5 audit (docs/v5_plan.md R1.5, Gate R1).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_dataset_v5_audit

Synthetic cases check differences and conservation without reading or rebuilding
the real dataset. Temporary files check the actual SHA-256 implementation.
"""
import hashlib
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from src.analysis import dataset_v5_audit as A


def test_hashes():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "one.txt").write_bytes(b"abc")
        (root / "two.txt").write_bytes(b"def")
        expected = {"one.txt": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
                    "two.txt": hashlib.sha256(b"def").hexdigest()}
        assert A.hash_files(root) == expected
        (root / "two.txt").write_bytes(b"changed")
        actual = A.hash_files(root)
        assert actual["one.txt"] == expected["one.txt"]
        assert actual["two.txt"] != expected["two.txt"]
    print("  1. two temporary files: exact SHA-256, changed bytes detected")


def test_wells():
    old = pd.DataFrame({"code_bss": ["a", "b"], "core": [True, False], "fold": [0, 1]})
    new = old.iloc[::-1].copy()
    expected = {"wells_identical": True, "v4_wells": 2, "v5_wells": 2, "v4_core": 1, "v5_core": 1,
                "added": [], "removed": [], "core_identical": True, "core_changed": [],
                "fold_identical": True, "fold_changed": []}
    assert A.compare_wells(old, new) == expected
    new.loc[new["code_bss"] == "a", "fold"] = 1
    expected.update(fold_identical=False, fold_changed=["a"])
    assert A.compare_wells(old, new) == expected
    new.loc[new["code_bss"] == "b", "core"] = True
    expected.update(core_identical=False, core_changed=["b"], v5_core=2)
    assert A.compare_wells(old, new) == expected
    print("  2. row order ignored; relabelled fold and changed core flag detected exactly")


def test_heads():
    old = pd.DataFrame({"code_bss": ["a"] * 4,
                        "week": pd.to_datetime(["2022-01-02", "2023-01-01", "2023-01-08", "2023-01-15"]),
                        "head": [0.0, 1.0, 0.0, 8.0]})
    new = old.iloc[:3].copy()
    new["head"] = [0.001, 1.002, 0.0005]
    expected = pd.DataFrame({"year": [2022, 2023], "common": [1, 2], "changed": [0, 1],
                             "not_comparable": [0, 0]})
    pd.testing.assert_frame_equal(A.compare_heads(old, new), expected)
    print("  3. heads: exact 1 mm excluded; 2 mm counted in 2023; unshared row excluded")


def test_forcing():
    old = pd.DataFrame({"cell_id": ["a", "a", "b"],
                        "week": pd.to_datetime(["2022-12-25", "2023-01-01", "2023-01-01"]),
                        "rain": [1.0, 2.0, 3.0], "ETP": [2.0, 4.0, 6.0]})
    new = old.iloc[::-1].copy()
    expected = pd.DataFrame([
        {"period": period, "variable": variable, "common": n, "not_comparable": 0,
         "changed": 0, "max_abs_delta": 0.0, "mean_abs_delta": 0.0}
        for period, n in (("before 2023", 1), ("2023 onward", 2)) for variable in ("rain", "ETP")])
    pd.testing.assert_frame_equal(A.compare_forcing(old, new), expected)
    new.loc[new["cell_id"] == "b", "rain"] = 7.0
    expected.loc[2, ["changed", "max_abs_delta", "mean_abs_delta"]] = [1, 4.0, 2.0]
    pd.testing.assert_frame_equal(A.compare_forcing(old, new), expected)
    print("  4. identical forcing block; exact post-2023 max/mean differences")


def test_splits():
    heads = pd.DataFrame({"code_bss": ["a", "a", "b", "a", "a", "a"],
                          "week": pd.to_datetime(["2019-12-29"] * 3 + ["2020-01-05", "2022-05-01", "2022-05-08"]),
                          "share_not_validated": [0.0, 0.5, 1.0, 0.25, 1.0, 0.0]})
    wells = pd.DataFrame({"code_bss": ["a", "b"], "core": [True, False]})
    splits = {"train": ["2005-01-01", "2019-12-31"], "validation": ["2020-01-01", "2022-04-30"],
              "test": ["2022-05-01", "2022-05-01"]}
    result = A.split_summary(heads, wells, splits)
    assert result["core_well_weeks"].tolist() == [2, 1, 1]
    assert result["share_not_validated"].tolist() == [0.25, 0.25, 1.0]
    print("  5. split bounds and core-only weekly mean unvalidated shares")


def test_canals():
    weeks = pd.to_datetime(["2025-01-05", "2026-01-04"])
    pumping = pd.DataFrame({"code_ouvrage": ["a", "b", "a", "b", "outside", "gw"],
                            "usage": ["irrigation", "canals"] * 3,
                            "week": [weeks[0]] * 2 + [weeks[1]] * 4,
                            "volume_m3": [1e6, 3e6, 2e6, 4e6, 1e8, 1e8],
                            "imputed": [False, True, True, False, True, True]})
    points = pd.DataFrame({"code_ouvrage": ["a", "b", "outside", "gw"],
                          "zone": ["plain", "plain", "outside", "plain"],
                          "source": ["surface", "surface", "surface", "groundwater"]})
    intakes = pd.DataFrame({"code_ouvrage": ["a", "b"], "basin": ["Tet", "Tet"]})
    weekly = pd.DataFrame({"week": list(weeks) * 2, "basin": ["Tet"] * 2 + ["unknown"] * 2,
                          "volume_m3": [4e6, 6e6, 0.0, 0.0]})
    annual, check = A.canal_summary(weekly, intakes, pumping, points)
    assert check == {"passed": True, "weeks": 2, "same_weeks": True, "finite": True,
                     "max_abs_delta_m3": 0.0, "missing_weeks": 0, "extra_weeks": 0,
                     "max_basin_allocation_delta_m3": 0.0}
    tet = annual[annual["basin"] == "Tet"].set_index("year")
    assert tet.loc[2025, "volume_Mm3"] == 4.0 and tet.loc[2025, "imputed_share"] == 0.75
    assert tet.loc[2026, "volume_Mm3"] == 6.0 and tet.loc[2026, "imputed_share"] == 1 / 3
    assert len(annual) == 30 and pd.isna(tet.loc[2012, "imputed_share"])
    assert not A.conservation(pd.Series([0.0], index=weeks[:1]), pd.Series([0.0, 0.0], index=weeks))["passed"]
    assert not A.conservation(pd.Series([1.0, 2.0], index=weeks), pd.Series([1.0, 3.0], index=weeks))["passed"]
    print("  6. basin annual volumes and imputed volume shares; missing/unequal weeks fail")


def test_diagnosis_and_guard():
    assert "Only built changed" in A.diagnose_change("meta.json", b'{"built":"a"}', b'{"built":"b"}')
    frame = pd.DataFrame({"value": [1.0, 2.0]})
    left, right = io.BytesIO(), io.BytesIO()
    frame.to_parquet(left, index=False)
    frame.iloc[::-1].reset_index(drop=True).to_parquet(right, index=False)
    assert "Row order only" in A.diagnose_change("table.parquet", left.getvalue(), right.getvalue())
    with patch.object(Path, "is_file", return_value=False), patch.object(A.subprocess, "run") as run:
        try:
            A.rebuild_audit(Path("unused"))
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("Must wait for T65")
        run.assert_not_called()
    print("  7. date/row-order diagnoses; missing T65 report blocks rebuild before subprocess")


if __name__ == "__main__":
    test_hashes()
    test_wells()
    test_heads()
    test_forcing()
    test_splits()
    test_canals()
    test_diagnosis_and_guard()
    print("test_dataset_v5_audit: all checks passed")
