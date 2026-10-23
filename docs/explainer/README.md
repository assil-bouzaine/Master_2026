# The water under the Roussillon: a plain-words guide

Open `index.html` in a browser (double-click it, or `xdg-open docs/explainer/index.html`).
It works offline. It needs no server and no internet.

What it covers, in simple words with pictures:
1. the question
2. the place and the underground
3. the data we collected
4. the weekly table
5. the contest of rival models
6. the four data versions
7. the two reviews
8. the knowledge map
9. the future model and its tests
10. the timeline
11. every decision, made or waiting
12. a searchable word list

Files:
- `index.html`: the chapters and the drawings. The text is written by hand: update it when a step finishes.
- `style.css`, `app.js`: layout, interactions and charts (plain SVG, no library).
- `data.js`: every number drawn in a chart. It is generated, so do not edit it by hand:
  `.venv/bin/python -m src.analysis.explainer_data`
  It reads `data/processed/dataset_v1–v4`, `results/v3/*/metrics_summary.csv` and
  `data/interim/pump_unit_attribution_eval.json`.

The colours of the data were checked with a colour-blindness validator, in light and in dark
mode. The three layer colours are the same everywhere in the guide:
- blue: river gravel layer
- aqua: deep sand-and-clay layers
- orange: karst
