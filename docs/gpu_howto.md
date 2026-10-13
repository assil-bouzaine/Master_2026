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
