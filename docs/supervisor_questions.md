# Supervisor questions and decisions

**2026-10-23.** The supervisor's answer to the open questions: *"do what is best for the
project."* Assil therefore took the decisions below, on scientific grounds, before any new
result. "Best for the project" means the strongest and most defensible thesis and paper.
It never means "whatever scores best on the test period": that would be cherry-picking, and
reviewers reject it. Where a choice depends on performance, it is made on validation data
only (`docs/analysis_plan.md`), and both options stay in the paper as arms.

What remains to ask is factual or administrative (§3). A short French e-mail informs the
supervisor of the decisions and asks for those facts (§4). A second e-mail requests the
missing pumping data (§5).

## 1. Decisions (2026-10-23)

| # | Question | Decision | Why it is best for the project |
|---|---|---|---|
| 2 | Scope against the subject | **Cover every objective of the subject**, some in small, measured versions: SWEET/INSPIRE/AGROVOC alignment, one satellite rule, a dashboard prototype, small text extraction. Future work: nitrate, socio-economics, full dashboard, Spain. | The jury reads the thesis against `sujet.docx`. The small versions cost about 3–4 weeks and close every gap, while the paper stays focused. |
| 3 | Transfer demo | **The Manouba phreatic aquifer** (Tunisia), qualitative, only if its data arrive by end of February. Otherwise a written "transfer recipe" chapter (which parts of the ontology change). Charf El Akab is the fallback. | Assil's university and MSE-UMA's sensors make access likeliest, and it is a SAVE Water Living Lab. The condition protects the schedule. |
| 4 | Start Phase 3 now? | **Yes, fully.** The ontology design is frozen after Assil's review of the competency questions. | Nothing waits on the supervisor any more. |
| 5 | Framing | **(A) the use conflict on the Pliocene is the main story; (B) canal-return recharge is a secondary case study** for the alluvium. | A rests on stronger evidence: 20 of 33 core wells; drinking water is 99 % groundwater; the pump → unit evidence of CQ2 now exists; BRGM documented the 2024 Pliocene rise after reduced abstraction; "conflits d'usage" is in the subject. B has 4–6 wells and no canal-area data, but it keeps the land-use side visible. Both are in the KG. |
| 6 | Main model | **The hybrid**: KG → heterogeneous GNN → sign-constrained response functions + a small residual. The black-box heterogeneous ST-GNN is a comparison arm. | Every ontology relation gets a precise job. Constraints hold by construction (RQ2), contributions are exact concepts (RQ3), explanations are exact (RQ4), and the parameters transfer to wells left out of training. It also continues the Pastas baseline, which hydrologists trust. The black box covers the nonlinearity risk. |
| 7 | Hard constraints | **Monotone by construction** (no PiShield) | PiShield cannot express the sign of a response to an input. |
| 8 | RQ3 concepts | **Driver contributions**, tested on a semi-synthetic twin; SGI accuracy reported only | The only test that can actually detect a shortcut: SGI is computed from the predicted head. |
| 9 | Title | **"Simulation"**, not "forecasting" | Chronos-2 dominates forecasting; our contribution is simulation and explanation. An honest title survives review. |
| 10 | Karst stations | **Keep them**, as the analysis plan already fixed before any result: primary set = 33 core wells, secondary = 26 plain wells; always reported per aquifer group. | The Corbières karst lies under the Pliocene in the BD LISA stack (141 km² of contact), so it belongs in the multilayer KG. Per-group reporting keeps any group from hiding another. |
| 11 | Newer RPG years | **No for now.** Keep 2016 + 2023; add 2024 only if the satellite rule needs a validation year. | Land use is stable at group level (vines stable in hectares since 2016); a new format would cost days for little gain. |
| 16 | Venue | **Environmental Modelling & Software first, JGR: Machine Learning and Computation second**; final check at Gate 4. HESS if the hybrid is strong. | EMS fits methods + software + ontologies. EMS is a hybrid journal (subscription route possible), so we can publish even if no open-access fee is paid. JGR: MLC is fully open access (fee). |

Decided by Assil on 2026-10-24 (no supervisor question needed):
- **Pump → unit links in the main runs: confident + probable.** They cover 72 % of the
  plain's declared groundwater volume (confident only: 27 %), and "probable" is given only
  where a rule's precision was measured (0.92–0.95 on 130 recorded boreholes, drinking
  water). Confident only, and all links, are sensitivity runs.
- **Competency questions:** the 6 MUST ones are approved as drafted; the ontology module
  starts with them while the 10 SHOULD/COULD ones are reviewed.
- **No model training on the laptop:** CPU fits run on Kaggle (CPU only), GPU fits on Colab.

Decided by Assil on 2026-10-24, late evening, after the third review
(`docs/review_codex_2026-10-24.md`; reasons and checks in
`docs/review_codex_2026-10-24_response.md` §2):
- **Framing (refines decision 5): drinking-water pressure is the main claim.** Under the
  main pump policy no groundwater irrigation volume gets an accepted unit (0 % of 161 Mm³
  declared 2012–2024: 85 % only "possible", 15 % unknown), while drinking water gets 98 % at
  unit-group and 84 % at exact-unit resolution. The model's claims are therefore about
  drinking-water pumping on the Pliocene within the agricultural context; the use conflict
  stays the motivation; farm-pumping effects come only from the all-links sensitivity,
  labelled provisional. The policy itself is unchanged.
- **The hydrology reference from v4: Pastas from training heads only**, decided before the
  Kaggle multistart results: the `--train-obs` fit, its start chosen by the frozen
  training-RMSE rule, whatever its test score, with its spread over the starts reported.
  Deciding after the results would look like choosing the reference that suits us.
- **Arms C–F share one backbone**, adopted now rather than at Gate 3: only the edges change
  between C and D, with the controls fixed in advance (hybrid without message passing,
  random-ID / shuffled statics, distance-matched rewiring, several graph draws;
  `docs/analysis_plan.md` §10). Otherwise D vs C would compare architectures, not edges.
- **Suspect placeholders masked by a rule:** a run of ≥ 28 days at a depth of exactly
  0.00 m leaves every scored variant from v4 (CORNEILLA PD5, 413 days), the v4 primary table
  is shown both ways, and the producer is asked (§6). These weeks are not measurements, and
  the rule was written after the test period was seen, hence the two versions.

Already applied before 2026-10-23:
- the primary metric
- dataset v3
- the RQ1 arms A–F
- OntoAligner kept in the thesis, and in the paper as a supporting result

## 2. Where the questions came from

| Source | Questions |
|---|---|
| `docs/memo_gate1_feasibility.md` §5 (Gate 1) | framing, karst stations, RPG year, venue and fees, defence date |
| `docs/summary_gate2_results.md` (Gate 2) | simulation vs forecasting, monthly drinking-water data, start of Phase 3 |
| `docs/feedback.md` §11 (critical review) | 8 design decisions |
| `docs/savewater_consortium_notes.md` | transfer site, D4.1 / D3.1, contacts, consortium meeting, publication |
| `docs/review_2026-10-23.md` §1 | the scope against the subject |

## 3. Still to obtain (facts, not choices)

| # | What | From whom | Needed by | Answer |
|---|---|---|---|---|
| 1 | **Defence date**, and any mid-term deadline | supervisor or the Master's administration (ISAMM) | **now**: the whole schedule depends on it | |
| 12 | Monthly drinking-water production of the Roussillon boreholes | the water utilities, or the syndicate that runs the SAGE of the Roussillon aquifers (e-mail §5) | Phase 4 (January); it breaks the pumping–weather collinearity | |
| 13 | SAVE Water D4.1 (database design) and D3.1 (data inventory) | supervisor / consortium | Phase 3 (nice to have: align the ontology with WP4) | |
| 14 | Contacts at MSE-UMA (Manouba sensors) and UGE/LASTIG (ontology review) | supervisor | Phase 3 (LASTIG review) and the transfer demo | |
| 15 | Presenting at a consortium meeting | supervisor | any time | |
| 17 | Co-authors, open-access funding, acknowledgement text, grant number | supervisor | before submission (April) | |

## 4. Short e-mail to the supervisor (French): decisions + remaining questions

> **Objet :** PFE SAVE Water — choix retenus et quelques informations
>
> Bonjour [Madame / Monsieur] [Nom],
>
> Merci pour votre confiance. Voici les choix que j'ai retenus pour le projet, avec leur
> justification détaillée dans le document joint :
>
> - **Périmètre :** tous les objectifs du sujet sont couverts, certains en version réduite
>   et mesurée :
>   - l'alignement avec SWEET, INSPIRE et AGROVOC
>   - une règle sémantique sur les images Sentinel-2
>   - un prototype de requêtes pour le tableau de bord
>   - une extraction textuelle limitée
>
>   Les nitrates et la socio-économie restent des perspectives.
> - **Cadrage :** le conflit d'usages sur le Pliocène (eau potable / agriculture) comme fil
>   principal, et la recharge par les canaux comme cas d'étude secondaire pour les
>   alluvions. Les conclusions du modèle porteront sur la pression des prélèvements d'eau
>   potable : la nappe captée par les forages agricoles est trop incertaine, leur effet ne
>   sera estimé qu'en analyse de sensibilité.
> - **Modèle principal :** un modèle hybride où le graphe de connaissances alimente un
>   réseau de graphes qui prédit des fonctions de réponse à signe imposé. Les contraintes
>   physiques sont ainsi garanties et les explications exactes. Un réseau de graphes
>   « boîte noire » sert de comparaison.
> - **Titre :** « simulation » plutôt que « prévision ».
> - **Revue visée :** *Environmental Modelling & Software*, puis *JGR: Machine Learning and
>   Computation*.
> - **Démonstration de transfert :** sur la nappe de la Manouba, si des données sont
>   disponibles d'ici fin février.
>
> J'aurais besoin de quelques informations :
> 1. **La date de la soutenance** et l'éventuelle échéance intermédiaire.
> 2. L'accès aux livrables SAVE Water D4.1 (conception de la base de données) et D3.1
>    (inventaire des données).
> 3. Un contact à MSE-UMA (capteurs de la Manouba) et à l'UGE/LASTIG (relecture de
>    l'ontologie), et si possible une présentation lors d'une réunion du consortium.
> 4. Pour la publication : co-auteurs, prise en charge éventuelle des frais d'accès ouvert,
>    formule de remerciement et numéro de convention.
>
> Je vous enverrai un point d'avancement chaque mois.
>
> Bien cordialement,
> Assil Bouzaine

Attach `docs/review_2026-10-23.md` (the reasons), or this file.

## 5. Data request: monthly drinking-water production (French)

To send to the water utility or the syndicate that runs the SAGE of the Roussillon
aquifers (find the contact on their website). Assil sends it; the supervisor may be
copied.

> **Objet :** Demande de données — production mensuelle des forages AEP de la plaine du
> Roussillon (recherche, projet PRIMA SAVE Water)
>
> Madame, Monsieur,
>
> Étudiant en Master (Université de la Manouba) dans le cadre du projet de recherche
> européen PRIMA SAVE Water, je modélise l'évolution des niveaux des nappes de la plaine du
> Roussillon (Pliocène et Quaternaire) sur 2005–2026, à partir de données publiques
> (ADES, BNPE, Météo-France).
>
> Les volumes déclarés à la BNPE sont annuels. Or c'est la répartition **mensuelle** des
> prélèvements d'eau potable qui permet de distinguer l'effet du pompage de celui de la
> météo, en particulier lors des sécheresses de 2022 à 2025. Serait-il possible d'obtenir,
> pour les forages d'eau potable de la plaine, les volumes produits **par mois** (idéalement
> 2010–2025, par forage ou par champ captant), ou à défaut un profil mensuel type ?
>
> Les données seraient utilisées uniquement à des fins de recherche, citées selon vos
> indications, et pourraient rester confidentielles (seuls des résultats agrégés seraient
> publiés). Je vous transmettrai volontiers les résultats.
>
> Je vous remercie par avance.
>
> Bien cordialement,
> Assil Bouzaine
> Master Science des données, ISAMM — Université de la Manouba

## 6. Note to the producer of CORNEILLA PD5 (French; added 2026-10-25)

To the Syndicat Mixte pour la Protection et la Gestion des Nappes Souterraines de la
Plaine du Roussillon (SMNPR), producer of the series (code producteur 20001584000016 in
Hub'Eau). Assil sends it. Why: from 30 Nov 2022 to 16 Jan 2024 the station reports a depth of
exactly 0.00 m on 413 consecutive days, qualified "Correcte" (contrôle niveau 2), while
flowing wells of the same network record negative depths. We mask these weeks when scoring
(`docs/analysis_plan.md` §1, §14); the producer's answer decides whether the mask stays, the
values become "artesian, head unknown", or a corrected series replaces them.

> **Objet :** Piézomètre 10971X0155/PD5 (Corneilla) — profondeur 0,00 m de novembre 2022 à
> janvier 2024
>
> Madame, Monsieur,
>
> Étudiant en Master (Université de la Manouba, projet de recherche PRIMA SAVE Water), je
> modélise les niveaux des nappes de la plaine du Roussillon à partir des données ADES /
> Hub'Eau, dont celles de votre réseau.
>
> Pour le piézomètre 10971X0155/PD5 (Corneilla-del-Vercol), la chronique publiée indique une
> profondeur de la nappe de exactement 0,00 m chaque jour du 30 novembre 2022 au 16 janvier
> 2024 (413 valeurs, « Valeur mesurée », « Donnée contrôlée niveau 2 », qualification
> « Correcte »), soit un niveau égal à la cote du repère (11,77 m NGF), alors que les autres
> ouvrages de la nappe pliocène baissaient. Avant et après cette période, la profondeur est
> d'environ 4 m puis 1,7 m. S'agit-il d'une période où l'ouvrage était artésien (niveau
> au-dessus du repère, non mesurable), d'une valeur par défaut liée à un capteur, ou d'une
> autre raison ? Une chronique corrigée existe-t-elle ?
>
> Dans l'attente, nous excluons ces semaines de nos évaluations. Je vous remercie par
> avance de votre aide.
>
> Bien cordialement,
> Assil Bouzaine
> Master Science des données, ISAMM — Université de la Manouba

