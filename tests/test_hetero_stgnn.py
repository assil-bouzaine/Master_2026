"""Unit tests for the black-box Hetero-STGNN competitor (analysis plan v3 §6, T95).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v5 .venv/bin/python -m tests.test_hetero_stgnn

Runs on a tiny synthetic fixture (6 wells, 10 facilities, 4 weather cells, 2 gauges, 1 canal,
2 aquifer units, 120 weeks) with at most a 3-epoch toy fit. No real-data training happens here.

Checks:
1. Causality through the entire network (temporal encoders + 2 HeteroConv layers + decoder):
   perturbing any dynamic node input at week t leaves all outputs before t unchanged to 0.0
   exactly, while outputs at/after t move; dilations match exact receptive fields {52, 104, 156};
   TemporalGraphConv sparse aggregation equals naive PyG message passing; chunked checkpointed
   TemporalEncoder matches unchunked outputs and gradients.
2. Dynamic input rules: training-window-only standardisation (validation/test edits never alter
   training inputs), facility pre-record weeks take each facility's training mean with imputed=1,
   gauge missing weeks take 0 with missing=1, wells carry season sin/cos only (no head/stress),
   aquifer units have no dynamic input.
3. Held-out well isolation: changing held-out wells' heads (to +/-1e6 or NaN) leaves the masked
   loss and every parameter gradient bit-for-bit identical; placeholder weeks are masked identically.
4. Training guard: both hetero_stgnn.main and tune_hstgnn.main refuse without PFE_ALLOW_TRAIN=1.
5. 3-epoch toy fit, predictions.parquet schema matching hybrid_gnn, replay (< 1e-5 m), and
   config lock refusing a changed hyperparameter on the same run folder.
6. Tuner (tune_hstgnn): 24-trial search space, 3-seed re-selection, resumable cache (mocked fits).
7. GPU runner syntax (`bash -n scripts/run_gpu.sh`), stubbed `hstgnn_tune` and `hstgnn` steps
   (including R2 folds + assembly and default 10 seeds), and `make_gpu_bundle.bundle_files()`.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch

import numpy as np
import optuna
from optuna.trial import TrialState
import pandas as pd
import torch

from src.config import ROOT
from src.models import hetero_graph as HG
from src.models import hetero_stgnn as S
from src.models import tune_hstgnn as T
from src.models.lstm import save_seed, save_seed_model, seed_mean_predictions, write_config
from src.models.manifest import write_manifest, write_schema


# ---------------------------------------------------------------------------
# Tiny synthetic fixture: 6 wells, 10 facilities, 4 cells, 2 gauges, 1 canal,
# 2 aquifer units, 120 weeks.
# ---------------------------------------------------------------------------

def _synthetic_fixture(seed: int = 2026):
    """Build synthetic export tables, weekly tables, HeteroData, dynamic inputs, and panel targets."""
    rng = np.random.default_rng(seed)
    n_wells, n_fac, n_cells, n_gauges, n_canals, n_units = 6, 10, 4, 2, 1, 2
    n_weeks = 120
    # 2009-07-05..2009-12-27 (26 warmup), 2010 (52 train), 2011 (28 val + 14 test).
    weeks = pd.date_range("2009-07-05", periods=n_weeks, freq="W-SUN")
    train_start, train_end = weeks[26], weeks[77]   # exact calendar year 2010 (52 weeks)

    well_codes = [f"W{i}" for i in range(n_wells)]
    fac_codes = [f"F{i}" for i in range(n_fac)]
    cell_codes = [f"C{i}" for i in range(n_cells)]
    gauge_codes = [f"G{i}" for i in range(n_gauges)]
    canal_codes = ["canal:Tet"]
    unit_codes = [f"U{i}" for i in range(n_units)]

    node_rows = []
    nid = 0
    for c in well_codes:
        node_rows.append({"node_id": nid, "type": "well", "code": c, "unit_type": None})
        nid += 1
    for c in fac_codes:
        node_rows.append({"node_id": nid, "type": "facility", "code": c, "unit_type": None})
        nid += 1
    for c in cell_codes:
        node_rows.append({"node_id": nid, "type": "weather_cell", "code": c, "unit_type": None})
        nid += 1
    for c in gauge_codes:
        node_rows.append({"node_id": nid, "type": "gauge", "code": c, "unit_type": None})
        nid += 1
    for c in canal_codes:
        node_rows.append({"node_id": nid, "type": "canal", "code": c, "unit_type": None})
        nid += 1
    unit_types = ["alluvial_aquifer", "multilayer_aquifer_system"]
    for c, ut in zip(unit_codes, unit_types):
        node_rows.append({"node_id": nid, "type": "aquifer_unit", "code": c, "unit_type": ut})
        nid += 1
    nodes_df = pd.DataFrame(node_rows)

    edge_rows = []

    def add_edge(rel, st, src, dst, w, dist=1000.0, sign="PositiveResponse", elig=True, cons=True, assoc=""):
        edge_rows.append({
            "relation": rel, "src_type": st, "src": src, "dst": dst,
            "weight": w, "distance_m": dist, "sign": sign,
            "eligible": elig, "constrained": cons, "association_types": assoc,
        })

    for i, w in enumerate(well_codes):
        add_edge("recharge", "weather_cell", cell_codes[i % n_cells], w, 0.7)
        add_edge("recharge_leakage", "weather_cell", cell_codes[(i + 1) % n_cells], w, 0.3)
        add_edge("pumping", "facility", fac_codes[i % n_fac], w, 0.8, 1200.0, "NegativeResponse")
        add_edge("pumping_unattributed", "facility", fac_codes[(i + 4) % n_fac], w, 0.4, 2400.0, "NegativeResponse")
        add_edge("river", "gauge", gauge_codes[i % n_gauges], w, 1.0, 800.0, "PositiveResponse", True, True, "OnOutcrop")
        add_edge("canal", "canal", canal_codes[0], w, 1.0, np.nan, "PositiveResponse", i == 0, i == 0)
        add_edge("monitors", "aquifer_unit", unit_codes[i % n_units], w, 1.0, np.nan, None, None, None)
        add_edge("well_link", "well", well_codes[(i + 1) % n_wells], w, 0.5, 1500.0, None, None, None)
    add_edge("overlies", "aquifer_unit", unit_codes[0], unit_codes[1], 1.0, np.nan, None, None, None)
    edges_df = pd.DataFrame(edge_rows)

    wells_df = pd.DataFrame({
        "code_bss": well_codes,
        "profondeur_investigation": np.linspace(12.0, 95.0, n_wells),
        "altitude_station": np.linspace(10.0, 60.0, n_wells),
        "pos_in_stack": [1.0, 2.0, 1.0, 2.0, 1.0, 2.0],
        "pct_days_artesian": np.linspace(0.0, 0.3, n_wells),
        "pct_days_artesian_f25": np.linspace(0.0, 0.3, n_wells),
        "pct_days_artesian_f50": np.linspace(0.0, 0.3, n_wells),
        "core": [True] * n_wells,
        "group": ["recent alluvium", "Pliocene multilayer"] * 3,
    })

    # Weather forcing for all 120 weeks.
    f_rows = []
    for c in cell_codes:
        rain = rng.gamma(1.2, 12.0, n_weeks)
        etp = 15.0 + 10.0 * np.sin(np.linspace(0, 4 * np.pi, n_weeks)) + rng.uniform(0, 3, n_weeks)
        pe = np.maximum(rain - etp, 0.0)
        f_rows.append(pd.DataFrame({"cell_id": c, "week": weeks, "rain": rain, "ETP": etp, "PE": pe}))
    forcing_df = pd.concat(f_rows, ignore_index=True)

    # Pumping record starts at week 20 (weeks 0..19 are pre-record -> facility training mean, imputed=1).
    pump_weeks = weeks[20:]
    pts_df = pd.DataFrame({
        "code_ouvrage": fac_codes + ["CAN0"],
        "source": ["groundwater"] * n_fac + ["surface"],
        "cell_id": [cell_codes[i % n_cells] for i in range(n_fac)] + [cell_codes[0]],
        "zone": ["plain"] * (n_fac + 1),
    })
    p_rows = []
    for i, fcode in enumerate(fac_codes):
        usage = "drinking water" if i % 2 == 0 else "irrigation"
        base = 500.0 * (i + 1)
        vols = base + rng.uniform(0.0, 200.0, len(pump_weeks))
        imp = np.array([wk < weeks[40] for wk in pump_weeks], dtype=bool)
        p_rows.append(pd.DataFrame({
            "code_ouvrage": fcode, "usage": usage, "week": pump_weeks,
            "volume_m3": vols, "imputed": imp,
        }))
    # Surface canal intake row for plain fallback.
    p_rows.append(pd.DataFrame({
        "code_ouvrage": "CAN0", "usage": "canals", "week": pump_weeks,
        "volume_m3": 1e5 + rng.uniform(0.0, 5e4, len(pump_weeks)), "imputed": False,
    }))
    pumping_df = pd.concat(p_rows, ignore_index=True)

    # Rivers: start at week 15, plus an internal gap at weeks 50..54 for G0.
    r_rows = []
    for g_idx, gcode in enumerate(gauge_codes):
        for w_idx in range(15, n_weeks):
            if g_idx == 0 and 50 <= w_idx <= 54:
                continue
            r_rows.append({"code_station": gcode, "week": weeks[w_idx], "q_m3s": float(rng.gamma(2.0, 4.0))})
    rivers_df = pd.DataFrame(r_rows)

    # Canal basins: start at week 20.
    canal_df = pd.DataFrame({
        "week": pump_weeks,
        "basin": "Tet",
        "volume_m3": 2e5 + rng.uniform(0.0, 1e5, len(pump_weeks)),
    })

    tables = {
        "nodes": nodes_df,
        "edges": edges_df,
        "static_edges": edges_df,
        "wells": wells_df,
        "forcing_weekly": forcing_df,
        "pumping_weekly": pumping_df,
        "pumping_points": pts_df,
        "rivers_weekly": rivers_df,
        "canal_basins_weekly": canal_df,
        "train_window": (train_start, train_end),
    }

    with patch.object(HG.statics, "training_window", return_value=(train_start, train_end, None)):
        graph_data, graph_index = HG.build_heterodata(Path("/nonexistent"), "D", tables=tables)

    x_dyn, dyn_cols, dyn_stats = S.build_dynamic_inputs(graph_data, graph_index, weeks, tables=tables)

    # Synthetic heads driven smoothly by weather + season + per-well baseline so a 3-epoch fit learns.
    rain_sig = x_dyn["weather_cell"][:, :, 0]
    t_grid = np.linspace(0.0, 6.0 * np.pi, n_weeks)
    head = np.zeros((n_wells, n_weeks), dtype=np.float64)
    for i in range(n_wells):
        smooth = pd.Series(rain_sig[i % n_cells]).rolling(8, min_periods=1).mean().to_numpy()
        head[i] = 20.0 + 3.0 * i + 1.2 * smooth + 0.6 * np.sin(t_grid + 0.3 * i) + rng.normal(0, 0.05, n_weeks)

    split_1d = np.array(
        ["warmup"] * 26 + ["train"] * 52 + ["validation"] * 28 + ["test"] * 14, dtype=object
    )
    split = np.broadcast_to(split_1d[None, :], (n_wells, n_weeks)).copy()
    tr_mask = split == "train"
    mu_1d = np.array([head[i, tr_mask[i]].mean() for i in range(n_wells)])
    sd_1d = np.maximum(np.array([head[i, tr_mask[i]].std(ddof=1) for i in range(n_wells)]), S.SD_FLOOR)
    mu = np.repeat(mu_1d[:, None], n_weeks, axis=1)
    sd = np.repeat(sd_1d[:, None], n_weeks, axis=1)

    data = {
        "codes": well_codes,
        "weeks": weeks.to_numpy(),
        "x_dyn": x_dyn,
        "head": head,
        "mu": mu,
        "sd": sd,
        "split": split,
        "core": np.ones((n_wells, n_weeks), dtype=bool),
        "placeholder_mask": np.zeros((n_wells, n_weeks), dtype=bool),
    }

    # Panel DataFrame matching seed_mean_predictions' expected columns.
    panel_rows = []
    for i, code in enumerate(well_codes):
        panel_rows.append(pd.DataFrame({
            "code_bss": code, "week": weeks, "mu": mu_1d[i], "sd": sd_1d[i],
            "head": head[i], "split": split_1d, "core": True,
        }))
    P = pd.concat(panel_rows, ignore_index=True)

    return {
        "tables": tables,
        "graph_data": graph_data,
        "graph_index": graph_index,
        "data": data,
        "P": P,
        "weeks": weeks,
        "dyn_cols": dyn_cols,
        "dyn_stats": dyn_stats,
        "train_window": (train_start, train_end),
    }


# ---------------------------------------------------------------------------
# 1. Causality, dilation schedule, TemporalGraphConv & chunking equivalence
# ---------------------------------------------------------------------------

def test_causality_and_architecture():
    # Exact receptive fields with zero holes.
    for rf in (8, 16, 52, 104, 156):
        dils = S.dilations_for_receptive_field(rf)
        assert S.receptive_field_of(dils) == rf, (rf, dils)
        covered = 1
        for d in dils:
            assert d <= covered, f"hole in dilation schedule {dils} for rf={rf}"
            covered += d

    fix = _synthetic_fixture(seed=101)
    gd = fix["graph_data"]
    x_dyn = {k: torch.from_numpy(v.copy()) for k, v in fix["data"]["x_dyn"].items()}
    dyn_dims = {k: int(v.shape[-1]) for k, v in x_dyn.items()}

    torch.manual_seed(11)
    net = S.HeteroSTGNN.from_heterodata(gd, dynamic_dims=dyn_dims, hidden=16, receptive_field=52, dropout=0.0)
    net.eval()

    with torch.no_grad():
        y_base = net(x_dyn, gd)
    assert y_base.shape == (6, 120)

    t0 = 60
    # Perturb each dynamic node type individually at week t0 and also all together.
    targets = list(x_dyn.keys()) + ["ALL"]
    for which in targets:
        x_pert = {k: v.clone() for k, v in x_dyn.items()}
        if which == "ALL":
            for k in x_pert:
                x_pert[k][:, t0, :] += 5.0
        else:
            x_pert[which][:, t0, :] += 5.0
        with torch.no_grad():
            y_pert = net(x_pert, gd)
        before_diff = float((y_pert[:, :t0] - y_base[:, :t0]).abs().max().item())
        after_diff = float((y_pert[:, t0:] - y_base[:, t0:]).abs().max().item())
        assert before_diff == 0.0, f"causality violated for {which}: max diff before t0 = {before_diff}"
        assert after_diff > 1e-5, f"perturbation of {which} at t0 had no effect on weeks >= t0"

    # TemporalGraphConv sparse path equals explicit message-passing propagate().
    torch.manual_seed(12)
    conv = S.TemporalGraphConv((8, 8), 8, aggr="add", node_dim=0)
    x_src = torch.randn(5, 12, 8, requires_grad=True)
    x_dst = torch.randn(4, 12, 8, requires_grad=True)
    ei = torch.tensor([[0, 1, 2, 3, 4, 1], [0, 0, 1, 2, 3, 0]], dtype=torch.long)
    ew = torch.tensor([0.3, 0.7, 1.2, 0.5, 0.9, 0.4], dtype=torch.float32)
    out_sparse = conv((x_src, x_dst), ei, edge_weight=ew)
    # Naive GraphConv propagate with 3D message()
    agg_naive = conv.propagate(ei, x=(x_src, x_dst), edge_weight=ew, size=(5, 4))
    out_naive = conv.lin_rel(agg_naive) + conv.lin_root(x_dst)
    conv_err = float((out_sparse - out_naive).abs().max().item())
    assert conv_err < 1e-5, f"TemporalGraphConv sparse vs naive mismatch: {conv_err}"

    # Chunked checkpointed TemporalEncoder matches unchunked outputs and gradients.
    torch.manual_seed(13)
    enc_full = S.TemporalEncoder(in_dyn=2, in_stat=3, hidden=8, receptive_field=16, dropout=0.0, chunk_size=100)
    enc_chunk = S.TemporalEncoder(in_dyn=2, in_stat=3, hidden=8, receptive_field=16, dropout=0.0, chunk_size=3)
    enc_chunk.load_state_dict(enc_full.state_dict())
    xd = torch.randn(10, 30, 2)
    xs = torch.randn(10, 3)
    enc_full.train()
    enc_chunk.train()
    o1 = enc_full(xd, xs)
    o1.mean().backward()
    o2 = enc_chunk(xd, xs)
    o2.mean().backward()
    assert torch.allclose(o1, o2, atol=1e-5, rtol=1e-5)
    for (n1, p1), (n2, p2) in zip(enc_full.named_parameters(), enc_chunk.named_parameters()):
        assert n1 == n2
        assert torch.allclose(p1.grad, p2.grad, atol=1e-5, rtol=1e-5), (n1, (p1.grad - p2.grad).abs().max().item())

    print(f"  1. causality & architecture: 0.0 exact diff before t={t0} for every node type; "
          f"TemporalGraphConv err {conv_err:.1e}; chunked checkpointed TCN matches unchunked")


# ---------------------------------------------------------------------------
# 2. Dynamic input rules (pre-record, missing, training-window standardisation)
# ---------------------------------------------------------------------------

def test_dynamic_inputs():
    fix = _synthetic_fixture(seed=102)
    x_dyn = fix["data"]["x_dyn"]
    weeks = fix["weeks"]
    t_start, t_end = fix["train_window"]
    tr_mask = np.asarray((weeks >= t_start) & (weeks <= t_end), dtype=bool)

    assert "aquifer_unit" not in x_dyn, "aquifer_unit must not have dynamic inputs"
    assert x_dyn["well"].shape == (6, 120, 2)
    assert fix["dyn_cols"]["well"] == ["season_sin", "season_cos"]
    assert x_dyn["weather_cell"].shape == (4, 120, 3)
    assert x_dyn["facility"].shape == (10, 120, 2)
    assert x_dyn["gauge"].shape == (2, 120, 2)
    assert x_dyn["canal"].shape == (1, 120, 1)

    # Facility pre-record weeks (0..19): imputed == 1.0, volume == facility's training mean (standardised).
    fac = x_dyn["facility"]
    assert np.all(fac[:, :20, 1] == 1.0), "pre-record facility weeks must have imputed=1"
    for i in range(fac.shape[0]):
        tr_mean = float(fac[i, tr_mask, 0].mean())
        assert np.allclose(fac[i, :20, 0], tr_mean, atol=1e-5), f"facility {i} pre-record != training mean"

    # Gauge missing weeks (0..14 and G0 weeks 50..54): value == 0.0, missing == 1.0.
    gauge = x_dyn["gauge"]
    assert np.all(gauge[:, :15, 0] == 0.0) and np.all(gauge[:, :15, 1] == 1.0)
    assert np.all(gauge[0, 50:55, 0] == 0.0) and np.all(gauge[0, 50:55, 1] == 1.0)
    assert np.all(gauge[1, 50:55, 1] == 0.0)

    # Standardisation uses training window only: perturbing post-train weeks leaves train inputs untouched.
    tables2 = {k: (v.copy() if isinstance(v, pd.DataFrame) else v) for k, v in fix["tables"].items()}
    post = tables2["forcing_weekly"]["week"] > t_end
    tables2["forcing_weekly"].loc[post, "rain"] += 500.0
    post_r = tables2["rivers_weekly"]["week"] > t_end
    tables2["rivers_weekly"].loc[post_r, "q_m3s"] += 500.0
    x_dyn2, _, stats2 = S.build_dynamic_inputs(fix["graph_data"], fix["graph_index"], weeks, tables=tables2)
    assert stats2 == fix["dyn_stats"], "post-training data changed training standardisation stats"
    for nt in ("weather_cell", "gauge", "facility", "canal", "well"):
        assert np.array_equal(x_dyn[nt][:, tr_mask, :], x_dyn2[nt][:, tr_mask, :]), nt

    print("  2. dynamic inputs: pre-record facility mean + imputed=1, gauge missing=0/1, "
          "training-window-only standardisation, no dynamic input on aquifer_unit")


# ---------------------------------------------------------------------------
# 3. Held-out well isolation (loss & gradients identical)
# ---------------------------------------------------------------------------

def test_held_out_well_isolation():
    fix = _synthetic_fixture(seed=103)
    gd = fix["graph_data"]
    data = fix["data"]
    x_dyn = {k: torch.from_numpy(v.copy()) for k, v in data["x_dyn"].items()}
    dyn_dims = {k: int(v.shape[-1]) for k, v in x_dyn.items()}

    torch.manual_seed(21)
    net = S.HeteroSTGNN.from_heterodata(gd, dynamic_dims=dyn_dims, hidden=16, receptive_field=52, dropout=0.0)
    net.train()

    keep_wells = np.array([True, True, True, True, False, False], dtype=bool)
    placeholder = np.zeros_like(data["placeholder_mask"])
    placeholder[0, 30:35] = True  # also verify placeholder weeks never enter loss
    obs_loss = np.isfinite(data["head"]) & (data["split"] == "train") & keep_wells[:, None] & ~placeholder
    sd_safe = np.maximum(data["sd"], S.SD_FLOOR)

    def run_grad(head_arr):
        net.zero_grad()
        y_hat = net(x_dyn, gd)
        loss = S.masked_mse_loss(y_hat, head_arr, data["mu"], sd_safe, obs_loss)
        loss.backward()
        grads = {name: p.grad.detach().clone() for name, p in net.named_parameters() if p.grad is not None}
        return float(loss.detach().item()), grads

    loss1, grads1 = run_grad(data["head"])

    # Corrupt held-out wells' heads AND placeholder weeks wildly (including NaN).
    head_bad = data["head"].copy()
    head_bad[4, :] = 1e6
    head_bad[5, :] = np.nan
    head_bad[0, 30:35] = -1e6
    loss2, grads2 = run_grad(head_bad)

    assert loss1 == loss2, f"held-out/placeholder heads changed loss: {loss1} vs {loss2}"
    assert set(grads1) == set(grads2) and len(grads1) > 0
    for name in grads1:
        assert torch.equal(grads1[name], grads2[name]), f"gradient changed for {name}"

    print(f"  3. held-out isolation: loss ({loss1:.6f}) and all {len(grads1)} parameter gradients "
          f"bit-for-bit identical under +/-1e6 and NaN on held-out wells & placeholders")


# ---------------------------------------------------------------------------
# 4. Training guard refuses without PFE_ALLOW_TRAIN=1
# ---------------------------------------------------------------------------

def test_training_guard():
    for val in (None, "0", ""):
        env = {k: v for k, v in os.environ.items() if k != S.ALLOW_TRAIN_ENV}
        if val is not None:
            env[S.ALLOW_TRAIN_ENV] = val
        with (
            patch.dict(os.environ, env, clear=True),
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
        ):
            for fn, argv in (
                (S.main, ["--arm", "D", "--epochs", "1", "--seeds", "0"]),
                (T.main, ["--arm", "D", "--trials", "1"]),
            ):
                try:
                    fn(argv)
                except SystemExit as exc:
                    assert S.ALLOW_TRAIN_ENV in str(exc), str(exc)
                else:
                    raise AssertionError(f"{fn.__module__} ran without {S.ALLOW_TRAIN_ENV}=1 (val={val!r})")
    print(f"  4. training guard: hetero_stgnn and tune_hstgnn refuse without {S.ALLOW_TRAIN_ENV}=1")


# ---------------------------------------------------------------------------
# 5. 3-epoch toy fit, predictions.parquet schema, replay (< 1e-5 m), config lock
# ---------------------------------------------------------------------------

def test_toy_fit_replay_and_config_lock():
    fix = _synthetic_fixture(seed=105)
    gd = fix["graph_data"]
    data = fix["data"]
    P = fix["P"]
    dyn_dims = {k: int(v.shape[-1]) for k, v in data["x_dyn"].items()}

    state = {}
    net, val_nse, n_ep, losses = S.train_seed(
        seed=0,
        data=data,
        graph_data=gd,
        epochs=3,
        lr=1e-2,
        weight_decay=1e-4,
        hidden=16,
        receptive_field=52,
        dropout=0.0,
        device="cpu",
        state_out=state,
        verbose=False,
    )
    assert n_ep == 3 and len(losses) == 3
    assert losses[-1] < losses[0], f"3-epoch toy fit did not lower training loss: {losses}"

    pz = S.predict_seed(net, data, gd, device="cpu")
    assert pz.shape == (6, 120) and np.isfinite(pz).all()

    with TemporaryDirectory() as tmp:
        out = Path(tmp) / "hstgnn_toy"
        out.mkdir()
        args = S.build_parser().parse_args([
            "--arm", "D", "--hidden", "16", "--receptive-field", "52",
            "--dropout", "0.0", "--epochs", "3", "--lr", "0.01", "--seeds", "0", "--run", "hstgnn_toy",
        ])
        inputs = [f"{nt}:{c}" for nt in sorted(fix["dyn_cols"]) for c in fix["dyn_cols"][nt]]
        fp = write_config(out, args, inputs, {"model": "hetero_stgnn"})
        write_schema(out, {"model": "hetero_stgnn", "nodes": data["codes"], "inputs": inputs})
        save_seed_model(out, 0, state, val_nse, n_ep, fp)
        save_seed(out / "seed_0.parquet", pz, data["codes"], data["weeks"], val_nse, n_ep, fp)
        write_manifest(out, vars(args) | {"fingerprint": fp}, [0])

        pred, n_seeds = seed_mean_predictions(out, P.assign(sd=P["sd"].clip(lower=S.SD_FLOOR)), [0])
        pred_path = out / "predictions.parquet"
        pred.to_parquet(pred_path, index=False)
        saved = pd.read_parquet(pred_path)
        assert list(saved.columns) == ["code_bss", "week", "pred", "pred_seed_sd", "task", "horizon"]
        assert n_seeds == 1 and len(saved) == 6 * 120
        assert (saved["task"] == "simulation").all() and (saved["horizon"] == 0).all()
        assert np.isfinite(saved["pred"]).all()

        # Replay reproduces predictions to < 1e-5 m.
        prep_stub = {
            "data": data,
            "graph_data": gd,
            "model_kwargs": {
                "dynamic_dims": dyn_dims,
                "well_graph_idx": None,
                "hidden": 16,
                "receptive_field": 52,
                "dropout": 0.0,
                "n_spatial_layers": S.N_SPATIAL_LAYERS,
            },
        }
        replayed = S.replay(out, 0, prep=prep_stub, device="cpu")
        merged = saved.merge(replayed, on=["code_bss", "week"], suffixes=("_saved", "_replay"))
        assert len(merged) == len(saved)
        max_err = float(np.abs(merged["pred_saved"] - merged["pred_replay"]).max())
        assert max_err < 1e-5, f"replay error {max_err} >= 1e-5 m"

        # Config lock refuses a changed setting on the same run folder.
        changed = S.build_parser().parse_args([
            "--arm", "D", "--hidden", "32", "--receptive-field", "52",
            "--dropout", "0.0", "--epochs", "3", "--lr", "0.01", "--seeds", "0", "--run", "hstgnn_toy",
        ])
        try:
            write_config(out, changed, inputs, {"model": "hetero_stgnn"})
        except SystemExit as exc:
            assert "other settings" in str(exc)
        else:
            raise AssertionError("config lock accepted a changed setting")

    print(f"  5. 3-epoch toy fit & replay: loss {losses[0]:.4f} -> {losses[-1]:.4f}; "
          f"predictions.parquet columns ok; replay max err {max_err:.2e} m (< 1e-5); config lock ok")


# ---------------------------------------------------------------------------
# 6. Tuner (tune_hstgnn): 24-trial search space, 3-seed re-selection, resume
# ---------------------------------------------------------------------------

def test_tuner_mocked():
    calls = []

    def fake_prepare(args, *, verbose=False):
        assert verbose is False
        return {
            "data": {}, "graph_data": "fake", "well_graph_idx": None,
            "train_mask": None, "keep_wells": None,
        }

    def hand_score(hidden, rf, epochs, lr, seed):
        base = hidden / 64.0 + rf / 156.0 + epochs / 800.0 + lr
        # Seed 0 rewards large base; seeds 1 & 2 invert it so re-selection must change the winner.
        return base if seed == 0 else 4.0 - base

    def fake_train(seed, data, graph_data, well_graph_idx, **kwargs):
        calls.append((seed, kwargs["hidden"], kwargs["receptive_field"], kwargs["epochs"]))
        val = hand_score(kwargs["hidden"], kwargs["receptive_field"], kwargs["epochs"], kwargs["lr"], seed)
        return object(), val, kwargs["epochs"], []

    with (
        TemporaryDirectory() as tmp,
        patch.dict(os.environ, {S.ALLOW_TRAIN_ENV: "1"}),
        patch.object(T, "RESULTS_DIR", Path(tmp)),
        patch.object(S, "prepare", side_effect=fake_prepare),
        patch.object(S, "train_seed", side_effect=fake_train),
        redirect_stdout(io.StringIO()),
    ):
        args = T.build_parser().parse_args(["--arm", "D"])
        assert args.trials == 24
        best = T.run(args)
        out = Path(tmp) / "hstgnn_D_tuning"
        study = T.open_study(out, "D")
        assert len(study.trials) == 24
        assert all(t.state == TrialState.COMPLETE for t in study.trials)
        for tr in study.trials:
            p = tr.params
            assert set(p) == {"hidden", "receptive_field", "lr", "weight_decay", "dropout", "epochs"}
            assert p["hidden"] in (16, 32, 64)
            assert p["receptive_field"] in (52, 104, 156)
            assert 1e-3 <= p["lr"] <= 1e-2 and tr.distributions["lr"].log
            assert 1e-5 <= p["weight_decay"] <= 1e-2 and tr.distributions["weight_decay"].log
            assert 0.0 <= p["dropout"] <= 0.3 and not tr.distributions["dropout"].log
            assert 100 <= p["epochs"] <= 800 and isinstance(p["epochs"], int)
        # 24 seed-0 trials + 3 * 2 re-selection fits = 30 calls total.
        assert len(calls) == 30
        assert sum(c[0] == 0 for c in calls) == 24
        assert sum(c[0] == 1 for c in calls) == sum(c[0] == 2 for c in calls) == 3
        top3 = sorted(study.trials, key=lambda t: (-t.value, t.number))[:3]
        expected_winner = min(top3, key=lambda t: (t.value, t.number))
        assert best["trial"] == expected_winner.number
        assert json.loads((out / "best.json").read_text()) == best

        # Resume does zero extra fits.
        resumed = T.run(args)
        assert resumed == best and len(calls) == 30

    print("  6. tuner (mocked): 24-trial search space, 3-seed re-selection (30 fits total), resume ok")


# ---------------------------------------------------------------------------
# 7. GPU script syntax, stubbed GPU steps, and bundle contents
# ---------------------------------------------------------------------------

def test_gpu_script_and_bundle():
    subprocess.run(["bash", "-n", "scripts/run_gpu.sh"], cwd=ROOT, check=True)

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        stub = root / "python-stub"
        stub.write_text(
            '#!/usr/bin/env bash\n'
            'if [ "$1" = -m ]; then printf "MODEL allow=%s %s\\n" "${PFE_ALLOW_TRAIN:-}" "$*"; fi\n'
            'if [ "$1" = -c ] && [[ "$2" == *assemble_lwo* ]]; then printf "ASSEMBLE %s %s\\n" "$3" "$4"; fi\n'
        )
        stub.chmod(0o755)
        results = root / "results"
        for arm, hidden in (("C", 16), ("D", 32)):
            tdir = results / f"hstgnn_{arm}_tuning"
            tdir.mkdir(parents=True)
            (tdir / "best.json").write_text(json.dumps({
                "params": {
                    "hidden": hidden, "receptive_field": 104,
                    "lr": 0.002, "weight_decay": 1e-4, "dropout": 0.1, "epochs": 200,
                }
            }))

        env = dict(
            os.environ,
            PY=str(stub),
            SKIP_PIP="1",
            PIN_TARGET=str(root / "pins"),
            PFE_DATASET="v5",
            PFE_RESULTS=str(results),
            STEPS="hstgnn_tune:D hstgnn:C hstgnn:E_degree:0 hstgnn:D:R2",
        )
        env.pop("HSTGNN_SEEDS", None)
        env.pop("HSTGNN_N_SEEDS", None)
        res = subprocess.run(
            ["bash", "scripts/run_gpu.sh"], cwd=ROOT, env=env,
            capture_output=True, text=True, check=True, timeout=30,
        )
        assert "failed, continuing" not in res.stdout, res.stdout + res.stderr
        model_lines = [shlex.split(ln) for ln in res.stdout.splitlines() if ln.startswith("MODEL ")]
        # Expected: 1 tune + 1 arm C R1 + 1 arm E_degree:0 R1 + 5 folds of arm D R2 = 8 commands.
        assert len(model_lines) == 8, (len(model_lines), model_lines)
        assert all(ln[1] == "allow=1" for ln in model_lines)
        assert model_lines[0][2:5] == ["-m", "src.models.tune_hstgnn", "--arm"]
        assert model_lines[0][5] == "D"
        # Default 10 seeds: 0..9.
        c_cmd = model_lines[1][2:]
        assert "--arm" in c_cmd and c_cmd[c_cmd.index("--arm") + 1] == "C"
        assert c_cmd[c_cmd.index("--hidden") + 1] == "16"
        assert c_cmd[c_cmd.index("--seeds") + 1:] == [str(i) for i in range(10)]
        # E_degree:0 reuses D's hidden=32.
        e_cmd = model_lines[2][2:]
        assert e_cmd[e_cmd.index("--arm") + 1] == "E_degree:0"
        assert e_cmd[e_cmd.index("--hidden") + 1] == "32"
        assert e_cmd[e_cmd.index("--run") + 1] == "hstgnn_E_degree_0"
        # D:R2 runs folds 0..4 and calls assemble_lwo.
        r2_folds = [ln[2:][ln[2:].index("--fold") + 1] for ln in model_lines[3:8]]
        assert r2_folds == ["0", "1", "2", "3", "4"]
        assert any(ln.startswith("ASSEMBLE hstgnn_D_lwo") for ln in res.stdout.splitlines())

        # Override seeds via HSTGNN_SEEDS.
        env2 = dict(env, STEPS="hstgnn:D:R3_f25", HSTGNN_SEEDS="0 1 2")
        res2 = subprocess.run(
            ["bash", "scripts/run_gpu.sh"], cwd=ROOT, env=env2,
            capture_output=True, text=True, check=True, timeout=30,
        )
        m2 = [shlex.split(ln) for ln in res2.stdout.splitlines() if ln.startswith("MODEL ")][0][2:]
        assert m2[m2.index("--regime") + 1] == "R3_f25"
        assert m2[m2.index("--run") + 1] == "hstgnn_D_f25"
        assert m2[m2.index("--seeds") + 1:] == ["0", "1", "2"]

    from scripts.make_gpu_bundle import bundle_files
    from src.config import DATASET, PROCESSED

    files = set(bundle_files())
    export = PROCESSED / "kg" / f"export_{DATASET}_main"
    for needed in (
        export / "nodes.parquet",
        export / "edges_C.parquet",
        export / "edges_D.parquet",
        export / "manifest.json",
        ROOT / "tests" / "test_hetero_stgnn.py",
    ):
        assert needed in files, f"missing from gpu bundle: {needed}"

    print("  7. GPU runner & bundle: bash -n ok, hstgnn_tune/hstgnn steps + R2 assembly + "
          "HSTGNN_SEEDS ok, bundle includes nodes/edges_C/edges_D/controls")


if __name__ == "__main__":
    optuna.logging.set_verbosity(optuna.logging.ERROR)
    t0 = time.perf_counter()
    for fn in (
        test_causality_and_architecture,
        test_dynamic_inputs,
        test_held_out_well_isolation,
        test_training_guard,
        test_toy_fit_replay_and_config_lock,
        test_tuner_mocked,
        test_gpu_script_and_bundle,
    ):
        fn()
    print(f"test_hetero_stgnn: all checks passed ({time.perf_counter() - t0:.2f}s)")
