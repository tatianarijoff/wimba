"""Build a scenario from a YAML config that *coordinates* input files.

The config says where to find things - the MAD-X optics file, per-element source
files (pytlwall cfg, tabulated impedances) - so the same information is never
written twice. Optics (position, length, beta) come from the MAD-X twiss, matched
by element name; the config only adds what MAD-X doesn't know (the source and any
device-specific info).

Two levels live here:

  * a `Scenario` is one computable case: a machine plus the beam it is computed
    with (and, later, its own optics file). Two scenarios of the same project may
    differ in gamma, in optics, or in which elements they contain.
  * a `Project` is the container: it owns the frequency and time grids, the
    output root, and the list of scenarios. The grids belong here and *not* to a
    scenario, because comparing two scenarios only means something when they were
    sampled on the same grid.

`Project` used to be what `Scenario` is now. `Project(name, machine, freqs, times)`
still works and wraps the machine in a single scenario, so existing callers and
`wimba build` keep running unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import yaml

from ..core.beam import Beam
from ..core.element import Element
from ..core.machine import Machine, TwissTable
from ..core.optics import Explicit, PreWeighted
from ..sources.resonator import Resonator, ResonatorProvider
from ..sources.table import TableProvider
from ..sources.pytlwall_bridge import ChamberProvider
from ..sources.iw2d_bridge import IW2DProvider
from . import madx


@dataclass
class Scenario:
    """One computable case: a machine and the beam it is computed with.

    `output` is a per-scenario sub-directory of the project's output root.
    `derived_from` records the scenario this one was duplicated from, so a
    comparison can say what actually changed between the two.

    The grids are not fields: they are read from the owning project, which is the
    single place they are defined.
    """
    name: str
    machine: Machine
    beam: Optional[object] = None          # a Beam; None until one is set
    output: Optional[str] = None
    derived_from: Optional[str] = None
    project: Optional["Project"] = field(default=None, repr=False, compare=False)

    @property
    def freqs(self):
        return self.project.freqs if self.project is not None else None

    @property
    def times(self):
        return self.project.times if self.project is not None else None


@dataclass
class Project:
    name: str
    scenarios: list = field(default_factory=list)
    freqs: Optional[np.ndarray] = None
    times: Optional[np.ndarray] = None
    out_dir: Optional[str] = None

    def __post_init__(self):
        # transitional: Project(name, machine, freqs, times) - the old signature -
        # still builds a valid single-scenario project.
        if isinstance(self.scenarios, Machine):
            self.scenarios = [Scenario(name=self.name, machine=self.scenarios)]
        elif self.scenarios is None:
            self.scenarios = []
        for sc in self.scenarios:
            sc.project = self

    # ---- scenario access ----
    def add(self, scenario: Scenario) -> Scenario:
        if any(s.name == scenario.name for s in self.scenarios):
            raise ValueError(f"scenario '{scenario.name}' already exists in this project")
        scenario.project = self
        self.scenarios.append(scenario)
        return scenario

    def scenario(self, name: str) -> Scenario:
        for s in self.scenarios:
            if s.name == name:
                return s
        raise KeyError(f"no scenario named '{name}' (have: "
                       f"{', '.join(s.name for s in self.scenarios) or 'none'})")

    @property
    def only(self) -> Scenario:
        """The single scenario, for the one-scenario case. Explicit error otherwise."""
        if len(self.scenarios) != 1:
            raise ValueError(f"this project holds {len(self.scenarios)} scenarios; "
                             "name the one you mean with project.scenario(<name>)")
        return self.scenarios[0]

    # ---- compatibility with the old single-machine Project ----
    @property
    def machine(self) -> Machine:
        return self.only.machine

    @property
    def output(self) -> Optional[str]:
        return self.only.output


def _build_resonator(el, base, beam):
    res = [Resonator(r["term"], float(r["Rs"]), float(r["Q"]), float(r["fr"]))
           for r in el["resonators"]]
    return ResonatorProvider(res)


def _build_table(el, base, beam):
    return TableProvider(str(base / el["file"]), term=el["term"],
                         origin=el.get("origin", "imported"),
                         quantity=el.get("quantity", "impedance"))


def _chamber_geom(el, base, beam):
    if "radius_m" in el:
        radius = float(el["radius_m"])
    elif "half_gap_mm" in el:
        radius = float(el["half_gap_mm"]) / 1000.0
    elif "radius" in el:
        radius = float(el["radius"])
    else:
        radius = 0.02
    def _axis(name):
        if f"{name}_m" in el:
            return float(el[f"{name}_m"])
        if f"{name}_mm" in el:
            return float(el[f"{name}_mm"]) / 1000.0
        return None
    return dict(radius_m=radius, layers=el.get("layers"),
                length_m=float(el.get("length", 1.0)),
                gamma=_element_gamma(el, beam),
                shape=el.get("shape", "CIRCULAR"), hor_m=_axis("hor"),
                ver_m=_axis("ver"),
                # read by the IW2D path only: pytlwall applies its own tables
                iw2d_yokoya=el.get("iw2d_yokoya"),
                # read by the pytlwall path only: IW2D's formalism has no
                # equivalent parameter
                test_beam_shift=el.get("test_beam_shift"))


def _build_pytlwall(el, base, beam):
    geom = _chamber_geom(el, base, beam)
    # The Yokoya factors are read by the IW2D path alone: pytlwall carries its
    # own tables and applies them itself, so handing it these would either be
    # ignored or - worse - applied twice.
    geom.pop("iw2d_yokoya", None)
    return ChamberProvider(space_charge=bool(el.get("space_charge", False)),
                           **geom)


def _build_iw2d(el, base, beam):
    geom = _chamber_geom(el, base, beam)
    # the mirror of the pytlwall case: IW2D's formalism has no test-beam shift
    geom.pop("test_beam_shift", None)
    return IW2DProvider(**geom)


SOURCE_BUILDERS = {
    "resonator": _build_resonator,
    "cst": _build_table,
    "table": _build_table,
    "pytlwall": _build_pytlwall,
    "iw2d": _build_iw2d,
}


def _grid(spec):
    if not spec:
        return None
    lo, hi, n = float(spec["min"]), float(spec["max"]), int(spec["n"])
    if spec.get("log"):
        return np.logspace(np.log10(lo), np.log10(hi), n)
    return np.linspace(lo, hi, n)


def _element_gamma(el, beam) -> float:
    """The gamma this element is solved at: its own if it declares one, otherwise
    the scenario's beam. There is no fallback value - a chamber computed at an
    unstated energy is not a result, and the old default of 7000 quietly turned
    every machine into the LHC."""
    if el.get("gamma") is not None:
        return float(el["gamma"])
    if beam is not None:
        return beam.gamma
    raise ValueError(
        f"element '{el.get('name')}' needs a relativistic gamma and none was given. "
        "Add a 'beam:' block to the config (e.g. beam: {particle: proton, gamma: 7461}) "
        "or a 'gamma:' on the element itself.")


def _provider(el, base, beam):
    source = el.get("source", "resonator")
    builder = SOURCE_BUILDERS.get(source)
    if builder is None:
        raise ValueError(f"element '{el.get('name')}' uses unknown source '{source}'. "
                         f"Known: {', '.join(sorted(SOURCE_BUILDERS))}.")
    return builder(el, base, beam)


def _element(el, base, twiss, beam=None):
    name = el["name"]
    row = twiss.get(name, {})
    pos = madx.get(row, "S", "POSITION")
    length = madx.get(row, "L", "LENGTH", default=el.get("length", 1.0))
    bx = madx.get(row, "BETX", "BETA_X")
    by = madx.get(row, "BETY", "BETA_Y")

    info = {"length": float(length) if length is not None else None}
    info.update(el.get("info", {}))

    if el.get("pre_weighted") or (bx is None and "beta_x" not in el):
        optics = PreWeighted()
        meta = {"position": pos, "beta_x": None, "beta_y": None,
                "info": {**info, "pre_weighted": True}}
    else:
        bx = float(el.get("beta_x", bx))
        by = float(el.get("beta_y", by))
        optics = Explicit(bx, by)
        meta = {"position": pos, "beta_x": bx, "beta_y": by, "info": info}

    return Element(name=name, category=el.get("category", "element"),
                   length=float(length) if length is not None else 1.0,
                   provider=_provider(el, base, beam), optics=optics, meta=meta)


def read_smooth_beta(data):
    """``smooth_beta:`` from a config, or None.

    The user's own average, typically R/Q from the tunes in smooth
    approximation. When present it wins over anything WIMBA could compute: it is
    stated on purpose, and a lattice average is only an estimate of the same
    thing.
    """
    block = data.get("smooth_beta")
    if block is None:
        return None
    if isinstance(block, (list, tuple)):
        return float(block[0]), float(block[1])
    if isinstance(block, dict):
        try:
            return float(block["x"]), float(block["y"])
        except KeyError:
            raise ValueError("smooth_beta: needs both x: and y: -- the two "
                             "planes have different tunes and so different "
                             "average betas.")
    raise ValueError("smooth_beta: expects {x: ..., y: ...}")


def resolve_beta_mean(data, twiss, machine=None):
    """The averages the transverse weights divide by, and where they came from.

    Returns ((mean_x, mean_y), source), in order of authority: ``smooth_beta:``
    stated in the config, then the length-weighted average over the twiss rows,
    then the same average over the machine's own elements, then 1.

    The third step matters: falling straight to 1 would weight elements by their
    bare beta again -- a hundred instead of about one -- which is exactly what
    the ratio exists to prevent. Averaging the elements is an estimate, and
    usually a high one since a model's elements are not a sample of the ring,
    but it is the right order of magnitude. Only a machine where nothing states
    a beta ends at 1, and there every ratio is 1 anyway.
    """
    stated = read_smooth_beta(data)
    if stated is not None:
        return stated, "smooth_beta"
    if twiss:
        mean = madx.mean_beta(twiss)
        if mean != (1.0, 1.0):
            return mean, "lattice"
    if machine is not None:
        mean = machine_mean_beta(machine)
        if mean != (1.0, 1.0):
            return mean, "elements"
    return (1.0, 1.0), "none"


def machine_mean_beta(machine) -> tuple:
    """Length-weighted average over the elements that carry an explicit beta."""
    sx = sy = total = 0.0
    elements = [el for g in machine.groups for el in g.elements] + list(machine.additional)
    for el in elements:
        bx, by = el.meta.get("beta_x"), el.meta.get("beta_y")
        if bx is None or by is None:
            continue
        length = float(el.length or 1.0)
        sx += float(bx) * length
        sy += float(by) * length
        total += length
    if total <= 0.0:
        return 1.0, 1.0
    return sx / total, sy / total


def _build_machine(data, base, beam=None) -> Machine:
    twiss = madx.read_twiss(base / data["optics"]) if data.get("optics") else {}
    # inline twiss (name -> [bx, by]) as a fallback / simple case
    for k, v in (data.get("twiss") or {}).items():
        twiss.setdefault(k, {"NAME": k, "BETX": float(v[0]), "BETY": float(v[1])})

    machine = Machine(twiss=TwissTable())  # optics carried per element (Explicit)
    for group_name, elements in (data.get("groups") or {}).items():
        group = machine.add_group(group_name)
        # `elements` is None for a group whose entries are all commented out - a
        # normal thing to write while a model is being built up, and not a reason
        # to refuse the file
        for el in (elements or []):
            group.add(_element(el, base, twiss, beam))
    for el in (data.get("additional") or []):
        machine.add_additional(_element(el, base, twiss, beam))
    # after the elements exist: they are the last fallback for the average
    machine.beta_mean, machine.beta_mean_source = resolve_beta_mean(data, twiss, machine)
    return machine


def read_beam(data) -> Optional[Beam]:
    """`beam:` block if there is one; a bare top-level `gamma:` is the old spelling
    and still reads, as a proton beam at that gamma."""
    if data.get("beam") is not None:
        return Beam.from_dict(data["beam"])
    if data.get("gamma") is not None:
        return Beam(mode="gamma", value=float(data["gamma"]))
    return None


def load_scenario(path, project: Optional[Project] = None) -> Scenario:
    """Read one machine YAML and return it as a scenario.

    With no project given, a single-scenario project is created around it so the
    scenario has the grids it needs; the project is reachable as `scenario.project`.
    """
    cfg_path = Path(path)
    data = yaml.safe_load(cfg_path.read_text()) or {}
    name = data.get("name", cfg_path.stem)
    beam = read_beam(data)
    scenario = Scenario(name=name, beam=beam,
                        machine=_build_machine(data, cfg_path.parent, beam),
                        output=data.get("output"))
    if project is not None:
        return project.add(scenario)

    grid = data.get("grid") or {}
    Project(name=name, scenarios=[scenario],
            freqs=_grid(grid.get("frequency") or grid.get("freq")),
            times=_grid(grid.get("time")))
    return scenario


def load_project(path) -> Project:
    """Read a project.

    A machine YAML (the `groups:` dialect) yields a project holding that one
    scenario, which is what this function has always returned in practice.
    """
    return load_scenario(path).project
