"""Black-box heterogeneous spatio-temporal GNN on the hybrid's HeteroData (analysis plan v3 §6).

    PFE_DATASET=v5 PFE_ALLOW_TRAIN=1 python -m src.models.hetero_stgnn \\
        --arm D --hidden 32 --receptive-field 104 --epochs 300 --run hstgnn_D

Why this module exists
----------------------
Hybrid-GNN v2 (`src/models/hybrid_gnn.py`) uses the knowledge graph only to predict parameters
of sign-constrained hydrological response functions. To measure whether the structured response
model helps or hurts against an unconstrained deep network on the **same** knowledge graph,
analysis plan v3 §6 pairs it with a black-box heterogeneous spatio-temporal GNN (Hetero-STGNN)
that reads the exact same `HeteroData` export (arms C vs D, and the E/F controls) and predicts
each well's weekly groundwater level in **simulation** mode (forcings and graph only; no past
head is ever an input).

Architecture
------------
1. **Graph:** built directly by `hetero_graph.build_heterodata(export_dir, arm, ...)`, keeping
   every node type, static feature, forward edge type, `rev_` reverse edge type, and export
   edge weight unchanged.
2. **Dynamic node inputs (weekly, from forcing start to last week), standardised with training-
   window statistics only (`statics.training_window`):**
   - `weather_cell`: rain, ETP, effective rain (PE);
   - `facility`: weekly abstraction (reconstruction 1, thousand m3/week) and a 0/1 `imputed`
     channel; weeks before the pumping record take the facility's training mean with `imputed=1`
     (plan v3 §3.6: unknown, not zero);
   - `gauge`: `log1p` weekly discharge, missing weeks 0 with a 0/1 `missing` channel;
   - `canal`: weekly volume of the node's basin (or plain series for a plain node), pre-record
     weeks filled with the node's training mean;
   - `well`: sin and cos of the week of year (no head, no stress);
   - other node types (`aquifer_unit`): no dynamic input.
   Every node type also carries its static features from `build_heterodata` (broadcast over weeks).
3. **Temporal encoder per dynamic node type:** linear input map (`dynamic + static -> d`), then
   a strictly causal dilated gated temporal convolution stack (`tanh * sigmoid`, kernel size 2,
   dilations `1, 2, 4, ...` capped to hit the exact requested receptive field between 52 and 156
   weeks with no holes), residual connections, and per-(node, week) LayerNorm, run over all weeks
   at once (no window sampling). Large node types (the 2,077 facilities) are chunked along the
   node axis with activation checkpointing during training so `d=64, rf=156` fits comfortably on
   a 15 GB Colab T4 GPU with identical outputs and gradients.
4. **Spatial message passing:** two layers of PyG `HeteroConv` over every forward and `rev_`
   edge type of the `HeteroData`, each relation a `TemporalGraphConv(d, d, aggr="add", node_dim=0)`
   subclass of PyG `GraphConv` that propagates `(nodes, weeks, d)` tensors weighted by the export
   weight (`edge_attr[:, 0]`, 1 where missing) using sparse matrix multiplication (mathematically
   identical to `GraphConv` without materialising an `(edges, weeks, d)` message tensor); summed
   over relations, plus a residual self term, LayerNorm, ReLU, and dropout. Static-only node
   types enter through their static features mapped to `d`.
5. **Decoder:** a 2-layer MLP on each well's final hidden state concatenated with its static
   features -> standardised head anomaly `y_hat_i(t)`. Predicted head is `mu_i + sd_i * y_hat_i(t)`
   with `mu_i`, `sd_i` (floored at `SD_FLOOR`) computed exactly as in `hybrid_gnn`.
6. **Training & guard:** masked MSE of `y_hat` over observed training weeks of training wells
   (placeholder weeks masked, equal weight per training well), all wells in one forward pass per
   epoch, AdamW + cosine-annealed learning rate for a fixed number of epochs (no early stopping).
   Refuses to fit unless `PFE_ALLOW_TRAIN=1` is set.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.checkpoint import checkpoint as grad_checkpoint
from torch_geometric.nn import GraphConv, HeteroConv

from src.config import DATASET, DATASET_DIR, PROCESSED, R3_STARTS
from src.dataset import canal_basins as CB
from src.dataset.placeholders import load_mask as load_placeholder_mask
from src.dataset.pumping import canal_series, seasonal_drinking_water
from src.models import response as R
from src.models import routing as RT
from src.models import statics
from src.models.evaluate import RESULTS, evaluate_run
from src.models.features import build_panel
from src.models.hetero_graph import build_heterodata
from src.models.lstm import (
    cached_seed,
    median_nse,
    regime_masks,
    run_fingerprint,
    save_seed,
    save_seed_model,
    seed_mean_predictions,
    write_config,
)
from src.models.manifest import load_checkpoint, write_manifest, write_schema

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DYNAMIC_CHANNELS = {
    "weather_cell": ("rain", "ETP", "PE"),
    "facility": ("volume", "imputed"),
    "gauge": ("log1p_q", "missing"),
    "canal": ("volume",),
    "well": ("season_sin", "season_cos"),
}
FLAG_CHANNELS = frozenset({"imputed", "missing"})

HIDDEN_CHOICES = (16, 32, 64)
RECEPTIVE_FIELD_CHOICES = (52, 104, 156)
N_SPATIAL_LAYERS = 2
TCN_KERNEL_SIZE = 2
TCN_NODE_CHUNK = 256

SD_FLOOR = R.SD_FLOOR
REGIMES = ("R1", "R2", "R3_f25", "R3_f50", "refit")
N_FOLDS = 5
CANAL_PLAIN = "canal-intakes:plain"
ALLOW_TRAIN_ENV = "PFE_ALLOW_TRAIN"
NO_SCORE_ENV = "PFE_NO_SCORE"


# ---------------------------------------------------------------------------
# Causal Temporal Encoder and Heterogeneous Spatial Message Passing
# ---------------------------------------------------------------------------

def dilations_for_receptive_field(receptive_field: int, kernel_size: int = TCN_KERNEL_SIZE) -> tuple[int, ...]:
    """Return causal TCN dilations ``(1, 2, 4, ...)`` with a contiguous receptive field.

    With ``kernel_size = 2``, the receptive field of dilations ``(d_0, ..., d_{L-1})`` is
    ``1 + sum(d_l)``. Doubling ``1, 2, 4, ...`` and capping the final dilation to the remaining
    span hits any integer ``receptive_field >= 2`` exactly with zero holes because each step is
    at most the receptive field already covered.
    """
    rf = int(receptive_field)
    k = int(kernel_size)
    if rf < 2:
        raise ValueError(f"receptive_field must be >= 2, got {rf}")
    if k < 2:
        raise ValueError(f"kernel_size must be >= 2, got {k}")
    step_span = k - 1
    needed = (rf - 1 + step_span - 1) // step_span
    dilations = []
    d = 1
    remaining = needed
    while remaining > 0:
        if remaining <= d:
            dilations.append(remaining)
            break
        dilations.append(d)
        remaining -= d
        d *= k
    return tuple(dilations)


def receptive_field_of(dilations, kernel_size: int = TCN_KERNEL_SIZE) -> int:
    """Exact receptive field (in weeks) of a causal dilated Conv1d stack."""
    return 1 + (int(kernel_size) - 1) * sum(int(d) for d in dilations)


class CausalGatedBlock(nn.Module):
    """One strictly causal dilated gated temporal convolution block with residual skip.

    Left-only padding ``(kernel_size - 1) * dilation`` guarantees that output at week ``t``
    depends only on weeks ``<= t``. LayerNorm acts across channels at each ``(node, week)``
    independently and never mixes information across time.
    """

    def __init__(self, channels: int, kernel_size: int = TCN_KERNEL_SIZE, dilation: int = 1, dropout: float = 0.1):
        super().__init__()
        self.pad = (int(kernel_size) - 1) * int(dilation)
        self.conv = nn.Conv1d(int(channels), 2 * int(channels), kernel_size=int(kernel_size), dilation=int(dilation))
        self.drop = nn.Dropout(float(dropout))
        self.norm = nn.LayerNorm(int(channels))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """``x`` of shape ``(N, C, T)`` -> ``(N, C, T)``."""
        x_pad = F.pad(x, (self.pad, 0))
        a, b = self.conv(x_pad).chunk(2, dim=1)
        gated = self.drop(torch.tanh(a) * torch.sigmoid(b))
        out = x + gated
        return self.norm(out.transpose(1, 2)).transpose(1, 2)


class TemporalEncoder(nn.Module):
    """Per-node-type input map (dynamic + broadcast static -> ``d``) + causal gated TCN stack.

    Nodes do not interact inside the temporal encoder, so large node types (e.g. 2,077 facilities
    over 1,925 weeks) are processed in node chunks with gradient checkpointing during training,
    giving identical outputs and gradients at a fraction of the peak GPU memory.
    """

    def __init__(
        self,
        in_dyn: int,
        in_stat: int,
        hidden: int,
        receptive_field: int,
        dropout: float = 0.1,
        chunk_size: int = TCN_NODE_CHUNK,
    ):
        super().__init__()
        self.in_dyn = int(in_dyn)
        self.in_stat = int(in_stat)
        self.hidden = int(hidden)
        self.receptive_field = int(receptive_field)
        self.chunk_size = int(chunk_size)
        self.dilations = dilations_for_receptive_field(self.receptive_field, TCN_KERNEL_SIZE)

        # dyn_proj(x_dyn) + stat_proj(x_stat).unsqueeze(1) equals Linear(in_dyn + in_stat, hidden)
        # on [x_dyn, broadcast(x_stat)] without materialising the concatenated static broadcast.
        self.dyn_proj = nn.Linear(self.in_dyn, self.hidden, bias=True)
        self.stat_proj = nn.Linear(self.in_stat, self.hidden, bias=False) if self.in_stat > 0 else None
        self.blocks = nn.ModuleList([
            CausalGatedBlock(self.hidden, kernel_size=TCN_KERNEL_SIZE, dilation=d, dropout=dropout)
            for d in self.dilations
        ])

    def _run_chunk(self, x_dyn: torch.Tensor, x_stat: torch.Tensor) -> torch.Tensor:
        h = self.dyn_proj(x_dyn)
        if self.stat_proj is not None:
            h = h + self.stat_proj(x_stat).unsqueeze(1)
        h = h.transpose(1, 2)  # (N_chunk, hidden, T)
        for block in self.blocks:
            h = block(h)
        return h.transpose(1, 2)  # (N_chunk, T, hidden)

    def forward(self, x_dyn: torch.Tensor, x_stat: torch.Tensor) -> torch.Tensor:
        """``x_dyn`` ``(N, T, F_dyn)``, ``x_stat`` ``(N, F_stat)`` -> ``(N, T, hidden)``."""
        n_nodes, n_weeks, _ = x_dyn.shape
        if n_nodes == 0:
            return x_dyn.new_zeros((0, n_weeks, self.hidden))
        if n_nodes <= self.chunk_size:
            return self._run_chunk(x_dyn, x_stat)
        use_ckpt = self.training and torch.is_grad_enabled()
        parts = []
        for start in range(0, n_nodes, self.chunk_size):
            xd = x_dyn[start:start + self.chunk_size]
            xs = x_stat[start:start + self.chunk_size]
            if use_ckpt:
                parts.append(grad_checkpoint(self._run_chunk, xd, xs, use_reentrant=False))
            else:
                parts.append(self._run_chunk(xd, xs))
        return torch.cat(parts, dim=0)


class TemporalGraphConv(GraphConv):
    """PyG ``GraphConv(d, d, aggr='add', node_dim=0)`` supporting 3D ``(nodes, weeks, d)`` tensors.

    Stock ``GraphConv.message`` uses ``edge_weight.view(-1, 1) * x_j``, which fails when ``x_j``
    is 3D ``(edges, weeks, d)`` and would also materialise an ``(edges, weeks, d)`` message
    tensor (over 11 GB on arm C's 22,350 pumping edges). For 3D tensors with ``aggr='add'``,
    sparse matrix multiplication computes the exact same weighted neighbour sum in
    ``O(N_src + N_dst)`` memory while preserving autograd gradients for both node states and
    ``edge_weight``.
    """

    def __init__(self, in_channels, out_channels: int, aggr: str = "add", bias: bool = True, **kwargs):
        kwargs.setdefault("node_dim", 0)
        super().__init__(in_channels, out_channels, aggr=aggr, bias=bias, **kwargs)

    def message(self, x_j: torch.Tensor, edge_weight=None) -> torch.Tensor:
        if edge_weight is None:
            return x_j
        view_shape = (-1,) + (1,) * (x_j.ndim - 1)
        return edge_weight.view(view_shape) * x_j

    def forward(self, x, edge_index, edge_weight=None, size=None) -> torch.Tensor:
        if isinstance(x, torch.Tensor):
            x = (x, x)
        x_src, x_dst = x
        if x_src.ndim == 3 and self.aggr == "add" and isinstance(edge_index, torch.Tensor):
            n_src, n_weeks, d_in = x_src.shape
            if x_dst is not None:
                n_dst = x_dst.shape[0]
            elif size is not None:
                n_dst = int(size[1])
            else:
                n_dst = n_src
            if edge_index.numel() == 0:
                agg = x_src.new_zeros((n_dst, n_weeks, d_in))
            else:
                ew = (
                    torch.ones(edge_index.shape[1], dtype=x_src.dtype, device=x_src.device)
                    if edge_weight is None
                    else edge_weight.to(dtype=x_src.dtype, device=x_src.device)
                )
                adj = torch.sparse_coo_tensor(
                    torch.stack([edge_index[1], edge_index[0]]),
                    ew,
                    size=(n_dst, n_src),
                    device=x_src.device,
                    dtype=x_src.dtype,
                ).coalesce()
                agg = torch.sparse.mm(adj, x_src.reshape(n_src, n_weeks * d_in)).reshape(
                    n_dst, n_weeks, d_in
                )
            out = self.lin_rel(agg)
            if x_dst is not None:
                out = out + self.lin_root(x_dst)
            return out
        return super().forward(x, edge_index, edge_weight=edge_weight, size=size)


def extract_edge_weight(data, et) -> torch.Tensor:
    """Return 1D float32 edge weights from ``edge_attr`` column 0, with ``1.0`` where missing."""
    store = data[et]
    n_edges = int(store.edge_index.shape[1])
    device = store.edge_index.device
    ea = getattr(store, "edge_attr", None)
    if ea is None or ea.ndim != 2 or ea.shape[1] == 0:
        return torch.ones(n_edges, dtype=torch.float32, device=device)
    w = ea[:, 0].to(dtype=torch.float32)
    names = list(getattr(store, "edge_attr_names", getattr(data, "edge_attr_names", [])))
    if "weight_missing" in names:
        miss = ea[:, names.index("weight_missing")] > 0.5
        w = torch.where(miss, torch.ones_like(w), w)
    return torch.where(torch.isfinite(w), w, torch.ones_like(w))


class HeteroSTGNN(nn.Module):
    """Black-box heterogeneous spatio-temporal GNN on the hybrid's ``HeteroData`` (plan v3 §6).

    1. Per-dynamic-node-type causal gated TCN encoder (input: dynamic + broadcast static).
    2. Static-only node types linearly mapped to ``hidden`` and broadcast across weeks.
    3. Two layers of PyG ``HeteroConv`` with ``TemporalGraphConv(d, d, aggr='add', node_dim=0)``
       over every forward and ``rev_`` edge type, weighted by the export weight, with relation
       summation, residual self term, LayerNorm, ReLU, and dropout.
    4. Decoder MLP on ``[h_well(t), static_well]`` -> standardised head anomaly ``y_hat_i(t)``.
    """

    def __init__(
        self,
        static_dims: dict[str, int],
        dynamic_dims: dict[str, int],
        edge_types: list[tuple[str, str, str]],
        *,
        well_graph_idx=None,
        n_wells: int | None = None,
        hidden: int = 32,
        receptive_field: int = 104,
        dropout: float = 0.1,
        n_spatial_layers: int = N_SPATIAL_LAYERS,
        well_type: str = "well",
        chunk_size: int = TCN_NODE_CHUNK,
    ):
        super().__init__()
        if well_type not in static_dims:
            raise ValueError(f"well_type {well_type!r} missing from static_dims {list(static_dims)}")
        if n_spatial_layers < 1:
            raise ValueError(f"n_spatial_layers must be >= 1, got {n_spatial_layers}")

        self.node_types = list(static_dims.keys())
        self.static_dims = {nt: int(dim) for nt, dim in static_dims.items()}
        self.dynamic_dims = {nt: int(dynamic_dims.get(nt, 0)) for nt in self.node_types}
        self.edge_types = [tuple(et) for et in edge_types]
        self.hidden = int(hidden)
        self.receptive_field = int(receptive_field)
        self.dropout = float(dropout)
        self.n_spatial_layers = int(n_spatial_layers)
        self.well_type = str(well_type)

        if well_graph_idx is not None:
            w_idx = torch.as_tensor(well_graph_idx, dtype=torch.long)
        elif n_wells is not None:
            w_idx = torch.arange(int(n_wells), dtype=torch.long)
        else:
            w_idx = None
        self.register_buffer("well_graph_idx", w_idx)

        # Temporal encoders for dynamic node types; linear static maps for static-only node types.
        self.temporal = nn.ModuleDict()
        self.static_proj = nn.ModuleDict()
        for nt in self.node_types:
            f_dyn = self.dynamic_dims[nt]
            f_stat = self.static_dims[nt]
            if f_dyn > 0:
                self.temporal[nt] = TemporalEncoder(
                    in_dyn=f_dyn,
                    in_stat=f_stat,
                    hidden=self.hidden,
                    receptive_field=self.receptive_field,
                    dropout=self.dropout,
                    chunk_size=chunk_size,
                )
            else:
                self.static_proj[nt] = nn.Linear(f_stat, self.hidden)

        # Two layers of PyG HeteroConv over all forward and rev_ edge types.
        self.convs = nn.ModuleList()
        self.spatial_norms = nn.ModuleList()
        for _ in range(self.n_spatial_layers):
            conv_map = {
                et: TemporalGraphConv((self.hidden, self.hidden), self.hidden, aggr="add", node_dim=0)
                for et in self.edge_types
            }
            self.convs.append(HeteroConv(conv_map, aggr="sum"))
            self.spatial_norms.append(nn.ModuleDict({nt: nn.LayerNorm(self.hidden) for nt in self.node_types}))
        self.drop = nn.Dropout(self.dropout)

        well_stat_dim = self.static_dims[self.well_type]
        self.decoder = nn.Sequential(
            nn.Linear(self.hidden + well_stat_dim, self.hidden),
            nn.ReLU(),
            nn.Dropout(self.dropout),
            nn.Linear(self.hidden, 1),
        )

    @classmethod
    def from_heterodata(
        cls,
        graph_data,
        dynamic_dims: dict[str, int],
        *,
        well_graph_idx=None,
        hidden: int = 32,
        receptive_field: int = 104,
        dropout: float = 0.1,
        n_spatial_layers: int = N_SPATIAL_LAYERS,
        well_type: str = "well",
        chunk_size: int = TCN_NODE_CHUNK,
    ):
        """Construct a ``HeteroSTGNN`` directly from a built ``HeteroData`` instance."""
        static_dims = {nt: int(graph_data[nt].x.size(-1)) for nt in graph_data.node_types}
        n_wells = int(graph_data[well_type].x.size(0))
        return cls(
            static_dims=static_dims,
            dynamic_dims=dynamic_dims,
            edge_types=list(graph_data.edge_types),
            well_graph_idx=well_graph_idx,
            n_wells=n_wells,
            hidden=hidden,
            receptive_field=receptive_field,
            dropout=dropout,
            n_spatial_layers=n_spatial_layers,
            well_type=well_type,
            chunk_size=chunk_size,
        )

    def forward(self, x_dyn: dict[str, torch.Tensor], graph_data) -> torch.Tensor:
        """Predict standardised head anomaly ``y_hat`` of shape ``(N_wells, T)``."""
        # Infer sequence length T from any dynamic node type.
        n_weeks = None
        for nt in self.node_types:
            if self.dynamic_dims[nt] > 0:
                n_weeks = int(x_dyn[nt].shape[1])
                break
        if n_weeks is None:
            raise ValueError("HeteroSTGNN requires at least one dynamic node type in x_dyn")

        h = {}
        for nt in self.node_types:
            x_stat = graph_data[nt].x
            if self.dynamic_dims[nt] > 0:
                h[nt] = self.temporal[nt](x_dyn[nt], x_stat)
            else:
                h[nt] = self.static_proj[nt](x_stat).unsqueeze(1).expand(-1, n_weeks, -1).contiguous()

        edge_index_dict = {et: graph_data[et].edge_index for et in self.edge_types}
        edge_weight_dict = {et: extract_edge_weight(graph_data, et) for et in self.edge_types}

        for layer_idx, conv in enumerate(self.convs):
            out = conv(h, edge_index_dict, edge_weight_dict=edge_weight_dict) if self.edge_types else {}
            norms = self.spatial_norms[layer_idx]
            next_h = {}
            for nt in self.node_types:
                base = h[nt] + out[nt] if nt in out else h[nt]
                next_h[nt] = self.drop(F.relu(norms[nt](base)))
            h = next_h

        well_h = h[self.well_type]
        well_stat = graph_data[self.well_type].x
        if self.well_graph_idx is not None:
            well_h = well_h[self.well_graph_idx]
            well_stat = well_stat[self.well_graph_idx]
        stat_exp = well_stat.unsqueeze(1).expand(-1, n_weeks, -1)
        return self.decoder(torch.cat([well_h, stat_exp], dim=-1)).squeeze(-1)


def count_parameters(net: nn.Module) -> int:
    """Total number of trainable scalar parameters in ``net``."""
    return sum(p.numel() for p in net.parameters() if p.requires_grad)


# ---------------------------------------------------------------------------
# Dynamic node inputs (training-window standardisation only)
# ---------------------------------------------------------------------------

def _load_table(tables, key, default_path):
    if tables is not None and key in tables:
        return tables[key]
    return pd.read_parquet(default_path)


def _standardise_dynamic(arr: np.ndarray, names: tuple[str, ...], train_mask: np.ndarray, obs_mask=None):
    """Standardise continuous dynamic channels using training-window entries only.

    ``arr`` has shape ``(N_nodes, T, F)``. Channels in ``FLAG_CHANNELS`` stay exact 0/1.
    Missing/non-finite entries (or entries where ``obs_mask`` is False) become ``0.0`` after
    standardisation. Returns ``(float32 array, list[str], {'mean': ..., 'sd': ...})``.
    """
    n_nodes, n_weeks, n_feat = arr.shape
    out = np.zeros((n_nodes, n_weeks, n_feat), dtype=np.float32)
    means = {}
    sds = {}
    t_mask = np.asarray(train_mask, dtype=bool)
    for j, name in enumerate(names):
        col = np.asarray(arr[:, :, j], dtype=np.float64)
        if name in FLAG_CHANNELS:
            out[:, :, j] = np.nan_to_num(col, nan=0.0).astype(np.float32)
            means[name] = 0.0
            sds[name] = 1.0
            continue
        valid = np.isfinite(col)
        if obs_mask is not None:
            valid = valid & np.asarray(obs_mask, dtype=bool)
        tr_valid = valid & t_mask[None, :]
        if tr_valid.any():
            vals = col[tr_valid]
            m = float(vals.mean())
            s = float(vals.std(ddof=0))
            if not np.isfinite(s) or s <= 0.0:
                s = 1.0
        else:
            m, s = 0.0, 1.0
        scaled = np.where(valid, (col - m) / s, 0.0)
        out[:, :, j] = scaled.astype(np.float32)
        means[name] = m
        sds[name] = s
    return out, list(names), {"mean": means, "sd": sds}


def _apply_seasonal_drinking_water(pw, pts, forcing_weekly=None):
    """Apply reconstruction-1 seasonal drinking-water profile, using injected forcing when given."""
    if forcing_weekly is None:
        return seasonal_drinking_water(pw, pts)
    f = forcing_weekly[["cell_id", "week", "ETP", "rain"]].copy()
    f["week"] = pd.to_datetime(f["week"])
    f["year"] = f["week"].dt.year
    f["deficit"] = (f["ETP"] - f["rain"]).clip(lower=0.0)
    f.loc[~f["week"].dt.month.between(4, 10), "deficit"] = 0.0
    tot = f.groupby(["cell_id", "year"])["deficit"].transform("sum")
    f["w"] = np.where(tot > 0, f["deficit"] / tot, 0.0)
    d = pw.copy()
    d["week"] = pd.to_datetime(d["week"])
    d = d.merge(pts[["code_ouvrage", "cell_id"]], on="code_ouvrage", how="left")
    dw = d["usage"] == "drinking water"
    d["year"] = d["week"].dt.year
    annual = d[dw].groupby(["code_ouvrage", "year"])["volume_m3"].transform("sum")
    d = d.merge(f[["cell_id", "week", "w"]], on=["cell_id", "week"], how="left")
    flat = d.loc[dw, "volume_m3"]
    d.loc[dw, "volume_m3"] = 0.5 * flat + 0.5 * annual * d.loc[dw, "w"].fillna(0.0)
    return d[pw.columns]


def _weather_dynamic(codes, weeks, train_mask, forcing_weekly):
    f = forcing_weekly[forcing_weekly["cell_id"].isin(codes)].copy()
    f["week"] = pd.to_datetime(f["week"])
    cols = []
    for var in DYNAMIC_CHANNELS["weather_cell"]:
        piv = f.pivot(index="week", columns="cell_id", values=var).reindex(index=weeks, columns=codes)
        cols.append(piv.to_numpy(dtype=np.float64).T)
    arr = np.stack(cols, axis=-1)
    return _standardise_dynamic(arr, DYNAMIC_CHANNELS["weather_cell"], train_mask)


def _facility_dynamic(codes, weeks, train_mask, pw, pts, forcing_weekly=None, reconstruction=1):
    """Weekly facility abstraction (thousand m3/wk) and 0/1 imputed channel (plan v3 §3.6).

    Weeks before the pumping record starts take each facility's own training-window mean with
    ``imputed = 1.0`` (unknown, not zero). Inside the record, absent facility-weeks have volume
    0.0 and ``imputed = 0.0``; if a facility has multiple usage rows in a week, ``imputed`` is 1
    when any row is flagged imputed.
    """
    n_fac, n_weeks = len(codes), len(weeks)
    if n_fac == 0:
        arr = np.zeros((0, n_weeks, 2), dtype=np.float64)
        return _standardise_dynamic(arr, DYNAMIC_CHANNELS["facility"], train_mask)

    pw_weeks = pd.to_datetime(pw["week"])
    record_start = pd.Timestamp(pw_weeks.min())
    sp = _apply_seasonal_drinking_water(pw, pts, forcing_weekly) if reconstruction != 2 else pw.copy()
    sp["week"] = pd.to_datetime(sp["week"])
    sp = sp[sp["code_ouvrage"].isin(codes)]

    if len(sp):
        vol_piv = (
            sp.groupby(["week", "code_ouvrage"])["volume_m3"].sum().unstack("code_ouvrage")
            .reindex(index=weeks, columns=codes) / 1e3
        )
        imp_piv = (
            sp.groupby(["week", "code_ouvrage"])["imputed"].any().unstack("code_ouvrage")
            .reindex(index=weeks, columns=codes)
        )
        vol = vol_piv.fillna(0.0).to_numpy(dtype=np.float64).T
        imp = imp_piv.eq(True).to_numpy(dtype=np.float64).T
    else:
        vol = np.zeros((n_fac, n_weeks), dtype=np.float64)
        imp = np.zeros((n_fac, n_weeks), dtype=np.float64)

    in_record = np.asarray(weeks >= record_start, dtype=bool)
    tr_rec = train_mask & in_record
    if tr_rec.any():
        fac_train_mean = vol[:, tr_rec].mean(axis=1, keepdims=True)
    else:
        fac_train_mean = np.zeros((n_fac, 1), dtype=np.float64)

    pre = ~in_record
    if pre.any():
        vol[:, pre] = fac_train_mean
        imp[:, pre] = 1.0

    arr = np.stack([vol, imp], axis=-1)
    return _standardise_dynamic(arr, DYNAMIC_CHANNELS["facility"], train_mask)


def _gauge_dynamic(codes, weeks, train_mask, rivers_weekly):
    """Weekly ``log1p(q_m3s)`` standardised on observed training weeks; missing weeks 0 + flag."""
    n_gauges, n_weeks = len(codes), len(weeks)
    if n_gauges == 0:
        arr = np.zeros((0, n_weeks, 2), dtype=np.float64)
        return _standardise_dynamic(arr, DYNAMIC_CHANNELS["gauge"], train_mask)

    rw = rivers_weekly[rivers_weekly["code_station"].isin(codes)].copy()
    rw["week"] = pd.to_datetime(rw["week"])
    if len(rw):
        piv = rw.pivot(index="week", columns="code_station", values="q_m3s").reindex(index=weeks, columns=codes)
        q = piv.to_numpy(dtype=np.float64).T
    else:
        q = np.full((n_gauges, n_weeks), np.nan, dtype=np.float64)

    obs = np.isfinite(q)
    logq = np.where(obs, np.log1p(np.clip(q, 0.0, None)), np.nan)
    missing = (~obs).astype(np.float64)
    arr = np.stack([logq, missing], axis=-1)
    return _standardise_dynamic(arr, DYNAMIC_CHANNELS["gauge"], train_mask, obs_mask=obs)


def _canal_dynamic(codes, weeks, train_mask, pw, pts, canal_basins_weekly=None, reconstruction=1):
    """Weekly canal volume (Mm3/week) per basin node or plain node, matching Hybrid-GNN v2."""
    n_canals, n_weeks = len(codes), len(weeks)
    if n_canals == 0:
        arr = np.zeros((0, n_weeks, 1), dtype=np.float64)
        return _standardise_dynamic(arr, DYNAMIC_CHANNELS["canal"], train_mask)

    wide_basin = None
    if canal_basins_weekly is not None and len(canal_basins_weekly):
        cb = canal_basins_weekly.copy()
        cb["week"] = pd.to_datetime(cb["week"])
        wide_basin = cb.pivot(index="week", columns="basin", values="volume_m3") / 1e6
    elif reconstruction == 3 and (DATASET_DIR / "canal_intakes_basin.parquet").is_file():
        intakes = pd.read_parquet(DATASET_DIR / "canal_intakes_basin.parquet")
        wide_basin = CB.canal_series_by_basin(intakes, pw=pw, pts=pts) / 1e6

    plain_s = canal_series(pw, pts) / 1e6
    plain_start = pd.Timestamp(plain_s.index.min()) if len(plain_s) else weeks[0]
    basin_start = pd.Timestamp(wide_basin.index.min()) if wide_basin is not None and len(wide_basin) else plain_start

    vol = np.zeros((n_canals, n_weeks), dtype=np.float64)
    for i, code in enumerate(codes):
        name = str(code)
        suffix = name.split(":", 1)[-1]
        if name == CANAL_PLAIN or wide_basin is None:
            raw = plain_s.reindex(weeks).to_numpy(dtype=np.float64)
            in_rec = np.asarray(weeks >= plain_start, dtype=bool)
        elif name in wide_basin.columns:
            raw = wide_basin[name].reindex(weeks).to_numpy(dtype=np.float64)
            in_rec = np.asarray(weeks >= basin_start, dtype=bool)
        elif suffix in wide_basin.columns:
            raw = wide_basin[suffix].reindex(weeks).to_numpy(dtype=np.float64)
            in_rec = np.asarray(weeks >= basin_start, dtype=bool)
        else:
            raise KeyError(f"canal node {name!r} matches no basin in {sorted(wide_basin.columns)}")

        # Gaps inside the record are 0; weeks before the record take the node's training mean.
        raw = np.where(in_rec & ~np.isfinite(raw), 0.0, raw)
        tr_rec = train_mask & in_rec & np.isfinite(raw)
        tr_mean = float(raw[tr_rec].mean()) if tr_rec.any() else 0.0
        vol[i] = np.where(np.isfinite(raw), raw, tr_mean)

    arr = vol[:, :, None]
    return _standardise_dynamic(arr, DYNAMIC_CHANNELS["canal"], train_mask)


def _well_dynamic(n_wells, weeks, train_mask):
    """Sin and cos of the week of year for each well (no head, no stress)."""
    doy = weeks.dayofyear.to_numpy(dtype=np.float64) / 365.25 * 2.0 * np.pi
    sc = np.stack([np.sin(doy), np.cos(doy)], axis=-1)  # (T, 2)
    arr = np.broadcast_to(sc[None, :, :], (int(n_wells), len(weeks), 2)).copy()
    return _standardise_dynamic(arr, DYNAMIC_CHANNELS["well"], train_mask)


def build_dynamic_inputs(
    graph_data,
    graph_index,
    weeks,
    *,
    train_start=None,
    reconstruction: int = 1,
    tables=None,
):
    """Build standardised weekly dynamic tensors for every dynamic node type in ``graph_data``.

    Returns ``(x_dyn_np, dynamic_cols, dynamic_stats)`` where ``x_dyn_np`` maps each dynamic
    node type present in ``graph_data`` to a float32 ndarray of shape ``(N_nt, T, F_dyn)``.
    Standardisation uses training-window weeks only (``statics.training_window(train_start)``).
    """
    weeks = pd.DatetimeIndex(weeks)
    if tables is not None and "train_window" in tables:
        start, end = (pd.Timestamp(x) for x in tables["train_window"])
    else:
        start, end, _ = statics.training_window(train_start)
    train_mask = np.asarray((weeks >= start) & (weeks <= end), dtype=bool)
    if not train_mask.any():
        raise ValueError(f"Training window [{start.date()}, {end.date()}] has no overlap with weeks")

    forcing_weekly = None
    pw = None
    pts = None
    if "weather_cell" in graph_index:
        forcing_weekly = _load_table(tables, "forcing_weekly", DATASET_DIR / "forcing_weekly.parquet")
    if any(t in graph_index for t in ("facility", "canal")):
        pw = (
            tables["pumping_weekly"]
            if tables is not None and "pumping_weekly" in tables
            else RT.pumping_table(reconstruction)
        )
        pts = _load_table(tables, "pumping_points", DATASET_DIR / "pumping_points.parquet")
        if forcing_weekly is None and tables is not None and "forcing_weekly" in tables:
            forcing_weekly = tables["forcing_weekly"]

    x_dyn = {}
    dyn_cols = {}
    dyn_stats = {}

    for nt in graph_data.node_types:
        codes = list(graph_index[nt].keys())
        if nt == "weather_cell":
            arr, cols, st = _weather_dynamic(codes, weeks, train_mask, forcing_weekly)
        elif nt == "facility":
            f_inj = forcing_weekly if (tables is not None and "forcing_weekly" in tables) else None
            arr, cols, st = _facility_dynamic(
                codes, weeks, train_mask, pw, pts, forcing_weekly=f_inj, reconstruction=reconstruction
            )
        elif nt == "gauge":
            rivers_weekly = _load_table(tables, "rivers_weekly", DATASET_DIR / "rivers_weekly.parquet")
            arr, cols, st = _gauge_dynamic(codes, weeks, train_mask, rivers_weekly)
        elif nt == "canal":
            cb_path = DATASET_DIR / "canal_basins_weekly.parquet"
            cb = (
                tables["canal_basins_weekly"]
                if tables is not None and "canal_basins_weekly" in tables
                else (pd.read_parquet(cb_path) if cb_path.is_file() else None)
            )
            arr, cols, st = _canal_dynamic(
                codes, weeks, train_mask, pw, pts, canal_basins_weekly=cb, reconstruction=reconstruction
            )
        elif nt == "well":
            arr, cols, st = _well_dynamic(len(codes), weeks, train_mask)
        else:
            # Static-only node types (e.g. aquifer_unit) have no dynamic input.
            continue
        x_dyn[nt] = arr
        dyn_cols[nt] = cols
        dyn_stats[nt] = st

    return x_dyn, dyn_cols, dyn_stats


# ---------------------------------------------------------------------------
# Training, inference, and replay
# ---------------------------------------------------------------------------

def _optimiser_groups(net: nn.Module, weight_decay: float):
    """Apply AdamW weight decay to linear/conv weights only; never biases or LayerNorm."""
    decay, no_decay = [], []
    for name, param in net.named_parameters():
        if not param.requires_grad:
            continue
        if param.ndim < 2 or name.endswith(".bias") or ".norm." in name or "spatial_norms" in name:
            no_decay.append(param)
        else:
            decay.append(param)
    groups = []
    if decay:
        groups.append({"params": decay, "weight_decay": float(weight_decay)})
    if no_decay:
        groups.append({"params": no_decay, "weight_decay": 0.0})
    return groups


def _to_device_dict(d: dict[str, np.ndarray | torch.Tensor], device: torch.device) -> dict[str, torch.Tensor]:
    return {
        k: (v.to(device) if isinstance(v, torch.Tensor) else torch.from_numpy(np.asarray(v, dtype=np.float32)).to(device))
        for k, v in d.items()
    }


def masked_mse_loss(
    y_hat: torch.Tensor,
    head: np.ndarray,
    mu: np.ndarray,
    sd_safe: np.ndarray,
    obs_loss: np.ndarray,
) -> torch.Tensor:
    """Equal-weight-per-well masked MSE on standardised head anomaly ``y_hat``.

    ``obs_loss`` is True only on observed, non-placeholder training weeks of training wells.
    Target values outside ``obs_loss`` are zeroed before tensor conversion so held-out wells'
    heads can never affect the loss or gradients (even if NaN or extreme).
    """
    mask_b = np.asarray(obs_loss, dtype=bool)
    z_np = np.where(mask_b, (head - mu) / sd_safe, 0.0).astype(np.float32)
    counts = mask_b.sum(axis=1, keepdims=True)
    n_active_wells = max(int((counts > 0).sum()), 1)
    wgt_np = (mask_b / np.maximum(counts, 1) / n_active_wells).astype(np.float32)
    z_t = torch.from_numpy(z_np).to(device=y_hat.device, dtype=y_hat.dtype)
    wgt_t = torch.from_numpy(wgt_np).to(device=y_hat.device, dtype=y_hat.dtype)
    return (wgt_t * (y_hat - z_t) ** 2).sum()


def train_seed(
    seed: int,
    data: dict,
    graph_data,
    well_graph_idx=None,
    *,
    epochs: int = 300,
    lr: float = 3e-3,
    weight_decay: float = 1e-4,
    hidden: int = 32,
    receptive_field: int = 104,
    dropout: float = 0.1,
    n_spatial_layers: int = N_SPATIAL_LAYERS,
    train_mask=None,
    keep_wells=None,
    device=None,
    state_out: dict | None = None,
    verbose: bool = True,
):
    """Train one seed of ``HeteroSTGNN`` for a fixed number of epochs (no early stopping).

    All wells run in one forward pass per epoch; AdamW with cosine-annealed learning rate.
    Returns ``(net_cpu, val_median_nse, epochs, loss_history)`` with ``net_cpu`` in ``eval()``.
    """
    torch.manual_seed(int(seed))
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(int(seed))
    torch.set_num_threads(int(os.environ.get("PFE_THREADS", 4)))

    dev = torch.device(device) if device is not None else torch.device("cuda" if torch.cuda.is_available() else "cpu")

    head, mu, sd, split, core = (data[k] for k in ("head", "mu", "sd", "split", "core"))
    sd_safe = np.maximum(sd, SD_FLOOR)
    n_wells, _ = head.shape

    if train_mask is None:
        train_mask = split == "train"
    if keep_wells is None:
        keep_wells = np.ones(n_wells, dtype=bool)
    else:
        keep_wells = np.asarray(keep_wells, dtype=bool)

    placeholder = data.get("placeholder_mask")
    obs_loss = np.isfinite(head) & np.asarray(train_mask, dtype=bool) & keep_wells[:, None]
    if placeholder is not None:
        obs_loss = obs_loss & ~np.asarray(placeholder, dtype=bool)

    z_np = np.where(obs_loss, (head - mu) / sd_safe, 0.0).astype(np.float32)
    counts = obs_loss.sum(axis=1, keepdims=True)
    n_active = max(int((counts > 0).sum()), 1)
    wgt_np = (obs_loss / np.maximum(counts, 1) / n_active).astype(np.float32)

    dynamic_dims = {nt: int(arr.shape[-1]) for nt, arr in data["x_dyn"].items()}
    net = HeteroSTGNN.from_heterodata(
        graph_data,
        dynamic_dims=dynamic_dims,
        well_graph_idx=well_graph_idx,
        hidden=hidden,
        receptive_field=receptive_field,
        dropout=dropout,
        n_spatial_layers=n_spatial_layers,
    ).to(dev)

    gd_dev = graph_data.to(dev)
    x_dyn_dev = _to_device_dict(data["x_dyn"], dev)
    z_t = torch.from_numpy(z_np).to(dev)
    wgt_t = torch.from_numpy(wgt_np).to(dev)

    opt = torch.optim.AdamW(_optimiser_groups(net, weight_decay), lr=float(lr))
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        opt, T_max=max(int(epochs), 1), eta_min=float(lr) * 1e-2
    )

    loss_history = []
    t0 = time.time()
    net.train()
    for _ in range(int(epochs)):
        y_hat = net(x_dyn_dev, gd_dev)
        loss = (wgt_t * (y_hat - z_t) ** 2).sum()
        opt.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(net.parameters(), 1.0)
        opt.step()
        scheduler.step()
        loss_history.append(float(loss.detach().cpu().item()))

    net.eval()
    with torch.no_grad():
        pz = net(x_dyn_dev, gd_dev).detach().cpu().numpy().astype(np.float32)
    es_core = core & keep_wells[:, None]
    val_score = median_nse(pz, head, split, es_core, mu, sd_safe, head)

    net_cpu = net.to("cpu")
    if state_out is not None:
        state_out.update({k: v.detach().cpu().clone() for k, v in net_cpu.state_dict().items()})

    if verbose:
        last_loss = loss_history[-1] if loss_history else float("nan")
        print(
            f"    seed {seed}: epochs {int(epochs)}, loss {last_loss:.4f}, "
            f"val median NSE {val_score:.3f} ({time.time() - t0:.1f}s)",
            flush=True,
        )
    return net_cpu, val_score, int(epochs), loss_history


def predict_seed(net: HeteroSTGNN, data: dict, graph_data, *, device=None) -> np.ndarray:
    """Compute standardised head anomaly ``pz`` ``(N_wells, T)`` in ``eval()`` mode."""
    dev = torch.device(device) if device is not None else next(net.parameters()).device
    net.eval()
    gd_dev = graph_data.to(dev)
    x_dyn_dev = _to_device_dict(data["x_dyn"], dev)
    with torch.no_grad():
        return net.to(dev)(x_dyn_dev, gd_dev).detach().cpu().numpy().astype(np.float32)


# ---------------------------------------------------------------------------
# CLI, preparation, replay, and LWO assembly
# ---------------------------------------------------------------------------

def _arm_name(s: str) -> str:
    try:
        kind, _ = RT.parse_arm(s)
    except ValueError as err:
        raise argparse.ArgumentTypeError(str(err)) from err
    if kind == "baseline":
        raise argparse.ArgumentTypeError("HeteroSTGNN requires a graph arm: C, D, or E/F control")
    return s


def arm_slug(arm: str) -> str:
    """Filesystem-safe arm identifier (e.g. ``E_degree:0`` -> ``E_degree_0``)."""
    return str(arm).replace(":", "_")


def default_run_name(arm: str, regime: str) -> str:
    """Default run folder name for ``(arm, regime)``."""
    base = f"hstgnn_{arm_slug(arm)}"
    suffix = {"R1": "", "R2": "_lwo", "R3_f25": "_f25", "R3_f50": "_f50", "refit": "_refit"}[regime]
    return base + suffix


def build_parser() -> argparse.ArgumentParser:
    """CLI argument parser matching ``src/models/hybrid_gnn.py`` conventions."""
    ap = argparse.ArgumentParser(description="Black-box Hetero-STGNN on Hybrid-GNN HeteroData (plan v3 §6)")
    ap.add_argument("--arm", type=_arm_name, default="D", help="graph arm: C, D, or E/F control")
    ap.add_argument("--policy", default="main", help="KG export policy (default: main)")
    ap.add_argument("--regime", choices=list(REGIMES), default="R1", help="evaluation regime")
    ap.add_argument("--fold", type=int, default=None, help="leave-wells-out fold (0-4; regime R2)")
    ap.add_argument("--train-start", default=None, help="explicit R3 training start override")
    ap.add_argument("--run", default=None, help="results sub-folder name")
    ap.add_argument("--seeds", type=int, nargs="*", default=list(range(10)))
    ap.add_argument("--epochs", type=int, default=300, help="fixed training epochs (no early stopping)")
    ap.add_argument("--lr", type=float, default=3e-3)
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--hidden", type=int, default=32)
    ap.add_argument("--receptive-field", type=int, default=104, help="causal TCN receptive field in weeks")
    ap.add_argument("--dropout", type=float, default=0.1)
    ap.add_argument("--n-spatial-layers", type=int, default=N_SPATIAL_LAYERS)
    ap.add_argument("--pumping-reconstruction", type=int, choices=[1, 2, 3], default=1)
    ap.add_argument("--wells", nargs="*", default=None, help="subset of wells (code_bss)")
    return ap


def _parser_defaults() -> dict:
    ap = build_parser()
    return {
        a.dest: (list(a.default) if isinstance(a.default, list) else a.default)
        for a in ap._actions
        if a.dest != "help"
    }


def args_from_config(cfg: dict) -> argparse.Namespace:
    """Rebuild an ``argparse.Namespace`` from a saved ``config.json``."""
    defaults = _parser_defaults()
    values = {k: (cfg[k] if k in cfg else v) for k, v in defaults.items()}
    return argparse.Namespace(**values)


def _canonicalize_args(args, error=None) -> dict:
    def fail(msg):
        if error is not None:
            error(msg)
        raise ValueError(msg)

    if args.epochs < 1:
        fail("--epochs must be >= 1")
    if args.hidden < 1:
        fail("--hidden must be >= 1")
    if args.receptive_field < 2:
        fail("--receptive-field must be >= 2")
    if args.weight_decay < 0:
        fail("--weight-decay must be >= 0")
    if not (0.0 <= args.dropout < 1.0):
        fail("--dropout must be in [0, 1)")

    regime = args.regime
    fold = args.fold
    train_start = args.train_start
    if fold is not None and regime == "R1":
        regime = "R2"
    if regime == "R2" and fold is None:
        fail("--regime R2 requires --fold 0..4")
    if regime != "R2" and fold is not None:
        fail(f"--fold cannot be combined with --regime {regime}")
    if regime == "R3_f25":
        train_start = train_start or R3_STARTS["f25"]
    elif regime == "R3_f50":
        train_start = train_start or R3_STARTS["f50"]
    refit = regime == "refit"

    run = args.run or default_run_name(args.arm, regime)
    return {
        "run": run,
        "arm": args.arm,
        "policy": args.policy,
        "regime": regime,
        "fold": fold,
        "train_start": train_start,
        "refit": refit,
        "reconstruction": args.pumping_reconstruction,
        "only": args.wells,
    }


def _export_dir(policy: str = "main", dataset: str = DATASET) -> Path:
    return PROCESSED / "kg" / f"export_{dataset}_{policy}"


def _build_graph_for_arm(arm: str, policy: str = "main", train_start=None, dataset: str = DATASET):
    """Build ``HeteroData`` for arm C, D, or any E/F control through the hybrid's machinery."""
    exp_dir = _export_dir(policy, dataset)
    kind, draw = RT.parse_arm(arm)
    _, meta = RT.load_arm(arm, policy, dataset)
    if draw is None and kind in ("C", "D"):
        graph_data, graph_index = build_heterodata(exp_dir, arm, train_start=train_start, policy=policy)
    else:
        edges, meta = RT.load_arm(arm, policy, dataset)
        graph_data, graph_index = build_heterodata(
            exp_dir, arm, tables={"edges": edges}, train_start=train_start, policy=policy
        )
    export_meta = {
        k: meta[k]
        for k in ("release", "policy", "code_version", "control", "export_sha256")
        if k in meta
    }
    return graph_data, graph_index, export_meta


def _placeholder_matrix(codes: list[str], weeks: np.ndarray) -> np.ndarray:
    """Boolean ``(N_wells, T)`` matrix marking suspect placeholder weeks (v4/v5)."""
    mask = np.zeros((len(codes), len(weeks)), dtype=bool)
    if DATASET < "v4":
        return mask
    df = load_placeholder_mask()
    if df is None or df.empty:
        return mask
    row_of = {c: i for i, c in enumerate(codes)}
    col_of = {pd.Timestamp(w): j for j, w in enumerate(pd.DatetimeIndex(weeks))}
    for code, wk in zip(df["code_bss"], pd.to_datetime(df["week"])):
        r = row_of.get(code)
        c = col_of.get(wk)
        if r is not None and c is not None:
            mask[r, c] = True
    return mask


def prepare(args, *, error=None, verbose: bool = True) -> dict:
    """Build panel targets, ``HeteroData``, dynamic inputs, masks, fingerprint, schema, kwargs."""
    def fail(msg):
        if error is not None:
            error(msg)
        raise ValueError(msg)

    config_args = args_from_config(vars(args))
    opt = _canonicalize_args(config_args, error=error)
    arm, policy, train_start = opt["arm"], opt["policy"], opt["train_start"]

    P = build_panel(train_start=train_start)
    P = P[P["mu"].notna()]
    if opt["only"] is not None:
        missing = sorted(set(opt["only"]) - set(P["code_bss"]))
        if missing:
            fail(f"unknown wells: {missing}")
        P = P[P["code_bss"].isin(opt["only"])]

    P = P.sort_values(["code_bss", "week"])
    codes = list(dict.fromkeys(P["code_bss"]))
    weeks = np.sort(P["week"].unique())
    n_wells, n_weeks = len(codes), len(weeks)
    piv = lambda col: P[col].to_numpy().reshape(n_wells, n_weeks)  # noqa: E731

    graph_data, graph_index, export_meta = _build_graph_for_arm(arm, policy=policy, train_start=train_start)
    well_map = graph_index["well"]
    missing_graph = [c for c in codes if c not in well_map]
    if missing_graph:
        fail(f"wells missing from HeteroData graph: {missing_graph}")
    well_graph_idx = np.array([well_map[c] for c in codes], dtype=np.int64)

    x_dyn, dyn_cols, dyn_stats = build_dynamic_inputs(
        graph_data,
        graph_index,
        weeks,
        train_start=train_start,
        reconstruction=opt["reconstruction"],
    )

    head = piv("head").astype(np.float64)
    mu = piv("mu").astype(np.float64)
    sd = piv("sd").astype(np.float64)
    split = piv("split")
    core = piv("core").astype(bool)
    placeholder_mask = _placeholder_matrix(codes, weeks)

    train_mask, keep_wells = regime_masks(
        split, weeks, codes, opt["fold"], train_start, refit=opt["refit"]
    )

    data = {
        "codes": codes,
        "weeks": weeks,
        "x_dyn": x_dyn,
        "head": head,
        "mu": mu,
        "sd": sd,
        "split": split,
        "core": core,
        "placeholder_mask": placeholder_mask,
    }

    inputs = [f"{nt}:{col}" for nt in sorted(dyn_cols) for col in dyn_cols[nt]]
    graph_hash = hashlib.sha256()
    for nt in sorted(graph_data.node_types):
        graph_hash.update(nt.encode())
        graph_hash.update(np.ascontiguousarray(graph_data[nt].x.numpy(), dtype=np.float32).tobytes())
    for et in sorted(graph_data.edge_types):
        graph_hash.update(str(et).encode())
        graph_hash.update(np.ascontiguousarray(graph_data[et].edge_index.numpy(), dtype=np.int64).tobytes())
        graph_hash.update(np.ascontiguousarray(extract_edge_weight(graph_data, et).numpy(), dtype=np.float32).tobytes())

    fp_extra = {
        "model": "hetero_stgnn",
        "dilations": list(dilations_for_receptive_field(config_args.receptive_field)),
        "graph_sha256_16": graph_hash.hexdigest()[:16],
    }
    if export_meta:
        fp_extra["export_release"] = export_meta.get("release")
        if "export_sha256" in export_meta:
            fp_extra["export_sha256"] = export_meta["export_sha256"]

    fingerprint = run_fingerprint(config_args, inputs, fp_extra)
    schema = {
        "model": "hetero_stgnn",
        "nodes": codes,
        "weeks": [str(weeks[0])[:10], str(weeks[-1])[:10]],
        "inputs": inputs,
        "dynamic_cols": dyn_cols,
        "dynamic_stats": dyn_stats,
        "node_counts": {nt: int(graph_data[nt].x.shape[0]) for nt in graph_data.node_types},
        "edge_counts": {":".join(et): int(graph_data[et].edge_index.shape[1]) for et in graph_data.edge_types},
        "arm": arm,
        "policy": policy,
        "regime": opt["regime"],
        "hidden": config_args.hidden,
        "receptive_field": config_args.receptive_field,
        "dilations": list(dilations_for_receptive_field(config_args.receptive_field)),
        "n_spatial_layers": config_args.n_spatial_layers,
        "export": export_meta,
    }

    dynamic_dims = {nt: int(arr.shape[-1]) for nt, arr in x_dyn.items()}
    model_kwargs = {
        "dynamic_dims": dynamic_dims,
        "well_graph_idx": well_graph_idx,
        "hidden": config_args.hidden,
        "receptive_field": config_args.receptive_field,
        "dropout": config_args.dropout,
        "n_spatial_layers": config_args.n_spatial_layers,
    }

    if verbose:
        n_nodes = sum(int(graph_data[nt].x.shape[0]) for nt in graph_data.node_types)
        n_edges = sum(int(graph_data[et].edge_index.shape[1]) for et in graph_data.edge_types)
        print(
            f"HeteroSTGNN arm {arm} ({policy}), regime {opt['regime']}: "
            f"{n_wells} wells x {n_weeks} weeks, {n_nodes} graph nodes, {n_edges} directed edges, "
            f"d={config_args.hidden}, rf={config_args.receptive_field}",
            flush=True,
        )

    return opt | {
        "P": P,
        "data": data,
        "graph_data": graph_data,
        "graph_index": graph_index,
        "well_graph_idx": well_graph_idx,
        "train_mask": train_mask,
        "keep_wells": keep_wells,
        "inputs": inputs,
        "fp_extra": fp_extra,
        "fingerprint": fingerprint,
        "schema": schema,
        "config_args": config_args,
        "model_kwargs": model_kwargs,
    }


def _resolve_run_dir(run_dir) -> Path:
    path = Path(run_dir)
    if (path / "config.json").is_file() or path.is_absolute():
        return path
    return RESULTS / run_dir


def load_seed_model(run_dir, seed: int, *, prep: dict | None = None, device=None):
    """Rebuild a saved ``HeteroSTGNN`` seed from ``config.json`` and ``seed_<seed>.pt``.

    Returns ``(net, data, graph_data)`` with ``net`` in ``eval()`` mode.
    """
    folder = _resolve_run_dir(run_dir)
    cfg_path = folder / "config.json"
    if not cfg_path.is_file():
        raise FileNotFoundError(f"Missing config.json in {folder}")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    if cfg.get("dataset") is not None and cfg["dataset"] != DATASET:
        raise ValueError(
            f"{folder}: saved for dataset {cfg['dataset']!r}, active PFE_DATASET is {DATASET!r}"
        )
    if prep is None:
        prep = prepare(args_from_config(cfg), verbose=False)

    net = HeteroSTGNN.from_heterodata(prep["graph_data"], **prep["model_kwargs"])
    ckpt_path = folder / f"seed_{seed}.pt"
    if not ckpt_path.is_file():
        raise FileNotFoundError(f"Missing checkpoint {ckpt_path}")
    ckpt = load_checkpoint(ckpt_path)
    net.load_state_dict(ckpt["state_dict"], strict=True)
    if device is not None:
        net = net.to(device)
    net.eval()
    return net, prep["data"], prep["graph_data"]


def replay(run_dir, seed: int, *, prep: dict | None = None, device=None) -> pd.DataFrame:
    """Recompute a seed's predictions from its saved checkpoint ``seed_<seed>.pt``.

    Returns a DataFrame with columns ``code_bss, week, z, pred`` where ``pred = mu + sd * z``
    in metres (using the same ``SD_FLOOR`` as ``hybrid_gnn``).
    """
    net, data, graph_data = load_seed_model(run_dir, seed, prep=prep, device=device)
    pz = predict_seed(net, data, graph_data, device=device)
    sd_safe = np.maximum(data["sd"], SD_FLOOR)
    pred_m = data["mu"] + sd_safe * pz
    idx = pd.MultiIndex.from_product(
        [data["codes"], pd.DatetimeIndex(data["weeks"])], names=["code_bss", "week"]
    )
    return pd.DataFrame(
        {"z": pz.reshape(-1), "pred": pred_m.reshape(-1).astype(np.float64)}, index=idx
    ).reset_index()


def assemble_lwo(run: str, seeds=None, *, score: bool | None = None):
    """Assemble held-out leave-wells-out predictions from ``fold_0..4`` into ``predictions.parquet``.

    Uses ``SD_FLOOR`` exactly like ``hybrid_gnn`` and scores via ``evaluate_run`` unless
    ``score=False`` or ``PFE_NO_SCORE=1``.
    """
    splits = json.loads((DATASET_DIR / "splits.json").read_text(encoding="utf-8"))
    folds = splits["leave_wells_out"]["fold_of_well"]
    P = build_panel()
    musd = P.drop_duplicates("code_bss").set_index("code_bss")[["mu", "sd"]]
    want = sorted(list(range(10)) if seeds is None else [int(s) for s in seeds])

    parts = []
    for k in range(N_FOLDS):
        fold_dir = RESULTS / run / f"fold_{k}"
        files = sorted(fold_dir.glob("seed_*.parquet"))
        got = sorted(int(f.stem.split("_")[1]) for f in files)
        if got != want:
            raise FileNotFoundError(f"{run}/fold_{k} has seeds {got}, expected {want}")
        z = pd.concat(pd.read_parquet(fold_dir / f"seed_{s}.parquet") for s in want)
        z = z[z["code_bss"].map(folds) == k]
        parts.append(
            z.groupby(["code_bss", "week"])["z"].agg(["mean", "std"]).reset_index().assign(n_seeds=len(want))
        )
    z = pd.concat(parts, ignore_index=True).join(musd, on="code_bss")
    sd = z["sd"].clip(lower=SD_FLOOR)
    pred = pd.DataFrame({
        "code_bss": z["code_bss"],
        "week": z["week"],
        "pred": z["mu"] + sd * z["mean"],
        "pred_seed_sd": sd * z["std"],
        "task": "simulation",
        "horizon": 0,
    }).dropna(subset=["pred"])
    out = RESULTS / run
    out.mkdir(parents=True, exist_ok=True)
    pred.to_parquet(out / "predictions.parquet", index=False)
    do_score = (os.environ.get(NO_SCORE_ENV) != "1") if score is None else bool(score)
    if do_score:
        return evaluate_run(run)
    return pred


def _require_train_guard():
    if os.environ.get(ALLOW_TRAIN_ENV) != "1":
        raise SystemExit(
            f"Refusing to train HeteroSTGNN without {ALLOW_TRAIN_ENV}=1 "
            "(training runs on Colab, not the laptop)."
        )


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    _canonicalize_args(args, error=ap.error)
    _require_train_guard()

    prep = prepare(args, error=ap.error, verbose=True)
    P, data, graph_data = prep["P"], prep["data"], prep["graph_data"]
    run = prep["run"]
    fold = prep["fold"]
    out = RESULTS / run / (f"fold_{fold}" if fold is not None else "")
    out.mkdir(parents=True, exist_ok=True)

    fp = write_config(out, prep["config_args"], prep["inputs"], prep["fp_extra"])
    write_schema(out, prep["schema"])

    for s in args.seeds:
        path = out / f"seed_{s}.parquet"
        if cached_seed(path, fp):
            continue
        state = {}
        net, val_score, n_ep, _ = train_seed(
            s,
            data,
            graph_data,
            prep["well_graph_idx"],
            epochs=args.epochs,
            lr=args.lr,
            weight_decay=args.weight_decay,
            hidden=args.hidden,
            receptive_field=args.receptive_field,
            dropout=args.dropout,
            n_spatial_layers=args.n_spatial_layers,
            train_mask=prep["train_mask"],
            keep_wells=prep["keep_wells"],
            state_out=state,
            verbose=True,
        )
        pz = predict_seed(net, data, graph_data, device="cpu")
        save_seed_model(out, s, state, val_score, n_ep, fp)
        save_seed(path, pz, data["codes"], data["weeks"], val_score, n_ep, fp)
        write_manifest(out, vars(prep["config_args"]) | {"fingerprint": fp}, [s])

    if fold is not None or os.environ.get(NO_SCORE_ENV) == "1":
        return

    pred, n = seed_mean_predictions(out, P.assign(sd=P["sd"].clip(lower=SD_FLOOR)), args.seeds)
    pred.to_parquet(out / "predictions.parquet", index=False)
    summary = evaluate_run(run)
    core_s = summary[(summary["group"] == "all core") & (summary["variant"] == "all")]
    print(f"== {run} ({n} seeds)")
    print(core_s[["split", "n_wells", "NSE", "skill", "KGE", "RMSE"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
