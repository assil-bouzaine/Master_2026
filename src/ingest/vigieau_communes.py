"""The daily drought-restriction level of each commune of a département, from VigiEau (for CQ9).

    python -m src.ingest.vigieau_communes            # cached: skips the download and the parse if done

Source: data.gouv.fr "Donnée Sécheresse - VigiEau" (dataset 662a5e2cd71b24df5e9a0827, Etalab 2.0),
resource "Historique Communes" (`historique-communes.zip`, 594 MB, one 12 GB JSON array): for every
French commune and every day since 2010-05-01, the highest restriction level in force for surface water
(SUP), groundwater (SOU) and drinking water (AEP, only from 2024-04-28), as VigiEau assigns alert zones
to communes. When several zones of one type overlap a commune, VigiEau keeps the highest level.

Why: CQ9 (docs/competency_questions.md) asks which restrictions applied at the location of a well or an
abstraction point, on official spatial evidence. The order files (`src.ingest.vigieau`) name alert zones
but carry no geometry, and VigiEau's yearly zone maps are national archives of 0.04-12 GB each; the
commune history is VigiEau's own spatial assignment, so a well inherits the levels of the commune it
stands in (its INSEE code). A null level means no restriction recorded for that type on that day, not an
unknown: VigiEau lists every commune every day.

The archive is never unpacked on disk: the JSON array is streamed from the zip, cut at each
`{"commune":` record and only the département's records are parsed.

Outputs
    data/raw/vigieau/2026-11-26/historique-communes.zip        download (cached; SHA-256 printed)
    data/interim/vigieau_communes_<dept>.parquet               commune, name, date, SUP, SOU, AEP
        levels as integers: 0 none (null), 1 vigilance, 2 alerte, 3 alerte renforcée, 4 crise

Not a model input (docs/analysis_plan.md §7: groundwater orders are triggered by the piezometers we
predict); used only for explanation context (CQ9).
"""
import hashlib
import json
import re
import zipfile

import pandas as pd

from src.config import DEPARTEMENT, INTERIM, RAW
from src.ingest.vigieau import LEVEL

URL = ("https://static.data.gouv.fr/resources/donnee-secheresse-vigieau/20261126-170419/"
       "historique-communes.zip")
SNAPSHOT = "2026-11-26"
ZIP = RAW / "vigieau" / SNAPSHOT / "historique-communes.zip"
MEMBER = "historique_communes.json"
START = b'{"commune":{"code":"'
TYPES = ("SUP", "SOU", "AEP")


def out_path(dept=DEPARTEMENT):
    return INTERIM / f"vigieau_communes_{dept}.parquet"


def download():
    """Fetch the archive once (594 MB); a complete file is kept."""
    if ZIP.exists() and ZIP.stat().st_size > 500e6:
        return
    from src.web import make_session
    ZIP.parent.mkdir(parents=True, exist_ok=True)
    tmp = ZIP.with_suffix(".tmp")
    with make_session().get(URL, timeout=600, stream=True) as r:
        r.raise_for_status()
        with tmp.open("wb") as f:
            for block in r.iter_content(1 << 22):
                f.write(block)
    tmp.replace(ZIP)


def records(dept=DEPARTEMENT, chunk=1 << 26):
    """Yield the parsed records of the département's communes, streaming the JSON array."""
    prefix = START + str(dept).encode()
    with zipfile.ZipFile(ZIP) as z, z.open(MEMBER) as stream:
        buf = b""
        while True:
            block = stream.read(chunk)
            buf += block
            starts = [m.start() for m in re.finditer(re.escape(START), buf)]
            # every record but the last one in the buffer is complete
            complete = starts if not block else starts[:-1]
            for i, s in enumerate(complete):
                end = starts[i + 1] if i + 1 < len(starts) else len(buf)
                if buf.startswith(prefix, s):
                    text = buf[s:end].rstrip().rstrip(b",").rstrip(b"]").rstrip()
                    yield json.loads(text)
            if not block:
                return
            buf = buf[starts[-1]:] if starts else buf[-len(START):]


def level(value):
    if value is None:
        return 0
    if value not in LEVEL:
        raise ValueError(f"unknown VigiEau level {value!r}")
    return LEVEL[value]


def build(dept=DEPARTEMENT):
    rows = []
    for rec in records(dept):
        code, name = rec["commune"]["code"], rec["commune"]["nom"]
        for r in rec["restrictions"]:
            rows.append((code, name, r["date"], *(level(r[t]) for t in TYPES)))
    df = pd.DataFrame(rows, columns=["commune", "name", "date", *TYPES])
    df["date"] = pd.to_datetime(df["date"])
    for t in TYPES:
        df[t] = df[t].astype("int8")
    return df.sort_values(["commune", "date"]).reset_index(drop=True)


def main():
    download()
    digest = hashlib.sha256(ZIP.read_bytes()).hexdigest()
    out = out_path()
    if out.exists():
        print(f"cached {out}")
        return
    df = build()
    df.to_parquet(out, index=False)
    print(f"{ZIP.name}: {ZIP.stat().st_size:,} bytes, SHA-256 {digest}")
    print(f"-> {out}: {len(df):,} rows, {df['commune'].nunique()} communes, "
          f"{df['date'].min().date()} to {df['date'].max().date()}")
    for t in TYPES:
        print(f"   {t}: days with a restriction {int((df[t] > 0).sum()):,}; levels {sorted(df[t].unique())}")


if __name__ == "__main__":
    main()
