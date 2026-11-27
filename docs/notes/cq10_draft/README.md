# CQ10 draft (integrated into ontology 0.12.0 on 2026-11-27)

**Status: integrated.** All drafted CQ10 terms (updated to v5 with `LocalRechargeStress`,
`RegionalRechargeStress`, `LeakageRechargeStress`, `TrainingMean`, `NoNetChange`, the seven BRGM
IPS `SgiClass` members with `lulcw:sgiUpperBound`, and all properties as full Turtle) were
integrated into `ontology/lulcw.ttl` (version `0.12.0`, module `xai`, generated into
`ontology/modules/lulcw-xai.ttl`), together with the six CQ10 SHACL shapes in
`ontology/shapes/lulcw-shapes.ttl`, negative controls in `tests/test_kg_rules.py`, and
`tests/cq/cq10_explanation.rq` / `cq10_status.rq` with fixtures in `tests/test_cq.py` (task T88).
`lulcw_090_terms.ttl` stays here as a historical design record only and is **not** in the ontology
catalog.

Remaining work (outside T88): `src/explain/result_graph.py` (real-data fact builder, R5.1) and the
v5 graph release rebuild / export regeneration handled by the lead.
