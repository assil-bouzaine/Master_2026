"""A graph release: facts, rule outputs and validation that belong together.

src.kg.apply_rules derives links from the facts written by src.kg.build_kg. Rebuilding the facts
without re-running the rules leaves a stale pair: the facts have new nodes whose derived links do
not exist yet, so a query reads "no derived coverage" as "no outcrop" (Codex review of 2026-10-26,
§1: MILLAS C2-1 got "no mapped outcrop" while 27 km² of its unit's outcrop were in the facts).
src.kg.apply_rules therefore writes lulcw_kg_<dataset>_release.json, only when the shapes find no
violation and after every output: the SHA-256 of each input (the facts, the rules, the shapes,
each file of the ontology network), hashed before the derivation and unchanged at its end, and of
each output (the rule outputs, the validation report). Every reader of the graph
(src.kg.cq.kg_store, the tests' data checks, the 12.8 export) calls check(), which recomputes the
hashes and refuses a graph whose files changed since that derivation. A failed or interrupted
derivation leaves no release: apply_rules deletes it before it starts.
"""
import hashlib
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from src.config import DATASET, PROCESSED, ROOT

KG = PROCESSED / "kg"
ONTOLOGY = ROOT / "ontology"
RULES = ONTOLOGY / "rules" / "lulcw-rules.ttl"
SHAPES = ONTOLOGY / "shapes" / "lulcw-shapes.ttl"
OUTPUTS = ("rule_outputs", "validation_report")


class StaleRelease(RuntimeError):
    """The graph files do not form a validated release."""


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def ontology_files():
    """The files of the ontology network, from the catalog (name -> path), sorted by name."""
    files = {u.get("name"): ONTOLOGY / u.get("uri")
             for u in ET.parse(ONTOLOGY / "catalog-v001.xml").getroot().iter() if u.tag.endswith("uri")}
    return dict(sorted(files.items()))


def paths(dataset=DATASET, kg=KG):
    """Every file a release binds: role -> path (ontology files as ontology:<name>)."""
    out = {"facts": kg / f"lulcw_kg_{dataset}.ttl", "rules": RULES, "shapes": SHAPES}
    out |= {f"ontology:{k}": v for k, v in ontology_files().items()}
    return out | {"rule_outputs": kg / f"lulcw_kg_{dataset}_rules.ttl",
                  "validation_report": kg / f"lulcw_kg_{dataset}_shacl.ttl"}


def input_hashes(dataset=DATASET, kg=KG):
    """SHA-256 of every input of the derivation (role -> hex), taken before it starts."""
    return {r: sha256(p) for r, p in paths(dataset, kg).items() if r not in OUTPUTS}


def manifest_path(dataset=DATASET, kg=KG):
    return kg / f"lulcw_kg_{dataset}_release.json"


def invalidate(dataset=DATASET, kg=KG):
    """Remove the release (a derivation is starting, or it failed)."""
    manifest_path(dataset, kg).unlink(missing_ok=True)


def write(inputs, dataset=DATASET, kg=KG, **record):
    """Write the release: `inputs` are the hashes taken before the derivation, which must still
    hold (an input edited during the run is refused), plus the outputs; `record` adds fields."""
    now = paths(dataset, kg)
    moved = sorted(r for r, h in inputs.items() if sha256(now[r]) != h)
    if moved or set(inputs) | set(OUTPUTS) != set(now):
        raise StaleRelease(f"inputs changed during the derivation: {moved or sorted(set(now) ^ set(inputs))}")
    files = {r: {"path": str(p.relative_to(ROOT) if p.is_relative_to(ROOT) else p),
                 "sha256": inputs[r] if r in inputs else sha256(p)} for r, p in now.items()}
    m = {"dataset": dataset, "released": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "files": files} | record
    manifest_path(dataset, kg).write_text(json.dumps(m, indent=1, ensure_ascii=False))
    return m


def check(dataset=DATASET, kg=KG):
    """The release manifest of `dataset` if every file it binds is unchanged; else StaleRelease
    naming the files that changed, appeared or are missing."""
    f = manifest_path(dataset, kg)
    hint = (f"run PFE_DATASET={dataset} python -m src.kg.apply_rules (after src.kg.build_kg if the "
            "facts are not current)")
    if not f.exists():
        raise StaleRelease(f"{f.name} missing: the current graph has no validated derivation; {hint}")
    m = json.loads(f.read_text())
    now = paths(dataset, kg)
    changed = sorted(r for r, p in now.items()
                     if r not in m["files"] or not p.exists() or sha256(p) != m["files"][r]["sha256"])
    changed += sorted(r for r in m["files"] if r not in now)
    if changed:
        raise StaleRelease(f"the graph of {dataset} changed since its derivation ({', '.join(changed)}); {hint}")
    return m
