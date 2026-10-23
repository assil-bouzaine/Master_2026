# Step 12: Phase 3, ontology and knowledge graph

## 12.1 Competency questions (draft, 2026-10-23)

### What was done
- Drafted 13 competency questions in `docs/competency_questions.md` (16 after the revision
  below). Each one has:
  - the parts of the project it feeds: graph, inputs, constraints, explanations,
    validation, framing
  - a priority (MUST / SHOULD / COULD)
  - an example answer computed from dataset v3
- Started from the 10 questions of the critical review (`docs/feedback.md` §7.1) and added
  three:
  - **CQ11**, same-unit neighbours at a similar depth: the one positive signal of the
    knowledge-graph pre-check.
  - **CQ12**, annual abstraction by unit and use: the Pliocene framing.
  - **CQ13**, stacked and nested wells: the anchors for RQ3 and the evidence against a
    head-ordering rule.

### Why
A competency question is a question the ontology must be able to answer. The list is the
ontology's specification and, later, its test suite:
- A class or relation enters the ontology only if a question needs it.
- Each question becomes a SPARQL query in `tests/`, whose answer is compared with one computed
  separately from the parquet tables.

This keeps Phase 3 inside its time-box and gives Gate 3 an objective "done".

### What the example answers already tell us
- **CQ2 is the bottleneck.** Only 240 of the 2,137 groundwater abstraction points carry a
  BSS code; around W1, 4 of 148. Linking pumps to aquifer units needs its own data step
  (rules plus a confidence level).
- **Around Millas (W2), 110 Mm³ of drinking water** was pumped within 5 km over 2012–2023,
  against 17 Mm³ of irrigation. Whether it came from the Têt alluvium or from the Pliocene
  below matters for both layers.
- **Depth matters inside the Pliocene.** W1's three same-unit neighbours, 2.8 km away
  (DEM'TER 1–3), have investigation depths of 15, 60 and 111 m; only one is at a depth
  similar to W1's 97 m.

### Revision after the project review (same day)
The review (`docs/review_2026-10-23.md`) found four errors in the first draft. All are fixed
in `docs/competency_questions.md`:
1. **Depth.** `profondeur_investigation` is the borehole's *investigation* depth, not its
   screen depth (screens are only in the BSS logs).
2. **Depth classes.** Fixed classes were not supported by the pre-check (p = 0.52), while
   the continuous depth difference was (p = 0.002). Depth stays a number.
3. **Restriction orders are not a model input** (CQ9): they would leak the target or are
   used only for the imputation.
4. **GWML2 has no `overlies`.** That relation is ours.

It also added three questions:
- CQ14, confinement
- CQ15, irrigation derived from satellite data (the subject's remote-sensing objective)
- CQ16, the dashboard scenario query

The ontology reuse plan changes too:
- GWML2 has no official OWL; the OWL rendering in SAWGraph's water ontology is used instead.
- SWEET, named in the subject, is added.
- WHOW-KG is kept as the architecture pattern only; it has no water-use module.
- **Two questions lack data:** canal command areas (CQ6) and restriction zones (CQ9). They are
  COULD.

### What to consider
- **Review the list** (add, drop, priorities). Open points:
  - the distance within which a pump can affect a well
  - what counts as a "similar depth"
  - a citable source for the irrigation demand of each crop group
  - a minimum contact area for `overlies` edges
- **Next:** step 2, reuse (find each term in the standard vocabularies, or define it in
  `lulcw:`); then the CQ2 data step.
- Two references, both checked on Crossref:
  - Grüninger & Fox 1995 (doi:10.1007/978-0-387-34847-6_3), the origin of competency
    questions.
  - Wiśniewski et al. 2019 (doi:10.1016/j.websem.2019.100534), how competency questions
    are written as SPARQL.
