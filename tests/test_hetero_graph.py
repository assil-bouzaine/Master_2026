"""Checks of the PyG HeteroData builder and static-only encoder (src/models/hetero_graph.py).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_hetero_graph

1. Equivalence with the export: for export_v4_main and arms C and D, every node count per type
   matches nodes.parquet and every edge of edges_<arm>.parquet appears exactly once in the
   forward edge types with its weight; reverse edges mirror every forward relation; an extra
   v5-like node type (aquifer_unit) and directed relations (monitors, overlies) work cleanly.
2. Zero start: an untrained HeteroEncoder returns exact zeros for every well (zero-initialised
   linear head).
3. No stress can enter: the encoder reads only x, edge_index and edge_attr; no node feature
   name contains a weekly forcing/head/flow/volume variable; altering post-training or
   pre-window weekly tables does not change any node feature under full train or R3 windows.
4. Locality: with a randomly re-initialised head, perturbing one facility's features changes
   every well within 2 hops of it and leaves every well further than 2 hops untouched.
5. Determinism: identical seeds yield bit-for-bit identical graphs and encoder outputs.
"""
from collections import deque
from functools import lru_cache
import json

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch_geometric.data import HeteroData

from src.config import DATASET_DIR, PROCESSED
from src.models.hetero_graph import (
    FORBIDDEN_WEEKLY_VARS,
    HeteroEncoder,
    build_heterodata,
)

EXPORT_V4_MAIN = PROCESSED / "kg" / "export_v4_main"


@lru_cache(maxsize=1)
def _base_tables():
    return {
        "wells": pd.read_parquet(DATASET_DIR / "wells.parquet"),
        "pumping_points": pd.read_parquet(DATASET_DIR / "pumping_points.parquet"),
        "pumping_weekly": pd.read_parquet(DATASET_DIR / "pumping_weekly.parquet"),
        "forcing_weekly": pd.read_parquet(DATASET_DIR / "forcing_weekly.parquet"),
        "rivers_weekly": pd.read_parquet(DATASET_DIR / "rivers_weekly.parquet"),
    }


@lru_cache(maxsize=2)
def _built_arm(arm):
    return build_heterodata(EXPORT_V4_MAIN, arm, tables=_base_tables())


def _bfs_distances(data, start_type, start_idx):
    """Shortest-path hop distances from (start_type, start_idx) over all edges in data."""
    adj = {}
    for et in data.edge_types:
        st, _, dt = et
        ei = data[et].edge_index.numpy()
        for u, v in zip(ei[0].tolist(), ei[1].tolist()):
            adj.setdefault((st, u), set()).add((dt, v))
            adj.setdefault((dt, v), set()).add((st, u))

    dist = {(start_type, start_idx): 0}
    queue = deque([(start_type, start_idx)])
    while queue:
        node = queue.popleft()
        d = dist[node]
        for nbr in adj.get(node, ()):
            if nbr not in dist:
                dist[nbr] = d + 1
                queue.append(nbr)
    return dist


def _randomise_head(encoder, seed=123):
    """Replace the zero-initialised output head with deterministic random weights."""
    torch.manual_seed(seed)
    nn.init.normal_(encoder.head.weight, mean=0.0, std=0.5)
    nn.init.normal_(encoder.head.bias, mean=0.0, std=0.1)


def test_equivalence_with_export():
    nodes = pd.read_parquet(EXPORT_V4_MAIN / "nodes.parquet")
    manifest = json.loads((EXPORT_V4_MAIN / "manifest.json").read_text())
    wells = pd.read_parquet(DATASET_DIR / "wells.parquet")
    expected_nodes = nodes["type"].value_counts().to_dict()
    assert expected_nodes == manifest["nodes"]

    for arm in ("C", "D"):
        edges = pd.read_parquet(EXPORT_V4_MAIN / f"edges_{arm}.parquet")
        data, index = build_heterodata(EXPORT_V4_MAIN, arm)

        # Node types, counts, well order, finite standardised tensors
        assert set(data.node_types) == set(expected_nodes)
        for ntype, count in expected_nodes.items():
            assert data[ntype].x.shape[0] == count, (arm, ntype)
            assert len(index[ntype]) == count
            assert torch.isfinite(data[ntype].x).all(), (arm, ntype)
        assert list(index["well"].keys()) == wells["code_bss"].tolist()

        # Forward edge equivalence: every export edge appears once with its weight
        inv_index = {nt: {row: code for code, row in mp.items()} for nt, mp in index.items()}
        got_edges = {}
        total_fwd = 0
        for et in data.forward_edge_types:
            st, rel, dt = et
            ei = data[et].edge_index.numpy()
            ea = data[et].edge_attr.numpy()
            assert np.isfinite(ea).all(), (arm, et)
            assert data[et].edge_attr_names[0] == "weight"
            total_fwd += ei.shape[1]
            for k in range(ei.shape[1]):
                key = (st, rel, dt, inv_index[st][int(ei[0, k])], inv_index[dt][int(ei[1, k])])
                assert key not in got_edges, f"Duplicate forward edge {key} in arm {arm}"
                got_edges[key] = float(ea[k, 0])

            # Matching reverse edge type with flipped indices and identical attributes
            rev_et = (dt, f"rev_{rel}", st)
            assert rev_et in data.edge_types
            assert torch.equal(data[rev_et].edge_index, data[et].edge_index.flip(0))
            assert torch.equal(data[rev_et].edge_attr, data[et].edge_attr)

        assert total_fwd == len(edges), (arm, total_fwd, len(edges))
        for row in edges.itertuples():
            key = (row.src_type, row.relation, "well", row.src, row.dst)
            assert key in got_edges, f"Missing export edge {key} in arm {arm}"
            np.testing.assert_allclose(got_edges[key], float(row.weight), rtol=1e-6, atol=1e-7)

        # Missing-flag columns match nulls in the export
        assert "distance_m_missing" in data.edge_attr_names
        assert "sign_missing" in data.edge_attr_names
        dist_miss_idx = data.edge_attr_names.index("distance_m_missing")
        sign_miss_idx = data.edge_attr_names.index("sign_missing")
        fwd_dist_miss = sum(int(data[et].edge_attr[:, dist_miss_idx].sum().item())
                            for et in data.forward_edge_types)
        fwd_sign_miss = sum(int(data[et].edge_attr[:, sign_miss_idx].sum().item())
                            for et in data.forward_edge_types)
        assert fwd_dist_miss == int(edges["distance_m"].isna().sum())
        assert fwd_sign_miss == int(edges["sign"].isna().sum())

        node_summary = ", ".join(f"{nt}={data[nt].x.shape[0]}x{data[nt].x.shape[1]}"
                                 for nt in sorted(data.node_types))
        edge_summary = ", ".join(f"{et[1]}={data[et].edge_index.shape[1]}"
                                 for et in data.forward_edge_types)
        print(f"  1. arm {arm}: nodes [{node_summary}]; forward edges ({total_fwd}) [{edge_summary}]; "
              f"edge_attr width={len(data.edge_attr_names)} ({data.edge_attr_names})")

    # Genericity check: v5-style aquifer_unit nodes + directed monitors and overlies relations
    w_codes = wells["code_bss"].iloc[:2].tolist()
    toy_nodes = pd.DataFrame([
        {"type": "well", "code": w_codes[0]},
        {"type": "well", "code": w_codes[1]},
        {"type": "aquifer_unit", "code": "718BP02"},
        {"type": "aquifer_unit", "code": "671AA00"},
    ])
    toy_edges = pd.DataFrame([
        {"relation": "monitors", "src_type": "well", "src": w_codes[0],
         "dst_type": "aquifer_unit", "dst": "718BP02", "weight": 1.0,
         "distance_m": None, "sign": None, "eligible": False, "constrained": False},
        {"relation": "overlies", "src_type": "aquifer_unit", "src": "671AA00",
         "dst_type": "aquifer_unit", "dst": "718BP02", "weight": 1.0,
         "distance_m": None, "sign": "PositiveResponse", "eligible": True, "constrained": True},
    ])
    toy_data, toy_idx = build_heterodata(
        EXPORT_V4_MAIN, "D", tables=_base_tables() | {"nodes": toy_nodes, "edges": toy_edges}
    )
    assert set(toy_data.node_types) == {"well", "aquifer_unit"}
    assert torch.equal(toy_data["aquifer_unit"].x, torch.ones((2, 1), dtype=torch.float32))
    assert ("well", "monitors", "aquifer_unit") in toy_data.forward_edge_types
    assert ("aquifer_unit", "rev_monitors", "well") in toy_data.reverse_edge_types
    assert ("aquifer_unit", "overlies", "aquifer_unit") in toy_data.forward_edge_types
    assert ("aquifer_unit", "rev_overlies", "aquifer_unit") in toy_data.reverse_edge_types
    assert toy_data["aquifer_unit", "overlies", "aquifer_unit"].edge_index.shape == (2, 1)
    print("     generic v5 check: aquifer_unit constant-1 feature + monitors/overlies forward & reverse edges ok")


def test_zero_start():
    for arm in ("C", "D"):
        data, index = _built_arm(arm)
        torch.manual_seed(0)
        encoder = HeteroEncoder.from_heterodata(data, n_out=6)
        for mode in ("eval", "train"):
            getattr(encoder, mode)()
            out = encoder(data)
            assert out.shape == (len(index["well"]), 6)
            assert torch.equal(out, torch.zeros((len(index["well"]), 6), dtype=torch.float32)), (arm, mode)
    print("  2. zero start: untrained HeteroEncoder returns exact zeros (65 x 6) for arms C and D in eval & train")


def test_no_stress_can_enter():
    data_d, _ = _built_arm("D")
    base_tables = _base_tables()

    # 3a. Feature names must never equal or contain a weekly forcing/head/flow/volume variable.
    weekly_tables = {
        "forcing_weekly": base_tables["forcing_weekly"],
        "rivers_weekly": base_tables["rivers_weekly"],
        "pumping_weekly": base_tables["pumping_weekly"],
        "heads_weekly": pd.read_parquet(DATASET_DIR / "heads_weekly.parquet"),
    }
    key_cols = {"cell_id", "week", "code_station", "n_days", "code_ouvrage", "usage",
                "imputed", "imputation", "code_bss", "share_not_validated"}
    discovered_weekly = set()
    for df in weekly_tables.values():
        discovered_weekly |= (set(df.columns) - key_cols)
    forbidden = FORBIDDEN_WEEKLY_VARS | discovered_weekly
    multi_char_forbidden = {v.lower() for v in forbidden if len(v) >= 2}

    all_feature_names = {}
    for nt in data_d.node_types:
        names = list(data_d[nt].feature_names)
        all_feature_names[nt] = names
        for name in names:
            assert name not in forbidden, f"Node type {nt!r} exposes weekly variable {name!r}"
            low = name.lower()
            for bad in multi_char_forbidden:
                assert bad not in low, f"Node feature {nt}.{name!r} contains weekly variable token {bad!r}"

    # 3b. Encoder only consumes x, edge_index and edge_attr (stripped graph gives exact same output).
    stripped = HeteroData()
    for nt in data_d.node_types:
        stripped[nt].x = data_d[nt].x.clone()
    for et in data_d.edge_types:
        stripped[et].edge_index = data_d[et].edge_index.clone()
        stripped[et].edge_attr = data_d[et].edge_attr.clone()
    torch.manual_seed(11)
    enc = HeteroEncoder.from_heterodata(data_d, n_out=5)
    _randomise_head(enc, seed=19)
    enc.eval()
    assert torch.equal(enc(data_d), enc(stripped))

    # 3c. Training-window isolation under full train and R3 f25 (train_start="2016-04-01"):
    # altering post-train, pre-window, and imputed weekly rows changes zero node features.
    splits = json.loads((DATASET_DIR / "splits.json").read_text())
    train_end = pd.Timestamp(splits["train"][1])
    pumping_points = base_tables["pumping_points"]

    for train_start in (None, "2016-04-01"):
        start_ts = pd.Timestamp(train_start or splits["train"][0])
        before, _ = build_heterodata(EXPORT_V4_MAIN, "D", tables=base_tables, train_start=train_start)

        mod_forcing = base_tables["forcing_weekly"].copy()
        out_f = (mod_forcing["week"] > train_end) | (mod_forcing["week"] < start_ts)
        mod_forcing.loc[out_f, ["rain", "ETP", "PE"]] = 99999.0

        mod_rivers = base_tables["rivers_weekly"].copy()
        out_r = (mod_rivers["week"] > train_end) | (mod_rivers["week"] < start_ts)
        mod_rivers.loc[out_r, "q_m3s"] = 99999.0

        mod_pumping = base_tables["pumping_weekly"].copy()
        out_p = (mod_pumping["week"] > train_end) | (mod_pumping["week"] < start_ts)
        mod_pumping.loc[out_p, "volume_m3"] = 1e12
        mod_pumping.loc[out_p, "usage"] = "industry"
        # Imputed groundwater rows inside the window must also be ignored by facility & well declared features
        imp_gw = mod_pumping["imputed"] & mod_pumping["code_ouvrage"].isin(
            pumping_points.loc[pumping_points["source"] == "groundwater", "code_ouvrage"]
        )
        mod_pumping.loc[imp_gw, "volume_m3"] = 1e12

        altered = base_tables | {
            "forcing_weekly": mod_forcing,
            "rivers_weekly": mod_rivers,
            "pumping_weekly": mod_pumping,
        }
        after, _ = build_heterodata(EXPORT_V4_MAIN, "D", tables=altered, train_start=train_start)
        for nt in before.node_types:
            assert torch.equal(before[nt].x, after[nt].x), (train_start, nt)

    # Positive control: altering forcing inside the training window DOES change weather_cell.x
    in_forcing = base_tables["forcing_weekly"].copy()
    first_cell = data_d["weather_cell"].node_codes[0]
    in_mask = (in_forcing["cell_id"] == first_cell) & in_forcing["week"].between("2016-04-01", train_end)
    in_forcing.loc[in_mask, "rain"] += 500.0
    changed, _ = build_heterodata(
        EXPORT_V4_MAIN, "D", tables=base_tables | {"forcing_weekly": in_forcing}, train_start="2016-04-01"
    )
    ref_f25, _ = build_heterodata(EXPORT_V4_MAIN, "D", tables=base_tables, train_start="2016-04-01")
    assert not torch.equal(ref_f25["weather_cell"].x, changed["weather_cell"].x)
    print(f"  3. no stress can enter: {len(forbidden)} weekly vars absent from node feature names "
          f"({sum(len(v) for v in all_feature_names.values())} features across {len(all_feature_names)} types); "
          f"full-train and f25 features invariant to out-of-window & imputed weekly perturbations")


def test_locality():
    data, index = _built_arm("D")
    n_wells = len(index["well"])

    # Pick a facility in arm D that has at least one 1-hop well, at least one 2-hop well,
    # and at least one well strictly further than 2 hops away.
    chosen = None
    for f_code, f_idx in index["facility"].items():
        dist = _bfs_distances(data, "facility", f_idx)
        w_dists = {w_idx: dist.get(("well", w_idx), 999) for w_idx in range(n_wells)}
        hop1 = [w for w, d in w_dists.items() if d == 1]
        hop2 = [w for w, d in w_dists.items() if d == 2]
        far = [w for w, d in w_dists.items() if d > 2]
        if hop1 and hop2 and far:
            chosen = (f_code, f_idx, hop1, hop2, far)
            break
    assert chosen is not None, "Expected a facility in arm D with 1-hop, 2-hop and >2-hop wells"
    f_code, f_idx, hop1, hop2, far = chosen

    torch.manual_seed(42)
    encoder = HeteroEncoder.from_heterodata(data, n_out=4)
    _randomise_head(encoder, seed=99)
    encoder.eval()

    with torch.no_grad():
        y0 = encoder(data)
        data_pert = data.clone()
        data_pert["facility"].x = data["facility"].x.clone()
        data_pert["facility"].x[f_idx] = data_pert["facility"].x[f_idx] + 5.0
        y1 = encoder(data_pert)

    diff = (y1 - y0).abs().max(dim=1).values
    within_2 = hop1 + hop2
    assert (diff[within_2] > 1e-6).all(), f"Some <=2-hop wells did not change: {diff[within_2]}"
    assert (diff[far] == 0.0).all(), f"Some >2-hop wells changed: max={diff[far].max().item()}"

    # Also test a synthetic 3-hop chain F0 -- W0 -- F1 -- W1 plus W0 -- W2 (2 hops) and isolated W3
    toy = HeteroData()
    toy["facility"].x = torch.tensor([[1.0, 0.0], [0.0, 1.0]], dtype=torch.float32)
    toy["well"].x = torch.tensor([[0.5, 0.5], [1.0, -0.5], [-0.5, 1.0], [0.2, 0.3]], dtype=torch.float32)
    ea2 = torch.tensor([[1.0, 0.1], [1.0, 0.2], [1.0, 0.3]], dtype=torch.float32)
    toy["facility", "pumping", "well"].edge_index = torch.tensor([[0, 1, 1], [0, 0, 1]], dtype=torch.long)
    toy["facility", "pumping", "well"].edge_attr = ea2
    toy["well", "rev_pumping", "facility"].edge_index = toy["facility", "pumping", "well"].edge_index.flip(0)
    toy["well", "rev_pumping", "facility"].edge_attr = ea2.clone()
    wl_ei = torch.tensor([[0, 2], [2, 0]], dtype=torch.long)
    wl_ea = torch.tensor([[0.8, 0.1], [0.8, 0.1]], dtype=torch.float32)
    toy["well", "well_link", "well"].edge_index = wl_ei
    toy["well", "well_link", "well"].edge_attr = wl_ea
    toy["well", "rev_well_link", "well"].edge_index = wl_ei.flip(0)
    toy["well", "rev_well_link", "well"].edge_attr = wl_ea.clone()

    torch.manual_seed(7)
    toy_enc = HeteroEncoder.from_heterodata(toy, n_out=3)
    _randomise_head(toy_enc, seed=13)
    toy_enc.eval()
    with torch.no_grad():
        ty0 = toy_enc(toy)
        toy_pert = toy.clone()
        toy_pert["facility"].x = toy["facility"].x.clone()
        toy_pert["facility"].x[0] += 3.0
        ty1 = toy_enc(toy_pert)
    tdiff = (ty1 - ty0).abs().max(dim=1).values
    assert tdiff[0] > 1e-6 and tdiff[2] > 1e-6, tdiff  # W0 (1 hop) and W2 (2 hops)
    assert tdiff[1] == 0.0 and tdiff[3] == 0.0, tdiff  # W1 (3 hops via F1) and W3 (isolated)

    print(f"  4. locality: arm D facility {f_code} -> {len(hop1)} 1-hop + {len(hop2)} 2-hop wells changed "
          f"(min diff {diff[within_2].min().item():.2e}), all {len(far)} >2-hop wells exact 0.0; "
          f"synthetic 3-hop chain exact")


def test_determinism():
    base = _base_tables()
    data1, idx1 = build_heterodata(EXPORT_V4_MAIN, "D", tables=base)
    data2, idx2 = build_heterodata(EXPORT_V4_MAIN, "D", tables=base)
    assert idx1 == idx2
    for nt in data1.node_types:
        assert torch.equal(data1[nt].x, data2[nt].x)
    for et in data1.edge_types:
        assert torch.equal(data1[et].edge_index, data2[et].edge_index)
        assert torch.equal(data1[et].edge_attr, data2[et].edge_attr)

    def run_once(seed):
        torch.manual_seed(seed)
        enc = HeteroEncoder.from_heterodata(data1, n_out=5)
        _randomise_head(enc, seed=seed + 100)
        enc.eval()
        with torch.no_grad():
            y_eval = enc(data1)
        torch.manual_seed(seed + 200)
        enc.train()
        with torch.no_grad():
            y_train = enc(data1)
        return y_eval, y_train

    e1, t1 = run_once(2026)
    e2, t2 = run_once(2026)
    e3, _ = run_once(2027)
    assert torch.equal(e1, e2)
    assert torch.equal(t1, t2)
    assert not torch.equal(e1, e3)
    print("  5. determinism: identical seeds produce bit-for-bit identical graphs and eval/train outputs")


if __name__ == "__main__":
    test_equivalence_with_export()
    test_zero_start()
    test_no_stress_can_enter()
    test_locality()
    test_determinism()
    print("test_hetero_graph: all checks passed")
