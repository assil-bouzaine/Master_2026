# Astra review of the groundwater simulation project

Reviewed commit `0171297` on 18 November 2026 against the project's analysis plan, using dataset v4. **The first correction I would make is to the twin's pumping intervention.** It changes facilities assigned to other wells, so a model can get credit for responding to the wrong facility. The Phase 4 reporter also has two paths by which an incomplete experiment can produce a confirmatory result.

All **34 repository test modules** exited successfully in a temporary checkout with the local data. The examples below are additional checks using saved results, small fixtures, or local simulations of the runners. The review did not require a new cloud training run.

## Spec

### 1. High — The pumping intervention changes the wrong facilities for each well

Score 5 calls for cutting each well's true pumping facilities by 20%. The implementation takes the **union across wells** and cuts that set for every prediction. In v4 base-world seed 0, all 33 core wells had extra active facilities cut in distance arm C. At `10915X0316/F3`, the intended cut covered 47 facilities. Arm C also saw reductions at **385 other facilities**. This changes the fitted response being compared with the known response. [Intervention implementation](src/models/twin.py#L459) · [Analysis plan](docs/analysis_plan.md#L1041)

**Correction.** Build the cut from each target well's true source IDs and score that target under both the fitted and true models. This can be batched by target. Check it on two wells with disjoint true facilities and a cross-link in the fitted graph. Recompute Score 5 for the affected worlds before using recovery of the intervention to compare protocols.

### 2. High — A test-period river observation enters validation through a 59-week gap

`interpolate(limit=8)` fills the first eight entries of a gap of any length. Gauge `Y047403001` had 59 consecutive missing weeks from 12 September 2021 through 23 October 2022. Its first missing validation week receives a log-discharge of **1.113916** using the observation on 30 October 2022. The median for that calendar week in the declared 2005–2019 training window is **1.011081**. The fallback calculation also includes warm-up dates and interpolated values. This input feeds the panel and the routed river stress. [Gap filling](src/models/features.py#L71) · [Routed river input](src/models/routing.py#L197) · [Declared gap rule](docs/analysis_plan.md#L288)

**Correction.** Identify each complete missing run before filling it. Interpolate only internal runs of at most eight weeks. Fill longer runs from observed discharges between both training bounds. Change the panel cache identity and rebuild the affected panels and fits. A regression check should vary the October 2022 observation and require the September 2021 fill to stay fixed.

### 3. High — A one-start prediction can be reported as a ten-start Phase 4 result

The response CLI averages exactly the seeds requested on its most recent invocation. The report independently counts all seed files left in the folder and accepts the saved metrics. In a copy of the ten-start `resp_free` run, rerunning with `--seeds 0` changed median drought RMSE from **0.700929 to 0.713301 m**. The report still returned **10 starts** for its uncertainty band. Its effect estimate and band now describe different ensembles. [Ensemble writer](src/models/response.py#L629) · [Saved metrics](src/analysis/arms_report.py#L112) · [Band calculation](src/analysis/arms_report.py#L131)

**Correction.** Record the exact seed IDs used for each aggregate. Before classifying a Phase 4 contrast, verify that both aggregates and both bands use the declared ten starts, in every applicable fold. Rebuild the aggregate from those files when possible. Keep partial aggregates available as progress output.

### 4. High — Missing contrasts make the Holm significance threshold easier to pass

Each confirmatory family has two declared tests. An unavailable run removes its test before Holm adjustment. With a raw p-value of 0.030, an interval excluding zero and an effect outside both noise bands, the reporter classified the available result as **detected**. Supplying the second planned test with p = 0.40 changed the first adjusted p to **0.060** and the verdict to **undecided**. The first result itself never changed. [Missing-run handling](src/analysis/arms_report.py#L247) · [Holm adjustment](src/analysis/arms_report.py#L224) · [Declared families](docs/analysis_plan.md#L888)

**Correction.** Keep the declared family membership for each regime and reconstruction. Show incomplete families as pending until all their p-values are available. If interim adjusted values are needed, account for every planned test conservatively and label the interim result. Update the existing test that expects a missing member to reduce the family size. [Current test](tests/test_arms_report.py#L73)

### 5. High — Score 6 reports a median in a column labeled as a share of worlds

Each world gets a 0/1 flag. The report passes those flags to its ordinary median-and-quantiles formatter. **Four flagged worlds out of twenty** produce `0.000 [0.000, 1.000]`, although the share is **20%**. The reported share can conceal how often an accurate model recovers the wrong pumping contribution. [Flag creation](src/analysis/twin_report.py#L52) · [Summary statistic](src/analysis/twin_report.py#L60) · [Score 6 table](src/analysis/twin_report.py#L226)

**Correction.** Report the number flagged, the number evaluable, and their ratio for each arm and cell. The saved world scores are sufficient to regenerate this table. For the planned shortcut-test detection and false-alarm rates, retain separate counts conditioned on whether the world meets the wrong-reasons definition. [Score 6 definition](docs/analysis_plan.md#L1042)

### 6. High — The twin report issues decisions on incomplete grids and exact ties

Two fixture cells outside the four cells designated to represent the real aquifer produced “no bracket cell pays” alongside “0 bracket cells present.” On a complete 12-cell fixture with **identical** recovery and accuracy for both protocols, the report credited `free` with **12 wins** and recommended it for Gate 3. Python's `min` and `max` return the first protocol on ties. The local grid also contained only **206 of 240** planned world files at review time, so interpreting a partial grid is a realistic path. [Bracket decision](src/analysis/twin_report.py#L128) · [Protocol choice](src/analysis/twin_report.py#L147) · [Worlds required](docs/analysis_plan.md#L1046)

**Correction.** Display partial cell counts descriptively. Require the relevant cells and paired world IDs before issuing the bracket conclusion or protocol recommendation. Count tied cells separately and recommend a protocol only when it has a strict majority and meets the accuracy rule. Test both zero bracket cells and a six-to-six split.

### 7. Medium — Saved response predictions use a different scale from their contributions

The response model divides its prediction by a training standard deviation floored at 0.001 m. The shared ensemble writer multiplies it by the original standard deviation. For `10984X0003/AIGUAN`, the saved seed-0 contributions and intercept give a maximum absolute anomaly of **0.007088 m**. Decoding the same seed gives **1.60 × 10⁻¹² m**. AIGUAN is outside the core set, which limits the impact on the published core scores. [Seed encoding](src/models/response.py#L403) · [Ensemble decoding](src/models/lstm.py#L323) · [Report decoding](src/analysis/arms_report.py#L88)

**Correction.** Store response predictions in metres, or persist the effective scale and reuse it in every response decoder, including fold assembly and reporting. Verify that a saved seed's head equals the training mean plus its intercept and contributions at each week.

### 8. Medium — The reported hydraulic lags differ from the model's impulse response

The exported mean lag is `a × n`, the mean of a continuous Gamma distribution. The fitted model applies a finite set of normalized weekly weights. In saved `resp_free` seed 0, PONT's reported recharge lag is **17.31 weeks**, while its implemented mean delay is **16.78 weeks**. The largest recharge discrepancy across wells in that start is **75.1 days**. The pumping peak comparison likewise uses the continuous mode. These values feed the comparison with physical transit times. [Kernel implementation](src/models/response.py#L237) · [Parameter export](src/models/response.py#L419) · [Physical comparison](src/analysis/ladder_report.py#L151)

**Correction.** Compute the implemented mean as the sum of each lag index times its normalized weight, and find the peak with the index of the largest weight. Regenerate the lag tables from the saved parameters. A unit impulse gives an independent check for both quantities.

### 9. Medium — Duplicate predictions can pass the 26-week eligibility threshold

The scorer counts rows after joining predictions to observations. Duplicating **13 distinct** drought-week predictions for `10795X0028/CARSTE` produced `n_weeks = 26` and a score. Passing the same 13 predictions once produced an unrelated `KeyError: 'code_bss'` because the empty metrics table had no columns. A repeated row can also give that week extra weight in RMSE. [Prediction join](src/models/evaluate.py#L123) · [Eligibility and empty result](src/models/evaluate.py#L150)

**Correction.** Validate uniqueness of `(code_bss, week, task, horizon)` and of the observation and benchmark keys before joining. Count distinct weeks, and return an empty table with the documented schema when no group qualifies. Test both the duplicated and the legitimate short input.

## Standards

### 10. High — Twin resume silently accepts worlds from a different experiment

`run_cell` constructs the requested configuration and then skips any existing world JSON solely because its path exists. In a temporary copy, requesting another export, the shared model, 17 steps and start 9 returned successfully while preserving the old free/pooled settings, 4,000-step budget and starts 0 and 1. Subsequent missing worlds could use the new settings. The report groups the resulting rows without checking their saved configuration or export. [Resume check](src/models/twin.py#L517) · [Report loader](src/analysis/twin_report.py#L36)

**Correction.** Give each cell a reproducible identity covering the generator, relevant input and export hashes, arms, fit settings, starts and step budget. Verify it before skipping or appending a world, and again when aggregating. Existing JSON contains configuration and source metadata that can be checked before regenerating anything.

### 11. High — Kaggle can report successful completion after all workers fail

Running the shell dispatcher locally with `PY=/bin/false` and `STEPS=twin_grid` returned **exit 0** after all four workers failed. The foreground `naive` step also returned 0 after logging its failure. A bare `wait` loses individual worker failures, the shell absorbs foreground errors, and the Python wrapper only logs the shell status. This makes a failed job look ready to pull. [Parallel dispatch](scripts/run_v4_cpu.sh#L75) · [Shell exit](scripts/run_v4_cpu.sh#L94) · [Python wrapper](scripts/kaggle_cpu_run.py#L172)

**Correction.** Collect each worker PID and exit status, finish independent steps, save completed work, and propagate a failure through both entry points. Give an intentional time-budget stop a distinct resumable status. An injected failing worker should make the overall job fail.

### 12. High — Pulling a later Kaggle session can discard the only copy of partial work

The remote runner exports only the run directories touched in that session. The local pull deletes the previous download **before** fetching the new output. It copies complete predictions and twin worlds into the project, while partial baseline seeds can remain solely in the download folder. Two simulated pulls containing different unfinished runs left only the second run available for the next resume bundle. A download failure also occurs after the previous copy has been deleted. [Remote save](scripts/kaggle_cpu_run.py#L122) · [Local pull](scripts/kaggle_cpu.py#L201) · [Resume bundle](scripts/kaggle_cpu.py#L143)

**Correction.** Download into a new staging directory, validate it, then merge all completed seed, fold, well and world artifacts into cumulative local state. Build the next resume archive from that state. Verify that two disjoint partial pulls and one failed pull preserve the first run's work.

### 13. High — The offline CPU bundle omits inputs required by Phase 4

A locally generated CPU archive contained the exported graph edges but omitted `data/raw/safran/grid_cells_66.parquet` and `data/interim/pumping_weekly_cropcal_v4.parquet`. The baseline arm calls `export.tables()`, which reads the grid even though this caller discards it. Every arm using reconstruction 3 opens the crop-calendar file. Both are present in the working project, so local tests pass while a clean offline session lacks them. [Bundle contents](scripts/kaggle_cpu.py#L127) · [Baseline loader](src/models/routing.py#L65) · [Grid read](src/kg/export.py#L86) · [Reconstruction 3](src/models/routing.py#L126)

**Correction.** Include the crop-calendar table and either package the grid or remove the baseline loader's unused dependency on it. Exercise baseline reconstruction 1 and each arm's reconstruction 3 from an extracted bundle using only its packaged files.

### 14. Medium — Concurrent twin workers can overwrite each other's completion records

The grid dispatches four processes into the same cell directories. Each manifest update reads, modifies and overwrites the same JSON file. When two local writers were synchronized after reading the previous state, both returned successfully and the final manifest recorded **one of two** completed IDs and only one session. The per-world files can survive while their provenance record is incomplete. [Concurrent workers](scripts/run_v4_cpu.sh#L77) · [World completion](src/models/twin.py#L540) · [Manifest update](src/models/manifest.py#L86)

**Correction.** Serialize the complete read–merge–write operation per cell and publish through atomic replacement, or write immutable per-worker records and derive the manifest from them. A two-worker test should require both IDs and both session records.

### 15. Medium — A clean baseline run writes missing forecast skill scores

`naive.main()` writes and evaluates persistence before it writes anomaly persistence, the benchmark used to score forecasts. With an empty results directory, **0 of 1,317** persistence metric rows had a skill value. Rescoring the identical predictions after the command finished populated **all 1,317**. The four-week core drought median changed from missing to **−0.1044**. [Run order](src/models/naive.py#L51) · [Benchmark loading](src/models/evaluate.py#L110)

**Correction.** Write the predictions for all three baselines first, then score them. Verify that a first invocation in an empty directory and a subsequent rescore produce identical metrics.

### 16. Medium — A Chronos smoke run can silently become the full forecast

The cross-learning mode caches all wells in one file under a fixed run name. In a three-well fixture with a stub predictor, `--mode xl --wells 1` wrote one well. A subsequent unrestricted `--mode xl` made **zero prediction calls** and again published only that well. Fine-tuning also reuses a fixed checkpoint path across well subsets and step budgets. [Well selection](src/models/chronos2.py#L112) · [Checkpoint reuse](src/models/chronos2.py#L120) · [Cross-learning cache](src/models/chronos2.py#L129)

**Correction.** Give smoke runs separate output directories. Persist and verify the selected well IDs, model revision and fit settings before reusing a checkpoint or predictions. Cross-learning shares information across wells, so a changed well set requires rebuilding the batch.

### 17. Medium — An offline bibliography refresh can erase all 104 references and exit successfully

The raw BibTeX cache is intentionally excluded from Git. In a fresh temporary checkout, `python paper/tools/fetch_bib.py --offline` listed the missing identifiers, replaced the tracked **104-entry** bibliography with a **zero-byte file**, and returned **exit 0**. A partially populated cache can similarly replace a complete bibliography with a subset. [Refresh entry point](paper/tools/fetch_bib.py#L205) · [Cache policy](paper/README.md)

**Correction.** Verify coverage of the requested identifiers before replacing `refs.bib`. On an incomplete refresh, preserve the existing complete output, list the missing records, and return a distinguishable status. If a partial export is useful, require an explicit destination for it.

The review found **nine experimental or scoring issues** and **eight reproducibility or tooling issues**. The per-well intervention changes the scientific quantity being measured. The Kaggle pull and resume defects can destroy partial work or mix incompatible worlds before that quantity is reported.
