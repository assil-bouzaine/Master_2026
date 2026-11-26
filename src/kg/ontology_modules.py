"""Generate the modular LULC-Water ontology and country profiles from one master source.

Implements v5 plan R2.2 (docs/v5_plan.md): ``ontology/lulcw.ttl`` remains the single authored
source (the master), where every ``lulcw:`` term carries exactly one ``lulcw:definedInModule``
annotation. From that master, this generator writes:
  - seven pan-Mediterranean core modules under ``ontology/modules/``
    (core, hydro, lulc, eo, causal, med-causal, xai);
  - three thin regional/country profiles under ``ontology/profiles/`` (eu, fr, tn);
  - the published modular entry point ``ontology/lulcw-modular.ttl``;
  - ``ontology/catalog-v001.xml`` with entries for every module and profile;
  - ``ontology/modules/assignment.csv`` (term, kind, module, rule).

``owl:imports`` of each module and profile are computed from the terms its triples mention.
The generator fails if any core module mentions a profile term or if the module import graph
has a cycle. Run with ``--check`` to verify that the generated files match the master without
writing anything.

    PFE_DATASET=v5 python -m src.kg.ontology_modules
    PFE_DATASET=v5 python -m src.kg.ontology_modules --check
"""
import argparse
import csv
import io
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

import rdflib
from rdflib import BNode, Literal, URIRef
from rdflib.collection import Collection
from rdflib.namespace import DCTERMS, OWL, PROV, RDF, RDFS, SKOS, XSD

from src.config import ROOT

ONTO = ROOT / "ontology"
MASTER = ONTO / "lulcw.ttl"
CATALOG = ONTO / "catalog-v001.xml"
BASE = "https://w3id.org/lulcw"
L = BASE + "#"
DEFINED_IN_MODULE = URIRef(L + "definedInModule")
CREATED_DATE = "2026-11-26"

SOSA = rdflib.Namespace("http://www.w3.org/ns/sosa/")
TIME = rdflib.Namespace("http://www.w3.org/2006/time#")
GEO = rdflib.Namespace("http://www.opengis.net/ont/geosparql#")
VANN = rdflib.Namespace("http://purl.org/vocab/vann/")

CORE_MODULES = ("core", "hydro", "lulc", "eo", "causal", "med-causal", "xai")
PROFILES = ("profile/eu", "profile/fr", "profile/tn")
ALL_MODULES = CORE_MODULES + PROFILES

MODULE_META = {
    "core": {
        "iri": f"{BASE}/core",
        "rel_path": "modules/lulcw-core.ttl",
        "title_en": "LULC-Water core module",
        "title_fr": "Module noyau LULC-Water",
        "desc_en": (
            "Country-agnostic core vocabulary of the LULC-Water ontology network: provenance "
            "(data releases, source records, derivation rules), qualified assertions, shared "
            "answer-contract and evidence schemes, and generic register-code and measurement properties."
        ),
        "desc_fr": (
            "Vocabulaire noyau indépendant des pays du réseau d'ontologies LULC-Water : provenance "
            "(versions de jeux de données, enregistrements sources, règles de dérivation), assertions "
            "qualifiées, schémas partagés du contrat de réponse et des preuves, et propriétés génériques "
            "de code de registre et de mesure."
        ),
    },
    "hydro": {
        "iri": f"{BASE}/hydro",
        "rel_path": "modules/lulcw-hydro.ttl",
        "title_en": "LULC-Water hydrogeology and surface-water module",
        "title_fr": "Module hydrogéologie et eaux de surface LULC-Water",
        "desc_en": (
            "Country-agnostic hydrogeological and surface-water vocabulary: piezometers, monitoring "
            "stations, observation series, hydrogeological units and stacks, groundwater abstraction "
            "and annual accounting, recharge-related outcrop geometry, watercourses, reaches, gauges, "
            "canals, and cover/confinement assessments."
        ),
        "desc_fr": (
            "Vocabulaire hydrogéologique et des eaux de surface indépendant des pays : piézomètres, "
            "stations de mesure, séries d'observations, entités et piles hydrogéologiques, prélèvements "
            "et bilans annuels, géométrie des affleurements, cours d'eau, tronçons, stations hydrométriques, "
            "canaux et évaluations de couverture et de captivité."
        ),
    },
    "lulc": {
        "iri": f"{BASE}/lulc",
        "rel_path": "modules/lulcw-lulc.ttl",
        "title_en": "LULC-Water land-use and crops module",
        "title_fr": "Module occupation du sol et cultures LULC-Water",
        "desc_en": (
            "Country-agnostic land-use and agricultural water-demand vocabulary: crop codes, harmonised "
            "crop classes with FAO-56 parameters, crop demand zones, dated clipped crop areas, potential "
            "irrigation demand estimates, and irrigation demand categories."
        ),
        "desc_fr": (
            "Vocabulaire d'occupation du sol et de demande agricole en eau indépendant des pays : codes "
            "culture, classes de cultures harmonisées avec paramètres FAO-56, zones de demande, surfaces "
            "découpées datées, estimations de demande potentielle d'irrigation et catégories de demande."
        ),
    },
    "eo": {
        "iri": f"{BASE}/eo",
        "rel_path": "modules/lulcw-eo.ttl",
        "title_en": "LULC-Water Earth-observation module",
        "title_fr": "Module observation de la Terre LULC-Water",
        "desc_en": (
            "Country-agnostic Earth-observation module of the LULC-Water network. Starts empty at "
            "0.10.0; satellite spectral-index observations and probable-irrigation terms (CQ15) will "
            "be added in a subsequent step."
        ),
        "desc_fr": (
            "Module d'observation de la Terre indépendant des pays du réseau LULC-Water. Initialement "
            "vide en version 0.10.0 ; les observations d'indices spectraux satellitaires et les termes "
            "d'irrigation probable (CQ15) seront ajoutés dans une étape ultérieure."
        ),
    },
    "causal": {
        "iri": f"{BASE}/causal",
        "rel_path": "modules/lulcw-causal.ttl",
        "title_en": "LULC-Water causal mechanisms and constraints module",
        "title_fr": "Module mécanismes causaux et contraintes LULC-Water",
        "desc_en": (
            "Country-agnostic causal-knowledge and model-constraint vocabulary: qualified driver-to-head "
            "influences, physical mechanisms, response signs, driver groups, constraint eligibility, "
            "export policies, constraint decisions, and observable driver properties."
        ),
        "desc_fr": (
            "Vocabulaire des connaissances causales et contraintes de modèle indépendant des pays : "
            "influences qualifiées, mécanismes physiques, signes de réponse, groupes de forçages, "
            "éligibilité aux contraintes, politiques d'export, décisions de contrainte et propriétés "
            "observables motrices."
        ),
    },
    "med-causal": {
        "iri": f"{BASE}/med-causal",
        "rel_path": "modules/lulcw-med-causal.ttl",
        "title_en": "LULC-Water Mediterranean literature causal-evidence module",
        "title_fr": "Module preuves causales de la littérature méditerranéenne LULC-Water",
        "desc_en": (
            "Country-agnostic documentary and literature-derived causal-evidence vocabulary: source "
            "documents, verbatim passages, exchange statements, exchange directions, hedging, evidence "
            "methods, and unit mappings, ready to hold extracted Mediterranean causal axioms (R2.1)."
        ),
        "desc_fr": (
            "Vocabulaire documentaire et des preuves causales issues de la littérature indépendant des "
            "pays : documents sources, passages cités, énoncés d'échange, sens d'échange, modalités, "
            "méthodes de preuve et correspondances d'entités, prêt à accueillir les axiomes causaux "
            "méditerranéens extraits (R2.1)."
        ),
    },
    "xai": {
        "iri": f"{BASE}/xai",
        "rel_path": "modules/lulcw-xai.ttl",
        "title_en": "LULC-Water explainable AI module",
        "title_fr": "Module IA explicable LULC-Water",
        "desc_en": (
            "Country-agnostic explainability module of the LULC-Water network. Starts empty at 0.10.0; "
            "model runs, driver contributions, explanation statements, and scenario terms (CQ10, CQ16) "
            "will be added in a subsequent step."
        ),
        "desc_fr": (
            "Module d'explicabilité indépendant des pays du réseau LULC-Water. Initialement vide en "
            "version 0.10.0 ; les exécutions de modèles, contributions de forçages, énoncés d'explication "
            "et termes de scénarios (CQ10, CQ16) seront ajoutés dans une étape ultérieure."
        ),
    },
    "profile/eu": {
        "iri": f"{BASE}/profile/eu",
        "rel_path": "profiles/lulcw-eu-profile.ttl",
        "title_en": "LULC-Water European Union profile",
        "title_fr": "Profil Union européenne LULC-Water",
        "desc_en": (
            "Optional European Union regional profile for the LULC-Water ontology network, declaring "
            "EU Water Framework Directive identifiers (such as lulcw:wfdCode) outside the pan-Mediterranean core."
        ),
        "desc_fr": (
            "Profil régional optionnel Union européenne du réseau d'ontologies LULC-Water, déclarant "
            "les identifiants de la directive-cadre sur l'eau (tels que lulcw:wfdCode) hors du noyau "
            "pan-méditerranéen."
        ),
    },
    "profile/fr": {
        "iri": f"{BASE}/profile/fr",
        "rel_path": "profiles/lulcw-fr-profile.ttl",
        "title_en": "LULC-Water France profile",
        "title_fr": "Profil France LULC-Water",
        "desc_en": (
            "Thin French country adapter profile for the LULC-Water ontology network, declaring French "
            "national agency register codes and reference dataset attributes (BD LISA, BNPE, BSS, "
            "BD Carthage, BD TOPO, RPG, SAFRAN) outside the pan-Mediterranean core."
        ),
        "desc_fr": (
            "Profil adaptateur France du réseau d'ontologies LULC-Water, déclarant les codes de registres "
            "nationaux et attributs de jeux de données français (BD LISA, BNPE, BSS, BD Carthage, BD TOPO, "
            "RPG, SAFRAN) hors du noyau pan-méditerranéen."
        ),
    },
    "profile/tn": {
        "iri": f"{BASE}/profile/tn",
        "rel_path": "profiles/lulcw-tn-profile.ttl",
        "title_en": "LULC-Water Tunisia profile",
        "title_fr": "Profil Tunisie LULC-Water",
        "desc_en": (
            "Thin Tunisian country adapter profile for the LULC-Water ontology network. Starts empty at "
            "0.10.0; Tunisian register codes (e.g. DGRE, CRDA, SONEDE, MSE-UMA) will be added when the "
            "Manouba transfer data are instantiated."
        ),
        "desc_fr": (
            "Profil adaptateur Tunisie du réseau d'ontologies LULC-Water. Initialement vide en version "
            "0.10.0 ; les codes de registres tunisiens (ex. DGRE, CRDA, SONEDE, MSE-UMA) seront ajoutés "
            "lors de l'instanciation des données de transfert de la Manouba."
        ),
    },
}

MODULAR_META = {
    "iri": f"{BASE}/modular",
    "rel_path": "lulcw-modular.ttl",
    "title_en": "LULC-Water modular meta-ontology",
    "title_fr": "Méta-ontologie modulaire LULC-Water",
    "desc_en": (
        "Published modular entry point of the LULC-Water ontology network: imports the seven "
        "pan-Mediterranean core modules, the EU and France profiles, and the alignment modules "
        "(GWML2/HyFO, SWEET, HY_Features, INSPIRE)."
    ),
    "desc_fr": (
        "Point d'entrée modulaire publié du réseau d'ontologies LULC-Water : importe les sept "
        "modules noyaux pan-méditerranéens, les profils UE et France et les modules d'alignement "
        "(GWML2/HyFO, SWEET, HY_Features, INSPIRE)."
    ),
}

ALIGNMENT_IMPORTS = (
    f"{BASE}/alignments/gwml2-hyfo",
    f"{BASE}/alignments/sweet",
    f"{BASE}/alignments/hyf",
    f"{BASE}/alignments/inspire",
)

EXTERNAL_IMPORTS = (
    (str(SOSA), f"{BASE}/imports/sosa"),
    (str(PROV), f"{BASE}/imports/prov"),
    (str(TIME), f"{BASE}/imports/time"),
    (str(SKOS), f"{BASE}/imports/skos"),
    (str(GEO), f"{BASE}/imports/geo"),
)

PREFIXES = (
    ("lulcw", L),
    ("owl", str(OWL)),
    ("rdf", str(RDF)),
    ("rdfs", str(RDFS)),
    ("xsd", str(XSD)),
    ("skos", str(SKOS)),
    ("sosa", str(SOSA)),
    ("prov", str(PROV)),
    ("time", str(TIME)),
    ("geo", str(GEO)),
    ("dcterms", str(DCTERMS)),
)

IRI_TO_MODULE = {meta["iri"]: name for name, meta in MODULE_META.items()}

# Provenance sets matching the assignment rules in T78 (for assignment.csv's rule column).
RULE1_TERMS = frozenset({
    "bdCarthageCode", "bdlisaCode", "bdlisaMediumCode", "bdlisaNatureCode",
    "bdlisaThemeCode", "bdtopoId", "bnpeCode", "bssCode", "bssId",
    "polygonCode", "rpgEdition", "rpgGroupCode", "safranGridXHm", "safranGridYHm",
    "wfdCode",
})
RULE2_TERMS = frozenset({
    "AnswerStatus", "Conflicting", "NotApplicable", "Partial",
    "Supported", "UnknownAnswer", "ModelResult", "SupersededStatus",
    "ImputedRecord", "ReconstructedRecord", "accountedFor", "accountingYear",
    "allocatedTo", "allocatedVolumeM3", "allocatesRecord", "allocationWeight",
    "eligibleDeclaredVolumeM3", "excludedVolumeM3", "facilityCount",
    "reportingExtent", "unresolvedVolumeM3",
})

KIND_ORDER = (
    (OWL.Class, "class"),
    (OWL.ObjectProperty, "object property"),
    (OWL.DatatypeProperty, "datatype property"),
    (OWL.AnnotationProperty, "annotation property"),
    (SKOS.ConceptScheme, "concept scheme"),
)

PRED_ORDER = [
    RDF.type,
    RDFS.subClassOf,
    RDFS.subPropertyOf,
    RDFS.domain,
    RDFS.range,
    SKOS.inScheme,
    SKOS.topConceptOf,
    SKOS.prefLabel,
    RDFS.label,
    SKOS.definition,
    RDFS.comment,
    DEFINED_IN_MODULE,
]
PRED_RANK = {p: i for i, p in enumerate(PRED_ORDER)}


def term_kind(graph, subject):
    """Human-readable OWL/SKOS kind of a declared lulcw term."""
    types = set(graph.objects(subject, RDF.type))
    for rdf_type, name in KIND_ORDER:
        if rdf_type in types:
            return name
    return "individual"


def classify_rule(graph, local_name, module):
    """Return the rule number (1-5) that placed `local_name` in `module`."""
    if local_name in RULE1_TERMS:
        return 1
    if local_name in RULE2_TERMS:
        return 2
    u = URIRef(L + local_name)
    types = set(graph.objects(u, RDF.type))
    if SKOS.ConceptScheme in types or (u, SKOS.inScheme, None) in graph:
        return 3
    if OWL.Class in types or SOSA.ObservableProperty in types or SOSA.Procedure in types:
        return 4
    return 5


def load_master(path=MASTER):
    """Parse the master ontology and validate lulcw:definedInModule tags."""
    g = rdflib.Graph().parse(path)
    master_iri = URIRef(BASE)
    version = str(g.value(master_iri, OWL.versionInfo))
    creator = str(g.value(master_iri, DCTERMS.creator))
    license_iri = g.value(master_iri, DCTERMS.license)
    assert version and creator and isinstance(license_iri, URIRef), "master ontology metadata missing"

    terms = sorted(
        str(s)[len(L):]
        for s in set(g.subjects(RDF.type, None))
        if isinstance(s, URIRef) and str(s).startswith(L)
    )
    term_to_mod = {}
    errors = []
    for t in terms:
        vals = list(g.objects(URIRef(L + t), DEFINED_IN_MODULE))
        if len(vals) != 1:
            errors.append(f"{t}: expected 1 lulcw:definedInModule, found {len(vals)}")
            continue
        mod_iri = str(vals[0])
        if mod_iri not in IRI_TO_MODULE:
            errors.append(f"{t}: unknown module IRI {mod_iri}")
            continue
        term_to_mod[t] = IRI_TO_MODULE[mod_iri]
    if errors:
        raise ValueError("Invalid lulcw:definedInModule tags in master:\n  " + "\n  ".join(errors))
    return g, version, creator, license_iri, term_to_mod


def _collect_bnode_subgraph(graph, root):
    """All triples reachable from blank node `root`."""
    triples, todo, seen = set(), [root], set()
    while todo:
        node = todo.pop()
        if node in seen:
            continue
        seen.add(node)
        for p, o in graph.predicate_objects(node):
            triples.add((node, p, o))
            if isinstance(o, BNode):
                todo.append(o)
    return triples


def split_triples(graph, term_to_mod):
    """Partition every term triple and root blank-node axiom of the master into modules."""
    mod_triples = {m: set() for m in ALL_MODULES}
    mod_root_bnodes = {m: [] for m in ALL_MODULES}

    for t, mod in term_to_mod.items():
        s = URIRef(L + t)
        for p, o in graph.predicate_objects(s):
            mod_triples[mod].add((s, p, o))
            if isinstance(o, BNode):
                mod_triples[mod] |= _collect_bnode_subgraph(graph, o)

    # Root blank-node axioms (e.g. owl:AllDisjointClasses) follow their referenced terms' module.
    all_bnodes = {s for s in graph.subjects() if isinstance(s, BNode)}
    root_bnodes = [b for b in all_bnodes if not any(graph.triples((None, None, b)))]
    for b in root_bnodes:
        sub = _collect_bnode_subgraph(graph, b)
        ref_mods = set()
        for _, p, o in sub:
            for x in (p, o):
                if isinstance(x, URIRef) and str(x).startswith(L):
                    ref_mods.add(term_to_mod[str(x)[len(L):]])
        if len(ref_mods) != 1:
            raise ValueError(f"Root blank-node axiom spans modules {sorted(ref_mods)}; cannot place unambiguously")
        target_mod = next(iter(ref_mods))
        mod_triples[target_mod] |= sub
        mod_root_bnodes[target_mod].append(b)

    return mod_triples, mod_root_bnodes


def compute_imports(mod_triples, term_to_mod):
    """Compute lulcw and external owl:imports for every module; fail on cycles or core->profile leaks."""
    lulcw_imports = {m: set() for m in ALL_MODULES}
    ext_imports = {m: set() for m in ALL_MODULES}

    for mod, triples in mod_triples.items():
        for s, p, o in triples:
            for node in (s, p, o):
                if not isinstance(node, URIRef):
                    continue
                u = str(node)
                if u.startswith(L):
                    target = term_to_mod[u[len(L):]]
                    if target != mod:
                        if mod in CORE_MODULES and target in PROFILES:
                            raise ValueError(
                                f"Core module '{mod}' mentions profile term 'lulcw:{u[len(L):]}' "
                                f"(defined in '{target}')"
                            )
                        lulcw_imports[mod].add(target)
                else:
                    for ns, imp_iri in EXTERNAL_IMPORTS:
                        if u.startswith(ns):
                            ext_imports[mod].add(imp_iri)

    # Check the module import graph for cycles (3-color DFS).
    color = {m: 0 for m in ALL_MODULES}
    path = []

    def dfs(u):
        color[u] = 1
        path.append(u)
        for v in sorted(lulcw_imports[u]):
            if color[v] == 1:
                cycle = " -> ".join(path[path.index(v):] + [v])
                raise ValueError(f"Import cycle in lulcw modules: {cycle}")
            if color[v] == 0:
                dfs(v)
        path.pop()
        color[u] = 2

    for m in ALL_MODULES:
        if color[m] == 0:
            dfs(m)

    return {m: sorted(lulcw_imports[m]) for m in ALL_MODULES}, {m: sorted(ext_imports[m]) for m in ALL_MODULES}


def _fmt_term(node, graph=None):
    """Format an RDF node deterministically in Turtle using PREFIXES."""
    if isinstance(node, URIRef):
        u = str(node)
        for pref, ns in PREFIXES:
            if u.startswith(ns):
                local = u[len(ns):]
                if local and all(c.isalnum() or c in "_-" for c in local) and not local[0].isdigit():
                    return f"{pref}:{local}"
        return f"<{u}>"
    if isinstance(node, Literal):
        escaped = (
            str(node)
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
        )
        if node.language:
            return f'"{escaped}"@{node.language}'
        if node.datatype and node.datatype != XSD.string:
            return f'"{escaped}"^^{_fmt_term(node.datatype)}'
        return f'"{escaped}"'
    if isinstance(node, BNode) and graph is not None:
        if (node, RDF.first, None) in graph:
            items = [_fmt_term(x, graph) for x in Collection(graph, node)]
            return "( " + " ".join(items) + " )"
        return _fmt_bnode_block(graph, node)
    raise TypeError(f"Unsupported RDF term: {node!r}")


def _pred_sort_key(pred):
    return (PRED_RANK.get(pred, len(PRED_ORDER)), str(pred))


def _obj_sort_key(obj, graph=None):
    if isinstance(obj, Literal):
        return (1, obj.language or "", str(obj.datatype or ""), str(obj))
    if isinstance(obj, URIRef):
        return (0, "", "", str(obj))
    return (2, "", "", _fmt_term(obj, graph))


def _fmt_bnode_block(graph, bnode):
    """Format a blank node (such as owl:AllDisjointClasses) as deterministic Turtle."""
    by_pred = defaultdict(list)
    for p, o in graph.predicate_objects(bnode):
        by_pred[p].append(o)
    parts = []
    for p in sorted(by_pred, key=_pred_sort_key):
        p_txt = "a" if p == RDF.type else _fmt_term(p)
        objs = sorted(by_pred[p], key=lambda o: _obj_sort_key(o, graph))
        o_txt = " , ".join(_fmt_term(o, graph) for o in objs)
        parts.append(f"{p_txt} {o_txt}")
    return "[] " + " ;\n    ".join(parts) + " ."


def _fmt_subject_block(graph, subject):
    """Format all triples of one URIRef subject deterministically in Turtle."""
    by_pred = defaultdict(list)
    for p, o in graph.predicate_objects(subject):
        by_pred[p].append(o)
    lines = []
    preds = sorted(by_pred, key=_pred_sort_key)
    for idx, p in enumerate(preds):
        p_txt = "a" if p == RDF.type else _fmt_term(p)
        objs = sorted(by_pred[p], key=lambda o: _obj_sort_key(o, graph))
        o_txt = " , ".join(_fmt_term(o, graph) for o in objs)
        end = " ." if idx == len(preds) - 1 else " ;"
        if idx == 0:
            lines.append(f"{_fmt_term(subject)} {p_txt} {o_txt}{end}")
        else:
            lines.append(f"    {p_txt} {o_txt}{end}")
    return "\n".join(lines)


def _used_prefixes(text_chunks, import_iris):
    """Keep the prefix header minimal and deterministic."""
    joined = "\n".join(text_chunks)
    out = []
    for pref, ns in PREFIXES:
        if pref in ("owl", "xsd", "dcterms") or f"{pref}:" in joined:
            out.append((pref, ns))
    return out


def render_module_ttl(mod_name, master_graph, triples, root_bnodes, lulcw_imps, ext_imps,
                      version, creator, license_iri):
    """Render one module or profile Turtle file deterministically."""
    meta = MODULE_META[mod_name]
    iri = meta["iri"]
    sub_g = rdflib.Graph()
    for t in triples:
        sub_g.add(t)

    subjects = sorted(
        {s for s in sub_g.subjects() if isinstance(s, URIRef) and str(s).startswith(L)},
        key=lambda u: str(u)[len(L):],
    )
    body_blocks = [_fmt_subject_block(sub_g, s) for s in subjects]
    bnode_blocks = sorted(_fmt_bnode_block(sub_g, b) for b in root_bnodes)
    all_blocks = body_blocks + bnode_blocks

    all_imports = [MODULE_META[m]["iri"] for m in lulcw_imps] + list(ext_imps)

    header_lines = [
        f"<{iri}> a owl:Ontology ;",
        f"    owl:versionIRI <{iri}/{version}> ;",
        f'    owl:versionInfo "{version}" ;',
        f'    dcterms:title {_fmt_term(Literal(meta["title_en"], lang="en"))} , '
        f'{_fmt_term(Literal(meta["title_fr"], lang="fr"))} ;',
        f'    dcterms:description {_fmt_term(Literal(meta["desc_en"], lang="en"))} ,',
        f'        {_fmt_term(Literal(meta["desc_fr"], lang="fr"))} ;',
        f'    dcterms:creator {_fmt_term(Literal(creator))} ;',
        f"    dcterms:license <{license_iri}> ;",
    ]
    if all_imports:
        header_lines.append(f'    dcterms:created "{CREATED_DATE}"^^xsd:date ;')
        imp_txt = " , ".join(f"<{u}>" for u in all_imports)
        header_lines.append(f"    owl:imports {imp_txt} .")
    else:
        header_lines.append(f'    dcterms:created "{CREATED_DATE}"^^xsd:date .')

    header_block = "\n".join(header_lines)
    annot_block = "\n".join([
        "dcterms:title a owl:AnnotationProperty .",
        "dcterms:description a owl:AnnotationProperty .",
        "dcterms:creator a owl:AnnotationProperty .",
        "dcterms:license a owl:AnnotationProperty .",
        "dcterms:created a owl:AnnotationProperty .",
    ])

    used = _used_prefixes([header_block, annot_block, *all_blocks], all_imports)
    prefix_lines = [f"@prefix {p + ':':8s} <{ns}> ." for p, ns in used]
    banner = (
        f"# Generated from ontology/lulcw.ttl (version {version}) by src.kg.ontology_modules.\n"
        "# Do not edit by hand: edit ontology/lulcw.ttl and re-run the generator."
    )
    sections = ["\n".join(prefix_lines), banner, header_block, annot_block]
    if all_blocks:
        sections.extend(all_blocks)
    return "\n\n".join(sections) + "\n"


def render_modular_ttl(version, creator, license_iri):
    """Render ontology/lulcw-modular.ttl importing the 7 modules, EU/FR profiles and alignments."""
    meta = MODULAR_META
    iri = meta["iri"]
    imports = (
        [MODULE_META[m]["iri"] for m in CORE_MODULES]
        + [MODULE_META["profile/eu"]["iri"], MODULE_META["profile/fr"]["iri"]]
        + list(ALIGNMENT_IMPORTS)
    )
    imp_lines = " ,\n        ".join(f"<{u}>" for u in imports)
    return (
        "@prefix owl:     <http://www.w3.org/2002/07/owl#> .\n"
        "@prefix xsd:     <http://www.w3.org/2001/XMLSchema#> .\n"
        "@prefix dcterms: <http://purl.org/dc/terms/> .\n\n"
        f"# Generated from ontology/lulcw.ttl (version {version}) by src.kg.ontology_modules.\n"
        "# Published modular entry point of the LULC-Water network: the seven pan-Mediterranean\n"
        "# core modules, the EU and France profiles, and the alignment modules.\n\n"
        f"<{iri}> a owl:Ontology ;\n"
        f"    owl:versionIRI <{iri}/{version}> ;\n"
        f'    owl:versionInfo "{version}" ;\n'
        f'    dcterms:title {_fmt_term(Literal(meta["title_en"], lang="en"))} , '
        f'{_fmt_term(Literal(meta["title_fr"], lang="fr"))} ;\n'
        f'    dcterms:description {_fmt_term(Literal(meta["desc_en"], lang="en"))} ,\n'
        f'        {_fmt_term(Literal(meta["desc_fr"], lang="fr"))} ;\n'
        f'    dcterms:creator {_fmt_term(Literal(creator))} ;\n'
        f"    dcterms:license <{license_iri}> ;\n"
        f'    dcterms:created "{CREATED_DATE}"^^xsd:date ;\n'
        f"    owl:imports {imp_lines} .\n\n"
        "dcterms:title a owl:AnnotationProperty .\n"
        "dcterms:description a owl:AnnotationProperty .\n"
        "dcterms:creator a owl:AnnotationProperty .\n"
        "dcterms:license a owl:AnnotationProperty .\n"
        "dcterms:created a owl:AnnotationProperty .\n"
    )


def render_catalog_xml(catalog_path=CATALOG):
    """Preserve existing catalog entries and ensure entries for modular, modules and profiles."""
    generated_entries = [(MODULAR_META["iri"], MODULAR_META["rel_path"])] + [
        (MODULE_META[m]["iri"], MODULE_META[m]["rel_path"]) for m in ALL_MODULES
    ]
    generated_iris = {iri for iri, _ in generated_entries}

    existing = []
    if catalog_path.exists():
        root = ET.parse(catalog_path).getroot()
        for u in root.iter():
            if u.tag.endswith("uri"):
                name, uri = u.get("name"), u.get("uri")
                if name not in generated_iris:
                    existing.append((name, uri))

    # Place lulcw/modular right after lulcw/meta, then modules/profiles, then alignments & imports.
    ordered = []
    inserted = False
    for name, uri in existing:
        ordered.append((name, uri))
        if name == f"{BASE}/meta":
            ordered.extend(generated_entries)
            inserted = True
    if not inserted:
        ordered.extend(generated_entries)

    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
        "<!-- Import IRIs of the LULC-Water network -> local files (read by Protégé, ROBOT and",
        "     tests/test_ontology.py). The w3id.org IRIs do not resolve on the web yet. -->",
        '<catalog prefer="public" xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">',
    ]
    for name, uri in ordered:
        lines.append(f'    <uri name="{name}" uri="{uri}"/>')
    lines.append("</catalog>")
    return "\n".join(lines) + "\n"


def render_assignment_csv(graph, term_to_mod):
    """Render ontology/modules/assignment.csv (term, kind, module, rule)."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["term", "kind", "module", "rule"])
    for term in sorted(term_to_mod):
        mod = term_to_mod[term]
        kind = term_kind(graph, URIRef(L + term))
        rule = classify_rule(graph, term, mod)
        w.writerow([term, kind, mod, rule])
    return buf.getvalue()


def build_outputs(master_path=MASTER, catalog_path=CATALOG):
    """Compute every generated file from `master_path` in memory (no disk writes)."""
    graph, version, creator, license_iri, term_to_mod = load_master(master_path)
    mod_triples, mod_root_bnodes = split_triples(graph, term_to_mod)
    lulcw_imps, ext_imps = compute_imports(mod_triples, term_to_mod)

    files = {}
    for mod in ALL_MODULES:
        out_path = ONTO / MODULE_META[mod]["rel_path"]
        files[out_path] = render_module_ttl(
            mod, graph, mod_triples[mod], mod_root_bnodes[mod],
            lulcw_imps[mod], ext_imps[mod], version, creator, license_iri,
        )
    files[ONTO / MODULAR_META["rel_path"]] = render_modular_ttl(version, creator, license_iri)
    files[catalog_path] = render_catalog_xml(catalog_path)
    files[ONTO / "modules" / "assignment.csv"] = render_assignment_csv(graph, term_to_mod)

    counts = {m: sum(1 for v in term_to_mod.values() if v == m) for m in ALL_MODULES}
    return files, {
        "version": version,
        "total": len(term_to_mod),
        "counts": counts,
        "core_total": sum(counts[m] for m in CORE_MODULES),
        "profile_total": sum(counts[m] for m in PROFILES),
        "lulcw_imports": lulcw_imps,
        "ext_imports": ext_imps,
    }


def check_outputs(master_path=MASTER, catalog_path=CATALOG):
    """Return list of generated paths that are missing or differ from disk."""
    files, summary = build_outputs(master_path, catalog_path)
    stale = []
    for path, expected in sorted(files.items()):
        if not path.exists() or path.read_text(encoding="utf-8") != expected:
            stale.append(path)
    return stale, summary


def write_outputs(master_path=MASTER, catalog_path=CATALOG):
    """Write every generated file to disk."""
    files, summary = build_outputs(master_path, catalog_path)
    for path, content in sorted(files.items()):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return sorted(files), summary


def print_summary(summary):
    total = summary["total"]
    core_total = summary["core_total"]
    print(f"lulcw {summary['version']}: {total} terms across {len(ALL_MODULES)} modules/profiles")
    print(f"{'module':14s} {'terms':>6s}  {'share':>7s}  lulcw imports")
    for m in ALL_MODULES:
        n = summary["counts"][m]
        imps = ", ".join(summary["lulcw_imports"][m]) or "—"
        print(f"{m:14s} {n:6d}  {100.0 * n / total:6.2f}%  {imps}")
    print(f"Pan-Mediterranean core (7 modules): {core_total}/{total} ({100.0 * core_total / total:.2f}%)")
    print(f"Regional/country profiles (EU/FR/TN): {summary['profile_total']}/{total} "
          f"({100.0 * summary['profile_total'] / total:.2f}%)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="exit non-zero if any generated file differs from the master")
    args = parser.parse_args()
    if args.check:
        stale, summary = check_outputs()
        if stale:
            print("Generated ontology files out of sync with ontology/lulcw.ttl:", file=sys.stderr)
            for p in stale:
                print(f"  {p.relative_to(ROOT)}", file=sys.stderr)
            raise SystemExit(1)
        print_summary(summary)
        print("ontology_modules --check: all generated files match the master")
        return
    written, summary = write_outputs()
    print_summary(summary)
    print(f"Wrote {len(written)} files:")
    for p in written:
        print(f"  {p.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
