"""Interrupted document downloads (src.ingest.documents; Codex review of 2026-11-06, S2).

    python -m tests.test_documents

On a throw-away directory, with a stand-in HTTP session (no network):
1. a failure on the second document leaves the first one complete and described by the index, and
   no partial file;
2. the next run downloads only the missing document and keeps the first entry and its date;
3. a stored copy without an index entry (a lost index) is fetched again, found identical and dated
   by that fetch with a note, never by a guessed date;
4. such a copy that differs from the source is refused;
5. a stored copy that changed after it was indexed is refused (the md5 check).
"""
import json
import tempfile
from pathlib import Path

from src.ingest import documents

DOCS = {"a": {"url": "https://example.org/a.pdf", "title": "A"},
        "b": {"url": "https://example.org/b.html", "kind": "html", "title": "B"}}
BODY = {"https://example.org/a.pdf": b"%PDF-1.4 a", "https://example.org/b.html": b"<html>b</html>"}


class Response:
    def __init__(self, content, ok=True):
        self.content, self.ok = content, ok

    def raise_for_status(self):
        if not self.ok:
            raise ConnectionError("connection reset (stand-in)")


class Session:
    """Serves BODY; `fail` names URLs that fail; `calls` records every request."""
    def __init__(self, fail=(), body=None):
        self.fail, self.body, self.calls = set(fail), body or BODY, []

    def get(self, url, timeout=None):
        self.calls.append(url)
        return Response(self.body[url], ok=url not in self.fail)


def refused(out, session, text):
    try:
        documents.main(out, DOCS, session)
    except (RuntimeError, AssertionError) as e:
        assert text in str(e), e
        return
    raise AssertionError(f"accepted: {text}")


def main():
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        try:
            documents.main(out, DOCS, Session(fail={"https://example.org/b.html"}))
            raise AssertionError("the failing download did not raise")
        except ConnectionError:
            pass
        log = json.loads((out / "documents.json").read_text())
        assert set(log) == {"a"} and (out / "a.pdf").read_bytes() == BODY["https://example.org/a.pdf"], log
        assert not (out / "b.html").exists() and not list(out.glob("*.part")), list(out.iterdir())
        print("  1. a failure on the second document: the first is complete and indexed, no partial file")

        first = log["a"]["retrieved"]
        s = Session()
        log = documents.main(out, DOCS, s)
        assert s.calls == ["https://example.org/b.html"], s.calls
        assert set(log) == {"a", "b"} and log["a"]["retrieved"] == first and "note" not in log["a"], log
        print("  2. the next run downloads only the missing document and keeps the first entry")

        (out / "documents.json").unlink()
        s = Session()
        log = documents.main(out, DOCS, s)
        assert len(s.calls) == 2 and all("fetched again" in log[k]["note"] for k in DOCS), log
        assert all(log[k]["md5"] for k in DOCS)
        print("  3. stored copies without an index entry: fetched again, identical, dated by that fetch")

        (out / "documents.json").unlink()
        refused(out, Session(body={**BODY, "https://example.org/a.pdf": b"%PDF-1.4 a, revised"}),
                "differs from the source")
        print("  4. such a copy that differs from the source is refused")

        documents.main(out, DOCS, Session())
        (out / "a.pdf").write_bytes(b"%PDF-1.4 edited")
        refused(out, Session(), "the stored copy changed")
        print("  5. a stored copy edited after indexing is refused")
    print("test_documents: all checks passed")


if __name__ == "__main__":
    main()
