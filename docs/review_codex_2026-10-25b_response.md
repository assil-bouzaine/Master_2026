# Response to the second Codex review of 2026-10-25

Review: `docs/review_codex_2026-10-25b.md` (written by Codex as `codex.md` at 13:09 and kept
unchanged; md5 70c4b11c…). Every claim was checked against the code and data on
2026-10-25 afternoon; decisions by Assil the same day. The review read a snapshot taken in
the middle of the land-use work (between commits `f03573d` and `8e3f420`), so some findings
describe that moment. They are marked "held at the snapshot".

## 1. Verdicts

| Point | Verdict | What was done |
|---|---|---|
| `tests.test_crop_demand` fails (`KeyError: demand_main_m3`) | Held at the snapshot: the columns had been renamed in the code, the file not yet rebuilt | Rebuilt on all 11 editions (`8e3f420`); passes |
| `tests.test_pumping_cropcal` fails (summer/non-summer ratio 4.4 < 5) | Held at the snapshot. As the review advises, the scientific invariant was checked first: 0 % of the weights December–February, peak June–July, 62 % in summer; orchards also need water in spring and September | The arbitrary 5× threshold was replaced by "winter < 1 %, summer > 50 %" (`8e3f420`); passes. The formula was not changed |
| `pumping_weekly_cropcal_v4.parquet` absent | Held at the snapshot | Built at 13:13; real-data checks pass (annual volumes of complete years kept; within-year r with the deficit 0.96 → 0.61) |
| "Prose saying that checks passed needs to identify the exact snapshot" | Holds | The new snapshot check (below) ties the land-use inputs to one verified state; notes give commits and file hashes |
| **P1** land-use inputs missing from run identity; LSTM could mix seeds from different land-use inputs | **Holds** (confirmed in `src/models/lstm.py`: the fingerprint hashes settings and input names, not values) | Each land-use panel now has an identity record (`<panel>.json`: variant, content hash of its land-use columns, index file, crop-class table, RPG editions, base panel); the hash is recomputed and compared on every use (`features.land_use_identity`); the LSTM puts it into its fingerprint, so a folder made from other land-use inputs stops; LightGBM and LSTM manifests record it; the Kaggle bundle ships the records. Kept off for the runs without land use, whose fingerprints must not change |
| (found while fixing P1) | **A regression of mine**: adding `--land-use` to `lstm.py` put `land_use: None` into every LSTM fingerprint. No fingerprinted LSTM run exists on the laptop, but a Kaggle kernel resuming EA-LSTM folds started with the older code would have stopped | An unset `--land-use` is now left out of the fingerprint; tested against the fingerprint the older code computes (`tests/test_land_use_inputs.py`) |
| **P2** the crop-area cache key lacks coordinates | **Holds** | The key now holds each well's coordinates, the CRS, the buffer and a calculation version (`CALC_VERSION`); the cache was rebuilt |
| **Spec 1** no prescribed comparison report | Held at the snapshot (`src/analysis/land_use_test.py` was written minutes later, before any run) | Paired contrasts on vs without with strict support, Holm over the two models per metric, placebo, wide, frozen and aquifer-group rows outside the family |
| **Spec 2** LU-4 must wait for a complete, rebuilt snapshot | **Holds**; at the snapshot 2018 and 2025 were still downloading and the area cache had 4 editions | All 11 editions clipped and used for their own year; `tests/test_land_use_inputs.py` checks the edition/lag inventory, the current schema, the four panels against the current index and their records. CLAUDE.md requires it to pass before the push |
| A complete two-well vertical path as the next milestone | Agreed; it is LU-6 of the road | Unchanged order: 12.6 → 12.7 → 12.8 with the land-use rules, then the two-well example |
| The placebo claim is too strong; one permutation cannot separate geography, registration and actual change | **Holds** | Wording narrowed in `src/dataset/crop_demand.py`, `land_use_test.py` and the analysis plan; **Assil added a "frozen" variant** (the 2019 crop areas in every year) before any run; claims per contrast fixed in §14 item 13 |
| Heudorfer et al. motivate identifier controls, not this design | Holds | Wording changed in the analysis plan |
| Keep demand, withdrawals and recharge distinct; no double counting | Holds | Written into §14 item 13 (Phase 4): crop demand needs a stated pathway before it gets a sign, unknown sources stay unknown, no withdrawal counted twice (reconstruction 3 already follows the crop calendar); to settle at Gate 3 |
| Proportional conclusions | Agreed | No change needed; the claim limits above follow it |
| `analysis_plan.md` still calls land use static (RPG 2016/2023) | Holds | Updated |
| `roadmap.md` has laptop training and "Kaggle is unavailable" | Holds | Updated to the rule of 2026-10-24 (no training on the laptop; Kaggle CPU; Colab GPU) |
| The subject-coverage table reads like a delivery plan | Holds | CLAUDE.md §1b has a dated status column (done / in progress / not started) |

## 2. Decisions (Assil, 2026-10-25, before any land-use run)

1. **Frozen variant** added to the pre-registered test: `--land-use frozen`, the main index
   with the crop areas of the 2019 edition in every year. Only "on beats frozen" supports a
   statement about the change of crop areas over the years.
2. A positive main contrast is worded "incremental predictive information from the demand
   index".

## 3. State after the answer

- Land-use inputs: RPG 2015–2025, crop-thirst index with main, wide, placebo and frozen
  columns, four panels with identity records; `tests/test_land_use_inputs.py`,
  `tests/test_crop_demand.py`, `tests/test_pumping_cropcal.py`, `tests/test_run_cache.py`,
  `tests/test_pumping_conservation.py` pass.
- LU-4 runs: not started. Launch order in CLAUDE.md §7 (after Kaggle kernel 5 is pulled; the
  snapshot check first).
