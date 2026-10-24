"""Saved models reproduce the predictions they were saved with (third review §7).

    python -m tests.test_checkpoint

No real model is fitted: toy networks on synthetic arrays take one optimiser step (fixed
epochs, a few milliseconds), and a toy LightGBM five rounds. Checks:
1. LSTM and graph runners: the weights handed out by train_seed(state_out=...), saved with
   save_checkpoint and loaded into a fresh network, give the predictions train_seed returned
   (an inference replay: what the post-freeze check of docs/analysis_plan.md §11 needs).
2. LightGBM: a saved booster predicts what the fitted one did.
3. schema.json: the same inputs pass, other inputs stop the run.
4. manifest.json: code hash, dataset version and environment are recorded; a resumed run
   adds its seeds and its session.
"""
import json
import tempfile
from pathlib import Path

import numpy as np
import torch

from src.models import lstm, stgnn
from src.models.manifest import load_checkpoint, save_checkpoint, write_manifest, write_schema


def toy(N=3, T=60, F=5, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(N, T, F)).astype(np.float32)
    Z = (X[:, :, 0] * 0.5 + rng.normal(scale=0.1, size=(N, T))).astype(np.float32)
    split = np.full((N, T), "train", dtype=object)
    split[:, 40:50] = "validation"
    split[:, 50:] = "test"
    core = np.ones((N, T), dtype=bool)
    mu, sd = np.full((N, T), 10.0), np.ones((N, T))
    return X, Z, split, core, mu, sd, mu + sd * Z


def main():
    torch.manual_seed(0)
    X, Z, split, core, mu, sd, head = toy()
    lstm.set_lookback(8)
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        state = {}
        pz, best, ep = lstm.train_seed(0, X, Z, split, core, mu, sd, head, 1, hidden=8,
                                       dropout=0.0, fixed_epochs=1, state_out=state)
        save_checkpoint(out / "seed_0.pt", state, {"seed": 0, "best_epoch": ep})
        ck = load_checkpoint(out / "seed_0.pt")
        net = lstm.Net(X.shape[2], hidden=8, dropout=0.0)
        net.load_state_dict(ck["state_dict"])
        again = lstm.predict_all(net.to(lstm.DEVICE), X)
        assert np.allclose(again, pz, equal_nan=True, atol=1e-6), "LSTM replay differs"
        assert ck["meta"]["best_epoch"] == 1
        print("  1a. LSTM: the saved weights replay the returned predictions")

        A = torch.full((X.shape[0], X.shape[0]), 1.0 / X.shape[0])
        make = lambda F: stgnn.Net(F, A, hidden=8, dropout=0.0)  # noqa: E731
        state = {}
        pz, _, ep = stgnn.train_seed(0, None, X, Z, split, core, mu, sd, head, 1, lookback=8,
                                     fixed_epochs=1, make_net=make, state_out=state)
        save_checkpoint(out / "graph.pt", state, {"seed": 0})
        net = make(X.shape[2])
        net.load_state_dict(load_checkpoint(out / "graph.pt")["state_dict"])
        again = stgnn.predict_all(net.to(stgnn.DEVICE), X, 8)
        assert np.allclose(again, pz, equal_nan=True, atol=1e-6), "graph replay differs"
        print("  1b. graph runner: the saved weights replay the returned predictions")

        import lightgbm as lgb
        rng = np.random.default_rng(1)
        xt, yt = rng.normal(size=(200, 4)), rng.normal(size=200)
        b = lgb.train({"objective": "regression", "verbose": -1, "num_threads": 1},
                      lgb.Dataset(xt, yt), num_boost_round=5)
        b.save_model(str(out / "model_seed_0.txt"))
        b2 = lgb.Booster(model_file=str(out / "model_seed_0.txt"))
        assert np.allclose(b.predict(xt), b2.predict(xt)), "LightGBM replay differs"
        print("  2. LightGBM: the saved booster predicts what the fitted one did")

        sch = {"nodes": ["W1", "W2"], "input_mean": [0.1, 0.2], "lookback": 8}
        write_schema(out, sch)
        write_schema(out, sch)
        try:
            write_schema(out, sch | {"input_mean": [0.1, 0.3]})
            raise AssertionError("a schema with other inputs was accepted")
        except SystemExit:
            pass
        print("  3. schema.json: the same inputs pass, other inputs stop the run")

        m = write_manifest(out, {"hidden": 8}, [0])
        m = write_manifest(out, {"hidden": 8}, [1])
        saved = json.loads((out / "manifest.json").read_text())
        assert saved["seeds_done"] == [0, 1] and len(saved["sessions"]) == 2
        assert len(saved["sessions"][0]["code"]["src_sha256"]) == 64
        assert saved["dataset"]["version"] and "torch" in saved["sessions"][0]["environment"]
        print(f"  4. manifest.json: code {m['sessions'][-1]['code']['src_sha256'][:12]}..., "
              f"dataset {saved['dataset']['version']}, seeds and sessions accumulate")
    print("test_checkpoint: all checks passed")


if __name__ == "__main__":
    main()
