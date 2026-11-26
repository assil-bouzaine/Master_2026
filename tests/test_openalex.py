"""Offline checks for the fixed R2.1 Track 1 harvest (docs/v5_plan.md, row 2.1).

    PFE_DATASET=v5 python -m tests.test_openalex

All records below are synthetic, not references to real papers. Their field
names follow the OpenAlex Work / Location / Source schema: id, doi, title,
publication_year, language, is_retracted, best_oa_location.pdf_url, .license,
and primary_location.source.display_name. No actual API response was obtained
for this task.
Both requests' network entry point and the production session factory are
patched to fail. All writes use a throw-away directory, including the CSV.
"""
import contextlib
import csv
import hashlib
import io
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import requests

from src.ingest import openalex as oa

DAY = "2026-11-26"
SEARCHES = [
    "groundwater irrigation Mediterranean aquifer overexploitation",
    "land use change groundwater recharge Mediterranean",
    "irrigation canal return flow aquifer recharge",
    "groundwater level decline irrigation Spain",
    "groundwater depletion irrigation Tunisia",
    "groundwater irrigation aquifer Morocco",
    "drought groundwater level Mediterranean",
    "nitrate groundwater agriculture Mediterranean",
    "seawater intrusion coastal aquifer pumping Mediterranean",
    "olive orchard vineyard irrigation groundwater",
]
PDF = b"%PDF-1.4 synthetic offline fixture\n"


def work(number, **changes):
    record = {
        "id": f"https://openalex.org/W{number}",
        "doi": f"https://doi.org/10.0000/offline-fixture-{number}",
        "title": f"Synthetic fixture {number}: eau et irrigation",
        "publication_year": 2020, "language": "en", "is_retracted": False,
        "primary_location": {"source": {"display_name": "Synthetic fixture venue"}},
        "best_oa_location": {
            "pdf_url": f"https://example.invalid/{number}.pdf", "license": "cc-by",
            "source": {"display_name": "Synthetic fixture repository"},
        },
    }
    record.update(changes)
    return record


def payload(records):
    return {"meta": {"count": len(records)}, "results": records}


class Response:
    def __init__(self, body, status=200, headers=None, chunks=None, interrupt=False):
        self.content, self.status = body, status
        self.headers = headers or {}
        self.chunks, self.interrupt = chunks, interrupt
        self.closed = False

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError(f"synthetic HTTP {self.status}")

    def iter_content(self, chunk_size):
        yield from (self.chunks if self.chunks is not None else [self.content])
        if self.interrupt:
            raise requests.ConnectionError("synthetic interrupted stream")

    def close(self):
        self.closed = True


class Session:
    """Allow only explicitly supplied fixture responses; all other URLs fail."""
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.headers = {"Authorization": "must-be-removed", "User-Agent": "must-be-replaced"}
        self.cookies = requests.cookies.RequestsCookieJar()
        self.cookies.set("private", "must-be-removed")
        self.auth, self.trust_env = ("private", "must-be-removed"), True
        self.calls = []

    def get(self, url, **kwargs):
        assert self.headers == {"User-Agent": "pfe-research-harvest/1.0"}, self.headers
        assert self.auth is None and not self.trust_env and not self.cookies
        self.calls.append((url, kwargs))
        key = kwargs.get("params", {}).get("search", url)
        assert key in self.responses, f"unrecorded request: {key}"
        return self.responses[key]


def run_in(out, command, session=None, **kwargs):
    return oa.run(command, DAY, out=out / "raw", papers=out / "configs" / "track1_papers.csv",
                  session=session, **kwargs)


def cache(out, pages):
    folder = out / "raw" / DAY
    folder.mkdir(parents=True, exist_ok=True)
    for query, records in zip(oa.load_config()["queries"], pages):
        (folder / f'{query["id"]}.json').write_text(
            json.dumps(payload(records)), encoding="utf-8")
    return folder


def tree_bytes(out):
    return {str(path.relative_to(out)): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in out.rglob("*") if path.is_file()}


def check_design():
    config = oa.load_config()
    assert [q["id"] for q in config["queries"]] == [f"q{i:02d}" for i in range(1, 11)]
    assert [q["search"] for q in config["queries"]] == SEARCHES
    assert config["target"] == 30 and config["max_pdf_bytes"] == 25 * 1024 * 1024
    assert config["request_interval_seconds"] == 1
    for query in config["queries"]:
        params = oa.request_parameters(config, query)
        assert params == {
            "search": query["search"],
            "filter": "open_access.is_oa:true,type:article,from_publication_date:2010-01-01",
            "per_page": 25, "sort": "relevance_score:desc",
        }, params
        url = urlsplit(oa.request_url(config, query))
        assert url.scheme == "https" and url.netloc == "api.openalex.org" and url.path == "/works"
        assert parse_qs(url.query) == {k: [str(v)] for k, v in params.items()}
        assert not url.username and not url.password and "@" not in str(params)
    session = Session({"https://example.invalid/a": Response(PDF)})
    requester = oa.Requester(config, session)
    requester.get("https://example.invalid/a")
    with patch.object(oa.time, "monotonic", return_value=requester.last_request + 0.25), \
            patch.object(oa.time, "sleep") as sleep:
        requester.get("https://example.invalid/a")
    sleep.assert_called_once_with(0.75)


def check_eligibility():
    records = [work(1), work(2, doi=None), work(3, best_oa_location=None),
               work(4, language="es"), work(5, is_retracted=True), work(6, title=None),
               work(7, language="fr"), work(8, best_oa_location={"pdf_url": None}),
               work(9, title=" "), work(10, doi=" ")]
    rows, counts = oa.eligible_rows(payload(records), "q01")
    assert [r["openalex_id"] for r in rows] == [work(1)["id"], work(7)["id"]]
    assert [r["rank_in_query"] for r in rows] == [1, 7]
    assert counts == {"returned": 10, "eligible": 2, "rejected": {
        "missing DOI": 2, "missing PDF URL": 2, "language outside en/fr": 1,
        "retracted": 1, "missing title": 2,
    }}, counts
    sparse = work(11, best_oa_location={"pdf_url": "https://example.invalid/11.pdf"},
                  primary_location=None)
    row = oa.eligible_rows(payload([sparse]), "q02")[0][0]
    assert row["licence"] == "" and row["venue"] == ""


def check_selection():
    pages = [[work(i + 10 * rank) for rank in range(4)] for i in range(1, 11)]
    pages[1][0] = work(101, doi=work(1)["doi"].upper())
    pages[2][0] = work(102, id=work(1)["id"])
    pages[3] = [work(4)]  # This query runs out before the next round.
    rows = [oa.eligible_rows(payload(page), f"q{i:02d}")[0]
            for i, page in enumerate(pages, 1)]
    selected = list(oa.round_robin(rows))[:30]
    expected = [1, 4, 5, 6, 7, 8, 9, 10,
                11, 12, 13, 15, 16, 17, 18, 19, 20,
                21, 22, 23, 25, 26, 27, 28, 29, 30, 31, 32, 33, 35]
    assert [r["openalex_id"] for r in selected] == [work(i)["id"] for i in expected]
    assert len({r["doi"].casefold() for r in selected}) == 30
    assert len({r["openalex_id"] for r in selected}) == 30
    assert list(oa.round_robin([])) == []
    assert len(list(oa.round_robin([rows[0][:1], [], rows[1][:1]]))) == 1


def check_search_and_dry_run(out):
    responses = {query: Response(json.dumps(payload([work(i)])).encode("utf-8"))
                 for i, query in enumerate(SEARCHES, 1)}
    session = Session(responses)
    rows = run_in(out, "search", session)
    assert len(rows) == 10 and len(session.calls) == 10
    for (url, kwargs), query in zip(session.calls, oa.load_config()["queries"]):
        assert url == "https://api.openalex.org/works"
        assert kwargs == {"params": oa.request_parameters(oa.load_config(), query), "timeout": oa.TIMEOUT}
    assert all(r.closed for r in responses.values())
    folder = out / "raw" / DAY
    raw_before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.glob("q*.json")}
    papers = out / "configs" / "track1_papers.csv"
    first = papers.read_bytes()
    session = Session()
    run_in(out, "search", session)
    assert not session.calls and papers.read_bytes() == first
    assert raw_before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.glob("q*.json")}
    manifest = json.loads((folder / "harvest.json").read_text(encoding="utf-8"))
    assert manifest["selected"] == 10
    assert all(q["eligible"] == 1 and q["returned"] == 1 and q["retrieved_at"]
               and q["request_url"] for q in manifest["queries"].values())
    before = tree_bytes(out)
    with contextlib.redirect_stdout(io.StringIO()) as output:
        assert run_in(out, "select", dry_run=True) == rows
    assert "order,query_id,rank_in_query" in output.getvalue()
    assert tree_bytes(out) == before
    assert not list(out.rglob("*.part"))


def check_search_resume(out):
    responses = {query: Response(json.dumps(payload([work(i)])).encode("utf-8"))
                 for i, query in enumerate(SEARCHES, 1)}
    responses[SEARCHES[1]] = Response(b"unavailable", status=503)
    try:
        run_in(out, "search", Session(responses))
    except requests.HTTPError:
        pass
    else:
        raise AssertionError("the failed search was accepted")
    folder = out / "raw" / DAY
    first = (folder / "q01.json").read_bytes()
    assert not (folder / "q02.json").exists() and not list(out.rglob("*.part"))
    manifest = json.loads((folder / "harvest.json").read_text(encoding="utf-8"))
    assert set(manifest["queries"]) == {"q01"}
    retrieved = manifest["queries"]["q01"]["retrieved_at"]
    responses[SEARCHES[1]] = Response(json.dumps(payload([work(2)])).encode("utf-8"))
    session = Session(responses)
    assert len(run_in(out, "search", session)) == 10
    assert [kwargs["params"]["search"] for _, kwargs in session.calls] == SEARCHES[1:]
    assert (folder / "q01.json").read_bytes() == first
    manifest = json.loads((folder / "harvest.json").read_text(encoding="utf-8"))
    assert manifest["queries"]["q01"]["retrieved_at"] == retrieved


def check_downloads(out):
    pages = [[work(i + rank * 10) for rank in range(4)] for i in range(1, 11)]
    folder = cache(out, pages)
    (folder / "pdf").mkdir()
    (folder / "pdf" / "W4.pdf").write_bytes(PDF)
    maximum = oa.load_config()["max_pdf_bytes"]
    responses = {work(i)["best_oa_location"]["pdf_url"]: Response(PDF) for i in range(1, 41)}
    responses[work(1)["best_oa_location"]["pdf_url"]] = Response(b"<html>not a PDF</html>")
    responses[work(2)["best_oa_location"]["pdf_url"]] = Response(
        PDF, headers={"Content-Length": str(maximum + 1)})
    responses[work(3)["best_oa_location"]["pdf_url"]] = Response(b"unavailable", status=503)
    responses[work(5)["best_oa_location"]["pdf_url"]] = Response(
        b"", chunks=[b"%PDF-", b"x" * maximum])  # Size limit also works without a header.
    session = Session(responses)
    published = []
    replace = Path.replace

    def inspect_replace(source, target):
        source, target = Path(source), Path(target)
        assert source.suffix == ".part" and source.exists()
        if target.suffix == ".pdf":
            assert not target.exists()
            assert source.read_bytes().startswith(b"%PDF-")
            published.append(target.name)
        return replace(source, target)

    with patch.object(Path, "replace", inspect_replace):
        rows = run_in(out, "download", session)
    failed = [r for r in rows if r["download_status"] == "failed"]
    assert [r["openalex_id"] for r in failed] == [work(i)["id"] for i in [1, 2, 3, 5]]
    for row, reason in zip(failed, ["%PDF-", "Content-Length", "HTTP 503", "stream"]):
        assert reason in row["download_reason"], row
        assert row["file_size"] == "" and row["sha256"] == ""
    good = [r for r in rows if r["download_status"] == "downloaded"]
    assert [r["openalex_id"] for r in rows] == [work(i)["id"] for i in range(1, 35)]
    assert len(good) == 30 and len(list((folder / "pdf").glob("*.pdf"))) == 30
    assert len(published) == 29 and "W4.pdf" not in published
    assert work(4)["best_oa_location"]["pdf_url"] not in [url for url, _ in session.calls]
    assert all(r["file_size"] == len(PDF) and r["sha256"] == hashlib.sha256(PDF).hexdigest() for r in good)
    assert not list(out.rglob("*.part"))
    papers = out / "configs" / "track1_papers.csv"
    with papers.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == list(oa.COLUMNS)
        recorded = list(reader)
    assert len(recorded) == 34 and recorded[0]["venue"] == "Synthetic fixture venue"
    assert recorded[0]["licence"] == "cc-by" and "eau et irrigation" in recorded[0]["title"]
    first = papers.read_bytes()
    # An interrupted second run must not erase failures later in the journal.
    original = oa.download_pdf

    def interrupt_second(row, *args):
        if row["openalex_id"] == work(4)["id"]:
            raise KeyboardInterrupt("synthetic process interruption")
        return original(row, *args)

    with patch.object(oa, "download_pdf", side_effect=interrupt_second):
        try:
            run_in(out, "download", Session())
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError("the interrupted re-run did not stop")
    session = Session()
    assert run_in(out, "download", session) == rows
    assert papers.read_bytes() == first
    assert not session.calls  # Both prior failures and complete PDFs are cached.
    assert run_in(out, "search", session) == rows
    assert not session.calls and papers.read_bytes() == first
    manifest = json.loads((folder / "harvest.json").read_text(encoding="utf-8"))
    assert manifest["failed"] == 4 and manifest["selected"] == 30
    assert manifest["download_started_at"] and manifest["download_completed_at"]


def check_failures(out):
    folder = cache(out, [[work(1)], [], [], [], [], [], [], [], [], []])
    response = Response(PDF, interrupt=True)
    rows = run_in(out, "download", Session({work(1)["best_oa_location"]["pdf_url"]: response}))
    assert len(rows) == 1 and rows[0]["download_status"] == "failed"
    assert "interrupted stream" in rows[0]["download_reason"]
    assert response.closed and not list(out.rglob("*.part"))
    assert not list((folder / "pdf").glob("*.pdf"))
    existing_out = out / "existing"
    existing_folder = cache(existing_out, [[work(1)], [], [], [], [], [], [], [], [], []])
    (existing_folder / "pdf").mkdir()
    (existing_folder / "pdf" / "W1.pdf").write_bytes(b"invalid existing PDF")
    rows = run_in(existing_out, "download", Session())
    assert rows[0]["download_status"] == "failed" and "%PDF-" in rows[0]["download_reason"]
    assert (existing_folder / "pdf" / "W1.pdf").read_bytes() == b"invalid existing PDF"
    (folder / "q10.json").unlink()
    before = tree_bytes(out)
    try:
        run_in(out, "select", dry_run=True)
    except FileNotFoundError as error:
        assert "run search" in str(error)
    else:
        raise AssertionError("an incomplete cache was accepted")
    assert tree_bytes(out) == before


def main():
    started = time.monotonic()
    print("Fixture keys:", sorted(work(1)))
    print("Fixture sample:", json.dumps(work(1)))
    with patch("requests.sessions.Session.request", side_effect=AssertionError("network forbidden")), \
            patch.object(oa, "make_session", side_effect=AssertionError("real session forbidden")), \
            patch.object(oa.time, "sleep"):
        check_design()
        print("  1. ten fixed queries, exact parameters, generic headers and one-second spacing")
        check_eligibility()
        print("  2. all eligibility exclusions and original response ranks")
        check_selection()
        print("  3. expected 30 candidates, duplicate DOI/id, uneven and empty query lists")
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            with contextlib.redirect_stdout(io.StringIO()):
                check_search_and_dry_run(out / "search")
                check_search_resume(out / "resume")
                check_downloads(out / "downloads")
                check_failures(out / "failures")
        print("  4. search caches ten pages once; re-run CSV identical; select writes nothing")
        print("  5. failed downloads replaced in order; 30 PDFs; size/hash and all CSV columns")
        print("  6. existing PDFs reused, atomic writes, interrupted runs resume, incomplete cache refused")
    print(f"test_openalex: all checks passed ({time.monotonic() - started:.2f} s)")


if __name__ == "__main__":
    main()
