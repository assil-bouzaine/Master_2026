# CLAUDE.md — SAVE Water / LULC-Water PFE

Read this file at the start of every session. It is the project brief, the
rules, and the current task.

---

## 1. The project in one paragraph

Master's PFE (projet de fin d'études) by Assil Bouzaine, Master in Data Science
and Information Retrieval, ISAMM (Université de la Manouba). It contributes to
the SAVE Water project. Goal: a neuro-symbolic pipeline that predicts
groundwater risk in a Mediterranean aquifer. A LULC-Water ontology describes
land use, aquifers and water use. A heterogeneous spatio-temporal graph neural
network learns groundwater levels with ontology-derived constraints. The
outputs are explained in terms of the ontology.

Four phases:
1. Knowledge engineering: ontology reuse and alignment
2. Semantic land use from Earth observation
3. Knowledge-constrained spatio-temporal GNN
4. Ontology-grounded explanations

Scope is a **Master's, not a PhD**: one aquifer system and one target variable
(groundwater level), built end to end. Everything else is documented as future
work.

---

## 2. Study sites

| Role | Site | Notes |
|---|---|---|
| Primary | **Plaine du Roussillon**, Pyrénées-Orientales (dept 66), France | Chosen for open data on every layer |
| Secondary | Campo de Cartagena / Segura, Spain | Generalisation; later |
| Demo | Cap Bon or Kairouan, Tunisia | Transfer demonstration only; later |

---

## 3. Design decisions already made

Do not change these without asking Assil first.

- **Ontology alignment:** OntoAligner (ESWC 2025), not PROMPT or OntoMerge.
- **Rules and validation:** SHACL (GeoSPARQL 1.1 ships a validator), not SWRL.
- **Ontology architecture:** a network of ontologies linked by alignment axioms
  (the WHOW-KG pattern, Scientific Data 2025), not one merged file.
- **Ontologies to reuse:** GWML2, HY_Features, SOSA/SSN, GeoSPARQL, HILUCS,
  AGROVOC.
- **Earth observation:** AlphaEarth Satellite Embedding (64-d, 10 m, Google
  Earth Engine) instead of training a Sentinel classifier from scratch.
- **Explanations:** templated text generated from ontology triples. An LLM may
  polish fluency only and never invents content.
- **Validity check:** the model must be tested for reasoning shortcuts
  (Marconato et al., NeurIPS 2023). Satisfying the constraints is not proof
  that the model learned the right concepts.

---

## 4. Environment

- Windows 11 laptop: i5-1035G1, 16 GB RAM, GeForce MX330. Runs on mains power
  only, so save progress often and make long jobs resumable.
- Shell: Git Bash. Use `pathlib` for every path. Never hard-code `/` or `\`.
- Python 3.11+ in a project venv. Prefer `uv` (`uv venv`, `uv pip install`)
  for speed; fall back to `python -m venv` + pip if `uv` is unavailable.
- Pin dependencies in `requirements.txt`.
- Use `py7zr` to extract `.7z` archives, so 7-Zip is not needed on PATH.
- Use `pyogrio` to read geodata, and `pyogrio.list_layers()` to inspect a
  FileGDB or GeoPackage.

**Learned during the rebuild (October 2026):**

- **Interpreter.** `uv` is not installed. The venv is `.venv` (Python
  3.13), created with `python -m venv`. Run scripts with
  `.venv/Scripts/python -m src.<pkg>.<module>`. Set `PYTHONIOENCODING=utf-8`
  when printing French text.
- **Windows Smart App Control is ON** and blocks the DLLs of brand-new
  wheels ("An Application Control policy has blocked this file"). Working
  pins:
  - pandas 2.2.3
  - pyarrow 18.1.0
  - numpy 2.2.6 (< 2.3)
  - pyogrio 0.10.0 (GDAL 3.9.1)

  Never `pip install --upgrade` blindly. If a new package is blocked, pin an
  older release. Do not suggest turning Smart App Control off: Windows can
  only turn it back on with a full reset.
- **Hub'Eau prélèvements API.** `size=5000` got the connection reset, and
  then the whole hubeau.eaufrance.fr refused this machine for about 10
  minutes. Use `size=2000` there. `niveaux_nappes` works with 5000.
- **IGN Géoplateforme.** The `/resource/RPG` listing is paginated (35 pages)
  and returns HTTP 429 when requests come too fast; pause 1 s per page. RPG
  reference tables (crop code → group) live at
  `https://data.geopf.fr/annexes/ressources/documentation/`.
- **Shared modules:**
  - `src/config.py`: paths, CRS, window.
  - `src/web.py`: retrying `requests` session.
  - `src/ingest/hubeau_piezo.fetch_all()`: follows Hub'Eau `next` links.
- **Learning notes.** Assil wants one note per step in
  `docs/notes/stepNN_<topic>.md` (what was done / why / what to consider),
  plus the progress table and glossary in `docs/notes/README.md`. Write it
  before reporting a step as done.

---

## 5. Repository layout

```
src/ingest/      one script per source, runnable as python -m src.ingest.<name>
src/analysis/    profiling, joins, figures
data/raw/        untouched downloads             (gitignored)
data/interim/    cleaned / filtered tables       (gitignored)
data/processed/  model-ready datasets            (gitignored)
data/README.md   data log — committed
docs/            roadmap, memos, literature notes
docs/literature/ literature-review outputs (Feynman reports, state of the art)
reports/figures/ maps and plots
notebooks/       exploration only; anything that matters moves into src/
```

---

## 6. Working rules

1. **Nothing is done until it runs from cold.**
   - Every script must be idempotent and cache what it downloads.
   - If a file already exists with a sensible size, skip re-downloading it.
2. **Log every pull** in `data/README.md`:
   - source and endpoint or URL
   - parameters
   - retrieval date
   - row counts and file sizes
3. **Never commit data.** Commit code after each step works, with a clear
   message.
4. **Don't guess column names.** Print the columns and a sample row from every
   new API or file before writing logic against it.
5. **Don't force the old numbers.**
   - Section 8 lists the counts from the first run.
   - If a new count differs, report the difference and explain why (for
     example, new data since August 2026).
   - Never tune filters just to hit the old number.
6. **Explain in plain language.** After each step, give Assil 3–6 sentences:
   - what was done
   - what the numbers mean for the project
   - what comes next

   He is learning the domain, so explain the *why*, not only the *what*.
7. **Ask before** deleting files, downloading more than 2 GB, or touching a
   design decision in section 3.
8. **Manual steps:** when a download needs a browser, stop and tell Assil
   exactly what to click and where to save the file. Then continue.
9. **Citations:**
   - Never invent a reference.
   - Every paper cited in code comments or docs needs a DOI or arXiv ID that
     you have checked.

---

## 7. CURRENT TASK — rebuild the data foundation from scratch

The data from the first run was lost. Re-download everything and redo roadmap
Steps 1 and 4–7, in order. Track progress with a task list. Stop after Step 7
and wait for Assil.

### ▶ STATUS (last updated 2026-10-05). Read this first in a new session

| Step | Status | Commit | Note |
|---|---|---|---|
| 1 Repo and environment | ✅ done | `eac175f` | `docs/notes/step01_environment.md` |
| 4 Hub'Eau piezometers | ✅ done | `245c2f7` | `docs/notes/step04_piezometers.md` |
| 5 RPG parcels | ✅ done | `33ccaa4` | `docs/notes/step05_rpg.md` |
| 6a BNPE abstraction | ✅ done | `a2b842f` | `docs/notes/step06a_bnpe.md` |
| **6b BD LISA** | **⏳ in progress — START HERE** | n/a | to write: `docs/notes/step06b_bdlisa.md` |
| 7 Gate 1 memo | ⬜ to do | n/a | `docs/memo_gate1_feasibility.md` |

**Where Step 6b stands:**

1. **Done.** Assil downloaded `data/raw/bdlisa/BDLISA_V3_OCC-gpkg.zip`
   (GeoPackage, 169 MB).
2. **Done.** `src/ingest/bdlisa.py` unzips it to
   `data/raw/bdlisa/BDLISA_V3_OCC-gpkg/BDLISA_V3.gpkg` and lists the layers.
   It runs and is committed.
3. **Done.** The official description
   (`.../Descriptif_donnees_BDLISA_V3.pdf`) confirms:
   - `milieueh`: 1 porous, 2 fissured, 3 karstic, 4–10 mixed porosity,
     11 fractured (SANDRE nomenclature 353).
   - `themeeh`: 1 alluvial, 2 sedimentary, 3 basement, 4 intensely folded,
     5 volcanic.
   - `natureeh` (level 3): 5 aquifer unit, 6 semi-permeable unit,
     7 impermeable unit.
   - Order 1 = outcropping (the layer at the surface).
   - `TABLE_GENEALOGIE` is a version changelog, not a hierarchy.
4. **Layers available:**

   | Layer | Fields | Rows |
   |---|---|---|
   | `ENTITES_NIVEAU3_ORDRES` | `CodeEH`, `ordreabseh`, `ordrereleh`, `incluseh`, `milieueh`, … | 1,475 |
   | `ENTITES_NIVEAU3_EXTENSION` | n/a | 568 |
   | `POLYG_ELEMENTAIRES` | `codepoly` | 16,789 |
   | `TABLE_PILE_ENTITES_NIV3` | `CodePoly`, `CodeEH`, `OrdRelatif` | 124,734 |
   | `TME` | attributes for all levels | n/a |
   | `TABLE_LITHOLOGIE_NIV3` | n/a | n/a |
   | `ZONE_KARSTIQUE` | n/a | n/a |

**Next actions for 6b:**

1. Write `src/analysis/bdlisa_profile.py`. Print the columns and a sample
   row of each layer used before writing logic against it.
2. Join the 33 working-set stations (`data/interim/piezo_working_set.parquet`,
   column `code_bdlisa`) to the entities. Check which station entities are
   missing from the Occitanie extract (first run: `760AE09`).
3. Build the vertical order of the plain's entities, shallow → deep, and
   the superposed pairs from `TABLE_PILE_ENTITES_NIV3`. These become the
   `overlies` edges.
4. Find vertical well pairs within 5 km in superposed entities (first
   run: 13).
5. Write the map/figure, the data log entry, `docs/notes/step06b_bdlisa.md`
   and the progress table, then commit.

Then do Step 7, the memo. Then **stop and wait for Assil.**

**Rebuild results so far (compare with section 8):**

- **Piezometers.**
  - 101 stations; 43 with ≥ 8 y record and active in 2024+; **33 in the
    working set**.
  - By layer: 20 `671AA00` Pliocene (median record 35.6 y); 6 alluvium
    (`718BP01-03`, `671AB01-02`); **6** Corbières karst `681AM00`; 1
    `760AE09`.
  - 115,443 measurements over 2016–2025.
  - Plain = bbox lon 2.55–3.06, lat 42.50–42.88 (`PLAIN_BBOX` in
    `src/analysis/piezo_profile.py`, documented in `data/README.md`).
  - 19% of window values are "Non qualifié", rising to 52% in 2025.
- **RPG within 3 km** (parcel centroid rule).
  - 2023: 10,222 parcels, 14,021 ha, median 0.74 ha; vines 32% (4,511 ha),
    orchards 19%, olives 2.3%.
  - 2016: 7,914 parcels, 11,697 ha.
  - Vines are stable in hectares. The share drop is a denominator effect:
    ~2,300 ha of newly *declared* land (pasture/landes, grassland,
    orchards). Always compare hectares, not just shares.
- **BNPE, plain 2012–2023 (Mm³).**
  - Irrigation: 741 surface / 144 groundwater → 84% surface (93% if
    canal intakes count).
  - Drinking water: 3 / 475 → 99% groundwater.
  - Canal intakes ("CANAUX"): 1,245 Mm³, reported separately.
  - 2018 reporting break: boreholes declaring groundwater irrigation jump
    from 370 to 950.
  - 2023 under-reported; canal intakes falling since 2017.
- **Open questions for the supervisor** (go in the Step 7 memo):
  - Keep or drop the 6 karst stations (core = 26 stations).
  - Which framing: use conflict on the Pliocene, or canal-return recharge.
  - Whether a more recent RPG year is wanted (2024/2025 are available, as
    GeoPackage v4.0).

### Step 1 — Repo and environment

- Check that `git` and `python` work, then create the venv.
- Install: `pandas geopandas pyogrio shapely pyarrow requests matplotlib py7zr`.
- Create the folder layout from section 5 and a `.gitignore` that excludes
  `data/` except `data/README.md`.
- **Done when:** the imports succeed and the first commit exists.

### Step 4 — Hub'Eau piezometers (groundwater levels)

**API.** Base URL: `https://hubeau.eaufrance.fr/api/v1/niveaux_nappes`
- `/stations` with `code_departement=66` returns the station list, coordinates,
  BSS codes and BD LISA codes.
- `/chroniques` per `code_bss` returns the full historical series.
- Pagination: HTTP **206** means more pages. Follow the `next` URL in the JSON
  body; don't increment page numbers yourself.
- Use a `requests.Session` with `Retry` (429/5xx, exponential backoff).

**Caching.** Cache each station's series separately at
`data/raw/hubeau/chroniques/<code_bss>.parquet`. Last time a single paginated
pull timed out, so a crash must never restart the whole download.

**Per-station table.** One row per station with:
- start and end date
- number of observations and observations per year
- percentage of missing days
- BD LISA entity code

**Working set.** Keep stations that meet all of:
- record of at least 8 years
- still reporting in 2024 or later
- at least 50 measurements per year
- inside the Roussillon plain

Define the plain's extent explicitly, either from BD LISA entities or a
bounding box, and record it in `data/README.md`. Common analysis window:
2016–2025.

**Outputs:** the stations table, the working-set table, and a map of stations
coloured by record length.

### Step 5 — RPG agricultural parcels

**Source:** IGN Géoplateforme, `https://data.geopf.fr/telechargement`
- `/resource/RPG` returns **Atom XML, not JSON**. Regex the raw text for names
  like `RPG_..._SHP_LAMB93_R76_YYYY-01-01`.
- Download from `/download/RPG/{name}/{name}.7z`.
- Region `R76` (Occitanie), editions **2016 and 2023**. If the naming has
  changed, list what is available and ask.

The archive may extract flat rather than into a folder, so find the shapefiles
with a recursive glob.

**Profile.** Use parcels within 3 km of the working-set piezometers, for both
years:
- parcel count, total area, median parcel size
- share of area by `CODE_GROUP`

Compare the two years at `CODE_GROUP` level. Changes at `CODE_CULTU` level are
mostly nomenclature drift.

### Step 6a — BNPE water abstraction

**API.** Base URL: `https://hubeau.eaufrance.fr/api/v1/prelevements`
- `referentiel/points_prelevement` with `code_departement=66` returns the
  abstraction points.
- `chroniques` with `code_departement=66` returns annual volumes.

**Surface vs groundwater.** Classify by `code_type_milieu` (CONT = surface,
SOUT = groundwater). **Do not use `code_bdlisa`**: it is always null, and last
time it produced a false 0% groundwater share.

**Summary.** Volumes by usage × water source inside the plain, cumulative over
about 2012–2023.

**Caveats to state in the memo:**
- The most recent year is under-reported (consolidation lag).
- Small boreholes below the declaration threshold are missing, so groundwater
  irrigation is a lower bound.

### Step 6b — BD LISA V3 aquifer entities (manual download)

**What Assil does.** Download the Occitanie extract from
`https://bdlisa.eaufrance.fr` (Téléchargement section) and save it under
`data/raw/bdlisa/`. Prefer GeoPackage if offered. Last time the file was
`BDLISA-V3-OCC-gdb.zip`, an Esri FileGDB, which is readable with pyogrio.

**What Claude Code does.**
1. Unzip the archive.
2. List the layers with `pyogrio.list_layers()`.
3. Read them. Non-spatial tables load as plain DataFrames, so don't call
   `.crs` on them.

**What the first run learned about the layers:**
- Entity codes look like `671AA00` (level 3, which is the level station codes
  use).
- `ordreabseh` gives the vertical order, shallow to deep.
- `milieueh` appears to encode the medium: 1 porous, 2 fissured, 3 karstic.
  Confirm this.
- `TABLE_PILE_ENTITES_NIV3` (`CodePoly`, `CodeEH`, `OrdRelatif`) gives
  spatially explicit superposition. These become the `overlies` edges.
- `TABLE_GENEALOGIE` is a changelog, not a hierarchy. Use the `incluseh`
  column for hierarchy.

**Joins and pairs.**
- Join stations to entities.
- Find vertical well pairs within 5 km that sit in superposed entities. These
  pairs decide whether the monotonic-drainage constraint is viable.

### Step 7 — Gate 1 feasibility memo

Write `docs/memo_gate1_feasibility.md`. Keep it short and plain; Assil will
translate it to French if needed and send it to his supervisor. It covers:
- the data inventory and counts
- the surface vs groundwater finding and what it implies
- caveats
- the questions for the supervisor

**The key framing.** In the first run, irrigation in the plain was about 85%
surface water (the historic Têt/Agly canals), while groundwater was mostly
drinking water. This partly contradicts the subject document's "crops pump
groundwater" causal chain. Sharper framings:
- the drinking-water vs agriculture use conflict on the Pliocene aquifer
- canal-return infiltration as a recharge term

Ask the supervisor which framing to commit to.

**Then stop.** Summarise what changed versus section 8 and wait for Assil.

---

## 8. Reference numbers from the first run (August 2026)

Use these to sanity-check the rebuild, not as targets.

**Hub'Eau piezometers:**
- 98 stations in dept 66; 45 with ≥8 years of record and active in 2024+.
- **34 in the working set.** The layers are unbalanced:
  - about 26 deep, in the Pliocene multilayer (BD LISA `671AA00` dominates with
    20 stations; median record 35 years)
  - about 7 shallow, in the Quaternary alluvium
  - 2 in the Corbières karst
- About 309k measurements over 2016–2025. **Correction (rebuild):** this
  was mislabelled. 33 daily stations give at most ~120k values in 10 years.
  The working set's *full* history is 303k; the 2016–2025 window is 115k.

**RPG parcels:**
- About 11,000 parcels and 15,800 ha within 3 km; median parcel 0.75 ha.
- Vines ~33% of area, orchards ~18%, olives ~2%.
- Land use stable 2016 → 2023 at group level.

**BNPE abstraction** (plain, cumulative, Mm³):

| Usage | From surface water | From groundwater |
|---|---|---|
| Irrigation | 811 | 144 |
| Drinking water | 20 | 483 |

**BD LISA:**
- 8 of 9 station entities found; `760AE09` is missing from the Occitanie
  extract.
- Vertical order, shallow to deep:
  1. recent alluvium Têt/Agly/Réart (`718BP01-03`)
  2. ancient alluvium (`671AB01-02`)
  3. Pliocene sands-clays multilayer (`671AA00`, 906 km²)
  4. Corbières limestone (`681AM00`)
  5. Côte Vermeille gneiss (`699AA01`)
- 9 distinct superposed entity pairs across 33 polygons.
- **13 vertical well pairs within 5 km**, which makes the monotonic-drainage
  constraint viable.

---

## 9. After the rebuild (only on Assil's go)

Roadmap continues:
- 8: six architecture papers
- 9: four method papers
- 10: ingestion module
- 11: distance graph + baseline GNN
- 12: Gate 2, commit to the target variable
- 13: competency questions
- 14–17: ontology reuse, bridging module, SHACL, alignment experiment
- 19–22: AlphaEarth embeddings, heterogeneous graph, Gate 3
- 23–24: semantic constraint + low-data ablation; explanations
- 26–29: evaluation, writing, defence

---

## 10. Literature anchors

Full notes live in `docs/literature/`. Papers to keep in mind when writing
code or docs:
- Wu et al., *Water Resources Research* 2025 — graph Fourier deep learning for
  groundwater levels, Yellow River Basin. The closest published analogue.
- Marconato et al., NeurIPS 2023 (arXiv 2305.19951) — reasoning shortcuts.
- OntoAligner, ESWC 2025 — ontology alignment toolkit.
- WHOW-KG, *Scientific Data* 2025 — network-of-ontologies pattern for water.
- Clark et al., *WRR* 2025 (doi:10.1029/2025WR041303) — XAI for
  spatio-temporal groundwater predictions.
- Dai et al., *JGR: Machine Learning and Computation* 2025
  (doi:10.1029/2025JH000703) — deep learning in hydrogeology. Names the three
  gaps this project addresses.
