"""Checks of the one-well explanation report (src/explain/report.py, Phase 5, CQ10).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_explain_report

1. Real run ``p4_B4_D_soft1_r1`` (arm D, R1, reconstruction 1), summer 2024
   (``2024-06-01:2024-09-30``), for ``10964X0119/NYLS-1`` and ``10906X0039/C2-1``:
   - renders in both ``en`` and ``fr`` with all five required sections and caveat line;
   - the sum of the listed report-group contributions equals the stated simulated change within
     ``1e-6 m``;
   - every facility listed in the report belongs to the well's export edges (reuses
     ``check_against_export`` and checks every ``OPR...`` code in the rendered text).
2. All five driver record sections exercised on real knowledge-graph chains of
   ``10906X0039/C2-1`` (top facilities by 2024 declared volume with routed-volume share,
   unattributed pumping summary, recharge cells/weights/outcrop unit, river gauge/path type,
   canal intake group) in EN and FR, verifying every listed facility against export edges.
3. Withheld statements built from a hand-made decomposition (as in
   ``tests/test_explain_statements.py``) list their reasons, omit any statement sentence, and
   receive no records subsection even when chain records exist for those groups.
4. ``write_report`` and CLI smoke checks using temporary paths only (never writing into ``docs/``).
"""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import math
from pathlib import Path
import re
import tempfile
from time import perf_counter

import pandas as pd

from src.explain import report as R
from src.explain.chains import cached_store, chains, check_against_export
from src.models.routing import load_edges

RUN = "p4_B4_D_soft1_r1"
TARGET = "2024-06-01:2024-09-30"
NYLS = "10964X0119/NYLS-1"
C2 = "10906X0039/C2-1"
_BNPE_RE = re.compile(r"\bOPR\d+\b")


def _hand_made_decomposition(
    well: str,
    rows: list[tuple[str, float, float, float]],
    *,
    observed: int = 18,
    strict: int = 18,
    imputed: float = 0.0,
    reconstruction: int = 1,
) -> dict:
    """Build a minimal decomposition dict matching ``contributions.decompose()``."""
    by_rg = pd.DataFrame(
        [(well, g, mean, sd, agr, 10) for g, mean, sd, agr in rows],
        columns=["code_bss", "report_group", "mean_m", "sd_m", "sign_agreement", "n_seeds"],
    )
    tot_mean = math.fsum(mean for _, mean, _, _ in rows)
    total = pd.DataFrame(
        [(well, tot_mean, 0.05, 1.0, 10)],
        columns=["code_bss", "mean_m", "sd_m", "sign_agreement", "n_seeds"],
    )
    flags = pd.DataFrame(
        [
            {
                "code_bss": well,
                "core": True,
                "n_weeks": 18,
                "n_observed": observed,
                "share_observed": observed / 18,
                "n_strict": strict,
                "share_strict": strict / 18,
                "n_placeholder": 0,
                "share_placeholder": 0.0,
                "routed_pumping_m3": 1_000_000.0,
                "imputed_pumping_m3": imputed * 1_000_000.0,
                "share_pumping_imputed": imputed,
            }
        ]
    )
    return {
        "run": "synthetic_run",
        "dataset": "v4",
        "target": tuple(TARGET.split(":")),
        "n_target_weeks": 18,
        "reference": {
            "kind": "average_forcing",
            "space": "input",
            "window": ("2005-01-01", "2019-12-31"),
        },
        "n_seeds": 10,
        "by_report_group": by_rg,
        "total": total,
        "flags": flags,
        "metadata": {
            "run": "synthetic_run",
            "dataset": "v4",
            "regime": "R1",
            "arm": "D",
            "export_policy": "main",
            "pumping_reconstruction": reconstruction,
            "pumping_reconstruction_name": "current",
            "mode": "pooled",
            "signs": "gate3",
            "residual": "none",
            "protocol": "pooled_l0.01_earlystop",
        },
    }


def test_real_run_both_wells_and_languages():
    store = cached_store("v4")
    edges_d, _ = load_edges("D", policy="main", dataset="v4")

    for well in (NYLS, C2):
        # Reuse check_against_export to guarantee chain/export equivalence for the well.
        chk = check_against_export(well, policy="main", arm="D", dataset="v4", store=store)
        assert chk["well"] == well

        data = R.build_report_data(RUN, well, TARGET, dataset="v4", store=store)
        listed_sum = math.fsum(c["mean_m"] for c in data["contributions"])
        stated_change = data["total"]["mean_m"]
        diff = abs(listed_sum - stated_change)
        assert diff < 1e-6, f"{well}: sum {listed_sum} != stated change {stated_change} (diff {diff})"

        export_facs = set(
            edges_d[
                (edges_d["dst"] == well)
                & (edges_d["relation"].isin(("pumping", "pumping_unattributed")))
            ]["src"]
        )

        for lang in ("en", "fr"):
            text = R.explain(RUN, well, TARGET, lang=lang, dataset="v4")
            assert text == R.render_report(data, lang=lang)
            assert well in text
            assert data["well"]["label"] in text
            assert data["well"]["unit_code"] in text
            assert R.CAVEAT_LINE[lang] in text

            # Every report group in the decomposition appears in the contributions table.
            for c in data["contributions"]:
                assert f"`{c['report_group']}`" in text

            # Every withheld statement has no records subsection.
            for st in data["statements"]:
                grp = st["report_group"]
                if st["status"] == "withheld":
                    assert grp not in data["records"]
                    assert f"({grp})" not in text.split("## Records behind" if lang == "en" else "## Enregistrements")[-1]
                    for reason in st["reasons"]:
                        assert reason in text
                elif st["status"] in ("accepted", "qualified") and grp in R.DRIVER_REPORT_GROUPS:
                    assert grp in data["records"]
                    assert f"(`{grp}`)" in text.split("## Records behind" if lang == "en" else "## Enregistrements")[-1]

            # Every BNPE facility code appearing in the rendered report is in the well's export edges.
            cited_facs = set(_BNPE_RE.findall(text))
            assert cited_facs.issubset(export_facs), (
                f"{well} ({lang}): cited facilities not in export: {cited_facs - export_facs}"
            )

            # Monthly SGI classes appear (summer 2024 has 4 months: 2024-06..2024-09).
            for month in ("2024-06", "2024-07", "2024-08", "2024-09"):
                assert month in text

        # Well-specific sanity checks on p4_B4_D_soft1_r1 summer 2024.
        if well == NYLS:
            assert "recharge" in data["records"] and "pumping_unattributed" in data["records"]
            assert "pumping_attributed" not in data["records"]
        elif well == C2:
            assert "recharge" in data["records"]
            assert "pumping_attributed" not in data["records"]

    print(
        f"  1. Real run {RUN} (summer 2024, {NYLS} & {C2}): EN/FR reports pass additivity (<1e-6 m), "
        "monthly SGI, statement gating, and export-edge facility checks."
    )


def test_all_driver_record_sections_against_export():
    """Exercise pumping_attributed, pumping_unattributed, recharge, river, and canal records on C2-1."""
    store = cached_store("v4")
    check_against_export(C2, policy="main", arm="D", dataset="v4", store=store)
    edges_d, _ = load_edges("D", policy="main", dataset="v4")
    c2_attr_export = set(
        edges_d[(edges_d["dst"] == C2) & (edges_d["relation"] == "pumping")]["src"]
    )
    ch = chains(C2, policy="main", arm="D", year=2024, dataset="v4", store=store)
    w_info, unit_labels = R._well_info(C2, dataset="v4", store=store)
    ew, rwin = R._routed_pumping_by_facility(C2, ("2024-06-01", "2024-09-30"), "D", "main", 1, dataset="v4")

    decomp = _hand_made_decomposition(
        C2,
        [
            ("recharge", -0.35, 0.04, 1.0),
            ("pumping_attributed", -0.22, 0.03, 1.0),
            ("pumping_unattributed", -0.11, 0.02, 1.0),
            ("river", -0.18, 0.04, 0.9),
            ("canal", +0.12, 0.03, 0.9),
        ],
        imputed=0.02,
    )
    data = R.build_report_from_decomposition(
        decomp,
        C2,
        chain_df=ch,
        well_info=w_info,
        unit_labels=unit_labels,
        policy="main",
        arm="D",
        top=5,
        volume_year=2024,
        edge_weights=ew,
        routed_window_m3=rwin,
    )
    assert abs(math.fsum(c["mean_m"] for c in data["contributions"]) - data["total"]["mean_m"]) < 1e-12
    assert set(data["records"]) == {"recharge", "pumping_attributed", "pumping_unattributed", "river", "canal"}

    p_rec = data["records"]["pumping_attributed"]
    assert len(p_rec["top_facilities"]) == 5
    listed_codes = [f["driver_code"] for f in p_rec["top_facilities"]]
    assert set(listed_codes).issubset(c2_attr_export)
    # Ordered descending by declared 2024 volume.
    vols = [f["annual_volume_m3"] for f in p_rec["top_facilities"]]
    assert vols == sorted(vols, reverse=True)
    assert 0.0 < p_rec["share_routed_volume"] <= 1.0 + 1e-9

    for lang in ("en", "fr"):
        text = R.render_report(data, lang=lang)
        cited = set(_BNPE_RE.findall(text))
        assert cited == set(listed_codes), (lang, cited, listed_codes)
        assert "6280_17450" in text and "718BP02" in text
        assert "Y046403001" in text
        assert ("on outcrop" if lang == "en" else "sur l'affleurement") in text
        assert "canal-intakes:plain" in text
        assert ("not selected by the `main` export policy" if lang == "en" else "pas retenu par la politique d'export `main`") in text
        assert R.CAVEAT_LINE[lang] in text

    print(
        "  2. All five driver record sections (pumping_attributed top 5 + routed share, "
        "pumping_unattributed, recharge, river, canal) pass in EN/FR and match export edges."
    )


def test_withheld_statement_lists_reasons_and_has_no_records():
    """Hand-made decomposition: withheld groups show reasons, no sentence, and no records section."""
    store = cached_store("v4")
    ch = chains(C2, policy="main", arm="D", year=2024, dataset="v4", store=store)

    # Case A: one withheld pumping group (high imputed share + low sign agreement) and one accepted recharge group.
    decomp_mixed = _hand_made_decomposition(
        C2,
        [
            ("recharge", -0.40, 0.03, 1.0),
            ("pumping_attributed", -0.25, 0.08, 0.6),
            ("river", -0.02, 0.01, 1.0),
        ],
        imputed=0.25,
    )
    data_mixed = R.build_report_from_decomposition(
        decomp_mixed,
        C2,
        chain_df=ch,
        policy="main",
        arm="D",
        top=5,
        volume_year=2024,
    )
    assert set(data_mixed["records"]) == {"recharge"}
    for lang in ("en", "fr"):
        text = R.render_report(data_mixed, lang=lang)
        # Reasons are listed for withheld groups.
        assert "high_imputed_pumping_share" in text
        assert "low_sign_agreement" in text
        assert "small_contribution" in text
        # No pumping facility or river gauge records appear anywhere in the report.
        assert not _BNPE_RE.findall(text)
        assert "Y046403001" not in text
        # Accepted recharge DOES have its records.
        assert "6280_17450" in text
        # Withheld lines carry no templated attribution sentence.
        stmt_sec = text.split("### Statements" if lang == "en" else "### Énoncés")[1].split("\n## ")[0]
        marker = "the model attributes" if lang == "en" else "le modèle attribue"
        assert stmt_sec.count(marker) == 1

    # Case B: all driver groups withheld (including reconstruction sign disagreement via sibling).
    decomp_all_w = _hand_made_decomposition(
        C2,
        [("pumping_attributed", -0.25, 0.02, 1.0)],
        imputed=0.0,
        reconstruction=1,
    )
    sib = _hand_made_decomposition(
        C2,
        [("pumping_attributed", +0.15, 0.02, 1.0)],
        imputed=0.0,
        reconstruction=2,
    )
    data_all_w = R.build_report_from_decomposition(
        decomp_all_w,
        C2,
        siblings={2: sib},
        chain_df=ch,
        policy="main",
        arm="D",
        volume_year=2024,
    )
    assert data_all_w["records"] == {}
    for lang in ("en", "fr"):
        text = R.render_report(data_all_w, lang=lang)
        assert "pumping_reconstruction_sign_disagreement" in text
        stmt_sec = text.split("### Statements" if lang == "en" else "### Énoncés")[1].split("\n## ")[0]
        assert ("the model attributes" if lang == "en" else "le modèle attribue") not in stmt_sec
        assert not _BNPE_RE.findall(text)
        assert ("no driver records are listed" if lang == "en" else "aucun enregistrement n'est donc listé") in text

    print(
        "  3. Hand-made withheld statements list their reasons, omit sentences, and get no records section."
    )


def test_write_report_and_cli_temp_only():
    with tempfile.TemporaryDirectory() as tmp:
        out_en = Path(tmp) / "sub" / "nyls_en.md"
        written = R.write_report(out_en, RUN, NYLS, TARGET, lang="en", dataset="v4")
        assert written == out_en and out_en.is_file()
        assert NYLS in out_en.read_text(encoding="utf-8")

        out_fr = Path(tmp) / "c2_fr.md"
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = R.main([RUN, C2, "--target", TARGET, "--lang", "fr", "--out", str(out_fr)])
        assert rc == 0 and out_fr.is_file()
        fr_text = out_fr.read_text(encoding="utf-8")
        assert C2 in fr_text and R.CAVEAT_LINE["fr"] in fr_text

        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = R.main([RUN, NYLS, "--target", TARGET])
        assert rc2 == 0 and R.CAVEAT_LINE["en"] in buf2.getvalue()

    print("  4. write_report() and CLI (--out to temp path and stdout) pass in EN and FR.")


def main():
    started = perf_counter()
    test_real_run_both_wells_and_languages()
    test_all_driver_record_sections_against_export()
    test_withheld_statement_lists_reasons_and_has_no_records()
    test_write_report_and_cli_temp_only()
    print(f"\ntest_explain_report: all checks passed ({perf_counter() - started:.1f}s)")


if __name__ == "__main__":
    main()
