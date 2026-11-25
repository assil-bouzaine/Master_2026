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

## ▶ START HERE (state at the last update: 2026-11-25 ≈ 21:30 local time)

**Running at the last update:**
- laptop: `arms_report` (v4, scoring only) → `docs/results_arms_v4.md`, log
  `results/logs/arms_report_v4_2026-11-25.log`.
- `sol` on T59 (inventory of the ontology terms tied to France → `src/kg/country_terms.py`,
  `docs/ontology_country_terms.md`).
- `neon` on T60 (canal intakes by basin → `src/dataset/canal_basins.py`, `docs/canal_basins.md`).
- No Colab session, no Kaggle kernel, no Camber node.

**Next, in order:**
1. If `docs/results_arms_v4.md` is missing or the log has no `exit=0`: rerun
   `PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m src.analysis.arms_report` (15–30 min).
2. Review T59 and T60 (diff, rerun their tests, commit naming the worker). Then brief T58 (Phase 4
   figures, `.agents/briefs/T58_phase4_figures.md`, change its worker line to `sol`).
3. R0 reading: RQ1 (B vs A, D vs C) and RQ2 in R1 and the regimes, controls, B5–B8, seed disagreement →
   `docs/notes/step14_phase4.md`; tell Assil the direction in plain words; tag `phase4-v1-frozen`.
4. R1 (data v5): SAFRAN 1990 (check the download size first), Hub'Eau refresh, BNPE 2025 check, InfoTerre
   WFS, Hub'Eau monthly canal re-check; then `dataset_v5`.

**Waiting for Assil:**
- `! camber login` (the Camber CLI token expired), so Claude can confirm the Camber account and its CPU/GPU
  engines (`camber me`, `camber engine list`).
- Register a Google Earth Engine noncommercial project (blocks R1.4: Sentinel-2 rule and Manouba).
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
