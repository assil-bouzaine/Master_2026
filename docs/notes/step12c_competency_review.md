# Step 12c: competency-question review (2026-10-24)

## What was done

Reviewed all 16 questions against `Documents/sujet.docx`, the project decisions,
analysis plan, ontology design, attribution code and local data. Rewrote
[competency_questions.md](../competency_questions.md) as a requirements catalogue:
each question has defined inputs, expected outputs, evidence, semantic limits,
acceptance cases and dependencies. The IDs and priorities remain stable: six
MUST, seven SHOULD, three COULD. The six MUST questions had already been approved;
this review refines their contracts rather than replacing the research scope.

Added a common contract for identifiers, units, time, provenance, uncertainty and
missing answers; a subject/research coverage matrix; and an implementation order.
Updated the [design](../ontology_design.md) to match. This is documentation and
test design, not an implementation of the ontology, queries or model experiments.

## Why the previous questions needed revision

The original list covered the main entities well. Its weakness was that several
questions built an unverified answer into their wording. An ontology would then
turn those assumptions into repeatable inferences, giving them more authority
than the evidence supports. These are the principal corrections:

| Questions | Previous risk | Revised requirement |
|---|---|---|
| All | Missing answer interpreted as false/zero; provenance optional in practice | Explicit answer status, coverage, evidence kind, dates, units and rule version |
| CQ1–CQ2 | Recorded unit, screened horizon and unit below a coordinate conflated | Qualified assignments; investigation depth separate from screen interval; conflicting records preserved |
| CQ2 | Alluvial group confidence promoted to exact-unit confidence | Report both evaluation resolutions and use applicability; keep empirical precision separate from individual probability |
| CQ3 | A global transitive ordering connects contacts from different places | Require compatible spatial witnesses for a local stack |
| CQ4–CQ6 | Outcrop, a river name or a canal intake treated as proof of recharge | Separate mapped association, hydraulic hypothesis, demonstrated pathway and quantified flux |
| CQ7 | High-demand crop treated as irrigated or groundwater-fed | Separate crop, contextual demand, actual irrigation and water source; retain unmapped codes and dates |
| CQ8 | Every path given an unconditional physical sign | State mechanism, variable, conditions, evidence policy and constraint eligibility |
| CQ9 | Unknown zone treated as level 0; whole-week applicability assumed | Require authoritative applicability and dated segments; preserve unknowns |
| CQ10 | Entity/sign checks treated as complete explanation validation | Link result/run, SGI reference, contributions and evidence; distinguish response sign, contribution sign, faithfulness and causal validity |
| CQ11/CQ13 | Near wells called nested; depth difference called a vertical gradient | Distinguish site evidence, screens, horizontal separation, comparable datums and matched observations |
| CQ12 | Alternative pump assignments duplicate water; reconstructed weeks called declarations | Account from original annual records; reconcile allocated, unresolved and excluded totals; separate estimates |
| CQ14 | Covered = confined; outcropping = unconfined everywhere | Separate mapped cover, local confinement and head-above-ground proxy |
| CQ15 | Crop agreement or canal access called irrigation validation | Dated, quality-qualified heuristic; independent labels at the scale being evaluated |
| CQ16 | Less irrigation assumed to improve groundwater everywhere | Explicit baseline, supply shares, return-flow effects, model/horizon and sensitivity; no ranking without sufficient inputs |

The intended benefit is a graph that can explain what is known, why it is believed,
and where it cannot yet answer. More classes or more questions alone would not
provide that benefit. Keeping 16 IDs also preserves links from the roadmap and
existing project notes.

## Evidence checked

Read the original subject directly from its DOCX. Inspected the schemas of v4
wells, pumping points, weekly pumping and gauges; interim station, attribution,
stack and pair tables; the annual BNPE source; and the attribution evaluation JSON.

- W1's recorded unit/depth are `671AA00` / 97 m; W2's are `718BP02` / 9 m, with
  stack `718BP02 > 671AA00`. These anchors were checked in v4, not copied from
  historical v3 summaries.
- The attribution evaluation reports alluvial-flag precision 0.947 at group level
  and 0.632 at entity level on 19 cases. This is a concrete reason for CQ2's
  resolution requirement. The validation set contains no irrigation boreholes.
- The 26 aggregate BD LISA contact pairs retain area/counts, not the identities
  of their supporting elementary polygons. CQ3 therefore requires those witnesses
  to be recovered from the source stack data.
- The annual BNPE source retains producer/quality/status fields lost from a simple
  weekly sum. CQ12 must preserve that distinction.

Sources checked on 2026-10-24, linked at their point of use in the catalogue:

- [Wiśniewski et al., 2019, DOI: 10.1016/j.websem.2019.100534](https://www.sciencedirect.com/science/article/pii/S1570826819300617): relation between CQs and formal queries.
- [OWL 2 Primer](https://www.w3.org/TR/owl2-primer/), [SHACL](https://www.w3.org/TR/shacl/), [SOSA/SSN 2017](https://www.w3.org/TR/2017/REC-vocab-ssn-20171019/), [PROV-O](https://www.w3.org/TR/prov-o/), [GeoSPARQL 1.1](https://docs.ogc.org/is/22-047r1/22-047r1.html): evidence/observation/query modelling foundations. The detailed answer contract is this project's design, not a claim that the standards prescribe these CQs.
- [BRGM/RP-62275-FR, §9.1.1](https://rapportage.eaufrance.fr/sites/default/files/DCE/2016/documents/FRN_guide_ME_2013_BRGM.pdf): distinction between mapped cover and hydraulic confinement.
- [USGS exchange guidance](https://ca.water.usgs.gov/sustainable-groundwater-management/interconnected-surface-water-depletion.html) and [artesian-well explanation](https://www.usgs.gov/water-science-school/science/artesian-water-and-artesian-wells): conditional exchange and pressure terminology.
- [FAO crop evapotranspiration guidance](https://www.fao.org/4/X0490E/x0490e04.htm): crop water requirements versus irrigation needs.

## What to consider

The main confident + probable pump-link policy was recorded as approved in the
project brief during this review; it is preserved. Its wider coverage does not
remove exact-unit uncertainty. Any implementation must expose that uncertainty
and keep confident-only/all-link sensitivity policies reproducible.

The acceptance examples are specifications for future tests. Numerical examples
marked synthetic are not Roussillon measurements. Historical empirical counts and
examples remain in [step12_ontology.md](step12_ontology.md),
[step12b_review_fixes.md](step12b_review_fixes.md) and the pre-check; they are not
unversioned test oracles.

Missing canal perimeters, restriction-zone applicability, satellite validation and
scenario supply/return-flow inputs remain real data gaps. A correct unknown answer
is useful, but does not satisfy the core's requirement for representative real-data
answers. Freeze the query contracts before using them to assess implementation.

## Verification performed

Documentation checks confirmed exactly 16 unique, ordered CQ IDs, agreement between
the catalogue and detailed sections, unchanged priorities, and all required fields
in every question. Local Markdown file links resolved and `git diff --check` passed.
The explainer data generator completed; only its generation date and commit metadata
changed, not its plotted data. No SPARQL, SHACL or reasoner pass is claimed for this
documentation revision; those implementations must be tested against these contracts.
