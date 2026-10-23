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

## Kaggle (from 2026-10-20, after the Camber allowance ran out)

Kaggle gives a weekly GPU quota (`kaggle_gpu.py quota` shows it) and runs a pushed kernel
**in the background**: the laptop can be off, which matters with its dead battery. Sessions
stop at 12 h, so the runner stops cleanly after 11 h and a new push resumes.

**Once (Assil):** a Kaggle account, phone-verified (Settings → Phone verification; needed
for GPU and internet), then in the Claude Code prompt `! .venv/bin/kaggle auth login`
(browser login, no key file to handle). CLI: `kaggle` 2.2.4 in `.venv` (a tool, not in
`requirements.txt`).

```bash
.venv/bin/python scripts/kaggle_gpu.py push      # bundle -> private dataset, kernel starts
.venv/bin/python scripts/kaggle_gpu.py status    # queued / running / complete / error
.venv/bin/python scripts/kaggle_gpu.py log       # execution log of the latest run
.venv/bin/python scripts/kaggle_gpu.py pull      # finished runs -> results/v3/<run>, rescored
.venv/bin/python scripts/kaggle_gpu.py push      # again, if the log says "push again"
```

- `push --steps "a b | c d"`: chains separated by `|` run in parallel, one GPU each (the T4
  machine has two T4s; quota counts session hours, not GPUs). Default: EA-LSTM tuning +
  regimes + Taccari default on GPU 0, Taccari tuning + regimes on GPU 1.
- The kernel (`scripts/kaggle_run.py`) first builds the venv with the pinned packages, then
  runs `tests/test_ealstm.py` on the GPU; if the cuDNN path does not match the loop, the
  EA-LSTM steps are dropped (check the log).
- `pull` keeps the whole output in `results/v3/_kaggle/output`; the next `push` ships it
  back as `state.zip`, so finished seeds, trials and folds are not recomputed.
- **T4, not P100:** recent PyTorch CUDA builds no longer include kernels for Pascal GPUs
  (P100), so the P100 may fail with the image's PyTorch.
- Datasets are created with `-t` (`--keep-tabular`): by default Kaggle converts uploaded
  tables to CSV.
- **Phone verification is required**: without it Kaggle silently runs the kernel on a CPU
  (the job's log shows `CUDA available: False`; the runner then stops at once). On
  2026-10-20 the verification SMS did not arrive on Assil's Tunisian number.
- EA-LSTM no longer needs a GPU: with the fused kernel it runs ~55 s/epoch on the laptop
  (`scripts/run_cpu.sh` steps `ealstm_tune`, `ealstm_regimes`). Taccari does (163 s/epoch on
  the laptop).

## Google Colab (from 2026-10-23; Kaggle dropped)

Free T4 GPU and no phone check: a Google account is enough. Sessions are interactive: the tab
must stay open (laptop on), Colab can stop a session without warning, and a GPU is not always
available. `scripts/colab_run.py` keeps the work resumable: it runs on the session's local disk
and copies the results to Google Drive (`MyDrive/pfe_colab/results_gpu`) every 5 min and when
it stops. Notebook: `pfe_v3_gpu.ipynb` in Assil's Drive (Colab Notebooks).

**First time (done 2026-10-23):**
1. Laptop: `PFE_DATASET=v3 .venv/bin/python scripts/make_gpu_bundle.py`. The Chrome
   extension uploads at most 10 MB per file, so split the zip (in the scratchpad):
   `split -b 7000000 -d gpu_bundle.zip gpu_bundle.zip.part`.
2. Colab: new notebook, Runtime > Change runtime type > **T4 GPU**. Upload the parts through
   the Files panel's "Upload to session storage" input (the extension cannot reach the input
   of `files.upload()`: cell outputs are cross-origin iframes), then
   `!cat /content/gpu_bundle.zip.part0* > /content/gpu_bundle.zip && md5sum /content/gpu_bundle.zip`
   and compare with the laptop's `md5sum gpu_bundle.zip`.
3. Mount Drive (**Assil** clicks "Connect to Google Drive", then Allow), then
   `!mkdir -p /content/drive/MyDrive/pfe_colab && cp /content/gpu_bundle.zip /content/drive/MyDrive/pfe_colab/`.

**Every session (also after a stop):** open the notebook (T4 runtime), then two cells:

```python
from google.colab import drive; drive.mount('/content/drive')      # Assil: Allow
!unzip -oq /content/drive/MyDrive/pfe_colab/gpu_bundle.zip -d /content/pfe && python /content/pfe/scripts/colab_run.py
```

Default steps: `taccari tune:taccari regimes:taccari` (set `STEPS` to change them). The cell
shows a short output (the first epoch of each seed, which gives its time, then seed and trial
results); the full log is `results_gpu/run_colab.log` on Drive.

**Bring the results back:** interrupt the cell (it saves to Drive when it stops), then

```python
!python /content/pfe/scripts/colab_run.py zip
from google.colab import files; files.download('/content/results_colab.zip')
```

and on the laptop `.venv/bin/python scripts/colab_pull.py ~/Downloads/results_colab.zip`
(copies finished runs and tuning studies to `results/v3/`, rescores them). A zip of the Drive
folder `pfe_colab/results_gpu` (Drive > Download) works too. Then re-run the sweep cell.

**Lessons (2026-10-23):**
- Colab image: Python 3.13, torch 2.11.0+cu130. The pins go to `/content/pins` (`PIN_TARGET`,
  as on Kaggle); about 1 min per session.
- `tests/` had no `__init__.py`, so it was only a namespace package, and a regular `tests`
  package elsewhere on Colab's path won (`No module named tests.test_taccari`).
  `tests/__init__.py` is now in the repo and the bundle.
- **Taccari default on the T4: 10 s per epoch** (laptop 163 s), so its ~80 runs need a few
  GPU-hours, not ~100 h.
- After a code change, rebuild the bundle and upload it again (or add the changed file to the
  Drive copy with `zip`), so that the next session unzips the new version.
