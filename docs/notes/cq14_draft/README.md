# CQ14 drafts (2026-11-21, Claude; not yet applied)

Drafts for CQ14 (cover, confinement and pressure state per well; Gate 3 point 15, analysis plan §14
item 23), written while the graph was being rebuilt (task T29) and parked here when the session
stopped. Not part of the ontology, the rules or the tests until they are applied:

- `terms.ttl` → append to `ontology/lulcw.ttl` (and bump the ontology to 0.8.0: versionIRI,
  versionInfo, a change note): HydrogeologicalSetting, PressureStateSummary, ConfinementAssessment,
  the CoverStatus and ConfinementState schemes, HeadAboveReferenceShare/Count, 13 properties.
- `rules.ttl` → `ontology/rules/lulcw-rules.ttl` (order 65: setting from the stack under the well, one
  per monitoring attribution; order 66: confinement per window, confined (probable) only when the
  water stood above the measurement reference, else unknown), plus two rule data nodes
  `<rule/hydrogeological-setting>` and `<rule/confinement-assessment>` (lulcw:DerivationRule, label,
  comment) at the end of the rules file, and the header list of orders.
- `shapes.ttl` → `ontology/shapes/lulcw-shapes.ttl`.
- `cq14_setting.rq`, `cq14_status.rq` → `tests/cq/`.
Still to write: `build_kg.pressure_states` (one lulcw:PressureStateSummary per well and window from
`src/kg/pressure.py`, a release "hubeau-piezo-chronicles" retrieved 2026-10-05, window intervals with
an exclusive end), `tests/test_cq14.py` (fixture with `tests.test_kg_rules.Fixture`: covered without
evidence → covered + unknown; outcropping → unknown, never unconfined; water above the reference →
confined, probable; no depth → unknown, share unbound; window choice; negative controls for every
shape; data check against `bdlisa_station_stacks.csv` and `pressure_state_v4`), docs (CQ14 in
`docs/competency_questions.md`, `docs/ontology_design.md`), then one release, exports, controls, tests.
