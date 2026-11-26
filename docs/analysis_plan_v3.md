# Analysis plan, version 3 (dataset v5, Hybrid-GNN v2) — DRAFT

**Status: draft of 2026-11-25** (Claude, branch `master_2026_fixes`). It becomes binding when it is tagged
`analysis-plan-v3` in git, which happens **before any v5 real-data run is scored** (step R3.1 of
`docs/v5_plan.md`). Until then each section can change; after the tag, changes are dated amendments at the
end, as in version 2 (`docs/analysis_plan.md` §14). Everything not changed here keeps version 2's rules
(`docs/analysis_plan.md`, tag `analysis-plan-v2`): endpoints, periods, the cluster sign-flip test with Holm,
the same-arm bands, the claim wording, the inputs that are never allowed.

## 0. Why a version 3, and what it may claim

Version 2's Phase 4 (dataset v4, the hybrid "v1") is complete and frozen (tag `phase4-v1-frozen`). An
external review (`gemini_neon_review.md`, adopted by Assil on 2026-11-25) read v4's **drought-period (test)**
scores and proposed changes: the leave-wells-out intercept, the weather-blind wells, a nonlinear recharge,
the canal split, the imputed pumping years, a parameter encoder that is a real graph network. Those changes
were chosen **after seeing the test weeks**. Hence:
1. v4 / Phase 4 v1 stays the **pre-specified** result of the thesis, reported as it is.
2. Every v5 result on the 2022–25 drought is labelled **"exploratory: design informed by v4's test
   scores"**. The v4 → v5 comparison is descriptive.
3. v5's **independent** evidence is limited to: (a) the twin v2 (known truth); (b) leave-wells-out transfer
   (R2), whose held-out wells were never fitted; (c) model selection on the validation period only; (d) the
   **post-freeze weeks**: observations recorded after dataset v5 is frozen (2026-11-25 snapshot), scored by
   the saved frozen v5 models (and the frozen v4 ones) in R7.1, never used to select anything.
4. The review's expectations are **not** hypotheses of this plan. In particular, the "train from 2012"
   result (f50) is weak evidence (`docs/v5_plan.md` §1 C3): the pumping-reliability rule (§3.6) is adopted
   on principle and its effect is measured, not assumed.

## 1. Data (dataset v5)

`PFE_DATASET=v5`, built by `src/dataset/build.py` (entry `v5`): v4's wells (65, 33 core) and rules, plus
- weather (SAFRAN-SIM2) from **1990** (15-year warm-up before the 2005 model start);
- the dated Hub'Eau snapshots of **2026-11-25** (piezometers: 2024–25 weeks re-qualified since v4; river
  flows to November 2026, from 2005 as the API serves nothing older);
- the canal volume **per river basin** (`canal_basins_weekly.parquet`; Têt, Agly, Tech, other, unknown);
- pumping before the first BNPE year stays imputed and flagged (`imputed`);
- no BRGM BSS evidence in the pump attribution: T62 measured that it adds nothing usable (only 240 BNPE points
  carry a BSS code; `docs/bss_evidence.md`), so v5 keeps the attribution of task 12.3;
- the Sentinel-2 `ProbablyIrrigatedParcel` shares per well (CQ15, built in R1.4/R2.2: decided by Assil on
  2026-11-26), as a static fact in one with/without row (§5), checked against the Agreste census or labelled a
  heuristic.
Splits, folds, regimes and masks as v4 (train ≤ 2019, validation 2020-01 → 2022-04, test from 2022-05
scored as drought and recovery). Météo-France republished SIM2 from 2023 after v4 was built (`data/README.md`):
v5's 2023+ weather may differ from v4's; the ladder's first rung (§4) separates data from model changes.

## 2. Knowledge graph and export (v5)

Arm D's edges come from the released v5 graph through `src/kg/export.py`, with the equivalence test against
pandas rules (unchanged principle). New relations:
- **recharge, three channels**, each its own stress: `local` (cells over the outcrop of the well's unit in its
  5 km zone: v4's main relation), `regional` (cells over that unit's outcrop across the forcing extent: v4's
  unit-wide sensitivity), `leakage` (cells over the outcrop, in the 5 km zone, of the unit lying directly above
  the well's unit in the well's own BD LISA stack: `lulcw:OverlyingLeakageInfluence`, a new SHACL-AF rule).
  Sign non-decreasing for all three (for leakage: Darcy flux through the confining layer grows with the upper
  head whatever its direction). **Gate R2 requires 0 of 33 core wells without any recharge path**, or a
  named, justified exception (e.g. a well outside BD LISA).
- **canal by basin:** a well with a canal edge receives its own basin's series (the basin of its nearest main
  river, `canal_basins.canal_edge_well_basins`), not the plain's sum. The canal sign stays free (Gate 3), except on
  the **eligible** canal edges, those with a measured or traced return into the well's own unit: hard ≥ 0 there
  (decided by Assil on 2026-11-26). Today that is the two wells on the Têt's recent alluvium (718BP02): MILLAS C2-1
  (geochemical mixing at the well: 45 % ± 8 of its water from canal irrigation, BRGM/RP-71486-FR p. 24) and
  10915X0395/PZ (canal losses into the unit by differential gauging, 1.2–1.7 m³/s, p. 29). It is a v5 constraint
  decision on the graph (`CanalReturnFlow` approved for eligible edges), so the export marks those edges
  constrained; Gate 3's free canal sign is kept as a sensitivity row.
- arms C, E, F rebuilt from the v5 export as in v2 §10 (same controls, same draws).

## 3. The main model: Hybrid-GNN v2 (`src/models/hybrid_gnn.py`)

Head anomaly of well i at week t (metres above its training mean μ_i):

    ŷ_i(t) = Σ_r [ c_ir(t) − m_ir ] + ρ_i(t),     c_ir = G_ir · (k_ir ∗ s_ir)

1. **Centring (fixes the LWO intercept):** m_ir = mean of c_ir over the well's observed training weeks (the
   weeks that define μ_i), computed from the **observed** forcing and then **held fixed**: it is a parameter
   estimated in closed form, not a function of the inputs. (Recomputing it from a counterfactual forcing
   would let extra rain inside the training period raise m and lower the anomaly at earlier weeks, breaking
   the sign rule; with m fixed, ŷ is monotone in every driver at every week, and the finite-difference test
   perturbs the inputs with m fixed.) No free per-well intercept. A held-out well gets its m from its own
   observed training weeks, which the design already gives it (μ_i). Unit test: the mean of ŷ_i over those
   weeks is 0 under the observed forcing. Expectation (T61, `docs/lwo_centring_v4.md`): centring alone is a
   minor part of the leave-wells-out failure (median offset ≈ 0.3 m; drought NSE did not improve), so R2
   transfer depends on the encoder (point 5) describing held-out wells' dynamics, not on the intercept.
2. **Gains in sd units, hard signs:** G_ir = σ_r · softplus(g_ir) · sd_i with σ_r ∈ {+1, −1} from the
   ontology (recharge channels +, pumping and unattributed pumping −, river + where eligible, canal + only
   where measured, else free).
3. **Nonlinear recharge, monotone by construction:** one weekly soil bucket per well and recharge channel,
   driven by the channel's weighted rain P and ETP:
   S⁺ = S + P; E = S⁺ (1 − exp(−ETP / S_max)); S⁺⁺ = S⁺ − E; O = max(S⁺⁺ − S_max, 0); S⁺⁺⁺ = min(S⁺⁺, S_max);
   Q = κ S⁺⁺⁺; S_next = S⁺⁺⁺ − Q; recharge R = (1 − β)(O + Q) + β P.
   Every step is non-decreasing in S and in P, so R is non-decreasing in rain at every week (and
   non-increasing in ETP); β is a fast bypass (karst conduits). Parameters S_max > 0, κ ∈ (0, 1), β ∈ [0, 1).
   The finite-difference test of v2 §10 is extended through the bucket. Reference for the design family:
   Pastas' FlexModel (Collenteur et al., to cite only after its DOI is checked).
4. **Kernels:** for each stress a mixture of a fast and a slow scaled-Gamma kernel (weights on a simplex,
   slow mean ≤ 104 weeks), causal FFT convolution (as `response.py --conv fft`), kernel length 416 weeks
   (`src/models/kernels.py`, T64). The slow component's shape is bounded below at n ≥ 1: with n = 0.5 and a
   104-week mean the 416-week truncation removes about 22 weeks of mean lag (T64's measurement).
5. **Parameter encoder (the graph network):** raw parameters θ_i = θ_g(i) + f_GNN(Z, graph)_i + δ_i, where
   f_GNN is a 2-layer heterogeneous graph network (PyG `HeteroConv` with `GATv2Conv`, hidden 32, 2 heads,
   dropout 0.1) over the export's node and relation types (well, aquifer unit, facility, weather cell, gauge,
   basin canal; monitors, overlies, same-unit-near, pumping, recharge channels, river, canal). Node features
   are **static facts only**, each computed inside the regime's training window and standardised
   (`src/models/hetero_graph.py`, `src/models/statics.py`; list fixed 2026-11-26):
   - wells, fact set B (14): log investigation depth and its missing flag, altitude, position in the BD LISA stack
     and its missing flag, the training-window artesian share (CQ14), the share and log volume of the attributed
     pumping and a no-pumping flag, the number of recharge cells, the river association (on outcrop, over cover,
     documented lateral) and a canal flag; arm A uses only the first six (set A);
   - facilities (6): log annual declared volume, the dominant use (drinking water, irrigation, industry, other),
     groundwater source;
   - weather cells (3): mean rain, ETP and effective rain;
   - gauges (1): log mean discharge;
   - basin canals (1): log mean canal volume;
   - aquifer units (5): the unit class (alluvial aquifer, confining unit, karst aquifer, multilayer system, other);
   - edge attributes: weight, log distance, sign, eligibility, constraint (with missing-value flags).

   The CQ15 irrigated share enters only its with/without row (§5). f never sees a stress, so the signs hold on the
   whole path. Arms A and B (§5) use a graph of wells only, so f reads each well's own facts (no message
   passing).
   **Two stages:** A, δ = 0 (well differences must come from facts and neighbours); B, δ with a ridge
   penalty (refinement on training wells only; held-out wells keep δ = 0).
6. **Pumping reliability** (revised 2026-11-26: the bug audit, `docs/v5_plan.md` §1b, and Assil's decision of the
   same day): invented pumping never calibrates a pumping response. "Invented" is decided **per facility and
   year** by the dataset's `imputed` flag, not by a date: before 2012 every volume is imputed, and from 2012 the
   back-filled facility-years (BNPE's 2018 reporting break: ≈ 15 % of the 2012–2017 groundwater volume, mostly
   irrigation boreholes in the unattributed input) are imputed too. Each pumping stress is split into its
   declared and imputed parts; the imputed part's response uses detached gains and kernels, at every week (its
   own weeks, the training-mean centre, and the kernel's memory of it later). On the weeks before the first
   declared week (2012) the whole pumping anomaly enters the loss as a fixed value. Values are unchanged; weather
   and the other drivers still learn from 2005–2011. Pumping weeks before the pumping record (1990–2002) are
   unknown, not zero: the well's training mean, like the canal series and the kernel's warm-up.
7. **Regularisation and convergence:** a strong penalty on the kernel and bucket parameters' spread around
   the group (λ_shape), a weak one on the gains (λ_gain < λ_shape); AdamW with cosine-annealed learning rate
   for a fixed number of epochs (no early stopping on test-like data; the epoch count and the λs are tuned on
   the **validation** period with the equal budget of v2 §5: 24 Optuna trials, re-selection over 3 seeds).
   One model serves accuracy and explanations (no B2 / B2conv split). **Tuning (Assil, 2026-11-26):** each main
   arm (A, B, C, D) gets its own budget, so no arm inherits another's tuning; E and F reuse D's settings (they
   test D's edges, not a tuning). The search covers six settings, the network's size staying as point 5 fixes
   it: stage-A epochs 300–1500, stage-B epochs 0–400, learning rate 0.003–0.03 (log), λ_shape 0.001–1 (log),
   λ_gain = r · λ_shape with r 0.01–0.5 (log; so λ_gain < λ_shape), λ_δ 0.001–1 (log). Objective: the median
   validation NSE of the core wells (v2 §5). The settings tuned in R1 serve every regime (R2, R3, refit). Cost
   (Colab smoke run, 2026-11-26): ≈ 0.4 s per epoch on one thread, a full fit ≈ 5 min, ≈ 280 fits per hour on
   a 24-vCPU runtime.
8. **Residual row (sensitivity only):** ρ_i(t) bounded (|ρ| ≤ 0.20 sd_i), seeing the day of year and static
   facts only; off in the main model.
9. **Seeds:** 10 per primary arm; replay of every checkpoint to < 1e-5 m.

## 4. The ablation ladder (R4.2; descriptive, on v5, same machine type, 10 seeds each)

1. the v4 hybrid (`response.py`, as frozen) on v5 data → 2. + centring and sd gains → 3. + three recharge
channels and basin canals → 4. + bucket and two-component kernels → 5. + pumping reliability and split
regularisation → 6. + the graph-network encoder (**the main model**) → 7. + bounded residual (sensitivity).
Each rung against the previous one: per-well drought log RMSE ratio, cluster-bootstrap interval, same-arm
band; no p-values (descriptive). Rung 1 vs frozen v4 separates the data change from the model changes.

## 5. Contrasts (R4.3)

The families of v2 §10, on v5 with the main model: RQ1 (B vs A: facts; D vs C: structure), RQ2 (soft and
hard vs none), in R1, R2 (LWO), R3 (25 %, 50 %), refit; the controls E_degree, E_distance, F_random,
F_complete; reconstructions 1–3 ("holds under all three"); pump-link policies; and, if CQ15 exists, a
with/without row for the irrigated share. Primary measure, tests and Holm families as v2 (cluster sign-flip
over the 14 clusters). Label of every drought result: §0 point 2.

## 6. The black-box competitor and the explanations

A heterogeneous spatio-temporal network on the same HeteroData (PyG `HeteroConv` + gated temporal
convolution or GRU), tuned with the same budget, edges C vs D. Explanations (R5): exact contributions for the
hybrid; Integrated Gradients and GNNExplainer for the black box, aggregated by node and relation type;
fidelity+/− and deletion curves; a randomisation sanity check (trained D vs weight-shuffled D vs rewired E).

## 7. Gate R3 (before any v5 real-data contrast is scored)

- finite-difference sign test: 0 violations over random parameters and stresses, through the bucket, the
  kernels and the residual row;
- replay of saved checkpoints to < 1e-5 m;
- centring unit test on held-out wells; no head value of a held-out well beyond μ_i, sd_i enters;
- twin v2 (nonlinear recharge, leakage, basin canals, imputed pumping), criterion fixed before the twin runs
  (Assil, 2026-11-26): the main model's pumping-contribution error is lower than arm C's in a majority of worlds,
  by a sign test over worlds at 5 %; the seed spread of that error is reported beside it.

## 8. Decisions and open points before the tag

Decided by Assil on 2026-11-26 (AskUserQuestion, recommendation first; each the recommended option):
1. **Canal sign:** hard ≥ 0 on the eligible canal edges (a measured or traced return into the well's own unit:
   C2-1 and 10915X0395/PZ today), free elsewhere; Gate 3's free sign as a sensitivity row (§2).
2. **Pumping reliability:** declared facility-years only, by the `imputed` flag (§3.6).
3. **Twin v2 criterion:** D's pumping-contribution error below C's in a majority of worlds, sign test at 5 % (§7).
4. **CQ15:** built (R1.4, R2.2) and used as a static fact in one with/without row (§1, §5); Gate R1 waits for it.
Settled by the data: no BSS evidence in v5 (§1; T62).

5. **Tuning** (after the Colab smoke run): each main arm its own budget, E and F reuse D's; six settings,
   ranges in §3 point 7.
6. **Node features:** the list in §3 point 5 (fixed from the code, 2026-11-26).
Still open: the Manouba transfer (qualitative, outside these contrasts).
