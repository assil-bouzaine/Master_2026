# Citation audit

Generated file. Do not edit by hand.

Command: `PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m src.analysis.citation_audit`

Source date: 2026-11-18 (latest Git commit date, kept stable for reproducible reruns).

## Summary

- Files: 247
- Identifiers: 104
- Checked: 103
- Not checked: 1
- Malformed or suspicious: 1
- Possibly inconsistent: 2

The checked set contains every identifier in `reading_list.md` and
`comparison_table.md`. Membership is not an online verification. DOI case and
arXiv versions are normalized. Bare DOI prefixes without a suffix stay outside
the checked set. A citing place is one unique `path:line`.

## Table 1, not in the checked set

| Identifier | Number of citing places | Every place | First citing line (≤ 100 characters) |
|---|---:|---|---|
| 10.1038/ | 2 | docs/literature/reading_list.md:227<br>ontology/lulcw-meta.ttl:6 | &#124; Lippolis, Lodi &amp; Nuzzolese, *The Water Health Open Knowledge Graph*, *Sci. Data* 12, 2025, **do... |

## Table 2, malformed or suspicious

These spelling checks can also flag unusual valid identifiers.

| Identifier | Reason | Every place |
|---|---|---|
| 10.1038/ | DOI suffix shorter than 3 characters | docs/literature/reading_list.md:227<br>ontology/lulcw-meta.ttl:6 |

## Table 3, possible inconsistencies (heuristic; false alarms expected)

For each citing line, use the first mention of the identifier. Select the nearest
year 1950–2029 before it within 80 characters. Only if none exists, select the nearest
year after it within 80 characters. Years inside the identifier are ignored. Flag
more than one distinct selected year across its citing lines. Adjacent references
and print, online or access dates can still cause false alarms.

| Identifier | Selected years | Places (selected year) |
|---|---|---|
| arXiv:2103.03098 | 2017, 2021 | docs/literature/reading_list.md:204 (2017)<br>fable_review.md:157 (2021)<br>fable_review.md:581 (2021) |
| arXiv:2205.11775 | 2017, 2023 | docs/analysis_plan.md:415 (2023)<br>docs/explainer/index.html:777 (2017)<br>docs/feedback.md:793 (2023)<br>docs/literature/comparison_table.md:78 (2023)<br>docs/literature/reading_list.md:130 (2023)<br>docs/literature/reading_list.md:170 (2023) |
