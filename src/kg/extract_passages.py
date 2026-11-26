"""Extract normalised page passages from the stored Track 2 documents (v5 plan R2.1).

Each PDF in data/raw/documents/documents.json is read with `pdftotext -layout` using the
same printed-page footer rules and normalisation as tests/test_exchange_evidence.py; the
stored HTML page becomes one passage. `build_passages()` returns one deterministic record
per actual page (dropping the trailing empty chunk after `pdftotext`'s final form feed,
giving unnumbered pages unique `unnumbered pNNN` labels) and checks that no passage
exceeds MAX_PASSAGE_CHARS characters.
"""
import hashlib
import html
import json
import re
import subprocess
from functools import lru_cache

from src.config import RAW

DOCS = RAW / "documents"
MAX_PASSAGE_CHARS = 12_000


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
