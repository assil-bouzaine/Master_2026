# Scripts behind `docs/feedback.md` (2026-10-20)

Exploration only, kept so the numbers of the review can be traced. They read
`results/v2/` and `data/processed/dataset_v2/` (paths are absolute to this laptop).

- `diag.py`: sub-period NSE, error decomposition, out-of-range share, KGE datum check
  (now part of `src/models/evaluate.py` and `src/analysis/baseline_report.py`)
- `diag2.py`: plain pumping by year, pumping–deficit collinearity
- `bnpe2024.py`: first look at BNPE 2024 (superseded by the 2026-10-20 snapshot and
  `src/dataset/bnpe_v3.py`)

The knowledge-graph pre-check became `src/analysis/kg_precheck.py`.
