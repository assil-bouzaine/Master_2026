"""Harvest the pre-specified paper set for R2.1 Track 1 (docs/v5_plan.md, row 2.1).

The ten searches in configs/openalex_track1_queries.json are fixed before any
results are seen, in this order:
q01 groundwater irrigation Mediterranean aquifer overexploitation
q02 land use change groundwater recharge Mediterranean
q03 irrigation canal return flow aquifer recharge
q04 groundwater level decline irrigation Spain
q05 groundwater depletion irrigation Tunisia
q06 groundwater irrigation aquifer Morocco
q07 drought groundwater level Mediterranean
q08 nitrate groundwater agriculture Mediterranean
q09 seawater intrusion coastal aquifer pumping Mediterranean
q10 olive orchard vineyard irrigation groundwater
Each requests one page of 25 articles, open access since 2010-01-01, sorted by
relevance_score:desc.
Only works with DOI, title, best_oa_location.pdf_url, language en/fr and no
retraction qualify. Keep their response order, then take one per query q01-q10
per round, skipping duplicate DOIs (case-insensitive) and OpenAlex ids, to 30 or
exhaustion. rank_in_query keeps the original response position for traceability.
No rule examines a paper's findings, and there is no extra geographic screening.

Use the shared retrying session with a generic User-Agent, no key or personal
data, and one second between requests. Raw responses are cached once under
data/raw/openalex/<date>/<query id>.json. Re-runs never request cached queries.
PDFs go through a temporary name into pdf/<OpenAlex short id>.pdf; existing
valid files are reused. Refuse bodies without %PDF- or larger than 25 MiB.
Record failures and replace them by the next unique candidate in the same
round-robin order until 30 PDFs exist or the candidates run out. The CSV retains
failed attempts as well as the papers downloaded, so replacements are auditable.

    PFE_DATASET=v5 python -m src.ingest.openalex search --date YYYY-MM-DD
    PFE_DATASET=v5 python -m src.ingest.openalex select --dry-run --date YYYY-MM-DD
    PFE_DATASET=v5 python -m src.ingest.openalex download --date YYYY-MM-DD

Search writes the initial metadata selection; download writes the attempted
selection with status, reason, size and SHA-256 to configs/track1_papers.csv.
harvest.json holds request parameters, URLs, counts, UTC timestamps and download
attempts. Failed attempts stay fixed for that dated snapshot, so a re-run cannot
change the paper set because a failed host happens to recover. Search preserves
an existing download selection. A new date starts a new harvest.
Select reads only a complete cache and writes nothing. An explicit date reuses
the same snapshot on another day. Tests use hand-written synthetic API fixtures;
they never contact OpenAlex or a PDF host.
"""
import argparse
import csv
import hashlib
import io
import json
import re
import tempfile
import time
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

import requests

from src.config import RAW, ROOT
from src.web import TIMEOUT, make_session

CONFIG = ROOT / "configs" / "openalex_track1_queries.json"
OUT = RAW / "openalex"
PAPERS = ROOT / "configs" / "track1_papers.csv"
COLUMNS = (
    "order", "query_id", "rank_in_query", "openalex_id", "doi", "title",
    "year", "venue", "language", "licence", "pdf_url", "download_status",
    "download_reason", "file_size", "sha256",
)


def load_config(path=CONFIG):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if [q["id"] for q in config["queries"]] != [f"q{i:02d}" for i in range(1, 11)]:
        raise ValueError("expected queries q01 to q10, in that order")
    return config


def request_parameters(config, query):
    return {"search": query["search"], **config["parameters"]}


def request_url(config, query):
    return requests.Request("GET", config["endpoint"],
                            params=request_parameters(config, query)).prepare().url


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def atomic_save(path, body):
    """Only publish a complete file; remove the temporary copy on failure."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".",
                                         suffix=".part", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(body)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_manifest(path, manifest):
    atomic_save(path, (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


class Requester:
    """Space requests, including PDF requests, without sleeping on cache hits."""
    def __init__(self, config, session=None):
        self.session = session if session is not None else make_session()
        # Clear inherited headers, authentication and netrc/proxy settings. Only
        # the generic agent header is sent, including on redirected requests.
        self.session.headers.clear()
        self.session.headers["User-Agent"] = config["user_agent"]
        self.session.auth = None
        self.session.trust_env = False
        self.interval = config["request_interval_seconds"]
        self.last_request = None

    def get(self, url, **kwargs):
        if self.last_request is not None:
            time.sleep(max(0, self.interval - (time.monotonic() - self.last_request)))
        self.session.cookies.clear()
        self.last_request = time.monotonic()
        return self.session.get(url, timeout=TIMEOUT, **kwargs)


def rejection_reason(work):
    """Use OpenAlex Work fields; missing optional metadata stays empty."""
    if not work.get("doi") or not str(work["doi"]).strip():
        return "missing DOI"
    if not (work.get("best_oa_location") or {}).get("pdf_url"):
        return "missing PDF URL"
    if work.get("language") not in ("en", "fr"):
        return "language outside en/fr"
    if work.get("is_retracted"):
        return "retracted"
    if not work.get("title") or not str(work["title"]).strip():
        return "missing title"
    return None


def eligible_rows(payload, query_id):
    rows = []
    rejected = Counter()
    for rank, work in enumerate(payload["results"], 1):
        reason = rejection_reason(work)
        if reason:
            rejected[reason] += 1
            continue
        location = work["best_oa_location"]
        rows.append(dict(query_id=query_id, rank_in_query=rank,
                         openalex_id=work.get("id") or "", doi=work["doi"],
                         title=work["title"], year=work.get("publication_year") or "",
                         venue=((work.get("primary_location") or {}).get("source") or {}).get(
                             "display_name") or "",
                         language=work["language"], licence=location.get("license") or "",
                         pdf_url=location["pdf_url"], download_status="pending",
                         download_reason="", file_size="", sha256=""))
    counts = {"returned": len(payload["results"]), "eligible": len(rows),
              "rejected": dict(sorted(rejected.items()))}
    return rows, counts


def round_robin(lists):
    """Yield unique candidates once; a failed download cannot return as a duplicate."""
    dois, ids = set(), set()
    for rank in range(max((len(rows) for rows in lists), default=0)):
        for rows in lists:
            if rank >= len(rows):
                continue
            row = rows[rank]
            doi = row["doi"].strip().casefold()
            work_id = row["openalex_id"]
            if doi in dois or (work_id and work_id in ids):
                continue
            dois.add(doi)
            if work_id:
                ids.add(work_id)
            yield dict(row)


def validate_payload(body):
    payload = json.loads(body)
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError("OpenAlex response must have a results list")
    return payload


def read_candidates(config, folder, fetch=False, requester=None):
    """Read every cached page; only search may fill missing pages."""
    manifest_path = folder / "harvest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {
        "date": folder.name, "started_at": utc_now(), "design": config,
        "parameters": config["parameters"], "queries": {},
    }
    if manifest["design"] != config:
        raise ValueError("the query design differs from this dated harvest; use its original config")
    lists = []
    printed = False
    for query in config["queries"]:
        query_id = query["id"]
        path = folder / f"{query_id}.json"
        if not path.exists():
            if not fetch:
                raise FileNotFoundError(f"missing cache {path}; run search with the same --date first")
            response = requester.get(config["endpoint"], params=request_parameters(config, query))
            try:
                response.raise_for_status()
                body = response.content
                validate_payload(body)
                atomic_save(path, body)
            finally:
                response.close()
        payload = validate_payload(path.read_bytes())
        if not printed:
            print("OpenAlex response keys:", sorted(payload))
            if payload["results"]:
                print("OpenAlex first work keys:", sorted(payload["results"][0]))
                print("OpenAlex first work:", json.dumps(payload["results"][0], ensure_ascii=False))
                printed = True
        rows, counts = eligible_rows(payload, query_id)
        lists.append(rows)
        previous = manifest["queries"].get(query_id, {})
        manifest["queries"][query_id] = {
            "parameters": request_parameters(config, query), "request_url": request_url(config, query),
            "retrieved_at": previous.get("retrieved_at") or datetime.fromtimestamp(
                path.stat().st_mtime, timezone.utc).isoformat(), **counts,
        }
        if fetch:
            # Saving after each query makes an interrupted harvest resumable.
            manifest["updated_at"] = utc_now()
            save_manifest(manifest_path, manifest)
    return list(round_robin(lists)), manifest


def write_papers(path, rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    atomic_save(path, stream.getvalue().encode("utf-8"))


def pdf_details(path, maximum):
    """Validate stored files too; never silently count a partial body."""
    size = path.stat().st_size
    if size > maximum:
        raise ValueError(f"PDF exceeds {maximum} bytes")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        if stream.read(5) != b"%PDF-":
            raise ValueError("body does not start with %PDF-")
        stream.seek(0)
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return size, digest.hexdigest()


def download_pdf(row, folder, requester, maximum):
    short_id = row["openalex_id"].rsplit("/", 1)[-1]
    if not re.fullmatch(r"W[0-9]+", short_id):
        raise ValueError("missing or invalid OpenAlex work id for PDF filename")
    path = folder / "pdf" / f"{short_id}.pdf"
    if path.exists():
        return pdf_details(path, maximum)
    path.parent.mkdir(parents=True, exist_ok=True)
    response = requester.get(row["pdf_url"], stream=True)
    temporary = None
    try:
        response.raise_for_status()
        length = response.headers.get("Content-Length")
        if length and int(length) > maximum:
            raise ValueError(f"PDF exceeds {maximum} bytes (Content-Length)")
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".",
                                         suffix=".part", delete=False) as stream:
            temporary = Path(stream.name)
            size = 0
            for chunk in response.iter_content(chunk_size=65536):
                size += len(chunk)
                if size > maximum:
                    raise ValueError(f"PDF exceeds {maximum} bytes (stream)")
                stream.write(chunk)
        details = pdf_details(temporary, maximum)
        temporary.replace(path)
        return details
    finally:
        response.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def run(command, day=None, dry_run=False, config_path=CONFIG, out=OUT,
        papers=PAPERS, session=None):
    if command == "select" and not dry_run:
        raise ValueError("select requires --dry-run")
    if dry_run and command != "select":
        raise ValueError("--dry-run is only supported for select")
    day = day or date.today().isoformat()
    if date.fromisoformat(day).isoformat() != day:
        raise ValueError("date must be YYYY-MM-DD")
    config = load_config(config_path)
    folder = Path(out) / day
    requester = Requester(config, session) if command in ("search", "download") else None
    candidates, manifest = read_candidates(config, folder, fetch=command == "search", requester=requester)
    if command == "search" and "downloads" in manifest:
        rows = manifest["downloads"]
        write_papers(papers, rows)
        print(f"search: preserved {len(rows)} recorded download attempts; metadata: {papers}")
        return rows
    previous = {r["doi"].strip().casefold(): r for r in manifest.get("downloads", [])}
    if command == "download":
        manifest.setdefault("download_started_at", utc_now())
    rows = []
    successes = 0
    for candidate in candidates:
        row = {"order": len(rows) + 1, **candidate}
        if command == "download":
            prior = previous.get(row["doi"].strip().casefold())
            if prior and prior["download_status"] == "failed":
                row.update(download_status="failed", download_reason=prior["download_reason"])
            else:
                try:
                    size, digest = download_pdf(row, folder, requester, config["max_pdf_bytes"])
                    if prior and prior["sha256"] != digest:
                        raise ValueError("stored PDF differs from its recorded SHA-256")
                    row.update(download_status="downloaded", file_size=size, sha256=digest)
                    successes += 1
                except (requests.RequestException, OSError, ValueError) as error:
                    row.update(download_status="failed", download_reason=f"{type(error).__name__}: {error}")
        else:
            successes += 1
        rows.append(row)
        if not dry_run:
            # Keep completed attempts even if a later request is interrupted.
            if command == "download":
                # Keep the whole old journal until this run is complete. If a
                # re-run stops early, failures further down the order stay fixed.
                previous[row["doi"].strip().casefold()] = row
                manifest.update(downloads=list(previous.values()), updated_at=utc_now())
                save_manifest(folder / "harvest.json", manifest)
            write_papers(papers, rows)
        if successes >= config["target"]:
            break
    if dry_run:
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        print(stream.getvalue(), end="")
    else:
        write_papers(papers, rows)
        if command == "download":
            manifest["downloads"] = rows
            manifest["download_completed_at"] = utc_now()
        manifest.update(updated_at=utc_now(), last_command=command,
                        candidates=len(candidates), attempted=len(rows),
                        selected=successes, failed=sum(r["download_status"] == "failed" for r in rows))
        save_manifest(folder / "harvest.json", manifest)
        print(f"{command}: {successes} selected, {len(rows)} rows; metadata: {papers}")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("search", "download", "select"))
    parser.add_argument("--date", help="dated cache to create or reuse (default: today)")
    parser.add_argument("--dry-run", action="store_true", help="required for select; writes nothing")
    args = parser.parse_args()
    run(args.command, args.date, args.dry_run)


if __name__ == "__main__":
    main()
