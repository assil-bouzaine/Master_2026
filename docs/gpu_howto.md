# Running the neural baselines on a free GPU (Colab, Kaggle or Camber)

The laptop is enough for development and single runs. Send the **sweeps** to
a GPU: the LSTM and ST-GNN with 5 seeds, and later the ablation grid. The
code uses the GPU automatically when one exists (`DEVICE` in
`src/models/lstm.py`).

## 1. On the laptop: make the bundle

```bash
.venv/bin/python scripts/make_gpu_bundle.py      # creates gpu_bundle.zip (~10 MB)
```

## 2. On the GPU machine (Colab notebook cells shown; same on Kaggle/Camber)

```python
# upload gpu_bundle.zip (Colab: Files panel, or mount Google Drive), then:
!unzip -q gpu_bundle.zip -d pfe && cd pfe
# keep the machine's CUDA torch: install everything except our CPU torch pin
!grep -v '^torch==' requirements.txt > req_gpu.txt && pip install -q -r req_gpu.txt
import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))
```

```python
!cd pfe && python -m src.models.lstm            # 5 seeds, resumable
!cd pfe && python -m src.models.stgnn           # 5 seeds, resumable
```

## 3. Bring the results back

Copy `pfe/results/lstm/` and `pfe/results/stgnn_distance/` (the
`seed_*.parquet` files and `predictions.parquet`) into the laptop's
`results/`, then score them with the same code as everything else:

```bash
.venv/bin/python -m src.models.evaluate lstm stgnn_distance
.venv/bin/python -m src.models.evaluate --compare
```

## Tips

- **Free Colab sessions stop without warning.** Each seed is saved as soon
  as it finishes, so re-running the same command resumes. On Colab, work
  inside Google Drive (`/content/drive/MyDrive/pfe`) so files survive a
  disconnect.
- **Use the free hours on sweeps, not on debugging.** Debug on the laptop
  with `--seeds 99 --epochs 2`.
- **Record which GPU and how long** each sweep took. The paper's
  reproducibility section needs it.

---

## Camber (checked 2026-10-13 against docs.cambercloud.com)

**What Camber offers:**
- GPU = NVIDIA L4 (24 GB). The `XSMALL` GPU node (1 L4, 8 CPU, 32 GB) costs
  **1.5 credits/hour** (1 credit = 1 US$).
- New accounts get **100 free credits**. The GitHub Student Pack offer is
  described as 200 CPU hours + 75 GB storage + 300 LLM queries; GPU hours
  are not mentioned, so **GPU time uses credits**.
- Credits are consumed only while a job is `RUNNING`.
- Our ST-GNN (5 seeds) + the rest of Chronos-2 should take a few GPU-hours
  at most, i.e. **a few credits**. Check the balance in the Camber web app
  before and after.

**What the Camber MCP can and cannot do:**
- It is real: `claude mcp add --transport http --scope user --client-id
  IPUNLiAS5zj2ZS8B --callback-port 17653 camber-mcp
  https://camber-mcp.cambercloud.com/mcp`, then `claude mcp login
  camber-mcp`.
- Its tools only manage Camber AI agents and teams (`agents_chat`,
  `agents_create`, `teams_list`…). **It cannot upload files or submit
  compute jobs**, so the GPU run is done with the CLI + the Camber web app
  below.

### Step 1: install the CLI and log in (once, on the laptop)

```bash
curl -sL https://cli.cambercloud.com/install-v2.sh | bash
camber login          # opens the browser
camber me             # shows your username = <user> below
```

### Step 2: upload the bundle (from the project folder)

```bash
.venv/bin/python scripts/make_gpu_bundle.py
camber stash cp gpu_bundle.zip stash://<user>/pfe/
```

### Step 3: start the GPU job (in the Camber web app)

Open app.cambercloud.com → JupyterLab. Your Stash is the notebook's file
system. In a notebook cell:

```python
!cd ~ && mkdir -p pfe && cd pfe && unzip -oq gpu_bundle.zip   # adjust if the zip sits elsewhere
!ls ~/pfe                                                       # should show src/ scripts/ data/ results/
```

Then submit the job on one L4 GPU:

```python
import camber
help(camber.mpi.create_job)        # check the current signature first (docs are partial)
job = camber.mpi.create_job(
    command="cd ~/pfe && bash scripts/run_gpu.sh",
    node_size="XSMALL",
    num_nodes=1,
    with_gpu=True,
)
job                                # shows job id and status
```

If `create_job` has changed, use Camber's assistant instead (documented
way to run code on a GPU node):

```
@nova Run "cd ~/pfe && bash scripts/run_gpu.sh" on an XSMALL node with GPU
```

The job writes its log to `~/pfe/results/gpu_run.log`. The first line says
`CUDA available: True NVIDIA L4` if the GPU was attached.

### Step 4: bring the results back (on the laptop)

```bash
camber stash cp -r stash://<user>/pfe/results/stgnn_distance ./results/
camber stash cp -r stash://<user>/pfe/results/chronos2 ./results/
camber stash cp stash://<user>/pfe/results/gpu_run.log ./results/
.venv/bin/python -m src.models.evaluate stgnn_distance chronos2
.venv/bin/python -m src.analysis.baseline_report
```

### If the job stops

Run Step 3 again. Finished seeds and wells are skipped, so nothing is
recomputed and few credits are wasted.

---

## What actually worked on Camber (2026-10-13)

- **CLI batch jobs are blocked on the free tier:** `camber job create` →
  "Job creation is not available on the free tier".
- **Use the interactive GPU node instead.** In the web app: start the
  **GPU · Xsmall** node → `</>` (top right) → **Open from Stash** → select
  `pfe/` → **Select**. A notebook opens in `/home/jovyan/pfe` (= your
  Stash).
- **Start the run detached** (from a notebook cell):
  `!setsid nohup bash scripts/run_gpu.sh > results/gpu_runN.log 2>&1 < /dev/null &`
- **Check progress** (from a notebook cell):
  `!ps aux | grep -E "[r]un_gpu|[s]rc.models"; tail -4 results/gpu_runN.log; nvidia-smi`
- **Bring results back** with `camber stash cp -r stash://assil0723/pfe/results/<run>/ results/<run>/`.
- **Press STOP on the node** when done (1.5 credits/hour while on).
- **Folders uploaded from the laptop are read-only for the job**
  (`Permission denied`). Write results to a fresh folder:
  `PFE_DATASET=v2a PFE_RESULTS=results_abl/v2a STEPS="stgnn lstm" bash scripts/run_gpu.sh`
  after `mkdir -p results_abl/v2a/_cache && cp results/v2a/_cache/panel.parquet results_abl/v2a/_cache/`.
- `run_gpu.sh` takes `STEPS` (any of `stgnn chronos2 lstm tune_lstm`).

---

## Dataset v3 sweep (from 2026-10-20)

`scripts/run_gpu.sh` now defaults to dataset v3 and runs one resumable sweep (steps can
be chosen with `STEPS="..."`):

| Step | What | Output run(s) |
|---|---|---|
| `lstm`, `stgnn`, `taccari` | default configurations, 5 seeds (comparability with v2) | `lstm`, `stgnn_distance`, `taccari` |
| `chronos2`, `chronos2_xl`, `chronos2_ft` | zero-shot, zero-shot with cross-learning, fine-tuned on train | `chronos2*` |
| `tune:<model>` | Optuna, 24 trials, validation only, then 5 seeds (lstm, ealstm, stgnn, taccari) | `<model>_tuning`, `<model>_tuned` |
| `regimes:<model>` | leave-wells-out (5 folds × 5 seeds), 25/50 % training data, refit on train+validation | `<model>_tuned_lwo`, `_f25`, `_f50`, `_refit` |

```bash
# laptop
PFE_DATASET=v3 .venv/bin/python scripts/make_gpu_bundle.py        # gpu_bundle.zip
camber stash cp gpu_bundle.zip stash://assil0723/pfe_v3/
# node (notebook cell), in /home/jovyan/pfe_v3
!unzip -oq gpu_bundle.zip && mkdir -p results_gpu
!PFE_DATASET=v3 PFE_RESULTS=results_gpu/v3 setsid nohup bash scripts/run_gpu.sh > results_gpu/run_v3.log 2>&1 < /dev/null &
# laptop, when finished
camber stash cp -r stash://assil0723/pfe_v3/results_gpu/v3/<run> results/v3/<run>
```

Order of the default steps = order of importance, so the node can be stopped early
without losing what matters most. Estimated L4 time: defaults and Chronos-2 ≈ 1 h,
each tuning 0.5–2 h, each regime set 0.5–3 h; the whole sweep ≈ 10–14 GPU-hours
(15–21 credits at 1.5/h). EA-LSTM is the slowest (Python loop over time steps), so it
comes last.

## Lessons from the v3 sweep (2026-10-20)

- **A folder created by `camber stash cp` is owned by root and read-only on the node**, even
  for `unzip`. Unzip into a folder the node creates itself:
  `!mkdir -p ~/pfe_v3_run && cd ~/pfe_v3_run && unzip -oq ~/pfe_v3/gpu_bundle.zip`.
  `/home/jovyan` is the Stash (persistent); `/tmp` is wiped when the node stops.
- **The CLI's view of the Stash lags the node's disk** (minutes). Check progress in a
  notebook cell; use the CLI to bring finished runs back.
- **Auto-stop:** start the sweep and the watcher together, so the node stops even if the
  laptop is off (`$!` is the sweep's PID; the watcher waits 10 min, then shuts the server):
  `!cd ~/pfe_v3_run && (STEPS="..." PFE_DATASET=v3 PFE_RESULTS=results_gpu/v3 setsid nohup bash scripts/run_gpu.sh >> results_gpu/run_v3.log 2>&1 < /dev/null & P=$!; setsid nohup python3 scripts/gpu_autostop.py $P 600 >> results_gpu/autostop.log 2>&1 < /dev/null &)`
  To change the plan, kill the watcher **first**, then the sweep (by PID, never with a
  `pkill -f` pattern that also matches your own shell).
- **Time per model on the L4:** LSTM and distance ST-GNN ≈ 1 min for 5 seeds; the Taccari
  graph needed ~45 s per epoch before the strided TCN (commit `b3a8b74`). Time one epoch
  of every new model before queueing its tuning.
- To patch code on a running node: upload to a new path (`.../pfe_v3_run/patch/`), copy it
  over from a notebook cell and compare `md5sum` (an overwrite through the CLI may not
  reach the node's copy).
- **The Student plan has a monthly GPU allowance, not a credit balance you can see on the
  node.** Check Account Settings → Billing & Usage ("GPU usage x % used", renews on the 13th)
  before a long sweep (the Personal Usage page crashed on 2026-10-20). When the allowance
  runs out the platform stops the node with no message in our logs (2026-10-20, 16:22 CET,
  after step 10 and ~4 h of the v3 sweep).
- **Never type long text into a notebook cell through the extension**: a 7 KB command froze
  the tab for minutes and was never run. Upload files (CLI or the Stash panel) and keep
  typed commands to one short line.
- EA-LSTM now runs with the fused LSTM kernel (cuDNN; commit `e09a482`, exact, 9–12× on
  CPU). Run `python -m tests.test_ealstm` first on any new GPU: it checks the cuDNN path
  against the explicit loop and times both.
