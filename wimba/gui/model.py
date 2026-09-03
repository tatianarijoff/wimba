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
#: What an element can be computed with. Only imported data can arrive already
#: weighted by beta over the average beta: for everything else WIMBA does the
#: weighting itself, so "(weighted)" there would mean weighting it twice.
METHODS = [
    "pytlwall",
    "IW2D",
    "precalculated", "precalculated (weighted)",
    "resonator",
]


#: A resonator says nothing about a wall: what defines it is a list of
#: resonances, each belonging to one impedance component. These are the
#: components a mode can be given for, spelled as the config spells them, and
#: the (R, Q, f) keys each one writes - the layout pywit uses for HOMs and the
#: one `sources/resonator.py` reads.
MODE_COMPONENTS = ("ZLong", "ZDipX", "ZDipY", "ZQuadX", "ZQuadY")
MODE_KEYS = {
    "ZLong":  ("Rl", "Ql", "fl"),
    "ZDipX":  ("Rxd", "Qxd", "fxd"),
    "ZDipY":  ("Ryd", "Qyd", "fyd"),
    "ZQuadX": ("Rxq", "Qxq", "fxq"),
    "ZQuadY": ("Ryq", "Qyq", "fyq"),
}
#: Rs units per component, for the panel: an impedance longitudinally, an
#: impedance per metre transversally.
MODE_UNITS = {"ZLong": "\u03a9", "ZDipX": "\u03a9/m", "ZDipY": "\u03a9/m",
              "ZQuadX": "\u03a9/m", "ZQuadY": "\u03a9/m"}
#: `core.terms` ids (what a built ResonatorProvider carries) -> the above.
TERM_COMPONENT = {"zlong": "ZLong", "zxdip": "ZDipX", "zydip": "ZDipY",
                  "zxquad": "ZQuadX", "zyquad": "ZQuadY"}


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
class GMode:
    """One resonance of a resonator element, as the panel edits it.

    One row, one component: a real object's mode often speaks in several planes
    at once, and the config can write it that way, but asking a user to fill a
    five-plane mode in one row is how empty cells become zeros. Rows sum, so
    two rows are the same physics as one mode carrying two triples.
    """
    q: str = "ZLong"                 # one of MODE_COMPONENTS
    Rs: float = 0.0                  # shunt impedance [Ohm] or [Ohm/m]
    Q: float = 1.0
    fr: float = 0.0                  # resonant frequency [Hz]


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
    modes: list = field(default_factory=list)      # list[GMode]: what defines
                                                   # this element when its
                                                   # method is 'resonator'.
                                                   # Kept beside the geometry,
                                                   # not instead of it: a
                                                   # method is a choice, and
                                                   # changing it back must not
                                                   # have thrown the wall away
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
    #: (x, y) WIMBA worked out for itself, and where from: the twiss rows, the
    #: elements' own betas, or nothing. Shown, never edited.
    beta_mean: tuple = (1.0, 1.0)
    beta_mean_source: str = "none"
    #: (x, y) stated by the user -- beta bar from the tunes in smooth
    #: approximation. None means "use the one above". When set it wins, because
    #: it was written on purpose and the other is only an estimate of it.
    smooth_beta: tuple = None

    def mean_in_use(self):
        """The averages a calculation would divide by, and where they came from."""
        if self.smooth_beta:
            return tuple(self.smooth_beta), "smooth_beta"
        return tuple(self.beta_mean), self.beta_mean_source
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
        layers=[], models=_models_from_provider(e),
        modes=_modes_from_provider(e))


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
    gm.beta_mean = tuple(getattr(sc.machine, "beta_mean", (1.0, 1.0)))
    gm.beta_mean_source = getattr(sc.machine, "beta_mean_source", "none")
    gm.smooth_beta = _stated_smooth_beta(path)
    for g in sc.machine.groups:
        gm.groups.append(GGroup(g.name, [_element_from(e) for e in g.elements]))
    gm.additional = [_element_from(e) for e in sc.machine.additional]
    return gm


def _stated_smooth_beta(path):
    """``smooth_beta:`` as written in the file, or None.

    Read from the YAML rather than taken from what the loader resolved: the
    panel has to show whether the user stated one, which is a different question
    from which average the calculation used.
    """
    import yaml as _yaml
    from pathlib import Path as _Path
    try:
        data = _yaml.safe_load(_Path(path).read_text()) or {}
    except Exception:
        return None
    block = data.get("smooth_beta")
    if isinstance(block, dict) and "x" in block and "y" in block:
        return float(block["x"]), float(block["y"])
    if isinstance(block, (list, tuple)) and len(block) == 2:
        return float(block[0]), float(block[1])
    return None


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
    gm.beta_mean = tuple(result.beta_mean)
    gm.beta_mean_source = result.beta_mean_source
    gm.smooth_beta = _stated_smooth_beta(path)
    if gm.smooth_beta:
        # the assembly already applied it; show it as the user's, not WIMBA's
        gm.beta_mean, gm.beta_mean_source = (1.0, 1.0), "none"

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
            models=default_models(method_label(r.method, r.weighted)),
            # a resonator row carries its modes in params: without them the
            # Models tab would show the method and nothing that defines it
            modes=modes_from_dicts(((r.params or {}).get("modes")
                                    if r.method == "resonator" else None))))
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


# pytlwall's Layer defaults (pytlwall/layer.py). These are the parameters that
# have a neutral value: writing them out changes no result, and leaving them
# out leaves a file that only computes because the solver happens to fill the
# same numbers in. A config should say what it means.
LAYER_DEFAULTS = {"type": "CW", "epsr": 1.0, "tau": 0.0, "k_Hz": "inf",
                  "muinf_Hz": 0.0, "RQ": 0.0}


# Vacuum and perfect-conductor layers are computed from a formula: pytlwall
# reads none of sigma, epsr, tau, k, mu-infinity or RQ for them.
ANALYTIC_TYPES = ("V", "PEC")
MATERIAL_KEYS = ("sigma", "epsr", "tau", "k_Hz", "muinf_Hz", "RQ")


def layer_out(lay: dict) -> dict:
    """One layer, as it should appear in a config.

    Thickness and conductivity are NOT defaulted: they are the physics of the
    wall, and a guess there would be a number nobody chose. The model
    parameters are completed from pytlwall's own defaults - except for V and
    PEC layers, where they would be figures no calculation ever reads.
    """
    out = {k: v for k, v in lay.items() if v not in (None, "")}
    kind = str(out.get("type") or "CW").upper()
    out["type"] = kind
    if kind in ANALYTIC_TYPES:
        return {k: v for k, v in out.items() if k not in MATERIAL_KEYS}
    for key, value in LAYER_DEFAULTS.items():
        out.setdefault(key, value)
    return out


# A chamber method computes every impedance component at once, so a compare
# entry that names one is only choosing a label. This is the value that says
# "all of them" - it must match the entry in the Models tab.
ALL_IMPEDANCE = "All impedance"


#: The wake counterpart of ALL_IMPEDANCE. A chamber method produces every wake
#: component in one call, exactly as it does for the impedance.
ALL_WAKE = "All wake"

#: Wake components a comparison can name. WIMBA's own names, as in the results.
WAKE_COMPONENTS = ("WLong", "WDipX", "WDipY", "WQuadX", "WQuadY")


def is_wake_component(q) -> bool:
    """True when a compare entry asks for a wake rather than an impedance."""
    return (q or "") == ALL_WAKE or str(q or "").startswith("W")


def _carry_beam(cfg: dict, base_cfg: dict) -> None:
    """Put the beam into an emitted config, not just its gamma.

    gamma alone computes the same numbers, but it throws away the particle and
    the quantity the user actually typed - so a component defined for positrons
    at a given energy reopens as a bare number, and the file no longer says
    what it was written for.
    """
    beam = base_cfg.get("beam")
    if isinstance(beam, dict) and beam:
        cfg["beam"] = {k: v for k, v in beam.items() if not k.startswith("_")}
    if base_cfg.get("gamma") is not None:
        cfg["gamma"] = base_cfg["gamma"]


#: Five factors - long, xdip, ydip, xquad, yquad - in IW2D's own order. They
#: turn a round solve into another geometry and are read ONLY by the IW2D path;
#: pytlwall applies its own tables and ignores them.
IW2D_YOKOYA = "iw2d_yokoya"


def _yokoya_out(geo: dict) -> dict:
    """The Yokoya factors of a geometry, if it states any."""
    raw = geo.get(IW2D_YOKOYA)
    if not raw:
        return {}
    factors = [float(v) for v in raw] if not isinstance(raw, str) else \
        [float(v) for v in raw.split()]
    if len(factors) != 5:
        raise ValueError(
            f"{IW2D_YOKOYA} needs five numbers - long, xdip, ydip, xquad, "
            f"yquad - got {len(factors)}.")
    return {IW2D_YOKOYA: factors}


def _aperture(geo: dict, who: str) -> dict:
    """The aperture keys a chamber spec needs, for the shape it declares.

    A circle is defined by one radius; an ellipse or a rectangle by two
    semi-axes. Requiring a radius for all three (as this did) makes a
    rectangular chamber impossible to state, and lets a stale radius travel
    with a shape that ignores it.
    """
    shape = str(geo.get("shape") or "CIRCULAR").upper()
    out = {"shape": shape}
    hor, ver = geo.get("hor"), geo.get("ver")
    if shape == "CIRCULAR":
        if geo.get("radius") is None:
            raise ValueError(f"{who} has no radius in its geometry.")
        out["radius_m"] = float(geo["radius"])
        return out
    if hor is None or ver is None:
        raise ValueError(
            f"{who} is {shape} but gives no horizontal and vertical "
            f"semi-axis. A circle takes a radius; every other shape takes both.")
    out["hor_m"] = float(hor)
    out["ver_m"] = float(ver)
    if geo.get("radius") is not None:
        out["radius_m"] = float(geo["radius"])
    return out


# ---------- element -> runnable config (single-element calculation) ----------
def modes_out(el: GElement) -> list:
    """`el.modes` as the `modes:` list a config carries.

    One row becomes one mode with one triple. Validation is deliberately NOT
    duplicated here: the emitted list goes through `assembly.read_modes`, which
    is the same check a hand-written config gets, so the panel and the file
    cannot drift into disagreeing about what a valid mode is.
    """
    from ..assembly import read_modes
    out = []
    for m in (el.modes or []):
        q = str(getattr(m, "q", "") or "ZLong")
        if q not in MODE_KEYS:
            raise ValueError(
                f"resonator mode: '{q}' is not an impedance component. "
                f"Use one of {', '.join(MODE_COMPONENTS)}.")
        rk, qk, fk = MODE_KEYS[q]
        row = {}
        for key, label, value in ((rk, "Rs", m.Rs), (qk, "Q", m.Q),
                                  (fk, "f_r", m.fr)):
            try:
                row[key] = float(value)
            except (TypeError, ValueError):
                # a half-typed field: the validator lets "1e" through while the
                # user is still typing, and it must not reach the engine
                raise ValueError(
                    f"resonator mode ({q}): {label} = '{value}' is not a "
                    f"number.") from None
        out.append(row)
    return read_modes(out, el.name.split("  (")[0])


def modes_from_dicts(modes) -> list:
    """`modes:` from a config (or a JSON HOM table) as panel rows.

    A mode carrying three planes comes back as three rows: the panel edits one
    component at a time, and rows sum to the same impedance.
    """
    rows = []
    for mode in (modes or []):
        if not isinstance(mode, dict):
            continue
        for q, (rk, qk, fk) in MODE_KEYS.items():
            if mode.get(rk) is None and mode.get(fk) is None:
                continue
            rows.append(GMode(q=q, Rs=as_number(mode.get(rk)) or 0.0,
                              Q=as_number(mode.get(qk)) or 1.0,
                              fr=as_number(mode.get(fk)) or 0.0))
    return rows


def _modes_from_provider(el) -> list:
    """Panel rows for an element whose provider is already built."""
    try:
        from ..sources.resonator import ResonatorProvider
    except Exception:                       # numpy-less environment: no rows
        return []
    prov = getattr(el, "provider", None)
    if not isinstance(prov, ResonatorProvider):
        return []
    return [GMode(q=TERM_COMPONENT.get(r.term, "ZLong"), Rs=r.Rs, Q=r.Q, fr=r.fr)
            for r in prov.resonators]


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
    element as edited in the GUI. Wall methods - pytlwall and IW2D - and
    resonator are supported: the first two from the geometry and layers, the
    third from the element's modes. A precalculated single-element run comes
    with the full machine->config bridge, since what defines it is a file and
    an import map rather than anything editable in the panels.
    """
    model = next((m for m in el.models if m.enabled), None)
    base = (method_base(model.method) if model else "pytlwall").lower()
    if base not in ("pytlwall", "iw2d", "resonator"):
        raise ValueError(
            f"single-element calculation supports a wall (pytlwall, IW2D) or a "
            f"resonator; this one is '{base}'. Imported data is computed "
            f"through Component \u25b8 Load Precalculated, which needs the file "
            f"and its import map.")

    geo = el.geometry or {}
    name = el.name.split("  (")[0]                     # strip '  (xN lattice segments)'

    if base == "resonator":
        spec = {
            "source": "resonator",
            "name": name,
            "method": "resonator",
            "length_m": float(el.optics.get("l") or geo.get("length") or 1.0),
            "beta_x": float(el.optics.get("bx") or 1.0),
            "beta_y": float(el.optics.get("by") or 1.0),
            "weighted": False,
            "modes": modes_out(el),
        }
    else:
        aperture = _aperture(geo, f"element '{el.name}'")
        spec = {
            "source": "chamber",
            "name": name,
            "method": base,
            **aperture,
            "length_m": float(el.optics.get("l") or geo.get("length") or 1.0),
            "beta_x": float(el.optics.get("bx") or 1.0),
            "beta_y": float(el.optics.get("by") or 1.0),
            "weighted": method_weighted(model.method) if model else False,
            "layers": [layer_out(lay) for lay in el.layers],
            **_yokoya_out(geo),
            **({"test_beam_shift": geo["test_beam_shift"]}
               if geo.get("test_beam_shift") is not None else {}),
        }
    # An element that carries its own gamma/grid belongs to no machine: its
    # settings win over the config that happens to be open in the GUI.
    base_cfg = dict(base_cfg or {})
    base_cfg.update({k: v for k, v in (getattr(el, "own_base", None) or {}).items() if v})
    devices = {} if compare_only else {"single": spec}
    output = [] if compare_only else [name]
    for i, cmp_ in enumerate(getattr(el, "compare", []) or []):
        cbase = method_base(cmp_.method).lower()
        wake = is_wake_component(cmp_.q)
        every = (cmp_.q or ALL_IMPEDANCE) in (ALL_IMPEDANCE, ALL_WAKE)
        cname = (f"{name}[{method_base(cmp_.method)}]" if every
                 else f"{name}[{method_base(cmp_.method)} {cmp_.q}]")
        if cbase == "precalculated":
            if every:
                raise ValueError(
                    "a precalculated comparison is one file, so it holds one "
                    "component: pick the component that file contains instead "
                    f"of '{cmp_.q}'.")
            if not cmp_.file:
                raise ValueError(
                    f"compare entry {cmp_.q} (precalculated) needs a file "
                    "(a plain .dat or an import-map .yaml).")
            if cmp_.file.lower().endswith((".yaml", ".yml")):
                # a map describes its own components, wake ones included
                key, val = "map", cmp_.file
            else:
                # a wake column belongs in wake_files: the run pipeline reads
                # the two separately, and putting a wake in files would have it
                # interpolated onto the frequency grid as if it were impedance
                key = "wake_files" if wake else "files"
                val = {cmp_.q: cmp_.file}
            cspec = {"source": "precalculated", "name": cname, key: val,
                     "weighted": method_weighted(cmp_.method)}
            if not cspec["weighted"]:
                # it is the same element, so it has the same optics: without
                # these the assembler cannot locate it and falls back to
                # beta = 1, warning about a device the user never placed
                cspec["beta_x"] = float(el.optics.get("bx") or 1.0)
                cspec["beta_y"] = float(el.optics.get("by") or 1.0)
        elif cbase in ("pytlwall", "iw2d"):
            if base == "resonator":
                # The base element is a mode spectrum, so its spec carries no
                # aperture and no layers: a wall comparison has to be built
                # from the geometry the element still holds. Which is exactly
                # why switching method leaves the wall in place rather than
                # clearing it.
                cspec = {"source": "chamber", "name": cname, "method": cbase,
                         **_aperture(geo, f"element '{el.name}'"),
                         "length_m": spec["length_m"],
                         "beta_x": spec["beta_x"], "beta_y": spec["beta_y"],
                         "weighted": method_weighted(cmp_.method),
                         "layers": [layer_out(lay) for lay in el.layers],
                         **_yokoya_out(geo)}
            else:
                cspec = dict(spec, name=cname, method=cbase,
                             weighted=method_weighted(cmp_.method))
            if cbase != "iw2d":
                # the factors are IW2D's; copying the base spec dragged them
                # into a pytlwall device, where they mean nothing
                cspec.pop(IW2D_YOKOYA, None)
        elif cbase == "resonator":
            raise ValueError(
                "a resonator comparison has nowhere to take its modes from: "
                "it would reuse this element's, which is the same calculation "
                "again. Build the resonator as its own component (Component "
                "\u25b8 New Component, method resonator) and plot the two "
                "results together.")
        else:
            raise ValueError(f"compare entry: method '{cmp_.method}' not supported.")

        # Two rows can ask for the same thing - the same method on the same
        # component - and would then produce two devices with one name: the
        # second silently overwrites the first in the results, and the output
        # list carries a duplicate. Number the repeats instead.
        if cspec["name"] in output:
            n = sum(1 for o in output if o == cspec["name"]
                    or o.startswith(cspec["name"] + " #"))
            cspec["name"] = f"{cspec['name']} #{n + 1}"
        devices[f"compare_{i}"] = cspec
        output.append(cspec["name"])
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
    _carry_beam(cfg, base_cfg)
    if base_cfg.get("materials"):
        cfg["materials"] = base_cfg["materials"]
    if "time" not in cfg["grid"]:
        cfg["grid"] = dict(cfg["grid"])
        cfg["grid"].setdefault("time", {"min": 1.0e-12, "max": 5.0e-9, "n": 200})
    return cfg


def wants_wake(el: GElement) -> bool:
    """True when any comparison on this element asks for a wake.

    Such a comparison produces nothing at all unless the calculation runs with
    a time grid, so asking for one is taken as asking for the wake rather than
    quietly returning an empty column.
    """
    return any(is_wake_component(c.q) for c in (getattr(el, "compare", None) or []))


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
            _carry_beam(cfg, base_cfg)
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
    elif base == "resonator":
        # No geometry and no layers: what the engine reads is the mode list.
        # Length and beta still belong here - a resonance is somewhere in a
        # ring, and its transverse weight is the same as any other element's.
        spec = {"source": "resonator", "name": f"{name}[resonator]",
                "method": "resonator",
                "length_m": float(el.optics.get("l")
                                  or (el.geometry or {}).get("length") or 1.0),
                "beta_x": float(el.optics.get("bx") or 1.0),
                "beta_y": float(el.optics.get("by") or 1.0),
                "weighted": False,
                "modes": modes_out(el)}
    elif base in ("pytlwall", "iw2d"):
        geo = el.geometry or {}
        aperture = _aperture(geo, f"component '{name}'")
        label = "IW2D" if base == "iw2d" else "pytlwall"
        spec = {"source": "chamber", "name": f"{name}[{label}]", "method": base,
                **aperture,
                "length_m": float(el.optics.get("l") or geo.get("length") or 1.0),
                "beta_x": float(el.optics.get("bx") or 1.0),
                "beta_y": float(el.optics.get("by") or 1.0),
                "weighted": method_weighted(method),
                "layers": [layer_out(lay) for lay in el.layers],
                **_yokoya_out(geo),
                **({"test_beam_shift": geo["test_beam_shift"]}
                   if geo.get("test_beam_shift") is not None else {})}
    else:
        raise ValueError(
            f"component bench: method '{method}' is not one it can compute. "
            f"Use pytlwall or IW2D for a wall, resonator for a mode spectrum, "
            f"or Load Precalculated for imported data.")

    cfg = {"name": f"{name}_component",
           "grid": base_cfg.get("grid") or {
               "frequency": {"min": 1.0e5, "max": 1.0e10, "n": 100, "log": True}},
           "output": [spec["name"]],
           "devices": {"bench": spec}}
    _carry_beam(cfg, base_cfg)
    if base_cfg.get("materials"):
        cfg["materials"] = base_cfg["materials"]
    return cfg


def component_save_config(el: GElement, method: Optional[str] = None,
                          base_cfg: Optional[dict] = None,
                          data_file: Optional[str] = None,
                          data_component: str = "ZLong") -> dict:
    """Config for saving a bench component to a file the user chooses.

    Same content as `component_config`, which is what the bench already writes
    to a temporary directory before every calculation - so this covers every
    method the bench supports, not only pytlwall. A pytlwall .cfg would not:
    it is a debug dump of one chamber at unit length and beta = 1, and it
    cannot express an IW2D or a precalculated component at all.

    Two differences from the temporary config. The method label is stripped
    from the device and output names ("PIPE[pytlwall]" -> "PIPE"): the label
    exists to keep accumulated runs apart in the Results tree, and would be
    baked into every result computed from the saved file. And the method is
    taken from the element's enabled model unless one is given.

    The result is an assembly config with a single device, so it reopens with
    File > Open Config and runs headless with `wimba run`.
    """
    if method is None:
        model = next((m for m in el.models if m.enabled), None)
        method = model.method if model else "pytlwall"
    if method_base(method).lower() == "precalculated" and not data_file:
        raise ValueError(
            "a precalculated component has no geometry to save: what defines "
            "it is the data file and how its columns are read. Save an import "
            "map instead (Component > Load Precalculated), which is a file in "
            "its own right and can be referenced from any config.")

    cfg = component_config(el, method, base_cfg=base_cfg,
                           data_file=data_file, data_component=data_component)
    name = el.name.split("  (")[0]
    label = f"[{method_base(method)}]"
    for spec in cfg.get("devices", {}).values():
        if isinstance(spec.get("name"), str) and spec["name"].endswith(label):
            spec["name"] = spec["name"][: -len(label)]
    cfg["output"] = [name]
    return cfg


def component_config_text(cfg: dict, method: str = "") -> str:
    """A saved component config as text: a header saying what the file is,
    then the YAML. The header matters because the file is opened again months
    later by someone who did not write it."""
    import yaml as _yaml

    name = cfg.get("output", ["component"])[0]
    engine = f" ({method})" if method else ""
    header = [
        f"# WIMBA component: {name}{engine}",
        "#",
        "# One device and nothing else - no lattice, no default pipe. Reopen it",
        "# with File > Open Config in the GUI, or compute it with:",
        "#",
        f"#     wimba run {name}_component.yaml",
        "#",
        "# The grid and gamma below are the ones the component was defined with;",
        "# used inside a machine, the study config's own values win instead.",
        "",
    ]
    if cfg.get("gamma") is None:
        header[-1:] = [
            "# NOTE: no gamma - this file states no beam, so a calculation from",
            "# it will refuse to run until one is added.",
            "",
        ]
    return "\n".join(header) + _yaml.safe_dump(cfg, sort_keys=False)


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
    src, dest = Path(src), Path(dest)
    base = src.parent
    data = read_yaml_text(src.read_text())

    # Nodes are edited IN PLACE rather than rebuilt. A dict comprehension would
    # return a plain dict and drop every comment ruamel attached to that
    # mapping, which is the whole point of loading it round-trip.
    def walk(node):
        if isinstance(node, dict):
            for k in list(node):
                node[k] = _resolve(k, node[k], base)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                node[i] = walk(v)
        return node

    def _resolve(key, value, base):
        if key in PATH_KEYS and isinstance(value, str):
            here = base / value
            return str(here.resolve()) if here.exists() else value
        if key in PATH_DICT_KEYS and isinstance(value, dict):
            for c in list(value):
                f = value[c]
                if isinstance(f, str) and (base / f).exists():
                    value[c] = str((base / f).resolve())
            return value
        return walk(value)

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(write_yaml_text(walk(data)))
    return dest


# ============================================================ comment-safe YAML
# PyYAML parses a document into plain Python objects and throws the text away:
# comments, blank lines and hand alignment do not survive safe_load/safe_dump.
# That is fine for a file WIMBA generates, and wrong for a file a user wrote --
# a config's comments are where the reasoning lives (why space charge is off,
# where a number came from, which alternative block to uncomment), and losing
# them on a Save Project is worse than losing nothing at all, because nothing
# reports it.
#
# ruamel.yaml in round-trip mode keeps the original text for everything it did
# not change. It normalises padding inside values and may re-wrap a very long
# flow sequence, which is cosmetic; every comment and the key order survive.

def _rt():
    """A round-trip YAML instance, or None when ruamel is not installed."""
    try:
        from ruamel.yaml import YAML
    except ImportError:
        return None
    y = YAML()                 # typ="rt" is the default
    y.preserve_quotes = True
    y.width = 4096             # do not re-wrap long flow sequences
    return y


def read_yaml_text(text):
    """Parse YAML, keeping the formatting when ruamel is available."""
    y = _rt()
    if y is None:
        import yaml
        return yaml.safe_load(text) or {}
    return y.load(text) or {}


def write_yaml_text(data) -> str:
    """Serialise, preserving whatever ``read_yaml_text`` kept."""
    y = _rt()
    if y is None:
        import yaml
        return yaml.safe_dump(data, sort_keys=False)
    import io
    buf = io.StringIO()
    y.dump(data, buf)
    return buf.getvalue()


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


def _deepcopy(node):
    """Deep copy that keeps ruamel's comment metadata (dict() would not)."""
    import copy as _copy
    return _copy.deepcopy(node)


def _set_mapping(cfg, key, new):
    """Write `new` into cfg[key] without replacing the node itself.

    Assigning a fresh dict would work, but ruamel attaches a mapping's trailing
    comments to its last key -- so replacing the `beam:` block also deletes the
    comment block written under it. Updating the existing node in place keeps
    those comments where the user put them.
    """
    old = cfg.get(key)
    if not isinstance(old, dict):
        cfg[key] = new
        return
    for k in list(old):
        if k not in new:
            del old[k]
    for k, v in new.items():
        old[k] = v


def _same_kind_copy(node):
    """A shallow copy that keeps the node's type.

    ``dict(node)`` would work, but on a ruamel CommentedMap it produces a plain
    dict and every comment attached to that mapping -- including the comments at
    the top of the document -- is dropped on the way out. ``.copy()`` keeps them.
    """
    if node is None:
        return {}
    copy = getattr(node, "copy", None)
    return copy() if callable(copy) else dict(node)


#: The five ways a beam can be stated. Exactly one of them is what the user
#: typed; the rest are derived from it.
BEAM_MODES = ("gamma", "beta", "energy", "kinetic", "momentum")


def beam_out(beam) -> dict:
    """The beam as the user stated it: the particle, the mode, and that value.

    ``Beam.to_dict()`` also carries everything derived from that value, which is
    right for handing a run its gamma and wrong for writing a file. Three keys
    that must agree, where one would do, are three keys that can disagree after
    the first hand edit -- and writing the derived form is what turned a
    hand-written ``8e+10`` into ``80000000000.0`` on every save.
    """
    full = {k: v for k, v in beam.to_dict().items() if not str(k).startswith("_")}
    mode = full.get("mode")
    if mode not in BEAM_MODES or mode not in full:
        return full                   # a mode we don't know: keep what we got
    out = {}
    for key in ("particle", "mode"):
        if key in full:
            out[key] = full[key]
    out[mode] = full[mode]
    return out


def _same_beam(existing, wanted: dict) -> bool:
    """True when the file already says what we would write.

    Compared through :func:`as_number`, because a config may spell the energy
    ``8e+10`` -- which YAML 1.1 hands back as a string, not a float. A file that
    already states the right beam is left byte for byte alone, keeping its own
    spelling, its own key order and any extra quantity its author chose to
    write down.
    """
    if not isinstance(existing, dict):
        return False
    for key, value in wanted.items():
        old, new = as_number(existing.get(key)), as_number(value)
        if isinstance(old, float) and isinstance(new, float):
            if old != new:
                return False
        elif str(old) != str(new):
            return False
    return True


def _element_length(el):
    """The length WIMBA would use, from the optics or from the geometry."""
    o = getattr(el, "optics", None) or {}
    v = o.get("l")
    if v is None:
        v = (getattr(el, "geometry", None) or {}).get("length")
    v = as_number(v)
    return v if isinstance(v, float) else None


def _carries_its_own_optics(el) -> bool:
    """A weighted source already has the local optics folded into its data.

    Counting one of these as "missing a beta" would be a false alarm: there is
    no single place in the ring where 2220 BPMs sit, and that is the point of
    the weighted flag.
    """
    return any("(weighted)" in (m.method or "")
               for m in getattr(el, "models", []) if m.enabled)


def summarize_elements(elements) -> dict:
    """What a group -- or a whole machine -- is made of.

    A group holds nothing but a name and its elements, so everything worth
    saying about one has to be aggregated from them. The synthetic default-pipe
    entry is excluded from every aggregate and counted separately: it stands for
    thousands of lattice rows and has no position, no length and no beta, so
    averaging it in would be meaningless rather than merely wrong.
    """
    els = [e for e in elements if getattr(e, "category", "") != "default_pipe"]
    out = {"n": len(elements), "n_pipe": len(elements) - len(els),
           "span": None, "length": None, "methods": {}, "beta_range": None,
           "beta_have": 0, "beta_of": 0, "quantities": [], "mixed": False,
           "attention": []}
    starts, ends, lengths, bx_all, by_all, sets = [], [], [], [], [], []

    for el in els:
        o = getattr(el, "optics", None) or {}
        s, length = as_number(o.get("s")), _element_length(el)
        if isinstance(s, float):
            starts.append(s)
            ends.append(s + length if isinstance(length, float) else s)
        if isinstance(length, float):
            lengths.append(length)

        enabled = [m for m in getattr(el, "models", []) if m.enabled]
        for base in sorted({method_base(m.method or "") for m in enabled}):
            if base:
                out["methods"][base] = out["methods"].get(base, 0) + 1
        on = tuple(sorted({m.q for m in enabled}))
        if on:
            sets.append(on)

        bx, by = as_number(o.get("bx")), as_number(o.get("by"))
        if not _carries_its_own_optics(el):
            out["beta_of"] += 1
            if isinstance(bx, float) and isinstance(by, float):
                out["beta_have"] += 1
                bx_all.append(bx)
                by_all.append(by)

        if not enabled:
            out["attention"].append((el.name, "no quantity switched on"))
        elif bx == 1.0 and by == 1.0 and not _carries_its_own_optics(el):
            out["attention"].append((el.name, "\u03b2 = 1, the fallback"))
        elif length == 0.0:
            out["attention"].append((el.name, "zero length"))

    if starts:
        out["span"] = (min(starts), max(ends))
    if lengths:
        out["length"] = sum(lengths)
    if bx_all:
        out["beta_range"] = (min(bx_all + by_all), max(bx_all + by_all))
    if sets:
        out["quantities"] = sorted({q for on in sets for q in on})
        out["mixed"] = len(set(sets)) > 1
    return out


def patch_config(cfg: dict, machine, optics=None) -> dict:
    """Return `cfg` with the machine's beam, removals and edits applied.

    Everything not listed here is left untouched, including entries whose element
    names this function cannot resolve (a `file:`-driven device expands to many
    elements at load time, so it is never dropped on the strength of a name).
    """
    # A deep copy, so the nested in-place edits below never reach the caller's
    # dict: this function is pure, and the GUI keeps the config it passes in.
    # deepcopy preserves ruamel's comments, where dict() would drop them.
    cfg = _deepcopy(cfg) if cfg else {}
    assembly = "devices" in cfg or "default_pipe" in cfg

    beam = getattr(machine, "beam", None)
    if beam is not None:
        wanted = beam_out(beam)
        if not _same_beam(cfg.get("beam"), wanted):
            _set_mapping(cfg, "beam", wanted)
            cfg.pop("gamma", None)      # one authority for the energy, not two

    stated = getattr(machine, "smooth_beta", None)
    if stated:
        want = {"x": float(stated[0]), "y": float(stated[1])}
        if not _same_beam(cfg.get("smooth_beta"), want):
            _set_mapping(cfg, "smooth_beta", want)
    elif "smooth_beta" in cfg:
        # cleared in the panel: the machine's own average takes over again
        del cfg["smooth_beta"]
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
        devices = _same_kind_copy(cfg.get("devices"))
        for key, spec in list(devices.items()):
            names = _entry_names(spec)
            if names and not (names & set(alive)):
                devices.pop(key)
                continue
            for name in names & set(edits):
                devices[key] = _apply_edits(_same_kind_copy(spec), edits[name],
                                            assembly=True)
        _set_mapping(cfg, "devices", devices)
    else:
        groups = {}
        for gname, entries in (cfg.get("groups") or {}).items():
            kept = []
            for spec in entries or []:
                name = spec.get("name")
                if name is not None and name not in alive:
                    continue
                kept.append(_apply_edits(_same_kind_copy(spec), edits[name], assembly=False)
                            if name in edits else spec)
            if kept:
                groups[gname] = kept
        _set_mapping(cfg, "groups", groups)
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
        # patch_config edits a file someone else maintains: it writes what was
        # changed and nothing more. Completing the layers here would inject five
        # keys into a hand-kept config as a side effect of an unrelated edit.
        spec["layers"] = [{k: v for k, v in lay.items() if v not in (None, "")}
                          for lay in el.layers]
    return spec


def write_config(path, machine, optics=None) -> Path:
    """Patch the config at `path` in place and report whether anything changed."""
    path = Path(path)
    before = path.read_text()
    cfg = read_yaml_text(before)
    after = write_yaml_text(patch_config(cfg, machine, optics=optics))
    if after != before:
        path.write_text(after)
    return path
