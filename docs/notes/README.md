# Project notebook (learning notes)

One file per step. Each note answers three questions:

1. **What was done**: the commands, scripts and outputs.
2. **Why**: the reasoning, in plain language.
3. **What to consider**: pitfalls, open questions, things to tell the
   supervisor or to remember when writing the thesis.

The notes are written for Assil to learn the domain and to reuse when writing
the PFE report (the "Méthodologie" and "Données" chapters).

## Progress: rebuild of the data foundation (CLAUDE.md §7)

| Step | Topic | Status | Note |
|---|---|---|---|
| 1 | Repo and environment | done | [step01_environment.md](step01_environment.md) |
| 4 | Hub'Eau piezometers | done | [step04_piezometers.md](step04_piezometers.md) |
| 5 | RPG agricultural parcels | done | [step05_rpg.md](step05_rpg.md) |
| 6a | BNPE water abstraction | done | [step06a_bnpe.md](step06a_bnpe.md) |
| 6b | BD LISA aquifer entities, overlies edges, vertical pairs | done | [step06b_bdlisa.md](step06b_bdlisa.md) |
| 7 | Gate 1 feasibility memo | to do | ../memo_gate1_feasibility.md |

Steps 2–3 of the roadmap (reading/literature) are not part of this rebuild.

## Glossary (grows as we go)

| Term | Meaning |
|---|---|
| **Piezometer** | A borehole used only to measure the water-table level (not to pump). Our target variable comes from these. |
| **Nappe / aquifer** | Underground rock or sediment layer that stores and transmits water. |
| **BSS code** | Banque du Sous-Sol identifier, the national ID of every French borehole (e.g. `BSS002LXXX`). |
| **BD LISA** | French national reference map of aquifer entities ("entités hydrogéologiques"), with codes like `671AA00`. |
| **Hub'Eau** | Free public REST APIs of French water data (eaufrance). |
| **RPG** | Registre Parcellaire Graphique: farmers' declared parcels and crops (EU CAP subsidies), published yearly by IGN. |
| **BNPE** | Banque Nationale des Prélèvements quantitatifs en Eau: declared annual water abstraction volumes. |
| **Lambert-93 (EPSG:2154)** | Official French map projection, in metres. Use it for distances and areas; GPS lat/lon (EPSG:4326) is in degrees. |
| **Parquet** | Compressed columnar file format; fast and keeps column types, unlike CSV. |
| **NGF altitude** | Height above French mean sea level (Nivellement Général de la France). `niveau_nappe_eau` is in m NGF. |
| **Working set** | The stations kept for modelling: long, recent, frequent records inside the plain. |
| **Pliocene multilayer** | Deep sand/clay layers (~2–5 million years old) under the plain; the main drinking-water aquifer (BD LISA `671AA00`). |
| **Quaternary alluvium** | Shallow gravels and sands left by the Têt, Agly, Réart and Tech rivers; sits above the Pliocene. |
| **Karst** | Limestone dissolved into conduits; water moves fast and unpredictably (Corbières, `681AM00`). |
| **CAP / PAC** | EU Common Agricultural Policy. Farmers declare their parcels every year to get subsidies; the RPG is built from these declarations. |
| **CODE_GROUP** | One of ~25 crop groups in the RPG (21 = vines, 20 = orchards, 23 = olives...). `CODE_CULTU` is the detailed crop code (~370 values). |
| **Centroid** | The geometric centre of a polygon. Used to assign each parcel to exactly one zone. |
| **Mm³** | Million cubic metres (1 Mm³ = 1 billion litres). Annual abstraction volumes are given in Mm³. |
| **AEP** | Alimentation en Eau Potable, i.e. drinking-water supply. |
| **Ouvrage** | The abstraction facility (borehole, river intake…) to which BNPE volumes are attached. |
| **Elementary polygon (BD LISA)** | Smallest map unit of BD LISA; each carries a vertical *stack* of aquifer entities, ordered from the surface down (`OrdRelatif` 1 = top). |
| **Overlies edge** | "Entity A lies directly on top of entity B" somewhere in the plain. Becomes a relation in the knowledge graph and an edge in the model's graph. |
| **Head (charge hydraulique)** | Water level in a well expressed as an altitude (m NGF). Water flows from high head to low head. |
| **Vertical gradient** | Difference in head between a shallow and a deep layer at the same place. Shallow > deep means water tends to go down; deep > shallow means up. |
| **Nested piezometers** | Two or more wells at the same site screened at different depths (e.g. C2-1/C2-2). The only clean way to measure a vertical gradient. |
| **Artesian** | The head is above the ground surface: the water would flow out of the well by itself. Sign of a confined, pressurised aquifer. |
| **Confined vs unconfined** | Unconfined: the water table is free (alluvium). Confined: the aquifer sits under a clay layer and is under pressure (deep Pliocene). |
| **Prise (dans la Têt)** | A river intake: the head of an irrigation canal that diverts river water. |
