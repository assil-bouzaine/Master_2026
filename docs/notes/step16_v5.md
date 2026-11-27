# Step 16 — v5: carrying out the Gemini Neon review (plan `docs/v5_plan.md`, phases R0–R7)

The plan, its owners and statuses live in `docs/v5_plan.md`; the session log in `SESSION_HANDOFF.md`. This note
records, step by step, what was done, why, and what to keep in mind. Earlier v5 work (2026-11-25: R0 closed, dataset
v5 built and audited, leakage recharge, the model's pieces) is in `SESSION_HANDOFF.md` and the worker reports
`results/_agents/reports/T58`–`T70`.

## 2026-11-26 — the bug audit (`docs/v5_bugs_to_fix.md`): checked, then fixed

An audit of yesterday's v5 work listed four bugs or gaps to fix before the first Colab run of Hybrid-GNN v2, and
five cleanups. Every claim was checked against the code and the data before anything changed (verdict table:
`docs/v5_plan.md` §1b). All nine items hold; one bug was larger than the audit said, and checking it found a tenth.

### What was done

1. **Imputed pumping no longer trains the pumping response (item 1).** The BNPE declarations start in 2012; the
   2005–2011 pumping is invented (each facility's later volume copied back: the plain's total is 881.5 thousand
   m³/week every year 2003–2011). Plan v3 §3.6 says invented pumping must never calibrate a pumping response. The
   first version only cut the gradient on the pre-2012 weeks. The audit found that the training-mean centre still
   let it through. Measuring it with a probe loss showed that this was only part of the leak. With an eight-year
   kernel, the 2012–2014 contributions are still partly made of 2005–2011 pumping, so the post-2012 weeks also
   calibrated the gain on invented volumes. In a toy model, multiplying the invented weeks by 100 moved the
   pumping-gain gradient by 405. The audit's own fix left 273.
   The fix splits each pumping series into a declared part and an imputed part. The imputed part's response is
   computed with "frozen" copies of the gain and kernel. The sum is the same number (convolution is linear), so
   the predictions do not change. Before 2012, the whole pumping term (contribution minus its centre) is frozen in
   the loss. After the fix the probe change is exactly 0, and the training values equal the inference values
   (3e-15).
2. **Pumping before 2003 is unknown, not zero (found while checking item 1).** Dataset v5 starts the weather in 1990
   (R1.1a) for a long warm-up, but the pumping table starts in 2003. The routing filled 1990–2002 with zeros, so
   the model saw pumping jump from 0 to its full level in January 2003. Slow kernels would have turned that jump
   into a fake rising drawdown through 2005–2011, the training years. Those weeks now take the well's training
   mean, as the canal series and the kernel's warm-up already did. Frozen v4 had the same problem for 2000–2002
   (its weather started in 2000). It stays unchanged, as a known limitation of the pre-registered result.
3. **Stage B is now a refinement of stage A (item 4).** The design (review §5, plan v3 §3.5) has two stages:
   - **A:** the graph network alone must explain why wells differ, from facts and neighbours.
   - **B:** each training well gets a small, penalised correction δ.

   The first version trained B from scratch with δ free from the first epoch. That repeats the v4 failure the
   review measured: δ soaks up the well differences, the encoder learns nothing transferable, and held-out wells
   (δ = 0) are poorly predicted. Stage B now runs the stage-A epochs first, with δ held at exactly 0. Then, for
   `--epochs-b` epochs, it trains δ only. Held-out wells therefore get exactly stage A's parameters and
   predictions. The test checks this bit for bit.
4. **Kernel bound in one place (item 5.1):** the slow kernel's shape bound n ≥ 1 moved into `src/models/kernels.py`;
   the duplicate decoder in `hybrid_gnn.py` is gone.
5. **Delegated (items 2, 3, 5.3):**
   - **T71 (neon):** the export gains aquifer-unit nodes, `monitors` and `overlies` edges and basin canal nodes,
     and the control graphs rewire every relation of arm D, including the regional and leakage recharge channels
     they missed.
   - **T72 (sol):** fixed the BSS report's stale note and ran Gate R1's dataset tests on v5. All pass.
6. **Deferred (items 5.4, 5.5):** two wording and classification fixes inside the ontology file wait for the R2.2
   module split. Editing `lulcw.ttl` now would force a full graph-release rebuild for a sentence.

### Why it matters

- **RQ1:** the pumping fix is what makes the plan's claim about pumping honest. Without it, the pumping gains of
  every v5 arm would be partly fitted to invented volumes, and the D vs C pumping contrast would carry that.
- **RQ3:** the twin's "right reasons" test asks whether the recovered pumping contribution is right. It would have
  measured a mixture of real and invented calibration.
- **R2:** the stage fix decides whether leave-wells-out transfer can work at all. Held-out wells rely entirely on
  what stage A learned from facts and the graph.

### What to keep in mind

- **The values did not change, only what each value is allowed to teach.** A v5 prediction is still computed from
  the invented 2005–2011 pumping. Those weeks still train the weather, river and canal responses. They just do not
  train the pumping response. If the invented volumes are badly wrong, the errors they cause still sit in the
  residuals of 2005–2011 and of the first years after 2012, as noise for the other drivers.
- **"Declared" is a simplification.** 2012–2017 still have ≈ 40 % imputed facility-years under BNPE's documented
  rules, and 2025–2026 are fully imputed (BNPE 2025 not published). The plan's rule cuts at 2012 only. A finer rule
  (the `imputed` flag week by week) is possible but is a plan change: raise it at the §8 decisions if wanted.
- **Stage B has a new setting, `--epochs-b`** (default 200). It joins the epochs and penalties in the validation
  tuning.

### Checks

- `PFE_DATASET=v5 python -m tests.test_hybrid_gnn`: all seven checks pass. Each check, and what it covers:
  - **3c:** imputed ×100 changes no pumping gradient (exactly 0).
  - **3d:** training values equal inference values.
  - **4c:** stage B's first phase is the stage-A fit, only δ changes after it, and held-out wells are unchanged.
  - **7:** on the real v5 export, pre-2003 pumping equals the training mean, and centring holds to < 4e-8.
- `python -m tests.test_kernels`: passes with the new bound.

## 2026-11-26 — workers' tasks, plan v3 decisions, the Colab smoke run

### What was done

- **T71 (neon)**, audit items 2 and 3:
  - The v5 export now has 50 aquifer-unit nodes, 60 `monitors` edges (unit → well) and 38 `overlies` edges (upper →
    lower unit, direct contacts), plus one canal node per river basin.
  - The control graphs E and F rewire every relation of arm D, including the regional and leakage recharge
    channels they used to miss.
  - Two follow-ups by the lead: in the controls, a well linked to several basin canals now receives their mean
    series (it used to get the last one), and the v4 Taccari baseline ignores the v5-only relations.
- **T72 (sol):** the BSS report's note; Gate R1's dataset tests pass on v5. **T73 (sol):** a v5 path for the CPU runners
  (`scripts/run_v5_cpu.sh`, `colab_cli push-cpu --dataset v5`); the v4 bundle is unchanged file for file.
- **Plan v3 §8 decisions (Assil, recommendation first, all four accepted;** `docs/analysis_plan_v3.md` §8):
  - Canal sign: ≥ 0 on the two measured canal wells. Implemented as a v5 constraint decision in the graph (T74,
    neon).
  - Pumping teaches the model only through declared facility-years: the dataset's `imputed` flag, not a date.
    Implemented the same day: each pumping input has a declared twin.
  - The twin's pass criterion: D beats C in a majority of worlds, by a sign test at 5 %.
  - CQ15: built, and used in one with/without comparison row.
- **The Colab smoke run** (TPU v5e1 runtime, 24 vCPU AMD EPYC 7B13, 0.12 compute units). Hybrid-GNN v2, stage B,
  5 + 3 epochs, seed 0, arms C and D, then D on one thread. `PFE_NO_SCORE=1`: no test-period score was computed.
  - Each run took 13–14 s in total; the fitting part took 3–4 s for 8 epochs, **≈ 0.4 s per epoch, the same on 1
    thread as on 24**. The problem is small: 64 wells × 1,925 weeks, one batched FFT per epoch.
  - A full fit (500 stage-A + 200 stage-B epochs) is therefore ≈ 5 min on one thread. A 24-vCPU runtime running
    24 single-thread fits in parallel does ≈ 280 fits per hour, so the tuning and the whole R4 matrix fit in a
    few runtime-hours.
- **Replay across machines (Gate R3 criterion):** the checkpoints saved on Colab (Python 3.13) and replayed on the
  laptop (Python 3.12, same torch 2.14.1) reproduce their saved predictions to 4.1e-6 m (arm D) and 6.3e-6 m
  (arm C), under the 1e-5 m bound.

### What to keep in mind

- The validation numbers printed by the smoke run (after 8 epochs) mean nothing: they only show the run reached
  the end. Its prediction files (`results/v5/_smoke/`) also hold test-period weeks. They are never scored, and the
  `_smoke` folder is excluded from every report.
- Fits are cheap. So the tuning can give every arm its own budget (24 trials, re-selection over 3 seeds) rather
  than tuning only arm D, which would favour it. To decide with Assil, together with the ranges.

## 2026-11-26 (afternoon) — CQ15, the tuner, the ontology modules; session end

### What was done

- **CQ15** (T76, then T79). The rule labels each parcel-year:
  - *insufficient data*: fewer than 4 valid pixels or 3 clear summer acquisitions;
  - *not applicable*: soil wetness of the parcel's weather cell above 0.5;
  - *positive*: summer NDVI ≥ 0.485, a threshold set by Otsu's method on 2017–2019 only and frozen before the
    census was looked at.

  The 2020 census check gives orchards 0.71 (in range), vines 0.13 (too high) and market gardening 0.18 (too
  low), so the verdict is **heuristic**, as CQ15's contract foresees. Each well's 2017–2019 share of
  probably irrigated land is the static fact of the with/without row. Since T79 the v5 build makes these
  files, and two runs give identical bytes.
- **Arms A and B** of Hybrid-GNN v2: facts only, no graph. **The equal-budget tuner** (T77): 24 trials per arm,
  scored on validation only, then re-selection over 3 seeds.
- **The ontology split** (T78, ontology 0.10.0). `lulcw.ttl` stays the one authored file. Each term carries the
  module it belongs to, and a generator writes the 7 modules and the EU/FR/TN profiles from it. 96.4 % of the
  terms sit in the country-agnostic core; the French register codes live only in the France profile. The graph
  release was rebuilt with 0 violations, and the exports are unchanged.
- **R2.1, Track 2 scorer** (T80): the answer format and the precision/recall scoring of the LLM extraction
  against the 32 hand-checked statements, fixed before any model is chosen or run.

### What to keep in mind

- **CQ15 "heuristic":** say "probably irrigated by a vegetation rule". It is not an irrigation map: vines are
  over-detected and vegetable plots under-detected. Four mountain wells get green alpine pastures counted as
  irrigation (their coverage is low; the 33 core wells are at ≥ 98 %).
- **Gate R1 is not yet recorded as passed.** The cold-rebuild audit with the CQ15 files still has to run (the
  commands are in `SESSION_HANDOFF.md`).

## 2026-11-26 (evening) — Assil's answers, Gate R1 passed

### What was done

- **What Assil decided before any work** (he asked for the list of what Claude needs, one item at a time):
  - Camber's command-line login renewed (a free L4 GPU for the LLM extraction and the black box).
  - Push only at the end of a session.
  - Nitrate and the Aude feasibility (optional step R1.1c) skipped: pollution stays future work.
  - Manouba from free data only (satellite, land cover, ERA5-Land weather, published aquifer maps).
  - One annotator for the AGROVOC gold set for now, and the four labelling rules (the plant; one concept covering a
    mixture; "Autre" codes as a broader match of their group; ignore the subsidy paperwork, "none" only when nothing
    is said about the land): `docs/notes/step12_ontology.md`, section "12.9 gold-set decision rules".
  - No e-mail to the professor or to SMNPR: the plan does not depend on them.
- **Gate R1 passed.** The v5 build was run again (its `meta.json` now records the CQ15 files), then the audit rebuilt
  everything in a fresh process: all 15 files byte-identical, CQ15 included. The graph release still validates.
  The gate's dataset tests pass.

### Why it matters

Gate R1 says the v5 data are fixed and reproducible from the raw downloads: every later result can be traced back
to them, and the "post-freeze weeks" of R7.1 are defined against this freeze.

### What to keep in mind

- **Caches record what they were built from.** The panel caches (`results/v5/_cache/`) store the hash of every
  dataset file, `meta.json` included, and refuse to load when one changes: after the new baseline they had to be
  rebuilt (`build_panel(refresh=True)`, same content). Any future change to `meta.json` (even its `built` date on
  another day) will trigger the same refusal: rebuild the caches, don't silence the check.
- **The AGROVOC labels are on the path to Gate R2**: the gate asks for the alignment P/R/F1 tables. Assil labels the
  40 dev codes first (the matchers are tuned on them), then the 158 eval codes.

### R2.1: the model-selection rule, fixed before any model output (Claude, 2026-11-26 evening)

- **Candidates** (checked on Hugging Face on 2026-11-26: Apache-2.0 licence, not gated, text-only causal LMs that
  `transformers` loads with `AutoModelForCausalLM`, bf16 weights within an L4's 24 GB):
  `Qwen/Qwen2.5-7B-Instruct` (7.6 B parameters; the review's proposal), `Qwen/Qwen3-8B` (8.2 B; run with
  `{"enable_thinking": false}`), `allenai/Olmo-3-7B-Instruct` (7.3 B; open training data). Each run pins the
  resolved commit (`run.json`).
- **Not candidates:** `Qwen/Qwen3.5-9B` and `mistralai/Ministral-3-8B-Instruct-2512` (vision-language architectures,
  `…ForConditionalGeneration`), `openai/gpt-oss-20b` and `ibm-granite/granite-4.0-h-small` (too large for an L4
  in bf16), `google/gemma-3-12b-it` (Gemma licence, gated).
- **Rule:** each candidate runs once on the **dev** pages (19 passages, 10 gold statements; greedy decoding, the
  frozen prompt). The model with the highest statement F1 on dev is chosen; ties broken by strict F1, then by fewer
  parse failures, then by the smaller model. Only the chosen model then runs on **eval**, once, and that score is
  the Track 2 result. Dev scores are reported for every candidate.
- **Cost:** three dev runs plus one eval run on a Colab L4 (≈ 2 units/h): about 1–1.5 units.

### R2.1 Track 1: the design, fixed before any paper is harvested (Claude, 2026-11-26 evening)

- **Papers:** the OpenAlex harvest (T86): ten fixed queries (Mediterranean groundwater, irrigation, land-use change,
  recharge, nitrate, seawater intrusion; Spain, Tunisia, Morocco named), open-access articles since 2010 with a PDF,
  English or French, round-robin selection of 30, failed downloads replaced by the next candidate in order.
- **Passages:** every page of each PDF up to its references section (`pdftotext`), at most 20 pages per paper.
- **Model:** the one chosen on Track 2's dev pages (same decoding, greedy), so Track 1 adds no model choice.
- **Answer:** cause–effect statements, one JSON object each: the driver (verbatim phrase) and its category (irrigation
  expansion, groundwater abstraction, land-use or crop change, urbanisation, drought or climate, canal irrigation or
  return flow, fertilisation, managed recharge, water policy or restriction, other), the effect (verbatim phrase) and
  its category (groundwater level, recharge, groundwater quality or nitrate, salinisation or seawater intrusion,
  streamflow, drought risk, water-use conflict, other), the polarity (increases, decreases, no effect, unclear), the
  evidence type (measured, modelled, reviewed literature, stated without evidence), the place if stated, the verbatim
  quote and the page. The exact schema and prompt are written before the first run.
- **Measure:** no gold exists, so Assil reviews every extracted statement (accept: the quote supports the driver,
  effect and polarity as extracted; reject otherwise, with a one-word reason). Reported: the acceptance rate (the
  precision of the extraction as judged), per category and per evidence type. The first **two** papers in the
  selection order are a **pilot**: the prompt and schema may be fixed after reading their outputs; they are then
  excluded from the reported rate, which covers the other 28 papers only.
- **Use:** accepted statements whose categories map to the ontology's mechanisms (e.g. groundwater abstraction →
  `lulcw:PumpingDrawdown`, canal return flow → `lulcw:CanalReturnFlow`) enter the `med-causal` module as cited
  literature hypotheses (evidence kind `lulcw:ExpertHypothesis`, DOI, quote): never as constraints of the model.

### R2.3: alignments to SAREF4WATR, ENVO and deeper SWEET (2026-11-26 evening)

**What was done.** Three vocabularies were read at versioned sources (SAREF4WATR v2.1.1, ENVO's 2026-10-23
release, SWEET's rivers, hydrological phenomena and agriculture modules), the terms we use extracted locally
(`src/kg/build_imports.py --only`), and 32 correspondences written with the two definitions compared and a
counterexample considered (`ontology/alignments/ledger.csv`): 28 asserted (6 subclass axioms, the rest SKOS
close or broad matches), 4 rejected. The reasoner gate now checks every SKOS mapping relation; it passes (50
asserted correspondences in all, 14 required subclass links hold, none of the 29 forbidden ones). EuroCrops' French
mapping (RPG code → HCAT3, by the EuroCrops authors) was pulled as the gold of a second matching experiment.

**Why this way.** A subclass link says every instance of our class *is* one of theirs, so it was asserted only where
every instance in our graph fits their definition: our monitoring stations and river gauges are SAREF4WATR monitoring
infrastructure and gauging stations; our 22 watercourses (checked one by one) are natural rivers (SAREF4WATR, ENVO);
our alluvial and karst units are aquifers in ENVO's sense (as already for GWML2). Where a known instance breaks the
definition, only a close match: some piezometers are springs, not wells; 50 canal reaches are mapped underground
(a closed conduit, not SAREF's open "channel"); a BNPE intake record can describe one installation under several
codes. Rejected correspondences are kept because they show the traps a word-matching tool falls into (a "groundwater
body" is a management unit, not "groundwater").

**What to keep in mind.**
- SWEET has no written definitions: its matches rest on names and hierarchy, so they stay close matches.
- SAREF4AGRI gives nothing yet: its "Parcel" waits for CQ15's registered-parcel class; "Crop" and "WeatherStation"
  were rejected (a register code is not a collection of plants; a reanalysis grid cell is not a sensor).
- GEMET and CORINE (Eionet) could not be reached from this network; retry before Gate R2.
- EuroCrops is CC BY-SA: it stays a separate evaluation resource, never copied into the CC BY ontology.

### R2.1 Track 2: the dev runs and the model chosen by the rule (2026-11-26 evening)

Colab L4, greedy decoding, the frozen prompt, the 19 dev passages (10 gold statements); runs in
`results/v5/extraction/<run>/` (raw answers, `config.json`, `run.json`, `score_dev.md`):

| Candidate (commit) | Predictions | Parse failures | Statement P / R / F1 | Strict F1 |
|---|---:|---:|---|---:|
| Qwen/Qwen3-8B (`b968826…`, thinking off) | 16 | 0 | 0.375 / 0.600 / **0.462** | 0.385 |
| Qwen/Qwen2.5-7B-Instruct (`a09a354…`) | 12 | 0 | 0.417 / 0.500 / 0.455 | 0.455 |
| allenai/Olmo-3-7B-Instruct (`6e5971d…`) | 0 | 1 | 0 / 0 / 0 | 0 |

By the rule fixed before any output (highest statement F1 on dev), **Qwen3-8B is chosen**; only it runs on eval.
Qwen2.5-7B was within one statement of it (and better on strict F1), which the thesis reports. OLMo-3 answered `[]`
on 18 pages and, on the long web page, produced a runaway answer that hit the 4,096-token limit (an unterminated
string): it does not follow this extraction format zero-shot. The Qwen2.5 run did not record its commit
(`resolved_revision` empty with transformers 5.19); its main branch has not changed since 2025-01-12, so it used
`a09a354…`; later runs pass the commit explicitly (`EXTRACT_REVISION`).

### R2.1 Track 1: amendment of the download rule (Assil, 2026-11-26 ≈ 19:40, before any model read a paper)

The scripted download obtained only 12 of the 30 papers selected by the round-robin rule: MDPI, Springer, Wiley and
Elsevier refuse scripted requests, so the replacement rule was filling the set with the next works from the few hosts
that allow them (6 replacements downloaded, 11 more failed before the run was stopped). That would bias the set
towards those publishers. **Decided by Assil:** the paper set is exactly the 30 works the rule selected (orders 1–30
of `configs/track1_papers.csv`); he downloads the 18 the script could not, through his university's access, into
`data/raw/openalex/2026-11-26/pdf/<OpenAlex id>.pdf`; the replacement rule is withdrawn. The replacement PDFs stay
on disk, outside the set. The CSV is updated after his downloads (status, size and SHA-256 of every file; a reason
"downloaded by hand, university access"). No model output existed at the time of this change.

### R2.1 Track 2: the eval result (2026-11-26 ≈ 19:46, scored once with the frozen prompt and model)

Qwen3-8B (`b968826…`, thinking off) on the 47 eval passages (22 gold statements): 102 predictions, 0 parse
failures; **statement precision 0.069, recall 0.318, F1 0.113; strict F1 0.065** (7 matched, 4 strict); matched-pair
accuracy: mechanism 0.86, direction 0.57, hedging 0.71, method 0.71, subject 0.14 (`results/v5/extraction/
qwen3_8b_eval/score_eval.md`). Far below dev (0.462): the model over-produces on the long BRGM pages and misses most
rows of the FRDG351 water-body table (11 eval statements on one page).

**Caveat to settle before reporting:** the 32 gold statements were curated as evidence for the knowledge graph, not
as an exhaustive annotation of every page, so an unmatched prediction may be a true statement the gold lacks; the
precision is then a lower bound. Next step: judge a fixed sample of the 95 unmatched predictions (e.g. every
fifth, by index) against the source page and report the share that are true statements beside the scores. The
scores above stay the pre-specified result.
- **Done the same evening:** Assil downloaded 14 of the 18 by hand (moved from `~/Documents` to the PDF folder under
  their OpenAlex names; size and SHA-256 recorded). The other 4 (orders 6, 17, 21, 26) could not be obtained by hand
  either, so, at his request, each was replaced by the original rule (the next downloaded work in the round-robin
  order: orders 35, 36, 37, 42). The set is 30 papers: 12 scripted, 14 by hand, 4 replacements; the other downloaded
  replacements are marked `outside_set`. Pilot = orders 1 and 2, as fixed.

### R2.1 Track 2: the sample check of unmatched predictions — rule fixed before judging (Claude, 2026-11-26 ≈ 23:05)

Why: the gold was curated as graph evidence, not as an exhaustive annotation, so an unmatched prediction can be a true
statement the gold lacks; the eval precision (0.069) is then a lower bound. The check estimates how much.
- **Sample (mechanical):** the valid unmatched predictions listed in `results/v5/extraction/qwen3_8b_eval/score_eval.md`
  (zero-based indices, 95 items), in increasing index order; every fifth, starting with the first (positions 0, 5,
  …, 90): 19 predictions (indices 1, 6, 11, …, 90, 96).
- **Judge:** Claude (the lead), against the source page (`data/interim/extraction_passages_track2.jsonl`), one verdict
  each: **supported** (the page states this exchange: mechanism and direction as extracted, about the named unit or
  watercourse; codes may be incomplete, none wrong); **partly** (an exchange of that mechanism is stated, but the
  direction or a code is wrong, or the quote is general background rather than a statement about a named unit or
  reach); **not supported** (no such statement on the page). Assil can review every verdict in the sheet.
- **Report:** counts per verdict, the supported share with its Wilson 95 % interval, and the implied precision range
  (matched + supported share × 95 unmatched, over 102). The pre-specified scores stay the result; this is a reading
  aid, labelled as Claude's judgement.

**Result of the sample check (Claude's judgement, 2026-11-26 ≈ 23:10; sheet `configs/track2_sample_check.csv`, one
reason per verdict).** Of the 19 sampled unmatched
predictions: **3 supported** (one an exact duplicate of another on the same page, so 2 distinct statements the gold
lacks), **6 partly** (the right exchange on the page but a wrong direction or code, or a methodological or
cross-reference sentence), **10 not supported**. A decision taken while judging, stated here: a duplicate is
supported on content but adds no statement, so the implied precision uses the 2 distinct ones.
- Supported share 2/19 = 0.105 (Wilson 95 % [0.029, 0.314]): **implied precision ≈ 0.17 [0.10, 0.36]** instead of the
  scored 0.069. Counting "partly" as true too: 9/19 = 0.47 [0.27, 0.68], implied precision ≈ 0.51 [0.32, 0.71]
  (generous: those carry wrong fields).
- **Pattern:** half of the 10 unsupported predictions (6, 75, 80, 90, 96) are exchanges **between two aquifers**
  (Quaternary ↔ Pliocene leakage) forced into `RiverExchange`; the schema has no leakage mechanism, and the model
  maps any "échange" onto the two it has. The others: canal water that never reaches groundwater (canal returns to the
  river, outflows to other sectors: 21, 65, 70), a table row with the wrong mechanism (48), the running title (85).
- **Reading:** the gold's non-exhaustiveness explains part of the gap (precision 0.07 → about 0.17), not most of it:
  the main error is a category confusion. Track 1's schema (driver → effect) can express a leakage statement (pumping
  in the Pliocene → leakage from the Quaternary) but has no category of its own for it (it falls under `other`): the
  pilot review should look at how the model handles such statements before the main run. The pre-specified Track 2
  scores stay the result.

### R2.2: CQ15 in the graph (T85) and why validation went from 9 to 82 minutes (Claude, 2026-11-26 night)

**What was done (T85, neon; reviewed by Claude).** Ontology 0.11.0 (39 terms: 6 `lulc`, 33 `eo`): registered parcels,
parcel–zone overlaps, Sentinel-2 summer NDVI observations with their quality counts, SIM2 summer soil wetness, the
probable-irrigation rule as a `DerivationRule` whose thresholds are read from `irrigation_s2_rule.json` (validity
`HeuristicRule`, from the 2020 census check), the 650 zone-season shares of all 65 wells, and the parcel-seasons of the
two LU-6 zones only (13,260). The SHACL-AF rule (order 70) derives the 13,260 classifications inside the graph; they
equal T76's Python statuses one for one (`test_kg_rules` 8, `test_cq`). Graph: facts 471,653 → 771,662 triples,
rule outputs +119,340. Every graph suite passed on the lead's rerun (logs `results/logs/t85_review_*.log`).

**The slowdown and its cause.** Rules 252 → 648 s, validation 551 → 4,905 s. A per-shape profile on the release graph
stopped after 15 min inside one check, `IrrigationClassificationKeyShape`'s completeness query:
`FILTER NOT EXISTS { ?c lulcw:classifiedParcel ?p ; lulcw:seasonYear ?y ; lulcw:derivationRule $this }`.
`apply_rules.fast_sparql` orders a block's patterns knowing only `$this` as bound; inside NOT EXISTS the outer `?p`
and `?y` are bound at run time but unknown to the ordering, so `?c lulcw:derivationRule $this` (one "free" variable)
runs first and scans all 13,260 classifications of the rule for each of the 13,260 observations. Synthetic benchmark
(`scripts/diag_bench_not_exists.py`): 12.5 s for 500 parcel-seasons, 40.9 s for 1,000 (quadratic); a runtime-aware
ordering by number of unbound terms does not help (both patterns have one unbound term; only their selectivity
differs). **Fix (to apply at the start of the next session, before T88's rebuild):** write the block as
`FILTER NOT EXISTS { ?c lulcw:classifiedParcel ?p ; lulcw:seasonYear ?y ; lulcw:derivationRule ?rule . FILTER (?rule
= $this) }` — 13,260 parcel-seasons in 9.2 s, same violations found. The other CQ15 shapes are SHACL Core or
subject-bound and stay fast. The rule's soil-wetness OPTIONAL costs about 40 lookups per parcel-season (not
quadratic); where the remaining +400 s of rule time goes is to measure with `scripts/diag_profile_rules.py`.

**What to keep in mind.** Inside NOT EXISTS / OPTIONAL / EXISTS, never write `$this` or a hub constant in a pattern:
bind a fresh variable and compare it in a FILTER, and write first the pattern that uses an outer variable (rule added
to the T88 brief). Open ontology points from T85, assigned to T88: `lulcw:cropCode`'s domain (now used on parcels too)
and the `eo` module's description.

## 2026-11-27 — graph speed, the persisted store, the matchers' first run, CLC, reuse

### What was done
- **CQ15 validation fix applied** (`c7cf39a`): the completeness check of `IrrigationClassificationKeyShape` binds the
  rule to `?rule` and compares it in a FILTER inside its NOT EXISTS. Checked end to end with pySHACL and the real
  shapes file on a synthetic graph: the 3 planted gaps are found at 300 and at 3,000 parcel-seasons (2.2 s, 9.8 s).
- **Rule profile** (`scripts/diag_profile_rules.py`, log `results/logs/diag_profile_rules_2026-11-27.log`): the
  rules took 645 s, the CQ15 rule (order 70) 429 s of them. Timing the rule piece by piece on a 300-parcel-season
  sample (`scripts/diag_cq15_rule_parts.py`) put 8.2 of its 8.7 s in the soil-wetness OPTIONAL. That block compared
  fresh variables to the outer ones in a FILTER (`?scell = ?cell && ?syear = ?year`), so rdflib ran the nested
  OPTIONAL and evaluated the FILTER for each of the 40 soil-wetness observations, for every parcel-season (27 ms
  each). Rewriting it with a FILTER on the property instead was slower (74 s); folding the parcel's cell into the
  same OPTIONAL and joining on `?cell` and `?year` inside the patterns let rdflib prune while matching: 1.5 s on the
  sample. On the full v5 facts: **615 s → 89 s, the same 119,340 triples** (`scripts/diag_cq15_rule_rewrite.py`,
  old rule from git HEAD, new from the working tree). A parcel without a matched cell still gets no soil wetness
  (negative control on the sample: the same triples as the old rule).
- **Persisted store** (`src/kg/store.py`, `tests/test_store.py`, 7 checks): the release's facts and rule outputs in a
  disk-backed, read-only pyoxigraph store `data/processed/kg/store_<dataset>/`, rebuilt only when the release
  manifest changes (its SHA-256 is recorded), swapped in atomically, locked against two builders. `kg_store()` now
  returns it (same two files, same default graph, so the same answers); `persisted=False` keeps the old in-memory
  path. **CQ timing** (`src/kg/cq_timing.py` → `docs/cq_timing_v5.md`): runs the CQ data checks of
  `tests/test_cq.py` on the store with every `ask` timed by query file; exits 1 if a query's slowest call reaches
  1 s (Gate R2). To run after the release rebuild.
- **T92** (sol) reviewed and committed: the matchers. First Colab run (`hcat`, L4): all three steps failed at
  import: OntoAligner imports pykeen, whose optimizer registry, built from the loaded classes, met bitsandbytes'
  Adam and Adagrad next to torch's (`RegistrationNameConflict`). bitsandbytes is an OntoAligner dependency used only
  by its 8-bit LLM loader, which `align_match` avoids: the step now uninstalls it in the session. Second run: fuzzy
  done; retrieval refused by T92's own commit check, because sentence-transformers 5 leaves
  `config._commit_hash` empty: BGE-M3 is now loaded from `huggingface_hub.snapshot_download` at the pinned commit
  (the snapshot folder is named by the resolved commit). `scripts/colab_pull.py` now copies alignment runs.
- **Fuzzy floor** (OntoAligner `SimpleFuzzySMLightweight`, RapidFuzz on the label strings, French source against
  English HCAT names): strict P = R = F1 = **0.135 on dev** (5/37), **0.110 on eval** (16/146); area-weighted on
  eval 0.248. As the brief expected, a floor.
- **T93** (sol) reviewed and committed: `src/kg/reuse_report.py` → `docs/ontology_reuse_tn.md`. At ontology 0.12.0
  (T88 in progress): 535 of 551 terms (97.1 %) are usable in Tunisia unchanged; the 16 others are French register
  codes (14) and the EU water-body code (2). But only 65 of 82 validation shapes, 7 of 17 rule shapes and 14 of 40
  CQ queries are reusable unchanged, because they match on `bdlisaCode`, `bssCode`, `bnpeCode`, `rpgEdition` or
  `bdCarthageCode`.
- **CORINE Land Cover** (R2.3): the Eionet CLC vocabulary has labels but no definitions, and `land.copernicus.eu`
  refused every connection; the official guideline pages of the eight agricultural classes came from Internet
  Archive copies (logged in `data/README.md`). From their definitions, `configs/lu_clc.csv`: vine and olive
  closeMatch 221 and 223; orchards, citrus and nuts broadMatch 222 (CLC 222 lists orchards, citrus species and nut
  crops); the annual classes relatedMatch 211, and also 212 when usually or partly irrigated; grassland relatedMatch
  231; no_crop and unmapped none. sol → **T94** wires it into the graph like HILUCS.
- **GEMET** candidates read in GEMET 4.2.3 (handoff, item 3 of "Next"); notably GEMET's "groundwater extraction"
  (3781) is defined as over-extraction, so it is a rejected-row example, and "water abstraction" (15394) the target.
- **Manouba**: besides Ferchichi et al. 2017, a search found an HAL record of a paper on the recharge areas of this
  aquifer (Saidi et al. 2017, *Environmental Earth Sciences*; DOI given by the search as 10.1007/s12665-017-6840-1,
  **not yet verified**); HAL blocks scripts (bot protection): on Assil's list.

### Why it matters
- The graph is rebuilt after every ontology change: rules went from about 11 to about 4 minutes and validation from
  82 back to about 10, so a release costs about 20 minutes instead of 100.
- Gate R2 asks every CQ query to answer in under 1 s on a persisted store; the store and the timing script make that
  a measured number.
- CLC classifies arable land by irrigation infrastructure, not by crop (drip-irrigated vegetables are 211, not
  212). A crop class therefore cannot say "irrigated land" in CLC's sense: the relatedMatch rows say so honestly, and
  this is one more reason CQ15 (irrigation from Sentinel-2) stays a separate, heuristic concept.
- The reuse report shows where the ontology is still French in practice: not in its vocabulary, but in the rules
  and queries that identify things by their French register codes.

### What to keep in mind
- In SPARQL for rdflib (rules and shapes): join on the outer variables **inside** the patterns of an OPTIONAL, not
  through a FILTER over fresh variables (same lesson as the NOT EXISTS fix: rdflib evaluates such a block once per
  outer row, and a FILTER only prunes after the block has run).
- The country-neutral refactor of rules and queries (identify wells, units and facilities by node or by a generic
  identifier, not by French codes) would raise the reuse numbers; it changes derived IRIs, so it needs the equality
  tests and exports updated: a design decision for Assil, not done.
