"""Draw one real pumping Influence and its attribution evidence from the released KG.

This illustrates the conditional Influence pattern and the graph's traceability
in analysis plan section 14, items 14 and 17. Select the nearest eligible,
constrained pumping record at MILLAS C2-1 under the main policy, using CQ8.
Draw all of that record's outgoing triples, including literal explanations,
and the two attributions' entities, unit, rules and confidence. Labels come
from lulcw.ttl and its local imports. Nothing is fitted or fetched.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 nice -n 15 .venv/bin/python paper/tools/fig_influence.py [--out DIR]
"""
import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import sys
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = ROOT / "results/_agents/tmp/T22"
os.environ.setdefault("MPLCONFIGDIR", str(SCRATCH / "matplotlib"))
if not __package__:
    sys.path.insert(0, str(ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch
from matplotlib.path import Path as MplPath
import pyoxigraph as ox
import rdflib
from rdflib.namespace import PROV, RDF, RDFS, SKOS

from src.analysis.lu6_example import MAIN
from src.kg.build_kg import L
from src.kg.cq import ask, iris, kg_store, local

OUT = ROOT / "paper/figures"
WELL_CODE = "10906X0039/C2-1"
WIDTH_MM, HEIGHT_MM = 190, 110
INK = "#283641"
LINE = "#78858e"
FILLS = {"record": "#eae5f5", "entities": "#e6eff8", "evidence": "#faf0dd", "values": "#e8f2eb"}


def named(term):
    return ox.NamedNode(str(term))


def outgoing(store, subject):
    """Keep RDF terms, including literal datatypes, instead of flattening them to text."""
    return tuple(sorted(((row["p"], row["o"]) for row in store.query(
        f"SELECT ?p ?o WHERE {{ {subject} ?p ?o }}")), key=lambda pair: (str(pair[0]), str(pair[1]))))


def ontology_labels():
    graph = rdflib.Graph().parse(ROOT / "ontology/lulcw.ttl")
    for path in sorted((ROOT / "ontology/imports").glob("*.ttl")):
        graph.parse(path)
    return graph


def english_label(graph, term):
    """Prefer rdfs:label, then skos:prefLabel, with stable choices among English variants."""
    for predicate in (RDFS.label, SKOS.prefLabel):
        labels = [value for value in graph.objects(rdflib.URIRef(term.value), predicate)
                  if isinstance(value, rdflib.Literal) and value.language
                  and value.language.lower().split("-")[0] == "en"]
        if labels:
            return str(min(labels, key=lambda value: (value.language.lower() != "en", str(value))))
    return None


def select_record(store, print_candidates=True):
    wells = iris(store, "SELECT ?c ?w WHERE { ?w a lulcw:Piezometer ; lulcw:bssCode ?c }")
    rows = ask(store, "cq08_influences", W=wells[WELL_CODE], policy=MAIN)
    candidates = sorted((row for row in rows if local(row["mechanism"]) == "PumpingDrawdown"
                         and row["selected"] and local(row["eligibility"]) == "EligibleConstraint"
                         and row["constrained"]),
                        key=lambda row: (row["distanceM"], row["driverCode"], row["influence"]))
    if print_candidates:
        print("Qualifying CQ8 candidates (distance in metres, then facility code):", flush=True)
        for row in candidates:
            print(f"  {row['driverCode']}  {row['distanceM']:.12f} m  {row['influence']}", flush=True)
    if not candidates:
        raise ValueError("CQ8 returned no selected, eligible, constrained pumping influence for " + WELL_CODE)
    return candidates[0]


@dataclass
class Node:
    term: object
    label: str
    group: str
    xy: tuple
    size: tuple
    artist: object = None
    text: object = None


@dataclass
class Edge:
    subject: object
    predicate: object
    object: object
    label: str
    points: tuple
    label_xy: tuple
    label_width: float = 25
    artist: object = None
    text: object = None


def diagram(store, labels, candidate):
    """Assign fixed slots to graph terms; refuse an unplaced triple rather than omit it."""
    influence = ox.NamedNode(candidate["influence"])
    triples = outgoing(store, influence)
    cache = {influence: triples}

    def pairs(term):
        if term not in cache:
            cache[term] = outgoing(store, term)
        return cache[term]

    def objects(term, predicate):
        return [value for prop, value in pairs(term) if prop == named(predicate)]

    def one(term, predicate):
        values = objects(term, predicate)
        if len(values) != 1:
            raise ValueError(f"Expected one {predicate} on {term}, found {len(values)}")
        return values[0]

    def identifier(term):
        for predicate in (L.bnpeCode, L.bssCode, L.bdlisaCode):
            if values := objects(term, predicate):
                return values[0].value
        if values := objects(term, L.attributedEntity):
            return identifier(values[0]) + " / " + local(term.value)
        return unquote(local(term.value))

    def node_label(term):
        if isinstance(term, ox.Literal):
            return term.value
        uri = rdflib.URIRef(term.value)
        types = set(labels.objects(uri, RDF.type)) | {rdflib.URIRef(value.value) for value in objects(term, RDF.type)}
        types = sorted(types, key=lambda value: (not str(value).startswith(str(L)), str(value)))
        kind = (english_label(labels, named(types[0])) or local(str(types[0]))) if types else ""
        value = identifier(term)
        if term == named(L.NegativeResponse):
            value += " (" + english_label(labels, term) + ")"
        return (kind + "\n" if kind else "") + value

    nodes, edges, missing = {}, [], set()

    def add_node(key, term, group, xy, size, label=None):
        nodes[key] = Node(term, node_label(term) if label is None else label, group, xy, size)
        return nodes[key]

    def add_edge(subject, predicate, obj, points, label_xy, width=25):
        predicate = named(predicate) if not isinstance(predicate, ox.NamedNode) else predicate
        label = english_label(labels, predicate)
        if label is None:
            label = local(predicate.value)
            missing.add(predicate)
        edge = Edge(subject, predicate, obj, label, tuple(points), label_xy, width)
        edges.append(edge)
        return edge

    driver, target = (one(influence, prop) for prop in (L.driverEntity, L.targetEntity))
    record_label = node_label(influence) + "\n" + identifier(driver) + "\n→ " + identifier(target)
    add_node("record", influence, "record", (95, 61), (26, 50), record_label)
    for key, term, x, prop in (("driver", driver, 30, L.driverEntity), ("target", target, 160, L.targetEntity)):
        add_node(key, term, "entities", (x, 76), (56, 8))
        left = x < 95
        add_edge(influence, prop, term, ((82 if left else 108, 76), (58 if left else 132, 76)),
                 (70 if left else 120, 78.2), 23)

    # Two routes to the shared unit. Rule and confidence nodes stay beside their attribution.
    shared_units = set()
    for key, x, entity in (("driverAttribution", 30, driver), ("wellAttribution", 160, target)):
        attr = ox.NamedNode(candidate[key])
        if (named(PROV.wasDerivedFrom), attr) not in triples:
            raise ValueError("CQ8 attribution is not evidence on the chosen influence")
        add_node(key, attr, "evidence", (x, 104), (56, 8))
        left = x < 95
        add_edge(influence, PROV.wasDerivedFrom, attr,
                 ((87 if left else 103, 86), (70 if left else 120, 92), (58 if left else 132, 100)),
                 (70 if left else 120, 93.8), 24)
        unit_pairs = [(prop, obj) for prop, obj in pairs(attr) if prop in (named(L.candidateUnit), named(L.candidateGroup))]
        if len(unit_pairs) != 1:
            raise ValueError("The fixed figure needs one unit or group on each attribution")
        prop, unit = unit_pairs[0]
        shared_units.add(unit)
        add_edge(attr, prop, unit, ((58 if left else 132, 104), (77 if left else 113, 104)),
                 (67.5 if left else 122.5, 106), 18)
        outer, child_x = (2, 44) if left else (188, 146)
        for prop, y, group in ((L.confidence, 95, "values"), (L.derivationRule, 85, "evidence")):
            obj = one(attr, prop)
            add_node(key + local(str(prop)), obj, group, (child_x, y), (28, 7))
            add_edge(attr, prop, obj,
                     ((outer, 104), (outer, y), (30 if left else 160, y)),
                     (16 if left else 174, y + 2), 27)
        if one(attr, L.attributedEntity) != entity:
            raise ValueError("Attribution entity differs from CQ8's driver or target")
        add_edge(attr, L.attributedEntity, entity,
                 ((outer, 104), (outer, 80.8), (x, 80.8), (x, 80)),
                 (16 if left else 174, 81.5), 27)
    if len(shared_units) != 1:
        raise ValueError("The two pumping attributions do not share one unit or group")
    add_node("unit", next(iter(shared_units)), "entities", (95, 104), (36, 8))

    # The predicates only set positions. Every object is read from the chosen record.
    columns = ((30, (L.mechanism, L.responseSign, L.driverVariable, L.driverGroup, L.resolution, L.horizontalDistanceM)),
               (160, (L.confidence, L.constraintEligibility, L.evidenceKind, RDF.type, L.derivationRule, PROV.wasGeneratedBy)))
    for x, predicates in columns:
        for index, prop in enumerate(predicates):
            values = objects(influence, prop)
            if not values and prop == PROV.wasGeneratedBy:
                continue
            if len(values) != 1:
                raise ValueError(f"The fixed figure needs one {prop}, found {len(values)}")
            obj, y = values[0], 68 - 5.8 * index
            label = f"{float(obj.value) / 1000:.1f} km" if prop == L.horizontalDistanceM else None
            group = "evidence" if prop in (L.derivationRule, PROV.wasGeneratedBy) else "values"
            add_node(str(prop), obj, group, (x, y), (56, 5.5), label)
            left = x < 95
            add_edge(influence, prop, obj, ((82 if left else 108, y), (58 if left else 132, y)),
                     (70 if left else 120, y), 23)

    policies = sorted(objects(influence, L.selectedUnder), key=str)
    if len(policies) > 3:
        raise ValueError("The fixed policy row has room for at most three policies")
    for x, policy in zip((70, 95, 120), policies):
        add_node(str(policy), policy, "values", (x, 31), (22, 8))
        add_edge(influence, L.selectedUnder, policy, ((95, 36), (x, 35)), (95, 40), 25)

    for prop, x in ((L.conditions, 47), (L.eligibilityReason, 143)):
        literal = one(influence, prop)
        add_node(str(prop), literal, "values", (x, 15), (90, 22))
        left = x < 95
        lane = 58.5 if left else 131.5
        add_edge(influence, prop, literal,
                 ((82 if left else 108, 36), (lane, 36), (lane, 28), (x, 28), (x, 26)),
                 (x, 29.5), 27)

    drawn = {(edge.predicate, edge.object) for edge in edges if edge.subject == influence}
    if drawn != set(triples):
        raise ValueError(f"Unplaced or extra Influence triples: missing={set(triples) - drawn}; extra={drawn - set(triples)}")
    return {"influence": influence, "candidate": candidate, "triples": triples, "nodes": nodes,
            "edges": edges, "missing_labels": sorted(missing, key=str)}


def wrap_label(text, width_mm, renderer, dpi, size=7):
    """Wrap by measured glyph widths, retaining every word and every literal value."""
    font = FontProperties(family="DejaVu Sans", size=size)
    limit = width_mm / 25.4 * dpi
    lines = []
    for paragraph in text.split("\n"):
        current = ""
        for word in paragraph.split():
            candidate = (current + " " + word).strip()
            if current and renderer.get_text_width_height_descent(candidate, font, False)[0] > limit:
                lines.append(current)
                current = word
            else:
                current = candidate
        lines.append(current)
    return "\n".join(lines)


def draw_influence(out=OUT, store=None, labels=None):
    """Write a vector PDF and a PNG, and return the actual nodes and edges for checking."""
    store = kg_store() if store is None else store
    labels = ontology_labels() if labels is None else labels
    candidate = select_record(store)
    result = diagram(store, labels, candidate)
    style = {"font.family": "DejaVu Sans", "font.size": 7, "pdf.fonttype": 42,
             "text.usetex": False, "savefig.bbox": None}
    with matplotlib.rc_context(style):
        fig = plt.figure(figsize=(WIDTH_MM / 25.4, HEIGHT_MM / 25.4), dpi=150, facecolor="white")
        ax = fig.add_axes((0, 0, 1, 1), xlim=(0, WIDTH_MM), ylim=(0, HEIGHT_MM), aspect="equal")
        ax.set_axis_off()
        renderer = fig.canvas.get_renderer()
        for index, edge in enumerate(result["edges"]):
            path = MplPath(edge.points, [MplPath.MOVETO] + [MplPath.LINETO] * (len(edge.points) - 1))
            edge.artist = FancyArrowPatch(path=path, arrowstyle="-|>", mutation_scale=5,
                                          linewidth=0.55, color=LINE, zorder=1)
            edge.artist.set_gid(f"rdf-edge-{index}")
            ax.add_patch(edge.artist)
        for node in result["nodes"].values():
            x, y = node.xy
            width, height = node.size
            node.artist = FancyBboxPatch((x - width / 2, y - height / 2), width, height,
                                         boxstyle="round,pad=0,rounding_size=1", linewidth=0.6,
                                         edgecolor=LINE, facecolor=FILLS[node.group], zorder=2)
            ax.add_patch(node.artist)
            size = 7.8 if node.group == "record" else 7
            text = wrap_label(node.label, width - 2, renderer, fig.dpi, size)
            node.text = ax.text(x, y, text, fontsize=size, color=INK, ha="center", va="center",
                                linespacing=1.05, zorder=3)
        labelled = set()
        for edge in result["edges"]:
            # The three policy arrows share one label; each still has its own arrow and object.
            key = (edge.label, edge.label_xy)
            if key not in labelled:
                edge.text = ax.text(*edge.label_xy, wrap_label(edge.label, edge.label_width, renderer, fig.dpi),
                                    fontsize=7, ha="center", va="center", color=INK, linespacing=1.0,
                                    bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.15}, zorder=4)
                labelled.add(key)
            else:
                edge.text = next(other.text for other in result["edges"]
                                 if other.label == edge.label and other.label_xy == edge.label_xy and other.text is not None)
        legend = [Patch(facecolor=FILLS[key], edgecolor=LINE, linewidth=0.6, label=label)
                  for key, label in (("record", "Record"), ("entities", "Entities"),
                                     ("evidence", "Evidence"), ("values", "Controlled values / literals"))]
        ax.legend(handles=legend, loc="lower center", bbox_to_anchor=(0.5, 0.002), ncol=4,
                  frameon=False, fontsize=7, handlelength=1.3, handleheight=0.9,
                  columnspacing=1.8, borderpad=0, labelspacing=0, borderaxespad=0.1)
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        fig.savefig(out / "influence.pdf", metadata={"Title": "A released LULC-Water pumping Influence",
                    "Subject": result["influence"].value, "CreationDate": None, "ModDate": None})
        fig.savefig(out / "influence.png", dpi=220, metadata={"Software": "Matplotlib"})
        result["figure"] = fig
        plt.close(fig)
    print("Chosen Influence:", result["influence"].value)
    print("Outgoing triples drawn:", len(result["triples"]))
    for predicate in result["missing_labels"]:
        print("No English property label; using local name:", predicate.value)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=OUT, help="output directory for influence.pdf and influence.png")
    args = parser.parse_args(argv)
    draw_influence(args.out)


if __name__ == "__main__":
    main()
