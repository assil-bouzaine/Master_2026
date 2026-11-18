"""Build the paper's bibliography from the checked reading list (CLAUDE.md §1a).

Cache each provider record with its fetch date. Offline runs rebuild from the
local cache and list missing entries. Keep the provider's fields and rewrite
only the entry key.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python paper/tools/fetch_bib.py --offline
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
from itertools import count, product, takewhile
from pathlib import Path
import re
import string
import sys
from tempfile import TemporaryDirectory
import time
import unicodedata
from urllib.parse import quote, unquote

from pyparsing import (Combine, DelimitedList, Group, Literal, OneOrMore, ParseException, Regex,
                       StringEnd, Suppress, ZeroOrMore, nested_expr, original_text_for)
from requests import RequestException

ROOT = Path(__file__).resolve().parents[2]
if not __package__:
    sys.path.insert(0, str(ROOT))

from src.analysis.citation_audit import identifiers
from src.web import TIMEOUT, make_session

READING_LIST = ROOT / "docs" / "literature" / "reading_list.md"
CACHE = ROOT / "paper" / "bib_cache"
REFS = ROOT / "paper" / "refs.bib"

ENTRY = re.compile(r"\A\s*(?:%[^\n]*\n\s*)*@(?P<kind>[a-zA-Z]+)\s*(?P<open>[{(])"
                   r"\s*(?P<key>[^,\s{}()]+)\s*,")
FETCHED = re.compile(r"\A% fetched (\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE)
BRACES = original_text_for(nested_expr("{", "}", ignore_expr=Regex(r"\\[{}]")))
QUOTED = original_text_for(Literal('"') + ZeroOrMore(BRACES | Regex(r'\\.|[^"{}\\]+')) + Literal('"'))

# Values can be nested, quoted or bare, and BibTeX joins parts with #.
STRING = (BRACES | QUOTED).add_parse_action(lambda tokens: tokens[0][1:-1])
VALUE = DelimitedList(STRING | Regex(r'[^,\s(){}"#]+'), delim="#").add_parse_action(
    lambda tokens: "".join(tokens))
FIELD = Group(Regex(r"[a-zA-Z][a-zA-Z0-9_\-]*") + Suppress("=") + VALUE)
FIELDS = DelimitedList(FIELD, allow_trailing_delim=True)
NAME = OneOrMore(Literal(",") | Combine(OneOrMore(BRACES | Regex(r"(?:\\[{}]|[^,\s{}])+"))))
TEX_LETTERS = {"aa": "a", "ae": "ae", "i": "i", "j": "j", "l": "l",
               "o": "o", "oe": "oe", "ss": "ss"}
LETTERS = str.maketrans({"æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "ø": "o", "Ø": "O",
                         "ł": "l", "Ł": "L", "ß": "ss", "ı": "i", "{": "", "}": ""})


def _identifiers(line):
    # The WHOW-KG note gives a parenthesized arXiv preprint ID without a colon.
    line = re.sub(r"(\barxiv\s+preprint\s*\(\s*)(?=\d)", r"\1arXiv:", line, flags=re.IGNORECASE)
    for identifier, _, _ in identifiers(line):
        # The reading list also quotes a truncated DOI prefix in an audit note.
        if identifier.startswith("arXiv:") or identifier.partition("/")[2]:
            yield identifier


def collect_identifiers(path):
    """Return unique reading-list identifiers in a stable order."""
    return sorted({identifier for line in path.read_text(encoding="utf-8").splitlines()
                   for identifier in _identifiers(line)})


def cache_path(cache, identifier):
    """Use a reversible filename even when a DOI contains slashes or punctuation."""
    return cache / (quote(identifier, safe="") + ".bib")


def _ascii_text(text):
    text = re.sub(r"""\\(?:["'`^~=.]|[uvHckbdtr](?=[\s{]))\s*""", "", text)

    def letter(match):
        command = match.group(1)
        replacement = TEX_LETTERS.get(command.lower(), "")
        return replacement.upper() if command.isupper() else replacement

    text = re.sub(r"\\([a-zA-Z]+)\s*", letter, text).translate(LETTERS)
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def _family_name(authors):
    names = NAME.parse_string(authors, parse_all=True)
    first = list(takewhile(lambda token: token.lower() != "and", names))
    if not first or first[0] == ",":
        raise ValueError("missing first author family name")
    if "," in first:
        return " ".join(first[:first.index(",")])
    # BibTeX's given-name-first form starts its family name at a lowercase particle.
    for index, word in enumerate(first[:-1]):
        if _ascii_text(word)[:1].islower():
            return " ".join(first[index:])
    return first[-1]


def _entry_key(record):
    """Read the fields needed for the key and retain the span of the provider's key."""
    entry = ENTRY.match(record)
    if entry is None or entry["kind"].lower() in {"comment", "preamble", "string"}:
        raise ValueError("expected one BibTeX entry")
    closer = "}" if entry["open"] == "{" else ")"
    try:
        parsed = (FIELDS + Suppress(closer) + StringEnd()).parse_string(record[entry.end():])
        fields = {name.lower(): value for name, value in parsed}
        author = re.sub(r"[^a-zA-Z0-9]", "", _ascii_text(_family_name(fields["author"])))
        title_words = re.findall(r"[a-zA-Z0-9]+", _ascii_text(fields["title"]))
        year = fields["year"].strip()
    except (ParseException, KeyError) as error:
        raise ValueError("could not read the BibTeX author, title and year") from error
    if not author or not title_words or re.fullmatch(r"[0-9]{4}", year) is None:
        raise ValueError("entry needs an author family name, title word and four-digit year")
    return author.capitalize() + year + title_words[0].capitalize(), entry.span("key")


def _suffixes():
    for length in count(1):
        for letters in product(string.ascii_lowercase, repeat=length):
            yield "".join(letters)


def _iso_date(timestamp):
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat()


def _write_complete(path, content):
    """Publish a complete file so a partial download cannot become a cache hit."""
    with TemporaryDirectory(dir=path.parent) as staging:
        staged = Path(staging) / path.name
        staged.write_text(content, encoding="utf-8")
        staged.replace(path)


def _fetch_records(missing, cache):
    failed = 0
    with make_session() as session:
        for index, identifier in enumerate(missing):
            if index:
                time.sleep(1)
            if identifier.startswith("arXiv:"):
                url = "https://arxiv.org/bibtex/" + identifier.removeprefix("arXiv:")
                headers = {}
            else:
                url = "https://doi.org/" + quote(identifier, safe="/")
                headers = {"Accept": "application/x-bibtex"}
            try:
                response = session.get(url, headers=headers, timeout=TIMEOUT, allow_redirects=True)
                response.raise_for_status()
                record = response.content.decode("utf-8-sig").strip()
                _entry_key(record)
            except (RequestException, ValueError) as error:
                print(f"Fetch failed for {identifier} ({error})", file=sys.stderr)
                failed += 1
                continue
            cache.mkdir(parents=True, exist_ok=True)
            fetched = datetime.now(timezone.utc).date().isoformat()
            _write_complete(cache_path(cache, identifier), f"% fetched {fetched}\n{record}\n")
    return failed


def _cached_entries(cache):
    entries = defaultdict(list)
    failed = 0
    for path in sorted(cache.glob("*.bib")):
        identifier = unquote(path.stem)
        try:
            if list(_identifiers(identifier)) != [identifier] or cache_path(cache, identifier) != path:
                raise ValueError("expected a cache filename created by this tool")
            record = path.read_text(encoding="utf-8-sig").strip()
            fetched = FETCHED.match(record)
            if fetched:
                fetched_date = fetched[1]
                record = record[fetched.end():].lstrip()
            else:
                # Plain records imported into the cache have only a filesystem date.
                fetched_date = _iso_date(path.stat().st_mtime)
            base, span = _entry_key(record)
        except (OSError, ValueError) as error:
            print(f"Cache error for {path.name} ({error})", file=sys.stderr)
            failed += 1
            continue
        entries[base].append((identifier, fetched_date, record, span))
    return entries, failed


def _render(entries):
    rewritten = {}
    reserved = set(entries)
    for base, group in sorted(entries.items()):
        suffixes = _suffixes()
        for identifier, fetched, record, (start, end) in sorted(group):
            key = base
            if len(group) > 1:
                key = next(base + suffix for suffix in suffixes
                           if base + suffix not in reserved and base + suffix not in rewritten)
            rewritten[key] = f"% {identifier}, fetched {fetched}\n{record[:start]}{key}{record[end:]}"
    return "\n\n".join(rewritten[key] for key in sorted(rewritten)) + ("\n" if rewritten else ""), len(rewritten)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--offline", action="store_true", help="use only the cached records")
    args = parser.parse_args(argv)
    wanted = collect_identifiers(READING_LIST)
    missing = [identifier for identifier in wanted if not cache_path(CACHE, identifier).is_file()]
    failed_fetches = _fetch_records(missing, CACHE) if missing and not args.offline else 0
    for identifier in missing:
        if not cache_path(CACHE, identifier).is_file():
            print(f"Missing {identifier}")
    entries, failed_cache = _cached_entries(CACHE)
    content, written = _render(entries)
    _write_complete(REFS, content)
    print(f"Wrote {written} entries to {REFS} from {len(wanted)} reading-list identifiers")
    return int(bool(failed_fetches or failed_cache))


if __name__ == "__main__":
    sys.exit(main())
