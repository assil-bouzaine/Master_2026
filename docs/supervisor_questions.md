# Questions for the supervisor (all in one place)

**Status:** prepared 2026-10-23, **not sent yet**. It is also the first
monthly progress report, which the PFE guide (`Documents/guide.docx.pdf`)
asks for.

**When the answers arrive:**
1. Fill in the "Answer" column of §2.
2. Update CLAUDE.md:
   - §1a: title, venue
   - §2: demo site
   - §3: every item marked (supervisor)
   - §7: status
3. Update `docs/roadmap.md`.

## Where the questions came from

Until now they were spread over four documents. They are merged and
deduplicated below:

| Source | Questions |
|---|---|
| `docs/memo_gate1_feasibility.md` §5 (Gate 1, 13 Oct) | framing, karst stations, RPG year, venue and fees, defence date |
| `docs/summary_gate2_results.md` (Gate 2, 13 Oct) | simulation vs forecasting, monthly drinking-water data, start of Phase 3 |
| `docs/feedback.md` §11 (critical review, 20 Oct) | 8 design decisions |
| `docs/savewater_consortium_notes.md` | transfer site, D4.1 / D3.1, contacts, consortium meeting, publication |
| `docs/review_2026-10-23.md` §1 | the scope against the subject |

---

## 1. E-mail ready to send (French)

> **Objet :** PFE SAVE Water — point d'avancement d'octobre et questions
>
> Bonjour [Madame / Monsieur] [Nom],
>
> Voici un point d'avancement de mon PFE (premier rapport mensuel) et les
> questions sur lesquelles j'ai besoin de votre avis avant de figer la phase
> ontologie.
>
> **Où j'en suis**
>
> - **Données :** jeu complet et reproductible pour la plaine du Roussillon :
>   - 65 piézomètres, 2005–2026
>   - climat SAFRAN
>   - prélèvements BNPE, y compris 2024
>   - BD LISA, RPG et débits des rivières
> - **Modèles de référence terminés :** Pastas, LightGBM, LSTM, réseaux de
>   graphes et Chronos-2, avec une évaluation plus rigoureuse :
>   - période de test séparée en sécheresse (mai 2022 → nov. 2025) et en
>     reprise (déc. 2025 →)
>   - score relatif à une « année normale » (climatologie)
>   - tests statistiques corrigés pour la dépendance spatiale
> - **Résultat :** sur la sécheresse, les meilleurs modèles réduisent
>   d'environ 55 % l'erreur de la climatologie et sont significativement
>   meilleurs que Pastas. L'erreur restante est surtout un décalage de niveau
>   en 2024–2025.
> - **Phase ontologie démarrée :** 16 questions de compétence rédigées, avec
>   des réponses tirées des données.
>
> Pièces jointes : le mémo de faisabilité (Gate 1), la synthèse des résultats
> (Gate 2) et une revue du projet (en anglais).
>
> **Questions**
>
> *A. Calendrier*
> 1. Quelle est la date de la soutenance ? Y a-t-il une échéance intermédiaire
>    (rapport à mi-parcours) ?
>
> *B. Périmètre par rapport au sujet*
> 2. Je propose de couvrir tous les objectifs du sujet, certains en version
>    réduite et mesurée :
>    - **fusion d'ontologies :** réutilisation de SWEET, INSPIRE (HILUCS),
>      AGROVOC (AgroPortal), GWML2, SOSA et HY_Features. S'y ajoute une
>      expérience d'alignement mesurée : codes cultures du RPG → AGROVOC, avec
>      OntoAligner (précision, rappel, F1).
>    - **enrichissement sémantique de la télédétection :** une règle
>      « parcelle probablement irriguée » (NDVI Sentinel-2 estival et humidité
>      du sol), vérifiée sur le RPG.
>    - **contraintes physiques :** les signes de réponse issus de l'ontologie
>      (le pompage fait baisser le niveau, la pluie le fait monter). La règle
>      « l'eau descend » est contredite par les données (seulement 50,5 % des
>      cas).
>    - **explications :** la chaîne causale tirée de l'ontologie, avec une
>      mesure de fidélité au modèle.
>    - **tableau de bord :** un prototype, c'est-à-dire les requêtes SPARQL des
>      questions de compétence, une carte et une requête de scénario.
>    - **extraction textuelle :** une version réduite (10 à 20 articles,
>      précision mesurée).
>
>    Hors périmètre (perspectives) : nitrates, socio-économie, tableau de bord
>    complet, Espagne. Êtes-vous d'accord avec ce périmètre ?
> 3. Le site d'étude est la plaine du Roussillon, choisie pour ses données
>    ouvertes sur 35 ans, alors que les Living Labs de SAVE Water sont au sud.
>    Je propose une démonstration de transfert en fin de projet, sur la nappe
>    de la Manouba (capteurs MSE-UMA) ou sur l'aquifère de Charf El Akab.
>    Lequel préférez-vous ? Des données piézométriques y sont-elles
>    disponibles, et depuis quand ?
> 4. Puis-je poursuivre la phase ontologie maintenant, en parallèle de votre
>    lecture ?
>
> *C. Choix de conception (détaillés dans la revue jointe)*
> 5. Cadrage scientifique : (A) le conflit d'usages sur le Pliocène (eau
>    potable contre agriculture), ou (B) la recharge des alluvions par les
>    retours d'irrigation des canaux ?
> 6. Modèle principal. Je propose un modèle hybride : le graphe de
>    connaissances alimente un réseau de graphes qui prédit les paramètres de
>    fonctions de réponse à signe imposé, une par relation causale de
>    l'ontologie, plus un petit réseau résiduel. Un réseau de graphes
>    « boîte noire » sert de comparaison. Ainsi, chaque relation de l'ontologie
>    a un rôle précis, les contraintes sont garanties et les explications sont
>    exactes. Êtes-vous d'accord ?
> 7. Contraintes « dures » : monotones par construction plutôt que PiShield,
>    qui ne peut pas exprimer le signe d'une réponse à une entrée. D'accord ?
> 8. Test des « raccourcis de raisonnement » : les concepts sont les
>    contributions des facteurs (pluie, pompage par nappe, canaux), testées sur
>    un jumeau semi-synthétique dont on connaît la vérité. La précision des
>    classes SGI sera rapportée, mais ce n'est pas un test de raccourci (elle
>    découle du niveau prédit). D'accord ?
> 9. Titre : « simulation » plutôt que « forecasting », Chronos-2 restant la
>    référence en prévision. D'accord ?
> 10. Stations karstiques des Corbières : les garder, ou travailler sur les
>     26 stations de la plaine ?
> 11. Occupation du sol : le RPG 2016 et 2023 suffit-il, ou faut-il ajouter
>     2024/2025 ?
>
> *D. Données*
> 12. Le projet peut-il obtenir la production mensuelle d'eau potable des
>     forages du Roussillon (syndicats, SAGE des nappes du Roussillon) ? C'est
>     la donnée manquante la plus utile.
>
> *E. SAVE Water*
> 13. Puis-je consulter le livrable D4.1 (conception de la base de données),
>     pour aligner l'ontologie et la proposer comme contribution au WP4, ainsi
>     que le D3.1 (inventaire des données) ?
> 14. Serait-il possible d'avoir un contact à MSE-UMA (capteurs de la Manouba)
>     et à l'UGE/LASTIG (relecture de l'ontologie) ?
> 15. Pourrais-je présenter mon travail lors d'une prochaine réunion du
>     consortium ?
>
> *F. Publication*
> 16. Revue visée : *Environmental Modelling & Software* en premier choix,
>     *JGR: Machine Learning and Computation* en second. D'accord ?
> 17. Co-auteurs, prise en charge des frais d'accès ouvert par SAVE Water,
>     formule de remerciement et numéro de convention ?
>
> Je vous remercie par avance.
>
> Bien cordialement,
> Assil Bouzaine

---

## 2. The same questions in English: source, our proposal, answer

| # | Question | Came from | Our proposal | Answer |
|---|---|---|---|---|
| 1 | Defence date; any mid-term deadline? | Gate 1 Q5 | — (plan assumes early June 2027) | |
| 2 | Scope against the subject: all objectives covered, some in small versions; nitrate, socio-economics, full dashboard, Spain as future work | review §1 | yes (CLAUDE.md §1b) | |
| 3 | Transfer demo: Manouba or Charf El Akab? Piezometric data available? | consortium notes Q1 | Manouba (Assil's university, MSE-UMA sensors) if data exist | |
| 4 | May Phase 3 continue now? | Gate 2 Q3 | yes, reversible parts only until answers | |
| 5 | Framing: (A) Pliocene use conflict or (B) canal-return recharge | Gate 1 Q1 | either; both are in the KG (CQ12, CQ6) | |
| 6 | Main model: the hybrid (KG → GNN → sign-constrained response functions + residual), black-box HGT as comparison | feedback §11.6 | yes | |
| 7 | Hard constraints: monotone by construction, not PiShield | feedback §11.4 | yes | |
| 8 | RQ3 concepts: driver contributions + semi-synthetic twin; SGI accuracy reported only | feedback §11.5 | yes | |
| 9 | Title: "simulation", not "forecasting" | feedback §11.8; Gate 2 Q1 | yes | |
| 10 | Karst stations: keep or drop | Gate 1 Q2 | keep in training (masked loss), report separately | |
| 11 | RPG: add 2024/2025? | Gate 1 Q3 | add 2024 if cheap (new format) | |
| 12 | Monthly drinking-water production for the Roussillon boreholes | Gate 2 Q2 | ask the syndicates / SAGE through the supervisor | |
| 13 | Access to SAVE Water D4.1 (database design) and D3.1 (data inventory) | consortium notes Q2–3 | align the ontology with D4.1; offer it to WP4 | |
| 14 | Contacts: MSE-UMA, UGE/LASTIG | consortium notes Q4 | — | |
| 15 | Present at a consortium meeting | consortium notes Q6 | — | |
| 16 | Venue: EMS first, JGR: MLC second | Gate 1 Q4 | yes | |
| 17 | Co-authors, open-access fees, acknowledgement text, grant number | Gate 1 Q4; consortium notes Q5 | — | |

Already applied, for information:
- the primary metric (feedback §11.1)
- dataset v3 (feedback §11.2)
- the RQ1 arms (feedback §11.3)
- OntoAligner kept in the thesis, and in the paper as a supporting result
  (feedback §11.7, adjusted by the review)

## 3. What to attach

- `docs/memo_gate1_feasibility.md` (Gate 1)
- `docs/summary_gate2_results.md` (Gate 2). Its numbers use the old
  evaluation. The e-mail gives the v3 headline, and the full interim v3
  results are in `docs/results_baselines.md`.
- `docs/review_2026-10-23.md`: optional, in English. It explains questions
  2 and 5–9.

To send them as PDF:
`pandoc docs/memo_gate1_feasibility.md -o memo_gate1.pdf` (if pandoc and a
LaTeX engine are installed), or open the files on GitHub and print to PDF.
