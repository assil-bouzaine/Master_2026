"""Inventory of ontology terms that mention France (docs/v5_plan.md, R2.2).

    PFE_DATASET=v4 python -m src.kg.country_terms

Name matches are possible France-profile terms. Text-only matches may just cite a source.
This audit records evidence and the existing term-usage categories; it moves no terms.
"""
import argparse
import re
import unicodedata
from collections import Counter
from time import perf_counter

import rdflib
from rdflib.namespace import DCTERMS, RDF, RDFS, SKOS

from src.config import DATASET, ROOT
from src.kg import term_usage as usage

# Applied after accent folding; local names also have camel case and underscores separated.
# Boundaries avoid matches inside unrelated words such as "design" (IGN).
TOKENS = {
    "bdlisa": r"\bbd\s*lisa\b",
    "bnpe": r"\bbnpe\b",
    "bss": r"\bbss\b",
    "rpg": r"\brpg\b",
    "safran": r"\b(?:safran|sim2)\b",
    "sandre": r"\bsandre\b",
    "ades": r"\bades\b",
    "bdtopo": r"\bbd\s*topo\b",
    "carthage": r"\bcarthage\b",
    "hubeau": r"\bhub['’\s-]*eau\b",
    "brgm": r"\bbrgm\b",
    "ign": r"\bign\b",
    "meteo_france": r"\bmeteo[\s-]+france\b",
    "agreste": r"\bagreste\b",
    "smnpr": r"\bsmnpr\b",
    "ofb": r"\b(?:ofb|onema)\b",
    "insee": r"\binsee\b",
    "lambert93": r"\b(?:lambert[\s-]*93|epsg\s*:\s*2154)\b",
    "frdg": r"\bfrdg\d*\b",
    "sierm": r"\bsierm\b",
    "france": r"\b(?:france|french|francais|francaise)\b",
    "roussillon": r"\broussillon\b",
    "pyrenees_orientales": r"\bpyrenees[\s-]+orientales\b",
    "departement": r"\bdepartement\b",
}

TEXT_PROPERTIES = ((SKOS.definition, "skos:definition"), (RDFS.comment, "rdfs:comment"),
                   (SKOS.scopeNote, "skos:scopeNote"), (SKOS.example, "skos:example"),
                   (DCTERMS.description, "dcterms:description"))
STATUSES = ("in the data", "rules, shapes or queries only", "ontology axioms only", "unused")
NO_USAGE = "not checked (--no-usage)"


def fold(value, local_name=False):
    """Keep word boundaries while making accents and letter case immaterial."""
    value = str(value)
    if local_name:
        value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", value)
        value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value).replace("_", " ")
    return "".join(c for c in unicodedata.normalize("NFKD", value)
                   if not unicodedata.combining(c)).casefold()


def matched_tokens(value, local_name=False):
    value = fold(value, local_name)
    return tuple(token for token, pattern in TOKENS.items() if re.search(pattern, value, re.I))


def annotation_counts(graph):
    """Counts over the whole ontology, including its header, before filtering declared terms."""
    return {name: sum(1 for _ in graph.triples((None, prop, None)))
            for prop, name in TEXT_PROPERTIES}


def usage_categories(terms, structural):
    """Use exactly term_usage.main's precedence, including alignment-file mentions."""
    manifest = usage.release.check()
    data = usage.data_counts(usage.kg_store())
    where = (usage.mentions([usage.ONTO / "rules" / "lulcw-rules.ttl"]),
             usage.mentions([usage.ONTO / "shapes" / "lulcw-shapes.ttl"]),
             usage.mentions(sorted(usage.CQ.glob("*.rq"))),
             usage.mentions(sorted((usage.ONTO / "alignments").glob("*.ttl"))))
    categories = {}
    for term in terms:
        categories[term] = (STATUSES[0] if sum(data[term].values()) else
                            STATUSES[1] if any(c[term] for c in where) else
                            STATUSES[2] if structural[term] else STATUSES[3])
    return categories, manifest


def excerpt(evidence):
    """Prefer a matching English label/definition; keep actual evidence if neither matches."""
    def priority(item):
        preferred = item["field"] in ("rdfs:label", "skos:definition")
        english = (item["language"] or "").lower().split("-")[0] == "en"
        return (0 if preferred and english else 1 if english else 2,
                0 if item["field"] == "rdfs:label" else 1)

    first = min(evidence, key=priority)
    return " ".join(first["value"].split())[:100]


def inventory(graph, terms=None, categories=None):
    """Return matched rows with every matching field and its tokens as evidence.

    The CLI supplies term_usage.declared's exact term set and kinds. A small in-memory
    graph can use the same declaration rule for tests without reading the data release.
    """
    if terms is None:
        terms = {}
        for subject in set(graph.subjects(RDF.type, None)):
            if str(subject).startswith(usage.L):
                types = set(graph.objects(subject, RDF.type))
                terms[str(subject)[len(usage.L):]] = next(
                    (kind for iri, kind in usage.KIND if iri in types), "individual")
    present = [(prop, name) for prop, name in TEXT_PROPERTIES
               if any(graph.triples((None, prop, None)))]
    rows = []
    for term, kind in sorted(terms.items()):
        subject = rdflib.URIRef(usage.L + term)
        values = [("name", "IRI local name", term, None)]
        for group, properties in (("name", [(RDFS.label, "rdfs:label")]), ("text", present)):
            for prop, field in properties:
                for value in sorted(graph.objects(subject, prop), key=lambda v: (str(v), v.language or "")):
                    values.append((group, field, str(value), value.language))
        evidence = []
        for group, field, value, language in values:
            tokens = matched_tokens(value, local_name=field == "IRI local name")
            if tokens:
                evidence.append({"group": group, "field": field, "value": value,
                                 "language": language, "tokens": tokens})
        if not evidence:
            continue
        rows.append({"term": term, "kind": kind,
                     "usage": categories[term] if categories is not None else NO_USAGE,
                     "classification": "name" if any(e["group"] == "name" for e in evidence) else "text-only",
                     "tokens": tuple(t for t in TOKENS if any(t in e["tokens"] for e in evidence)),
                     "fields": tuple(dict.fromkeys(f"{e['group']}: {e['field']}" for e in evidence)),
                     "excerpt": excerpt(evidence), "evidence": evidence})
    return rows


def cell(value):
    """Keep annotation punctuation from breaking a Markdown table."""
    return str(value).replace("&", "&amp;").replace("|", "&#124;").replace("\n", " ")


def report(rows, n_terms, counts, manifest=None):
    classes = ("name", "text-only")
    totals = Counter(row["classification"] for row in rows)
    release_note = (f"graph release of {manifest['released']}" if manifest else
                    "usage not checked (`--no-usage`); no graph release loaded")
    lines = ["# France-related lulcw terms (generated)", "",
             f"Generated by `python -m src.kg.country_terms` (dataset **{DATASET}**, {release_note}); "
             f"do not edit by hand. Scanned **{n_terms}** declared terms in `ontology/lulcw.ttl`.", "",
             "Name = IRI local name and every `rdfs:label`; text = the annotation properties listed "
             "below. Matching is case-insensitive with accents folded and word boundaries. Camel case "
             "and underscores in local names are separated before matching. Only the fixed token list "
             "is used. A name match takes precedence over a text match; no term is moved by this audit.", "",
             "## Annotation properties checked", "",
             "Counts include the ontology header; only declared lulcw terms enter the inventory. "
             "Properties absent from the ontology are ignored.", "",
             "| property | triples in ontology |", "|---|---:|",
             *[f"| `{name}` | {n} |" for name, n in counts.items()], "",
             "## Summary", "",
             f"Matched **{len(rows)}** terms: **{totals['name']} name** and "
             f"**{totals['text-only']} text-only**. The external review (§2.2 point 1) reported "
             f"**49**; this fixed-token inventory finds **{len(rows)}**. "
             "Text-only matches can cite French sources for otherwise generic terms; "
             "these counts do not decide which terms belong in a country profile.", ""]
    kinds = [kind for _, kind in usage.KIND] + ["individual"]
    statuses = STATUSES if manifest else (NO_USAGE,)
    for title, keys, column in (("By token", TOKENS, "tokens"), ("By kind", kinds, "kind"),
                                ("By usage category", statuses, "usage")):
        lines += [f"### {title}", "", "| value | name | text-only | total |", "|---|---:|---:|---:|"]
        for key in keys:
            subtotal = Counter(row["classification"] for row in rows
                               if (key in row[column] if column == "tokens" else row[column] == key))
            lines.append(f"| {key} | {subtotal['name']} | {subtotal['text-only']} | {sum(subtotal.values())} |")
        lines.append("")
    lines += ["Token counts count terms once per token; a term can match several tokens. "
              "Usage categories and kinds follow `src.kg.term_usage` exactly, including alignments "
              "in the category named ‘rules, shapes or queries only’.", "",
              "The excerpt is the first 100 characters of a matching English label or definition. "
              "If neither matches, it shows the matching comment, other annotation, non-English label "
              "or local name instead. Fields list every place that matched.", ""]
    for classification in classes:
        lines += [f"## {'Name matches' if classification == 'name' else 'Text-only matches'} "
                  f"({totals[classification]})", "",
                  "| term | kind | usage | tokens matched | field(s) | matching excerpt |",
                  "|---|---|---|---|---|---|"]
        for row in rows:
            if row["classification"] == classification:
                values = (f"`{row['term']}`", row["kind"], row["usage"], ", ".join(row["tokens"]),
                          "; ".join(row["fields"]), row["excerpt"])
                lines.append("| " + " | ".join(cell(v) for v in values) + " |")
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-usage", action="store_true", help="scan ontology without loading the graph release")
    args = parser.parse_args()
    started = perf_counter()
    graph = rdflib.Graph().parse(usage.ONTO / "lulcw.ttl")
    counts = annotation_counts(graph)
    print("Annotation properties (triples in the whole ontology):", counts, flush=True)
    terms, structural = usage.declared()
    categories, manifest = (None, None) if args.no_usage else usage_categories(terms, structural)
    rows = inventory(graph, terms, categories)
    out = ROOT / "docs" / "ontology_country_terms.md"
    out.write_text(report(rows, len(terms), counts, manifest), encoding="utf-8")
    print(dict(Counter(row["classification"] for row in rows)), "->", out.relative_to(ROOT),
          f"({perf_counter() - started:.2f}s)")


if __name__ == "__main__":
    main()
