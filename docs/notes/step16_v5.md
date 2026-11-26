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
