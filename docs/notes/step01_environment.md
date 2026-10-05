# Step 1: Repository and environment

**Date:** 2026-10-05 · **Status:** done

## What was done

1. Read the project documents in `Documents/`:
   - `sujet.docx` / `sujet.pptx`: the official PFE subject (in French).
   - `PRIMA 2023 SaveWater description.docx`: the funded SAVE Water proposal.
     Our PFE contributes to its *objective 3* (impact of land-use change on
     hydrology), *objective 4* (big data / AI) and *objective 8* (GIS
     dashboard).
   - `guide.docx.pdf`: the lab's "young researcher" guide (databases, Zotero,
     how to read papers, monthly progress report).
2. Checked the tools: git 2.55, Python 3.13.15. `uv` is not installed, so we
   used the standard `python -m venv .venv`.
3. Installed `pandas geopandas pyogrio shapely pyarrow requests matplotlib
   py7zr` and pinned the exact versions in `requirements.txt`.
4. Created the folder layout from CLAUDE.md §5, a `.gitignore` and the data
   log `data/README.md`.

### How to recreate the environment on any machine

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows (Git Bash)
# .venv/bin/python -m pip install -r requirements.txt     # Linux / macOS
```

Run scripts with the venv interpreter, e.g. `.venv/Scripts/python -m src.ingest.hubeau_piezo`.

## Why

- **A virtual environment (`.venv`)** isolates this project's packages from
  the rest of the laptop. Two projects can then need different pandas
  versions without breaking each other.
- **Pinned versions (`requirements.txt`)** make the results reproducible. A
  jury member, or you in six months, can reinstall exactly the same thing.
  This is part of the rule "nothing is done until it runs from cold".
- **The folder layout** separates three kinds of data:
  - `raw/`: what the internet gave us, never modified.
  - `interim/`: cleaned versions.
  - `processed/`: model-ready datasets.

  If a cleaning step has a bug, you fix the code and regenerate. You never
  need to re-download, and you never lose the original.
- **Data is never committed.** It is large, it can be re-downloaded, and git
  is bad at big binary files. `data/README.md` records exactly how to get it
  back. That matters here: the first run's data was lost, and this log is how
  we rebuild it.

## What to consider

### ⚠️ Windows Smart App Control blocked the newest packages

The first install failed with
`ImportError: DLL load failed ... An Application Control policy has blocked this file`.

Your laptop has **Smart App Control** turned on in enforcement mode. This
Windows 11 security feature refuses to run compiled files (`.dll`, `.pyd`)
that Microsoft's cloud doesn't know yet. Brand-new package releases have no
"reputation" yet, so they get blocked:

| Package | Latest (blocked) | Pinned (works) |
|---|---|---|
| pandas | 3.0.6 | **2.2.3** |
| pyarrow | latest | **18.1.0** |
| pyogrio (bundles GDAL) | 0.13.0 | **0.10.0** (GDAL 3.9.1) |
| numpy | 2.5.x | **2.2.6** (pandas 2.2.3 needs < 2.3) |

Older releases have been installed by millions of people, so Windows trusts
them. They are fully sufficient for this project.

**Consequences for you:**

- **Don't run `pip install --upgrade` blindly.** If a future package fails
  with "Application Control policy has blocked this file", pin an older
  version of it.
- **pandas 2.2 vs 3.0:** tutorials written for pandas 3 may use
  copy-on-write behaviour by default. Our code targets pandas 2.2.
- **Leave Smart App Control on.** Turning it off is possible, but Windows
  can only turn it back on after a full reset. Pinning versions is the
  safer fix.
- The heavy packages coming later (PyTorch, PyTorch Geometric, rdflib,
  pyshacl, earthengine-api) may hit the same problem. Plan time for it.

### Other notes

- **Hardware.** The MX330 GPU has only 2 GB of memory. It is fine for
  plotting, but the GNN in later steps will probably train on CPU or in
  Google Colab. A graph of about 34 piezometers is small, so the CPU should
  be enough.
- **Mains power only.** Every download script caches per file and can be
  restarted after a crash or power cut without starting over.
- **Pre-existing `.gitignore`.** It ignored every hidden file (`.*`). We kept
  that rule and added `!.gitkeep`, so the empty folders `reports/figures/`,
  `notebooks/` and `docs/literature/` can exist in git.
- **The subject vs CLAUDE.md design decisions.** The subject document
  mentions PROMPT/OntoMerge for alignment and SWRL for rules. CLAUDE.md §3
  replaces them with **OntoAligner** and **SHACL** (more recent and better
  maintained, and SHACL ships with GeoSPARQL 1.1). Be ready to justify this
  substitution to your supervisor; it should go in the thesis's "choix
  méthodologiques" section.
- **Monthly progress report.** The lab guide recommends one per month. These
  notes plus `data/README.md` are the raw material for it.
