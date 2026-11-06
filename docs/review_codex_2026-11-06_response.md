# Response to the Codex review of 2026-11-06

Review: `docs/review_codex_2026-11-06.md` (written at 11:23 on the four commits of the morning, CQ5
and CQ6; moved from the repository root, unchanged). Assil, the same day: "check it out and if
there's something concerning or good adapt it, otherwise continue". Every point was checked against
the code and the released graph before anything changed; the verdicts are below, then what was done
and what changed in the numbers.

Verdicts: ✅ correct, done · 🔶 correct, done in part or left for a decision (Gate 3) · ❌ not
followed (with the reason).

## Verdicts

| Point | Verdict | Checked | Done |
|---|---|---|---|
| **S1** WKT gate | ✅ | Reproduced: 45 gauge points written `POINT (x y)` (Shapely's `to_wkt`) beside 2,433 written `POINT(x y)`; none off the box. The regex turned them into NaN and the assertion blamed the coordinates. The space also mattered elsewhere: `cq02_candidates.rq` parses `POINT(` as text, so a gauge-distance query would have failed silently. | Gauges written by the graph's own `point()` helper (one form everywhere); `tests/test_kg.py` now names points of the wrong form before checking the box. `test_kg` passes. |
| **S2** document ingestion | ✅ | `src/ingest/documents.py`: the index was saved only at the end, so a failure after the first download left a file without an entry, and the next run raised `KeyError`. | Atomic writes, the index saved after each document; a stored copy without an entry is fetched again and compared (dated by that fetch, with a note), never dated by guess; a differing copy is refused. `tests/test_documents.py` (5 checks, a stand-in session, an injected failure). |
| **Q1** CQ8 completed-search claim | ✅ | Reproduced on BSS002MVJS (COLLIOURE, 699AA01): 448 m of the Massane off the map, CQ5 partial, CQ8 `river=none_found` "a completed search". | `cq08_status`: river reaches off the map turn `none_found` into `unknown` (and `no_pool_gauge` when a pool-gauged river is off the map); canal reaches the same; the off-map length is given. Fixture R8; anchor RIMBAU. |
| **Q2** CQ5 supported despite off-map reaches | ✅ | Reproduced on BSS002MQNK (BARQUA): supported with 32 m of the Agly off the map. | `cq05_status`: off-map reaches make a documented answer partial, with the length. Fixture R7; anchor BARQUA. |
| **Q3** a well's measurement applied to another well | ✅ | `brgm-c2-1-mixing` (MILLAS C2-1) was an applicable statement of 10915X0395/PZ's canal association. | A statement measured at a site applies only in that site's zone (river and canal rules, shapes, CQ5/CQ8 stale checks). Its canal edge stays eligible on the statements about 718BP02 itself. Fixture C4 (R1 only, not R7). |
| **Temporal/policy signature** | 🔶 | CQ5's contract has U, S, T and a policy; the queries took U, S. | CQ5 and CQ6 take an optional period (`?T0`, `?T1`): dated statements outside it are not counted, undated ones are reported as such (`temporalScope`, `evidencePeriods`). The policy acts through the influences (CQ8), as before. |
| **R1** body-level evidence promoted to unit level | ✅ | Confirmed and wider than reported: besides FRDG351's 14 rows (8 units each), five more statements name an aggregate: the EVP's "aquifères", BRGM's "Quaternary groundwater (poles P1 and P2)" (P1 and P2 are water end-members, not the two alluvium units: BRGM/RP-71486-FR p. 23), BRGM's "formations du Quaternaire", "aquifère quaternaire", SMNPR's "nappes quaternaires", and "nappe alluviale de l'Agly". Two of the four lateral associations rested on FRDG351 alone (HIPPO2, 10915X0395/PZ on the Agly), and three on-outcrop eligible signs had no statement about their unit at all (BARQUA, 10915X0395/PZ on the Têt, 10972X0094/111111). | `configs/exchange_evidence.csv`: `subject` (unit or aggregate), `groundwater_body`, `method`. Graph: `aboutUnit` only for a unit itself, `aggregateMemberUnit` and `aboutGroundwaterBody` otherwise (ontology 0.7.0). Rules: an aggregate never makes a documented lateral association or an eligible sign; on outcrop it is localised to the unit in contact (`localizedStatement`, a separate inference). `test_exchange_evidence` gate 6 checks each subject against its sheet's own unit list (a body statement read as unit evidence is refused); the synthetic body of the acceptance case is fixture S7/R9. The two lateral associations and the three body-only signs are gone; whether outcrop localisation may make a sign eligible is a Gate 3 question (analysis plan §14 item 17). |
| **R2** a proxy needs its own sign justification | ✅ (design) 🔶 (decision) | Agreed: the physics justifies a response to the local stage; a remote gauge's discharge and the plain's summed canal diversions are proxies whose adequacy was argued in prose only. | Three layers made explicit: the influence's eligibility (evidence), the proxy review and the approval (`lulcw:ConstraintDecision` per mechanism and policy, from `configs/constraint_decisions.csv`). Pumping accepted (CLAUDE.md §3); recharge, river and canal pending: no such sign constrains a model before Gate 3. `cq08_influences` reports `proxyReview`, `constraintApproval` and `constrained`. The adequacy questions are listed for Gate 3. |
| **R3** HY_FlowPath subclass | ✅ | Agreed: canal reaches realise no catchment, and the graph holds none for river reaches. The import also rendered HY_River's `skos:broader` as `rdfs:subClassOf`. | River reaches are a close match of HY_FlowPath, canal reaches unmatched; the import keeps the source's `skos:broader`. The **alignment ledger** (`ontology/alignments/ledger.csv`, 25 rows) records every correspondence, rejected ones included, with required and forbidden entailments, checked by HermiT in `test_ontology` gate 8. Building it found a second faulty axiom: `Piezometer ⊑ GW_Well`, although some monitoring points are springs (Fontestramar, Source de la Tirounère, Source Sainte-Cécile, Source Clots de Rhodes): now a close match, and the class definition says so. |
| **R4** space, time and evidence type | ✅ | Confirmed: `cq05_status` called any opposite pair in a zone a conflict, e.g. FRDG351's FRDR224 (losing) beside FRDR223 (draining downstream), which are different stretches. Every statement had `ExpertHypothesis` only. | `lulcw:overlapsSection` (lines running together over at least 500 m; computed in `src/kg/rivers.py`); a conflict needs the same or overlapping stretches and either overlapping dated periods (contradiction) or an undated statement (unresolved); otherwise variation. `evidenceMethod` (differential gauging, geochemical tracing, water balance, synthesis) for all 32 statements, read from each passage; hedging stays separate. The canal eligibility rule still uses the wording ("stated"); replacing it with a method criterion is a Gate 3 question (both give the same edges today). |
| Results section | ✅ (no action) | The medians match `docs/results_baselines_v4.md`; the baseline report already gives single-seed spreads beside the saved aggregates. | — |
| §1 two-well example, §2 export inventory, §3 twin | ✅ already planned | Same as CLAUDE.md's resume list. | The export's path-aggregation rule is proposed in analysis plan §14 item 17 (one edge per driver, well and relation; eligible only if every selected path agrees), to confirm before scoring. |
| §4 alignment benchmark criteria | ✅ | Good additions. | Written into analysis plan §14 item 17 (recall@k, joint target-and-relation correctness, near-duplicate audit, blind annotations, the benchmark's name). |
| §5 data | ✅ already planned | The data requests (canal perimeters, a local pumping series, the two-well review) are on Assil's list. | — |
| §6 release identity | ✅ | `30832cf+uncommitted` did not identify the code; snapshots were chosen as "the newest directory". | Code versions now carry the hash of the uncommitted changes (`c7555f5+uncommitted-…`); the facts summary records the hashes of the configuration files and snapshot manifests; `configs/snapshots.json` pins the BD TOPO, Sandre and AGROVOC snapshots (a newer one is reported, never used silently), and the tests read the same pins. |
| Publication position | ✅ (no action) | Agreed: the contribution is the traceable translation of uncertain knowledge into edges and conditional constraints, with tests of when it helps. | — |

Nothing in the review was rejected.

## Numbers before and after (release of 2026-11-06, dataset v4, main policy)

Morning release (09:32 UTC) against the release of the afternoon (rebuilt 14:28–14:43 local time; facts
469,450 triples, rule outputs 162,922, no SHACL violation):

| | morning | afternoon | why |
|---|---|---|---|
| documented lateral river associations | 4 | **2** | HIPPO2 and 10915X0395/PZ (Agly) rested on FRDG351's body-level row alone; the two 10962X PZ keep BRGM's statement about 671AB02 itself |
| wells with a river edge in D | 35 (24 core) | **34 (23 core)** | HIPPO2 had only its lateral edge |
| river influences | 43 | **41** | the two lateral ones |
| eligible river signs | 8 influences, 7 wells (5 core) | **3 influences, 3 wells (2 core)**: MILLAS C2-1, CORBERE and 10962X0075/PZ | HIPPO2 and 10915X0395/PZ (Agly) lost their lateral edges; BARQUA, 10915X0395/PZ (Têt) and 10972X0094/111111 have only aggregate statements (FRDG351, the EVP, BRGM's "Quaternary formations"), localised by the outcrop: a Gate 3 question whether that suffices |
| over-cover-only wells | 18 (16 core) | 18 (16 core) | unchanged |
| canal edges | 5 wells (4 core), 2 eligible | 5 wells (4 core), 2 eligible | unchanged; 10915X0395/PZ keeps its eligible edge without C2-1's measurement |
| statements applicable / localised | 69 applications | 41 applicable to the unit itself, 15 localised from an aggregate | the aggregate rows no longer count as evidence about each member |
| CQ5 status (65 wells' recorded units) | conflicting 4, supported 16, partial 39, unknown 1 | **conflicting 2**, supported 15, partial 42, unknown 1 | the two 10962X PZ no longer meet FRDG351's rows (lateral: nothing localises an aggregate there); BARQUA and the other wells with 32 m of the Agly off the map are partial (Q2) |
| CQ8 river answers | derived 35, no_pool_gauge 17, none_found 7, unknown 6 | derived 34, no_pool_gauge 17, none_found 7, **unknown 7** | COLLIOURE RIMBAU: 448 m of the Massane off the map (Q1); HIPPO2 is now a completed none_found |
| constraint decisions | — | pumping accepted; recharge, river, canal pending | no recharge, river or canal sign constrains a model before Gate 3 |

The two remaining conflicts are of the "unresolved" kind (an undated FRDG351 or EVP Têt statement
against BRGM's September 2017 campaign on overlapping stretches of the Têt): MILLAS C2-1 and
10915X0395/PZ.

## Left open

- Gate 3 (analysis plan §14 item 17, ❓): outcrop localisation of body-level statements for a sign;
  the proxy adequacy of the river discharge, the summed canal diversions and the effective
  rainfall; a soft-prior sensitivity; the canal eligibility criterion (wording or method); the
  export's path-aggregation rule.
- The bounded domain review of the two example wells (supervisor, SMNPR or BRGM): unchanged.
- OOPS! (a web service) stays a separate gate.
