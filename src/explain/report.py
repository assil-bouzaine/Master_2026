"""One-well, one-period explanation report in English and French (Phase 5, SO4, CQ10).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m src.explain.report \\
        p4_B4_D_soft1_r1 10964X0119/NYLS-1 --target 2024-06-01:2024-09-30
    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m src.explain.report \\
        p4_B4_D_soft1_r1 10906X0039/C2-1 --target 2024-06-01:2024-09-30 --lang fr

Why this module exists (docs/analysis_plan.md §12; docs/notes/step15_explanations.md)
------------------------------------------------------------------------------------
Phase 5 turns the hybrid model's exact additive decomposition into a readable report for a
hydrologist or decision-maker. For one well and one inclusive target window, the report brings
together four pieces that were built and tested separately:

1. Exact per-group contributions, seed spread, sign agreement, and data-quality flags
   (``src/explain/contributions.py``).
2. Observed vs. simulated groundwater head and monthly BRGM IPS drought classes computed with
   the well's frozen training-period observed reference (reusing ``src/analysis/hydro_errors.py``'s
   ``references``, ``to_sgi``, and ``classify`` — never a new threshold table).
3. Rule-checked English and French statements (``src/explain/statements.py``), withholding claims
   that fail the pre-registered stability, reconstruction-agreement, size, or imputation rules,
   and stating caveats for qualified claims.
4. The real-world knowledge-graph records behind each stated driver (``src/explain/chains.py``):
   top abstraction facilities by declared annual volume with their share of the routed pumping
   volume, SAFRAN weather cells over the monitored unit's outcrop, river gauge and path type,
   canal intake group, and the count and declared total of nearby unattributed facilities.

Withheld driver groups list their reasons and get neither a statement sentence nor a records
subsection. Every report ends with the caveat that the decomposition explains the model's
computation, not measured physical effects.
"""
from __future__ import annotations

import argparse
from collections.abc import Iterable, Mapping
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyoxigraph as ox

from src.analysis import hydro_errors as H
from src.config import DATASET
from src.explain.chains import (
    REPORT_GROUP_ORDER as CHAIN_GROUP_ORDER,
    VALID_ARMS as CHAIN_ARMS,
    cached_store,
    chains,
)
from src.explain.contributions import (
    GROUPS_PATH,
    _dataset_dir,
    _load_pumping_for_flags,
    _parse_window,
    _run_dir,
    decompose,
    load_groups,
)
from src.explain.statements import (
    _date_range,
    _reference_text,
    statements,
)
from src.kg.build_kg import GROUP_LABELS
from src.models.routing import load_arm

VALID_LANGS = ("en", "fr")
DRIVER_REPORT_GROUPS = tuple(CHAIN_GROUP_ORDER)
_CONFIDENCE_RANK = {"Confident": 0, "Probable": 1, "Possible": 2}

CAVEAT_LINE = {
    "en": (
        "These numbers explain the model's computation (an exact decomposition); "
        "they are not measured physical effects."
    ),
    "fr": (
        "Ces chiffres expliquent le calcul du modèle (une décomposition exacte) ; "
        "ce ne sont pas des effets physiques mesurés."
    ),
}

_STATUS_LABEL = {
    "accepted": {"en": "accepted", "fr": "retenu"},
    "qualified": {"en": "qualified", "fr": "nuancé"},
    "withheld": {"en": "withheld", "fr": "non retenu"},
}

_GROUP_SHORT = {
    "recharge": {"en": "Recharge proxy", "fr": "Indicateur de recharge"},
    "pumping_attributed": {
        "en": "Pumping on the graph's links",
        "fr": "Prélèvements reliés par le graphe",
    },
    "pumping_unattributed": {
        "en": "Unattributed pumping nearby",
        "fr": "Prélèvements voisins non attribués",
    },
    "canal": {"en": "Canal diversions", "fr": "Dérivations des canaux"},
    "river": {"en": "River stage proxy", "fr": "Indicateur du niveau du cours d'eau"},
    "residual": {"en": "Fixed seasonal residual", "fr": "Résidu saisonnier fixe"},
}

_REASON_LABEL = {
    "high_imputed_pumping_share": {
        "en": "high imputed pumping share (> 10 %)",
        "fr": "part élevée de prélèvements imputés (> 10 %)",
    },
    "low_sign_agreement": {
        "en": "low sign agreement across starts (< 80 %)",
        "fr": "faible accord de signe entre départs (< 80 %)",
    },
    "pumping_reconstruction_sign_disagreement": {
        "en": "pumping reconstructions disagree on sign",
        "fr": "désaccord de signe entre reconstructions de prélèvements",
    },
    "small_contribution": {
        "en": "small contribution (< 0.05 m)",
        "fr": "contribution faible (< 0,05 m)",
    },
    "no_observed_weeks": {
        "en": "no observed weeks in window",
        "fr": "aucune semaine observée sur la période",
    },
    "low_validated_observation_share": {
        "en": "low share of validated observed weeks (< 50 %)",
        "fr": "faible part de semaines observées validées (< 50 %)",
    },
    "imputed_pumping": {
        "en": "imputed routed pumping volume (0–10 %)",
        "fr": "volume de prélèvement acheminé partiellement imputé (0–10 %)",
    },
    "probable_only": {
        "en": "knowledge-graph path rests only on probable links",
        "fr": "chemin du graphe reposant uniquement sur des liens probables",
    },
}

_RECON_FR = {
    1: "profil courant",
    2: "eau potable constante",
    3: "calendrier cultural",
}

_WATER_USE_LABEL = {
    "drinking water": {"en": "drinking water", "fr": "eau potable"},
    "irrigation": {"en": "irrigation", "fr": "irrigation"},
    "industry": {"en": "industry", "fr": "industrie"},
    "canal supply": {"en": "canal supply", "fr": "alimentation de canal"},
    "energy": {"en": "energy", "fr": "énergie"},
}

_CONFIDENCE_LABEL = {
    "Confident": {"en": "confident", "fr": "sûr"},
    "Probable": {"en": "probable", "fr": "probable"},
    "Possible": {"en": "possible", "fr": "possible"},
}

_ASSOC_TYPE_LABEL = {
    "OnOutcrop": {"en": "on outcrop", "fr": "sur l'affleurement"},
    "OverCover": {"en": "over cover", "fr": "sur la couverture"},
    "DocumentedLateral": {"en": "documented lateral", "fr": "latéral documenté"},
}

_AQUIFER_GROUP_EXTRA = {
    "other": ("other", "autre"),
}

# Per-process caches so generating many reports stays fast.
_WELL_KG_CACHE: dict[int, tuple[dict[str, dict[str, str | None]], dict[str, str]]] = {}
_HEADS_CACHE: dict[str, pd.DataFrame] = {}
_WELLS_TABLE_CACHE: dict[str, pd.DataFrame] = {}


def clear_cache() -> None:
    """Clear per-process caches of KG well/unit labels and dataset tables."""
    _WELL_KG_CACHE.clear()
    _HEADS_CACHE.clear()
    _WELLS_TABLE_CACHE.clear()


def _fmt_num(value: float, digits: int, lang: str, *, signed: bool = False) -> str:
    if value is None or not np.isfinite(value):
        return "n/a" if lang == "en" else "n.d."
    fmt = f"{value:+.{digits}f}" if signed else f"{value:.{digits}f}"
    return fmt.replace(".", ",") if lang == "fr" else fmt


def _fmt_int(value: float | int, lang: str) -> str:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "n/a" if lang == "en" else "n.d."
    s = f"{round(float(value)):,}"
    return s.replace(",", "\u202f") if lang == "fr" else s


def _fmt_pct(share: float, lang: str, digits: int = 1) -> str:
    if share is None or not np.isfinite(share):
        return "n/a" if lang == "en" else "n.d."
    text = f"{share * 100.0:.{digits}f}"
    if lang == "fr":
        text = text.replace(".", ",")
    return f"{text} %"


def _translate_use(use: str | None, lang: str) -> str:
    if not use or pd.isna(use):
        return "—"
    parts = [p.strip() for p in str(use).split(",") if p.strip()]
    mapped = [_WATER_USE_LABEL.get(p, {}).get(lang, p) for p in parts]
    return ", ".join(mapped) if mapped else "—"


def _translate_confidence(conf: str | None, lang: str) -> str:
    if not conf or pd.isna(conf):
        return "—"
    parts = [p.strip() for p in str(conf).split(",") if p.strip()]
    mapped = [_CONFIDENCE_LABEL.get(p, {}).get(lang, p) for p in parts]
    return ", ".join(mapped) if mapped else "—"


def _translate_assoc(assoc: str | None, lang: str) -> str:
    if not assoc or pd.isna(assoc):
        return "—"
    parts = [p.strip() for p in str(assoc).split(",") if p.strip()]
    mapped = [_ASSOC_TYPE_LABEL.get(p, {}).get(lang, p) for p in parts]
    return ", ".join(mapped) if mapped else "—"


def _translate_via(via_code: str | None, lang: str) -> str:
    if not via_code or pd.isna(via_code):
        return "—"
    parts = [p.strip() for p in str(via_code).split(",") if p.strip()]
    out = []
    for p in parts:
        if p == "alluvium":
            out.append("alluvions" if lang == "fr" else "alluvium")
        else:
            out.append(p)
    return ", ".join(out) if out else "—"


def _translate_aquifer_group(group: str | None, lang: str) -> str:
    if not group or pd.isna(group):
        return "unknown" if lang == "en" else "inconnu"
    idx = 0 if lang == "en" else 1
    if group in GROUP_LABELS:
        return GROUP_LABELS[group][idx]
    if group in _AQUIFER_GROUP_EXTRA:
        return _AQUIFER_GROUP_EXTRA[group][idx]
    return str(group)


def _format_reason(code: str, lang: str) -> str:
    label = _REASON_LABEL.get(code, {}).get(lang)
    return f"{label} (`{code}`)" if label else f"`{code}`"


def _kg_well_and_unit_index(
    store: ox.Store,
) -> tuple[dict[str, dict[str, str | None]], dict[str, str]]:
    """Index piezometer labels, monitored units, and unit labels from the knowledge graph."""
    key = id(store)
    if key in _WELL_KG_CACHE:
        return _WELL_KG_CACHE[key]

    wells_meta: dict[str, dict[str, str | None]] = {}
    for r in store.query(
        """
        PREFIX lulcw: <https://w3id.org/lulcw#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT ?c ?lbl ?ucode ?ulbl WHERE {
            ?w a lulcw:Piezometer ; lulcw:bssCode ?c .
            OPTIONAL { ?w rdfs:label ?lbl . }
            OPTIONAL {
                ?w lulcw:monitors ?u .
                OPTIONAL { ?u lulcw:bdlisaCode ?ucode . }
                OPTIONAL { ?u rdfs:label ?ulbl . }
            }
        }
        """
    ):
        code = r["c"].value
        entry = wells_meta.setdefault(
            code,
            {"label": None, "unit_code": None, "unit_label": None},
        )
        if entry["label"] is None and r["lbl"] is not None:
            entry["label"] = r["lbl"].value
        if entry["unit_code"] is None and r["ucode"] is not None:
            entry["unit_code"] = r["ucode"].value
        if entry["unit_label"] is None and r["ulbl"] is not None:
            entry["unit_label"] = r["ulbl"].value

    unit_labels: dict[str, str] = {}
    for r in store.query(
        """
        PREFIX lulcw: <https://w3id.org/lulcw#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT ?code ?lbl WHERE {
            ?u lulcw:bdlisaCode ?code ; rdfs:label ?lbl .
        }
        """
    ):
        code = r["code"].value
        if code not in unit_labels:
            unit_labels[code] = r["lbl"].value

    _WELL_KG_CACHE[key] = (wells_meta, unit_labels)
    return wells_meta, unit_labels


def _load_wells_table(dataset: str, dataset_dir: str | Path | None = None) -> pd.DataFrame:
    ds = _dataset_dir(dataset, dataset_dir)
    key = str(ds.resolve())
    if key not in _WELLS_TABLE_CACHE:
        path = ds / "wells.parquet"
        _WELLS_TABLE_CACHE[key] = pd.read_parquet(path) if path.is_file() else pd.DataFrame()
    return _WELLS_TABLE_CACHE[key]


def _load_masked_heads(dataset: str, dataset_dir: str | Path | None = None) -> pd.DataFrame:
    """Load ``heads_weekly.parquet`` with suspect placeholder weeks removed (v4+)."""
    ds = _dataset_dir(dataset, dataset_dir)
    key = f"{ds.resolve()}::{dataset}"
    if key not in _HEADS_CACHE:
        heads = pd.read_parquet(
            ds / "heads_weekly.parquet",
            columns=["code_bss", "week", "head"],
        )
        heads["week"] = pd.to_datetime(heads["week"])
        if dataset_dir is None and dataset == DATASET:
            heads = H.masked_heads(heads)
        elif dataset >= "v4":
            mask_path = ds / "placeholder_weeks.parquet"
            if mask_path.is_file():
                mask = pd.read_parquet(mask_path)
                mask["week"] = pd.to_datetime(mask["week"])
                heads = heads.merge(
                    mask.assign(_flag=True), on=["code_bss", "week"], how="left"
                )
                heads = heads[heads["_flag"].isna()].drop(columns="_flag")
        _HEADS_CACHE[key] = heads
    return _HEADS_CACHE[key]


def _well_info(
    well: str,
    *,
    dataset: str = DATASET,
    dataset_dir: str | Path | None = None,
    store: ox.Store | None = None,
) -> tuple[dict[str, str | None], dict[str, str]]:
    """Return ``(well_meta, unit_labels)`` combining the knowledge graph and ``wells.parquet``."""
    info: dict[str, str | None] = {
        "code_bss": well,
        "label": None,
        "unit_code": None,
        "unit_label": None,
        "aquifer_group": None,
    }
    unit_labels: dict[str, str] = {}
    if store is not None:
        kg_wells, unit_labels = _kg_well_and_unit_index(store)
        if well in kg_wells:
            info.update(kg_wells[well])

    wt = _load_wells_table(dataset, dataset_dir)
    if not wt.empty and "code_bss" in wt.columns:
        row = wt[wt["code_bss"] == well]
        if not row.empty:
            r = row.iloc[0]
            if info["aquifer_group"] is None and "group" in wt.columns and pd.notna(r["group"]):
                info["aquifer_group"] = str(r["group"])
            if info["unit_code"] is None and "code_bdlisa" in wt.columns and pd.notna(r["code_bdlisa"]):
                info["unit_code"] = str(r["code_bdlisa"])
                if info["unit_label"] is None:
                    info["unit_label"] = unit_labels.get(info["unit_code"])
    return info, unit_labels


def _simulated_and_observed(
    run_dir: Path,
    well: str,
    target: tuple[str, str],
    *,
    dataset: str = DATASET,
    dataset_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Compute window mean simulated/observed heads and monthly SGI classes.

    Reuses ``src.analysis.hydro_errors`` (``references``, ``to_sgi``, ``classify``, ``CLASSES``)
    with the well's frozen training-period observed reference and placeholder-masked observations.
    """
    t_start, t_end = _parse_window(target)
    pred_path = run_dir / "predictions.parquet"
    pred = pd.read_parquet(pred_path)
    if "task" in pred.columns:
        pred = pred[pred["task"] == "simulation"]
    if "horizon" in pred.columns:
        pred = pred[pred["horizon"] == 0]
    pred = pred[pred["code_bss"] == well][["code_bss", "week", "pred"]].copy()
    pred["week"] = pd.to_datetime(pred["week"])
    pred_win = pred[pred["week"].between(t_start, t_end)].sort_values("week")

    heads = _load_masked_heads(dataset, dataset_dir)
    well_heads = heads[heads["code_bss"] == well].copy()
    obs_win = well_heads[
        well_heads["week"].between(t_start, t_end) & well_heads["head"].notna()
    ].sort_values("week")

    mean_sim = float(pred_win["pred"].mean()) if not pred_win.empty else float("nan")
    mean_obs = float(obs_win["head"].mean()) if not obs_win.empty else float("nan")

    # Frozen observed training reference for this well (identical to hydro_errors.references).
    refs = H.references(well_heads)

    # Monthly SGI: use the same observed weeks for both obs and sim when a month has observed
    # weeks (matching hydro_errors.monthly_classes), falling back to all simulated weeks in any
    # unobserved month so simulated SGI is still reported.
    merged = pred_win.merge(
        obs_win[["code_bss", "week", "head"]], on=["code_bss", "week"], how="left"
    )
    merged["month"] = merged["week"].dt.to_period("M").dt.to_timestamp()

    monthly_rows: list[dict[str, Any]] = []
    for month, grp in merged.groupby("month", sort=True):
        obs_sub = grp[grp["head"].notna()]
        n_obs_m = int(len(obs_sub))
        if n_obs_m > 0:
            obs_m = float(obs_sub["head"].mean())
            sim_m = float(obs_sub["pred"].mean())
        else:
            obs_m = float("nan")
            sim_m = float(grp["pred"].mean())
        cal_month = np.array([int(month.month)], dtype=int)
        z_obs = float(H.to_sgi(well, cal_month, np.array([obs_m], dtype=float), refs)[0])
        z_sim = float(H.to_sgi(well, cal_month, np.array([sim_m], dtype=float), refs)[0])
        c_obs_i = int(H.classify(np.array([z_obs], dtype=float))[0])
        c_sim_i = int(H.classify(np.array([z_sim], dtype=float))[0])
        monthly_rows.append(
            {
                "month": month.strftime("%Y-%m"),
                "n_weeks_sim": int(len(grp)),
                "n_weeks_obs": n_obs_m,
                "obs_head_m": obs_m,
                "sim_head_m": sim_m,
                "sgi_obs": z_obs,
                "class_obs": H.CLASSES[c_obs_i] if c_obs_i >= 0 else None,
                "sgi_sim": z_sim,
                "class_sim": H.CLASSES[c_sim_i] if c_sim_i >= 0 else None,
            }
        )

    return {
        "mean_sim_head_m": mean_sim,
        "mean_obs_head_m": mean_obs,
        "n_sim_weeks": int(len(pred_win)),
        "n_obs_weeks_unmasked": int(len(obs_win)),
        "monthly_sgi": monthly_rows,
    }


def _window_volume_year(target: tuple[str, str]) -> int:
    """Pick the calendar year for facility declared volumes (majority of days/weeks, latest tie)."""
    t_start, t_end = _parse_window(target)
    if t_start.year == t_end.year:
        return int(t_start.year)
    days = pd.date_range(t_start, t_end, freq="D")
    counts = days.year.value_counts()
    max_count = int(counts.max())
    return max(int(y) for y, c in counts.items() if int(c) == max_count)


def _probable_only_map(chain_df: pd.DataFrame | None, arm: str | None) -> dict[str, bool]:
    """Flag each KG report group whose selected influences rest exclusively on 'Probable' links."""
    if chain_df is None or chain_df.empty or arm != "D":
        return {}
    out: dict[str, bool] = {}
    for group in ("recharge", "pumping_attributed", "river", "canal"):
        sub = chain_df[chain_df["report_group"] == group]
        confs = {str(c) for c in sub["confidence"].dropna().unique()}
        out[group] = confs == {"Probable"}
    return out


def _ordered_report_groups(
    present: Iterable[str],
    groups_df: pd.DataFrame | None = None,
) -> list[str]:
    if groups_df is None:
        groups_df = load_groups()
    present_set = set(present)
    ordered = [g for g in dict.fromkeys(groups_df["report_group"]) if g in present_set]
    ordered.extend(sorted(present_set - set(ordered)))
    return ordered


def _routed_pumping_by_facility(
    well: str,
    target: tuple[str, str],
    arm: str,
    policy: str,
    reconstruction: int,
    *,
    dataset: str = DATASET,
    dataset_dir: str | Path | None = None,
) -> tuple[dict[str, float], dict[str, float]]:
    """Return ``(edge_weight_by_fac, routed_window_m3_by_fac)`` for ``relation == 'pumping'``."""
    edges, _ = load_arm(arm, policy=policy, dataset=dataset)
    pe = edges[(edges["dst"] == well) & (edges["relation"] == "pumping")]
    if pe.empty:
        return {}, {}
    weights = dict(zip(pe["src"].astype(str), pe["weight"].astype(float)))
    t_start, t_end = _parse_window(target)
    years = set(range(t_start.year, t_end.year + 1))
    pw = _load_pumping_for_flags(
        reconstruction,
        dataset=dataset,
        dataset_dir=dataset_dir,
        facilities=set(weights),
        years=years,
    )
    if pw.empty:
        return weights, {}
    pw = pw.copy()
    pw["week"] = pd.to_datetime(pw["week"])
    pw_win = pw[pw["week"].between(t_start, t_end)]
    vol_by_fac = pw_win.groupby("code_ouvrage")["volume_m3"].sum().to_dict()
    routed = {fac: weights[fac] * float(vol_by_fac.get(fac, 0.0)) for fac in weights}
    return weights, routed


def _dedup_facilities(sub: pd.DataFrame) -> pd.DataFrame:
    """Collapse multi-path KG rows into one row per facility (never double-counting volumes)."""
    if sub.empty:
        return sub.copy()
    rows: list[dict[str, Any]] = []
    for code, grp in sub.groupby("driver_code", sort=False):
        first = grp.iloc[0]
        vias = sorted({str(v) for v in grp["via_code"].dropna().unique() if str(v)})
        confs = sorted(
            {str(c) for c in grp["confidence"].dropna().unique() if str(c)},
            key=lambda c: _CONFIDENCE_RANK.get(c, 99),
        )
        rows.append(
            {
                "driver_code": str(code),
                "label": first["label"] if pd.notna(first["label"]) else None,
                "water_use": first["water_use"] if pd.notna(first["water_use"]) else None,
                "via_code": ", ".join(vias) if vias else None,
                "distance_m": float(grp["distance_m"].min()) if grp["distance_m"].notna().any() else float("nan"),
                "confidence": ", ".join(confs) if confs else None,
                "annual_volume_m3": float(first["annual_volume_m3"]) if pd.notna(first["annual_volume_m3"]) else float("nan"),
                "record_kind": first["record_kind"] if pd.notna(first["record_kind"]) else None,
                "volume_year": int(first["volume_year"]) if pd.notna(first["volume_year"]) else None,
                "path": str(first["path"]),
            }
        )
    return pd.DataFrame(rows)


def _summarize_records(
    chain_df: pd.DataFrame | None,
    stated_groups: set[str],
    *,
    top: int,
    volume_year: int | None,
    unit_labels: dict[str, str],
    edge_weights: dict[str, float] | None = None,
    routed_window_m3: dict[str, float] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build structured driver-record summaries only for groups with an accepted/qualified statement."""
    records: dict[str, dict[str, Any]] = {}
    if chain_df is None:
        return records

    for group in DRIVER_REPORT_GROUPS:
        if group not in stated_groups:
            continue
        sub = chain_df[chain_df["report_group"] == group]

        if group == "pumping_attributed":
            facs = _dedup_facilities(sub)
            n_total = int(len(facs))
            n_declared = int(facs["annual_volume_m3"].notna().sum()) if n_total else 0
            total_decl = float(facs["annual_volume_m3"].dropna().sum()) if n_declared else 0.0
            if n_total:
                ranked = facs.sort_values(
                    ["annual_volume_m3", "distance_m", "driver_code"],
                    ascending=[False, True, True],
                    na_position="last",
                    kind="mergesort",
                )
                top_df = ranked.head(top)
                top_codes = set(top_df["driver_code"])
                # Share of routed pumping volume carried by the listed top facilities.
                share_routed = float("nan")
                share_basis = "none"
                if routed_window_m3:
                    tot_r = math.fsum(routed_window_m3.get(c, 0.0) for c in facs["driver_code"])
                    if tot_r > 0.0:
                        top_r = math.fsum(routed_window_m3.get(c, 0.0) for c in top_codes)
                        share_routed = top_r / tot_r
                        share_basis = "window_routed"
                if not np.isfinite(share_routed) and edge_weights and n_declared:
                    tot_rw = math.fsum(
                        edge_weights.get(r.driver_code, 1.0) * r.annual_volume_m3
                        for r in facs.itertuples(index=False)
                        if pd.notna(r.annual_volume_m3)
                    )
                    if tot_rw > 0.0:
                        top_rw = math.fsum(
                            edge_weights.get(r.driver_code, 1.0) * r.annual_volume_m3
                            for r in top_df.itertuples(index=False)
                            if pd.notna(r.annual_volume_m3)
                        )
                        share_routed = top_rw / tot_rw
                        share_basis = "weighted_declared"
                if not np.isfinite(share_routed) and total_decl > 0.0:
                    top_d = float(top_df["annual_volume_m3"].dropna().sum())
                    share_routed = top_d / total_decl
                    share_basis = "declared"
                top_rows = top_df.to_dict(orient="records")
                path_kind = str(facs["path"].iloc[0])
            else:
                top_rows = []
                share_routed = float("nan")
                share_basis = "none"
                path_kind = "knowledge graph"
            records[group] = {
                "total_count": n_total,
                "declared_count": n_declared,
                "total_declared_m3": total_decl,
                "volume_year": volume_year,
                "top_facilities": top_rows,
                "share_routed_volume": share_routed,
                "share_basis": share_basis,
                "path": path_kind,
            }

        elif group == "pumping_unattributed":
            facs = _dedup_facilities(sub)
            n_total = int(len(facs))
            n_declared = int(facs["annual_volume_m3"].notna().sum()) if n_total else 0
            total_decl = float(facs["annual_volume_m3"].dropna().sum()) if n_declared else 0.0
            records[group] = {
                "total_count": n_total,
                "declared_count": n_declared,
                "total_declared_m3": total_decl,
                "volume_year": volume_year,
            }

        elif group == "recharge":
            cells: list[dict[str, Any]] = []
            if not sub.empty:
                for (code, via), grp in sub.groupby(["driver_code", "via_code"], dropna=False, sort=False):
                    ws = grp["cell_weight"].dropna().to_numpy(dtype=float)
                    w = float(math.fsum(ws) / len(ws)) if len(ws) else float("nan")
                    via_s = str(via) if pd.notna(via) else None
                    cells.append(
                        {
                            "driver_code": str(code),
                            "label": grp["label"].iloc[0] if pd.notna(grp["label"].iloc[0]) else str(code),
                            "cell_weight": w,
                            "via_code": via_s,
                            "via_label": unit_labels.get(via_s) if via_s else None,
                            "path": str(grp["path"].iloc[0]),
                        }
                    )
                cells.sort(
                    key=lambda r: (
                        -(r["cell_weight"] if np.isfinite(r["cell_weight"]) else -1.0),
                        r["driver_code"],
                    )
                )
            records[group] = {"cells": cells}

        elif group == "river":
            gauges: list[dict[str, Any]] = []
            if not sub.empty:
                for (code, via), grp in sub.groupby(["driver_code", "via_code"], dropna=False, sort=False):
                    assocs = sorted({str(a) for a in grp["association_type"].dropna().unique() if str(a)})
                    confs = sorted(
                        {str(c) for c in grp["confidence"].dropna().unique() if str(c)},
                        key=lambda c: _CONFIDENCE_RANK.get(c, 99),
                    )
                    via_s = str(via) if pd.notna(via) else None
                    gauges.append(
                        {
                            "driver_code": str(code),
                            "label": grp["label"].iloc[0] if pd.notna(grp["label"].iloc[0]) else str(code),
                            "via_code": via_s,
                            "via_label": unit_labels.get(via_s) if via_s else None,
                            "association_types": ", ".join(assocs) if assocs else None,
                            "confidence": ", ".join(confs) if confs else None,
                            "path": str(grp["path"].iloc[0]),
                        }
                    )
            records[group] = {"gauges": gauges}

        elif group == "canal":
            intakes: list[dict[str, Any]] = []
            if not sub.empty:
                for (code, via), grp in sub.groupby(["driver_code", "via_code"], dropna=False, sort=False):
                    confs = sorted(
                        {str(c) for c in grp["confidence"].dropna().unique() if str(c)},
                        key=lambda c: _CONFIDENCE_RANK.get(c, 99),
                    )
                    via_s = str(via) if pd.notna(via) else None
                    intakes.append(
                        {
                            "driver_code": str(code),
                            "label": grp["label"].iloc[0] if pd.notna(grp["label"].iloc[0]) else str(code),
                            "via_code": via_s,
                            "via_label": unit_labels.get(via_s) if via_s else None,
                            "confidence": ", ".join(confs) if confs else None,
                            "path": str(grp["path"].iloc[0]),
                        }
                    )
            records[group] = {"intakes": intakes}

    return records


def _resolve_siblings(
    siblings: Iterable[str | Path] | Mapping[int, dict] | None,
    primary_recon: int,
    well: str,
    target: str | tuple[str, str],
    reference: str | tuple[str, str],
    *,
    dataset: str = DATASET,
) -> dict[int, dict]:
    """Normalize ``siblings`` (mapping of precomputed decompositions or list of run names)."""
    if siblings is None:
        return {}
    if isinstance(siblings, Mapping):
        return dict(siblings)
    run_list = [siblings] if isinstance(siblings, (str, Path)) else list(siblings)
    resolved: dict[int, dict] = {}
    for sib_run in run_list:
        sib_decomp = decompose(
            sib_run,
            target=target,
            reference=reference,
            wells=[well],
            dataset=dataset,
        )
        num = int(sib_decomp["metadata"]["pumping_reconstruction"])
        if num == primary_recon or num in resolved:
            raise ValueError(
                f"Pumping reconstruction {num} appears in more than one run (primary={primary_recon})"
            )
        resolved[num] = sib_decomp
    return resolved


def build_report_from_decomposition(
    decomposition: dict,
    well: str,
    *,
    siblings: Mapping[int, dict] | None = None,
    chain_df: pd.DataFrame | None = None,
    well_info: dict[str, str | None] | None = None,
    unit_labels: dict[str, str] | None = None,
    head_summary: dict[str, Any] | None = None,
    policy: str | None = None,
    arm: str | None = None,
    top: int = 5,
    volume_year: int | None = None,
    edge_weights: dict[str, float] | None = None,
    routed_window_m3: dict[str, float] | None = None,
    probable_only: bool | Mapping[str, bool] | None = None,
    groups_path: str | Path = GROUPS_PATH,
) -> dict[str, Any]:
    """Assemble the structured report payload from an existing decomposition dict.

    Separating assembly from file loading lets unit tests verify withheld-statement behaviour and
    exact additivity on hand-made decompositions without fitting or loading model checkpoints.
    """
    if top < 0:
        raise ValueError(f"top must be non-negative, got {top}")

    meta = dict(decomposition.get("metadata") or {})
    eff_arm = arm if arm is not None else meta.get("arm")
    eff_policy = policy if policy is not None else meta.get("export_policy")

    groups_df = load_groups(groups_path)
    rg_all = decomposition["by_report_group"]
    rg_well = rg_all[rg_all["code_bss"] == well].set_index("report_group")
    ordered_groups = _ordered_report_groups(rg_well.index, groups_df=groups_df)

    if "total" in decomposition and decomposition["total"] is not None:
        tot_df = decomposition["total"]
        tot_row = tot_df[tot_df["code_bss"] == well].iloc[0]
        total_stats = {
            "mean_m": float(tot_row["mean_m"]),
            "sd_m": float(tot_row["sd_m"]),
            "sign_agreement": float(tot_row["sign_agreement"]),
            "n_seeds": int(tot_row.get("n_seeds", decomposition.get("n_seeds", 0))),
        }
    else:
        total_stats = {
            "mean_m": float(rg_well["mean_m"].sum()),
            "sd_m": float("nan"),
            "sign_agreement": float("nan"),
            "n_seeds": int(decomposition.get("n_seeds", 0)),
        }

    flags_row = decomposition["flags"].set_index("code_bss").loc[well]
    n_weeks = int(flags_row.get("n_weeks", decomposition.get("n_target_weeks", 0)))
    n_observed = int(flags_row["n_observed"])
    n_strict = int(flags_row["n_strict"])
    n_placeholder = int(flags_row.get("n_placeholder", 0))
    flags = {
        "n_weeks": n_weeks,
        "n_observed": n_observed,
        "share_observed": float(flags_row.get("share_observed", n_observed / n_weeks if n_weeks else np.nan)),
        "n_strict": n_strict,
        "share_strict": float(flags_row.get("share_strict", n_strict / n_weeks if n_weeks else np.nan)),
        "share_validated_of_observed": (n_strict / n_observed) if n_observed else float("nan"),
        "n_placeholder": n_placeholder,
        "share_placeholder": float(flags_row.get("share_placeholder", n_placeholder / n_weeks if n_weeks else np.nan)),
        "routed_pumping_m3": float(flags_row.get("routed_pumping_m3", float("nan"))),
        "share_pumping_imputed": float(flags_row.get("share_pumping_imputed", float("nan"))),
    }

    prob = probable_only if probable_only is not None else _probable_only_map(chain_df, eff_arm)
    stmt_list = statements(
        decomposition,
        well,
        siblings=siblings or None,
        probable_only=prob,
        lang=VALID_LANGS,
    )
    stmt_by_group = {s["report_group"]: s for s in stmt_list}
    ordered_statements = [stmt_by_group[g] for g in ordered_groups if g in stmt_by_group]

    contributions = []
    for g in ordered_groups:
        row = rg_well.loc[g]
        st = stmt_by_group[g]
        contributions.append(
            {
                "report_group": g,
                "mean_m": float(row["mean_m"]),
                "sd_m": float(row["sd_m"]),
                "sign_agreement": float(row["sign_agreement"]),
                "status": st["status"],
                "reasons": list(st["reasons"]),
            }
        )

    stated_driver_groups = {
        s["report_group"]
        for s in ordered_statements
        if s["status"] in ("accepted", "qualified") and s["report_group"] in DRIVER_REPORT_GROUPS
    }
    vol_year = volume_year if volume_year is not None else _window_volume_year(decomposition["target"])
    records = _summarize_records(
        chain_df,
        stated_driver_groups,
        top=top,
        volume_year=vol_year,
        unit_labels=unit_labels or {},
        edge_weights=edge_weights,
        routed_window_m3=routed_window_m3,
    )

    primary_recon = int(meta.get("pumping_reconstruction", 1))
    checked_recons = sorted({primary_recon, *(int(k) for k in (siblings or {}))})

    return {
        "well": well_info or {
            "code_bss": well,
            "label": None,
            "unit_code": None,
            "unit_label": None,
            "aquifer_group": None,
        },
        "run": decomposition.get("run") or meta.get("run"),
        "dataset": decomposition.get("dataset") or meta.get("dataset"),
        "n_seeds": int(decomposition.get("n_seeds", total_stats["n_seeds"])),
        "metadata": meta,
        "arm": eff_arm,
        "policy": eff_policy,
        "checked_reconstructions": checked_recons if siblings else [],
        "target": tuple(decomposition["target"]),
        "n_target_weeks": int(decomposition.get("n_target_weeks", n_weeks)),
        "reference": dict(decomposition["reference"]),
        "head_summary": head_summary,
        "total": total_stats,
        "flags": flags,
        "contributions": contributions,
        "statements": ordered_statements,
        "records": records,
        "top": top,
        "volume_year": vol_year,
    }


def build_report_data(
    run: str | Path,
    well: str,
    target: str | tuple[str, str],
    *,
    reference: str | tuple[str, str] = "average_forcing",
    siblings: Iterable[str | Path] | Mapping[int, dict] | None = None,
    policy: str | None = None,
    arm: str | None = None,
    top: int = 5,
    dataset: str = DATASET,
    dataset_dir: str | Path | None = None,
    store: ox.Store | None = None,
) -> dict[str, Any]:
    """Compute all numbers, statements, SGI classes, and KG records for one well and window."""
    run_dir = _run_dir(run, dataset=dataset)
    decomp = decompose(
        run_dir,
        target=target,
        reference=reference,
        wells=[well],
        dataset=dataset,
        dataset_dir=dataset_dir,
    )
    meta = decomp["metadata"]
    eff_arm = arm if arm is not None else meta.get("arm")
    eff_policy = policy if policy is not None else (meta.get("export_policy") or "main")
    primary_recon = int(meta.get("pumping_reconstruction", 1))

    sib_map = _resolve_siblings(
        siblings, primary_recon, well, target, reference, dataset=dataset
    )

    kg = cached_store(dataset) if store is None else store
    w_info, unit_labels = _well_info(well, dataset=dataset, dataset_dir=dataset_dir, store=kg)
    vol_year = _window_volume_year(decomp["target"])

    cfg_path = run_dir / "config.json"
    recharge_rel = "recharge"
    if cfg_path.is_file():
        import json

        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        recharge_rel = cfg.get("recharge_relation") or "recharge"

    chain_df: pd.DataFrame | None = None
    edge_weights: dict[str, float] = {}
    routed_win: dict[str, float] = {}
    if eff_arm in CHAIN_ARMS:
        chain_df = chains(
            well,
            policy=eff_policy,
            arm=eff_arm,
            year=vol_year,
            recharge=recharge_rel if eff_arm == "D" else "recharge",
            dataset=dataset,
            store=kg,
        )
        edge_weights, routed_win = _routed_pumping_by_facility(
            well,
            decomp["target"],
            eff_arm,
            eff_policy,
            primary_recon,
            dataset=dataset,
            dataset_dir=dataset_dir,
        )

    head_summary = _simulated_and_observed(
        run_dir,
        well,
        decomp["target"],
        dataset=dataset,
        dataset_dir=dataset_dir,
    )

    return build_report_from_decomposition(
        decomp,
        well,
        siblings=sib_map or None,
        chain_df=chain_df,
        well_info=w_info,
        unit_labels=unit_labels,
        head_summary=head_summary,
        policy=eff_policy,
        arm=eff_arm,
        top=top,
        volume_year=vol_year,
        edge_weights=edge_weights,
        routed_window_m3=routed_win,
    )


def render_report(data: dict[str, Any], *, lang: str = "en") -> str:
    """Render a structured report payload from ``build_report_data`` as Markdown (EN or FR)."""
    if lang not in VALID_LANGS:
        raise ValueError(f"Unsupported language {lang!r}: expected one of {VALID_LANGS}")
    en = lang == "en"

    well = data["well"]
    code = well["code_bss"]
    label = well.get("label")
    title_well = f"{label} (`{code}`)" if label else f"`{code}`"
    title = (
        f"# Explanation report — {title_well}"
        if en
        else f"# Rapport d'explication — {title_well}"
    )

    unit_code = well.get("unit_code")
    unit_label = well.get("unit_label")
    if unit_code and unit_label:
        unit_text = f"`{unit_code}` — {unit_label}"
    elif unit_code:
        unit_text = f"`{unit_code}`"
    else:
        unit_text = "none recorded in graph" if en else "aucune enregistrée dans le graphe"

    aquifer_text = _translate_aquifer_group(well.get("aquifer_group"), lang)

    meta = data["metadata"]
    run_name = data["run"] or "unknown"
    arm_text = data["arm"] or ("panel (no graph)" if en else "panneau (sans graphe)")
    policy_text = data["policy"] or ("none" if en else "aucune")
    recon_num = meta.get("pumping_reconstruction", 1)
    recon_name = (
        meta.get("pumping_reconstruction_name", str(recon_num))
        if en
        else _RECON_FR.get(int(recon_num), meta.get("pumping_reconstruction_name", str(recon_num)))
    )
    protocol = meta.get("protocol", "unknown")
    regime = meta.get("regime", "unknown")
    signs = meta.get("signs", "none")
    residual = meta.get("residual", "none")
    n_seeds = data["n_seeds"]

    checked = data.get("checked_reconstructions") or []
    if checked:
        nums = ", ".join(str(x) for x in checked)
        sib_note = (
            f"reconstructions {nums} checked for sign agreement"
            if en
            else f"accord de signe vérifié sur les reconstructions {nums}"
        )
    else:
        sib_note = (
            "single reconstruction (no sibling check)"
            if en
            else "reconstruction unique (sans vérification inter-reconstructions)"
        )

    t0, t1 = data["target"]
    period_words = _date_range(t0, t1)[lang]
    n_wks = data["n_target_weeks"]
    ref_words = _reference_text(data["reference"])[lang]

    lines: list[str] = [title, ""]
    if en:
        lines.extend(
            [
                f"- **Well:** `{code}`" + (f" ({label})" if label else ""),
                f"- **Monitored unit:** {unit_text}",
                f"- **Aquifer group:** {aquifer_text}",
                (
                    f"- **Run:** `{run_name}` (dataset `{data['dataset']}`, regime `{regime}`, "
                    f"arm `{arm_text}`, export policy `{policy_text}`, "
                    f"pumping reconstruction {recon_num} ({recon_name}; {sib_note}), "
                    f"protocol `{protocol}`, signs `{signs}`, residual `{residual}`, {n_seeds} starts)"
                ),
                f"- **Target period:** {period_words} (`{t0}` to `{t1}`, {n_wks} weeks)",
                f"- **Reference condition:** {ref_words}",
            ]
        )
    else:
        lines.extend(
            [
                f"- **Piézomètre :** `{code}`" + (f" ({label})" if label else ""),
                f"- **Unité suivie :** {unit_text}",
                f"- **Groupe aquifère :** {aquifer_text}",
                (
                    f"- **Exécution :** `{run_name}` (jeu `{data['dataset']}`, régime `{regime}`, "
                    f"branche `{arm_text}`, politique d'export `{policy_text}`, "
                    f"reconstruction des prélèvements {recon_num} ({recon_name} ; {sib_note}), "
                    f"protocole `{protocol}`, signes `{signs}`, résidu `{residual}`, {n_seeds} départs)"
                ),
                f"- **Période cible :** {period_words} (`{t0}` au `{t1}`, {n_wks} semaines)",
                f"- **Condition de référence :** {ref_words}",
            ]
        )

    # ------------------------------------------------------------ Section 2
    lines.extend(["", "## Simulated and observed" if en else "## Simulé et observé", ""])
    tot = data["total"]
    hs = data.get("head_summary")
    flags = data["flags"]

    tot_mean_s = _fmt_num(tot["mean_m"], 3, lang, signed=True)
    tot_sd_s = _fmt_num(tot["sd_m"], 3, lang)
    if hs is not None:
        sim_h = _fmt_num(hs["mean_sim_head_m"], 3, lang)
        obs_h = _fmt_num(hs["mean_obs_head_m"], 3, lang)
        n_obs_u = hs["n_obs_weeks_unmasked"]
        n_sim_w = hs["n_sim_weeks"]
        if en:
            lines.append(
                f"- **Mean simulated head:** {sim_h} m NGF ({n_sim_w} weeks); "
                f"**change vs. reference:** {tot_mean_s} ± {tot_sd_s} m (= sum of contributions)"
            )
            lines.append(
                f"- **Mean observed head:** {obs_h} m NGF ({n_obs_u}/{n_sim_w} non-placeholder observed weeks)"
            )
        else:
            lines.append(
                f"- **Niveau simulé moyen :** {sim_h} m NGF ({n_sim_w} semaines) ; "
                f"**écart par rapport à la référence :** {tot_mean_s} ± {tot_sd_s} m (= somme des contributions)"
            )
            lines.append(
                f"- **Niveau observé moyen :** {obs_h} m NGF ({n_obs_u}/{n_sim_w} semaines observées hors valeurs suspectes)"
            )

        monthly = hs.get("monthly_sgi") or []
        if monthly:
            lines.append("")
            if en:
                lines.append(
                    "Monthly SGI and BRGM IPS class (frozen observed training reference up to 2019):"
                )
                lines.append("")
                lines.append(
                    "| Month | Observed head (m NGF) | Observed SGI (IPS class) | "
                    "Simulated head (m NGF) | Simulated SGI (IPS class) |"
                )
                lines.append("|---|---:|---|---:|---|")
            else:
                lines.append(
                    "IPS (SGI) mensuel et classe BRGM (référence observée figée sur l'entraînement jusqu'en 2019) :"
                )
                lines.append("")
                lines.append(
                    "| Mois | Niveau observé (m NGF) | SGI observé (classe IPS) | "
                    "Niveau simulé (m NGF) | SGI simulé (classe IPS) |"
                )
                lines.append("|---|---:|---|---:|---|")
            for mrow in monthly:
                o_h = _fmt_num(mrow["obs_head_m"], 3, lang)
                s_h = _fmt_num(mrow["sim_head_m"], 3, lang)
                o_z = _fmt_num(mrow["sgi_obs"], 2, lang, signed=True)
                s_z = _fmt_num(mrow["sgi_sim"], 2, lang, signed=True)
                o_cls = mrow["class_obs"] or ("n/a" if en else "n.d.")
                s_cls = mrow["class_sim"] or ("n/a" if en else "n.d.")
                o_cell = f"{o_z} ({o_cls})" if np.isfinite(mrow["sgi_obs"]) else ("n/a" if en else "n.d.")
                s_cell = f"{s_z} ({s_cls})" if np.isfinite(mrow["sgi_sim"]) else ("n/a" if en else "n.d.")
                lines.append(f"| {mrow['month']} | {o_h} | {o_cell} | {s_h} | {s_cell} |")
    else:
        if en:
            lines.append(
                f"- **Simulated change vs. reference:** {tot_mean_s} ± {tot_sd_s} m (= sum of contributions)"
            )
            lines.append("- **Mean simulated / observed head and SGI:** n/a (not supplied)")
        else:
            lines.append(
                f"- **Écart simulé par rapport à la référence :** {tot_mean_s} ± {tot_sd_s} m (= somme des contributions)"
            )
            lines.append("- **Niveaux simulé / observé et IPS :** n.d. (non fournis)")

    # Data quality line
    sh_obs = _fmt_pct(flags["share_observed"], lang)
    sh_str = _fmt_pct(flags["share_strict"], lang)
    sh_val_obs = _fmt_pct(flags["share_validated_of_observed"], lang)
    sh_ph = _fmt_pct(flags["share_placeholder"], lang)
    sh_imp = _fmt_pct(flags["share_pumping_imputed"], lang)
    if np.isnan(flags["share_pumping_imputed"]):
        imp_str = "n/a (zero routed volume)" if en else "n.d. (volume acheminé nul)"
    else:
        imp_str = sh_imp
    lines.append("")
    if en:
        lines.append(
            f"- **Data quality:** observed {flags['n_observed']}/{flags['n_weeks']} weeks ({sh_obs}); "
            f"strictly validated {flags['n_strict']}/{flags['n_weeks']} weeks ({sh_str} of window, "
            f"{sh_val_obs} of observed); suspect placeholders {flags['n_placeholder']}/{flags['n_weeks']} "
            f"({sh_ph}); imputed routed pumping {imp_str}."
        )
    else:
        lines.append(
            f"- **Qualité des données :** observées {flags['n_observed']}/{flags['n_weeks']} semaines ({sh_obs}) ; "
            f"strictement validées {flags['n_strict']}/{flags['n_weeks']} semaines ({sh_str} de la période, "
            f"{sh_val_obs} des semaines observées) ; valeurs suspectes (placeholder) "
            f"{flags['n_placeholder']}/{flags['n_weeks']} ({sh_ph}) ; prélèvements acheminés imputés {imp_str}."
        )

    # ------------------------------------------------------------ Section 3
    lines.extend(["", "## What the model credits" if en else "## Ce que le modèle attribue", ""])
    if en:
        lines.append("| Report group | Contribution (m) | Sign agreement | Status |")
        lines.append("|---|---:|---:|---|")
    else:
        lines.append("| Groupe de forçages | Contribution (m) | Accord de signe | Statut |")
        lines.append("|---|---:|---:|---|")

    for c in data["contributions"]:
        g = c["report_group"]
        g_name = _GROUP_SHORT.get(g, {}).get(lang, g)
        val = f"{_fmt_num(c['mean_m'], 3, lang, signed=True)} ± {_fmt_num(c['sd_m'], 3, lang)}"
        agr = _fmt_pct(c["sign_agreement"], lang, digits=0)
        st_lbl = _STATUS_LABEL[c["status"]][lang]
        lines.append(f"| {g_name} (`{g}`) | {val} | {agr} | {st_lbl} |")

    tot_agr = _fmt_pct(tot["sign_agreement"], lang, digits=0)
    tot_label = "**Total (sum of contributions)**" if en else "**Total (somme des contributions)**"
    lines.append(f"| {tot_label} | **{tot_mean_s} ± {tot_sd_s}** | {tot_agr} | — |")

    lines.extend(["", "### Statements" if en else "### Énoncés", ""])
    for st in data["statements"]:
        g = st["report_group"]
        g_name = _GROUP_SHORT.get(g, {}).get(lang, g)
        status = st["status"]
        st_lbl = _STATUS_LABEL[status][lang]
        reasons_txt = "; ".join(_format_reason(r, lang) for r in st["reasons"])
        text = st[f"text_{lang}"]
        if status == "withheld":
            if en:
                lines.append(f"- **{g_name}** (`{g}`) — *{st_lbl}* ({reasons_txt}).")
            else:
                lines.append(f"- **{g_name}** (`{g}`) — *{st_lbl}* ({reasons_txt}).")
        elif status == "qualified":
            if en:
                lines.append(f"- **{g_name}** (`{g}`) — *{st_lbl}* ({reasons_txt}): {text}")
            else:
                lines.append(f"- **{g_name}** (`{g}`) — *{st_lbl}* ({reasons_txt}) : {text}")
        else:
            if en:
                lines.append(f"- **{g_name}** (`{g}`) — *{st_lbl}*: {text}")
            else:
                lines.append(f"- **{g_name}** (`{g}`) — *{st_lbl}* : {text}")

    # ------------------------------------------------------------ Section 4
    lines.extend(
        [
            "",
            (
                "## Records behind each stated driver"
                if en
                else "## Enregistrements derrière chaque forçage retenu ou nuancé"
            ),
            "",
        ]
    )
    records = data["records"]
    if not records:
        if en:
            lines.append(
                "No driver group has an accepted or qualified statement in this window, "
                "so no driver records are listed."
            )
        else:
            lines.append(
                "Aucun groupe de forçages ne fait l'objet d'un énoncé retenu ou nuancé sur cette période ; "
                "aucun enregistrement n'est donc listé."
            )
    else:
        for group in DRIVER_REPORT_GROUPS:
            if group not in records:
                continue
            rec = records[group]
            g_name = _GROUP_SHORT.get(group, {}).get(lang, group)
            lines.append(f"### {g_name} (`{group}`)")
            lines.append("")

            if group == "pumping_attributed":
                n_tot = rec["total_count"]
                n_decl = rec["declared_count"]
                yr = rec["volume_year"]
                top_facs = rec["top_facilities"]
                share = rec["share_routed_volume"]
                share_s = _fmt_pct(share, lang)
                if n_tot == 0:
                    lines.append(
                        "No abstraction facilities are linked to this well under the run's export policy."
                        if en
                        else "Aucun ouvrage de prélèvement n'est relié à ce piézomètre selon la politique d'export."
                    )
                else:
                    if rec["path"] == "distance rule":
                        path_note = (
                            " (connected by distance rules; no knowledge-graph path)"
                            if en
                            else " (reliés par règles de distance ; aucun chemin dans le graphe de connaissances)"
                        )
                    else:
                        path_note = ""
                    if en:
                        lines.append(
                            f"Showing top {len(top_facs)} of {n_tot} linked facilities by declared {yr} "
                            f"volume ({n_decl}/{n_tot} have a {yr} BNPE declaration; these {len(top_facs)} "
                            f"facilities carry {share_s} of the routed attributed pumping volume){path_note}:"
                        )
                        lines.append("")
                        lines.append(
                            f"| Label | BNPE code | Use | Unit / group | Distance (m) | Confidence | "
                            f"Declared volume ({yr}, m³) |"
                        )
                        lines.append("|---|---|---|---|---:|---|---:|")
                    else:
                        lines.append(
                            f"Principaux ouvrages ({len(top_facs)} sur {n_tot} reliés) classés par volume "
                            f"déclaré en {yr} ({n_decl}/{n_tot} disposent d'une déclaration BNPE {yr} ; "
                            f"ces {len(top_facs)} ouvrages portent {share_s} du volume acheminé attribué){path_note} :"
                        )
                        lines.append("")
                        lines.append(
                            f"| Libellé | Code BNPE | Usage | Unité / groupe | Distance (m) | Confiance | "
                            f"Volume déclaré ({yr}, m³) |"
                        )
                        lines.append("|---|---|---|---|---:|---|---:|")
                    for f in top_facs:
                        lbl = f["label"] or "—"
                        use = _translate_use(f["water_use"], lang)
                        via = _translate_via(f["via_code"], lang)
                        dist = _fmt_int(f["distance_m"], lang)
                        conf = _translate_confidence(f["confidence"], lang)
                        vol = _fmt_int(f["annual_volume_m3"], lang)
                        lines.append(
                            f"| {lbl} | `{f['driver_code']}` | {use} | {via} | {dist} | {conf} | {vol} |"
                        )

            elif group == "pumping_unattributed":
                n_tot = rec["total_count"]
                n_decl = rec["declared_count"]
                tot_decl = _fmt_int(rec["total_declared_m3"], lang)
                yr = rec["volume_year"]
                if en:
                    lines.append(
                        f"- **Facilities:** {n_tot} groundwater facilities within 5 km "
                        f"({n_decl} with a declared {yr} BNPE volume); "
                        f"**total declared {yr} volume:** {tot_decl} m³."
                    )
                    lines.append(
                        f"- These facilities' link to the well's unit is not selected by the "
                        f"`{policy_text}` export policy (possible or unattributed links)."
                    )
                else:
                    lines.append(
                        f"- **Ouvrages :** {n_tot} ouvrages souterrains dans un rayon de 5 km "
                        f"({n_decl} avec un volume BNPE déclaré en {yr}) ; "
                        f"**volume total déclaré en {yr} :** {tot_decl} m³."
                    )
                    lines.append(
                        f"- Le lien entre ces ouvrages et l'unité du piézomètre n'est pas retenu par la "
                        f"politique d'export `{policy_text}` (liens possibles ou non attribués)."
                    )

            elif group == "recharge":
                cells = rec["cells"]
                if not cells:
                    lines.append(
                        "No weather cells are linked to this well."
                        if en
                        else "Aucune maille météorologique n'est reliée à ce piézomètre."
                    )
                else:
                    if en:
                        lines.append("| Weather cell | Weight | Outcrop unit |")
                        lines.append("|---|---:|---|")
                    else:
                        lines.append("| Maille météo | Poids | Unité affleurante |")
                        lines.append("|---|---:|---|")
                    for c in cells:
                        w_s = _fmt_num(c["cell_weight"], 4, lang)
                        if c["via_code"] and c["via_label"]:
                            u_s = f"`{c['via_code']}` — {c['via_label']}"
                        elif c["via_code"]:
                            u_s = f"`{c['via_code']}`"
                        else:
                            u_s = (
                                "distance rule (nearest cell)"
                                if en
                                else "règle de distance (maille la plus proche)"
                            )
                        lines.append(f"| `{c['driver_code']}` | {w_s} | {u_s} |")

            elif group == "river":
                gauges = rec["gauges"]
                if not gauges:
                    lines.append(
                        "No river gauge is linked to this well."
                        if en
                        else "Aucune station hydrométrique n'est reliée à ce piézomètre."
                    )
                else:
                    if en:
                        lines.append("| Gauge | Code | Path type | Unit | Confidence |")
                        lines.append("|---|---|---|---|---|")
                    else:
                        lines.append("| Station | Code | Type de chemin | Unité | Confiance |")
                        lines.append("|---|---|---|---|---|")
                    for g_row in gauges:
                        ptype = (
                            _translate_assoc(g_row["association_types"], lang)
                            if g_row["association_types"]
                            else ("distance rule" if en else "règle de distance")
                        )
                        via_s = f"`{g_row['via_code']}`" if g_row["via_code"] else "—"
                        conf_s = _translate_confidence(g_row["confidence"], lang)
                        lines.append(
                            f"| {g_row['label']} | `{g_row['driver_code']}` | {ptype} | {via_s} | {conf_s} |"
                        )

            elif group == "canal":
                intakes = rec["intakes"]
                if not intakes:
                    lines.append(
                        "No canal intake group is linked to this well."
                        if en
                        else "Aucun groupe de prises de canaux n'est relié à ce piézomètre."
                    )
                else:
                    for item in intakes:
                        via_s = f"`{item['via_code']}`" if item["via_code"] else "—"
                        conf_s = _translate_confidence(item["confidence"], lang)
                        if en:
                            lines.append(
                                f"- **Intake group:** {item['label']} (`{item['driver_code']}`; "
                                f"unit {via_s}, confidence: {conf_s})."
                            )
                        else:
                            lines.append(
                                f"- **Groupe de prises :** {item['label']} (`{item['driver_code']}` ; "
                                f"unité {via_s}, confiance : {conf_s})."
                            )
            lines.append("")

    # ------------------------------------------------------------ Section 5
    if lines and lines[-1] != "":
        lines.append("")
    lines.append(f"> {CAVEAT_LINE[lang]}")
    return "\n".join(lines) + "\n"


def explain(
    run: str | Path,
    well: str,
    target: str | tuple[str, str],
    *,
    reference: str | tuple[str, str] = "average_forcing",
    siblings: Iterable[str | Path] | Mapping[int, dict] | None = None,
    policy: str | None = None,
    arm: str | None = None,
    top: int = 5,
    lang: str = "en",
    dataset: str = DATASET,
) -> str:
    """Return a Markdown explanation report for one well and inclusive target window."""
    if lang not in VALID_LANGS:
        raise ValueError(f"Unsupported language {lang!r}: expected one of {VALID_LANGS}")
    data = build_report_data(
        run,
        well,
        target,
        reference=reference,
        siblings=siblings,
        policy=policy,
        arm=arm,
        top=top,
        dataset=dataset,
    )
    return render_report(data, lang=lang)


def write_report(
    out: str | Path,
    run: str | Path,
    well: str,
    target: str | tuple[str, str],
    *,
    reference: str | tuple[str, str] = "average_forcing",
    siblings: Iterable[str | Path] | Mapping[int, dict] | None = None,
    policy: str | None = None,
    arm: str | None = None,
    top: int = 5,
    lang: str = "en",
    dataset: str = DATASET,
) -> Path:
    """Render one explanation report and write it to ``out`` (UTF-8 Markdown)."""
    text = explain(
        run,
        well,
        target,
        reference=reference,
        siblings=siblings,
        policy=policy,
        arm=arm,
        top=top,
        lang=lang,
        dataset=dataset,
    )
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate one Markdown explanation report for one well and period (EN or FR)."
    )
    parser.add_argument("run", help="Run name under results/<dataset>/ or path to a run folder.")
    parser.add_argument("well", help="Piezometer BSS code (e.g. 10964X0119/NYLS-1).")
    parser.add_argument(
        "--target",
        required=True,
        help="Inclusive target window 'YYYY-MM-DD:YYYY-MM-DD'.",
    )
    parser.add_argument(
        "--reference",
        default="average_forcing",
        help="Reference condition: 'average_forcing' (default), 'training_seasonal', or 'START:END'.",
    )
    parser.add_argument(
        "--sibling",
        nargs="+",
        action="extend",
        default=[],
        help="Optional sibling run(s) with other pumping reconstructions.",
    )
    parser.add_argument(
        "--policy",
        default=None,
        help="Export policy override (defaults to the run's config.json).",
    )
    parser.add_argument(
        "--arm",
        default=None,
        help="Graph arm override (defaults to the run's config.json).",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="Number of top attributed pumping facilities by declared volume to list (default: 5).",
    )
    parser.add_argument(
        "--lang",
        choices=VALID_LANGS,
        default="en",
        help="Report language: 'en' (default) or 'fr'.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional output Markdown path. Prints to stdout when omitted.",
    )
    parser.add_argument(
        "--dataset",
        default=DATASET,
        help=f"Dataset version (default: {DATASET}).",
    )
    args = parser.parse_args(argv)

    siblings = args.sibling if args.sibling else None
    if args.out is not None:
        out_path = write_report(
            args.out,
            args.run,
            args.well,
            args.target,
            reference=args.reference,
            siblings=siblings,
            policy=args.policy,
            arm=args.arm,
            top=args.top,
            lang=args.lang,
            dataset=args.dataset,
        )
        print(f"-> {out_path}")
    else:
        print(
            explain(
                args.run,
                args.well,
                args.target,
                reference=args.reference,
                siblings=siblings,
                policy=args.policy,
                arm=args.arm,
                top=args.top,
                lang=args.lang,
                dataset=args.dataset,
            ),
            end="",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
