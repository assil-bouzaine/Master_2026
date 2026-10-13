# Step 6b: BD LISA aquifer entities, overlies edges and vertical well pairs

**Date:** 2026-10-13 · **Status:** done

## What was done

| Script | What it does |
|---|---|
| `src/ingest/bdlisa.py` | Unzips the manually downloaded GeoPackage and lists its layers. |
| `src/analysis/bdlisa_profile.py` | Decodes entity attributes. Finds the stack of aquifer entities *under each well* (point → elementary polygon → stack). Builds the `overlies` edges of the plain. Finds vertical well pairs and compares their heads week by week. |

```bash
.venv/bin/python -m src.ingest.bdlisa
.venv/bin/python -m src.analysis.bdlisa_profile
```

### Results

**Stations ↔ entities**
- 32 of the 33 working-set stations have their entity in the extract.
  `760AE09` (CARRIE) is missing, as in the first run.
- For 31 wells, the stack under the well contains the well's own entity.
  The two exceptions:
  - ALENYA (`718BP03`, Réart alluvium) sits just inside a `718BP04` (Tech
    alluvium) polygon. It is a boundary effect.
  - CARRIE is the missing entity.

**The plain's vertical structure** (simple, as expected):

| Position | Entity | BD LISA nature | Medium |
|---|---|---|---|
| top | recent alluvium Têt / Agly / Réart / Tech (`718BP01-04`) | aquifer unit | porous |
| top or 2nd | ancient alluvium (`671AB01-04`) | aquifer unit | porous |
| under the alluvium | Pliocene sands and clays (`671AA00`, 902 km² under the plain, 289 km² outcropping) | **semi-permeable unit** | porous |
| under the Pliocene (north) | Corbières karst (`681AM00`) | aquifer unit | karstic |

- The plain has 26 direct `overlies` edges. Of these, 9 are between station
  entities, the same 9 as the first run.
- They are saved in `data/interim/bdlisa_overlies_plain.csv` and will become
  `gwml2`-style `overlies` triples in the knowledge graph (Phase 3).

**Vertical well pairs** (≤ 5 km, shallow entity above deep entity):
- **17 pairs** (first run: 13). 15 of them are superposed in the stack under
  one of the two wells.
- The count is higher because "above" now follows the stack transitively
  (alluvium → Pliocene → karst), so the 3 Pliocene/karst pairs and 1
  alluvium/alluvium pair count too.
- Figures: `reports/figures/bdlisa_plain_entities_pairs.png`,
  `reports/figures/bdlisa_pair_head_difference.png`.

### The key number: is the shallow head above the deep head?

| | Result |
|---|---|
| All 17 pairs, 17,124 pair-weeks | shallow head above deep in **50.5%** of weeks |
| Pairs with a consistent ordering (≥ 95% one way) | 10 of 17, in **both** directions |
| Nested pair **C2-1 / C2-2**, Millas, Têt valley, 20 m apart | shallow above deep **100%** of weeks: water goes **down** |
| Nested pair **BARQUA / F**, Agly, 50 m apart | shallow above deep only **5.5%** of weeks: water goes **up** from the Pliocene; up to 14.5% in autumn |
| BARQUA vs BAR3 / F3N4 (3–5 km) | flips with the season: shallow above in summer and autumn, never in spring |

- **Artesian wells:** 4 Pliocene wells sometimes have their head *above
  the ground*:
  - F: 24.5% of days
  - F3N4: 21.4%
  - FE1: 1.2%
  - F1N4: 0.6%

## Why

- **Why the stack under the well, not the entity map.** BD LISA describes
  the subsurface as a pile of entities on each small "elementary polygon".
  Reading the pile under each well tells us exactly what is above and
  below the screened layer at that spot. That is more precise than saying
  "these two entities touch somewhere".
- **Why compare heads.** The subject proposed the constraint "water
  infiltrates downward". If that held, the shallow head would always be
  above the deep head. The data says it holds at Millas and fails at the
  Agly site:
  - At the Agly site the Pliocene is under pressure (confined, sometimes
    artesian), so water would rise if the clay let it.
  - In summer, pumping lowers the Pliocene and the gradient reverses.

  A hard "shallow ≥ deep" rule would therefore force the model to be wrong
  half of the time.
- **What we use instead** (decided in CLAUDE.md §3): constraints on the
  *direction of responses*. Pumping lowers the head, rain raises it. These
  hold everywhere. The vertical connection stays in the graph as an
  `overlies` edge, but **without a sign**: the model learns whether, where
  and when the layers exchange water.
- **The seasonal flip is itself a result.** It is direct evidence of the
  use conflict on the Pliocene: summer abstraction, mostly drinking water
  (99% groundwater, Step 6a), is strong enough to reverse the natural
  vertical gradient. That supports the "use conflict" framing for the
  supervisor.

## What to consider

- **Distant pairs mix two things.** Wells 3–5 km apart differ also because
  the water table slopes towards the sea. Only nested pairs (≤ 100 m: C2-1/C2-2
  and BARQUA/F) measure a pure vertical gradient. The ±35 m values
  (C2-1 / PZ) are topography, not vertical flow.
- **Pliocene "semi-permeable".** BD LISA classes `671AA00` as a
  semi-permeable unit: a multilayer of sands (aquifers) and clays
  (aquitards). One entity code hides several aquifer levels. Wells of
  different depths in `671AA00` (11 m to 235 m) may monitor different sand
  layers. Keep the screen depth (`profondeur_investigation`) as a node
  feature.
- **LAFAR** (`671AA00`, 11.2 m deep) is a shallow Pliocene well. Check with
  the supervisor whether its code is right.
- **Karst stations.** The 3 Pliocene/karst pairs show the Pliocene head
  15–18 m above the karst head. That is a strong difference between two
  systems. One more argument to discuss keeping or dropping the karst
  stations.
