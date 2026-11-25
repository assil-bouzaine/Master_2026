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

---

## ▶ START HERE (state at the last update: 2026-11-25 ≈ 21:45 local time)

**Running at the last update:**
- laptop: `arms_report` (v4, scoring only) → `docs/results_arms_v4.md`, log
  `results/logs/arms_report_v4_2026-11-25.log` (prints only at the end; `exit=0` line when done).
- laptop: SAFRAN 1990–1999 pull (`results/logs/safran_1990_2026-11-25.log`; then it re-checks 2000–2026).
- `sol` on T61 (post-hoc centring of the v4 leave-wells-out predictions → `docs/lwo_centring_v4.md`).
- `neon` on T62 (what the BRGM BSS records add to pump attribution → `docs/bss_evidence.md`).
- No Colab session, no Kaggle kernel, no Camber node.

**Next, in order:**
1. If `docs/results_arms_v4.md` is missing or the log has no `exit=0`: rerun
   `PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m src.analysis.arms_report` (15–40 min).
   Then brief T58 (Phase 4 figures, `.agents/briefs/T58_phase4_figures.md`, worker line → `sol`).
2. Review T61 and T62 (diff, rerun tests, commit naming the worker).
3. R0 reading: RQ1 (B vs A, D vs C) and RQ2 in R1 and the regimes, controls, B5–B8, seed disagreement →
   `docs/notes/step14_phase4.md`; tell Assil the direction in plain words; tag `phase4-v1-frozen`.
4. R1.5: when SAFRAN 1990 is done, build `dataset_v5` (`PFE_DATASET=v5 python -m src.dataset.build`; the
   v5 entry exists in `src/dataset/build.py`; v4 is unchanged at code level: `PFE_DATASET=v4` resolves the
   same raw paths, and every new branch is gated on a v5-only setting), then the dataset tests; log in
   `data/README.md`. Note: a full v4 rebuild would differ anyway in its last weeks if the SAFRAN pull
   refreshed `sim2_66_2026.parquet` (the ingest updates the current year): check its log.
5. R1.4 once Earth Engine is authenticated; R1.3 integration after T62's precision.

**Waiting for Assil:**
- `! .venv/bin/earthengine authenticate` (Earth Engine sign-in, his) and the **Cloud project ID** Earth Engine
  is registered under (Assil said on 2026-11-25 that the account exists): unblocks R1.4.
- `! camber login` only if Camber jobs are to run from the terminal (the web app is logged in; account
  confirmed: the account named in .agents/RESOURCES.md, Student plan, CPU + single L4 GPU).
- Say whether to push the branch `master_2026_fixes` to GitHub (nothing pushed yet).
- (unchanged) the professor's e-mail, the two data e-mails, the AGROVOC gold set, the paywalled papers,
  the defence date.

---

## Session log

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
