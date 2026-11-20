"""Check the real Influence figure against CQ8 and the released graph.

This checks the traceable graph pattern of analysis plan section 14. Select
the example independently, inspect the actual plotted edges and labels, and
compare a second build made in a fresh process. No graph or model is fitted.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 nice -n 15 .venv/bin/python -m tests.test_fig_influence
"""
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

from paper.tools import fig_influence as figure

from PIL import Image
from matplotlib.backends.backend_agg import FigureCanvasAgg
import pyoxigraph as ox
import rdflib
from rdflib.namespace import RDF, RDFS, SKOS

from src.analysis.lu6_example import MAIN
from src.kg.cq import ask, iris, kg_store, local

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / "results/_agents/tmp/T22"


def _words(text):
    return " ".join(text.split())


def _labels():
    labels = rdflib.Graph().parse(ROOT / "ontology/lulcw.ttl")
    for path in sorted((ROOT / "ontology/imports").glob("*.ttl")):
        labels.parse(path)
    return labels


def _english_values(labels, predicate):
    """Read expected labels directly from the RDF files, without the figure helper."""
    for label_property in (RDFS.label, SKOS.prefLabel):
        values = {str(value) for value in labels.objects(rdflib.URIRef(predicate.value), label_property)
                  if isinstance(value, rdflib.Literal) and value.language
                  and value.language.lower().split("-")[0] == "en"}
        if values:
            return values
    return set()


def _check_selection(store, result):
    well = iris(store, "SELECT ?code ?well WHERE { ?well a lulcw:Piezometer ; lulcw:bssCode ?code }")["10906X0039/C2-1"]
    rows = ask(store, "cq08_influences", W=well, policy=MAIN)
    eligible = [row for row in rows if row["selected"] and row["constrained"]
                and row["mechanism"] == str(figure.L.PumpingDrawdown)
                and row["eligibility"] == str(figure.L.EligibleConstraint)]
    expected = min(eligible, key=lambda row: (row["distanceM"], row["driverCode"], row["influence"]))
    assert result["influence"].value == expected["influence"]
    assert result["candidate"] == expected
    print(f"  1. independent CQ8 selection: {len(eligible)} candidates; {expected['driverCode']} "
          f"at {expected['distanceM']:.6f} m")


def _check_edges(store, labels, result):
    subject = result["influence"]
    queried = {(row["p"], row["o"]) for row in store.query(f"SELECT ?p ?o WHERE {{ {subject} ?p ?o }}")}
    direct = [edge for edge in result["edges"] if edge.subject == subject]
    assert {(edge.predicate, edge.object) for edge in direct} == queried
    assert len(direct) == len(queried), "An Influence triple must not be drawn twice"
    ax = result["figure"].axes[0]
    all_node_terms = {node.term for node in result["nodes"].values()}
    missing = set()
    for edge in result["edges"]:
        assert edge.artist in ax.patches and edge.artist.get_visible()
        assert edge.text in ax.texts and edge.text.get_visible()
        assert edge.subject in all_node_terms and edge.object in all_node_terms
        assert edge.artist.get_gid().startswith("rdf-edge-")
        actual = _words(edge.text.get_text())
        if expected := _english_values(labels, edge.predicate):
            assert edge.label in expected and actual == edge.label, (edge.predicate, actual, expected)
        else:
            assert actual == local(edge.predicate.value), (edge.predicate, actual)
            missing.add(edge.predicate)
        # Attribution edges are also real triples, rather than inferred shortcuts.
        exists = store.query(f"ASK {{ {edge.subject} {edge.predicate} {edge.object} }}")
        assert bool(exists), (edge.subject, edge.predicate, edge.object)
    assert set(result["missing_labels"]) == missing
    attr_subjects = {ox.NamedNode(result["candidate"][key]) for key in ("driverAttribution", "wellAttribution")}
    assert {edge.subject for edge in result["edges"] if edge.subject != subject} == attr_subjects
    for attr in attr_subjects:
        predicates = {edge.predicate.value for edge in result["edges"] if edge.subject == attr}
        assert {str(figure.L.confidence), str(figure.L.derivationRule), str(figure.L.attributedEntity)} <= predicates
        assert str(figure.L.candidateUnit) in predicates or str(figure.L.candidateGroup) in predicates
    print(f"  2. all {len(direct)} outgoing Influence triples appear once as actual arrows; "
          f"all {len(result['edges'])} drawn edges are graph triples and use their English property label "
          f"or the local-name fallback ({len(missing)} properties)")


def _check_nodes(store, labels, result):
    record = result["influence"]
    distance_objects = {edge.object for edge in result["edges"]
                        if edge.subject == record and edge.predicate.value == str(figure.L.horizontalDistanceM)}
    for node in result["nodes"].values():
        text = _words(node.text.get_text())
        assert node.artist is not None and node.text is not None
        if isinstance(node.term, ox.Literal):
            if node.term in distance_objects:
                assert text == f"{float(node.term.value) / 1000:.1f} km"
            else:
                assert text == _words(node.term.value), "Literal explanation was shortened or changed"
        else:
            facts = list(store.query(f"SELECT ?p ?o WHERE {{ {node.term} ?p ?o }}"))
            codes = [row["o"].value for row in facts if row["p"].value in {
                str(figure.L.bnpeCode), str(figure.L.bssCode), str(figure.L.bdlisaCode)}]
            identifiers = codes or [local(node.term.value)]
            assert any(code in text for code in identifiers)
            types = {row["o"].value for row in facts if row["p"].value == str(RDF.type)}
            types |= {str(value) for value in labels.objects(rdflib.URIRef(node.term.value), RDF.type)}
            class_labels = set().union(*(_english_values(labels, ox.NamedNode(kind)) for kind in types))
            if class_labels:
                assert any(text.startswith(label + " ") for label in class_labels), (text, class_labels)
    unit = result["nodes"]["unit"]
    assert result["candidate"]["viaCode"] in unit.label
    assert result["candidate"]["driverCode"] in result["nodes"]["driver"].label
    assert "10906X0039/C2-1" in result["nodes"]["target"].label
    assert set(node.group for node in result["nodes"].values()) == set(figure.FILLS)
    print("  3. node identities and shared BD LISA code match the graph; literal explanations are complete, "
          "distance is converted to km with one decimal, and all four colour groups appear")


def _check_layout(result):
    fig = result["figure"]
    width, height = fig.get_size_inches() * 25.4
    assert abs(width - 190) < 1e-8 and height <= 110 + 1e-8
    canvas = FigureCanvasAgg(fig)
    canvas.draw()
    renderer = canvas.get_renderer()
    overflows = []
    for key, node in result["nodes"].items():
        text_box = node.text.get_window_extent(renderer)
        node_box = node.artist.get_window_extent(renderer)
        if (text_box.x0 < node_box.x0 - 0.6 or text_box.x1 > node_box.x1 + 0.6
                or text_box.y0 < node_box.y0 - 0.6 or text_box.y1 > node_box.y1 + 0.6):
            overflows.append((key, tuple(text_box.bounds), tuple(node_box.bounds)))
    assert not overflows, overflows
    all_text = [*fig.axes[0].texts, *fig.axes[0].get_legend().get_texts()]
    for text in all_text:
        assert 7 <= text.get_fontsize() <= 8
        bounds = text.get_window_extent(renderer)
        assert (bounds.x0 >= fig.bbox.x0 and bounds.x1 <= fig.bbox.x1
                and bounds.y0 >= fig.bbox.y0 and bounds.y1 <= fig.bbox.y1), text.get_text()
    print(f"  4. layout: {width:g} x {height:g} mm, fonts 7–8 pt, all node text fits its box")


def _check_artifacts(first, second):
    for name in ("influence.pdf", "influence.png"):
        assert (first / name).is_file() and (first / name).stat().st_size > 0
        assert (first / name).read_bytes() == (second / name).read_bytes(), name
    pdf = (first / "influence.pdf").read_bytes()
    assert pdf.startswith(b"%PDF-") and b"/Subtype /Image" not in pdf
    assert b"/CreationDate" not in pdf and b"/ModDate" not in pdf
    media = re.search(rb"/MediaBox\s*\[\s*([\d.\s]+)\]", pdf)
    assert media
    x0, y0, x1, y1 = map(float, media[1].split())
    assert abs((x1 - x0) / 72 * 25.4 - 190) < 1e-6 and (y1 - y0) / 72 * 25.4 <= 110 + 1e-6
    with Image.open(first / "influence.png") as png:
        assert png.format == "PNG" and abs(png.width - 190 / 25.4 * 220) < 1
        assert abs(png.height - 110 / 25.4 * 220) < 1
    print("  5. non-empty PDF and PNG; vector PDF with the required page size and no timestamps; "
          "identical bytes from the in-process build and a fresh CLI process")


def test_figure():
    store, labels = kg_store(), _labels()
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=SCRATCH) as temporary:
        first, second = (Path(temporary) / name for name in ("first", "second"))
        result = figure.draw_influence(first, store=store, labels=labels)
        _check_selection(store, result)
        _check_edges(store, labels, result)
        _check_nodes(store, labels, result)
        _check_layout(result)
        cold = subprocess.run([sys.executable, "paper/tools/fig_influence.py", "--out", str(second)],
                              cwd=ROOT, capture_output=True, text=True)
        assert cold.returncode == 0, cold.stdout + cold.stderr
        assert result["influence"].value in cold.stdout
        assert "Qualifying CQ8 candidates" in cold.stdout
        _check_artifacts(first, second)


def main():
    started = time.perf_counter()
    test_figure()
    print(f"test_fig_influence: all checks passed ({time.perf_counter() - started:.2f}s)")


if __name__ == "__main__":
    main()
