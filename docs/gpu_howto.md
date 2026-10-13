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
