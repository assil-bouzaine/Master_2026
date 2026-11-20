"""Check the paper bibliography tool on temporary fixtures with the network blocked.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_fetch_bib
"""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from paper.tools import fetch_bib as B

DOI = "10.99999/example(1)/metadata"
ARXIV = "arXiv:2601.01234"
MISSING = "10.99999/uncached"
DOI_RECORD = r"""@article{doi-original,
  title = {{Hydrology} of {Nested} Wells, with Examples},
  author = {Garc{\'i}a, Alice and {Lab of Soil and Water}},
  year = {2022},
  note = {Preserve the publisher's fields, braces and punctuation.}
}
"""
ARXIV_RECORD = """@misc(arxiv-original,
  author = "Boris García and Chen, Dana",
  title = "{Hydrology} observations" # { in wells},
  year = 2022,
  eprint = {2601.01234},
)
"""
EXISTING = b"% Existing complete bibliography.\r\n@misc{keep, title={Keep these bytes}}\r\n"


def test_identifiers(reading_list):
    reading_list.write_text(
        f"A DOI [doi:{DOI.upper()}], repeated as https://doi.org/{DOI}.\n"
        "An arXiv preprint (2601.01234v3), also https://arxiv.org/abs/2601.01234v1.\n"
        f"A missing record doi:{MISSING}. A truncated prefix in an audit note: `10.99999/`.\n",
        encoding="utf-8",
    )
    assert B.collect_identifiers(reading_list) == [DOI, MISSING, ARXIV]
    print("  1. The shared parser finds DOI and arXiv IDs, handles the preprint spelling and deduplicates.")


def test_empty(reading_list, cache, refs):
    refs.write_bytes(EXISTING)
    captured = StringIO()
    with redirect_stdout(captured):
        assert B.main(["--offline"], reading_list, cache, refs) == 2
    assert refs.read_bytes() == EXISTING
    for identifier in (DOI, MISSING, ARXIV):
        assert f"Missing {identifier}" in captured.getvalue()
    assert "refs.bib left unchanged: 0 of 3 identifiers have a record" in captured.getvalue()
    print("  2. An empty cache lists every missing identifier and preserves the bibliography's bytes.")


def test_offline(reading_list, cache, refs):
    cache.mkdir()
    # Create the files in reverse identifier order. The collision suffixes depend on their IDs.
    fixtures = [(ARXIV, "2026-01-09", ARXIV_RECORD), (DOI, "2026-01-08", DOI_RECORD)]
    for identifier, date, record in fixtures:
        path = B.cache_path(cache, identifier)
        assert path.parent == cache and "/" not in path.name
        path.write_text(f"% fetched {date}\n{record}", encoding="utf-8")
    before = {path.name: path.read_bytes() for path in cache.iterdir()}
    partial = refs.with_name("partial.bib")
    captured = StringIO()
    with redirect_stdout(captured):
        assert B.main(["--offline"], reading_list, cache, refs) == 2
        assert not partial.exists()
        assert B.main(["--offline", "--partial-out", str(partial)], reading_list, cache, refs) == 2
        first = partial.read_text(encoding="utf-8")
        assert B.main(["--offline", "--partial-out", str(partial)], reading_list, cache, refs) == 2
    assert refs.read_bytes() == EXISTING
    assert captured.getvalue().count(f"Missing {MISSING}") == 3
    assert captured.getvalue().count("refs.bib left unchanged: 2 of 3 identifiers have a record") == 3
    assert captured.getvalue().count("Wrote 2 entries") == 2
    assert first == partial.read_text(encoding="utf-8")
    assert first == (f"% {DOI}, fetched 2026-01-08\n"
                     + DOI_RECORD.replace("doi-original", "Garcia2022Hydrologya")
                     + f"\n% {ARXIV}, fetched 2026-01-09\n"
                     + ARXIV_RECORD.replace("arxiv-original", "Garcia2022Hydrologyb"))
    assert {path.name: path.read_bytes() for path in cache.iterdir()} == before
    print("  3. Partial exports preserve both cached records, their stable keys and dates, and the existing refs.")


def test_complete(reading_list, cache, refs):
    reading_list.write_text(f"doi:{DOI}\narXiv:2601.01234\n", encoding="utf-8")
    entries, failed = B._cached_entries(cache)
    assert failed == 0
    expected, count = B._render(entries)
    assert count == 2
    before = {path.name: path.read_bytes() for path in cache.iterdir()}
    captured = StringIO()
    with redirect_stdout(captured):
        assert B.main(["--offline"], reading_list, cache, refs) == 0
        first = refs.read_bytes()
        assert B.main(["--offline"], reading_list, cache, refs) == 0
    assert first == expected.encode("utf-8") == refs.read_bytes()
    assert "Missing" not in captured.getvalue()
    assert captured.getvalue().count("Wrote 2 entries") == 2
    assert {path.name: path.read_bytes() for path in cache.iterdir()} == before
    print("  4. A complete offline refresh matches the renderer byte for byte and is repeatable.")


def test_cache_errors(reading_list, cache, refs):
    before = refs.read_bytes()
    broken = B.cache_path(cache, MISSING)
    broken.write_text("This is not a BibTeX record.\n", encoding="utf-8")
    # Even an unrelated broken record makes the refresh unsafe.
    for wanted, found in ((f"doi:{DOI}\n", 1), (f"doi:{DOI}\ndoi:{MISSING}\n", 1)):
        reading_list.write_text(wanted, encoding="utf-8")
        captured, errors = StringIO(), StringIO()
        with redirect_stdout(captured), redirect_stderr(errors):
            assert B.main(["--offline"], reading_list, cache, refs) == 2
        assert refs.read_bytes() == before
        total = len(B.collect_identifiers(reading_list))
        assert f"refs.bib left unchanged: {found} of {total} identifiers have a record" in captured.getvalue()
        assert "Cache error" in errors.getvalue()
        if total == 2:
            assert f"Missing {MISSING}" in captured.getvalue()
    print("  5. Malformed records block a refresh, even when they are outside the reading list.")


def test_partial_destination(reading_list, cache, refs):
    alias = refs.with_name("refs-alias.bib")
    alias.symlink_to(refs)
    before = refs.read_bytes()
    for destination in (refs, alias):
        with redirect_stderr(StringIO()):
            try:
                B.main(["--offline", "--partial-out", str(destination)], reading_list, cache, refs)
            except SystemExit as error:
                assert error.code == 2
            else:
                raise AssertionError("a partial export was allowed to replace refs.bib")
        assert refs.read_bytes() == before
    print("  6. A partial destination cannot name refs.bib directly or through a symlink.")


def main():
    scratch = B.ROOT / "results" / "_agents" / "tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=scratch) as tmp, \
            patch.object(B, "make_session", side_effect=AssertionError("network")) as session:
        root = Path(tmp)
        reading_list, cache, refs = root / "reading_list.md", root / "cache", root / "refs.bib"
        test_identifiers(reading_list)
        test_empty(reading_list, cache, refs)
        test_offline(reading_list, cache, refs)
        test_complete(reading_list, cache, refs)
        test_cache_errors(reading_list, cache, refs)
        test_partial_destination(reading_list, cache, refs)
        session.assert_not_called()
    print("test_fetch_bib: all checks passed")


if __name__ == "__main__":
    main()
