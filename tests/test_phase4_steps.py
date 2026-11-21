"""Check the Phase 4 dispatcher against its declared runs (analysis plan §14, items 18 and 20).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_phase4_steps
"""
from collections import Counter
from itertools import takewhile
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

from src.analysis import arms_report as A

ROOT = Path(__file__).resolve().parents[1]
STEPS = ("p4_B1", "p4_B1c", "p4_B2", "p4_B2conv", "p4_B3", "p4_B4", "p4_B5", "p4_B6", "p4_B7", "p4_B8")


def dry_run(steps, **settings):
    env = {key: value for key, value in os.environ.items() if not key.startswith("P4_") and key != "STATUS_FILE"}
    env.update(P4_DRYRUN="1", P4_CONFIRMED="1", STEPS=" ".join(steps), PY=sys.executable)
    env.update(settings)
    return subprocess.run(["bash", "scripts/run_v4_cpu.sh"], cwd=ROOT, env=env, text=True,
                          capture_output=True, timeout=60)


def commands(result):
    assert result.returncode == 0, (result.stdout, result.stderr)
    fits, assemblies = [], []
    for line in result.stdout.splitlines():
        if line.startswith("== "):
            continue
        args = shlex.split(line)
        if args[1:3] == ["-m", "src.models.response"]:
            fits.append(args)
        else:
            assert args[1] == "-c" and "assemble_lwo(sys.argv[1]" in args[2], line
            assemblies.append(args[3])
    return fits, assemblies


def flag(cmd, name):
    return [cmd[i + 1] for i, arg in enumerate(cmd) if arg == name][-1]


def seeds(cmd):
    return list(takewhile(lambda arg: not arg.startswith("--"), cmd[cmd.index("--seeds") + 1:]))


def declared_runs(config):
    specs = [spec for family in config["families"].values() for spec in family]
    specs += config["controls"] + config["exploratory"]
    runs = set()
    for spec in specs:
        for regime, recon in A._cases(config, spec):
            for stem in (spec["a"], spec["b"]):
                choices = config["soft_candidates"] if "{best}" in stem else [None]
                for best in choices:
                    for draw in spec.get("draws", [None]):
                        runs.add(A._run_name(stem.format(best=best, d=draw), regime, recon))
    assert len(config["explanations"]) == 3
    for recon, entry in zip(config["reconstructions"], config["explanations"]):
        assert entry["regimes"] == [""] and entry["reconstructions"] == [recon]
        assert entry["protocol"] == "pooled_l0.1_fixed3000"
        assert (entry["a"], entry["b"]) == (f"p4_B2conv_D_r{recon}", f"p4_B2conv_C_r{recon}")
        runs.update((entry["a"], entry["b"]))
    return runs


def test_explanations():
    fits, assemblies = commands(dry_run(("p4_B2conv",)))
    assert len(fits) == 6 and not assemblies
    names = {flag(cmd, "--run") for cmd in fits}
    assert names == {f"p4_B2conv_{arm}_r{recon}" for arm in "CD" for recon in (1, 2, 3)}
    for cmd in fits:
        name = flag(cmd, "--run")
        assert flag(cmd, "--arm") == name.split("_")[2]
        assert flag(cmd, "--pumping-reconstruction") == name[-1]
        assert flag(cmd, "--mode") == "pooled" and flag(cmd, "--lam") == "0.1"
        assert flag(cmd, "--fixed-steps") == "3000" and flag(cmd, "--recharge") == "linear"
        assert all(arg not in cmd for arg in ("--fold", "--train-start", "--refit-from"))

    fits, assemblies = commands(dry_run(("p4_B2conv",), P4_OVERRIDE="1", P4_MODE="shared", P4_LAM="9",
                                        P4_FIXED="12", P4_RECHARGE="pe", P4_RECONS="2", P4_SEEDS="4 7",
                                        P4_RUNG4_STATICS="B"))
    assert len(fits) == 2 and not assemblies
    for cmd in fits:
        assert flag(cmd, "--run").endswith("_r2") and flag(cmd, "--pumping-reconstruction") == "2"
        assert flag(cmd, "--mode") == "pooled" and flag(cmd, "--lam") == "0.1"
        assert flag(cmd, "--fixed-steps") == "3000" and flag(cmd, "--recharge") == "pe"
        assert flag(cmd, "--statics") == "B" and seeds(cmd) == ["4", "7"]
    print("  1. Six R1 explanation fits use the converged protocol, including under overrides.")


def test_full_plan():
    fits, assemblies = commands(dry_run(STEPS))
    runs = declared_runs(json.loads(A.CONFIG.read_text()))
    expected_fits = {(name, str(fold)) for name in runs if name.endswith("_lwo") for fold in range(5)}
    expected_fits.update((name, None) for name in runs if not name.endswith("_lwo"))
    fit_ids = [(flag(cmd, "--run"), flag(cmd, "--fold") if "--fold" in cmd else None) for cmd in fits]
    counts = Counter(name.split("_")[1] for name, _ in fit_ids)
    assert counts == {"B1": 54, "B1c": 18, "B2": 54, "B2conv": 6, "B3": 96, "B4": 90, "B5": 28, "B6": 24, "B7": 4, "B8": 4}
    assert len(fit_ids) == 378 and set(fit_ids) == expected_fits
    assert len(assemblies) == 51 and set(assemblies) == {name for name in runs if name.endswith("_lwo")}

    b7 = []
    for cmd in fits:
        name = flag(cmd, "--run")
        assert flag(cmd, "--conv") == "fft"
        assert seeds(cmd) == [str(k) for k in range(10)]
        # the signs Gate 3 approved (item 23): every fit; RQ2's none and soft keep their slots and reference
        signs = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "--signs"]
        if name.startswith("p4_B4_D_none_") or name.startswith("p4_B4_D_soft"):
            assert signs == ["gate3", "none"] and flag(cmd, "--sign-ref") == "gate3", name
        else:
            assert signs == ["gate3"] and "--sign-ref" not in cmd, name
        if name.startswith("p4_B2conv_"):
            continue
        assert flag(cmd, "--mode") == "pooled" and flag(cmd, "--lam") == "0.01" and "--fixed-steps" not in cmd
        if name.startswith("p4_B7_"):
            assert flag(cmd, "--arm") == "D" and flag(cmd, "--pumping-reconstruction") == "1"
            b7.append((name, flag(cmd, "--recharge")))
            if name == "p4_B7_D_unitwide_r1":
                assert flag(cmd, "--recharge-relation") == "recharge_unitwide"
        else:
            assert flag(cmd, "--recharge") == "linear"
    assert b7 == [("p4_B7_D_unitwide_r1", "linear"), ("p4_B7_D_drainage_r1", "drainc"), ("p4_B7_D_pe_r1", "pe"),
                  ("p4_B7_D_canalsoft_r1", "linear")]
    # B8 (Gate 3 point 20): every row has the seasonal residual, nothing else does
    for cmd in fits:
        assert (flag(cmd, "--residual") == "seasonal") == flag(cmd, "--run").startswith("p4_B8_") \
            if "--residual" in cmd else not flag(cmd, "--run").startswith("p4_B8_"), flag(cmd, "--run")
    canal = [cmd for cmd in fits if flag(cmd, "--run") == "p4_B7_D_canalsoft_r1"][0]
    assert flag(canal, "--soft") == "10" and flag(canal, "--soft-stresses") == "canal"
    print(f"  2. {len(fits)} declared fits across {len(runs)} run IDs and {len(assemblies)} fold assemblies. {dict(counts)}")


def test_guard():
    for key, value in (("P4_MODE", "shared"), ("P4_LAM", "0.1"), ("P4_LAM", ""),
                       ("P4_FIXED", "3000"), ("P4_RECHARGE", "pe")):
        result = dry_run(("p4_B7",), **{key: value})
        assert result.returncode == 1 and key in result.stderr and "P4_OVERRIDE=1" in result.stderr
        assert "src.models.response" not in result.stdout
    fits, _ = commands(dry_run(("p4_B7",), P4_MODE="pooled", P4_LAM="0.01", P4_FIXED="", P4_RECHARGE="linear"))
    assert len(fits) == 4
    fits, _ = commands(dry_run(("p4_B7",), P4_LAM="0.1", P4_OVERRIDE="1"))
    assert len(fits) == 4 and all(flag(cmd, "--lam") == "0.1" for cmd in fits)
    locked = dry_run(("p4_B2conv",), P4_CONFIRMED="0", P4_LAM="0.1")
    assert locked.returncode == 0 and "Phase 4 is locked" in locked.stdout and not locked.stderr
    assert "src.models.response" not in locked.stdout
    print("  3. The four declared defaults are guarded, the override works and the confirmation lock comes first.")


def main():
    test_explanations()
    test_full_plan()
    test_guard()
    print("test_phase4_steps: all checks passed")


if __name__ == "__main__":
    main()
