"""Offline citation checks for CLAUDE.md §6 rule 9 and the T02b review fixes.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_citation_audit

Check DOI punctuation, publisher URL tails, arXiv versions, one nearby year per citing line,
and the generated tables. Fixtures stay in memory. Mutated identifiers are parser test strings,
not claims about papers. Build those strings at runtime so they do not become audit citations.
"""
from html import unescape
from pathlib import Path
from unittest.mock import patch

from src.analysis import citation_audit as audit

DOI = "10.5194/hess-28-525-2024"
ARXIV = "arXiv:1703.03717"
LEGACY = "10.1016/0022-1694(70)90255-6"
# The second DOI is the parsing fixture supplied in T02b, not a new literature reference.
LEGACY_OTHER = "10.1016" + "/S0022-1694(01)00421-8"


def extract(text):
    return [identifier for identifier, _, _ in audit.identifiers(text)]


def scan_text(text):
    with patch.object(Path, "read_text", return_value=text):
        return audit.scan([Path("fixture.md")])


def selected_year(text, identifier=DOI):
    for found, start, end in audit.identifiers(text):
        if found == identifier:
            return audit.nearest_year(text, start, end)
    raise AssertionError(f"Fixture does not contain {identifier}")


def test_normalization():
    wrappers = f'**doi:{DOI.upper()}** [{DOI}] ({DOI}) <{DOI}> "{DOI}" `{DOI}`'
    assert extract(wrappers) == [DOI] * 6
    assert extract(DOI + ".,;:") == [DOI]
    inner_dots = "10.14778/3712221.3712222"
    assert extract(inner_dots) == [inner_dots]
    assert extract(ARXIV + "v2 https://arxiv.org/abs/1703.03717v3") == [ARXIV, ARXIV]
    assert extract(ARXIV.upper() + "V2") == [ARXIV]
    assert extract(ARXIV[:-1]) == [ARXIV[:-1]]
    assert extract("arXiv: arxiv.org/abs/") == []
    assert not audit.suspicious(DOI) and not audit.suspicious(ARXIV)
    print("  1. DOI case, punctuation, Markdown, inner dots, and arXiv lengths and versions")


def test_balanced_dois():
    square = LEGACY.replace("(", "[").replace(")", "]")
    nested = LEGACY.replace("(70)", "([70])")
    for identifier in (LEGACY, LEGACY_OTHER, square, nested):
        expected = identifier.lower()
        assert extract(identifier) == [expected]
        assert extract(f"(Nash 1970, doi:{identifier})") == [expected]
        assert extract(f"[doi:{identifier}]") == [expected]
        assert not audit.suspicious(expected)
    assert extract(f"({LEGACY})[{DOI}]") == [LEGACY, DOI]
    assert extract(LEGACY + ") ignored") == [LEGACY]
    assert extract(LEGACY + "] ignored") == [LEGACY]
    for broken in (LEGACY.split(")")[0], LEGACY.replace("(70)", "[70)")):
        assert audit.suspicious(extract(broken)[0])
    print("  2. both legacy Elsevier DOIs, balanced and nested brackets, and outer closers")


def test_url_tails():
    frontiers = "10.3389/feart.2022.907609"
    for tail in ("pdf", "full", "abstract", "epdf", "html"):
        url = f"https://www.frontiersin.org/articles/{frontiers}/{tail}"
        assert extract(url) == [frontiers]
        assert extract(f"(doi:{frontiers}/{tail.upper()}.,;:)") == [frontiers]
        identifier, start, end = next(audit.identifiers(url))
        assert url[start:end] == identifier
    assert extract(frontiers + "/pdf/full") == [frontiers + "/pdf"]
    assert extract(frontiers + "/fulltext") == [frontiers + "/fulltext"]
    assert extract(frontiers + "/pdf/more") == [frontiers + "/pdf/more"]
    bare_suffix = DOI.split("/")[0] + "/pdf"
    assert extract(bare_suffix) == [bare_suffix] and not audit.suspicious(bare_suffix)
    print("  3. all five publisher tails stripped once; other and inner segments retained")


def test_malformed():
    for month in ("00", "13"):
        bad_month = ARXIV.replace("1703", "17" + month)
        assert audit.suspicious(extract(bad_month)[0])
    assert audit.suspicious(ARXIV[:-3])
    for suffix in ("", "ab", "truncated-", "odd…", "odd?", "odd*inside"):
        candidate = DOI.split("/")[0] + "/" + suffix
        assert extract(candidate) == [candidate]
        assert audit.suspicious(candidate)
    print("  4. empty, short, truncated and odd DOI suffixes; arXiv months and truncation")


def test_year_selection():
    assert selected_year(f"2017 Author 2024, doi:{DOI}; read 2026") == 2024
    assert selected_year(f"2017 {' ' * 10}{DOI} 2024") == 2017
    assert selected_year(f"doi:{DOI}, 2024; read 2026") == 2024
    assert selected_year(DOI) is None
    assert selected_year(f"11950 {DOI} 12026") is None
    assert selected_year(f"1949 {DOI} 2030") is None
    assert selected_year("1950" + " " * 76 + DOI) == 1950
    assert selected_year("1950" + " " * 77 + DOI) is None
    assert selected_year(DOI + " " * 76 + "2029") == 2029
    assert selected_year(DOI + " " * 77 + "2029") is None
    assert selected_year("11950" + " " * 76 + DOI) is None
    multiple = scan_text(f"Ross 2017 {ARXIV}; Heudorfer 2024 {DOI}; read 2026")
    assert multiple[ARXIV][0].years == {2017} and multiple[DOI][0].years == {2024}
    repeated = scan_text(f"2017 {ARXIV}v2; 2023 {ARXIV}v3")
    assert len(repeated[ARXIV]) == 1 and repeated[ARXIV][0].years == {2017}
    repeated_case = scan_text(f"2024 {DOI.upper()} {DOI}")
    assert len(repeated_case[DOI]) == 1 and repeated_case[DOI][0].years == {2024}
    print("  5. nearest preceding year, following fallback, boundaries, and one year per line")


def test_tables():
    text = "\n".join((f"2017 {ARXIV}v2; 2023 {ARXIV}v3",
                      f"2024 {DOI} | `<tag>` " + "x" * 120,
                      DOI.upper(), f"2023 {ARXIV}"))
    citations = scan_text(text)
    assert len(citations[ARXIV]) == 2 and len(citations[DOI]) == 2
    assert [hit.years for hit in citations[ARXIV]] == [{2017}, {2023}]
    assert [hit.years for hit in citations[DOI]] == [{2024}, set()]
    report, counts = audit.render([Path("fixture.md")], citations, {ARXIV}, "2026-11-16")
    assert counts == {"files": 1, "identifiers": 2, "checked": 1, "not checked": 1,
                      "malformed or suspicious": 0, "possibly inconsistent": 1}
    assert report == audit.render([Path("fixture.md")], citations, {ARXIV}, "2026-11-16")[0]
    assert "fixture.md:2<br>fixture.md:3" in report
    assert "fixture.md:1 (2017)<br>fixture.md:4 (2023)" in report
    assert "&#124;" in report and "&lt;tag&gt;" in report and "&#96;" in report
    first_table = report.split("## Table 2")[0]
    row = next(line for line in first_table.splitlines() if line.startswith("| " + DOI))
    excerpt = unescape(row.split(" | ")[-1].removesuffix(" |"))
    assert len(excerpt) == 100 and excerpt.endswith("...")
    unordered = dict(reversed(list(citations.items())))
    all_unchecked = audit.render([Path("fixture.md")], unordered, set(), "2026-11-16")[0]
    rows = [line for line in all_unchecked.split("## Table 2")[0].splitlines()
            if line.startswith("| 10.") or line.startswith("| arXiv:")]
    assert [line.split(" | ")[0].removeprefix("| ") for line in rows] == sorted(citations)
    empty, empty_counts = audit.render([], {}, set(), "2026-11-16")
    assert not any(empty_counts.values()) and empty.count("None found.") == 3
    print("  6. unique places, real year conflicts, excerpts, escaping, ordering and empty tables")


def test_scope_and_checked():
    expected = {Path("fixture" + extension) for extension in audit.EXTENSIONS}
    listed = "\0".join(str(path) for path in expected | {audit.OUTPUT, Path("ignored.txt")}) + "\0"
    with patch.object(audit, "git", return_value=listed):
        assert audit.tracked_files() == sorted(expected)
    fragment = "10." + "1038/"
    note = f"Verified: {DOI}. Audit note: truncated `{fragment}`."
    with patch.object(Path, "read_text", return_value=note):
        assert fragment in audit.scan(audit.CHECKED)
        assert audit.checked_identifiers() == {DOI}
    print("  7. tracked extensions, generated-file exclusion, and empty fragments in checked notes")


if __name__ == "__main__":
    test_normalization()
    test_balanced_dois()
    test_url_tails()
    test_malformed()
    test_year_selection()
    test_tables()
    test_scope_and_checked()
    print("test_citation_audit: all checks passed")
