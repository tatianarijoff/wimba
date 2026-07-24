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
    models: list = field(default_factory=list)     # list[GModel] (base calculation)
    compare: list = field(default_factory=list)    # list[GModel]: additional
                                                   # calculations, q = component
                                                   # (ZLong, ...), for comparison


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
    # impedance quantities only: the wake has its own explicit Calculate actions
    return [GModel(q=q, enabled=(q == "zlong"), method=method)
            for q, _, _ in QUANTITIES if q != "wake"]


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
    # fill the remaining impedance quantities as disabled rows (uniform table);
    # the wake is not a per-quantity model: it has its own Calculate actions
    present = {m.q for m in models}
    for q, _, _ in QUANTITIES:
        if q == "wake" or q in present:
            continue
        models.append(GModel(q=q, enabled=False, method="resonator"))
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
    pipe_count, pipe_geo, pipe_method = 0, None, "pytlwall"
    for r in result.rows:
        if r.kind == "default_pipe":
            pipe_count += 1
            if pipe_geo is None and r.geometry:
                pipe_geo = r.geometry
                pipe_method = method_label(r.method, r.weighted)
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
        geo = dict(pipe_geo or {})
        layers = list(geo.pop("layers", None) or [])
        pipe_name = geo.pop("name", None) or "default pipe"
        note = GElement(name=f"{pipe_name}  (\u00d7{pipe_count} lattice segments)",
                        category="default_pipe", geometry=geo,
                        optics={"pre": True}, layers=layers,
                        models=default_models(pipe_method))
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


# ---------- element -> runnable config (single-element calculation) ----------
def element_to_config(el: GElement, base_cfg: Optional[dict] = None) -> dict:
    """Emit an assemble config that computes just this element.

    Grid, gamma and user materials are inherited from the config the machine was
    opened from (base_cfg); geometry, layers and beta come from the element as
    edited in the GUI. Only pytlwall elements are supported for now (resonator /
    precalculated single-element runs come with the full machine->config bridge).
    """
    model = next((m for m in el.models if m.enabled), None)
    base = method_base(model.method) if model else "pytlwall"
    if base.lower() != "pytlwall":
        raise ValueError(
            f"single-element calculation supports pytlwall elements for now "
            f"(this one is '{base}').")

    geo = el.geometry or {}
    if geo.get("radius") is None:
        raise ValueError(f"element '{el.name}' has no radius in its geometry.")
    name = el.name.split("  (")[0]                     # strip '  (xN lattice segments)'

    spec = {
        "source": "chamber",
        "name": name,
        "method": "pytlwall",
        "radius_m": float(geo["radius"]),
        "shape": geo.get("shape", "CIRCULAR"),
        "length_m": float(el.optics.get("l") or geo.get("length") or 1.0),
        "beta_x": float(el.optics.get("bx") or 1.0),
        "beta_y": float(el.optics.get("by") or 1.0),
        "weighted": method_weighted(model.method) if model else False,
        "layers": [dict(lay) for lay in el.layers],
    }
    for axis in ("hor", "ver"):
        if geo.get(axis) is not None:
            spec[f"{axis}_m"] = float(geo[axis])

    base_cfg = base_cfg or {}
    devices = {"single": spec}
    output = [name]
    for i, cmp_ in enumerate(getattr(el, "compare", []) or []):
        cbase = method_base(cmp_.method).lower()
        cname = f"{name}[{method_base(cmp_.method)} {cmp_.q}]"
        if cbase == "precalculated":
            if not cmp_.file:
                raise ValueError(
                    f"compare entry {cmp_.q} (precalculated) needs a file "
                    "(a plain .dat or an import-map .yaml).")
            key = "map" if cmp_.file.lower().endswith((".yaml", ".yml")) else "files"
            val = cmp_.file if key == "map" else {cmp_.q: cmp_.file}
            cspec = {"source": "precalculated", "name": cname, key: val,
                     "weighted": method_weighted(cmp_.method)}
        elif cbase in ("pytlwall", "iw2d"):
            cspec = dict(spec, name=cname, method=cbase,
                         weighted=method_weighted(cmp_.method))
        else:
            raise ValueError(f"compare entry: method '{cmp_.method}' not supported.")
        devices[f"compare_{i}"] = cspec
        output.append(cname)
    cfg = {
        "name": f"{name}_single",
        "grid": base_cfg.get("grid") or {
            "frequency": {"min": 1.0e5, "max": 1.0e10, "n": 100, "log": True}},
        "output": output,
        "devices": devices,
    }
    if base_cfg.get("gamma") is not None:
        cfg["gamma"] = base_cfg["gamma"]
    if base_cfg.get("materials"):
        cfg["materials"] = base_cfg["materials"]
    if "time" not in cfg["grid"]:
        cfg["grid"] = dict(cfg["grid"])
        cfg["grid"].setdefault("time", {"min": 1.0e-12, "max": 5.0e-9, "n": 200})
    return cfg


def component_config(el: GElement, method: str, base_cfg: Optional[dict] = None,
                     data_file: Optional[str] = None,
                     data_component: str = "ZLong") -> dict:
    """Config for the Component bench: ONE calculation of this component with the
    given method. Source names carry the method label ("NAME[pytlwall]",
    "NAME[precalculated: file]") so accumulated runs are distinguishable."""
    from pathlib import Path as _P

    base = method_base(method).lower()
    name = el.name.split("  (")[0]
    if base == "precalculated":
        if not data_file:
            raise ValueError("Load Precalculated needs a data file "
                             "(a plain .dat or an import-map .yaml).")
        label = f"precalculated: {_P(data_file).name}"
        if str(data_file).lower().endswith((".yaml", ".yml")):
            spec = {"source": "precalculated", "name": f"{name}[{label}]",
                    "map": str(data_file), "weighted": True}
        else:
            spec = {"source": "precalculated", "name": f"{name}[{label}]",
                    "files": {data_component: str(data_file)}, "weighted": True}
    elif base in ("pytlwall", "iw2d"):
        geo = el.geometry or {}
        if geo.get("radius") is None:
            raise ValueError(f"component '{name}' has no radius in its geometry.")
        label = "IW2D" if base == "iw2d" else "pytlwall"
        spec = {"source": "chamber", "name": f"{name}[{label}]", "method": base,
                "radius_m": float(geo["radius"]),
                "shape": geo.get("shape", "CIRCULAR"),
                "length_m": float(el.optics.get("l") or geo.get("length") or 1.0),
                "beta_x": float(el.optics.get("bx") or 1.0),
                "beta_y": float(el.optics.get("by") or 1.0),
                "weighted": method_weighted(method),
                "layers": [dict(lay) for lay in el.layers]}
        for axis in ("hor", "ver"):
            if geo.get(axis) is not None:
                spec[f"{axis}_m"] = float(geo[axis])
    else:
        raise ValueError(f"component bench: method '{method}' not supported.")

    base_cfg = base_cfg or {}
    cfg = {"name": f"{name}_component",
           "grid": base_cfg.get("grid") or {
               "frequency": {"min": 1.0e5, "max": 1.0e10, "n": 100, "log": True}},
           "output": [spec["name"]],
           "devices": {"bench": spec}}
    if base_cfg.get("gamma") is not None:
        cfg["gamma"] = base_cfg["gamma"]
    if base_cfg.get("materials"):
        cfg["materials"] = base_cfg["materials"]
    return cfg
