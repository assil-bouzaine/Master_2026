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

## 1b. Checks of the bug audit of 2026-11-26 (`docs/v5_bugs_to_fix.md`)

An audit of commit `720fb40` listed four bugs or gaps to fix before any Colab run of Hybrid-GNN v2 and five
cleanups. Assil: fix the valid ones, then continue the plan. Each claim was checked against the code and data
first (Claude, 2026-11-26); step note `docs/notes/step16_v5.md`.

| # | Claim | Check | Verdict | Fix |
|---|---|---|---|---|
| 1 | Imputed 2005–2011 pumping still trains the pumping gain through the training-mean centre on post-2012 weeks | A probe loss linear in the post-2012 predictions isolates gradient paths: multiplying every imputed pumping week by 100 moved the pumping-gain gradient by 405 (toy model). The audit's fix (detach the pre-2012 slice of the centre) left 273: the eight-year kernel's memory carries imputed pumping into the 2012+ contributions, a second path the audit missed | ✅ real, larger than reported | Each pumping stress split into declared and imputed parts; the imputed part's response uses a detached gain and kernel at every week, and before 2012 the whole pumping anomaly is fixed in the loss. Values unchanged; probe change exactly 0 (`tests.test_hybrid_gnn` 3c) |
| 1b | (found while checking 1) v5 pumping stress is **0 for 1990–2002** | The pumping table starts in 2003, v5's weather in 1990, and `routed_v5_inputs` filled the gap with 0: summed pumping 0.0 until 2002, 881.5 thousand m³/week from 2003, a step the kernels carry into 2005–2011 (frozen v4 had the same gap for 2000–2002, its weather starting in 2000: recorded as a v4 limitation, v4 unchanged) | ✅ real | Weeks before the pumping record are NaN, filled with the well's training mean like the canal series and the kernel warm-up (test 7 checks it on the real v5 export) |
| 2 | The v5 export has no aquifer units, `monitors`, `overlies` or basin canal nodes promised by plan v3 §3.5 | `export_v5_main`: 5 node types, one plain canal node, no unit nodes | ✅ real gap | T71 (neon): 25 unit nodes typed by the written rule, `monitors` (well ← unit), `overlies` (direct contacts), basin canal nodes, pandas oracles |
| 3 | Controls E/F omit `recharge_leakage` and `recharge_unitwide` | v5 controls: 181 local recharge edges only; D has 181 + 765 + 105 | ✅ real | T71: the controls rewire every relation of D |
| 4 | Stage B trains from scratch, not as a refinement of stage A | `train_seed`: per-well δ trainable from epoch 0; the review (§5) designs B as a δ refinement after A, against the v4 failure where δ absorbed the well differences | ✅ real | Stage B = the stage-A epochs (δ = 0, out of the optimiser), then `--epochs-b` epochs of δ only; held-out wells equal stage A exactly (test 4c) |
| 5.1 | `n_slow ≥ 1` duplicated in `hybrid_gnn.py` | `kernels.raw_to_kernel_params` kept n ≥ 0.5 | ✅ | `kernels.N_SLOW_MIN = 1`, duplicate removed |
| 5.2 | Stale statuses in this plan | R0.2, R1.3, R1.5, R3.2 | ✅ | Updated below |
| 5.3 | Stale note in `docs/bss_evidence.md` | Line 5 claimed paging duplicates in a snapshot without any | ✅ | T72 (sol): the generator reports the counts |
| 5.4 | "Vertical leakage is not yet derived" in `lulcw:VerticalLeakage` and `cq08_status.rq` | Stale since T65 (leakage influences exist) | ✅ | **Deferred to R2.2**: editing `lulcw.ttl` changes the ontology hash and forces a graph-release rebuild, which the R2.2 module split does anyway |
| 5.5 | `wfdCode` (EU Water Framework Directive) not among the France-profile candidates | A classification question, not a bug | ✅ note | Decided in R2.2 (EU/France profile or core) |

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
| 0.2 | T58 Phase 4 figures; RQ1/RQ2 reading in `docs/notes/step14_phase4.md` | S (T58), C (reading) | ✅ reading 2026-11-25 (facts: no effect of interest; structure: undecided; hard signs: no accuracy cost; D beats random graphs, ties distance rewires); T58 figures committed 2026-11-25 (`reports/figures/phase4_*_v4.png`) |
| 0.3 | commit, tag `phase4-v1-frozen` (push: ask A) | C | ✅ tag `phase4-v1-frozen`, pushed 2026-11-25 |

### R1 — dataset v5 (laptop + Earth Engine)
| Step | Task | Owner | Status |
|---|---|---|---|
| 1.1a | SAFRAN 1990–1999 (`src.ingest.safran --start 1990`; size checked first, >2 GB asks A) | C | ✅ 2026-11-25 (≈ 1.4 GB transferred); Météo-France republished 2023+: differences 0.01–0.17 % of totals (`data/README.md`) |
| 1.1b | Hub'Eau piezometer refresh (2024–25 validations); BNPE 2025 check | C | ✅ 2026-11-25: dated snapshots (piezometers: 6,574 records since 2024 now "Correcte"; rivers to Nov 2026, from 2005 only); BNPE 2025 not published (0 records) |
| 1.1c | (optional) nitrate (`qualite_nappes`, parameter 1340); Aude (dept 11) feasibility | C | ⬜ |
| 1.2 | canal intakes by basin (T60); Hub'Eau monthly re-check of the canal stations | N, C | ✅ 2026-11-25: `src/dataset/canal_basins.py`, `docs/canal_basins.md` (Têt 72 % of the volume, −33 % 2022→2023; annual totals unrelated to the deficit); no canal flow series exists. Open: the 2 large unknown intakes (override needs a documented reason) |
| 1.3 | BRGM InfoTerre WFS (BSS) borehole depths → pump attribution re-run | C (API), N | ✅ 2026-11-25: `src/ingest/brgm_bss.py` (tiled pull); T62 (`docs/bss_evidence.md`): BSS adds nothing usable for irrigation attribution (only 240 BNPE points carry a BSS code), so no re-run; whether it enters v5 at all is a plan v3 §8 point |
| 1.4 | Earth Engine: Sentinel-2 NDVI/NDMI per RPG parcel (Roussillon); S2 + WorldCover + ERA5-Land (Manouba) | A (register), C | ✅ Roussillon 2026-11-26: CQ15 enters v5 (Assil, plan v3 §8 item 4); `src/ingest/gee_s2.py` (142,282 parcel-years 2017–2025); CQ15 rule `src/dataset/irrigation_s2.py` (T76): NDVI ≥ 0.485 frozen on 2017–2019, dry SWI ≤ 0.5, census check → verdict **heuristic** (orchards in range, vines over, market gardening under; `docs/irrigation_s2.md`), per-well 2017–2019 share for the with/without row. Manouba (S2 + WorldCover + ERA5-Land) moves to R2.4 with the Manouba KG |
| 1.5 | build `dataset_v5` (`forcing_start` 1990, refreshed heads, basin canals, BSS attribution, S2 summaries); log pulls in `data/README.md`; Gate R1 | C | 🔄 built 2026-11-25 without BSS and S2 (same wells, core and folds as v4; core test weeks not validated 41.5 % → 23.7 %); reproducible (T68: 13/13 files identical after a cold rebuild); ends at the last weather week 2026-11-22 (T69); v5 graph released; dataset tests pass on v5 (T72, 2026-11-26: pumping conservation, regime boundaries, folds, audit, canal basins, placeholders). 🔄 Gate R1: the CQ15 outputs join the v5 build (T79), then the full cold-rebuild audit (lead, after T78's graph rebuild) |

### R2 — ontology `lulcw` 1.0, alignments, text extraction (laptop + Colab GPU)
| Step | Task | Owner | Status |
|---|---|---|---|
| 2.1 | Paper extraction: OpenAlex → 20–30 open-access Mediterranean papers; local open LLM on Colab (Track 1: causal axioms, reviewed by A; Track 2: P/R/F1 against the 32 statements of `configs/exchange_evidence.csv`). Model fixed before scoring (the review proposes Qwen2.5-7B-Instruct; compare a newer Apache-2.0 model on the dev statements first) | C, N | 🔄 2026-11-26: Track 2 scorer and answer schema fixed before any model runs (`src/kg/extract_eval.py`, `configs/extraction_schema.json`, T80); ⬜ choose the model, OpenAlex pull, the Colab run, Track 1 |
| 2.2 | Split `lulcw.ttl`: 7 core modules (core, hydro, lulc, eo, med-causal, causal, xai) + profiles `lulcw-fr`, `lulcw-tn`; prune/justify unused terms (C6); rules for `OverlyingLeakageInfluence`, `RegionalOutcropInfluence`, basin-split `CanalReturnInfluence` (hard ≥ 0 where measured), `ProbablyIrrigatedParcel` (CQ15); CQ10, CQ16 terms | C | 🔄 2026-11-25: overlying-leakage rule + `recharge_leakage` export done (T65; ontology 0.9.0; 32/33 core wells have a recharge path, CARRIE the named exception); item 5.4 done in T74 (0.9.1); unused-term review T75 (keep 8 / move 14 / prune 1; `wfdCode` → EU profile); ✅ T78 (2026-11-26): seven modules + EU/FR/TN profiles generated from `lulcw.ttl` (`src/kg/ontology_modules.py`, `ontology/modules/`, `ontology/profiles/`, `ontology/lulcw-modular.ttl`), `lulcw:registerCode`, ontology 0.10.0, core share 400/415 = 96.4 %, release 2026-11-26T12:48:36Z; ⬜ CQ15 terms (eo) and rule as SHACL-AF, CQ16 terms (xai with CQ10 in R5.1); follow-ups from T78's report: integer register codes under `registerCode`, `groundwaterBodyCode` → EU profile |
| 2.3 | Alignments: SAREF4WATR, SAREF4AGRI, CORINE SKOS, ENVO, GEMET, deeper SWEET (each term checked at its source, ledger + HermiT); EuroCrops HCAT mapping; AGROVOC gold set (A) + OntoAligner (Colab) → P/R/F1 | C, N, A | ⬜ |
| 2.4 | Roussillon v5 KG + Manouba KG in a persisted `pyoxigraph.Store`; France → Tunisia reuse %; pyLODE docs; export v5 (C, D, E, F + equivalence test); Gate R2 (0/33 core wells weather-blind) | C, N | ⬜ |

### R3 — `analysis-plan-v3`, Hybrid-GNN v2, twin v2 (Colab)
| Step | Task | Owner | Status |
|---|---|---|---|
| 3.1 | `analysis-plan-v3` (ladder, architecture, pumping-reliability rule, black box, §2 above); tag | C | 🔄 2026-11-26: every §8 point decided by Assil (canal sign, pumping by declared facility-year, twin criterion, CQ15, tuning budget per arm) and the node-feature list fixed; the tag waits until just before the tuning (after Gates R1–R2) |
| 3.2 | `src/models/hybrid_gnn.py`: centred contributions, gains in sd units, monotone soil bucket (FlexModel), fast + slow kernels (amax 104 wk), two-channel recharge, basin canals, PyG HeteroConv/GATv2 parameter encoder (stage A δ = 0, stage B regularised δ), 2005–2011 pumping-gradient mask, split regularisation, cosine LR, bounded monotone residual row; black box `Hetero-STGNN` on the same HeteroData | C (design, core), N (pieces) | 🔄 design in `docs/analysis_plan_v3.md` §3 (draft); ✅ `bucket.py` (T63), `kernels.py` (T64), `hetero_graph.py` (T66), first assembly (T70), audit fixes 2026-11-26 (§1b: declared-only pumping gradients, pre-record pumping, stage B as a refinement, `n_slow ≥ 1` in `kernels.py`); ✅ export with units, `monitors`, `overlies`, basin canals and complete controls (T71); ✅ Colab smoke run 2026-11-26 (TPU v5e1: ≈ 0.4 s per epoch on one thread, a full fit ≈ 5 min, ≈ 280 fits per runtime-hour; replay across machines < 1e-5 m); ✅ canal constraint decision for v5 (T74, ontology 0.9.1); ✅ arms A/B (facts, no graph); ✅ equal-budget tuner `src/models/tune_hgnn.py` + `hgnn_tune` step (T77); ⬜ black box (Hetero-STGNN) |
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
