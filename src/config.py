"""Project-wide paths and constants. Import from here instead of hard-coding paths."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DATA = ROOT / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"
FIGURES = ROOT / "reports" / "figures"

DEPARTEMENT = "66"  # Pyrénées-Orientales
CRS_WGS84 = "EPSG:4326"
CRS_L93 = "EPSG:2154"  # Lambert-93, metres: use for distances and areas

# Common analysis window (CLAUDE.md section 7, Step 4)
WINDOW_START = "2016-01-01"
WINDOW_END = "2025-12-31"

# Model-ready dataset version and its results folder (CLAUDE.md section 7, step 10).
# v1: plain wells, training from 2012 (Phase 2). v2: all dept-66 wells, training
# from 2005, pumping over the whole departement. Select with PFE_DATASET=v1|v2.
DATASET = os.environ.get("PFE_DATASET", "v2")
DATASET_DIR = PROCESSED / f"dataset_{DATASET}"
# PFE_RESULTS overrides the results folder (relative to the repo root or absolute);
# used on Camber, where folders uploaded from the laptop are read-only for the job.
RESULTS_DIR = (ROOT / os.environ["PFE_RESULTS"]) if os.environ.get("PFE_RESULTS") \
    else ROOT / "results" / DATASET
