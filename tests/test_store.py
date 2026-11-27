"""The persisted graph store (src.kg.store; v5 plan R2.4).

    python -m tests.test_store

On a throw-away directory with a small stand-in release (the rules, shapes and ontology files are
the real ones, only read and hashed):
1. the first call builds the store from the facts and the rule outputs, read-only, and it answers
   a query exactly as an in-memory store of the same two files does;
2. a second call opens the same store without rebuilding it;
3. the store refuses to be written;
4. facts changed after the release: the release is refused (StaleRelease), so the old store is
   never served;
5. a new release of the changed facts: the store is rebuilt and holds the new triple;
6. a left-over directory of an interrupted build is cleared and the build succeeds;
7. a record that names another manifest (e.g. written for an older release) forces a rebuild.
"""
import json
import tempfile
from pathlib import Path

import pyoxigraph as ox

from src.kg import release, store

D = "t"
FACTS = """@prefix ex: <http://example.org/> .
ex:w1 ex:monitors ex:u1 .
ex:w2 ex:monitors ex:u1 .
ex:w3 ex:monitors ex:u2 .
"""
DERIVED = """@prefix ex: <http://example.org/> .
ex:w1 ex:linked ex:w2 .
ex:w2 ex:linked ex:w1 .
"""
Q = "SELECT ?w ?u WHERE { ?w <http://example.org/monitors> ?u } ORDER BY ?w"


def write_release(kg, facts=FACTS):
    (kg / f"lulcw_kg_{D}.ttl").write_text(facts)
    (kg / f"lulcw_kg_{D}_rules.ttl").write_text(DERIVED)
    (kg / f"lulcw_kg_{D}_shacl.ttl").write_text("# conforms\n")
    release.write(release.input_hashes(D, kg), D, kg)


def rows(s):
    return [tuple(t.value for t in r) for r in s.query(Q)]


def in_memory(kg):
    s = ox.Store()
    for f in store.release_files(D, kg):
        s.bulk_load(path=str(f), format=ox.RdfFormat.TURTLE)
    return s


def main():
    with tempfile.TemporaryDirectory() as tmp:
        kg = Path(tmp)
        write_release(kg)

        s = store.persisted_store(D, kg)                                    # 1
        rec = store.read_record(D, kg)
        assert len(s) == 5 and rec["triples"] == 5, (len(s), rec)
        assert rec["manifest_sha256"] == store.manifest_digest(D, kg)
        assert rows(s) == rows(in_memory(kg)) and len(rows(s)) == 3, rows(s)
        print("  1. built on first use: 5 triples, same answers as the in-memory store")

        built = rec["built"]
        s2 = store.persisted_store(D, kg)                                   # 2
        assert store.read_record(D, kg)["built"] == built and rows(s2) == rows(s)
        print("  2. second call: same store, not rebuilt")

        try:                                                                # 3
            s2.add(ox.Quad(ox.NamedNode("http://example.org/x"), ox.NamedNode("http://example.org/p"),
                           ox.Literal("y")))
            raise AssertionError("a read-only store accepted a triple")
        except RuntimeError:
            print("  3. the store is read-only")
        del s, s2

        new = FACTS + "<http://example.org/w4> <http://example.org/monitors> <http://example.org/u2> .\n"
        (kg / f"lulcw_kg_{D}.ttl").write_text(new)                          # 4
        try:
            store.persisted_store(D, kg)
            raise AssertionError("a stale release was served")
        except release.StaleRelease as e:
            assert "facts" in str(e), e
        print("  4. facts changed after the release: refused (StaleRelease)")

        write_release(kg, new)                                              # 5
        s = store.persisted_store(D, kg)
        assert len(rows(s)) == 4 and store.read_record(D, kg)["triples"] == 6, rows(s)
        print("  5. new release: store rebuilt, 6 triples")
        del s

        tmpdir = kg / f"store_{D}.building"                                 # 6
        tmpdir.mkdir()
        (tmpdir / "junk").write_text("left by an interrupted build")
        store.record_path(D, kg).unlink()
        s = store.persisted_store(D, kg)
        assert not tmpdir.exists() and len(rows(s)) == 4
        print("  6. an interrupted build's directory is cleared; build succeeds")
        del s

        rec = store.read_record(D, kg)                                      # 7
        rec["manifest_sha256"] = "0" * 64
        store.record_path(D, kg).write_text(json.dumps(rec))
        assert not store.is_current(D, kg)
        s = store.persisted_store(D, kg)
        assert store.is_current(D, kg) and len(rows(s)) == 4
        print("  7. a record of another manifest forces a rebuild")
    print("test_store: all checks passed")


if __name__ == "__main__":
    main()
