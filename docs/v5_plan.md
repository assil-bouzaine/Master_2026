# v5 plan: carrying out the Gemini Neon review (started 2026-11-25)

**Source:** `gemini_neon_review.md` (repository root; Gemini 4 Neon, 2026-11-25). **Decision (Assil,
2026-11-25):** "we will do all the changes it gave us". **Where:** git branch `master_2026_fixes`
(branched from `main` at `2950148`). `main` and `results/v4/` keep the frozen v4 / Phase 4 v1 work
(tag `phase4-v1-frozen` at the end of R0); v5 results go to `results/v5/`.
**Session log and where to restart:** `SESSION_HANDOFF.md`. Accounts and compute: `.agents/RESOURCES.md`
(private, not in git).

Why a branch and not a copied folder: a copy of the repository would break every path (`src/config.py`
finds `data/` from the repository root, and `data/` is gitignored, several GB), double the disk, and make
the fixes impossible to review as one diff. A branch keeps the same data and tools, and `git diff
main...master_2026_fixes` shows every change.

---

## 1. Checks of the review's claims (Claude, 2026-11-25, before any work)

The review is adopted in full, but each claim that drives a change was checked against the data or code
first. Where a claim fails, the change stays, with expectations fixed accordingly.

| # | Claim of the review | Check | Verdict | What changes |
|---|---|---|---|---|
| C1 | Real daily canal flows (`is_canal=True`) are already downloaded and never used (§2.1.2, §4.1.3) | `data/raw/hubeau_hydro/`: 15 canal stations in dept 66; 14 have no data (empty or closed); one (canal adducteur, Villeneuve-de-la-Raho) has 58 days, Jan–Feb 2005. Same as CLAUDE.md Step 8 ("no usable canal flow series"). Re-checked on the API the same day: no monthly (QmM) canal flow after 2004 either (`data/README.md`). | ❌ wrong | R1.2 = the basin split of the BNPE canal intakes (T60) plus one re-check of Hub'Eau's monthly series for those stations. The weekly canal series stay annual totals spread by the deficit: the split changes **between-year** variation per basin, not the within-year link with the weather (r ≈ 0.96 by construction). |
| C2 | In leave-wells-out, held-out wells keep intercept d = 0 while the inputs are not centred, so their predictions carry an offset (§2.3 bug 1) | `src/models/response.py:361`: output = d_i + Σ contributions; d_i is per well and never trained for a held-out well; the stresses are raw (not centred). T61 (`docs/lwo_centring_v4.md`): centring the frozen v4 LWO predictions improves median drought RMSE in 37 of 56 runs but median drought NSE in only 14; for `p4_B2_D_r1_lwo` validation NSE −0.32 → +0.04 and drought RMSE −16 % (review: 22 %), but drought NSE −1.88 → −2.49; median offset ≈ 0.3 m. | ✅ real bug, ⚠️ minor part of the LWO failure | Centre each contribution on its training-period mean (forcings only, no head: no leakage) in Hybrid-GNN v2; report a post-hoc centred rescoring of the v4 leave-wells-out runs as a diagnostic, beside the frozen numbers. |
| C3 | Training from July 2012 (f50) "proves" that the invented 2005–2011 pumping hurts: D +0.014 → +0.226 (§2.1.1) | Drought median NSE, 33 core wells: D R1 0.014 / f50 0.226 / **f25 −0.069** (f25 is also entirely after 2012). Every model moves by about ±0.2 between regimes: LSTM 0.124 / −0.039 / 0.131; ST-GNN 0.055 / 0.131 / 0.205; C −0.188 / −0.085 / 0.040. | ⚠️ weak evidence | Keep the fix (calibrating pumping gains on invented years is wrong in principle): mask the pumping gradient on 2005–2011. Expect no particular gain; the ladder (R4.2 step 5) measures it. Never cite f50 alone as the proof. |
| C4 | 6 of 33 core wells have no recharge edge in arm D (§2.2.3) | Matches CQ4 (2026-10-27): 5 Pliocene wells without Pliocene outcrop within 5 km, plus CARRIE (unit outside BD LISA). | ✅ | Two-channel recharge (overlying leakage + regional outcrop), R2.2. Target: 0 of 33 core wells without a recharge path. |
| C5 | 49 terms of `lulcw.ttl` are tied to French agencies (§2.2.1) | T59 (`docs/ontology_country_terms.md`): 83 of 413 terms mention a French source; 16 in their name (e.g. `bdlisaCode`, `bnpeCode`, `bssCode`, `rpgEdition`), 67 only in their definition. | ⚠️ count differs (16 / 83, not 49) | The France profile (R2.2) moves the 16 name matches; the 67 keep their place, with definitions made country-neutral where the French source is only an example. |
| C6 | 23 terms are unused (§2.2.2) | `docs/ontology_term_usage.md` says 23. Several are CQ answer-status individuals or placeholders for modules whose data come later (e.g. `ModelResult` for CQ10). | ✅ count; ⚠️ "prune all" | Review each: prune, or keep with a reason (R2.2). |

## 2. A rule for honest reporting: v5 was designed after seeing v4's test scores

The v5 changes were chosen after reading v4's **drought-period (test)** scores (karst, the weather-blind
wells, f50, the canal sign). Re-scoring v5 on the same weeks and calling it a confirmation would overstate
it (a garden of forking paths). So:
1. v4 / Phase 4 v1 stays the pre-registered result, reported as it is (`analysis-plan-v2`).
2. `analysis-plan-v3` (R3.1) says in its first paragraph that v5's design used v4's test scores.
3. v5's **confirmatory** evidence comes from: the twin v2 (known truth), leave-wells-out, model selection
   on the validation period only, and the **post-freeze weeks** (R7.1: observations recorded after
   dataset v5 is frozen). The v4 → v5 drought comparison is reported as descriptive.

---

## 3. Phases, tasks and status

Owners: **C** = Claude (lead), **N** = neon (Gemini 4 Neon high), **S** = sol (GPT Sol 6.1 high),
**A** = Assil. Status: ✅ done · 🔄 in progress · ⬜ not started · ⛔ blocked (by what).

### R0 — close the v4 milestone (laptop)
| Step | Task | Owner | Status |
|---|---|---|---|
| 0.1 | `arms_report` → `docs/results_arms_v4.md` | C | ✅ 2026-11-25: every family complete, 0 pending |
| 0.2 | T58 Phase 4 figures; RQ1/RQ2 reading in `docs/notes/step14_phase4.md` | S (T58), C (reading) | 🔄 reading ✅ 2026-11-25 (facts: no effect of interest; structure: undecided; hard signs: no accuracy cost; D beats random graphs, ties distance rewires); T58 figures after T64 |
| 0.3 | commit, tag `phase4-v1-frozen` (push: ask A) | C | ✅ local tag at 80eabfe (2026-11-25); not pushed |

### R1 — dataset v5 (laptop + Earth Engine)
| Step | Task | Owner | Status |
|---|---|---|---|
| 1.1a | SAFRAN 1990–1999 (`src.ingest.safran --start 1990`; size checked first, >2 GB asks A) | C | ✅ 2026-11-25 (≈ 1.4 GB transferred); Météo-France republished 2023+: differences 0.01–0.17 % of totals (`data/README.md`) |
| 1.1b | Hub'Eau piezometer refresh (2024–25 validations); BNPE 2025 check | C | ✅ 2026-11-25: dated snapshots (piezometers: 6,574 records since 2024 now "Correcte"; rivers to Nov 2026, from 2005 only); BNPE 2025 not published (0 records) |
| 1.1c | (optional) nitrate (`qualite_nappes`, parameter 1340); Aude (dept 11) feasibility | C | ⬜ |
| 1.2 | canal intakes by basin (T60); Hub'Eau monthly re-check of the canal stations | N, C | ✅ 2026-11-25: `src/dataset/canal_basins.py`, `docs/canal_basins.md` (Têt 72 % of the volume, −33 % 2022→2023; annual totals unrelated to the deficit); no canal flow series exists. Open: the 2 large unknown intakes (override needs a documented reason) |
| 1.3 | BRGM InfoTerre WFS (BSS) borehole depths → pump attribution re-run | C (API), N | 🔄 2026-11-25: `src/ingest/brgm_bss.py` (water points with depth and BD LISA entities, boreholes with depth reached); T62 measures the precision before any use |
| 1.4 | Earth Engine: Sentinel-2 NDVI/NDMI per RPG parcel (Roussillon); S2 + WorldCover + ERA5-Land (Manouba) | A (register), C | ⬜ unblocked 2026-11-25: Earth Engine works from the laptop (Assil's project; the three collections checked for both sites) |
| 1.5 | build `dataset_v5` (`forcing_start` 1990, refreshed heads, basin canals, BSS attribution, S2 summaries); log pulls in `data/README.md`; Gate R1 | C | 🔄 2026-11-25: built without BSS and S2 (same wells, core and folds as v4; core test weeks not validated 41.5 % → 23.7 %); v5 graph building; Gate R1 checks (cold rebuild hashes, dataset tests) pending |

### R2 — ontology `lulcw` 1.0, alignments, text extraction (laptop + Colab GPU)
| Step | Task | Owner | Status |
|---|---|---|---|
| 2.1 | Paper extraction: OpenAlex → 20–30 open-access Mediterranean papers; local open LLM on Colab (Track 1: causal axioms, reviewed by A; Track 2: P/R/F1 against the 32 statements of `configs/exchange_evidence.csv`). Model fixed before scoring (the review proposes Qwen2.5-7B-Instruct; compare a newer Apache-2.0 model on the dev statements first) | C, N | ⬜ |
| 2.2 | Split `lulcw.ttl`: 7 core modules (core, hydro, lulc, eo, med-causal, causal, xai) + profiles `lulcw-fr`, `lulcw-tn`; prune/justify unused terms (C6); rules for `OverlyingLeakageInfluence`, `RegionalOutcropInfluence`, basin-split `CanalReturnInfluence` (hard ≥ 0 where measured), `ProbablyIrrigatedParcel` (CQ15); CQ10, CQ16 terms | C | ⬜ (T59 feeds it) |
| 2.3 | Alignments: SAREF4WATR, SAREF4AGRI, CORINE SKOS, ENVO, GEMET, deeper SWEET (each term checked at its source, ledger + HermiT); EuroCrops HCAT mapping; AGROVOC gold set (A) + OntoAligner (Colab) → P/R/F1 | C, N, A | ⬜ |
| 2.4 | Roussillon v5 KG + Manouba KG in a persisted `pyoxigraph.Store`; France → Tunisia reuse %; pyLODE docs; export v5 (C, D, E, F + equivalence test); Gate R2 (0/33 core wells weather-blind) | C, N | ⬜ |

### R3 — `analysis-plan-v3`, Hybrid-GNN v2, twin v2 (Colab)
| Step | Task | Owner | Status |
|---|---|---|---|
| 3.1 | `analysis-plan-v3` (ladder, architecture, pumping-reliability rule, black box, §2 above); tag | C | ⬜ |
| 3.2 | `src/models/hybrid_gnn.py`: centred contributions, gains in sd units, monotone soil bucket (FlexModel), fast + slow kernels (amax 104 wk), two-channel recharge, basin canals, PyG HeteroConv/GATv2 parameter encoder (stage A δ = 0, stage B regularised δ), 2005–2011 pumping-gradient mask, split regularisation, cosine LR, bounded monotone residual row; black box `Hetero-STGNN` on the same HeteroData | C (design, core), N (pieces) | 🔄 design in `docs/analysis_plan_v3.md` §3 (draft); pieces: ✅ `bucket.py` (T63), 🔄 `kernels.py` (T64, sol), 🔄 `hetero_graph.py` (T66, neon) |
| 3.3 | Twin v2 (nonlinear recharge, leakage, basin canals, imputed pumping); Gate R3 (finite-difference 0 % sign violations, replay < 1e-5 m, centred LWO, twin) | C, N | ⬜ |

### R4 — v5 real-data runs (Colab v5e1 + Kaggle CPU in parallel; Colab L4 / Camber L4 for GPU)
| Step | Task | Owner | Status |
|---|---|---|---|
| 4.1 | Baselines on v5 (Pastas reference, LSTM, ST-GNN, Hetero-STGNN C/D, Chronos-2), same machine per contrast | C | ⬜ |
| 4.2 | Ablation ladder 1–7, 10 seeds each | C | ⬜ |
| 4.3 | Full matrix: arms A–F × R1/R2/R3/refit; RQ2 none/soft/hard; reconstructions 1–3; pump policies; CQ15 ablation | C | ⬜ |
| 4.4 | `arms_report` on v5 + v4 vs v5 table; Gate R4 | C, S (figures) | ⬜ |

### R5 — explanations and XAI benchmark (SO4, CQ10)
| Step | Task | Owner | Status |
|---|---|---|---|
| 5.1 | `src/explain/result_graph.py`: runs, heads, contributions, statements as `lulcw-xai` RDF; CQ10 shapes | C, N | ⬜ |
| 5.2 | Case studies (NYLS-1 2024 vs average and vs 2023; 2023 drop; C2-1 canal) + what-if explanations | C | ⬜ |
| 5.3 | Integrated Gradients + GNNExplainer on the black box; fidelity+/−, deletion curves; Adebayo randomisation check | N, C | ⬜ |

### R6 — dashboard (SO5, CQ16)
| Step | Task | Owner | Status |
|---|---|---|---|
| 6.1 | Streamlit, 4 tabs: map (Roussillon + Manouba), explanation explorer, CQ query console, what-if simulator | N, C | ⬜ |
| 6.2 | Offline HTML backup; explainer update (v4 → v5) | S, C | ⬜ |

### R7 — final technical lock
| Step | Task | Owner | Status |
|---|---|---|---|
| 7.1 | Score frozen v4 and v5 on the weeks observed after the v5 freeze | C | ⬜ |
| 7.2 | Full test gate from cold start; tag `thesis-technical-freeze` | C | ⬜ |

## 4. Compute plan

- CPU-bound fits (the hybrid's starts): Colab TPU v5e1 (24 vCPU, ≈ 3.1–3.3 units/h) as two shards **and**
  Kaggle CPU (free, 12 h, background) at the same time, sharded by contrast so both sides of a contrast
  run on the same machine type.
- GPU (Hetero-STGNN, Chronos-2, local LLMs): Colab L4 (≈ 1.9–2.3 units/h); Camber L4 while its monthly
  allowance lasts (after `camber login`).
- The review estimates 55–75 Colab units for the whole plan; balance 165.30 on 2026-11-25.
