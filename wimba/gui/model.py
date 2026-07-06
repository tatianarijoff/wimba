"""GUI view-model: a loose, editable mirror of a WIMBA project.

The core `wimba` objects are built for computation (a provider per element). The
GUI needs something editable and uniform across sources, so it keeps its own
light model and converts a loaded `Project` into it. Phase 3 will translate this
back into providers when calculating.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# quantity id -> (label, units)
QUANTITIES = [
    ("zlong",  "Longitudinal Impedance", "\u03a9"),
    ("zxdip",  "Dipolar Impedance X",    "\u03a9/m"),
    ("zydip",  "Dipolar Impedance Y",    "\u03a9/m"),
    ("zxquad", "Quadrupolar Impedance X","\u03a9/m"),
    ("zyquad", "Quadrupolar Impedance Y","\u03a9/m"),
    ("wake",   "Wakefield",              "V/pC"),
]
QLABEL = {q: lab for q, lab, _ in QUANTITIES}
QUNITS = {q: u for q, _, u in QUANTITIES}
METHODS = [
    "pytlwall", "pytlwall (weighted)",
    "IW2D", "IW2D (weighted)",
    "precalculated", "precalculated (weighted)",
    "resonator", "resonator (weighted)",
]


def method_base(method: str) -> str:
    """'pytlwall (weighted)' -> 'pytlwall'."""
    return method.replace("(weighted)", "").strip()


def method_weighted(method: str) -> bool:
    return "(weighted)" in (method or "")


def method_label(base: str, weighted: bool = False) -> str:
    return f"{base} (weighted)" if weighted else base


def method_needs_file(method: str) -> bool:
    return method_base(method).lower() == "precalculated"


@dataclass
class GModel:
    q: str
    enabled: bool = False
    method: str = "resonator"
    file: str = ""
    origin: str = ""
    status: str = "ready"
    params: dict = field(default_factory=dict)


@dataclass
class GElement:
    name: str
    category: str = "element"
    geometry: dict = field(default_factory=dict)
    optics: dict = field(default_factory=dict)     # s, l, bx, by, pre
    layers: list = field(default_factory=list)
    models: list = field(default_factory=list)     # list[GModel]


@dataclass
class GGroup:
    name: str
    elements: list = field(default_factory=list)


@dataclass
class GMachine:
    name: str
    output: str = ""
    groups: list = field(default_factory=list)
    additional: list = field(default_factory=list)

    def all_elements(self):
        for g in self.groups:
            for e in g.elements:
                yield g, e
        for e in self.additional:
            yield None, e


def default_models(method="resonator"):
    return [GModel(q=q, enabled=(q == "zlong"), method=method) for q, _, _ in QUANTITIES]


# ---------- conversion from a loaded wimba Project ----------
def _models_from_provider(el):
    from ..sources.resonator import ResonatorProvider
    from ..sources.table import TableProvider
    from ..sources.pytlwall_bridge import ChamberProvider
    from ..sources.iw2d_bridge import IW2DProvider
    prov = el.provider
    models = []
    if isinstance(prov, ResonatorProvider):
        for r in prov.resonators:
            models.append(GModel(q=r.term, enabled=True, method="resonator",
                                 status="ready", params={"Rs": r.Rs, "Q": r.Q, "fr": r.fr}))
    elif isinstance(prov, TableProvider):
        models.append(GModel(q=prov.term, enabled=True, method="precalculated",
                             file=prov.path, origin=prov.origin, status="loaded"))
    elif isinstance(prov, ChamberProvider):
        for q, _, _ in QUANTITIES:
            if q != "wake":
                models.append(GModel(q=q, enabled=True, method="pytlwall", status="ready"))
    elif isinstance(prov, IW2DProvider):
        models.append(GModel(q="zlong", enabled=True, method="IW2D", status="ready"))
    # fill the remaining quantities as disabled rows so the table is uniform
    present = {m.q for m in models}
    for q, _, _ in QUANTITIES:
        if q not in present:
            models.append(GModel(q=q, enabled=False, method="As resonator"))
    order = {q: i for i, (q, _, _) in enumerate(QUANTITIES)}
    models.sort(key=lambda m: order.get(m.q, 99))
    return models


def _element_from(e):
    m = e.meta or {}
    info = dict(m.get("info", {}))
    pre = bool(info.get("pre_weighted", False))
    return GElement(
        name=e.name, category=getattr(e, "category", "element"),
        geometry=info,
        optics={"s": m.get("position"), "l": info.get("length"),
                "bx": m.get("beta_x"), "by": m.get("beta_y"), "pre": pre},
        layers=[], models=_models_from_provider(e))


def from_project(path) -> GMachine:
    import yaml
    from pathlib import Path
    data = yaml.safe_load(Path(path).read_text()) or {}
    if "devices" in data or "default_pipe" in data or ("groups" not in data and "optics" in data):
        raise ValueError(
            "This looks like an assemble/run config (optics + devices, no groups).\n"
            "Use  File \u2192 Open Config  to compute it, not Load Machine.")

    from ..builders import load_project
    proj = load_project(path)
    out = proj.output if isinstance(proj.output, str) else None
    gm = GMachine(name=proj.name, output=(out or f"output/{proj.name}/"))
    for g in proj.machine.groups:
        gm.groups.append(GGroup(g.name, [_element_from(e) for e in g.elements]))
    gm.additional = [_element_from(e) for e in proj.machine.additional]
    return gm


def from_config(path) -> GMachine:
    """Build the view-model from an assemble/run config (optics + devices).

    Uses the resolved assignment array, so the Machine tree and the Optics panel
    show the real per-element positions and betas. The (many) default-pipe lattice
    rows are summarised as a single entry rather than listed one by one.
    """
    from pathlib import Path
    from ..assembly import load_assembly

    result = load_assembly(str(path))
    gm = GMachine(name=result.name,
                  output=f"{Path(path).with_suffix('')}_output/")

    groups = {}
    order = []
    pipe_count = 0
    for r in result.rows:
        if r.kind == "default_pipe":
            pipe_count += 1
            continue
        g = r.group or "devices"
        if g not in groups:
            groups[g] = []
            order.append(g)
        groups[g].append(GElement(
            name=r.name, category=r.method,
            geometry=dict(r.geometry or {}),
            optics={"s": r.position, "l": r.length,
                    "bx": r.beta_x, "by": r.beta_y, "pre": r.weighted},
            layers=list(r.geometry.get("layers") or []) if r.geometry else [],
            models=default_models(method_label(r.method, r.weighted))))
    for g in order:
        gm.groups.append(GGroup(g, groups[g]))
    if pipe_count:
        note = GElement(name=f"default pipe  (\u00d7{pipe_count} lattice segments)",
                        category="default_pipe", geometry={},
                        optics={"pre": True}, layers=[], models=[])
        gm.groups.append(GGroup("default resistive wall", [note]))
    return gm


def new_machine(name="Untitled") -> GMachine:
    return GMachine(name=name, output="", groups=[GGroup("Group 1", [])], additional=[])


def new_element(name) -> GElement:
    return GElement(name=name, category="element",
                    geometry={"length": 1.0}, optics={}, layers=[],
                    models=default_models())


def optics_completeness(gm: GMachine):
    need = have = 0
    for _, e in gm.all_elements():
        if e.optics.get("pre"):
            continue
        need += 1
        if e.optics.get("bx") is not None:
            have += 1
    return have, need
