# CQ10 draft (ontology 0.9.0, explanations)

Draft terms for the explanation module decided by Assil on 2026-11-24 (analysis plan §14 item 24;
design in `docs/notes/step15_explanations.md`). `lulcw_090_terms.ttl` is **not** in the ontology
catalog: inserting it into `ontology/lulcw.ttl` changes the graph release's hash, so every reader of
the graph (exports, routing, the replay of routed runs) refuses to run until `src.kg.apply_rules`
rebuilds the release. Insert it when no worker or run reads the graph.

Left to do: the seven SGI classes and the properties as full Turtle (listed as comments at the end of
the draft), version 0.9.0 header and changelog line, the shapes (step 15 note, six checks, each
with a negative control), `src/explain/result_graph.py`, `tests/cq/cq10_*.rq` with fixtures,
`python -m tests.test_ontology`, the release rebuild and the export/control regeneration (edges
must stay identical).
