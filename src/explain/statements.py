"""Turn simulated head contributions into checked English and French statements.

The fixed rules from the Step 15 note and analysis plan §12 govern which
claims can be shown. The sign compares the simulated head to its reference.

    PFE_DATASET=v4 python -m src.explain.statements RUN --target START:END --well WELL
"""
from __future__ import annotations

import argparse
from collections.abc import Iterable, Mapping

import numpy as np

from src.explain.contributions import decompose, load_groups

MAX_IMPUTED_PUMPING_SHARE = 0.10
MIN_SIGN_AGREEMENT = 0.80
MIN_CONTRIBUTION_M = 0.05
MIN_VALIDATED_OBSERVATION_SHARE = 0.50
PUMPING_GROUPS = {"pumping_attributed", "pumping_unattributed"}

TEMPLATES = {
    "en": (
        "Compared with {reference}, the model attributes {direction} of {magnitude:.2f} m of the "
        "simulated head at {well} over {period} to {label}."
    ),
    "fr": (
        "Par rapport à {reference}, le modèle attribue {direction} de {magnitude:.2f} m du niveau "
        "simulé à {well} sur {period} à {label}."
    ),
}
DIRECTIONS = {"en": ("a lowering", "a rise"), "fr": ("une baisse", "une hausse")}
RESIDUAL = {
    "en": "The residual is a fixed seasonal term with no driver.",
    "fr": "Le résidu est un terme saisonnier fixe sans forçage.",
}
CAVEATS = {
    "low_validated_observation_share": {
        "en": "Caveat: only {validated} % of the observed weeks are validated.",
        "fr": "Réserve : seules {validated} % des semaines observées sont validées.",
    },
    "no_observed_weeks": {
        "en": "Caveat: there are no observed weeks in the window.",
        "fr": "Réserve : le niveau n'a été observé pendant aucune semaine de la période.",
    },
    "imputed_pumping": {
        "en": "Caveat: {imputed} % of the routed pumping volume is imputed.",
        "fr": "Réserve : {imputed} % du volume de prélèvement acheminé est imputé.",
    },
    "probable_only": {
        "en": "Caveat: the knowledge-graph path rests only on probable links.",
        "fr": "Réserve : le chemin dans le graphe de connaissances repose uniquement sur des liens probables.",
    },
}


def _reference_text(reference: dict) -> dict[str, str]:
    start, end = reference["window"]
    years = f"{start[:4]}–{end[:4]}"
    if reference["kind"] == "average_forcing":
        return {
            "en": f"an average year at the same time ({years} forcing)",
            "fr": f"une année moyenne à la même époque (forçages {years})",
        }
    if reference["kind"] == "training_seasonal":
        return {
            "en": f"the seasonal mean of the model's contributions ({years} training period)",
            "fr": f"la moyenne saisonnière des contributions du modèle (entraînement {years})",
        }
    if reference["kind"] == "window":
        return {"en": f"the same weeks of {start} to {end}", "fr": f"la même période de {start} à {end}"}
    raise ValueError(f"Unknown reference condition {reference['kind']!r}")


def _percent(share: float, language: str) -> str:
    percent = f"{share * 100:.3g}"
    return percent.replace(".", ",") if language == "fr" else percent


def _well_groups(decomposition: dict, well: str):
    return decomposition["by_report_group"].set_index(["code_bss", "report_group"]).loc[well]


def statements(
    decomposition: dict,
    well: str,
    *,
    siblings: Mapping[int, dict] | None = None,
    probable_only: bool | Mapping[str, bool] | None = None,
    lang: Iterable[str] = ("en", "fr"),
) -> list[dict]:
    """Return one record per report group for a well in ``decompose()``.

    Siblings are comparable decompositions keyed by their pumping reconstruction.
    Pass a mapping to ``probable_only`` to qualify individual report groups, or
    a bool to apply the flag to every driver. Reasons are stable codes in rule
    order, including any caveats that apply to withheld claims. Text is ``None``
    for withheld claims and for languages absent from ``lang``.
    """
    languages = tuple(lang)
    if set(languages) - TEMPLATES.keys():
        raise ValueError("Statement languages must be 'en' or 'fr'")

    groups = _well_groups(decomposition, well)
    flags = decomposition["flags"].set_index("code_bss").loc[well]
    # share_strict uses all weeks in the window. This rule uses observed weeks.
    n_observed = int(flags["n_observed"])
    validated = float(flags["n_strict"]) / n_observed if n_observed else 0.0
    imputed = float(flags["share_pumping_imputed"])
    labels = (
        load_groups()[["report_group", "label_en", "label_fr"]]
        .drop_duplicates().set_index("report_group", verify_integrity=True)
    )
    reference = _reference_text(decomposition["reference"])
    start, end = decomposition["target"]
    periods = {"en": f"the period from {start} to {end}", "fr": f"la période du {start} au {end}"}
    sibling_means = []
    if siblings and PUMPING_GROUPS.intersection(groups.index):
        sibling_means = [_well_groups(sibling, well)["mean_m"] for sibling in siblings.values()]

    records = []
    for group, row in groups.iterrows():
        mean_m = float(row["mean_m"])
        agreement = float(row["sign_agreement"])
        record = {
            "report_group": group, "mean_m": mean_m, "sd_m": float(row["sd_m"]),
            "sign_agreement": agreement, "status": "accepted", "reasons": [],
            "text_en": None, "text_fr": None,
        }
        records.append(record)
        if group == "residual":
            for language in languages:
                record[f"text_{language}"] = RESIDUAL[language]
            continue

        pumping = group in PUMPING_GROUPS
        withheld = []
        caveats = []
        # A NaN imputed share means zero routed volume and triggers neither pumping rule.
        if pumping and imputed > MAX_IMPUTED_PUMPING_SHARE:
            withheld.append("high_imputed_pumping_share")
        if agreement < MIN_SIGN_AGREEMENT:
            withheld.append("low_sign_agreement")
        if pumping and sibling_means:
            signs = {np.sign(means.loc[group]) for means in sibling_means}
            signs.add(np.sign(mean_m))
            if len(signs) > 1:
                withheld.append("pumping_reconstruction_sign_disagreement")
        if abs(mean_m) < MIN_CONTRIBUTION_M:
            withheld.append("small_contribution")
        if not n_observed:
            caveats.append("no_observed_weeks")
        elif validated < MIN_VALIDATED_OBSERVATION_SHARE:
            caveats.append("low_validated_observation_share")
        if pumping and 0.0 < imputed <= MAX_IMPUTED_PUMPING_SHARE:
            caveats.append("imputed_pumping")
        probable = probable_only.get(group, False) if isinstance(probable_only, Mapping) else probable_only
        if probable:
            caveats.append("probable_only")

        record["reasons"] = withheld + caveats
        if withheld:
            record["status"] = "withheld"
            continue
        if caveats:
            record["status"] = "qualified"
        for language in languages:
            text = TEMPLATES[language].format(
                reference=reference[language], direction=DIRECTIONS[language][mean_m > 0],
                magnitude=abs(mean_m), well=well, period=periods[language],
                label=labels.loc[group, f"label_{language}"],
            )
            shares = {"validated": _percent(validated, language), "imputed": _percent(imputed, language)}
            caveat_texts = [
                CAVEATS[reason][language].format(**shares) for reason in caveats
            ]
            record[f"text_{language}"] = " ".join([text, *caveat_texts])
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", help="Saved run name or directory.")
    parser.add_argument("--target", required=True, help="Inclusive window 'YYYY-MM-DD:YYYY-MM-DD'.")
    parser.add_argument("--well", required=True, nargs="+", action="extend", help="Well code (code_bss).")
    parser.add_argument("--sibling", nargs="+", action="extend", default=[], help="Other reconstruction runs.")
    args = parser.parse_args(argv)

    result = decompose(args.run, target=args.target, wells=args.well)
    primary = result["metadata"]["pumping_reconstruction"]
    siblings = {}
    for run in args.sibling:
        sibling = decompose(run, target=args.target, wells=args.well)
        number = sibling["metadata"]["pumping_reconstruction"]
        if number == primary or number in siblings:
            parser.error(f"pumping reconstruction {number} appears in more than one run")
        siblings[number] = sibling

    if siblings:
        numbers = ", ".join(map(str, sorted([primary, *siblings])))
        print(f"Pumping reconstruction sign check ran for reconstructions {numbers}.")
    else:
        print("Pumping reconstruction sign check: not checked (no sibling runs supplied).")
    for well in dict.fromkeys(args.well):
        print(f"\n{well}")
        for record in statements(result, well, siblings=siblings):
            print(
                f"{record['report_group']} [{record['status']}] (mean {record['mean_m']:+.3f} m, "
                f"sd {record['sd_m']:.3f} m, sign agreement {record['sign_agreement']:.0%})"
            )
            if record["reasons"]:
                print("  Reasons: " + ", ".join(record["reasons"]))
            for language in ("en", "fr"):
                if record[f"text_{language}"] is not None:
                    print(f"  {record[f'text_{language}']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
