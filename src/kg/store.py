"""The graph release as a persisted pyoxigraph store (v5 plan R2.4; Gate R2: "Oxigraph queries in < 1 s").

Until 2026-11-27, src.kg.cq.kg_store() parsed the two Turtle files of a release (the facts of
src.kg.build_kg and the rule outputs of src.kg.apply_rules: about 900,000 triples for v5) into a new
in-memory store at every call, which costs tens of seconds before the first query. This module keeps
one disk-backed store per dataset, `data/processed/kg/store_<dataset>/` (RocksDB, through pyoxigraph),
loaded once per graph release and bound to it:

- a release is the set of files src.kg.release binds by SHA-256 (facts, rules, shapes, ontology files,
  rule outputs, validation report); its manifest `lulcw_kg_<dataset>_release.json` changes whenever any
  of them changes;
- the store is loaded from the facts and the rule outputs only (the same two files, in the same default
  graph, as the in-memory store: every query answers exactly as before), and its record
  `store_<dataset>.json` holds the SHA-256 of the manifest it was loaded from;
- persisted_store() first calls release.check() (a stale release is refused, as everywhere else), then
  opens the store read-only when its record matches the current manifest, and rebuilds it otherwise.

The rebuild loads into a temporary directory, checks that the release did not change during the load,
then swaps the directories and writes the record last, so an interrupted rebuild never leaves a store
that looks current. A lock file serialises two processes that would rebuild at the same time. Opened
read-only, the store can be shared by several readers (tests, reports, the dashboard's query console)
and none of them can change it.

    from src.kg.store import persisted_store
    s = persisted_store()                     # PFE_DATASET's release; built on first use
    PFE_DATASET=v5 python -m src.kg.store     # build (or confirm) the store and print its record
"""
import fcntl
import hashlib
import json
import shutil
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone

import pyoxigraph as ox

from src.config import DATASET
from src.kg import release

KG = release.KG


def store_dir(dataset=DATASET, kg=KG):
    return kg / f"store_{dataset}"


def record_path(dataset=DATASET, kg=KG):
    return kg / f"store_{dataset}.json"


def release_files(dataset=DATASET, kg=KG):
    """The two files a store is loaded from: the facts and the rule outputs of the release."""
    p = release.paths(dataset, kg)
    return [p["facts"], p["rule_outputs"]]


def manifest_digest(dataset=DATASET, kg=KG):
    return hashlib.sha256(release.manifest_path(dataset, kg).read_bytes()).hexdigest()


def read_record(dataset=DATASET, kg=KG):
    f = record_path(dataset, kg)
    return json.loads(f.read_text()) if f.exists() else None


def is_current(dataset=DATASET, kg=KG):
    """True when the store exists and was loaded from the current release manifest."""
    r = read_record(dataset, kg)
    return (r is not None and store_dir(dataset, kg).is_dir()
            and r.get("manifest_sha256") == manifest_digest(dataset, kg))


@contextmanager
def _lock(dataset, kg):
    with open(kg / f"store_{dataset}.lock", "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def build(dataset=DATASET, kg=KG):
    """Load the release into a fresh store directory and record which manifest it came from."""
    manifest = release.check(dataset, kg)
    digest = manifest_digest(dataset, kg)
    final, tmp = store_dir(dataset, kg), kg / f"store_{dataset}.building"
    shutil.rmtree(tmp, ignore_errors=True)          # a previous interrupted build of ours
    t0 = time.time()
    s = ox.Store(str(tmp))
    for f in release_files(dataset, kg):
        s.bulk_load(path=str(f), format=ox.RdfFormat.TURTLE)
    s.flush()
    s.optimize()
    n = len(s)
    del s                                           # closes the RocksDB instance
    if manifest_digest(dataset, kg) != digest:
        shutil.rmtree(tmp, ignore_errors=True)
        raise release.StaleRelease("the release changed while its store was being loaded; run again")
    record_path(dataset, kg).unlink(missing_ok=True)  # no record while the directories are swapped
    shutil.rmtree(final, ignore_errors=True)
    tmp.rename(final)
    rec = {"dataset": dataset, "release": manifest["released"], "manifest_sha256": digest,
           "triples": n, "load_seconds": round(time.time() - t0, 1),
           "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "pyoxigraph": ox.__version__,
           "files": {str(f.name): manifest["files"][role]["sha256"]
                     for role, f in zip(("facts", "rule_outputs"), release_files(dataset, kg))}}
    out = record_path(dataset, kg)
    part = out.with_suffix(".json.part")
    part.write_text(json.dumps(rec, indent=1))
    part.replace(out)                               # the record is written last
    return rec


def persisted_store(dataset=DATASET, kg=KG):
    """A read-only pyoxigraph store of the current validated release of `dataset` (built on first use
    and after every new release); release.StaleRelease when the graph files form no release."""
    release.check(dataset, kg)
    if not is_current(dataset, kg):
        with _lock(dataset, kg):
            if not is_current(dataset, kg):         # another process may have built it meanwhile
                build(dataset, kg)
    return ox.Store.read_only(str(store_dir(dataset, kg)))


def main():
    t = time.time()
    current = is_current() if release.manifest_path().exists() else False
    persisted_store()
    print(("store already current" if current else "store built") + f" in {time.time() - t:.1f} s")
    print(json.dumps(read_record(), indent=1))


if __name__ == "__main__":
    sys.exit(main())
