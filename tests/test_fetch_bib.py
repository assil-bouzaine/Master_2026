"""Check the paper bibliography tool on temporary fixtures with the network blocked.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_fetch_bib
"""
from contextlib import redirect_stdout
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


def test_identifiers(reading_list):
    reading_list.write_text(
        f"A DOI [doi:{DOI.upper()}], repeated as https://doi.org/{DOI}.\n"
        "An arXiv preprint (2601.01234v3), also https://arxiv.org/abs/2601.01234v1.\n"
        f"A missing record doi:{MISSING}. A truncated prefix in an audit note: `10.99999/`.\n",
        encoding="utf-8",
    )
    assert B.collect_identifiers(reading_list) == [DOI, MISSING, ARXIV]
    print("  1. The shared parser finds DOI and arXiv IDs, handles the preprint spelling and deduplicates.")


def test_offline(reading_list, cache, refs):
    cache.mkdir()
    # Create the files in reverse identifier order. The collision suffixes depend on their IDs.
    fixtures = [(ARXIV, "2026-01-09", ARXIV_RECORD), (DOI, "2026-01-08", DOI_RECORD)]
    for identifier, date, record in fixtures:
        path = B.cache_path(cache, identifier)
        assert path.parent == cache and "/" not in path.name
        path.write_text(f"% fetched {date}\n{record}", encoding="utf-8")
    before = {path.name: path.read_bytes() for path in cache.iterdir()}
    args = {"READING_LIST": reading_list, "CACHE": cache, "REFS": refs}
    with patch.multiple(B, **args), patch.object(B, "make_session", side_effect=AssertionError("network")) as session:
        captured = StringIO()
        with redirect_stdout(captured):
            assert B.main(["--offline"]) == 0
            first = refs.read_text(encoding="utf-8")
            assert B.main(["--offline"]) == 0
        session.assert_not_called()
    assert captured.getvalue().count(f"Missing {MISSING}") == 2
    assert captured.getvalue().count("Wrote 2 entries") == 2
    assert first == refs.read_text(encoding="utf-8")
    assert first == (f"% {DOI}, fetched 2026-01-08\n"
                     + DOI_RECORD.replace("doi-original", "Garcia2022Hydrologya")
                     + f"\n% {ARXIV}, fetched 2026-01-09\n"
                     + ARXIV_RECORD.replace("arxiv-original", "Garcia2022Hydrologyb"))
    assert {path.name: path.read_bytes() for path in cache.iterdir()} == before
    print("  2. Offline output preserves both records, normalizes the keys and adds stable a/b suffixes.")


def main():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        reading_list = root / "reading_list.md"
        test_identifiers(reading_list)
        test_offline(reading_list, root / "cache", root / "refs.bib")
    print("test_fetch_bib: all checks passed")


if __name__ == "__main__":
    main()
