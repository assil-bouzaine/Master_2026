# Response to the second external review (2026-10-23)

The review is `docs/review_codex_2026-10-23.md` (kept unchanged). This file records:
1. what Claude checked in the data and code
2. the verdict on each recommendation
3. what the checks found beyond the review
4. Assil's decisions (same day) and where each change lives

**Decisions by Assil (2026-10-23, 16:30):**
- **Dataset v4** is adopted. All baselines are re-run on it with the settings tuned on v3.
  The v3 runs in progress finish as planned.
- **Analysis plan v2** gets four changes:
  - the cluster-level test
  - the harder twin
  - pumping robustness
  - freeze + confirmation
- **Framing:** the umbrella question, and an honest claim for the ontology with an
  equivalence test.

## 1. The review's numbers, checked

| Claim of the review | How it was checked | Result |
|---|---|---|
| 71 weekly targets contain values qualified "Incorrecte" | raw Hub'Eau chronicles of the 65 wells | **Confirmed.** 71 weeks in the model window (72 with one in 2000): 63 consist only of such values (347 days at F3 in 2007), 8 are mixed (the mean shifts by ≤ 0.11 m). None is in the test period. |
| "validated" allows < 50 % unqualified days | `src/models/evaluate.py` | **Confirmed.** In practice weeks with 0 < share < 0.5 are only 0.2–0.3 % of weeks, so the subset was nearly strict already. |
| Unqualified share ≈ 52 % in 2025, 75 % in 2026 | core well-weeks of dataset v3 | **Confirmed:** 52.2 % and 74.5 %. |
| Pumping 2025–2026 entirely imputed | `pumping_weekly.parquet`, flag `imputed` | **Confirmed.** Also 2003–2011 (back-filled) and 7–8 % of 2023–2024. |
| Held-out wells keep their own mean and sd | `docs/analysis_plan.md` §4 | **Confirmed.** This is the documented "dynamics" convention. It was never "ungauged" prediction, but the wording must say so. |
| `pct_days_artesian` (from heads) stays an input for held-out wells | `src/models/features.py` | **Confirmed.** Since v3 it uses the training period only, so the test period does not leak. It belongs to the same convention as mean and sd. |
| 8 of 33 core wells have a core well in another fold < 500 m away; closest pair ≈ 20 m | fold assignment of v3 | **Confirmed:** 8 (12 within 1 km); 19.7 m (C2-1/C2-2). The pairs are nested sites of *different* units: exactly where unit knowledge should matter, and where a random split lets the twin carry the answer. |
| Less-data regimes keep statistics of the full period | `build_panel`, regimes | **Confirmed.** With only 2016–2019, a well's mean shifts by a median 0.16 m (max 1.82 m) and its sd by a median 13 %. |
| The forecast setup is not operational | `lagged_panel`, `build.py` | **Confirmed.** Within a year, the weekly pumping weights are normalised by the deficit of the *whole* year. Imputed years use later means. River gaps are interpolated between both ends. The docstring claimed "nothing after t-h is used": wrong, now corrected. |
| Wilcoxon treats wells as independent; 14 spatial clusters | `src/analysis/stats.py` | **Confirmed:** 14 cells of 10 km for the 33 core wells. |
| "50 of 53 Pliocene points are False" ≠ "False means Pliocene" | attribution data (§3) | **Confirmed, and it matters.** On the coded points of the plain, False means Pliocene in only 53 of 112 cases. |
| Comparison table incomplete; superseded verdicts in the reading list | `docs/literature/` | **Confirmed:** Wu 2025 ×2 "to complete". The reading list still had the semantic loss, PiShield and SGI-as-shortcut-test. Fixed (§4). |
| Schorpp et al. 2023; Chu et al. 2026; Water Research 2026 | Crossref, 2026-10-23 | **All three exist.** The Water Research paper is Jeong et al. The two 2026 abstracts are paywalled (ScienceDirect refuses automated access), so they are listed "to read", not described. |

## 2. Verdict on each recommendation

| # | Recommendation | Verdict | What changes | Where |
|---|---|---|---|---|
| P1 | Drop "Incorrecte" before aggregation; a truly validated subset with its coverage | adopt | v4 drops "Incorrecte" and "Qualification non définissable" values; new `strict` variant (every value "Correcte") with `n_weeks`; share of reconstructed values per week | `src/dataset/build.py`, `src/models/evaluate.py` |
| P1 | Recent results are provisional | adopt | The strict variant covers only **7 wells / 296 weeks** of the recovery (all weeks: 32 / 1,362). Recovery conclusions are labelled provisional and re-scored when ADES validates 2025–2026. | analysis plan v2 §1, §11 |
| P2 | Pumping is a reconstruction: test several | adopt (Assil) | Main contrasts under 3 reconstructions: the current one, flat drinking water, and irrigation timing from a fixed crop calendar independent of the year's weather. Conclusions must hold under all three. | analysis plan v2 §8, §10 |
| P2 | "Missing knowledge is the bottleneck" is too strong | adopt | Wording: missing measurements, forcing assumptions, model structure and memory are competing explanations. | analysis plan v2 §12; CLAUDE.md findings |
| P2 | Ask for monthly drinking-water production | already planned | E-mail ready (`docs/supervisor_questions.md` §5) | Assil |
| P3 | Label leave-wells-out accurately; group nearby wells | adopt (Assil) | R2 = "transfer to monitored wells left out of training, given their training-period head statistics (mean, sd, artesian share)". v4 folds keep wells < 2 km apart together: 45 blocks, the closest wells in different folds are 2,153 m apart (v3: 20 m). 4 Pliocene core wells per fold. | `src/dataset/build.py` (`grouped_folds`), analysis plan v2 §4 |
| P3 | Less-data regimes: recompute statistics on the allowed history | adopt (Assil) | From v4, `build_panel(train_start=...)` takes mean, sd, climatology and artesian share from the window only (cached as `panel_f25/f50`). The benchmark climatology stays the full-period one, so skill keeps one yardstick across regimes. | `src/models/features.py`, `lstm.py`, `stgnn.py`, `lgbm.py` |
| P4 | Information-availability audit; "operational" is not justified | adopt | The forecast task is renamed a **hindcast with reconstructed forcings**, with an audit table of what is available at issue time. Simulation is retrospective by definition. | analysis plan v2 §7b; `features.py` docstring |
| P4 | Freeze the hypotheses; confirm on later data | adopt (Assil) | Analysis plan v2 is tagged in git before any Phase 4 run. A confirmation check scores the weeks observed after the freeze, and the 2025–26 weeks once ADES validates them. | analysis plan v2 §11 |
| P5 | Validate pump attribution: both directions, coverage by volume and use, ambiguity allowed | adopt | Task 12.3 done (§3 below): rules with precision measured on 130 recorded boreholes, use-aware confidence, unknown kept. | `src/kg/pump_attribution.py` |
| P5 | A stack is geology, not connectivity; investigation ≠ screened depth | adopt (wording) | Stated in the attribution module, the ontology design and CQ2. | `docs/ontology_design.md` §4.3 |
| P6 | Hard monotonicity must hold on the whole input → output path | adopt | Conditions written down: the gain may not depend on the input it constrains; the residual network does not see the constrained drivers. A finite-difference test of the sign on random inputs goes into `tests/` with the model. | analysis plan v2 §10 |
| P6 | Exact additive explanations are not physical truth | adopt | Ontology consistency, faithfulness and causal correctness are reported as three separate properties. | analysis plan v2 §12 |
| P6 | The twin must include mechanisms the model cannot fit | adopt (Assil) | Twin variants: a different response shape, a missing driver, wrong KG links. Pastas gains become a comparator, not the reference. | analysis plan v2 §10; CLAUDE.md §3 |
| LU | Two RPG snapshots cannot support annual land-use effects | adopt | Land use is static context (2016, 2023). No annual land-use effect is claimed. | analysis plan v2 §12 |
| LU | RPG crop agreement cannot validate irrigation detection | adopt | `ProbablyIrrigatedParcel` is a labelled heuristic unless independent irrigation evidence is found. Candidates to check: Agreste census irrigated areas, ASA/canal perimeters, BNPE irrigation points. | `docs/ontology_design.md`; task 12.10 |
| LU | Test whether the satellite concept adds information | adopt | Arm B with and without the concept (one ablation row) | analysis plan v2 §10 |
| O | Relax "exactly one unit and depth" | adopt | The SHACL shape asks for at least one `UnitAttribution` (possibly "unknown") with a confidence; depth is optional and flagged when missing. | `docs/ontology_design.md` §5 |
| O | Compare with the same information as plain tables and rules | adopt, as a **test, not an arm** (Assil: framing) | The edge list produced by SPARQL must equal the one produced by pandas rules from the same tables. Equal edges give equal predictions, so an extra arm would only measure seed noise. The claim for the ontology is traceability, consistency and reuse; accuracy gains are credited to the knowledge. | analysis plan v2 §10; task 12.8 |
| S | Cluster-aware inference; effect sizes first | adopt (Assil) | Sign-flip permutation test over the 14 clusters (exact: 16,384 patterns); Holm on it; the Wilcoxon p is kept for comparison only. Tested in `tests/test_stats.py`. | `src/analysis/stats.py`, `baseline_report.py` |
| L | Complete the critical comparison; fix outdated verdicts | adopt | Positioning matrix (past heads as input? forcings? split? knowledge supplied? explanation validated?) for the central papers. Outdated verdicts corrected. New references added. | `docs/literature/` |
| R | Umbrella question | adopt (Assil) | "When does explicit hydrogeological knowledge improve groundwater simulation and explanation reliability under uncertain pumping information?" sits above RQ1–4; the title is unchanged. | CLAUDE.md §1a |
| Scope | Cuts | mostly already the plan | AlphaEarth/TESSERA: not planned unless a question needs them. No claim of predicting use conflicts (the conflict is the motivation). No crop-policy recommendation. Transfer demo and dashboard stay small and conditional. | CLAUDE.md §1b, §3 |

## 3. What the checks found beyond the review

1. **The headline "ML beats Pastas in the drought" does not survive the cluster-level
   test.**
   - Per-well Wilcoxon: p_holm 0.002–0.04.
   - Cluster sign-flip test on the same v3 runs: p_holm 0.08–0.23 for drought NSE and
     skill.
   - The effects are large: median ΔNSE +0.6 to +1.0. Most cluster-bootstrap intervals
     exclude 0.
   - Correct wording: "a large improvement, consistent across clusters in the bootstrap,
     not significant at 5 % with 14 clusters after Holm".
   - Only LightGBM's recovery NSE stays significant (p_holm 0.039).
   - The test family is not redefined after seeing this: that would be p-hacking.
2. **Recovery-phase evidence is thin once restricted to validated data:** 7 wells and 296
   weeks.
3. **The ADES record is not a perfect reference.**
   - 7 of the 10 recorded "recent alluvium" boreholes with a False flag are 96–130 m deep;
     one is named "forage dans nappe profonde".
   - Alluvium boreholes confirmed by both record and flag are 6–23 m deep.
   - The attribution therefore checks the record against depth: 4 boreholes are moved to
     the Pliocene, and the recorded unit is kept as a "possible" alternative.
4. **"False → Pliocene" works only together with the stack.**
   - Flag False with the Pliocene under the point: Pliocene in 92 % of the recorded
     boreholes (82 % against the raw record).
   - Flag False alone: 53 of 112 coded points.
   - Flag True → alluvium: 95 %. The exact alluvial entity is right in only 63 %.
5. **The recorded boreholes are drinking-water (114) and industry (16) wells: no
   irrigation.**
   - The rules' precision is unmeasured for irrigation boreholes, which therefore stay
     "possible".
   - Coverage of the plain's declared volume (2012–2024):
     - confident 27 %
     - probable 45 %, all drinking water
     - possible 21 %, mostly irrigation
     - unknown 7 %
   - 98 % of drinking-water volume is confident or probable.
6. **The recorded unit is often not under the point:** 30 % of recorded boreholes, median
   819 m away. Coordinates and polygon edges are approximate, so attributions use a 1 km
   tolerance and report it.

## 4. Still to do (owner)

| Item | When | Owner |
|---|---|---|
| Re-run every baseline on v4 (CPU: naive, LightGBM, Pastas; GPU: LSTM, EA-LSTM, distance ST-GNN, Taccari) with the v3-selected settings | after the v3 sweep, next days | Claude (+ Assil's Colab clicks) |
| Analysis plan v2 tagged (`analysis-plan-v2`) after Assil reads it; Phase 4 families confirmed at Gate 3 | before Phase 4 | Assil, then Claude |
| Equivalence test SPARQL edges = pandas edges | task 12.8 | Claude |
| Twin variants, pumping reconstructions, the monotonicity test | Phase 4 | Claude |
| Read the paywalled 2026 papers (university access) and fill their rows | Phase 3 | Assil |
| Independent irrigation evidence for the satellite rule | task 12.10 | Claude to search, Assil to confirm |
| Main runs: confident + probable pump links instead of confident only (proposal, §3 of CLAUDE.md) | before 12.8 | Assil decides |
