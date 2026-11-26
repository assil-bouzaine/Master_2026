"""Build browsable ontology documentation for v5 plan R2.4.

The sorted module/profile globs are the only source list. pyLODE stays outside the
project environment and is called through its CLI, with the explicit ontpub profile.
With pyLODE 3.6.1, core renders varied in the ordering of the embedded schema.org
JSON-LD graph and in the language picked for the definedInModule property heading.
We sort JSON-LD object keys and unordered arrays, preserving ordered @list values.
That specific link heading displays both observed labels in a fixed order. The
term's own bilingual definition is untouched. No dates or identifiers are removed.

pyLODE uses local-name anchors for classes, label-derived anchors for some
properties (whose full IRI is in a code element), and full-IRI links for referenced
individuals. Completeness accepts those exact HTML attributes or the full IRI in
an anchored entity's code element. Prose and embedded JSON-LD do not count. Missing
terms are errors; an incomplete build receives a clearly marked index that --check
refuses, so reviewers can inspect the pages without mistaking them for a release.

Terms missing from pyLODE receive source-derived entries using its property/entity
CSS classes, before </main> (or </body> when there is no main). The entries include
English/French labels and definitions, compact types and SKOS concept relations.
Their local-name ids are checked against all existing ids; a collision uses
supp-<local name>, with another supp- prefix if that fallback is also occupied.
Every literal is HTML-escaped. Entries and values are sorted, and the source name
and first twelve SHA-256 characters identify the Turtle used for the supplement.

    PFE_DATASET=v5 python -m src.kg.ontology_docs [--out DIR] [--check]
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from html import escape
from html.parser import HTMLParser
from pathlib import Path

import rdflib
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS

from src.config import ROOT
from src.kg.ontology_modules import DEFINED_IN_MODULE, L
from src.kg.release import sha256

ONTOLOGY = ROOT / "ontology"
OUTPUT = ROOT / "docs" / "ontology"
PYLODE_VERSION = "3.6.1"
INSTALL = "uv tool install pylode==3.6.1"
SCHEMA = re.compile(r'(<script\b[^>]*\bid="schema\.org"[^>]*>)(.*?)(</script>)', re.S)
MODULE_HEADING = re.compile(
    r'(<a\b[^>]*\bhref="' + re.escape(str(DEFINED_IN_MODULE))
    + r'"[^>]*>)(?:Defined In Module|Défini Dans Le Module)(</a>)')


class DocumentationError(RuntimeError):
    """Documentation is incomplete, stale, or cannot be rendered."""


def sources(ontology=ONTOLOGY):
    """Discover the modules and profiles, without maintaining another filename list."""
    return sorted([*ontology.glob("modules/lulcw-*.ttl"),
                   *ontology.glob("profiles/lulcw-*-profile.ttl")])


def find_pylode():
    """Refuse missing or different tools rather than changing pinned dependencies."""
    executable = shutil.which("pylode")
    if executable is None:
        fallback = Path.home() / ".local/bin/pylode"
        if not fallback.is_file():
            raise DocumentationError(f"pyLODE is missing; install separately with: {INSTALL}")
        executable = str(fallback)
    try:
        result = subprocess.run([executable, "-v"], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise DocumentationError(f"Cannot run {executable} -v; install with: {INSTALL}") from error
    version = result.stdout.strip()
    if version != PYLODE_VERSION:
        raise DocumentationError(
            f"pyLODE {PYLODE_VERSION} required, found {version!r}; install with: {INSTALL}")
    return executable


def source_record(source, ontology=ONTOLOGY):
    """Read the header and the terms actually assigned to this module/profile."""
    graph = rdflib.Graph().parse(source, format="turtle")
    headers = list(graph.subjects(RDF.type, OWL.Ontology))
    if len(headers) != 1:
        raise DocumentationError(f"{source}: expected one owl:Ontology header")
    header = headers[0]
    titles = sorted(str(value) for value in graph.objects(header, DCTERMS.title)
                    if isinstance(value, rdflib.Literal) and value.language == "en")
    version = graph.value(header, OWL.versionInfo)
    if not titles or version is None:
        raise DocumentationError(f"{source}: missing English dcterms:title or owl:versionInfo")
    terms = sorted({str(term) for term in graph.subjects(DEFINED_IN_MODULE, header)
                    if isinstance(term, rdflib.URIRef) and str(term).startswith(L)})
    record = {"source": source.relative_to(ontology).as_posix(), "title": titles[0],
              "version": str(version), "terms": len(terms), "sha256": sha256(source),
              "page": source.stem + ".html"}
    return record, terms


def _ordered_json(value, preserve_order=False):
    if isinstance(value, dict):
        return {key: _ordered_json(item, key == "@list") for key, item in sorted(value.items())}
    if isinstance(value, list):
        items = [_ordered_json(item) for item in value]
        return items if preserve_order else sorted(items, key=lambda item: json.dumps(item, sort_keys=True))
    return value


def normalize_html(html):
    """Fix the observed JSON-LD order and bilingual annotation-heading variations."""
    def replace(match):
        data = _ordered_json(json.loads(match[2]))
        return match[1] + "\n" + json.dumps(data, ensure_ascii=True, indent=2) + "\n    " + match[3]
    html = SCHEMA.sub(replace, html)
    return MODULE_HEADING.sub(
        lambda match: match[1] + "Defined In Module / Défini Dans Le Module" + match[2], html)


class _PageTerms(HTMLParser):
    """Collect actual links/anchors, plus IRIs within anchored entity definitions."""

    def __init__(self):
        super().__init__()
        self.references = set()
        self.ids = set()
        self.entity_depth = 0
        self.entity_iri_seen = False
        self.code = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        self.references.update(value for key, value in attrs.items()
                               if key in ("id", "name", "href") and value)
        if tag == "div":
            if self.entity_depth:
                self.entity_depth += 1
            elif attrs.get("id") and "entity" in attrs.get("class", "").split():
                self.entity_depth = 1
                self.entity_iri_seen = False
        # pyLODE puts the IRI row first. Later code fragments may be prose examples.
        if tag == "code" and self.entity_depth and not self.entity_iri_seen:
            self.code = []
            self.entity_iri_seen = True

    def handle_data(self, data):
        if self.code is not None:
            self.code.append(data)

    def handle_endtag(self, tag):
        if tag == "code" and self.code is not None:
            self.references.add("".join(self.code).strip())
            self.code = None
        if tag == "div" and self.entity_depth:
            self.entity_depth -= 1


def missing_terms(html, terms):
    """Use the same coverage rule to select supplements and check the final page."""
    parser = _PageTerms()
    parser.feed(html)
    return sorted(term for term in terms
                  if not {term, term[len(L):], "#" + term[len(L):]} & parser.references)


def check_completeness(page, terms):
    """A bare mention in a definition or JSON-LD is not a browsable term."""
    missing = missing_terms(page.read_text(encoding="utf-8"), terms)
    if missing:
        raise DocumentationError(f"{page.name}: missing terms: {', '.join(missing)}")


def _rdf_html(graph, value):
    """Keep RDF links browsable and literal markup harmless."""
    if isinstance(value, rdflib.URIRef):
        name = graph.namespace_manager.normalizeUri(value)
        return f'<a href="{escape(str(value), quote=True)}">{escape(name)}</a>'
    text = escape(str(value), quote=True)
    if isinstance(value, rdflib.Literal) and value.language:
        return f'<span lang="{escape(value.language, quote=True)}">{text}</span>'
    return text


def _supplement_entry(graph, term, ids):
    """Render one source term, reserving an id so later entries cannot reuse it."""
    local = term[len(L):]
    anchor = local
    while anchor in ids:
        anchor = "supp-" + anchor
    ids.add(anchor)
    subject = rdflib.URIRef(term)
    rows = [f'<tr><th>IRI</th><td><a href="{escape(term, quote=True)}">'
            f'<code>{escape(term)}</code></a></td></tr>']

    def row(predicate, values, language=None):
        values = sorted(values, key=lambda value: value.n3())
        if not values:
            return
        name = escape(graph.namespace_manager.normalizeUri(predicate))
        if language:
            name += f" ({language})"
        content = '<ul class="pylodelitlist">' + ''.join(
            f'<li>{_rdf_html(graph, value)}</li>' for value in values) + '</ul>'
        rows.append(f'<tr><th>{name}</th><td>{content}</td></tr>')

    row(RDF.type, graph.objects(subject, RDF.type))
    for predicate in (RDFS.label, SKOS.prefLabel, SKOS.definition):
        for language in ("en", "fr"):
            row(predicate, (value for value in graph.objects(subject, predicate)
                            if isinstance(value, rdflib.Literal) and value.language == language),
                language)
    if (subject, RDF.type, SKOS.Concept) in graph:
        for predicate in (SKOS.inScheme, SKOS.broader, SKOS.notation):
            row(predicate, graph.objects(subject, predicate))
    return (f'<div class="property entity" id="{escape(anchor, quote=True)}">\n'
            f'<h3>{escape(local)}</h3>\n<table>\n' + '\n'.join(rows)
            + '\n</table>\n</div>')


def supplement_html(html, source, terms):
    """List only terms absent under the completeness rule, directly from Turtle."""
    missing = missing_terms(html, terms)
    if not missing:
        return html
    parser = _PageTerms()
    parser.feed(html)
    graph = rdflib.Graph().parse(source, format="turtle")
    entries = [_supplement_entry(graph, term, parser.ids) for term in missing]
    section = ('\n<section>\n<h2>Terms not rendered by pyLODE</h2>\n'
               f"<p>pyLODE {PYLODE_VERSION}'s ontology profile does not render SKOS concepts, "
               'concept schemes or observable-property individuals, so these entries are listed '
               f'directly from <code>{escape(source.name)}</code> '
               f'(SHA-256 <code>{sha256(source)[:12]}</code>).</p>\n'
               + '\n'.join(entries) + '\n</section>\n')
    position = html.rfind("</main>")
    if position == -1:
        position = html.rfind("</body>")
    if position == -1:
        raise DocumentationError(f"{source.name}: page has no closing main or body for supplement")
    return html[:position] + section + html[position:]


def render_page(executable, source, page, terms=None):
    """Render offline, normalise variations, and supplement missing source terms."""
    started = time.perf_counter()
    try:
        result = subprocess.run(
            [executable, "-p", "ontpub", "-s", "true", str(source), "-o", str(page)],
            capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as error:
        raise DocumentationError(
            f"pyLODE failed for {source.name}:\n{error.stdout}\n{error.stderr}") from error
    except OSError as error:
        raise DocumentationError(f"Cannot run pyLODE: {error}") from error
    if not page.is_file():
        raise DocumentationError(f"pyLODE produced no page for {source.name}: {result.stdout} {result.stderr}")
    if terms is None:
        _, terms = source_record(source, source.parent)
    html = normalize_html(page.read_text(encoding="utf-8"))
    page.write_text(supplement_html(html, source, terms), encoding="utf-8")
    elapsed = time.perf_counter() - started
    print(f"  {page.name}: {page.stat().st_size:,} bytes, {elapsed:.2f} s", flush=True)
    return elapsed


def write_index(records, out, errors=()):
    """Write the same source records for readers and for the freeze gate."""
    rows = []
    for record in records:
        title, version, page, digest = (escape(record[key], quote=True)
                                        for key in ("title", "version", "page", "sha256"))
        rows.append(f'<tr><td><a href="{page}">{title}</a></td><td>{version}</td>'
                    f'<td>{record["terms"]}</td><td><code>{digest}</code></td></tr>')
    status = ""
    if errors:
        status = ('<p><strong>Incomplete build: the documentation completeness check failed. '
                  'These pages are available for inspection; regenerate after fixing the omissions.</strong></p>\n'
                  '<ul>' + ''.join(f'<li>{escape(error)}</li>' for error in errors) + '</ul>\n')
    html = ('<!doctype html>\n<html lang="en"><meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<title>LULC-Water ontology documentation</title>\n'
            '<style>body{font-family:system-ui;margin:2rem}table{border-collapse:collapse}'
            'th,td{padding:.6rem;border:1px solid #ccc;text-align:left}'
            'code{overflow-wrap:anywhere}</style>\n<h1>LULC-Water ontology documentation</h1>\n'
            '<p>The LULC-Water network contains seven country-agnostic modules and EU, France '
            'and Tunisia profiles, generated from <code>ontology/lulcw.ttl</code>. '
            f'These pages use pyLODE {PYLODE_VERSION} (ontpub).</p>\n' + status +
            '<table><thead><tr><th>Module or profile</th><th>Version</th>'
            '<th>Defined lulcw: terms</th><th>Source SHA-256</th></tr></thead><tbody>\n'
            + '\n'.join(rows) + '\n</tbody></table>\n</html>\n')
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / "index.json").write_text(json.dumps(
        {"pylode_version": PYLODE_VERSION, "complete": not errors,
         "errors": list(errors), "sources": records}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")


def check(out=OUTPUT, ontology=ONTOLOGY):
    """Check every discovered source and page without finding or invoking pyLODE."""
    paths = sources(ontology)
    expected = {path.relative_to(ontology).as_posix(): path for path in paths}
    manifest_path = out / "index.json"
    if not manifest_path.is_file():
        pages = ", ".join(path.stem + ".html" for path in paths)
        raise DocumentationError(f"{manifest_path}: missing index; undocumented pages: {pages}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        records = {record["source"]: record for record in manifest["sources"]}
        if len(records) != len(manifest["sources"]):
            raise ValueError("duplicate source records")
    except (ValueError, KeyError, TypeError) as error:
        raise DocumentationError(f"{manifest_path}: invalid index: {error}") from error
    errors = []
    for name, source in expected.items():
        page = source.stem + ".html"
        record = records.get(name)
        if record is None:
            errors.append(f"{page}: missing index record")
        elif record.get("sha256") != sha256(source) or record.get("page") != page:
            errors.append(f"{page}: stale source or page record ({name})")
        if not (out / page).is_file():
            errors.append(f"{page}: missing page")
    errors.extend(f'{records[name].get("page", name)}: source no longer exists'
                  for name in sorted(records.keys() - expected.keys()))
    if manifest.get("pylode_version") != PYLODE_VERSION:
        errors.append(f"index.json: expected pyLODE {PYLODE_VERSION}")
    if manifest.get("complete") is not True:
        errors.append("index.json: incomplete build")
        errors.extend(manifest.get("errors", []))
    if errors:
        raise DocumentationError("Documentation needs rebuilding:\n  " + "\n  ".join(errors))
    return manifest


def build(out=OUTPUT, ontology=ONTOLOGY):
    executable = find_pylode()
    paths = sources(ontology)
    if not paths:
        raise DocumentationError(f"No module/profile Turtle sources found under {ontology}")
    out.mkdir(parents=True, exist_ok=True)
    # A failed rebuild must not leave an old manifest claiming that it succeeded.
    (out / "index.json").unlink(missing_ok=True)
    records, errors = [], []
    started = time.perf_counter()
    for source in paths:
        record, terms = source_record(source, ontology)
        page = out / record["page"]
        render_page(executable, source, page, terms)
        try:
            check_completeness(page, terms)
        except DocumentationError as error:
            errors.append(str(error))
        if sha256(source) != record["sha256"]:
            errors.append(f"{page.name}: source changed during generation")
        records.append(record)
    print(f"Rendered {len(records)} pages in {time.perf_counter() - started:.2f} s", flush=True)
    write_index(records, out, errors)
    if errors:
        raise DocumentationError("Incomplete documentation:\n  " + "\n  ".join(errors))
    check(out, ontology)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        if args.check:
            manifest = check(args.out)
            print(f"Ontology documentation is current: {len(manifest['sources'])} pages")
        else:
            build(args.out)
    except (DocumentationError, OSError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
