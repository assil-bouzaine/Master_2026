"""Shared HTTP session with retries, used by every ingest script."""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TIMEOUT = (15, 180)  # (connect, read) seconds


def make_session() -> requests.Session:
    """Session that retries on 429 and 5xx with exponential backoff (2, 4, 8, ... s)."""
    retry = Retry(
        total=6,
        backoff_factor=2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        respect_retry_after_header=True,
    )
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers["User-Agent"] = "SAVE-Water-PFE/0.1 (research; ISAMM)"
    return s
