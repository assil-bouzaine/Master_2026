"""Graph releases (src.kg.release; Codex review of 2026-10-26, §1).

    python -m tests.test_release

On a throw-away directory of small stand-in files (the rules, shapes and ontology are the real
ones, only read):
1. a release written after a derivation is accepted while nothing changes;
2. new facts with the old rule outputs (the stale pair Codex found) are refused, naming the facts;
3. rule outputs rewritten after the release are refused, naming them;
4. an input edited during the derivation stops the release from being written;
5. a derivation that starts (or fails) removes the release, and no release is refused.
"""
import tempfile
from pathlib import Path

from src.kg import release


def files(kg, facts="facts v1"):
    (kg / "lulcw_kg_t_.ttl").write_text("")                 # an unrelated file is ignored
    (kg / "lulcw_kg_t.ttl").write_text(facts)
    (kg / "lulcw_kg_t_rules.ttl").write_text(f"derived from {facts}")
    (kg / "lulcw_kg_t_shacl.ttl").write_text("conforms")


def refused(kg, *names):
    try:
        release.check("t", kg)
    except release.StaleRelease as e:
        assert all(n in str(e) for n in names), (names, e)
        return str(e)
    raise AssertionError(f"accepted: {names}")


def main():
    with tempfile.TemporaryDirectory() as d:
        kg = Path(d)
        files(kg)
        inputs = release.input_hashes("t", kg)
        m = release.write(inputs, "t", kg, rule_outputs_triples=1)
        assert release.check("t", kg)["files"] == m["files"]
        assert set(m["files"]) >= {"facts", "rules", "shapes", "rule_outputs", "validation_report"}
        assert any(r.startswith("ontology:") for r in m["files"])
        print("  1. a release is accepted while its files are unchanged")

        (kg / "lulcw_kg_t.ttl").write_text("facts v2")     # build_kg again, rules not re-run
        refused(kg, "facts", "apply_rules")
        print("  2. new facts with old rule outputs: refused")

        (kg / "lulcw_kg_t.ttl").write_text("facts v1")
        release.check("t", kg)                             # restored: accepted again
        (kg / "lulcw_kg_t_rules.ttl").write_text("edited")
        refused(kg, "rule_outputs")
        print("  3. rule outputs changed after the release: refused")

        files(kg)
        inputs = release.input_hashes("t", kg)
        (kg / "lulcw_kg_t.ttl").write_text("facts v3")     # edited while the rules run
        try:
            release.write(inputs, "t", kg)
            raise AssertionError("a release was written over inputs that changed during the run")
        except release.StaleRelease as e:
            assert "facts" in str(e), e
        print("  4. an input edited during the derivation: no release written")

        files(kg)
        release.write(release.input_hashes("t", kg), "t", kg)
        release.invalidate("t", kg)
        refused(kg, "missing")
        print("  5. a derivation in progress or failed leaves no release, and none is refused")
    print("test_release: all checks passed")


if __name__ == "__main__":
    main()
