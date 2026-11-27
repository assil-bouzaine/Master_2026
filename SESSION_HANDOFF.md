# Session handoff (read this first in every new session)

What each session did, where the work stands, and where to start next. **Newest session first.** Claude
keeps it current during the session (after every finished task, not only at the end), because a session
can end abruptly or hit a usage limit. Rule (Assil, 2026-11-25): when Claude's usage reaches ≈ 95 % of its
5-hour or weekly window (`limit-alerts status`, row "Claude"), it stops the task and brings this file up to
date.

- **Branch:** `master_2026_fixes` (all work since 2026-11-25). `main` = frozen v4 milestone.
- **Plan:** `docs/v5_plan.md` (the review's steps R0–R7 with owner and status; the claim checks).
- **Review being carried out:** `gemini_neon_review.md` (root).
- **Accounts, compute, worker rules:** `.agents/RESOURCES.md` (private, gitignored: it names accounts).
- **Workers:** at the start of every session open `neon` (Gemini 4 Neon high: moderate tasks) and `sol`
  (GPT Sol 6.1 high: easiest tasks) in herdr; stop briefing a worker at 70 % of its 5-hour window.
  Briefs `.agents/briefs/Tnn_*.md`, reports `results/_agents/reports/Tnn.md`.

## Rules for every session (Assil, 2026-11-25)

1. **Start:** read this file, then `docs/v5_plan.md` (phases R0–R7, owner and status per step, the claim checks
   and the honest-reporting rule), then `docs/analysis_plan_v3.md`; open the two herdr workers (`neon` = Gemini 4
   Neon high, moderate tasks; `sol` = GPT Sol 6.1 high, easiest tasks) after checking their 5-hour windows.
2. **Follow the plan in order.** Each phase ends with a gate (`docs/v5_plan.md`, from the review's §6): never run a
   later phase's real-data experiments before the earlier gate passes; code for later phases may be written
   earlier (tests only, no fitting). Tag `analysis-plan-v3` before any v5 real-data result is scored. Record every
   step's status in `docs/v5_plan.md` and every decision Assil takes (AskUserQuestion, recommendation first).
3. **Git:** commit and push only as `assil-bouzaine`; **no `Co-Authored-By` line, no contributor attribution for
   Claude**; push only when Assil says so.
4. **Limits:** workers stop getting tasks at 70 % of their 5-hour window; Claude stops at ≈ 95 % of its own and
   updates this file. No model training on the laptop (Colab, Kaggle, Camber; `.agents/RESOURCES.md`).
5. Keep this file current after every finished task, not only at the end.

---

## ▶ START HERE (state during the session of 2026-11-27, ≈ 17:10 local time; updated as tasks finish)

**Running when this was written:** the **graph release rebuild** on the laptop (`bash scripts/rebuild_release.sh v5
results/logs/rebuild_2026-11-27`: facts, rules + validation, persisted store, inventory/export/controls of the three
policies, CQ timing; log `results/logs/rebuild_2026-11-27/rebuild.log`). **Never edit `ontology/`, rules or shapes
while it runs.** If the session ended mid-run: rerun the same command. Worker **neon → T95** (Hetero-STGNN black box,
model code only; brief `.agents/briefs/T95_hetero_stgnn.md`). Worker **sol**: idle (T96 done). Colab: no session
(`hcat` pulled and stopped; balance 160.58 units).

**Done this session (all committed locally, nothing pushed):** CQ15 validation fix; CQ15 rule 615 s → 89 s (same
triples); persisted store (`src/kg/store.py`, `kg_store()` uses it) and `src/kg/cq_timing.py`; T92 matchers + three
Colab fixes (bitsandbytes clash, BGE-M3 commit check, importer); **SO1 HCAT table** (`docs/alignment_hcat_v5.md`:
eval strict F1 fuzzy 0.110, retrieval 0.151, Qwen3-8B 0.390 [0.304, 0.475]); T93 reuse report (97.1 % of terms, but
41 % of rule shapes and 35 % of CQ queries reusable unchanged: French register codes); CLC correspondences
(`configs/lu_clc.csv`, T94 in the graph); **T88** (CQ10 + CQ16, ontology 0.12.0); **GEMET** alignment (22 asserted,
5 rejected) and **SAREF4AGRI** (`RegisteredParcel` closeMatch `s4agri:Parcel`); meta 0.5.0; step16 note updated.

**Next, in order:**
1. When the rebuild finishes: check `rebuild.log`; compare the export edges with the fingerprints taken before
   (`results/logs/rebuild_2026-11-27/export_*_before.sha256`; the CLC facts and the speed-ups should not move an
   edge); read `docs/cq_timing_v5.md` (Gate R2: < 1 s per query). Then the graph suites: test_modules, test_kg
   (check 11 data part now runs), test_kg_rules, test_cq, test_release, test_inventory, test_export, test_controls,
   test_store; `src.kg.ontology_docs` (regenerate, `--check`); `src.kg.reuse_report` (regenerate). Commit.
2. **neon → T91** (CQ9 + CQ13; brief ready) once T95 is reviewed, then another rebuild (`scripts/rebuild_release.sh`).
3. sol: free; candidate tasks: none urgent (the country-neutral refactor of rules/queries is a decision for Assil).
4. Track 1: Assil reviews the pilot sheet; then the main run (28 papers, ≈ 4 h L4).
5. R2.4: Manouba KG (needs the aquifer extent: Ferchichi et al. 2017, or Saidi et al. 2017 on HAL, DOI to verify);
   OOPS! scan on the 0.12 ontology; Gate R2. R3: twin v2 design (lead), black box (T95).

**Where we are in `docs/v5_plan.md`:** R0 ✅ · R1 ✅ (Gate R1 passed 2026-11-26) · R2 in progress:
- R2.1: Track 2 ✅ (eval F1 0.113; sample check: implied precision ≈ 0.17). Track 1: pilot ✅ (88 statements from the
  two pilot papers, `results/v5/extraction/track1_qwen3_pilot/`), review sheet for Assil ✅, main run ⬜.
- R2.2: CQ15 ✅ (validation fix and rule speed-up ✅ 2026-11-27); CQ10, CQ16 ✅ (T88, ontology 0.12.0); CQ9, CQ13 (T91) ⬜.
- R2.3: SAREF4WATR, ENVO, deeper SWEET ✅; GEMET ✅, SAREF4AGRI ✅, CLC (crop classes, data level) ✅; HCAT matchers ✅
  (SO1 table `docs/alignment_hcat_v5.md`); AGROVOC labels (Assil) ⬜ then the same matchers on AGROVOC.
- R2.4: pyLODE documentation ✅ (regenerate after the rebuild); persisted store ✅; CQ timing 🔄 (in the rebuild);
  reuse report ✅ (`docs/ontology_reuse_tn.md`, regenerate); Manouba KG ⬜ (extent); OOPS! ⬜.

**VPN (installed 2026-11-26 ≈ 19:45 at Assil's request):** `openvpn` 2.7.9 + `networkmanager-openvpn` 1.12.5
(pacman), NetworkManager profile **`Univ-Manouba`** imported from the university's `.ovpn` (certificate-based, server
`vpn-21584.cck.rnu.tn:1194`; `data-ciphers-fallback=AES-256-CBC` added for the old server). Connect:
`nmcli connection up Univ-Manouba`; disconnect: `nmcli connection down Univ-Manouba`. Use it only for Assil's
browser downloads (publishers allow IP access for Springer and Wiley; Elsevier/ScienceDirect is **not** subscribed
since 2017, so Chu 2026 and Jeong 2026 stay out of reach). The 23 open-access papers are blocked only for scripts,
not by the network. Never connect it while a Colab job is being pulled. **Test of 2026-11-26 19:47:** the profile loads, but the server (196.203.128.101, UDP 1194) answered "no route to host" from the home network: server down or the port blocked on that network; retry later or from another network, else ask the university's IT. The sudo password Assil gave for this
session is not stored anywhere (`sudo -k` run at the end).

**Waiting for Assil:**
1. **The Track 1 pilot review:** open `data/interim/track1_review_pilot.xlsx` (88 statements from the two pilot
   papers; sheet "Guide" says what to judge), choose `accept` or `reject` (+ a reason) per row, save, then tell Claude
   (it runs `python -m src.kg.track1_review import --worksheet data/interim/track1_review_pilot.xlsx --out
   data/interim/track1_review_pilot.csv` and the score). Worth checking first: statements about exchanges between two
   aquifers (Track 2's main confusion).
2. The AGROVOC labels (`data/interim/agrovoc_gold_worksheet.xlsx`, dev codes first; `import` after each sitting).
3. Papers: **Ferchichi et al. 2017** (Manouba aquifer, needed for R2.4's extent; doi:10.1007/s12517-017-3314-4, open
   access but blocks scripts); also **Saidi et al. 2017**, *Environmental Earth Sciences*, recharge areas of the same
   aquifer (HAL record hal-01591256; DOI given by a search as 10.1007/s12665-017-6840-1, unverified; HAL blocks
   scripts); Shapoori 2015 (VPN); `docs/papers_to_download.md`.
4. Later: the alignment ledger review; the defence date when known.

---

## Session log

### 2026-11-27 (Claude Opus 5.5, from ≈ 15:10 local time)
- CQ15 validation fix applied and checked end to end (pySHACL with the real shapes file: the 3 planted gaps found at
  300 and 3,000 parcel-seasons in 2.2 s and 9.8 s); committed `c7cf39a` before any worker touched the shapes.
- Workers opened (space `sp9be5d05c0e222699a49c7ecee89e333e`): neon → T88, sol → T92 (GPT-6.1-Sol high checked).
  Sol asked whether it may create `configs/align_prompt_hcat.md` (named in the brief's design, missing from its file
  list): yes.
- Rule profile (`results/logs/diag_profile_rules_2026-11-27.log`): rules 645 s, of which the CQ15 rule 429 s. Cause
  (cProfile + piece-by-piece timing on samples, `scripts/diag_cq15_rule_{cprofile,parts}.py`): the soil-wetness
  OPTIONAL compared fresh variables in a FILTER, so rdflib ran the nested OPTIONAL and the FILTER for each of the 40
  candidate observations per parcel-season (27 ms each). A FILTER-based rewrite was slower (74 s vs 8.5 s on 300);
  the fix folds the cell lookup into the same OPTIONAL and joins on ?cell/?year in the patterns (1.5 s on 300, same
  triples, also for a parcel without a cell).
- T92 reviewed (tests rerun, hashes match) and committed; `align:<matcher>` steps; Colab `hcat` started.
- New lead code: persisted store (`src/kg/store.py`, `tests/test_store.py`: 7 checks pass), `kg_store()` uses it;
  `src/kg/cq_timing.py`.
- sol → T93 (reuse report).
- T93 committed; CLC: guideline pages from the Internet Archive (`land.copernicus.eu` unreachable), `configs/lu_clc.csv`
  decided, T94 (sol) wired it into the graph, committed.
- Colab `hcat`: fuzzy done; retrieval refused by the BGE-M3 commit check (sentence-transformers 5 leaves
  `_commit_hash` empty) → load from a pinned `snapshot_download`; importer copies alignment runs; LLM done; pulled,
  stopped. SO1 table (T96, sol) committed.
- T88 (neon) reviewed and committed (+ the generator's stale descriptions fixed by the lead); neon → T95.
- GEMET and SAREF4AGRI alignments (lead), committed; all ontology gates pass.
- Rebuild started (`scripts/rebuild_release.sh`, committed).


### 2026-11-26 (night, Claude Opus 5.5, from ≈ 22:50 local time)
- T89 (sol) reviewed and committed (`9b6269b`); Track 1 passages rebuilt on the complete 30-paper set (453 passages;
  pilot = orders 1–2, 30 passages; main = 28 papers, 423 passages).
- T85 (neon, CQ15 in the graph, ontology 0.11.0) reviewed: results exact (13,260 LU-6 parcel-seasons = T76's
  statuses) but **graph validation 9 → 82 min**. Cause found (synthetic benchmark + per-shape profiler): rdflib orders a
  `FILTER NOT EXISTS` / `OPTIONAL` block's patterns without knowing the variables bound outside it, so the CQ15
  completeness check scans all 13,260 classifications for each of the 13,260 observations. A runtime-aware pattern
  order does not help (benchmark); the fix is to rewrite that one block (written, to apply first next session).
  T85 committed (`4535474`) after the lead's rerun of all nine graph suites (all pass).
- sol → **T90** (pyLODE HTML docs of the modules and profiles; pyLODE 3.6.1 installed by the lead as an isolated
  `uv tool`, because it would upgrade the pinned httpx2/httpcore2).
- Track 2 sample check done and committed (`e3f6a87`): implied precision ≈ 0.17 instead of 0.069; the main error is
  aquifer–aquifer leakage forced into `RiverExchange` (step16 note).
- CQ9 data: `src/ingest/vigieau_communes.py` → `data/interim/vigieau_communes_66.parquet` (226 communes × 6,054 days,
  SUP/SOU/AEP levels; committed `8f3daaa`). GEMET 4.2.3 and the CLC vocabulary saved from Internet Archive copies
  (`data/raw/vocab/`, logged) for the GEMET/CORINE alignments (lead, after T88/T91: they touch
  `ontology_modules.py`/catalog). OntoAligner 1.9.4 wheel unpacked for reading in `.agents/ref/` (its deps would
  downgrade huggingface-hub and add `datasets`: run it on Colab only).
- Briefs ready: **T88** (neon; updated: no release rebuild, T85 follow-ups, the SPARQL-in-shapes rule), **T91**
  (neon after T88: CQ9 + CQ13).
- Colab `t1pilot` (L4, ≈ 23:11–23:51 local, ≈ 1.5 units): Track 1 pilot done (30 pages, 88 statements, 0 invalid);
  pulled, session stopped; review sheet `data/interim/track1_review_pilot.xlsx` written for Assil.
- T90 + T90b (sol) committed (`4bf4df3`): pyLODE pages of the 7 modules and 3 profiles, 43 terms pyLODE omits listed
  from the source; `src.kg.ontology_docs --check` gate.
- Assil at ≈ 23:40: "once sol finishes update the handoff and stop": workers closed, nothing running, this file
  updated; nothing pushed.

### 2026-11-26 (evening, Claude Opus 5.5, from ≈ 17:50 local time)
- Assil: "before u start doing anything, give me what u need from me and guide me one by one until u don't need
  anything from me". Claude listed 9 items (now: Camber login, 4 quick decisions, the AGROVOC labelling rules;
  e-mails: the professor, SMNPR; homework: the gold set labels, 8 paywalled papers; later: Track 1 review, ledger
  review); retired from his list: the SHOULD/COULD CQ review (all 16 CQs are in the adopted v5 plan).
- Camber CLI login done by Assil (`camber me` works, user `assil0723`).
- Decided by Assil: **push only at the end of this session** (commit locally until then); **Manouba transfer from
  free data only** (no local data: Sentinel-2, WorldCover, ERA5-Land, published aquifer maps); **R1.1c skipped**
  (nitrate stays future work; maybe a dashboard layer in R6); **one gold-set annotator for now**; the **four AGROVOC
  labelling rules** (the plant; one concept covering a mixture; "Autre" → group concept, broadMatch; ignore the
  paperwork part, none only when nothing is said about the land), written in `docs/notes/step12_ontology.md`.
- Assil: **no e-mail to the professor** ("no need to send any email to my professor"); **public or private repository
  decided later, once there is a demo** ("don't bother urself with this kinda questions"): do not ask again (Gate 3
  point 17 and the professor's e-mail are off the waiting list). **No SMNPR e-mail either** ("don't write it, if we
  are not depending on them").
- **Gate R1 passed** (≈ 18:30): v5 rebuilt (new baseline with CQ15 in `meta.json`), then the audit's fresh rebuild:
  15/15 files byte-identical; release check OK; the gate's dataset tests pass (logs `results/logs/gate_r1_*`). The
  v5 panel caches (`results/v5/_cache/panel*.parquet`) had to be refreshed (their identity record holds
  `meta.json`'s hash): content identical. `openpyxl` 3.1.5 installed and pinned (gold-set worksheet, T81).
- Workers opened (space `sp34af9f51e4d6b4cc4d1eee9c657f4623`): `sol` (GPT-6.1-Sol high) → **T81** (the AGROVOC
  gold-set worksheet + import for Assil); `neon` (Gemini 4 Neon high) → **T82** (R2.1 Track 2: passages, prompt,
  dev/eval split fixed by Claude, the LLM runner with a stub, GPU step).
- **R2.3 started (lead):** SAREF4WATR v2.1.1 + ENVO 2026-10-23 alignment modules, deeper SWEET, 32 ledger rows (28
  asserted, 4 rejected), gate 8 extended to every SKOS mapping relation, meta 0.4.0; `test_ontology` passes.
  EuroCrops HCAT3 + French mapping pulled (183/198 codes; the gold of an RPG → HCAT experiment). GEMET and CORINE SKOS:
  Eionet unreachable from this network today (retry). **The graph release is stale** (ontology files changed): rebuild
  after the R2.2 terms (CQ15/CQ16), `PFE_DATASET=v5 .venv/bin/python -m src.kg.apply_rules` (≈ 10–15 min), then the
  exports and controls of the three policies and the graph test suites.
- T81 (worksheet; Assil's file `data/interim/agrovoc_gold_worksheet.xlsx` generated), T82 + T83 (Track 2 runner,
  fixes) and T84 (Colab GPU path for v5) reviewed and committed. R2.1 model-selection rule fixed before any output
  (step16 note: Qwen2.5-7B-Instruct, Qwen3-8B, OLMo-3-7B-Instruct on dev, best statement F1).
- **⚠ Colab session `ext` (L4, 2.33 units/h) RUNNING since ≈ 19:02 local** (job: `extract`, Qwen2.5-7B-Instruct,
  dev). If this session ends: `.venv/bin/python -m scripts.colab_cli pull ext`, then `stop ext` (never leave it
  billing). Then the other two candidates the same way (`EXTRACT_RUN=qwen3_8b_dev` with
  `EXTRACT_TEMPLATE_KWARGS={"enable_thinking": false}`, `EXTRACT_RUN=olmo3_7b_dev`), score each with
  `python -m src.kg.extract_llm score --pred results/v5/extraction/<run>/predictions_dev.json --split dev`.
- Workers now: `neon` → **T85** (CQ15 in the ontology and graph, then the release rebuild); `sol` → **T86** (OpenAlex
  harvest tool for Track 1; Claude runs it).
- ≈ 19:30: T86 committed; the real OpenAlex search ran (30 selected, `configs/track1_papers.csv`); PDF downloads
  running (`results/logs/openalex_download_2026-11-26.log`). Track 2 dev: **Qwen2.5-7B-Instruct statement F1 0.455**
  (P 0.417, R 0.500; commit `a09a354…`, unpinned run but main unchanged since 2025-01); Qwen3-8B (pinned
  `b968826…`) running on `ext`; OLMo-3-7B (`6e5971d…`) next. Track 1 schema and prompt committed (`02f8bf2`).
  Briefs ready: **T87** (sol, alignment scorer; running), **T88** (neon after T85: CQ10 + CQ16 + register codes).
  Eionet (GEMET, CORINE) still unreachable; the Manouba aquifer paper (Ferchichi et al. 2017,
  doi:10.1007/s12517-017-3314-4, open access) blocks scripts: on Assil's paper list.

### 2026-11-26 (Claude Opus 5.5, from ≈ 11:20 local time)
- Assil: "there is a bug fix folder start with that if those are valid bugs then continue the work as planned";
  Codex workers must use GPT Sol 6.1 high (not the global 6.2 default): spawned with `-m gpt-6.1-sol -c
  model_reasoning_effort=high`, status line checked ("GPT-6.1-Sol high"); memory updated.
- The "folder" is the file `docs/v5_bugs_to_fix.md` (audit of `720fb40`). Every item checked against code and data
  (`docs/v5_plan.md` §1b): all real. Item 1 (imputed pumping training the pumping gain): a linear probe loss shows a
  gradient change of 405 when only imputed pumping changes; the audit's fix leaves 273 (the 8-year kernel's memory);
  fixed by splitting each pumping stress into declared and imputed parts (imputed response with detached gain and
  kernel; pumping anomaly fixed in the loss before 2012): change exactly 0, values unchanged. New bug: v5 pumping 0
  for 1990–2002 (pumping table starts 2003, weather 1990) → now the well's training mean. Item 4: stage B = stage-A
  epochs then δ-only refinement (`--epochs-b`); held-out wells equal stage A bit for bit. Item 5.1 kernels bound;
  5.4/5.5 deferred to R2.2. All 7 checks of `tests.test_hybrid_gnn` and `tests.test_kernels` pass.
- Workers: neon → T71 (items 2–3), sol → T72 (BSS note, Gate R1 dataset tests on v5: all pass; committed), then T73.
- T71 (export units/overlies/basin canals, complete controls), T73 (v5 CPU path), T74 (v5 canal decision, ontology
  0.9.1, graph release 2026-11-26T11:26:11Z), T75 (unused-term review) reviewed and committed; lead follow-ups:
  multi-basin canal routing for controls, Taccari ignores v5-only relations.
- Plan v3 §8 decided by Assil (two AskUserQuestion rounds, every recommendation accepted): canal sign, pumping by
  declared facility-year (implemented: `pump_*_decl` arrays), twin criterion, CQ15, tuning budget per arm.
- Colab smoke run (v5e1, 0.12 units): ≈ 0.4 s/epoch on 1 thread; replay of its checkpoints on the laptop < 1e-5 m.
- R1.4: `src/ingest/gee_s2.py` pulled 142,282 parcel-years (8 min); logged in `data/README.md`.
- Arms A/B (facts, no graph) added to Hybrid-GNN v2; canal routing by basin node or plain node.
- Workers now: neon → T76 (CQ15 rule), sol → T77 (tuner). Usage at ≈ 13:45: Claude 5 h ≈ 60 %.
- Afternoon:
  - T76 (CQ15 rule: heuristic verdict) and T77 (tuner) reviewed and committed; plan v3 node features fixed.
  - T79 (CQ15 in the v5 build, deterministic), T80 (Track 2 scorer) and T78 (ontology modules and profiles,
    0.10.0, release rebuilt) reviewed and committed.
- Assil at ≈ 15:10: "after the 2 workers complete review their work and commit and push as assil-bouzaine and
  update where we are and what are the next steps". Done: workers closed, this file updated, branch pushed.
  Claude 5 h ≈ 85 % at the stop.

### 2026-11-25 (evening, Claude Opus 5.5, from ≈ 21:00 local time)
- Read `gemini_neon_review.md` (513 lines: 12 fixes, roadmap R0–R7). Assil: do all of it, in a new branch
  or a folder; Claude chose the branch `master_2026_fixes` (reason in `docs/v5_plan.md`).
- Checked the review's key claims before starting (`docs/v5_plan.md` §1): canal flow gauges ❌ (14 of 15
  stations empty, the 15th has 58 days of 2005); leave-wells-out intercept bug ✅ (`response.py:361`);
  the "train from 2012" proof ⚠️ weak (f25, also all after 2012, gives D −0.069; every model moves ±0.2
  between regimes); 6 weather-blind core wells ✅. Added an honest-reporting rule: v5 was designed after
  seeing v4's test scores, so v5's confirmation must come from the twin, leave-wells-out, validation and
  the post-freeze weeks (`docs/v5_plan.md` §2).
- Compute checked: Colab 165.30 units, no session; Kaggle `assilbouzaine` works (kernel idle); Camber CLI
  token expired (needs `camber login`). Written to `.agents/RESOURCES.md` (private).
- Workers opened in herdr: `sol` (gpt-6.1-sol high) → T59; `neon` (gemini-4-neon-high) → T60.
  `.agents/briefs/RULES.md` updated (new pair, branch rule).
- Started `arms_report` (R0.1) on the laptop.
- Camber checked in the web app (Chrome): account named in .agents/RESOURCES.md,
  Student plan with CPU and a single L4 GPU, 5.19 h used so far (October). Assil: "we also have Google Earth
  Engine": `earthengine-api` 1.7.53 installed and pinned; sign-in and project ID pending.
- T59 (sol) committed: 83 of 413 ontology terms mention a French source, 16 in their name (the France-profile
  candidates), 67 only in definitions (the review said 49).
- T60 (neon) committed: canal intakes by river basin via BD Carthage codes (Têt 72 % of the volume, −33 %
  2022→2023); annual basin totals unrelated to the yearly deficit (r ≈ 0).
- R1 pulls (all logged in `data/README.md`): BRGM BSS points from the open WFS (`src/ingest/brgm_bss.py`,
  6,049 water points with depth and BD LISA entities in dept 66; only 217 BNPE points join by BSS code);
  BNPE 2025 not published (0 records); dated Hub'Eau snapshots of 2026-11-25 for piezometers (6,574 records
  since 2024 now "Correcte") and river flows (to Nov 2026; QmnJ exists from 2005 only); canal stations have
  no flow after 2004 (claim C1 rejected again). Both Hub'Eau ingests got a `--snapshot DAY` mode so v4's
  caches stay untouched.
- `src/dataset/build.py`: a `v5` entry (forcing from 1990, the two snapshots, canal basins written as
  `canal_basins_weekly.parquet`), `CHRON`/`HYDRO` version-aware; `placeholders.py` reads the builder's
  `CHRON`. Not yet built (waits for SAFRAN 1990).
- Sol → T61 (LWO centring diagnostic), Neon → T62 (BSS evidence precision).
- R0 closed: `arms_report` (`docs/results_arms_v4.md`) and the reading in `docs/notes/step14_phase4.md`: facts no
  effect of interest (they act like name tags), structure undecided (intervals ±0.12), hard signs cost no accuracy,
  D beats random graphs but ties distance-preserving rewires; B7 (unit-wide recharge, drainage) no paired gain.
  Tag `phase4-v1-frozen` (pushed with the branch on 2026-11-25; commit IDs changed when the co-author lines and
  an e-mail address were removed from the branch history before its first push).
- T61 (sol): the LWO intercept is a minor part of the transfer failure (`docs/lwo_centring_v4.md`).
- T62 (neon): BSS adds nothing usable for irrigation attribution (`docs/bss_evidence.md`); it found that the paged
  WFS pull skipped ≈ 22 % of features: the ingest now tiles (`raw/brgm_bss/2026-11-25-tiled/`).
- T63 (neon): `src/models/bucket.py`, the monotone soil bucket (0 sign violations, water balance exact).
- SAFRAN 1990–1999 pulled; Météo-France republished 2023+ (0.01–0.17 % changes). Dataset v5 built: same wells,
  core and folds as v4; core test weeks not validated 41.5 % → 23.7 %. v5 crop demand and reconstruction 3 built.
- `docs/analysis_plan_v3.md` drafted (centring held fixed after estimation, so every driver stays monotone).
- torch_geometric 2.8.1 and earthengine-api 1.7.53 installed and pinned.
- Earth Engine: Assil signed in and gave the project; a first sign-in with a non-owner account was refused
  (serviceusage permission); after `earthengine authenticate --force` with the owner account it works; the three
  collections of the review are readable for Roussillon and Manouba.
- T64 (sol) kernels and T66 (neon) HeteroData builder + encoder committed; Sol on T58 (figures); v5 graph release
  validated (no violation), v5 graph test suites running.
- T58 (sol) Phase 4 figures committed (`reports/figures/phase4_*_v4.png`); v5 graph suites pass with the current rules;
  Neon on T65, Sol on T67.
- T65 (neon) committed: overlying-leakage recharge (rule by Claude), ontology 0.9.0, export `recharge_leakage`; v5
  release 2026-11-25T21:44:39Z; the 5 weather-blind Pliocene core wells now get recharge; CARRIE (unit outside
  BD LISA) is the only core well without a recharge path (Gate R2's named exception). Found: v5's last head week has
  no weather (T69 fixes it).
- T67 (sol) committed: RQ2 sign-violation counts reproduced (`docs/rq2_signs_v4.md`).
- Claude stopped briefing new work at ≈ 76 % of its 5-hour window to keep room for reviews and this file.
- T68 (sol) committed: Gate R1 reproducibility (13/13 files identical after a rebuild); the producer revised 2,273
  historical weekly heads (> 1 mm). Sol → T69, Neon → T70 (`hybrid_gnn.py` first assembly). Claude ended its active
  work at ≈ 78 % of its 5-hour window.
- T70 (neon) committed: Hybrid-GNN v2 first assembly. Open design point it raised: plan v3 §2 wants a hard canal sign
  (≥ 0) where a return into the well's own unit was measured (C2-1), but the v5 export marks every canal edge
  unconstrained (Gate 3's canal decision): decide in plan v3 §8 before the tag (the model already has a `canal_c` slot).
  Next for R3: Colab smoke run (`PFE_ALLOW_TRAIN=1`, a few epochs on v5), then tuning on validation, then twin v2.
- T69 (sol) committed: v5 ends at the last weather week (2026-11-22); v5 graph rebuilt (release
  2026-11-25T22:35:50Z); all 8 graph suites pass. Session ended at ≈ 83 % of Claude's 5-hour window.
