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
| 12a | Fixes from the critical review: evaluation, analysis plan, dataset v3, new baselines, knowledge-graph pre-check | done (2026-10-23; EA-LSTM regimes on v4 only) | [step12a_fixes.md](step12a_fixes.md) |
| 12b | Fixes from the second review: dataset v4, strict validated data, grouped folds, cluster-level test, R3 window statistics, analysis plan v2 | done; v4 re-runs of the baselines started 2026-10-24 (Kaggle CPU baselines done; Colab session 1 done; Pastas stability check and EA-LSTM final done 2026-10-25, its regimes running on Kaggle; Chronos-2 and Taccari regimes wait for Colab session 2); first v4 results 2026-10-25: the Pastas reference spreads widely over its starting values, only the ensemble beats it against every start (interim `docs/results_baselines_v4.md`); third review (Codex) checked and its quick fixes done, 2026-10-25; second pass the same night: PD5 placeholder mask, pump coverage by resolution, drought-class scores, saved models and manifests, Pastas replay, tuning budget, analysis-plan amendments (§14) | [step12b_review_fixes.md](step12b_review_fixes.md) |
| 12c | Review and strengthen all 16 competency questions | documentation complete (2026-10-24); query/fixture implementation remains Phase 3 work | [step12c_competency_review.md](step12c_competency_review.md) |
| 12d | Land-use thread after the Codex subject-alignment review: annual RPG 2015–2025, harmonised crop classes with FAO-56 Kc, pre-registered land-use test | in progress (2026-10-25: annual RPG on the département extent, crop classes, crop-thirst index with placebo, pumping reconstruction (3), size and registration checks, land-use test coded; second Codex review answered: run identity, frozen variant, snapshot check; the land-use test (LU-4) pushed to Kaggle on 2026-10-25 evening with same-machine control runs; LU-4 scored on 2026-10-26: no detectable information from the crop-thirst index, main contrast on vs none chosen before the pull) | [step12d_land_use.md](step12d_land_use.md) |
| 12 | Phase 3: ontology and knowledge graph | in progress (six MUST CQs approved; all 16 contracts revised; 12.3 attribution done; 12.4 ontology module 0.1.0 with quality gates; 12.5 knowledge graph filled from the tables, ontology 0.1.1, 2026-10-24; 12.6 rules and shape checks for the layer, well and pump links, ontology 0.2.0, then land use inside the graph (crop codes, classes, clipped areas, demand estimates, dated high-demand categories), ontology 0.3.0, 2026-10-25; validation 26 min → 134 s and doubles stored exactly, 2026-10-26; 12.7 CQ queries: 7 of the 9 MUST (CQ1, 2, 3, 7, 8, 11, 12) with status queries, fixtures and source-table oracles, 2026-10-26; CQ4 (weather cells over each unit's outcrop), graph releases, exact paired support and the Codex review of 2026-10-26 answered, 2026-10-27; CQ4 increment 2: recharge proxies as influences (cell → well, effective rainfall standing in for recharge, the omitted pathways named), ontology 0.5.0, 2026-10-27; CQ5 and CQ6: rivers, gauges, canals and quoted exchange statements, river and canal influences for arm D (35 wells with a river edge, 5 with a canal edge), ontology 0.6.1, 2026-11-06) | [step12_ontology.md](step12_ontology.md) |
| 13 | Review of 2026-11-10; model ladder, rungs 1–2 (response superposition for all wells, signs by construction) | first results 2026-11-10 (`docs/results_ladder_v4.md`): better than Pastas, behind the LSTM, not yet stable across starts; follow-up runs on Kaggle | [step13_ladder.md](step13_ladder.md) |

Steps 2–3 of the roadmap (reading/literature) are not part of this rebuild.

## Glossary (grows as we go)

| Term | Meaning |
|---|---|
| Equifinality | Many different parameter sets fit the same data equally well. The fit cannot tell them apart, so what the model says outside the fitted period depends on which one the optimiser happened to find. |
| Model ladder | The main model built in steps, each adding one ingredient (joint fitting, sharing by aquifer group, knowledge-graph features, routing, message passing), so that each comparison has one explanation. |
| Partial pooling | Each well has its own parameters, pulled towards the average of its group. Between "every well alone" and "one model for all". |
| Log RMSE ratio | log(error of model a / error of model b) for one well. Negative means a is better; −0.05 is about 5 % less error. The primary measure of a contrast since 2026-11-10. |
| Same-arm band | The difference between two halves of the same model's training runs. It shows how much of a difference training noise alone produces. |
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
| **Vertical hydraulic gradient** | Head difference divided by the relevant vertical separation, using comparable datums and screened intervals. A nearby pair's head difference alone is not a vertical gradient. |
| **Nested piezometers** | Two or more wells at the same site screened at different depths (e.g. C2-1/C2-2). The only clean way to measure a vertical gradient. |
| **Investigation depth** | `profondeur_investigation` in Hub'Eau: how deep the borehole goes. Not the screen depth (the open interval that the water comes from), which is only in the BSS borehole logs. |
| **Artesian / flowing artesian** | Artesian pressure raises water above the top of a confined aquifer. Flowing conditions require it to reach the outlet; head above ground is a proxy for this, not a record of actual flow. |
| **Confined vs unconfined** | Hydraulic conditions of an aquifer at a location. Mapped cover or an alluvial name alone does not establish confinement; local evidence is needed. |
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
| **Answer contract** | The inputs, expected output, evidence, units and missing-data behaviour a query must satisfy; one CQ may require several queries. |
| **Open-world assumption** | A fact missing from the ontology is unknown, not automatically false. A zero or a claim of absence needs evidence of coverage. |
| **Evidence resolution** | The level at which a claim was checked, such as alluvium as a group versus one exact BD LISA unit. Confidence at one level does not establish confidence at the other. |
| **Oracle / test fixture** | An oracle is an independently computed expected answer. A fixture is a small controlled example used to check correct answers and prohibited inferences. |
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
| **Ontology module / TBox** | The vocabulary part of an ontology: classes, properties and their axioms (`ontology/lulcw.ttl`). The facts about real wells and pumps (the ABox) come later, in the knowledge graph. |
| **Qualified assertion (n-ary relation)** | A link stored as its own node so that it can carry evidence, e.g. a `UnitAttribution` that says which rule linked a pump to a unit, how precise that rule was, and what the alternatives are. |
| **SKOS concept scheme** | A controlled list of values (e.g. confident / probable / possible) with labels and definitions; the values are SKOS concepts. |
| **MIREOT** | "Minimum information to reference an external ontology term": copy only the declaration, labels and hierarchy of each reused term into a small local file, instead of importing the whole external ontology. |
| **ROBOT** | The command-line tool of the OBO community for ontologies (`tools/robot.jar`): extracts, merges, runs reasoners and quality reports. |
| **Reasoner (ELK, HermiT)** | A program that draws the logical consequences of an ontology and finds contradictions. ELK is fast and partial; HermiT is complete for OWL 2. "Consistent" means no contradiction was found. |
| **Catalog file** | `ontology/catalog-v001.xml`: tells Protégé and ROBOT where to find each imported ontology on disk, so nothing is fetched from the web. |
| **w3id.org** | A free service for permanent web addresses of research vocabularies; our IRIs `https://w3id.org/lulcw#...` will resolve once a redirect is registered there. |
| **ABox / instance data** | The facts part of a knowledge graph (this well, this pump, this volume), as opposed to the vocabulary (TBox). Ours is `data/processed/kg/lulcw_kg_v4.ttl`, built by `src/kg/build_kg.py`. |
| **Turtle** | A readable text format for RDF triples (`.ttl`); prefixes such as `lulcw:` shorten the long web addresses. |
| **Placeholder value** | A number written into a data series when no real measurement exists (a sensor default such as a depth of exactly 0.00 m for months). It looks valid, may even be qualified "Correcte", and must be found by a plausibility rule. |
| **Confusion matrix** | A table of observed classes (rows) against predicted classes (columns); the diagonal holds the correct predictions. |
| **Balanced accuracy** | The mean of the recall of each observed class, so a frequent class (43 % "très bas" months) cannot dominate the score. |
| **Weighted kappa (QWK)** | Agreement between two ordered classifications, corrected for chance; quadratic weights punish a two-class miss four times more than a one-class miss. 1 = perfect, 0 = chance. |
| **POD / FAR / CSI** | For a yes/no event (here "low levels"): probability of detection (share of events predicted), false-alarm ratio (share of predicted events that did not happen), critical success index (hits / all hits, misses and false alarms). |
| **Wilson interval** | A confidence interval for a proportion (e.g. 36 of 39 boreholes correct) that behaves well with small samples and proportions near 0 or 1. |
| **Inference replay** | Re-running a saved model (weights or parameters) and checking it gives the stored predictions: proof that the model, not only its output, was saved. |
| **Leave-one-cluster-out (LOCO)** | Recomputing a result with each spatial cluster of wells removed in turn, to see whether one area drives it. |
| **Run manifest** | A file saved with a run that records the code version, data hashes, settings, seeds and machine: what is needed to reproduce or audit it. |
| **WKT (well-known text)** | A text form of a geometry, e.g. `POINT(653200.0 6176400.0)`; in GeoSPARQL it starts with its coordinate system (here EPSG:2154). |
| **Flat-rate volume (volume forfaitaire)** | A BNPE volume estimated from a standard rate (e.g. per hectare) instead of measured by a meter. 60 % of the declared groundwater irrigation volume is flat-rate. |
| **Pre-specified vs confirmatory** | A comparison fixed in writing before it is run is pre-specified. It is confirmatory only if its test data played no part in designing the method; our 2022–25 drought did, so only weeks observed later are an independent check. |
| **Paired support** | When two models are compared well by well, both must be scored on exactly the same weeks; otherwise part of the difference comes from the weeks, not the models. |
| **Run fingerprint** | A short hash of a run's settings, saved with each result, so that a cached result made with other settings is never reused by mistake. |
| **Crop coefficient (Kc)** | How much water a crop uses compared with a reference grass (FAO-56). It changes over the season: low after planting, highest in mid-season, lower before harvest. A crop's water need ≈ Kc × ETP. |
| **Potential irrigation demand ("crop thirst")** | The crop water need not covered by rain: max(0, Kc × ETP − rain), times the crop area. It says how much water the crops *would* need, not how much was actually pumped or delivered. |
| **Registration effect** | A change in the crop maps that comes from what farmers declare (new codes, newly declared land), not from a change on the ground. Example: peaches got their own RPG code, so "other orchards" seemed to shrink. |
| **Clipped area** | The part of a field that lies inside a zone. A 10 ha field half inside a well's 3 km circle counts 5 ha (the older "centroid" rule counted all or nothing). |
| **Witness polygon** | The map piece whose pile of layers shows a statement such as "A lies on B". Every layer statement keeps its witness, so two statements from different places are never chained. |
| **Export policy / selection** | A named choice of which links the model sees (main runs: confident and probable). Selecting a link never changes its evidence or its confidence; a path is selected only if every link in it is. |
| **Constraint eligibility** | Whether a link's evidence allows its direction ("more pumping can only lower the level") to become a built-in rule of the model: yes when the pump and the well share the exact layer, no when only the layer family is known. |
| **Graph release** | A record saying "these facts, these derived links, these rules and this ontology belong together and passed the checks", with a fingerprint (SHA-256) of each file. Every program that reads the knowledge map checks the fingerprints first; if one file changed (new facts, old links), it refuses, so a link not yet derived is never read as "no link". |
| **Completed search** | A "no" answer counts only when the map shows the place was searched and nothing was found. If the facts show outcrop but the coverage was never computed, the answer is "unknown", not "no outcrop". |
| **Outcrop coverage, cell weight** | For one layer and one area (a 5 km circle around a well, or all the weather cells): where the layer is at the surface, which 8 km weather cells lie over it, and each cell's share (its weight). Outcrop is a mapped fact, not proof that rain gets in there. |
| **Clipping (share of the unit inside S)** | How much of a layer's whole surface outcrop lies inside the area studied. The weather cells hold 85 % of unit 681AF00's outcrop: the rest is outside the modelled weather, so the answer says "partial". |
| **Exact paired support** | Two models are compared on a well only if they were scored on exactly the same weeks. Before, only the number of weeks was compared; now a fingerprint of the week dates is. |
| **Recharge proxy** | A weather quantity used as a stand-in for the water that reaches the aquifer (here effective rain, or soil drainage, which is part of it). A proxy, not measured recharge: the deep Pliocene layer is fed mostly from elsewhere (the Têt valley upstream, the Corbières karst, leakage from the alluvium). |
| **Replayable run** | A model run kept with its fitted model (weights or parameters), so it can be run again on new weeks or tested with "what if" changes. A run with only its predictions can be rescored but not run again. |
| **Recharge-proxy influence** | A link in the map from one weather cell to one well: the cell lies over the outcrop of the well's own layer (within 5 km in the main runs, anywhere in the weather cells in the unit-wide variant), with the cell's share of that outcrop. Its sign says "more effective rain here does not lower this well"; whether the model must obey it is decided at Gate 3. |
| **Omitted pathway** | A way water also reaches a layer that a link does not represent (water from neighbouring rocks, leakage from the layer above, rivers, canals). Each recharge-proxy link names its omitted pathways, so an explanation never presents a proxy as the whole story. |
| **River reach (tronçon)** | One short stretch of a river or canal in the IGN map (BD TOPO), between two junctions. We cut each reach where it crosses a well's 5 km zone and the BD LISA polygons, so we know which layer lies under every piece of river. |
| **Main stem** | The longest path along a river's network, from its source to its end; it lets us say whether a gauge is upstream or downstream of the stretch near a well. |
| **Water body (masse d'eau)** | A stretch of river (or a groundwater body) that the EU Water Framework Directive reports on as one unit, with a code such as FRDR224 ("La Têt du barrage de Vinça à la Comelade"). The groundwater sheets describe the river-aquifer exchange water body by water body. |
| **Losing / gaining river (perdant / drainant)** | A losing river feeds the aquifer below it; a gaining (draining) river receives water from it. The direction can change with the season and the water levels, so the graph keeps it as a dated state with its source, never as a fixed sign. |
| **River-unit association** | The graph's link between a river and a layer near a well: *on outcrop* (the river runs on the layer), *over cover* (it runs over other layers that cover it, so any exchange passes through them) or *documented lateral* (a source says they exchange although the river runs beside the layer). An association is geometry or documentation, not a proven hydraulic connection. |
| **Gauge pool** | The fixed set of gauges a model may use: here the 5 full-record gauges of arm C, so that arms C and D differ only in which gauge is linked to which well. |
| **Command area (périmètre irrigué)** | The fields a canal serves. No map of them exists for the plain, so the graph can say that a canal crosses a layer's outcrop, not which parcels it irrigates or how much of its water reaches the aquifer. |
