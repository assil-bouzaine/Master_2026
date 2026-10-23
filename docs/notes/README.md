# Project notebook (learning notes)

One file per step. Each note answers three questions:

1. **What was done**: the commands, scripts and outputs.
2. **Why**: the reasoning, in plain language.
3. **What to consider**: pitfalls, open questions, things to tell the
   supervisor or to remember when writing the thesis.

The notes are written for Assil to learn the domain and to reuse when writing
the PFE report (the "Méthodologie" and "Données" chapters).

**Start here if a word is unclear:** the plain-words guide `docs/explainer/index.html`
explains the whole project with pictures (open it in a browser).

## Progress: rebuild of the data foundation (CLAUDE.md §7)

| Step | Topic | Status | Note |
|---|---|---|---|
| 1 | Repo and environment | done | [step01_environment.md](step01_environment.md) |
| 4 | Hub'Eau piezometers | done | [step04_piezometers.md](step04_piezometers.md) |
| 5 | RPG agricultural parcels | done | [step05_rpg.md](step05_rpg.md) |
| 6a | BNPE water abstraction | done | [step06a_bnpe.md](step06a_bnpe.md) |
| 6b | BD LISA aquifer entities, overlies edges, vertical pairs | done | [step06b_bdlisa.md](step06b_bdlisa.md) |
| 7 | Gate 1 feasibility memo | done (waiting for the supervisor) | [../memo_gate1_feasibility.md](../memo_gate1_feasibility.md) |
| 8 | Phase 1: climate, rivers, weekly pumping, dataset v1 | done | [step08_dataset.md](step08_dataset.md) |
| 9 | Phase 2: baselines on v1 | done | [step09_baselines.md](step09_baselines.md) |
| 10 | Baselines v2: more data, tuning, ensemble, ablation | done | [step10_baselines_v2.md](step10_baselines_v2.md) |
| 12a | Fixes from the critical review: evaluation, analysis plan, dataset v3, new baselines, knowledge-graph pre-check | in progress | [step12a_fixes.md](step12a_fixes.md) |
| 12b | Fixes from the second review: dataset v4, strict validated data, grouped folds, cluster-level test, R3 window statistics, analysis plan v2 | done (v4 re-runs of the baselines pending) | [step12b_review_fixes.md](step12b_review_fixes.md) |
| 12 | Phase 3: ontology and knowledge graph | in progress (12.1 drafted, waiting for review; 12.3 pump → unit attribution done) | [step12_ontology.md](step12_ontology.md) |

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
| **Investigation depth** | `profondeur_investigation` in Hub'Eau: how deep the borehole goes. Not the screen depth (the open interval that the water comes from), which is only in the BSS borehole logs. |
| **Artesian** | The head is above the ground surface: the water would flow out of the well by itself. Sign of a confined, pressurised aquifer. |
| **Confined vs unconfined** | Unconfined: the water table is free (alluvium). Confined: the aquifer sits under a clay layer and is under pressure (deep Pliocene). |
| **SAFRAN / SIM2** | Météo-France's gridded reconstruction of daily weather (8 km cells) and of the soil water balance (model ISBA). Our source for rain and evapotranspiration. |
| **ETP** | Potential evapotranspiration: how much water the air *could* take from a well-watered surface (mm). Actual ET (EVAP) is what was really evaporated. |
| **Effective rain / drainage** | Rain left after evaporation (PE), and the part that drains below the roots (DRAINC) towards the water table: a proxy for recharge. |
| **SGI** | Standardised Groundwater Index: a level converted to "how unusual for this month at this well", on a normal scale (0 = typical, −1.28 = driest 10%). |
| **IPS classes** | BRGM's 7 classes of the standardised level, from "très bas" (driest 10%) to "très haut". Used in the official drought bulletins. |
| **Warm-up** | The period of input data a model needs *before* its first prediction, because groundwater remembers past rain. |
| **Data leakage** | When information from the test period sneaks into training (e.g. defining "normal" with test years). It makes results look better than they are. |
| **Baseline** | A simpler, standard model the new method must beat. Without baselines, "NSE 0.6" means nothing. |
| **Simulation vs forecast** | Simulation: level predicted from weather + pumping only. Forecast: level h weeks ahead, knowing today's level. |
| **NSE** | Nash–Sutcliffe efficiency: 1 = perfect, 0 = no better than the mean level, < 0 = worse than the mean. |
| **KGE** | Kling–Gupta efficiency: combines correlation, variability and bias; 1 = perfect. |
| **Pastas / TFN model** | Transfer-function noise model: the level = sum of each stress (rain, pumping) convolved with a response curve, plus noise. The hydrologists' standard. |
| **Anomaly persistence** | Forecast "the level will be as far from normal in h weeks as it is today". Hard to beat at short horizons. |
| **Ablation** | Changing one thing at a time to see which change caused an effect (here: longer history vs more wells). |
| **Wilcoxon test (paired)** | Checks whether one model beats another *well by well* more often than chance would. p < 0.05 is the usual bar for "significant". |
| **Hyperparameter tuning** | Searching the model's settings (window length, size, learning rate) automatically; chosen on validation, never on test. |
| **Ensemble** | Averaging several models; their errors partly cancel. |
| **Prise (dans la Têt)** | A river intake: the head of an irrigation canal that diverts river water. |
| **Ontology** | A formal vocabulary for a domain: classes (well, aquifer unit), relations (pumps from, overlies) and rules, written so that a computer can reason with them. |
| **Knowledge graph (KG)** | The facts written with that vocabulary ("well C2-1 monitors unit 718BP02"), stored as a network of entities and relations. |
| **RDF triple** | The unit of a knowledge graph: subject, relation, object. RDF is the standard format. |
| **Competency question (CQ)** | A question the ontology must be able to answer. The CQs are its requirements, and each becomes a SPARQL test. |
| **SPARQL** | The query language of RDF knowledge graphs (like SQL for tables). |
| **SHACL / SHACL-AF** | SHACL checks that the graph has the expected shape (every `pumpsFrom` has a source); SHACL-AF rules derive new facts (a "high irrigation demand zone"). |
| **Bridging module (`lulcw:`)** | Our own small ontology: it links the reused standard vocabularies and adds the causal relations with their sign. |
| **Polarity** | The sign of a causal link: `decreasesHead` (pumping) or `increasesHead` (rain, canal seepage). |
| **Provenance / confidence** | Where a fact comes from (BSS record, depth rule, name rule) and how sure we are of it. |
| **Strict validated weeks** | Test weeks whose every daily value is qualified "Correcte" by the producer. Recent data are mostly "Non qualifié" (not yet checked), which is not the same as wrong. |
| **Grouped (blocked) cross-validation** | Wells close to each other are kept in the same fold, so a held-out well cannot be predicted from its near twin. |
| **Cluster (sign-flip) permutation test** | A significance test that respects dependence: under "no difference" the sign of the paired differences of a whole cluster of wells may flip, never one well alone. |
| **Effect size** | How large a difference is (e.g. median ΔNSE +0.8), as opposed to whether it is "significant". Reported first. |
| **p-hacking** | Changing the analysis after seeing the results until a p-value drops below 0.05. Avoided by fixing the plan in advance (analysis plan, git tag). |
| **Hindcast** | A forecast made after the fact with inputs that were not all available at the time (here: annual pumping totals). Not an operational forecast. |
| **Precision vs recall (of a rule)** | Precision: when the rule fires, how often it is right. Recall: of the cases it should find, how many it finds. "50 of 53 Pliocene points are False" is a recall; the rule "False → Pliocene" needs a precision. |
