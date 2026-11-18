"""Find citations that need review under CLAUDE.md §6 rule 9 (task T02).

Scan tracked text files for DOI and arXiv identifiers. Compare them with the two checked
literature lists, flag odd spellings, and show nearby years that may disagree. This is an
offline check for the lead to review; it does not establish whether a paper or identifier exists.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m src.analysis.citation_audit
"""
import html
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path("docs/literature/citation_audit.md")
CHECKED = (Path("docs/literature/reading_list.md"),
           Path("docs/literature/comparison_table.md"))
EXTENSIONS = {".md", ".py", ".sh", ".ttl", ".csv", ".json", ".toml", ".yaml", ".yml",
              ".rq", ".tex", ".bib", ".html", ".js"}
# arXiv identifiers end at brackets. DOI suffixes may contain balanced brackets.
TOKEN = r"[^\s\])}>\"'`‘’“”]*"
IDENTIFIER = re.compile(r"(?P<doi>(?<![0-9])10\.[0-9]{4,9}/)|"
                        r"(?:arxiv:|arxiv\.org/abs/)(?P<arxiv>(?=[0-9])" + TOKEN + r")", re.IGNORECASE)
URL_TAIL = re.compile(r"/(?:pdf|full|abstract|epdf|html)$", re.IGNORECASE)
ARXIV = re.compile(r"[0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?", re.IGNORECASE)
YEAR = re.compile(r"(?<![0-9])(?:19[5-9][0-9]|20[0-2][0-9])(?![0-9])")
COMMAND = "PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m src.analysis.citation_audit"


@dataclass
class Citation:
    path: Path
    line: int
    text: str
    years: set[int]

    def place(self):
        return f"{self.path.as_posix()}:{self.line}"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8")


def tracked_files():
    """Use the index, not a directory walk, so caches and untracked drafts stay out."""
    return sorted({Path(name) for name in git("ls-files", "-z").split("\0")
                   if name and Path(name).suffix in EXTENSIONS and Path(name) != OUTPUT})


def doi_end(line, start):
    """Keep balanced parentheses and square brackets; an outer closing bracket ends the DOI."""
    opened = []
    for end in range(start, len(line)):
        character = line[end]
        if character.isspace() or character in "}>\"'`‘’“”":
            return end
        if character in "([":
            opened.append(character)
        elif character in ")]":
            if not opened or character != {"(": ")", "[": "]"}[opened[-1]]:
                return end
            opened.pop()
    return len(line)


def identifiers(line):
    """Normalize DOI case and one publisher URL tail, and remove arXiv version numbers."""
    position = 0
    while match := IDENTIFIER.search(line, position):
        is_doi = match.group("doi") is not None
        position = doi_end(line, match.end()) if is_doi else match.end()
        raw = line[match.start():position] if is_doi else match.group("arxiv")
        value = raw.rstrip(".,;:*")
        end = position - (len(raw) - len(value))
        if is_doi:
            if value.count("/") > 1:
                value = URL_TAIL.sub("", value)
            end = match.start() + len(value)
            identifier = value.lower()
        else:
            identifier = "arXiv:" + re.sub(r"v[0-9]+$", "", value, flags=re.IGNORECASE)
        yield identifier, match.start(), end


def suspicious(identifier):
    """These are review hints, not registration checks; unusual valid DOIs can be flagged."""
    if identifier.startswith("arXiv:"):
        body = identifier.removeprefix("arXiv:")
        if not ARXIV.fullmatch(body):
            return ["Expected four digits, a dot, then four or five digits"]
        if not 1 <= int(body[2:4]) <= 12:
            return ["arXiv month outside 01–12"]
        return []
    suffix = identifier.split("/", 1)[1]
    reasons = []
    if len(suffix) < 3:
        reasons.append("DOI suffix shorter than 3 characters")
    if suffix.endswith(("-", "/")):
        reasons.append("DOI ends in a hyphen or slash; possibly truncated")
    if re.search(r"[^a-z0-9._;()/,:+\[\]\-]", suffix):
        reasons.append("Unusual DOI suffix characters")
    if (suffix.count("(") != suffix.count(")") or suffix.count("[") != suffix.count("]")
            or "{" in suffix):
        reasons.append("Unclosed bracket; possibly truncated")
    return reasons


def nearest_year(line, start, end):
    """Prefer the nearest year before a mention; use the nearest after it only as a fallback."""
    years = list(YEAR.finditer(line))
    before = [year for year in years if year.start() >= max(0, start - 80) and year.end() <= start]
    if before:
        return int(before[-1].group())
    after = [year for year in years if year.start() >= end and year.end() <= end + 80]
    return int(after[0].group()) if after else None


def scan(paths):
    """Count one place per identifier and line, using the first mention's selected year."""
    citations = {}
    for path in sorted(paths):
        for number, line in enumerate((ROOT / path).read_text(encoding="utf-8", errors="replace")
                                      .splitlines(), 1):
            found = {}
            for identifier, start, end in identifiers(line):
                if identifier not in found:
                    year = nearest_year(line, start, end)
                    found[identifier] = {year} if year is not None else set()
            for identifier, years in found.items():
                citations.setdefault(identifier, []).append(Citation(path, number, line, years))
    return citations


def checked_identifiers():
    """A bare DOI prefix quoted in an audit note is not a checked identifier."""
    return {identifier for identifier in scan(CHECKED)
            if not identifier.startswith("10.") or identifier.partition("/")[2]}


def cell(text):
    """Keep source pipes, quotes and HTML from breaking the generated Markdown tables."""
    return html.escape(str(text), quote=False).replace("|", "&#124;").replace("`", "&#96;")


def places(citations):
    return "<br>".join(cell(citation.place()) for citation in citations)


def render(paths, citations, checked, source_date):
    unchecked = sorted(citations.keys() - checked)
    odd = {identifier: suspicious(identifier) for identifier in sorted(citations)
           if suspicious(identifier)}
    inconsistent = {}
    for identifier in sorted(citations):
        years = set().union(*(citation.years for citation in citations[identifier]))
        if len(years) > 1:
            inconsistent[identifier] = years
    counts = {"files": len(paths), "identifiers": len(citations),
              "checked": len(citations.keys() & checked), "not checked": len(unchecked),
              "malformed or suspicious": len(odd), "possibly inconsistent": len(inconsistent)}
    lines = ["# Citation audit", "", "Generated file. Do not edit by hand.", "",
             f"Command: `{COMMAND}`", "",
             f"Source date: {source_date} (latest Git commit date, kept stable for reproducible reruns).", "",
             "## Summary", ""]
    lines += [f"- {label.capitalize()}: {count}" for label, count in counts.items()]
    lines += ["", "The checked set contains every identifier in `reading_list.md` and",
              "`comparison_table.md`. Membership is not an online verification. DOI case and",
              "arXiv versions are normalized. Bare DOI prefixes without a suffix stay outside",
              "the checked set. A citing place is one unique `path:line`.", "",
              "## Table 1, not in the checked set", "",
              "| Identifier | Number of citing places | Every place | First citing line (≤ 100 characters) |",
              "|---|---:|---|---|"]
    for identifier in unchecked:
        hits = citations[identifier]
        excerpt = " ".join(hits[0].text.split())
        if len(excerpt) > 100:
            excerpt = excerpt[:97] + "..."
        lines.append(f"| {cell(identifier)} | {len(hits)} | {places(hits)} | {cell(excerpt)} |")
    if not unchecked:
        lines += ["", "None found."]
    lines += ["", "## Table 2, malformed or suspicious", "",
              "These spelling checks can also flag unusual valid identifiers.", "",
              "| Identifier | Reason | Every place |", "|---|---|---|"]
    for identifier, reasons in odd.items():
        lines.append(f"| {cell(identifier)} | {cell('; '.join(reasons))} | {places(citations[identifier])} |")
    if not odd:
        lines += ["", "None found."]
    lines += ["", "## Table 3, possible inconsistencies (heuristic; false alarms expected)", "",
              "For each citing line, use the first mention of the identifier. Select the nearest",
              "year 1950–2029 before it within 80 characters. Only if none exists, select the nearest",
              "year after it within 80 characters. Years inside the identifier are ignored. Flag",
              "more than one distinct selected year across its citing lines. Adjacent references",
              "and print, online or access dates can still cause false alarms.", "",
              "| Identifier | Selected years | Places (selected year) |", "|---|---|---|"]
    for identifier, years in inconsistent.items():
        evidence = "<br>".join(cell(f"{hit.place()} ({', '.join(map(str, sorted(hit.years)))})")
                               for hit in citations[identifier] if hit.years)
        lines.append(f"| {cell(identifier)} | {', '.join(map(str, sorted(years)))} | {evidence} |")
    if not inconsistent:
        lines += ["", "None found."]
    return "\n".join(lines) + "\n", counts


def main():
    paths = tracked_files()
    citations = scan(paths)
    checked = checked_identifiers()
    source_date = git("log", "-1", "--format=%cs").strip()
    content, counts = render(paths, citations, checked, source_date)
    (ROOT / OUTPUT).write_text(content, encoding="utf-8")
    print(f"Wrote {OUTPUT}: " + ", ".join(f"{value} {label}" for label, value in counts.items()))


if __name__ == "__main__":
    main()
