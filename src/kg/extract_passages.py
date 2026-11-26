"""Extract normalised pages from Track 2 documents and Track 1 papers (v5 plan R2.1).

Each PDF in data/raw/documents/documents.json is read with `pdftotext -layout` using the
same printed-page footer rules and normalisation as tests/test_exchange_evidence.py; the
stored HTML page becomes one passage. `build_passages()` returns one deterministic record
per actual page (dropping the trailing empty chunk after `pdftotext`'s final form feed,
giving unnumbered pages unique `unnumbered pNNN` labels) and checks that no passage
exceeds MAX_PASSAGE_CHARS characters.

Track 1 uses physical page numbers, drops empty pages and stops before the first standalone
references heading, with a cap of twenty physical pages per downloaded paper.
"""
import csv
import hashlib
import html
import json
import re
import subprocess
from functools import lru_cache
from pathlib import Path

from src.config import RAW, ROOT

DOCS = RAW / "documents"
MAX_PASSAGE_CHARS = 12_000
PAPERS_PATH = ROOT / "configs" / "track1_papers.csv"
PAPER_PDF_DIR = RAW / "openalex" / "2026-11-26" / "pdf"
REFERENCES_RE = re.compile(
    r"^\s*(?:References|REFERENCES|Bibliography|Références|Literature cited|Literature Cited)\s*$"
)


def downloaded_papers(path=PAPERS_PATH):
    """Read one harvest snapshot; failed downloads never enter the selection order."""
    with Path(path).open(encoding="utf-8", newline="") as stream:
        rows = [dict(row) for row in csv.DictReader(stream) if row["download_status"] == "downloaded"]
    for row in rows:
        row["document"] = row["openalex_id"].rstrip("/").rsplit("/", 1)[-1]
        if not re.fullmatch(r"W\d+", row["document"]):
            raise ValueError(f"Invalid OpenAlex short id: {row['document']!r}")
        row["order"] = int(row["order"])
    for key in ("document", "order"):
        if len({row[key] for row in rows}) != len(rows):
            raise ValueError(f"Duplicate downloaded paper {key}")
    return sorted(rows, key=lambda row: row["order"])


def build_paper_passages(papers_path=PAPERS_PATH, pdf_dir=PAPER_PDF_DIR, *, papers=None):
    """Keep non-empty physical pages 1–20, stopping just before a references heading.

    Inspect lines before normalising: a reference to the word inside a sentence must not
    cut the paper. A missing or unreadable downloaded PDF is an error, so a partial harvest
    cannot silently change which papers form the pilot.
    """
    papers = downloaded_papers(papers_path) if papers is None else papers
    passages = []
    for paper in sorted(papers, key=lambda row: row["order"]):
        doc = paper["document"]
        path = Path(pdf_dir) / f"{doc}.pdf"
        text = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True,
                              text=True, check=True).stdout
        for physical_page, chunk in enumerate(text.split("\f")[:20], 1):
            lines = chunk.splitlines()
            heading = next((i for i, line in enumerate(lines) if REFERENCES_RE.fullmatch(line)), None)
            kept = norm("\n".join(lines if heading is None else lines[:heading]))
            if kept:
                passages.append({
                    "passage_id": f"{doc}:p{physical_page:03d}",
                    "document": doc,
                    "page": str(physical_page),
                    "order": paper["order"],
                    "text": kept,
                    "sha256": hashlib.sha256(kept.encode("utf-8")).hexdigest(),
                })
            if heading is not None:
                break
    return passages


def norm(s):
    return " ".join(s.replace("\u00a0", " ").split())


@lru_cache(maxsize=None)
def pages(doc):
    """[(printed page label, normalised text)] of a stored document."""
    index = json.loads((DOCS / "documents.json").read_text())
    f = DOCS / index[doc]["file"]
    if f.suffix == ".html":
        t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", f.read_text(encoding="utf-8"), flags=re.S)
        return [("web page", norm(html.unescape(re.sub(r"<[^>]+>", " ", t))))]
    out = subprocess.run(["pdftotext", "-layout", str(f), "-"], capture_output=True, text=True,
                         check=True).stdout
    result = []
    for chunk in out.split("\f"):
        m = re.findall(r"(?:^|\n)\s*(\d{1,3})\s+BRGM/RP-71486-FR|BRGM/RP-71486-FR[^\n]*?Roussillon\s+(\d{1,3})\s*(?:\n|$)",
                       chunk)
        # the footer line of a portrait page; the annex's landscape pages put the number on a line
        # of its own; the groundwater-body sheets end each page with "... Page N"
        nums = ([a or b for a, b in m] or re.findall(r"Page\s+(\d+)", chunk)
                or re.findall(r"(?m)^\s*(\d{1,3})\s*$", chunk))
        result.append((nums[-1] if nums else "?", norm(chunk)))
    return result


def build_passages():
    """Return one deterministic passage dict per printed page across documents.json."""
    index = json.loads((DOCS / "documents.json").read_text(encoding="utf-8"))
    passages = []
    for doc in sorted(index):
        doc_pages = list(pages(doc))
        # pdftotext terminates the final PDF page with a form feed, leaving a trailing empty split.
        if doc_pages and doc_pages[-1] == ("?", ""):
            doc_pages = doc_pages[:-1]
        for physical_index, (page_label, text) in enumerate(doc_pages):
            passage_id = f"{doc}:p{physical_index:03d}"
            # Keep `pages()` unchanged for test_exchange_evidence; disambiguate unnumbered
            # pages here so (document, page) is unique across all passages.
            unique_label = f"unnumbered p{physical_index:03d}" if page_label == "?" else page_label
            if len(text) > MAX_PASSAGE_CHARS:
                raise ValueError(
                    f"Passage {passage_id} ({len(text)} chars) exceeds the "
                    f"{MAX_PASSAGE_CHARS}-character limit; stop and report."
                )
            passages.append({
                "passage_id": passage_id,
                "document": doc,
                "page": unique_label,
                "physical_index": physical_index,
                "text": text,
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            })
    return passages
