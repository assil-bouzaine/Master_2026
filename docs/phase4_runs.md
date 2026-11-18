# Phase 4 run plan (draft of 2026-11-18, for Gate 3)

What Phase 4 will run, how many fits that is, what it costs on Kaggle, and what code is still
missing. **Nothing here runs before Gate 3 and the git tag of the analysis plan** (analysis plan §11,
§14 items 18–20). The decisions this plan depends on are marked *(Gate 3, point n)* and refer to
`docs/gate3_decisions.md`.

## 1. Fixed for every run

- **Model:** the response superposition of the ladder (`src/models/response.py`): Gamma kernels on
  312 weeks, FFT convolution (`--conv fft`), signs built in ("hard") unless the block is about RQ2.
- **Routing:** every arm goes through `src/models/routing.py`: `baseline` (the panel's rules, no
  graph: arms A and B), `C`, `D`, and the controls `E_degree:<d>`, `E_distance:<d>`, `F_random:<d>`,
  `F_complete` (`src/kg/controls.py`, five draws each).
- **Fitting protocol:** early stopping on validation or 3,000 fixed steps with pooling *(Gate 3,
  point 1; the twin's grid decides)*; the pooled λ chosen on validation in R1, nested (other folds
  only) in R2 (§10).
- **Starts:** 10 per run (item 18 point 4); a same-arm band (random halves of the starts) beside
  every primary contrast.
- **Machine:** Kaggle CPU for every arm of a contrast (one machine type per contrast, item 18).
- **Data:** dataset v4, export policy "main", pumping reconstruction (1) unless the block says
  otherwise.
- **Measure:** per core well, log(RMSE_x / RMSE_y) in the drought phase; median over wells, its
  cluster-bootstrap interval and the cluster sign-flip test (14 clusters), Holm within each family
  (item 18 point 3; families: Gate 3 point 14).

## 2. The blocks

Regimes (§4): R1 (main), R2 (five leave-wells-out folds), R3 (the 25 % and 50 % windows), the
refit on training + validation: **9 regime runs** per arm and setting. Reconstructions (§8): (1)
current, (2) flat drinking water, (3) crop calendar.

| Block | Question | Arms (command) | Regimes | Recon. | Runs | Starts |
|---|---|---|---|---|---|---|
| B1 | RQ1, knowledge as information (B vs A) | `--arm baseline --statics A` vs `--statics B`, rung 3 | 9 | 3 | 2 × 9 × 3 = 54 | 540 |
| B1c | facts or name tags? (controls of B) | B with `--static-control nametags`, `shuffled` | 9 | 1 | 2 × 9 = 18 | 180 |
| B2 | RQ1, edge semantics (D vs C), primary form: routing | `--arm C` vs `--arm D`, rung 4 *(with or without set-B facts: Gate 3, point 2)* | 9 | 3 | 2 × 9 × 3 = 54 | 540 |
| B3 | is D's gain semantic, local or density? | `E_degree`, `E_distance`, `F_random` (5 draws each), `F_complete` | R1, R2 | 1 | 16 × 6 = 96 | 960 |
| B4 | RQ2, sign constraints | arm D: hard, none, soft with λ_s ∈ {1, 10, 100} *(Gate 3, point 6)* | R1, R2 | 3 | 5 × 6 × 3 = 90 | 900 |
| B5 | rung 5, message passing (secondary) | `--message 1` on C and D (+ the B3 controls on R1) | R1, R2 | 1 | 2 × 6 + 16 = 28 | 280 |
| B6 | pump-link policy sensitivity | D vs C with the `confident-only` and `all-links` exports | R1, R2 | 1 | 2 × 2 × 6 = 24 | 240 |
| B7 | recharge sensitivities | D with unit-wide recharge cells; D with soil drainage instead of PE | R1 | 1 | 2 | 20 |
| | | | | | **366** | **3,660** |

**Cost.** Measured on Kaggle CPU (2,516 fits of the twin, real shapes, one thread per fit): an
early-stopped start takes a median 20 s (90th percentile 35 s), a 3,000-step start 98 s. With four
fits at once and 11 hours per session (2,640 CPU-minutes):

| Protocol | CPU-minutes for 3,660 starts | Kaggle sessions |
|---|---|---|
| early stopping (20–35 s per start) | 1,200–2,100 | 1 |
| 3,000 fixed steps (98 s per start) | about 6,000 | 2–3 |

So compute does not limit Phase 4: the whole table fits in one to three sessions, and a second
reconstruction-wide repeat of any block is affordable. The limit is the number of contrasts we can
read honestly: only B1 and B2 (RQ1) and B4 (RQ2) are confirmatory families; B1c, B3, B5–B7 are
declared now but reported as exploratory controls and sensitivities (§10, item 20).

## 3. Code still missing before the first Phase 4 run

| Piece | Status (2026-11-18) |
|---|---|
| Fact table of rung 3 (`src/models/statics.py`) | in progress (brief T03) |
| Pumping reconstructions (2) and (3) in the routed path | in progress (brief T06); arms A/B route through `baseline` for this reason |
| Arms report: contrasts, same-arm bands, coverage per relation, draw-vs-start variance of the controls | to write (extend `src/analysis/ladder_report.py`) |
| Kaggle steps for B1–B7 in `scripts/run_v4_cpu.sh` | to write after Gate 3 (settings depend on points 1, 2, 6) |
| Exports for the policy sensitivities (`python -m src.kg.export --policy confident-only`, `all-links`) | to build (B6) |
| Soil-drainage recharge input (B7) | to add to routing (DRAINC from SAFRAN) |
| The bounded residual network ("each rung with and without it", item 18) | not designed: Gate 3 |
| The black-box comparison (heterogeneous ST-GNN on the same graph, CLAUDE.md §3) | not built (GPU, Colab): Gate 3 to confirm its scope |

## 4. Reading order after the runs

1. The twin's map first (it says what a real-data D vs C can show: item 19 point 10 (d)).
2. B2 and B1 (RQ1), then B4 (RQ2): the confirmatory families.
3. B3 and B1c beside them: is a gain semantic, local, dense, or a name tag?
4. B5–B7: sensitivities, each read against its own main run.
