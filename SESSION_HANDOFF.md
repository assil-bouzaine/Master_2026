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

## ▶ START HERE (state on 2026-11-26 ≈ 12:30 local time; session in progress)

**Running:** worker `neon` on T71 (export: aquifer units, `monitors`, `overlies`, basin canal nodes; controls for
every relation of D; rebuild of the v5 exports and controls), worker `sol` (GPT Sol 6.1 high) on T73 (a v5 path for
the CPU runners: `scripts/run_v5_cpu.sh` with `prepare_check` and `hgnn_smoke`, `--dataset v5` in the bundlers). No
Colab, Kaggle or Camber job. Branch `master_2026_fixes`; commits of today local (push only when Assil says so).

**Done today:** the bug audit `docs/v5_bugs_to_fix.md` checked item by item (verdicts: `docs/v5_plan.md` §1b, step
note `docs/notes/step16_v5.md`): all real; item 1 larger than reported (the kernel's memory also leaked imputed
pumping) and a new bug found (v5 pumping 0 for 1990–2002); hybrid fixes committed (`9f5dfbc`), `PFE_NO_SCORE`
(`7a2ff0c`), T72 BSS note + Gate R1 dataset tests pass on v5 (`dfd7ba5`).

**Next, in order:**
1. Review and commit T71 (neon) and T73 (sol) when their reports arrive (`results/_agents/reports/T71.md`, `T73.md`).
2. Plan v3 §8 decisions with Assil (canal sign at the 2 eligible 718BP02 wells, pumping reliability by year or by
   facility-year, twin v2 criterion, CQ15 in v5); then write them into `docs/analysis_plan_v3.md` §8.
3. Colab smoke run (after T71 + T73): `colab_cli up smoke --runtime v5e1`, `push-cpu smoke --dataset v5 --steps
   hgnn_smoke --budget 1`, pull, stop; read the time per epoch → the tuning budget (24 trials × 3 seeds).
4. R1.4 Sentinel-2 (`src/ingest/gee_s2.py`), then CQ15; R2.1 / R2.3 / R2.2 as listed in `docs/v5_plan.md`.

**Waiting for Assil:** (unchanged) `! camber login` if Camber should run jobs; the professor's e-mail, the two data
e-mails, the AGROVOC gold set, the paywalled papers, the defence date.

---

## Session log

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
