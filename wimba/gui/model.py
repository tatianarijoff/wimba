"""GUI view-model: a loose, editable mirror of a WIMBA machine.

The core `wimba` objects are built for computation (a provider per element). The
GUI needs something editable and uniform across sources, so it keeps its own
light model and converts a loaded `Scenario` into it. Phase 3 will translate this
back into providers when calculating.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from pathlib import Path
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


_UID = itertools.count(1)


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
    uid: int = field(default_factory=lambda: next(_UID))
    edited: set = field(default_factory=set)
    # which fields the *user* changed in the panels ("bx", "by", "l", "geometry",
    # "layers"). Only these are written back to the config: a beta that came from
    # the twiss must not be frozen into the file just because it was displayed,
    # or changing the optics file would stop moving it.
    # session-unique identity: the NAME is the human descriptor (files, optics,
    # results stay name-based by design); the uid is what the GUI uses to tell
    # elements apart, so renames and duplicate names cannot confuse identity
    own_base: dict = field(default_factory=dict)
    # gamma and frequency grid the element brought with it, e.g. from the
    # [beam_info] and [frequency_info] sections of a pytlwall config. An element
    # loaded from its own config does not belong to a machine, so these win over
    # whatever config happens to be open in the GUI. Empty for elements that came
    # from a machine, which correctly inherit the machine's settings.


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
    beam: object = None                            # a core.beam.Beam, or None
    optics_path: str = ""                          # twiss loaded from the GUI
    # The machine's beam. None means "not stated yet": every calculation then
    # refuses rather than assuming an energy, which is what the old default of
    # gamma = 7000 did silently.

    def all_elements(self):
        for g in self.groups:
            for e in g.elements:
                yield g, e
        for e in self.additional:
            yield None, e


def default_models(method=None):
    if method is None:
        from ..config import default_method
        method = default_method()
    # impedance quantities only: the wake has its own explicit Calculate actions
    return [GModel(q=q, enabled=(q == "zlong"), method=method)
            for q, _, _ in QUANTITIES if q != "wake"]


# ---------- conversion from a loaded wimba Scenario ----------
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


def from_machine_file(path) -> GMachine:
    """Build the view-model from a machine YAML (the `groups:` dialect).

    Named for what it reads. `from_project` used to be the name, back when the
    loader called a machine file a project; a project is now the container that
    holds several scenarios, so the old name pointed at the wrong level.
    """
    import yaml
    from pathlib import Path
    data = yaml.safe_load(Path(path).read_text()) or {}
    if "devices" in data or "default_pipe" in data or ("groups" not in data and "optics" in data):
        raise ValueError(
            "This looks like an assemble/run config (optics + devices, no groups).\n"
            "Use  File \u2192 Open Config  to compute it, not Load Machine.")

    from ..builders import load_scenario
    sc = load_scenario(path)
    out = sc.output if isinstance(sc.output, str) else None
    gm = GMachine(name=sc.name, output=(out or f"output/{sc.name}/"), beam=sc.beam)
    for g in sc.machine.groups:
        gm.groups.append(GGroup(g.name, [_element_from(e) for e in g.elements]))
    gm.additional = [_element_from(e) for e in sc.machine.additional]
    return gm


def from_config(path) -> GMachine:
    """Build the view-model from an assemble/run config (optics + devices).

    Uses the resolved assignment array, so the Machine tree and the Optics panel
    show the real per-element positions and betas. The (many) default-pipe lattice
    rows are summarised as a single entry rather than listed one by one.
    """
    from pathlib import Path
    from ..assembly import load_assembly

    import yaml as _yaml
    from ..builders import read_beam

    result = load_assembly(str(path))
    gm = GMachine(name=result.name,
                  output=f"{Path(path).with_suffix('')}_output/",
                  beam=read_beam(_yaml.safe_load(Path(path).read_text()) or {}))

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
        note = GElement(name=pipe_name,
                        category="default_pipe", geometry=geo,
                        optics={"pre": True}, layers=layers,
                        models=default_models(pipe_method))
        gm.groups.append(GGroup(
            f"default resistive wall  (\u00d7{pipe_count} lattice segments)", [note]))
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
def element_to_config(el: GElement, base_cfg: Optional[dict] = None,
                      compare_only: bool = False) -> dict:
    """Emit an assemble config that computes just this element.

    With ``compare_only`` the base element is left out and only the entries of
    ``el.compare`` are emitted, so an added comparison can be computed without
    repeating a calculation that is already in the Results tree.

    Grid, gamma and user materials are inherited from the config the machine was
    opened from (base_cfg), unless the element carries its own (``own_base``),
    as one loaded from a pytlwall config does: such an element belongs to no
    machine, so its own settings win. Geometry, layers and beta come from the
    element as edited in the GUI. Only pytlwall elements are supported for now (resonator /
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
        "layers": [{k: v for k, v in lay.items() if v not in (None, "")}
                   for lay in el.layers],
    }
    for axis in ("hor", "ver"):
        if geo.get(axis) is not None:
            spec[f"{axis}_m"] = float(geo[axis])

    # An element that carries its own gamma/grid belongs to no machine: its
    # settings win over the config that happens to be open in the GUI.
    base_cfg = dict(base_cfg or {})
    base_cfg.update({k: v for k, v in (getattr(el, "own_base", None) or {}).items() if v})
    devices = {} if compare_only else {"single": spec}
    output = [] if compare_only else [name]
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
    if compare_only and not devices:
        raise ValueError(
            "no comparison to calculate: add one under 'Additional calculations' "
            "first.")
    cfg = {
        "name": f"{name}_compare" if compare_only else f"{name}_single",
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
    # An element that carries its own gamma/grid belongs to no machine: its
    # settings win over the config that happens to be open in the GUI.
    base_cfg = dict(base_cfg or {})
    base_cfg.update({k: v for k, v in (getattr(el, "own_base", None) or {}).items() if v})
    if base == "precalculated":
        if not data_file:
            raise ValueError("Load Precalculated needs a data file "
                             "(a plain .dat or an import-map .yaml).")
        # a dict maps several components to (usually) one file: a spreadsheet or
        # an export holding them all
        if isinstance(data_file, dict):
            first = next(iter(data_file.values()))
            label = f"precalculated: {_P(first).name}"
            spec = {"source": "precalculated", "name": f"{el.name}[{label}]",
                    "files": {c: str(f) for c, f in data_file.items()},
                    "weighted": True}
            cfg = {"name": f"{el.name}_component", "grid": base_cfg.get("grid") or {
                       "frequency": {"min": 1.0e5, "max": 1.0e10, "n": 100, "log": True}},
                   "output": [spec["name"]], "devices": {"component": spec}}
            if base_cfg.get("gamma") is not None:
                cfg["gamma"] = base_cfg["gamma"]
            if base_cfg.get("materials"):
                cfg["materials"] = base_cfg["materials"]
            return cfg

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
                "layers": [{k: v for k, v in lay.items() if v not in (None, "")}
                           for lay in el.layers]}
        for axis in ("hor", "ver"):
            if geo.get(axis) is not None:
                spec[f"{axis}_m"] = float(geo[axis])
    else:
        raise ValueError(f"component bench: method '{method}' not supported.")

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


# ====================================================================== project
# A project is the container the GUI works in: one grid, one output root, and the
# scenarios being compared. A scenario is a machine plus the beam it is computed
# with; every scenario after the first is a duplicate of an earlier one, which is
# what keeps the comparison honest - they cannot have drifted apart in ways
# nobody chose.
@dataclass
class GScenario:
    label: str                      # what the user types and what plots are keyed by
    config: str                     # file name inside the project dir
    beam: object = None             # a core.beam.Beam, or None
    derived_from: Optional[str] = None
    computed_at: Optional[str] = None
    slug: str = ""                  # folder name; derived from the label

    def __post_init__(self):
        self.slug = self.slug or slugify(self.label)

    def to_dict(self) -> dict:
        d = {"label": self.label, "slug": self.slug, "config": self.config}
        if self.beam is not None:
            d["beam"] = self.beam.to_dict()
        if self.derived_from:
            d["derived_from"] = self.derived_from
        if self.computed_at:
            d["computed_at"] = self.computed_at
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "GScenario":
        from ..core.beam import Beam
        beam = d.get("beam")
        return cls(label=d["label"], config=d["config"],
                   beam=Beam.from_dict(beam) if beam else None,
                   derived_from=d.get("derived_from"),
                   computed_at=d.get("computed_at"),
                   slug=d.get("slug", ""))


@dataclass
class GProject:
    name: str
    dir: str
    scenarios: list = field(default_factory=list)
    grid: dict = field(default_factory=dict)     # shared by every scenario
    current: int = 0

    # ---- access ----
    @property
    def scenario(self) -> Optional[GScenario]:
        if not self.scenarios:
            return None
        return self.scenarios[min(self.current, len(self.scenarios) - 1)]

    def labels(self) -> list:
        return [s.label for s in self.scenarios]

    def unique_label(self, wanted: str) -> str:
        """A label not already taken, so folders never collide."""
        taken = {s.label for s in self.scenarios}
        slugs = {s.slug for s in self.scenarios}
        if wanted not in taken and slugify(wanted) not in slugs:
            return wanted
        n = 2
        while f"{wanted} ({n})" in taken or slugify(f"{wanted} ({n})") in slugs:
            n += 1
        return f"{wanted} ({n})"

    def add(self, scenario: GScenario) -> GScenario:
        if any(s.slug == scenario.slug for s in self.scenarios):
            raise ValueError(f"a scenario folder named '{scenario.slug}' already exists")
        self.scenarios.append(scenario)
        self.current = len(self.scenarios) - 1
        return scenario

    def rename(self, index: int, label: str) -> GScenario:
        sc = self.scenarios[index]
        if label != sc.label:
            others = [s for i, s in enumerate(self.scenarios) if i != index]
            if any(s.label == label or s.slug == slugify(label) for s in others):
                raise ValueError(f"another scenario is already called '{label}'")
            for s in self.scenarios:
                if s.derived_from == sc.label:
                    s.derived_from = label        # keep the lineage pointing somewhere
            sc.label, sc.slug = label, slugify(label)
        return sc

    def remove(self, index: int) -> GScenario:
        sc = self.scenarios[index]
        children = [s.label for s in self.scenarios if s.derived_from == sc.label]
        if children:
            raise ValueError(
                f"'{sc.label}' is what {', '.join(children)} was duplicated from; "
                "remove those first, or rename this one instead.")
        self.scenarios.pop(index)
        self.current = max(0, min(self.current, len(self.scenarios) - 1))
        return sc

    # ---- serialisation ----
    def to_dict(self) -> dict:
        return {"name": self.name, "grid": self.grid,
                "scenarios": [s.to_dict() for s in self.scenarios]}

    @classmethod
    def from_dict(cls, data: dict, directory) -> "GProject":
        return cls(name=data.get("name", Path(directory).name), dir=str(directory),
                   grid=data.get("grid") or {},
                   scenarios=[GScenario.from_dict(s) for s in data.get("scenarios") or []])


def slugify(label: str) -> str:
    """Folder name for a free-text label: 'flat top' -> 'flat_top'."""
    out = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(label).strip())
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_").lower() or "scenario"


def as_number(x):
    """YAML floats that are not YAML floats.

    PyYAML follows YAML 1.1, where an exponent needs a sign: `1.0e+8` is a float
    but `1.0e8` is a plain string. Configs are full of the second spelling, so
    anything read out of a grid has to be coerced before it is compared or
    formatted - a `:g` on a string raises.
    """
    if isinstance(x, (bool, int)) or x is None:
        return x                       # a point count stays an int, not 400.0
    try:
        return float(x)
    except (TypeError, ValueError):
        return x


def grid_of(cfg: dict) -> dict:
    """The frequency/time grid a config asks for, in comparable form."""
    grid = (cfg or {}).get("grid") or {}
    freq = grid.get("frequency") or grid.get("freq") or {}
    time = grid.get("time") or {}
    keep = lambda d: {k: as_number(d[k]) for k in ("min", "max", "n", "log") if k in d}
    out = {}
    if freq:
        out["frequency"] = keep(freq)
    if time:
        out["time"] = keep(time)
    return out


# keys whose string values are file references, relative to the config's folder
PATH_KEYS = {"optics", "file", "map", "path"}
PATH_DICT_KEYS = {"files", "wake_files"}


def freeze_config(src, dest) -> Path:
    """Copy a config into the project, keeping its file references working.

    A scenario owns its config: the copy is what the user then edits per
    scenario, and it must not change under them when the original is touched.
    But the data those configs point at - the MAD-X twiss, imported .dat files -
    is large and shared, so it stays where it is and the copy points at it by
    absolute path instead. Only references that actually resolve next to the
    source are rewritten; anything else is left exactly as written, so a config
    using absolute paths, or one whose data is missing, is copied unharmed and
    fails later with its own error rather than a confusing one from here.
    """
    import yaml

    src, dest = Path(src), Path(dest)
    base = src.parent
    data = yaml.safe_load(src.read_text()) or {}

    def walk(node):
        if isinstance(node, dict):
            return {k: _resolve(k, v, base) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    def _resolve(key, value, base):
        if key in PATH_KEYS and isinstance(value, str):
            here = base / value
            return str(here.resolve()) if here.exists() else value
        if key in PATH_DICT_KEYS and isinstance(value, dict):
            return {c: (str((base / f).resolve()) if isinstance(f, str)
                        and (base / f).exists() else f) for c, f in value.items()}
        return walk(value)

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(yaml.safe_dump(walk(data), sort_keys=False))
    return dest


# =================================================================== serialiser
# Writing the panels back into the scenario's config.
#
# This patches the config that is already there; it never dumps a fresh one from
# the view-model. That is not caution for its own sake - the view-model is a
# lossy picture of the file. A pytlwall element loaded from a machine file
# arrives here with `layers=[]`, because the layers live inside the provider and
# were never unpacked; and an assembly config's `devices:`/`default_pipe:` rules
# have already been resolved into an assignment array, so the rules themselves
# cannot be recovered from what the GUI holds. Dumping would quietly delete both.
# Patching writes only what the GUI genuinely owns and leaves every other line of
# the file exactly as the user wrote it.

# per-element keys the GUI owns, and what they are called in each dialect
_OPTICS_KEYS = {"bx": ("beta_x", "beta_x"), "by": ("beta_y", "beta_y"),
                "l": ("length", "length_m")}


def _entry_names(spec) -> set:
    """Element names a config entry stands for, when it says so explicitly."""
    name = spec.get("name") if isinstance(spec, dict) else None
    if isinstance(name, str):
        return {name}
    if isinstance(name, list):
        return set(name)
    return set()          # a file-driven entry expands to names we cannot see here


def patch_config(cfg: dict, machine, optics=None) -> dict:
    """Return `cfg` with the machine's beam, removals and edits applied.

    Everything not listed here is left untouched, including entries whose element
    names this function cannot resolve (a `file:`-driven device expands to many
    elements at load time, so it is never dropped on the strength of a name).
    """
    cfg = dict(cfg or {})
    assembly = "devices" in cfg or "default_pipe" in cfg

    beam = getattr(machine, "beam", None)
    if beam is not None:
        cfg["beam"] = beam.to_dict()
        cfg.pop("gamma", None)      # one authority for the energy, not two
    if optics:
        cfg["optics"] = str(optics)

    alive, edits = {}, {}
    for _g, e in machine.all_elements():
        if getattr(e, "category", "") == "default_pipe":
            continue                        # the pipe is a rule, not an element
        alive[e.name] = e
        if e.edited:
            edits[e.name] = e

    if assembly:
        devices = dict(cfg.get("devices") or {})
        for key, spec in list(devices.items()):
            names = _entry_names(spec)
            if names and not (names & set(alive)):
                devices.pop(key)
                continue
            for name in names & set(edits):
                devices[key] = _apply_edits(dict(spec), edits[name], assembly=True)
        cfg["devices"] = devices
    else:
        groups = {}
        for gname, entries in (cfg.get("groups") or {}).items():
            kept = []
            for spec in entries or []:
                name = spec.get("name")
                if name is not None and name not in alive:
                    continue
                kept.append(_apply_edits(dict(spec), edits[name], assembly=False)
                            if name in edits else spec)
            if kept:
                groups[gname] = kept
        cfg["groups"] = groups
        extra = [spec for spec in (cfg.get("additional") or [])
                 if spec.get("name") is None or spec.get("name") in alive]
        if extra:
            cfg["additional"] = extra
        elif "additional" in cfg:
            cfg.pop("additional")
    return cfg


def _apply_edits(spec: dict, el, assembly: bool) -> dict:
    """Write the fields the user changed on this element into its config entry."""
    for key, (machine_key, assembly_key) in _OPTICS_KEYS.items():
        if key not in el.edited:
            continue
        value = el.optics.get(key)
        target = assembly_key if assembly else machine_key
        if value is None:
            spec.pop(target, None)
        else:
            if assembly and target == "length_m" and "length" in spec:
                target = "length"       # follow the spelling already in the file
            spec[target] = float(value)
    if "geometry" in el.edited:
        geo = el.geometry or {}
        for src, dest in (("radius", "radius_m"), ("hor", "hor_m"), ("ver", "ver_m")):
            if geo.get(src) is not None:
                spec[dest] = float(geo[src])
        if geo.get("shape"):
            spec["shape"] = geo["shape"]
    if "layers" in el.edited and el.layers:
        spec["layers"] = [{k: v for k, v in lay.items() if v not in (None, "")}
                          for lay in el.layers]
    return spec


def write_config(path, machine, optics=None) -> Path:
    """Patch the config at `path` in place and report whether anything changed."""
    import yaml

    path = Path(path)
    before = path.read_text()
    cfg = yaml.safe_load(before) or {}
    after = yaml.safe_dump(patch_config(cfg, machine, optics=optics), sort_keys=False)
    if after != before:
        path.write_text(after)
    return path
