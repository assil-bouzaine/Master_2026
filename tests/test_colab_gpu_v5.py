"""Check GPU pre-step selection for extraction sessions (v5 plan R2.1) offline.

All runner calls are stubbed: no installs, Colab calls or model fits take place.
    PYTHONIOENCODING=utf-8 PFE_DATASET=v5 .venv/bin/python -m tests.test_colab_gpu_v5
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts import colab_run as runner


def test_pre_step_tests():
    cases = {"extract": [], "setup extract": [], "setup": [], "": [],
             "taccari": ["tests.test_taccari"],
             "extract chronos2": ["tests.test_taccari"],
             "ealstm": ["tests.test_taccari", "tests.test_ealstm"],
             "extract final:ealstm regimes:ealstm": ["tests.test_taccari", "tests.test_ealstm"]}
    for steps, expected in cases.items():
        assert runner.pre_step_tests(steps) == expected, steps
    print(f"  1. {len(cases)} step lists select only the required model tests.")


def test_runner(root):
    """Check extraction logging and keep the existing model-check failure behavior."""
    cases = [("extract", None, "extract"), ("setup extract", None, "setup extract"),
             ("taccari", None, "taccari"), ("extract chronos2", None, "extract chronos2"),
             ("ealstm", None, "ealstm"), ("extract ealstm", "tests.test_ealstm", "extract"),
             ("ealstm", "tests.test_ealstm", "none"), ("taccari", "tests.test_taccari", None)]
    for index, (steps, failure, expected_steps) in enumerate(cases):
        local = root / str(index) / "results_gpu"

        def run(command, env):
            return int(command[-1] == failure)

        with (patch.multiple(runner, STEPS=steps, DRIVE=root / "drive", DATASET="v5", LOCAL=local,
                             SAVED=root / "saved", LOG=local / "run_colab.log"),
              patch.object(runner.sys, "argv", ["colab_run.py"]),
              patch.object(runner, "gpu", return_value="fixture GPU"),
              patch.object(runner, "copy_new", return_value=0),
              patch.object(runner, "run", side_effect=run) as execute,
              patch.object(runner.threading, "Thread") as thread):
            try:
                runner.main()
            except SystemExit as error:
                assert failure == "tests.test_taccari" and "stopping" in str(error)
            else:
                assert expected_steps is not None
            calls = execute.call_args_list
            assert calls[0].args[0] == ["bash", "scripts/run_gpu.sh"]
            assert calls[0].args[1]["STEPS"] == "setup"
            checked = [call.args[0][-1] for call in calls if call.args[0][:2] == ["python3", "-m"]]
            assert checked == runner.pre_step_tests(steps)
            if expected_steps is None:
                thread.assert_not_called()
            else:
                assert calls[-1].args[0] == ["bash", "scripts/run_gpu.sh"]
                assert calls[-1].args[1]["STEPS"] == expected_steps
                assert calls[-1].args[1]["SKIP_PIP"] == "1"
            text = (local / "run_colab.log").read_text()
            assert ("No pre-step tests" in text) == (not runner.pre_step_tests(steps))
    print(f"  2. {len(cases)} stubbed sessions preserve test failures and log why extraction skips model checks.")


def main():
    test_pre_step_tests()
    with TemporaryDirectory(prefix="test_colab_gpu_v5_") as folder:
        test_runner(Path(folder))
    print("test_colab_gpu_v5: all checks passed")


if __name__ == "__main__":
    main()
