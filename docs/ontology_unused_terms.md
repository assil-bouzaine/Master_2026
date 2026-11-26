# Review of the 23 unused ontology terms for R2.2

**Recommendation: keep 8, move 14, prune 1.** R2.2 should keep the shared answer,
evidence and assessment vocabulary in `lulcw-core`; move the annual-accounting
properties and abstraction-record values to `lulcw-hydro`, with their classes and
schemes; and prune `witnessAreaM2`, whose information CQ3 already retrieves from
the witness polygons. Keep the documented future uses distinct from implemented
RDF consumers: a missing consumer today does not cancel a CQ requirement. Separately,
move `wfdCode` to an optional **EU profile**, imported by France and omitted by Tunisia.
That property is outside the 23, so it is excluded from these counts. This review
changes documentation only; the ontology, queries, profiles and graph stay unchanged.

## Basis and reading the recommendations

Reviewed on 2026-11-26 against `ontology/lulcw.ttl` 0.9.0 on
`master_2026_fixes`. The fixed list is the section **Terms nothing uses (23)** in
[ontology_term_usage.md](ontology_term_usage.md), generated from the v4 graph release
of 2026-11-21. It is not a new audit of v5. The audit scans RDF use, rules, shapes,
queries, alignments and ontology axioms; it does not scan every Python consumer.
For example, `src/explain/chains.py` already recognises `ImputedRecord` and
`ReconstructedRecord` in `_RECORD_KIND_LABEL`, although the graph builder currently
writes only `DeclaredRecord`.

The decision follows [v5_plan.md](v5_plan.md) §1 C6 and R2.2 rather than the external
review's blanket instruction to prune all 23. Module destinations below are the
planned seven-module split, not a claim that those files already exist. **Keep**
means retain in the shared core during that split; **move** means retain in the
named domain module. Moving a declaration need not change its existing `lulcw:` IRI.

**History H:** for each of the 23 names, `git log -S '<term>' --oneline --
ontology/lulcw.ttl` identifies the same adding commit, `e6418f9` (2026-10-24,
Task 12.4, ontology 0.1.0). Its message names annual abstraction accounting,
spatially witnessed stratigraphic relations and twelve SKOS schemes for the common
answer contract. The file header, lines 14–19, likewise names CQ1, CQ2, CQ3, CQ8,
CQ11, CQ12 and the shared contract. Later changelog entries do not establish a new
purpose for these terms. **H** in every row refers to that checked origin; the
CQ reference states the specific requirement it served. Definitions are exact
excerpts from the English `skos:definition` in `lulcw.ttl`.

## Keep: shared contract in lulcw-core (8)

| Term | Kind | Definition (quoted excerpt) | Declared purpose / origin | Planned v5 use and recommendation |
|---|---|---|---|---|
| `AnswerStatus` | class | “Status of an answer to a competency question” | H; CQ common answer contract §2, all 16 CQs. | **Keep — lulcw-core.** Shared status vocabulary, including CQ10/CQ15/CQ16 answers. No current status query returns its instances as IRIs; RDF answer publication remains a recommendation, not an implemented R5.1 feature. |
| `Conflicting` | individual | “Cited sources disagree; every alternative is returned with its source.” | H; §2 conflicting-evidence answer. | **Keep — lulcw-core.** Preserve the contract value for contradictory evidence, including CQ10 evidence checks. It is an answer status, not a confidence level. |
| `NotApplicable` | individual | “The question does not apply to the requested entity or period, with a stated reason.” | H; §2 applicability of an answer. | **Keep — lulcw-core.** Common contract for all CQs, including conditional CQ16. Missing scenario inputs normally mean unknown or partial, not automatically not applicable. |
| `Partial` | individual | “Part of the requested scope is answered; the rest is reported as missing.” | H; §2 answer coverage. | **Keep — lulcw-core.** CQ10 withheld statements, CQ15 incomplete coverage and CQ16 missing assumptions need this common meaning; no claim of an existing RDF status writer. |
| `Supported` | individual | “The answer is supported by the cited evidence within the declared scope.” | H; §2 evidence support within scope. | **Keep — lulcw-core.** Shared answer contract, including CQ10. Support never establishes model faithfulness or physical truth by itself. |
| `UnknownAnswer` | individual | “The evidence needed to answer is missing; never read as false or zero.” | H; §2 missing evidence. | **Keep — lulcw-core.** Applies to missing CQ10 results and unavailable CQ15/CQ16 evidence. Do not manufacture a negative classification or zero scenario effect. |
| `ModelResult` | individual | “An output of a model run or a scenario, kept distinct from observed facts.” | H; §2 evidence kind, model/scenario result. | **Keep — lulcw-core**, as a value of the shared `EvidenceKind` scheme. CQ10/R5.1 and CQ16 supply the planned consumers in `lulcw-xai`. This is an evidence-kind individual, **not a model-result class**; R5.1 still needs run, result and statement records. |
| `SupersededStatus` | individual | “Replaced by a later assertion from a newer release or rule version.” | H; §2 assessment of qualified assertions and source revisions. | **Keep — lulcw-core.** Versioned evidence in CQ10 and revised source/attribution records in CQ12 must retain replaced assertions. This belongs to `AssessmentStatus`, not `AnswerStatus`; no current producer of superseded assertions was found. |

## Move: abstraction and annual accounting in lulcw-hydro (14)

These terms are generic water-accounting concepts, not French identifiers. Their
definitions and CQ12 justify a domain module rather than a France profile. R2.2
should move them with `AnnualAbstractionRecord`, `VolumeAllocation`,
`AccountingResult`, `RecordKind`, its scheme, and `DeclaredRecord`, so their
dependencies and alternative record kinds remain together. These companion terms
are outside the 23 and do not change the counts.

| Term | Kind | Definition (quoted excerpt) | Declared purpose / origin | Planned v5 use and recommendation |
|---|---|---|---|---|
| `ImputedRecord` | individual | “An annual volume filled by a documented imputation rule for a missing declaration.” | H; CQ12 separates imputed estimates from declarations; CQ10 exposes imputation flags. | **Move — lulcw-hydro.** CQ12 record-kind distinction and CQ10/R5.1 evidence flags. Python explanations already recognise the value; keep imputed inputs separate from observed declarations. No new RDF imputation exporter is claimed. |
| `ReconstructedRecord` | individual | “A volume obtained by spreading or harmonising declarations” | H; CQ12 distinguishes annual source records from weekly reconstruction; CQ10 source-quality flags. | **Move — lulcw-hydro.** CQ12 and CQ10/R5.1 provenance, also recognised by the Python explanations. Weekly arrays stay in parquet; a linked summary need not copy them into RDF. |
| `accountedFor` | object property | “The hydrogeological unit or unit group an accounting result is about.” | H; CQ12 result target and resolution. | **Move — lulcw-hydro.** Identify the unit/group of a published annual `AccountingResult`. Group evidence must not silently become exact-unit evidence. |
| `accountingYear` | datatype property | “Calendar year an accounting result covers.” | H; CQ12 calendar-year scope. | **Move — lulcw-hydro.** Date annual results independently of their production time; preserve year totals across December/January weekly boundaries. |
| `allocatedTo` | object property | “The hydrogeological unit or unit group a volume allocation gives its share to.” | H; CQ12 explicit allocation target, distinct from alternative assignments. | **Move — lulcw-hydro.** Name a `VolumeAllocation` target only under an explicit allocation policy. Candidate units alone do not establish fractions. |
| `allocatedVolumeM3` | datatype property | “Part of the eligible declared volume, in cubic metres, attributed to the unit or group under the policy.” | H; CQ12 allocated component of the accounting identity. | **Move — lulcw-hydro.** Publish allocated totals by scope/use/policy; alternative sensitivity results are never summed. |
| `allocatesRecord` | object property | “The annual abstraction record a volume allocation shares out.” | H; CQ12 one source record, no duplicate allocation across alternatives. | **Move — lulcw-hydro.** Link each explicit share to its source record so per-record reconciliation can be checked. |
| `allocationWeight` | datatype property | “Share, between 0 and 1, of an annual record's volume given to the allocated unit or group.” | H; CQ12 allocation acceptance case: weights sum to at most 1. | **Move — lulcw-hydro.** Represent an explicit policy's weights; retain the unallocated remainder as unresolved. No fractional allocation is inferred just from rank or confidence. |
| `eligibleDeclaredVolumeM3` | datatype property | “Total declared volume, in cubic metres, of the records an accounting covers, after documented deduplication.” | H; CQ12 eligible declared total and coverage denominator. | **Move — lulcw-hydro.** Store the denominator for reconciliation and coverage; it is not all actual abstraction. |
| `excludedVolumeM3` | datatype property | “Part of the eligible declared volume, in cubic metres, explicitly excluded by the policy, with a stated reason.” | H; CQ12 explicitly excluded component of the identity. | **Move — lulcw-hydro.** Keep policy exclusions separate from unresolved attribution and report their reasons. |
| `facilityCount` | datatype property | “Number of facilities an accounting result covers.” | H; CQ12 facility counts. | **Move — lulcw-hydro.** Publish distinct facility counts with the result's declared scope; counting allocations or source revisions is not counting facilities. |
| `reportingExtent` | object property | “The area whose facilities an accounting result includes, by an explicit selection rule” | H; CQ12 reporting extent S and facility-selection rule. | **Move — lulcw-hydro.** Carry the spatial denominator of an annual result; do not claim the extent contains every withdrawal from the unit. |
| `underPolicy` | object property | “The policy a volume allocation or an accounting result was computed under.” | H; CQ12 attribution/allocation policy. | **Move — lulcw-hydro.** Preserve the result's policy and version. Its range remains `ExportPolicy`, owned by the causal/policy module in the planned split; that dependency must be resolved without merging alternative totals. |
| `unresolvedVolumeM3` | datatype property | “Part of the eligible declared volume, in cubic metres, without an accepted attribution under the policy.” | H; CQ12 unresolved component of the identity. | **Move — lulcw-hydro.** Keep the undealt-with volume visible; missing accepted assignments do not turn declared withdrawals into zero. |

CQ12 already has executable aggregation queries: `tests/cq/cq12_declared.rq`
returns declared totals and `cq12_accounting.rq` partitions them under the selected
policy. They compute bindings such as `?volumeM3` and `?facilities`; they do not
materialise `AccountingResult` or `VolumeAllocation` nodes with these 12 properties.
Their absence from the graph is therefore not evidence that CQ12 accounting is
unimplemented. The planned use is publication of the specified result/allocation
records, not a second independent total. A future writer must check
`eligible declared total = allocated + unresolved + explicitly excluded`, record
deduplication, weights at most 1, dated use, and separate imputed/reconstructed
estimates before those records become evidence for CQ10 or CQ16.

## Prune: redundant area property (1)

| Term | Kind | Definition (quoted excerpt) | Declared purpose / origin | Planned v5 use and recommendation |
|---|---|---|---|---|
| `witnessAreaM2` | datatype property | “Total area, in square metres (Lambert-93), of the polygons that witness a stratigraphic relation.” | H; original CQ3 spatial-witness area descriptor. CQ3 still requires overlap-area information. | **Prune.** No use found for this aggregate property in the planned CQ10, CQ12, CQ15 or CQ16 modules, or a distinct CQ3 consumer. CQ3 already returns each witness polygon's `geo:hasMetricArea`; the rule creates relations inside individual polygon stacks. The extra total adds no required information and fixes the definition to Lambert-93. Preserve the witness links, geometry and existing area retrieval. |

This removes a redundant predicate, not CQ3's area requirement. If a future query
needs area within a selected S, it must compute the appropriate clipped/union area
from the witnesses, with CRS and deduplication, rather than treat a global total as
the area of every requested extent. See `tests/cq/cq03_relations.rq`,
`src/kg/build_kg.py`'s polygon areas, and the `stratigraphicRelation` rule in
`ontology/rules/lulcw-rules.ttl`.

## Answer statuses: strings today, a reusable vocabulary for publication

`AnswerStatus` is a class; the five individuals are `Supported`, `Partial`,
`UnknownAnswer`, `Conflicting` and `NotApplicable`. Keep `AnswerStatusScheme`
alongside them; it is outside the 23 because the ontology uses it in axioms.
`SupersededStatus`, `ModelResult`, `ImputedRecord` and `ReconstructedRecord` belong
to different schemes and must not be interpreted as additional answer statuses.

The current SELECT queries compute lowercase string literals, not `lulcw:` IRIs.
For example, these are verbatim lines from two status queries:

`tests/cq/cq02_status.rq:18`:

```sparql
    BIND (IF(!?isWell, "not_applicable", IF(!?hasUnit, "unknown", "supported")) AS ?status)
```

`tests/cq/cq03_status.rq:17`:

```sparql
    BIND (IF(!?isUnit, "not_applicable", IF(!?mapped, "unknown", "supported")) AS ?st)
```

Other queries supply `partial` and `conflicting` by the same literal convention,
for example `cq01_status.rq`. A query-result variable called `?status` is not an
RDF property assertion. The five mappings, if RDF publication is added, are
`supported` → `Supported`, `partial` → `Partial`, `unknown` → `UnknownAnswer`,
`conflicting` → `Conflicting`, `not_applicable` → `NotApplicable`. In particular,
the English preferred label of `NotApplicable` is “not applicable”, with a space;
the query token has an underscore. A serializer should map explicitly rather than
guess from label or capitalisation.

R5.1 in [v5_plan.md](v5_plan.md) promises runs, heads, contributions and statements
as `lulcw-xai` RDF, with CQ10 shapes. It does **not** specify that answer statuses
must be these individuals. CQ10 can satisfy §2 with an application query returning
the existing strings and reasons. The individuals are therefore not a prerequisite
for writing numerical results. **Recommend keeping the six terms in core because
they encode the explicit, shared §2 contract**, and using the individuals if R5.1
also publishes answer/statement assessment records in RDF. The assessment link and
its shapes would have to be designed then; no existing status predicate or result
writer is asserted here. Retaining the vocabulary does not by itself implement
that consumer or prove semantic consistency, computational faithfulness or causal
validity. `ModelResult`, through the existing `evidenceKind` property, addresses the
separate CQ10/CQ16 distinction between simulated results and observations.

CQ15's rule-positive/rule-negative/insufficient-data classification is a separate,
dated domain result, not an alternative set of answer statuses. None of these 23
terms supplies its NDVI/quality/season schema. CQ16 similarly needs its own scenario,
baseline and assumption records in `lulcw-xai`; retaining `ModelResult` supplies
only the evidence kind. The tables do not claim these future modules already use
the retained IRIs.

## wfdCode: put the European identifier in an optional EU profile

Item 5.5 of [v5_bugs_to_fix.md](v5_bugs_to_fix.md) is a profile decision, not an
unused-term finding. `lulcw:wfdCode` is a functional datatype property, with domain
`SurfaceWaterBody` and range `xsd:string`. Its complete definition is:

> European code of a WFD water body (CdEuMasseDEau), e.g. FRDR224.

The writer is `src/kg/rivers.py:339`, `kg.add(n, L.wfdCode, Literal(s))`, on the
`water-body` node created as `SurfaceWaterBody`. `Context.__init__` reads the
Sandre `masses_eau_riviere_vrap2022.parquet` and uppercases `CdEuMasseDEau` into
`code`; `sections()` matches the configured water-body section against that code
and returns the uppercase section ID used as `s`. Thus the property carries WFD
**river surface-water-body codes**, not gauge codes, BD LISA unit codes, or the
separate groundwater-body identifiers. The literal has the WFD identifier rather
than the source column name or a French agency's internal row key.

Read-only inspection of `data/processed/kg/lulcw_kg_v5.ttl` found 13 values:

```text
FRDR1012  FRDR211   FRDR212   FRDR223   FRDR224   FRDR232A  FRDR232B
FRDR234A  FRDR234B  FRDR235   FRDR237A  FRDR984   FRDR986B
```

**Recommend an optional EU-level profile**, with the France profile importing it
and the Tunisia profile not importing it. The Water Framework Directive applies
across EU members, while Tunisia is outside that scope. French instances of an
EU identifier do not make the property intrinsically French, and the property is
not needed in a country-neutral Mediterranean core. This is a proposed shared
regional adapter in addition to R2.2's two named country profiles; it has not been
created by this task. It can serve other EU Mediterranean profiles without making
them import French identifiers. Retain the existing property IRI and graph values;
only its declaring/importing module changes.

The France-token inventory [ontology_country_terms.md](ontology_country_terms.md)
explicitly uses a fixed token list without `wfd`. Its omission is not proof that
`wfdCode` is a universal core identifier. The review's original France-profile
placement is understandable for the first implementation, but an EU adapter
represents the scope more accurately. During the actual split, also review the
property's `SurfaceWaterBody` dependency and the WFD-specific definition of
`GroundwaterBody`, so WFD semantics do not leak back into the generic core. Those
class decisions are outside this 23-term review, and no class edits were made.
