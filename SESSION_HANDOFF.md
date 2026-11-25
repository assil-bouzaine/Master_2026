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

**Running at the last update (≈ 22:25):**
- `sol` on T68 (dataset v5 audit for Gate R1: hashes before/after a rebuild, v4 vs v5 comparison →
  `docs/dataset_v5_audit.md`); its watcher was in the ended session, so check `results/_agents/reports/T68.md`.
- `neon` idle (T65 done and committed). No Colab, Kaggle, Camber or laptop job.

**Done today (details in the session log below):** R0 closed (arms report, reading, local tag
`phase4-v1-frozen`); R1 data pulled and dataset v5 built; T59–T63 reviewed and committed; analysis-plan-v3 drafted.

**Next, in order:**
1. Open the two workers (memory `codex-worker-orchestration`). Review T68 (sol) if its report exists; commit.
2. **T69** (brief ready: `.agents/briefs/T69_v5_end_at_forcing.md`): v5 heads end one week after the weather
   (2026-11-29 vs 2026-11-22) → `end_at_forcing` for v5, rebuild v5, its graph, exports, controls, all graph suites
   (incl. `tests.test_controls`, whose step 8 fails on that week). Give it to a worker; review; commit.
3. **R3, Hybrid-GNN v2** (`docs/analysis_plan_v3.md` §3; pieces done: `bucket.py`, `kernels.py`, `hetero_graph.py`):
   Claude writes `src/models/hybrid_gnn.py` (assembly, centring held fixed, sd gains, three recharge channels +
   basin canals from the v5 export, pumping reliability mask, two-stage encoder, split regularisation, cosine LR),
   its finite-difference sign test and replay; then the twin v2 (`src/models/twin.py`). Settle plan v3 §8's open
   points and tag `analysis-plan-v3` before any v5 real-data run.
4. **R1.4 Earth Engine** (ready): `src/ingest/gee_s2.py` (summer NDVI/NDMI per RPG parcel 2017–2025; Manouba S2 +
   WorldCover + ERA5-Land for a sourced aquifer box), then CQ15's `ProbablyIrrigatedParcel` rule.
5. R2.1 (literature extraction: OpenAlex + a local open LLM on Colab), R2.3 (alignments: SAREF4WATR/AGRI, CORINE,
   ENVO, GEMET, SWEET, EuroCrops HCAT; every term checked at its source), R2.2 rest (France/Tunisia profiles from
   `docs/ontology_country_terms.md`'s 16 name matches; the 23 unused terms reviewed one by one).

**Waiting for Assil:**
- Say whether to push the branch `master_2026_fixes` and the tag `phase4-v1-frozen` (nothing pushed yet).
- `! camber login` only if Camber jobs are to run from the terminal (web app logged in; account
  the account named in .agents/RESOURCES.md, Student plan, CPU + single L4 GPU).
- (unchanged) the professor's e-mail, the two data e-mails, the AGROVOC gold set, the paywalled papers, the
  defence date.

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
- R0 closed: `arms_report` (`docs/results_arms_v4.md`) and the reading in `docs/notes/step14_phase4.md`: facts no
  effect of interest (they act like name tags), structure undecided (intervals ±0.12), hard signs cost no accuracy,
  D beats random graphs but ties distance-preserving rewires; B7 (unit-wide recharge, drainage) no paired gain.
  Local tag `phase4-v1-frozen` at 80eabfe.
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
