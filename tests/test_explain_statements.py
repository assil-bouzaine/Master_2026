"""Check the Step 15 statement rules and templates (analysis plan §12).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_explain_statements

Hand-made tables isolate every rule. A saved ladder run exercises the CLI.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from math import nextafter
from time import perf_counter
from unittest.mock import patch

import pandas as pd

from src.explain import statements as S

WELL = "TEST-1"
TARGET = "2024-06-01:2024-09-30"
PUMPING = "pumping_attributed"
ATTRIBUTIONS = pd.DataFrame([
    (PUMPING, "to the groundwater pumping on the well's knowledge-graph links",
     "aux prélèvements d'eau souterraine reliés au piézomètre par le graphe de connaissances"),
    ("pumping_unattributed", "to the nearby groundwater pumping", "aux prélèvements d'eau souterraine voisins"),
    ("recharge", "to the recharge proxy", "à l'indicateur de recharge"),
    ("residual", "to the fixed seasonal residual (no driver)", "au résidu saisonnier fixe (sans forçage)"),
], columns=["report_group", "to_en", "to_fr"])


def decomposition(*, group=PUMPING, mean=0.25, agreement=1.0, strict=75, observed=100,
                  imputed=0.0, reconstruction=1):
    return {
        "target": tuple(TARGET.split(":")),
        "reference": {"kind": "average_forcing", "space": "input", "window": ("2005-01-01", "2019-12-31")},
        "by_report_group": pd.DataFrame(
            [(WELL, group, mean, 0.02, agreement, 10)],
            columns=["code_bss", "report_group", "mean_m", "sd_m", "sign_agreement", "n_seeds"],
        ),
        "flags": pd.DataFrame([{
            "code_bss": WELL, "n_weeks": 100, "n_observed": observed, "n_strict": strict,
            "share_strict": strict / 100, "share_pumping_imputed": imputed,
        }]),
        "metadata": {"pumping_reconstruction": reconstruction},
    }


def only_statement(result, **kwargs):
    with patch.object(S, "load_groups", return_value=ATTRIBUTIONS):
        record, = S.statements(result, WELL, **kwargs)
    return record


def assert_status(record, status, reasons):
    assert record["status"] == status, record
    assert record["reasons"] == reasons, record
    if status == "withheld":
        assert record["text_en"] is None and record["text_fr"] is None, record


def test_individual_rules_and_boundaries():
    cases = [
        ({}, {}, "accepted", []),
        ({"imputed": nextafter(0.10, 1.0)}, {}, "withheld", ["high_imputed_pumping_share"]),
        ({"agreement": nextafter(0.80, 0.0)}, {}, "withheld", ["low_sign_agreement"]),
        ({"mean": nextafter(0.05, 0.0)}, {}, "withheld", ["small_contribution"]),
        ({}, {"siblings": {2: decomposition(mean=-0.25)}},
         "withheld", ["pumping_reconstruction_sign_disagreement"]),
        ({"strict": 49}, {}, "qualified", ["low_validated_observation_share"]),
        ({"strict": 0, "observed": 0}, {}, "qualified", ["no_observed_weeks"]),
        ({"imputed": 0.02}, {}, "qualified", ["imputed_pumping"]),
        ({}, {"probable_only": True}, "qualified", ["probable_only"]),
        ({}, {"probable_only": {"recharge": True}}, "accepted", []),
        # Equal to 0.05 m or 80 % meets the respective minimum.
        ({"mean": 0.05}, {}, "accepted", []),
        ({"mean": -0.05}, {}, "accepted", []),
        ({"agreement": 0.80}, {}, "accepted", []),
        # Equal to 10 % qualifies. Zero and zero routed volume carry no pumping caveat.
        ({"imputed": 0.10}, {}, "qualified", ["imputed_pumping"]),
        ({"imputed": 0.0}, {}, "accepted", []),
        ({"imputed": float("nan")}, {}, "accepted", []),
        # Validation uses the observed weeks, and exactly 50 % meets the minimum.
        ({"strict": 25, "observed": 50}, {}, "accepted", []),
        ({"strict": 24, "observed": 50}, {}, "qualified", ["low_validated_observation_share"]),
        ({}, {"siblings": {2: decomposition(mean=0.02), 3: decomposition(mean=0.31)}}, "accepted", []),
        ({}, {"siblings": {2: decomposition(mean=0.25), 3: decomposition(mean=0.0)}},
         "withheld", ["pumping_reconstruction_sign_disagreement"]),
        ({"group": "pumping_unattributed", "imputed": 0.11}, {}, "withheld", ["high_imputed_pumping_share"]),
        ({"group": "recharge", "imputed": 0.80}, {"siblings": {2: decomposition()}}, "accepted", []),
    ]
    for inputs, options, status, reasons in cases:
        assert_status(only_statement(decomposition(**inputs), **options), status, reasons)
    print("  Individual rules and equality boundaries passed.")


def test_combined_rules_and_residual():
    result = decomposition(mean=0.04, agreement=0.70, strict=40, imputed=0.11)
    options = {"siblings": {2: decomposition(mean=-0.06)}, "probable_only": {PUMPING: True}}
    assert_status(only_statement(result, **options), "withheld", [
        "high_imputed_pumping_share", "low_sign_agreement", "pumping_reconstruction_sign_disagreement",
        "small_contribution", "low_validated_observation_share", "probable_only",
    ])
    result["flags"]["share_pumping_imputed"] = 0.10
    assert_status(only_statement(result, **options), "withheld", [
        "low_sign_agreement", "pumping_reconstruction_sign_disagreement", "small_contribution",
        "low_validated_observation_share", "imputed_pumping", "probable_only",
    ])

    qualified = only_statement(decomposition(strict=30, imputed=0.023), probable_only=True)
    assert_status(qualified, "qualified", ["low_validated_observation_share", "imputed_pumping", "probable_only"])
    assert qualified["text_en"] == (
        "Compared with an average year at the same time (2005–2019 forcing), the model attributes "
        "a rise of 0.25 m of the simulated head at TEST-1 over the period from 1 June to 30 September 2024 "
        "to the groundwater pumping on the well's knowledge-graph links. "
        "Caveat: only 30 % of the observed weeks are validated. "
        "Caveat: 2.3 % of the routed pumping volume is imputed. "
        "Caveat: the knowledge-graph path rests only on probable links."
    )
    assert qualified["text_fr"] == (
        "Par rapport à une année moyenne à la même époque (forçages 2005–2019), le modèle attribue "
        "une hausse de 0,25 m du niveau simulé à TEST-1 sur la période du 1er juin au 30 septembre 2024 "
        "aux prélèvements d'eau souterraine reliés au piézomètre par le graphe de connaissances. "
        "Réserve : seules 30 % des semaines observées sont validées. "
        "Réserve : 2,3 % du volume de prélèvement acheminé est imputé. "
        "Réserve : le chemin dans le graphe de connaissances repose uniquement sur des liens probables."
    )

    zero_validated = only_statement(decomposition(group="recharge", mean=-2.127, strict=0))
    assert_status(zero_validated, "qualified", ["low_validated_observation_share"])
    assert zero_validated["text_en"] == (
        "Compared with an average year at the same time (2005–2019 forcing), the model attributes "
        "a lowering of 2.13 m of the simulated head at TEST-1 over the period from 1 June to 30 September 2024 "
        "to the recharge proxy. Caveat: none of the observed weeks is validated."
    )
    assert zero_validated["text_fr"] == (
        "Par rapport à une année moyenne à la même époque (forçages 2005–2019), le modèle attribue "
        "une baisse de 2,13 m du niveau simulé à TEST-1 sur la période du 1er juin au 30 septembre 2024 "
        "à l'indicateur de recharge. Réserve : aucune des semaines observées n'est validée."
    )

    residual = only_statement(decomposition(group="residual", mean=-0.01, agreement=0.20, strict=0,
                                           imputed=0.99), probable_only=True)
    assert_status(residual, "accepted", [])
    assert residual["text_en"] == "The residual is a fixed seasonal term with no driver."
    assert residual["text_fr"] == "Le résidu est un terme saisonnier fixe sans forçage."
    print("  Combined reasons, caveats and residual passed.")


def test_templates_and_reference():
    result = decomposition()
    assert only_statement(result) == {
        "report_group": PUMPING, "mean_m": 0.25, "sd_m": 0.02, "sign_agreement": 1.0,
        "status": "accepted", "reasons": [],
        "text_en": (
            "Compared with an average year at the same time (2005–2019 forcing), the model attributes "
            "a rise of 0.25 m of the simulated head at TEST-1 over the period from 1 June to 30 September 2024 "
            "to the groundwater pumping on the well's knowledge-graph links."
        ),
        "text_fr": (
            "Par rapport à une année moyenne à la même époque (forçages 2005–2019), le modèle attribue "
            "une hausse de 0,25 m du niveau simulé à TEST-1 sur la période du 1er juin au 30 septembre 2024 "
            "aux prélèvements d'eau souterraine reliés au piézomètre par le graphe de connaissances."
        ),
    }

    result = decomposition(mean=-0.61)
    result["target"] = ("2024-12-21", "2025-02-01")
    result["reference"] = {"kind": "window", "window": ("2023-12-21", "2024-02-01")}
    negative = only_statement(result)
    assert negative["text_en"] == (
        "Compared with the same weeks from 21 December 2023 to 1 February 2024, "
        "the model attributes a lowering of 0.61 m of the simulated head at TEST-1 "
        "over the period from 21 December 2024 to 1 February 2025 "
        "to the groundwater pumping on the well's knowledge-graph links."
    )
    assert negative["text_fr"] == (
        "Par rapport à la même période du 21 décembre 2023 au 1er février 2024, "
        "le modèle attribue une baisse de 0,61 m du niveau simulé à TEST-1 "
        "sur la période du 21 décembre 2024 au 1er février 2025 "
        "aux prélèvements d'eau souterraine reliés au piézomètre par le graphe de connaissances."
    )
    french = only_statement(result, lang=("fr",))
    assert french["text_en"] is None and french["text_fr"] == negative["text_fr"]
    result["reference"] = {"kind": "training_seasonal", "window": ("2015-01-01", "2019-12-31")}
    seasonal = only_statement(result)
    assert seasonal["text_en"] == (
        "Compared with the seasonal mean of the model's contributions (2015–2019 training period), "
        "the model attributes a lowering of 0.61 m of the simulated head at TEST-1 "
        "over the period from 21 December 2024 to 1 February 2025 "
        "to the groundwater pumping on the well's knowledge-graph links."
    )
    assert seasonal["text_fr"] == (
        "Par rapport à la moyenne saisonnière des contributions du modèle (entraînement 2015–2019), "
        "le modèle attribue une baisse de 0,61 m du niveau simulé à TEST-1 "
        "sur la période du 21 décembre 2024 au 1er février 2025 "
        "aux prélèvements d'eau souterraine reliés au piézomètre par le graphe de connaissances."
    )
    print("  Exact bilingual templates, both directions, references and language selection passed.")


def test_cli_siblings():
    runs = [decomposition(), decomposition(reconstruction=2), decomposition(mean=-0.1, reconstruction=3)]
    output = StringIO()
    with (patch.object(S, "load_groups", return_value=ATTRIBUTIONS),
          patch.object(S, "decompose", side_effect=runs) as load, redirect_stdout(output)):
        assert S.main(["run1", "--target", TARGET, "--well", WELL, "--sibling", "run2", "run3"]) == 0
    assert [call.args for call in load.call_args_list] == [("run1",), ("run2",), ("run3",)]
    assert all(call.kwargs == {"target": TARGET, "wells": [WELL]} for call in load.call_args_list)
    text = output.getvalue()
    assert "sign check ran for reconstructions 1, 2, 3" in text
    assert "pumping_attributed [withheld]" in text and "pumping_reconstruction_sign_disagreement" in text
    assert "the model attributes" not in text
    print("  CLI sibling dispatch and sign disagreement passed.")


def test_real_run():
    wells = ["10964X0119/NYLS-1", "10906X0039/C2-1"]
    output = StringIO()
    with redirect_stdout(output):
        assert S.main(["resp_pooled_l001", "--target", TARGET, "--well", *wells]) == 0
    text = output.getvalue()
    assert "Pumping reconstruction sign check: not checked" in text
    for well in wells:
        assert f"\n{well}\n" in text
        assert f"simulated head at {well}" in text
        assert f"niveau simulé à {well}" in text
    print("\nSummer 2024 statements from resp_pooled_l001")
    print(text.rstrip())


def main():
    started = perf_counter()
    test_individual_rules_and_boundaries()
    test_combined_rules_and_residual()
    test_templates_and_reference()
    test_cli_siblings()
    test_real_run()
    print(f"\ntest_explain_statements: all checks passed ({perf_counter() - started:.1f}s)")


if __name__ == "__main__":
    main()
