"""Knowledge-graph records behind each model driver (Phase 5, SO4, CQ10).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m src.explain.chains \\
        10906X0039/C2-1 --policy main --arm D --year 2024

Why this module exists (docs/analysis_plan.md §12; docs/notes/step15_explanations.md)
------------------------------------------------------------------------------------
Contribution tables (``src/explain/contributions.py``) say how much each driver group moved a
well's simulated head (for example, "the model attributes -0.22 m to pumping on the well's
knowledge-graph links"). To state that explanation **in ontology terms** (subject SO4, CQ10),
the explanation layer must name the exact records behind each driver: which abstraction
facilities (with their use, unit, distance, confidence, and declared annual volume for the
window's year), which weather cells over which unit's outcrop (with their weights), which
stream gauge, and which canal intake group.

Two sources of truth in arm D — and why they differ
---------------------------------------------------
1. ``recharge``, ``pumping_attributed``, ``river``, and ``canal`` come from the competency-question
   query ``tests/cq/cq08_influences.rq`` (bound via ``src.kg.cq.bind``), restricted to the
   ``lulcw:Influence`` records **selected under the run's export policy**. For recharge, this
   module applies the same extent choice (the well's 5 km outcrop search zone by default, or
   ``recharge_unitwide`` for the unit-wide sensitivity) and the same ``MIN_CELL_SHARE`` cutoff
   (0.001, Gate 3 point 12, ``src.kg.export.MIN_CELL_SHARE``) that ``src/kg/export.py`` applies
   when writing ``edges_D.parquet``: the knowledge graph keeps tiny sliver cells, while the model
   export drops them, and an explanation must cite exactly what the model saw.
2. ``pumping_unattributed`` comes from the run's export edge table
   (``src.models.routing.load_edges(arm, policy)``), joined back to the knowledge graph for each
   facility's IRI, label, declared water use, and declared annual volume. The two sources differ
   by construction: the unattributed pumping input is defined by what the export policy does
   **not** select (groundwater facilities within 5 km that have no selected pumping influence on
   the well), so those pairs have no ``lulcw:Influence`` node in the graph.

Arm C (distance rules)
----------------------
Arm C connects each well by distance rules only (nearest weather cell, 2 nearest pool gauges,
every groundwater facility within 10 km, and the plain's canal node for plain wells) and has no
knowledge-graph path. For ``arm="C"``, ``chains()`` returns the export's driver edges joined to
the graph for entity IRIs, labels, and facility volumes, with ``influence`` empty (``None``) and
``path="distance rule"``, so the explanation layer can state that no ontology pathway exists.
Well-to-well links (``well_link``) are omitted because they are not exogenous drivers.

What the graph holds for labels and volumes
-------------------------------------------
- Labels come strictly from ``rdfs:label`` on ``lulcw:AbstractionFacility``, ``lulcw:WeatherCell``,
  ``lulcw:RiverGauge``, and ``lulcw:CanalIntakeGroup``. The graph does not store facility communes,
  so no commune field is fabricated.
- Annual facility volumes come from ``lulcw:AnnualAbstractionRecord`` (``sosa:hasSimpleResult`` in
  m³) with ``lulcw:recordKind`` (``declared``, ``imputed``, or ``reconstructed``). Following the
  knowledge-graph contract (CQ12), a missing declaration stays absent (``NaN`` / ``None``), never
  zero, and records of different ``recordKind`` are never summed together.
"""
from __future__ import annotations

import argparse
import math
from typing import Any

import numpy as np
import pandas as pd
import pyoxigraph as ox
import rdflib

from src.config import DATASET, ROOT
from src.kg.cq import CQ, FUNCTIONS, bind, kg_store, local, py
from src.kg.export import D_IRI, MIN_CELL_SHARE
from src.kg.inventory import MECHANISM
from src.models.routing import load_edges

LULCW_NS = "https://w3id.org/lulcw#"
GROUPS_PATH = ROOT / "configs" / "explain_groups.csv"
VALID_POLICIES = ("main", "confident-only", "all-links")
VALID_ARMS = ("D", "C")
VALID_RECHARGE = ("recharge", "recharge_unitwide")
WEIGHT_TOL = 1e-9

REPORT_GROUP_ORDER = (
    "recharge",
    "pumping_attributed",
    "pumping_unattributed",
    "river",
    "canal",
)
_GROUP_RANK = {name: i for i, name in enumerate(REPORT_GROUP_ORDER)}

# Export edge relation -> report_group (aligned with configs/explain_groups.csv).
_EXPORT_TO_REPORT = {
    "recharge": "recharge",
    "recharge_unitwide": "recharge",
    "pumping": "pumping_attributed",
    "pumping_unattributed": "pumping_unattributed",
    "river": "river",
    "canal": "canal",
}

_RECORD_KIND_LABEL = {
    "DeclaredRecord": "declared",
    "ImputedRecord": "imputed",
    "ReconstructedRecord": "reconstructed",
}
_RECORD_KIND_PRIORITY = {"declared": 0, "imputed": 1, "reconstructed": 2}

_WATER_USE_LABEL = {
    "DrinkingWaterUse": "drinking water",
    "IrrigationUse": "irrigation",
    "IndustryUse": "industry",
    "CanalSupplyUse": "canal supply",
    "EnergyUse": "energy",
}

COLUMNS = (
    "report_group",
    "path",
    "influence",
    "driver_iri",
    "driver_code",
    "label",
    "water_use",
    "mechanism",
    "response_sign",
    "driver_group",
    "distance_m",
    "cell_weight",
    "via_code",
    "via_iri",
    "association_type",
    "confidence",
    "selected",
    "constrained",
    "annual_volume_m3",
    "record_kind",
    "volume_year",
)

# Per-process caches so repeated calls for different wells take ~0.1 s each.
_STORE_CACHE: dict[str, ox.Store] = {}
_INDEX_CACHE: dict[int, dict[str, Any]] = {}
_EDGES_CACHE: dict[tuple[str, str, str], pd.DataFrame] = {}
_GROUPS_CACHE: dict[str, dict[str, str]] | None = None
_CQ08_TEXT: str | None = None


def clear_cache() -> None:
    """Clear the per-process store, graph index, and export edge caches."""
    _STORE_CACHE.clear()
    _INDEX_CACHE.clear()
    _EDGES_CACHE.clear()


def cached_store(dataset: str = DATASET) -> ox.Store:
    """Return the validated pyoxigraph store for ``dataset``, cached per process."""
    if dataset not in _STORE_CACHE:
        _STORE_CACHE[dataset] = kg_store(dataset)
    return _STORE_CACHE[dataset]


def _load_explain_groups() -> dict[str, dict[str, str]]:
    """Read ``configs/explain_groups.csv`` keyed by ``report_group``."""
    global _GROUPS_CACHE
    if _GROUPS_CACHE is None:
        df = pd.read_csv(GROUPS_PATH, keep_default_na=False)
        _GROUPS_CACHE = {
            str(r["report_group"]): {
                "stress": str(r["stress"]),
                "driver_group": str(r["driver_group"]) or None,
                "label_en": str(r.get("label_en", "")),
                "label_fr": str(r.get("label_fr", "")),
            }
            for _, r in df.iterrows()
        }
    return _GROUPS_CACHE


def _cq08_query_text() -> str:
    global _CQ08_TEXT
    if _CQ08_TEXT is None:
        _CQ08_TEXT = (CQ / "cq08_influences.rq").read_text(encoding="utf-8")
    return _CQ08_TEXT


def _run_cq08(store: ox.Store, well_iri: str, policy: str) -> list[dict[str, Any]]:
    """Execute ``tests/cq/cq08_influences.rq`` bound with ``src.kg.cq.bind``."""
    params = {
        "W": rdflib.URIRef(well_iri),
        "policy": rdflib.URIRef(f"{D_IRI}policy/{policy}"),
    }
    res = store.query(bind(_cq08_query_text(), params), custom_functions=FUNCTIONS)
    cols = [v.value for v in res.variables]
    return [{c: py(r[c]) for c in cols} for r in res]


def _cached_edges(arm: str, policy: str, dataset: str) -> pd.DataFrame:
    key = (dataset, policy, arm)
    if key not in _EDGES_CACHE:
        edges, _ = load_edges(arm, policy=policy, dataset=dataset)
        _EDGES_CACHE[key] = edges
    return _EDGES_CACHE[key]


def _build_store_index(store: ox.Store) -> dict[str, Any]:
    """Extract compact, fast lookup tables from ``store`` once per process (~0.3 s).

    Reads only asserted facts and ``lulcw:Influence`` driver pointers:
    - piezometers (``lulcw:bssCode`` <-> IRI),
    - ``lulcw:Influence`` -> ``lulcw:driverEntity`` IRI (not in ``cq08_influences.rq`` SELECT),
    - driver entity IRIs and ``rdfs:label`` for facilities, gauges, weather cells, and canals,
    - ``lulcw:AnnualAbstractionRecord`` volumes, record kinds, and water uses by facility and year.
    """
    wells_by_code: dict[str, str] = {}
    wells_by_iri: dict[str, str] = {}
    for r in store.query(
        "PREFIX lulcw: <https://w3id.org/lulcw#> "
        "SELECT ?c ?w WHERE { ?w a lulcw:Piezometer ; lulcw:bssCode ?c }"
    ):
        code, iri = r["c"].value, r["w"].value
        wells_by_code[code] = iri
        wells_by_iri[iri] = code

    influence_driver: dict[str, str] = {
        r["i"].value: r["d"].value
        for r in store.query(
            "PREFIX lulcw: <https://w3id.org/lulcw#> "
            "SELECT ?i ?d WHERE { ?i a lulcw:Influence ; lulcw:driverEntity ?d }"
        )
    }

    entity_meta: dict[str, tuple[str, str | None]] = {}
    for r in store.query(
        """
        PREFIX lulcw: <https://w3id.org/lulcw#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT ?e ?c ?l WHERE {
            { ?e a lulcw:AbstractionFacility ; lulcw:bnpeCode ?c . }
            UNION
            { ?e a lulcw:RiverGauge ; lulcw:gaugeCode ?c . }
            UNION
            { ?e a lulcw:WeatherCell . BIND(STRAFTER(STR(?e), "/weather-cell/") AS ?c) }
            UNION
            { ?e a lulcw:CanalIntakeGroup .
              BIND(CONCAT("canal-intakes:", STRAFTER(STR(?e), "/canal-intakes/")) AS ?c) }
            OPTIONAL { ?e rdfs:label ?l . }
        }
        """
    ):
        code = r["c"].value
        label = r["l"].value if r["l"] is not None else None
        # Keep the first label if an entity ever carries labels in multiple languages.
        if code not in entity_meta or entity_meta[code][1] is None:
            entity_meta[code] = (r["e"].value, label)

    # Group annual abstraction records by (facility_code, year, record_kind) so records of
    # different recordKind (declared / imputed / reconstructed) are never summed together.
    grouped_ann: dict[tuple[str, int], dict[str, list[tuple[float, str | None]]]] = {}
    all_uses: dict[str, set[str]] = {}
    for r in store.query(
        """
        PREFIX lulcw: <https://w3id.org/lulcw#>
        PREFIX sosa: <http://www.w3.org/ns/sosa/>
        PREFIX time: <http://www.w3.org/2006/time#>
        SELECT ?c ?d ?v ?rk ?u WHERE {
            ?o a lulcw:AnnualAbstractionRecord ;
               sosa:hasFeatureOfInterest ?f ;
               sosa:hasSimpleResult ?v ;
               sosa:phenomenonTime/time:hasBeginning/time:inXSDDate ?d ;
               lulcw:recordKind ?rk .
            ?f lulcw:bnpeCode ?c .
            OPTIONAL { ?o lulcw:waterUse ?u . }
        }
        """
    ):
        code = r["c"].value
        yr = int(r["d"].value[:4])
        vol = float(r["v"].value)
        rk_local = local(r["rk"].value)
        rk = _RECORD_KIND_LABEL.get(rk_local, rk_local)
        use_label = _WATER_USE_LABEL.get(local(r["u"].value), local(r["u"].value)) if r["u"] is not None else None
        if use_label is not None:
            all_uses.setdefault(code, set()).add(use_label)
        grouped_ann.setdefault((code, yr), {}).setdefault(rk, []).append((vol, use_label))

    annual_records: dict[tuple[str, int], tuple[float, str, str | None]] = {}
    for key, by_kind in grouped_ann.items():
        # Prefer declared over imputed over reconstructed if a future graph holds multiple kinds.
        rk = min(by_kind, key=lambda k: _RECORD_KIND_PRIORITY.get(k, 99))
        entries = by_kind[rk]
        vol = math.fsum(v for v, _ in entries)
        uses = sorted({u for _, u in entries if u is not None})
        annual_records[key] = (vol, rk, ", ".join(uses) if uses else None)

    facility_uses = {code: ", ".join(sorted(uses)) for code, uses in all_uses.items()}
    return {
        "wells_by_code": wells_by_code,
        "wells_by_iri": wells_by_iri,
        "influence_driver": influence_driver,
        "entity_meta": entity_meta,
        "annual_records": annual_records,
        "facility_uses": facility_uses,
    }


def _store_index(store: ox.Store) -> dict[str, Any]:
    key = id(store)
    if key not in _INDEX_CACHE:
        _INDEX_CACHE[key] = _build_store_index(store)
    return _INDEX_CACHE[key]


def _resolve_well(well: str, index: dict[str, Any]) -> tuple[str, str]:
    """Resolve a BSS code or piezometer IRI to ``(code_bss, well_iri)``."""
    if well in index["wells_by_code"]:
        return well, index["wells_by_code"][well]
    if well in index["wells_by_iri"]:
        return index["wells_by_iri"][well], well
    raise ValueError(f"Unknown well {well!r}: not found among the graph's piezometers")


def _curie_driver_group(iri: str | None) -> str | None:
    if not iri:
        return None
    if iri.startswith(LULCW_NS):
        return f"lulcw:{iri[len(LULCW_NS):]}"
    return iri


def _facility_volume_and_use(
    code: str,
    year: int | None,
    index: dict[str, Any],
) -> tuple[str | None, float, str | None, int | None]:
    """Return ``(water_use, annual_volume_m3, record_kind, volume_year)`` for one facility.

    When ``year`` is given and the graph holds an ``AnnualAbstractionRecord`` for that year,
    returns that year's declared volume (m³), record kind, and declared use. When ``year`` is
    ``None`` or no declaration exists in ``year``, the volume and record kind remain absent
    (``NaN``, ``None`` — never zero) and ``water_use`` falls back to the distinct uses recorded
    for that facility across the graph's annual records.
    """
    if year is not None:
        rec = index["annual_records"].get((code, int(year)))
        if rec is not None:
            vol, rk, use_y = rec
            use = use_y if use_y is not None else index["facility_uses"].get(code)
            return use, float(vol), rk, int(year)
    return index["facility_uses"].get(code), float("nan"), None, None


def _finalize_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Build a consistently typed and deterministically sorted chains DataFrame."""
    if not rows:
        df = pd.DataFrame({c: pd.Series(dtype="object") for c in COLUMNS})
        for col in ("distance_m", "cell_weight", "annual_volume_m3"):
            df[col] = df[col].astype("float64")
        for col in ("selected", "constrained"):
            df[col] = df[col].astype("bool")
        return df

    df = pd.DataFrame(rows, columns=COLUMNS)
    for col in ("distance_m", "cell_weight", "annual_volume_m3"):
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
    for col in ("selected", "constrained"):
        df[col] = df[col].astype(bool)

    df = df.assign(
        _grp_rank=df["report_group"].map(lambda g: _GROUP_RANK.get(g, 99)),
        _neg_weight=-df["cell_weight"],
        _inf_sort=df["influence"].fillna(""),
    ).sort_values(
        ["_grp_rank", "distance_m", "_neg_weight", "driver_code", "_inf_sort"],
        ascending=[True, True, True, True, True],
        na_position="last",
        kind="mergesort",
    ).drop(columns=["_grp_rank", "_neg_weight", "_inf_sort"]).reset_index(drop=True)
    return df


def _chains_arm_d(
    code_bss: str,
    well_iri: str,
    policy: str,
    year: int | None,
    recharge: str,
    dataset: str,
    store: ox.Store,
    index: dict[str, Any],
) -> pd.DataFrame:
    groups = _load_explain_groups()
    cq_rows = [r for r in _run_cq08(store, well_iri, policy) if r["selected"]]

    # Group selected CQ8 rows by (relation, driverCode) so recharge applies the exact same
    # extent filter and MIN_CELL_SHARE cutoff as src/kg/export.py (Gate 3 point 12).
    selected_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in cq_rows:
        mech_local = local(r["mechanism"])
        rel = MECHANISM[mech_local]
        if rel == "recharge":
            is_unitwide = bool(r["extent"] and r["extent"].endswith("/forcing-cells"))
            rel = "recharge_unitwide" if is_unitwide else "recharge"
            if rel != recharge:
                continue
        selected_by_key.setdefault((rel, r["driverCode"]), []).append(r)

    rows: list[dict[str, Any]] = []
    for (rel, driver_code), paths in selected_by_key.items():
        if rel in VALID_RECHARGE:
            ws = [p["cellWeight"] for p in paths if p["cellWeight"] is not None]
            if ws and (math.fsum(ws) / len(ws)) < MIN_CELL_SHARE:
                continue

        report_group = _EXPORT_TO_REPORT[rel]
        ent_iri_fallback, label = index["entity_meta"].get(driver_code, (None, None))
        is_facility = report_group == "pumping_attributed"
        if is_facility:
            water_use, annual_vol, record_kind, vol_year = _facility_volume_and_use(
                driver_code, year, index
            )
        else:
            water_use, annual_vol, record_kind, vol_year = None, float("nan"), None, None

        for p in paths:
            inf_iri = p["influence"]
            driver_iri = index["influence_driver"].get(inf_iri, ent_iri_fallback)
            rows.append(
                {
                    "report_group": report_group,
                    "path": "knowledge graph",
                    "influence": inf_iri,
                    "driver_iri": driver_iri,
                    "driver_code": driver_code,
                    "label": label,
                    "water_use": water_use,
                    "mechanism": local(p["mechanism"]),
                    "response_sign": local(p["responseSign"]),
                    "driver_group": _curie_driver_group(p["driverGroup"]),
                    "distance_m": float(p["distanceM"]) if p["distanceM"] is not None else float("nan"),
                    "cell_weight": float(p["cellWeight"]) if p["cellWeight"] is not None else float("nan"),
                    "via_code": p["viaCode"],
                    "via_iri": p["via"],
                    "association_type": p["associationType"] or None,
                    "confidence": local(p["confidence"]),
                    "selected": bool(p["selected"]),
                    "constrained": bool(p["constrained"]),
                    "annual_volume_m3": annual_vol,
                    "record_kind": record_kind,
                    "volume_year": vol_year,
                }
            )

    # Unattributed pumping: defined by exclusion (facilities within 5 km not selected by policy).
    edges_d = _cached_edges("D", policy, dataset)
    un_edges = edges_d[(edges_d["dst"] == code_bss) & (edges_d["relation"] == "pumping_unattributed")]
    un_driver_group = groups["pumping_unattributed"]["driver_group"]
    for e in un_edges.itertuples(index=False):
        code = str(e.src)
        driver_iri, label = index["entity_meta"].get(code, (None, None))
        water_use, annual_vol, record_kind, vol_year = _facility_volume_and_use(code, year, index)
        dist = float(e.distance_m) if pd.notna(e.distance_m) else float("nan")
        rows.append(
            {
                "report_group": "pumping_unattributed",
                "path": "unattributed",
                "influence": None,
                "driver_iri": driver_iri,
                "driver_code": code,
                "label": label,
                "water_use": water_use,
                "mechanism": None,
                "response_sign": None,
                "driver_group": un_driver_group,
                "distance_m": dist,
                "cell_weight": float("nan"),
                "via_code": None,
                "via_iri": None,
                "association_type": None,
                "confidence": None,
                "selected": False,
                "constrained": False,
                "annual_volume_m3": annual_vol,
                "record_kind": record_kind,
                "volume_year": vol_year,
            }
        )

    return _finalize_frame(rows)


def _chains_arm_c(
    code_bss: str,
    policy: str,
    year: int | None,
    dataset: str,
    index: dict[str, Any],
) -> pd.DataFrame:
    groups = _load_explain_groups()
    edges_c = _cached_edges("C", policy, dataset)
    driver_rels = ("recharge", "pumping", "river", "canal")
    well_edges = edges_c[(edges_c["dst"] == code_bss) & (edges_c["relation"].isin(driver_rels))]

    rows: list[dict[str, Any]] = []
    for e in well_edges.itertuples(index=False):
        rel = str(e.relation)
        report_group = _EXPORT_TO_REPORT[rel]
        driver_group = groups[report_group]["driver_group"]
        code = str(e.src)
        driver_iri, label = index["entity_meta"].get(code, (None, None))
        if rel == "pumping":
            water_use, annual_vol, record_kind, vol_year = _facility_volume_and_use(code, year, index)
        else:
            water_use, annual_vol, record_kind, vol_year = None, float("nan"), None, None
        dist = float(e.distance_m) if pd.notna(e.distance_m) else float("nan")
        cweight = float(e.weight) if rel == "recharge" and pd.notna(e.weight) else float("nan")
        rows.append(
            {
                "report_group": report_group,
                "path": "distance rule",
                "influence": None,
                "driver_iri": driver_iri,
                "driver_code": code,
                "label": label,
                "water_use": water_use,
                "mechanism": None,
                "response_sign": None,
                "driver_group": driver_group,
                "distance_m": dist,
                "cell_weight": cweight,
                "via_code": None,
                "via_iri": None,
                "association_type": None,
                "confidence": None,
                "selected": False,
                "constrained": False,
                "annual_volume_m3": annual_vol,
                "record_kind": record_kind,
                "volume_year": vol_year,
            }
        )

    return _finalize_frame(rows)


def chains(
    well: str,
    policy: str = "main",
    arm: str = "D",
    year: int | None = None,
    *,
    recharge: str = "recharge",
    dataset: str = DATASET,
    store: ox.Store | None = None,
) -> pd.DataFrame:
    """Return the knowledge-graph records (or arm C distance-rule edges) behind one well's drivers.

    Parameters
    ----------
    well : str
        Piezometer BSS code (e.g. ``"10906X0039/C2-1"``) or piezometer IRI.
    policy : {"main", "confident-only", "all-links"}, default "main"
        Export policy selecting which qualified links enter the model.
    arm : {"D", "C"}, default "D"
        ``"D"`` reads selected influences from ``tests/cq/cq08_influences.rq`` plus the export's
        ``pumping_unattributed`` edges; ``"C"`` reads the distance-rule export edges with
        ``influence=None`` and ``path="distance rule"``.
    year : int or None, default None
        Calendar year for facility annual abstraction volumes (m³) from the graph's
        ``lulcw:AnnualAbstractionRecord`` nodes. When ``None`` or absent in the graph,
        ``annual_volume_m3`` is ``NaN`` and ``record_kind`` is ``None``.
    recharge : {"recharge", "recharge_unitwide"}, default "recharge"
        Recharge relation for arm D (5 km search zone by default, or unit-wide sensitivity).
    dataset : str, default PFE_DATASET
        Dataset release version (e.g. ``"v4"``).
    store : pyoxigraph.Store or None, default None
        Optional pre-loaded store; defaults to the per-process cached store.
    """
    if policy not in VALID_POLICIES:
        raise ValueError(f"Unknown policy {policy!r}: expected one of {VALID_POLICIES}")
    if arm not in VALID_ARMS:
        raise ValueError(f"Unknown arm {arm!r}: expected one of {VALID_ARMS}")
    if recharge not in VALID_RECHARGE:
        raise ValueError(f"Unknown recharge relation {recharge!r}: expected one of {VALID_RECHARGE}")
    if arm == "C" and recharge != "recharge":
        raise ValueError("Arm C has no 'recharge_unitwide' relation")
    if year is not None and not isinstance(year, (int, np.integer)):
        raise TypeError(f"year must be an int or None, got {year!r}")

    kg = cached_store(dataset) if store is None else store
    index = _store_index(kg)
    code_bss, well_iri = _resolve_well(well, index)

    if arm == "D":
        return _chains_arm_d(code_bss, well_iri, policy, year, recharge, dataset, kg, index)
    return _chains_arm_c(code_bss, policy, year, dataset, index)


def check_against_export(
    well: str,
    policy: str = "main",
    arm: str = "D",
    *,
    recharge: str = "recharge",
    dataset: str = DATASET,
    store: ox.Store | None = None,
    tol: float = WEIGHT_TOL,
) -> dict[str, Any]:
    """Verify that ``chains()`` cites the exact sources and recharge weights the model saw.

    Checks for each driver relation (recharge, pumping, pumping_unattributed, river, canal) that:
    1. the set of driver codes in ``chains(well, policy, arm)`` equals the set of ``src`` nodes
       in ``edges_<arm>.parquet`` for ``dst == well``;
    2. every recharge cell's weight agrees with the export edge table within ``tol`` (default 1e-9).

    Raises ``AssertionError`` on any discrepancy and returns a summary dict on success.
    """
    kg = cached_store(dataset) if store is None else store
    index = _store_index(kg)
    code_bss, _ = _resolve_well(well, index)

    df = chains(code_bss, policy=policy, arm=arm, recharge=recharge, dataset=dataset, store=kg)
    edges = _cached_edges(arm, policy, dataset)
    well_edges = edges[edges["dst"] == code_bss]

    relation_pairs = (
        (recharge, "recharge"),
        ("pumping", "pumping_attributed"),
        ("pumping_unattributed", "pumping_unattributed"),
        ("river", "river"),
        ("canal", "canal"),
    )

    counts: dict[str, int] = {}
    max_weight_diff = 0.0
    for export_rel, report_group in relation_pairs:
        got_sub = df[df["report_group"] == report_group]
        exp_sub = well_edges[well_edges["relation"] == export_rel]
        got_set = set(got_sub["driver_code"])
        exp_set = set(exp_sub["src"])
        if got_set != exp_set:
            only_got = sorted(got_set - exp_set)[:5]
            only_exp = sorted(exp_set - got_set)[:5]
            raise AssertionError(
                f"{code_bss} (arm={arm}, policy={policy}, relation={export_rel}): "
                f"sources differ from export (only in chains: {only_got}; only in export: {only_exp})"
            )
        counts[report_group] = len(got_set)

        if report_group == "recharge" and not exp_sub.empty:
            exp_weights = dict(zip(exp_sub["src"], exp_sub["weight"].astype(float)))
            for cell, grp in got_sub.groupby("driver_code", sort=False):
                ws = grp["cell_weight"].to_numpy(dtype=float)
                if np.isnan(ws).any():
                    raise AssertionError(
                        f"{code_bss} (arm={arm}, policy={policy}): NaN cell_weight for {cell}"
                    )
                got_w = math.fsum(ws) / len(ws)
                diff = abs(got_w - exp_weights[cell])
                max_weight_diff = max(max_weight_diff, diff)
                if diff > tol:
                    raise AssertionError(
                        f"{code_bss} (arm={arm}, policy={policy}): recharge cell {cell} weight "
                        f"{got_w:.12g} differs from export {exp_weights[cell]:.12g} (diff {diff:.2e} > {tol:.1e})"
                    )

    return {
        "well": code_bss,
        "policy": policy,
        "arm": arm,
        "counts": counts,
        "n_rows": int(len(df)),
        "max_recharge_weight_diff": max_weight_diff,
    }


def format_chains(
    df: pd.DataFrame,
    well: str,
    policy: str,
    arm: str,
    year: int | None,
    *,
    max_unattributed: int | None = 15,
) -> str:
    """Format a chains table as a plain-text report for the CLI."""
    counts = {
        grp: int(df.loc[df["report_group"] == grp, "driver_code"].nunique())
        for grp in REPORT_GROUP_ORDER
    }
    year_str = str(year) if year is not None else "none"
    lines = [
        f"Well: {well}  |  arm: {arm}  |  policy: {policy}  |  year: {year_str}",
        "Sources per report_group: "
        + ", ".join(f"{grp}={counts[grp]}" for grp in REPORT_GROUP_ORDER)
        + f" (rows={len(df)})",
    ]
    if df.empty:
        lines.append("(no driver records)")
        return "\n".join(lines)

    show_cols = [
        "report_group",
        "path",
        "driver_code",
        "label",
        "water_use",
        "via_code",
        "distance_m",
        "cell_weight",
        "confidence",
        "constrained",
        "annual_volume_m3",
        "record_kind",
    ]

    def _fmt(sub: pd.DataFrame) -> str:
        view = sub[show_cols].copy()
        view["label"] = view["label"].map(
            lambda x: (x[:38] + "...") if isinstance(x, str) and len(x) > 41 else (x or "-")
        )
        view["water_use"] = view["water_use"].fillna("-")
        view["via_code"] = view["via_code"].fillna("-")
        view["confidence"] = view["confidence"].fillna("-")
        view["record_kind"] = view["record_kind"].fillna("-")
        view["distance_m"] = view["distance_m"].map(lambda x: f"{x:.0f}" if pd.notna(x) else "-")
        view["cell_weight"] = view["cell_weight"].map(lambda x: f"{x:.4f}" if pd.notna(x) else "-")
        view["annual_volume_m3"] = view["annual_volume_m3"].map(
            lambda x: f"{x:,.0f}" if pd.notna(x) else "-"
        )
        return view.to_string(index=False)

    primary = df[df["report_group"] != "pumping_unattributed"]
    unattr = df[df["report_group"] == "pumping_unattributed"]

    if not primary.empty:
        lines.append("")
        lines.append(_fmt(primary))
    if not unattr.empty:
        lines.append("")
        if max_unattributed is not None and len(unattr) > max_unattributed:
            lines.append(
                f"Unattributed pumping ({len(unattr)} facilities within 5 km; "
                f"showing nearest {max_unattributed}, pass --all for every row):"
            )
            lines.append(_fmt(unattr.head(max_unattributed)))
        else:
            lines.append(f"Unattributed pumping ({len(unattr)} facilities within 5 km):")
            lines.append(_fmt(unattr))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="List the knowledge-graph records behind each model driver for one well."
    )
    parser.add_argument("well", help="Piezometer BSS code (e.g. 10906X0039/C2-1) or IRI.")
    parser.add_argument(
        "--policy",
        default="main",
        choices=VALID_POLICIES,
        help="Export policy (default: main).",
    )
    parser.add_argument(
        "--arm",
        default="D",
        choices=VALID_ARMS,
        help="Graph arm: D (knowledge graph) or C (distance rules) (default: D).",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Calendar year for facility declared annual volumes (m3).",
    )
    parser.add_argument(
        "--recharge",
        default="recharge",
        choices=VALID_RECHARGE,
        help="Recharge relation for arm D (default: recharge).",
    )
    parser.add_argument(
        "--dataset",
        default=DATASET,
        help=f"Dataset version (default: {DATASET}).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Show all unattributed pumping rows instead of truncating to the nearest 15.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Also run check_against_export() and print the result.",
    )
    args = parser.parse_args(argv)

    df = chains(
        args.well,
        policy=args.policy,
        arm=args.arm,
        year=args.year,
        recharge=args.recharge,
        dataset=args.dataset,
    )
    print(
        format_chains(
            df,
            args.well,
            args.policy,
            args.arm,
            args.year,
            max_unattributed=None if args.all else 15,
        )
    )
    if args.check:
        summary = check_against_export(
            args.well,
            policy=args.policy,
            arm=args.arm,
            recharge=args.recharge,
            dataset=args.dataset,
        )
        print(
            f"\nExport equivalence check: PASS "
            f"(max recharge weight diff = {summary['max_recharge_weight_diff']:.2e})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
