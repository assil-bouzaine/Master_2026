# Step 15 — Phase 5: explanations in ontology terms (SO4, CQ10)

Started 2026-11-24, while the Phase 4 fits ran on Colab. Plan: CLAUDE.md §3 ("Validity and
explanations"), roadmap Phase 5, analysis plan §8, §12 and §14 item 24. Decided by Assil on
2026-11-24: a small explanation module in the ontology (version 0.9.0, the second exception to the
0.7.x freeze), and shortcut test 2 kept as an uncalibrated diagnostic.

## What an explanation is here

One explanation = one **simulated head** of one well over one time window, compared with a stated
**reference condition**, split into **driver contributions**, each tied to the **knowledge-graph
records** that let that driver reach the well, with every statement checked before it is shown.

Three properties stay apart (analysis plan §12), each with its own evidence:
1. **Ontology consistency**: the cited entities exist, are linked to the well under the run's export
   policy, and the stated direction agrees with the contribution's sign. Checked by SHACL shapes.
2. **Faithfulness to the model**: removing a driver group's anomaly changes the simulated head by
   the stated amount (fidelity+/−). For the hybrid this is exact by construction (a sum of
   convolutions); it is still tested, because a bug would break it. For the black box it is an
   estimate (Integrated Gradients, aggregated by node type and relation).
3. **Physical validity**: whether the model's attribution is the real cause. Only the twin (where
   the truth is known) and independent evidence (e.g. the BRGM bulletin on the summer 2024 rise)
   speak to it. An explanation says "the model attributes ...", never "pumping caused ...".

## The numbers (`src/explain/contributions.py`, task T46)

- Source: the exact per-stress contributions of the hybrid, saved per start
  (`contrib_seed_<k>.parquet`, metres).
- Groups: `configs/explain_groups.csv` maps each model stress to a report group and to the
  knowledge graph's driver group (`lulcw:RechargeProxies`, `lulcw:SummerDemand`,
  `lulcw:RiverDischargeGroup`).
- Reference condition: by default the run's own training-period mean of each contribution at the
  same week of the year (2005–2019 for R1). The anomaly then holds only between-year variation,
  the scale at which §8 allows pumping claims. Case studies may use an explicit reference window
  (summer 2024 against summer 2023) and say so.
- Explained runs: the converged-pooling runs `p4_B2conv_D_*` (Gate 3 point 1), the three pumping
  reconstructions side by side: a pumping statement must keep its direction under all three.
- Stability: mean and sd over the 10 starts, and the share of starts that agree on the sign.

## Statement rules (fixed 2026-11-24, before any explanation was computed)

A statement about a driver group is:
- **withheld** when its weeks carry imputed pumping input (pumping groups only: any imputed share
  > 0 in the window), when fewer than 8 of the 10 starts agree on its sign, when the three
  reconstructions disagree on its direction (pumping groups), or when its size is below 0.05 m
  (smaller than the half-width of a typical same-arm band; not a claim worth making);
- **qualified** (stated with its caveat) when the window has under 50 % strictly validated observed
  weeks, or when the knowledge-graph path rests only on "probable" links;
- **accepted** otherwise.
The direction stated is the contribution's sign relative to the reference ("lowered the head by
0.4 m compared with an average year at this time"), never the response polarity: less pumping than
usual contributes positively although pumping lowers heads (CQ10's acceptance case).

## The ontology module (version 0.9.0, CQ10)

Reuses PROV-O, OWL-Time's dates through the existing `lulcw:periodStart`/`periodEnd`, and the
existing `lulcw:Influence`, `lulcw:ExportPolicy`, `lulcw:DataRelease`, `lulcw:DriverGroup`,
`lulcw:selectedUnder`. New terms (minimal):

| Term | Kind | Meaning |
|---|---|---|
| `ModelRun` | class ⊑ prov:Activity | one fitted run (`results/v4/<run>`); its export policy, graph release, regime, reconstruction and protocol |
| `SimulatedHead` | class ⊑ prov:Entity | a model result for one well and window (never an observation): mean simulated head (m NGF), SGI value and class with the frozen training reference |
| `DriverContribution` | class ⊑ prov:Entity | the part of a simulated head's anomaly that the model attributes to one driver group, with its reference condition, unit (m), start sd and sign agreement |
| `ReferenceCondition` | SKOS scheme | `TrainingSeasonalMean`, `ReferenceWindow` (with its dates) |
| `ExplanationStatement` | class ⊑ prov:Entity | one sentence (FR and EN) that cites a contribution and the influences behind it |
| `ContributionDirection` | SKOS scheme | `RaisedHead`, `LoweredHead`, `NoNetChange` (relative to the reference; distinct from `ResponseSign`) |
| `StatementStatus` | SKOS scheme | `AcceptedStatement`, `QualifiedStatement`, `WithheldStatement`, with a reason |
| `SgiClass` | SKOS scheme | the 7 BRGM IPS classes with their bounds (the threshold version of `src.dataset.build`) |

Properties: `generatedByRun` (or prov:wasGeneratedBy), `simulatedAt` (→ Piezometer),
`contributionTo`, `contributionGroup`, `contributionM`, `seedSdM`, `seedSignAgreement`,
`imputedPumpingShare`, `referenceCondition`, `explains`, `citesContribution`, `citesInfluence`,
`statedDirection`, `statementStatus`, `withheldReason`, `statementText`, `sgiValue`, `sgiClass`.

Shapes (each a negative-control test, CQ10's acceptance cases):
1. every cited influence exists, targets the statement's well and is selected under the run's
   export policy (a path the policy excludes is rejected);
2. the influence's driver group is the contribution's group;
3. the stated direction agrees with the sign of `contributionM`;
4. a pumping statement over imputed weeks is withheld;
5. the SGI class matches the SGI value by the IPS bounds; the window lies inside the run's period
   (a mismatched period is rejected);
6. an accepted statement has sign agreement ≥ 0.8.

## Order of work

1. T46 (Neon): the numbers. ⏳ running
2. Ontology terms 0.9.0 (Claude), quality gates.
3. Result graph builder `src/explain/result_graph.py` + shapes + `tests/cq/cq10_*.rq` + fixtures.
4. Templates FR/EN (`src/explain/templates.py`); an LLM may only polish wording, never content.
5. Faithfulness (`src/explain/faithfulness.py`): driver-group interventions (anomaly → reference)
   through the saved parameters; the black box with Integrated Gradients on Colab.
6. Case studies: summer 2024 Pliocene rise (BRGM bulletin, 16 Sept 2024), the 2023 drop, an
   alluvium well (canal); plus a fixed sample of ordinary cases and failures chosen by a rule
   (per aquifer group, the well at the median and the well at the worst drought NSE of
   `p4_B2conv_D_r1`), fixed before any explanation is read.
