# SAVE Water consortium: what the thesis can connect to

Written 2026-10-13 from public sources. **On hold until Assil has contacted
the supervisor / consortium.** Nothing here changes CLAUDE.md yet.

Sources:
- ANR record ANR-25-PRIM-0014: https://anr.fr/Project-ANR-25-PRIM-0014
- Project website: https://www.savewater.tn (living-labs.html,
  work-packages.html, deliverables.html)
- LinkedIn page: could not be read automatically (LinkedIn blocks bots).

## Project facts

- **Title:** *GeoSpatial and Artificial intelligence technologies: InnovatiVE
  approach for water resources management.* PRIMA S2 2024, topic 2.1.1 (RIA).
- **Coordinator:** Salwa Saidi, Faculty of Sciences of Tunis (FST-UTM).
- **Dates:** 36 months from May 2025 (to about April 2028), so October
  2026 ≈ month 18.
- **13 partners:**
  - Tunisia: FST-UTM; MSE-UMA (Manouba School of Engineering)
  - Morocco: FSTT (Tanger); IAV Hassan II
  - Algeria: UBMA (Annaba)
  - Germany: TU Berlin
  - Italy: ISASI-CNR; Agrianto
  - Egypt: FOAFU (Fayoum)
  - France: CIRAD (SELMET); UGE (Univ. Gustave Eiffel, LASTIG)
  - Portugal: FC.ID
  - Spain: USC (Santiago de Compostela)
- **Overlap with the thesis:** one ANR objective is word for word our topic:
  "model the impact of land use and climate change on hydrological systems,
  using remote sensing".

## Living Labs (from living-labs.html)

| Country | Site | Problem | Partners | Relevance |
|---|---|---|---|---|
| Tunisia | **Manouba phreatic aquifer** (979 wells), Mornag plain, Gabès | groundwater vulnerability; low-cost sensors | FST, MSE | ★★★ Assil's university; candidate transfer site |
| Morocco | **Charf El Akab coastal aquifer** | over-abstraction, falling heads, seawater intrusion | FSTT, UGE | ★★★ same problem as the Roussillon; candidate transfer site |
| Spain | Galicia | groundwater scarcity | USC | ★★ |
| Morocco | Aït Bouguemez valley | land-use change and hydrology | IAV, CIRAD | ★ |
| Portugal / Italy / Algeria / Egypt / Germany | Alentejo, Agrianto, Annaba, Fayoum, Berlin Adlershof | surface water, climate extremes, urban ET | various | low |

**There is no French Living Lab.** The Roussillon is not a project site. It
stays the method-development site (only site with 35-year open records on
every layer; the project covers "Mediterranean and European" regions). The
transfer demo should move from "Cap Bon or Kairouan" (CLAUDE.md §2) to
**Manouba or Charf El Akab**, depending on what data the consortium
confirms.

## Work packages where the thesis fits

| WP | Lead | Link to the thesis | Deliverable / month |
|---|---|---|---|
| WP4 water system database | ISASI-CNR | the ontology as the common vocabulary to harmonise partner data | D4.1 database design, **M18 (≈ now)**; D4.2 standardised datasets M21 |
| WP5 real-time AI/ML monitoring, sensors | MSE-UMA | Manouba sensor data for the transfer | D5.1 sensors M24 |
| WP6 remote sensing + AI for vegetation/hydrology | CIRAD | land-use → hydrology modelling (same objective) | D6.1 SVAT and AI models M30 |
| WP7 GIS multicriteria vulnerability model | FST-UTM / FSTT | forecasts and SGI drought classes as inputs | D7.2 vulnerability model M30 |
| WP8 dashboard | FOAFU | knowledge graph as the "semantic intelligence" layer (subject document) | D8.2 data integration framework M27 |

**The gap the thesis fills:** no work package mentions ontologies, and
groundwater levels are barely mentioned.

## Questions to ask (via the supervisor, not the LinkedIn page)

1. Roussillon as the method site and transfer to Manouba or Charf El Akab:
   OK? Which one has piezometric data, and from when?
2. Access to the draft **D4.1 database design**, to align the ontology and
   offer it as a WP4 contribution.
3. Access to **D3.1 data inventory** (M12).
4. Contacts: MSE-UMA (Manouba sensors) and UGE/LASTIG (ontology review).
5. Publication: co-authors, open-access fees, acknowledgement text and
   grant number.
6. Presenting at the next consortium meeting.

## Draft message to the supervisor (French)

> Bonjour [Professeur],
>
> J'ai étudié le site du projet (savewater.tn). Mon sujet comble un manque :
> aucun lot ne prévoit d'ontologie, et les niveaux piézométriques y sont peu
> traités. Je propose de garder le Roussillon comme site de développement de
> la méthode (données ouvertes sur 35 ans), puis de la transférer vers un
> Living Lab du projet. Quelques questions :
>
> 1. Pour le transfert, lequel convient le mieux : la nappe phréatique de la
>    Manouba (capteurs du WP5, MSE-UMA) ou l'aquifère côtier de Charf El Akab
>    (FSTT/UGE) ? Des données piézométriques y sont-elles disponibles, et à
>    quelle date ?
> 2. Puis-je consulter le projet de conception de la base de données (D4.1,
>    WP4) ? Mon ontologie pourrait servir de vocabulaire commun pour
>    harmoniser les données des partenaires.
> 3. Puis-je consulter le rapport d'inventaire des données (D3.1) ?
> 4. Serait-il possible d'avoir un contact à MSE-UMA (capteurs de la Manouba)
>    et à l'UGE/LASTIG (ontologie) ?
> 5. Publication : co-signature, financement de l'open access, formule de
>    remerciement et numéro de convention.
> 6. Pourrais-je présenter mon travail lors d'une prochaine réunion du
>    consortium ?
>
> Je joins le mémo de faisabilité. Merci,
> Assil

## After the answers

- Update CLAUDE.md §2: replace the demo site.
- Update `docs/roadmap.md` Phase 3: align the ontology with D4.1.
- Update the Gate 1 memo, if not yet sent.
