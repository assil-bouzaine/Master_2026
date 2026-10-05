"""Project-wide paths and constants. Import from here instead of hard-coding paths."""
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
