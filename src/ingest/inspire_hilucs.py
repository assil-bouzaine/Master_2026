"""INSPIRE HILUCS (Hierarchical INSPIRE Land Use Classification System) code list, from the INSPIRE
registry: the land-use values the crop classes of the graph are mapped to (src/kg/landuse.py,
configs/lu_hilucs.csv).

    python -m src.ingest.inspire_hilucs        # first run downloads; later runs reuse the snapshot

Source: https://inspire.ec.europa.eu/codelist/HILUCSValue/HILUCSValue.en.json (the registry's JSON
of the code list; each value's "id" is its IRI, e.g.
http://inspire.ec.europa.eu/codelist/HILUCSValue/1_1_1_CommercialAgriculturalProduction; checked
2026-11-16: 98 values, status Valid).

Outputs: data/raw/inspire_hilucs/<YYYY-MM-DD>/HILUCSValue.en.json, release.json (URL, date, size,
SHA-256, value count). The graph reads the snapshot pinned in configs/snapshots.json.
"""
import hashlib
import json
from datetime import date

from src.config import RAW
from src.web import TIMEOUT, make_session

URL = "https://inspire.ec.europa.eu/codelist/HILUCSValue/HILUCSValue.en.json"
OUT = RAW / "inspire_hilucs"
NAME = "HILUCSValue.en.json"


def snapshot():
    done = sorted(d for d in OUT.glob("????-??-??") if (d / "release.json").exists())
    return done[-1] if done else None


def values(path):
    """IRI -> {label, definition, parent, status} from a stored code-list file."""
    text = lambda x: x.get("text") if isinstance(x, dict) else x  # noqa: E731
    out = {}
    for it in json.loads(path.read_text(encoding="utf-8"))["codelist"]["containeditems"]:
        v = it["value"]
        parents = v.get("parents") or []
        out[v["id"]] = {"label": text(v.get("label")), "definition": text(v.get("definition")),
                        "parent": parents[0]["parent"]["id"] if parents else None,
                        "status": text(v.get("status", {}).get("label")) if isinstance(v.get("status"), dict) else None}
    return out


def main():
    have = snapshot()
    if have is not None:
        print(f"snapshot {have} exists: nothing downloaded")
        return
    d = OUT / date.today().isoformat()
    d.mkdir(parents=True, exist_ok=True)
    r = make_session().get(URL, timeout=TIMEOUT)
    r.raise_for_status()
    (d / NAME).write_bytes(r.content)
    vals = values(d / NAME)
    rel = {"url": URL, "retrieved": date.today().isoformat(), "bytes": len(r.content),
           "sha256": hashlib.sha256(r.content).hexdigest(), "values": len(vals),
           "valid": sum(v["status"] == "Valid" for v in vals.values())}
    (d / "release.json").write_text(json.dumps(rel, indent=1))
    print(f"-> {d}: {rel['values']} values ({rel['valid']} Valid), {rel['bytes'] / 1e3:.0f} kB")


if __name__ == "__main__":
    main()
