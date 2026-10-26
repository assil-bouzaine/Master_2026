"""AGROVOC Core (FAO's multilingual agricultural thesaurus) as a dated local snapshot, and its
French and English labels (task 12.9: RPG crop codes -> AGROVOC; LU-2).

    python -m src.ingest.agrovoc            # first run: downloads the current release; later
                                            # runs reuse the snapshot (the gold set is tied to it)
    python -m src.ingest.agrovoc --check    # compares the snapshot with the release online
                                            # (HEAD request only, nothing downloaded)

FAO serves only its newest release, at a fixed URL (https://agrovoc.fao.org/latestAgrovoc/, the
"AGROVOC Release" dataset of the FAO data catalogue, data.apps.fao.org/catalog); older releases
are sent on request only. So the zip is kept under the release date the server states
(Last-Modified), with its ETag, size and md5 and the release's VoID description, and it is never
downloaded again unless the snapshot folder is removed. The zip is read as a stream (its
N-Triples file is about ten times larger) and never extracted.

Outputs: data/raw/agrovoc/<YYYY-MM-DD>/agrovoc_core.nt.zip, void.ttl, release.json
         data/interim/agrovoc_labels.parquet   one row per concept, label and language (fr, en):
             concept, label, lang, kind (pref | alt), vocab (skos | skosxl), deprecated, release
         data/interim/agrovoc_broader.parquet  concept -> broader concept (skos:broader), release
"""
import argparse
import hashlib
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import pandas as pd

from src.config import INTERIM, RAW
from src.web import TIMEOUT, make_session

URL = "https://agrovoc.fao.org/latestAgrovoc/agrovoc_core.nt.zip"
VOID = "http://aims.fao.org/aos/agrovoc/void.ttl"
OUT = RAW / "agrovoc"
LABELS = INTERIM / "agrovoc_labels.parquet"
BROADER = INTERIM / "agrovoc_broader.parquet"
LANGS = ("fr", "en")
CHUNK = 1 << 20  # 1 MiB

SKOS = "http://www.w3.org/2004/02/skos/core#"
SKOSXL = "http://www.w3.org/2008/05/skos-xl#"
CONCEPT = f"{SKOS}Concept"
TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
DEPRECATED = "http://www.w3.org/2002/07/owl#deprecated"
KIND = {f"{SKOS}prefLabel": "pref", f"{SKOS}altLabel": "alt"}
XL_KIND = {f"{SKOSXL}prefLabel": "pref", f"{SKOSXL}altLabel": "alt"}
LITERAL_FORM = f"{SKOSXL}literalForm"

# N-Triples (W3C 2014): IRI subjects here (AGROVOC has no blank-node labels), IRI predicates
TRIPLE = re.compile(r'^<([^>]*)> <([^>]*)> (.*) \.\s*$')
LITERAL = re.compile(r'^"((?:[^"\\]|\\.)*)"(?:@([A-Za-z0-9-]+)|\^\^<([^>]*)>)?$')
ESCAPE = re.compile(r'\\(?:u([0-9A-Fa-f]{4})|U([0-9A-Fa-f]{8})|(.))')
SIMPLE = {"t": "\t", "b": "\b", "n": "\n", "r": "\r", "f": "\f", '"': '"', "'": "'", "\\": "\\"}


def unescape(s):
    return ESCAPE.sub(lambda m: chr(int(m.group(1) or m.group(2), 16)) if (m.group(1) or m.group(2))
                      else SIMPLE[m.group(3)], s)


def head(session):
    r = session.head(URL, timeout=TIMEOUT, allow_redirects=True)
    r.raise_for_status()
    return {"url": URL, "etag": r.headers.get("ETag", "").strip('"'),
            "last_modified": r.headers["Last-Modified"],
            "content_length": int(r.headers["Content-Length"])}


def snapshots():
    return sorted(d for d in OUT.glob("????-??-??") if (d / "release.json").exists())


def download(session):
    info = head(session)
    day = parsedate_to_datetime(info["last_modified"]).astimezone(timezone.utc).date().isoformat()
    d = OUT / day
    d.mkdir(parents=True, exist_ok=True)
    z, part = d / "agrovoc_core.nt.zip", d / "agrovoc_core.nt.zip.part"
    md5 = hashlib.md5()
    with session.get(URL, timeout=TIMEOUT, stream=True) as r:
        r.raise_for_status()
        etag = r.headers.get("ETag", "").strip('"')
        if etag != info["etag"]:
            raise RuntimeError(f"the release changed between HEAD and GET (ETag {info['etag']} -> {etag})")
        with part.open("wb") as f:
            for chunk in r.iter_content(CHUNK):
                f.write(chunk)
                md5.update(chunk)
    if part.stat().st_size != info["content_length"]:
        raise RuntimeError(f"{part}: {part.stat().st_size} bytes, Content-Length {info['content_length']}")
    part.rename(z)
    v = session.get(VOID, timeout=TIMEOUT)
    v.raise_for_status()
    (d / "void.ttl").write_bytes(v.content)
    info |= {"md5": md5.hexdigest(), "release_date": day,
             "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "void_url": VOID, "catalogue": "https://data.apps.fao.org/catalog/dataset/agrovoc-release",
             "licence": "CC BY 4.0 (FAO, AGROVOC)"}
    (d / "release.json").write_text(json.dumps(info, indent=2) + "\n")
    return d


def check(d):
    with zipfile.ZipFile(d / "agrovoc_core.nt.zip") as zf:   # opens: the zip is complete
        names = zf.namelist()
    info = json.loads((d / "release.json").read_text())
    md5 = hashlib.md5()
    with (d / "agrovoc_core.nt.zip").open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            md5.update(chunk)
    if md5.hexdigest() != info["md5"]:
        raise RuntimeError(f"{d}: md5 {md5.hexdigest()} differs from release.json ({info['md5']})")
    return names


def parse(d):
    """One pass over the N-Triples stream: SKOS and SKOS-XL labels in LANGS, skos:broader,
    concept typing and owl:deprecated."""
    plain, xl_links, xl_forms, broader = [], [], {}, []
    concepts, deprecated = set(), set()
    with zipfile.ZipFile(d / "agrovoc_core.nt.zip") as zf:
        (name,) = [n for n in zf.namelist() if n.endswith(".nt")]
        with zf.open(name) as raw:
            for line in io.TextIOWrapper(raw, encoding="utf-8"):
                m = TRIPLE.match(line)
                if not m:
                    continue
                s, p, o = m.groups()
                if p in KIND or p == LITERAL_FORM:
                    lit = LITERAL.match(o)
                    if not lit or lit.group(2) is None:
                        continue
                    lang = lit.group(2).lower()
                    if lang not in LANGS:
                        continue
                    text = unescape(lit.group(1))
                    if p == LITERAL_FORM:
                        xl_forms[s] = (text, lang)
                    else:
                        plain.append((s, text, lang, KIND[p], "skos"))
                elif p in XL_KIND:
                    xl_links.append((s, o[1:-1], XL_KIND[p]))
                elif p == f"{SKOS}broader" and o.startswith("<"):
                    broader.append((s, o[1:-1]))
                elif p == TYPE and o == f"<{CONCEPT}>":
                    concepts.add(s)
                elif p == DEPRECATED and o.startswith('"true"'):
                    deprecated.add(s)
    xl = [(c, *xl_forms[lab], kind, "skosxl") for c, lab, kind in xl_links if lab in xl_forms]
    labels = pd.DataFrame(plain + xl, columns=["concept", "label", "lang", "kind", "vocab"])
    labels = labels[labels["concept"].isin(concepts)].drop_duplicates()
    labels["deprecated"] = labels["concept"].isin(deprecated)
    edges = pd.DataFrame(broader, columns=["concept", "broader"]).drop_duplicates()
    edges = edges[edges["concept"].isin(concepts) & edges["broader"].isin(concepts)]
    return labels, edges, len(concepts), len(deprecated & concepts)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="compare the snapshot with the release online")
    args = ap.parse_args()
    session = make_session()
    have = snapshots()
    if args.check:
        online = head(session)
        for d in have:
            local = json.loads((d / "release.json").read_text())
            same = local["etag"] == online["etag"]
            print(f"{d.name}: ETag {local['etag']} ({'same as' if same else 'differs from'} the "
                  f"release online, {online['last_modified']})")
        if not have:
            print(f"no snapshot; online: {online}")
        return
    d = have[-1] if have else download(session)
    names = check(d)
    info = json.loads((d / "release.json").read_text())
    print(f"snapshot {d.name}: {info['content_length'] / 1e6:.1f} MB, md5 {info['md5']}, {names}")
    labels, edges, n_concepts, n_dep = parse(d)
    labels["release"] = edges["release"] = d.name
    labels.to_parquet(LABELS, index=False)
    edges.to_parquet(BROADER, index=False)
    by = labels.groupby(["lang", "kind", "vocab"]).size()
    print(f"{n_concepts} concepts ({n_dep} deprecated); labels in {LANGS}:\n{by.to_string()}")
    print(f"-> {LABELS.name}: {len(labels)} rows, {labels['concept'].nunique()} concepts; "
          f"{BROADER.name}: {len(edges)} broader links")


if __name__ == "__main__":
    main()
