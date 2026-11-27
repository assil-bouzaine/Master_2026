# Gate R2 checklist (v5 plan; criteria from `gemini_neon_review.md` §6, "Gate R2 (Must Pass Before R3)")

Kept by Claude; each line names its evidence. Status: ✅ met · 🔄 in progress · ⬜ not started · ⛔ waiting for Assil.
Last update: 2026-11-27 (end of session).

| # | Criterion (review's wording, shortened) | Evidence | Status |
|---|---|---|---|
| 1 | ROBOT HermiT consistency: 0 errors | `python -m tests.test_ontology` gates 5 and 7 (ELK and HermiT consistent, ROBOT report 0 ERROR), ontology 0.12.0, meta 0.5.0, 2026-11-27 | ✅ |
| 2 | OOPS!: 0 critical pitfalls | `python -m src.kg.oops_scan` → `docs/oops_report.md`; last scan 2026-11-16 (lulcw 0.7.1: no critical pitfall); rescan of 0.12.0 refused by the service on 2026-11-27 (HTTP 503, twice) | 🔄 retry |
| 3 | Entailment ledger: 100 % pass | `tests.test_ontology` gate 8: 73 asserted correspondences = the alignment modules, 19 rejected ones asserted nowhere, 14 required subsumptions hold, none of 31 forbidden ones (2026-11-27) | ✅ |
| 4 | SHACL: 0 violations on the Roussillon v5 graph | release 2026-11-27T15:51:51Z (`src.kg.apply_rules`: `shacl_conforms_no_violation: true`; report bound to the release by SHA-256); suites test_kg, test_kg_rules, test_release pass | ✅ |
| 5 | SHACL: 0 violations on the Manouba graph | the Manouba graph does not exist yet: it needs the aquifer's extent (Ferchichi et al. 2017 or Saidi et al. 2017, to download); proposal in `docs/notes/step16_v5.md` (R2.4, Manouba) | ⛔ |
| 6 | All 16 CQ test suites pass (incl. CQ10, CQ15, CQ16) | 2026-11-27: CQ data checks pass on the rebuilt release (inside the timing run, 5,859 calls), test_kg_rules passes (CQ10, CQ16 fixtures and negative controls); CQ10 and CQ16 have no model output yet; CQ9 and CQ13 to build (T91) | 🔄 14 of 16 |
| 7 | Oxigraph queries < 1 s | `python -m src.kg.cq_timing --store memory` → `docs/cq_timing_v5.md` (2026-11-27, measured while three test suites ran: pessimistic): 29 of the 31 query files the data checks call stay under 1 s; `cq04_status` (max 3.7 s, median 0.05 s) and `cq07_status` (max 1.1 s) do not; 9 files are not called by the data checks yet (CQ10, CQ16: no data; cq14_*: tested in test_cq14; cq01_series, cq01_bodies, cq04_outcrop). The disk store is 2.5–6× slower on the heavy queries (step16 note): the store stays in memory for queries | 🔄 optimise 2 queries, time 9 |
| 8 | Export equivalence test passes | `tests.test_export`, `test_inventory`, `test_controls` pass on the exports of 2026-11-27 (three policies) | ✅ |
| 9 | 0 of 33 core wells weather-blind in arm D | T65: 32 of 33 core wells have a recharge path; CARRIE (unit outside BD LISA) is the named exception (`docs/analysis_plan_v3.md` §2) | ✅ with the named exception |
| 10 | SO1 alignment P/R/F1 tables | RPG → HCAT3: `docs/alignment_hcat_v5.md` (eval strict F1: fuzzy 0.110, retrieval 0.151, Qwen3-8B 0.390 [0.304, 0.475]); RPG → AGROVOC: matchers ready to run blind (T97), scoring waits for Assil's gold labels | ✅ HCAT · ⛔ AGROVOC |
| 11 | Two-track extraction P/R/F1 tables | Track 2: eval F1 0.113 (P 0.069, R 0.318; sample check implied precision ≈ 0.17), `docs/notes/step16_v5.md`; Track 1: pilot done, review sheet `data/interim/track1_review_pilot.xlsx` waiting for Assil, then the main run (28 papers) | ✅ Track 2 · ⛔ Track 1 |

**Not gate criteria but measured for R2.4:** France → Tunisia reuse (`docs/ontology_reuse_tn.md`: 97.1 % of terms; 66/83
shapes, 7/17 rule shapes, 14/40 CQ queries reusable unchanged at 0.12.0; regenerate after each ontology change);
pyLODE documentation (`docs/ontology/`, regenerate after each ontology change).

**Waiting for Assil:** items 5 (a paper to download), 10 (AGROVOC labels), 11 (Track 1 pilot review). None of them
changes the Roussillon graph or model that R3 uses.
