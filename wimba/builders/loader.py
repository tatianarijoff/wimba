"""Build a project from a YAML config that *coordinates* input files.

The config says where to find things - the MAD-X optics file, per-element source
files (pytlwall cfg, tabulated impedances) - so the same information is never
written twice. Optics (position, length, beta) come from the MAD-X twiss, matched
by element name; the config only adds what MAD-X doesn't know (the source and any
device-specific info).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import yaml

from ..core.element import Element
from ..core.machine import Machine, TwissTable
from ..core.optics import Explicit, PreWeighted
from ..sources.resonator import Resonator, ResonatorProvider
from ..sources.table import TableProvider
from ..sources.pytlwall_bridge import ChamberProvider
from ..sources.iw2d_bridge import IW2DProvider
from . import madx


@dataclass
class Project:
    name: str
    machine: Machine
    freqs: Optional[np.ndarray] = None
    times: Optional[np.ndarray] = None
    output: Optional[str] = None


def _build_resonator(el, base):
    res = [Resonator(r["term"], float(r["Rs"]), float(r["Q"]), float(r["fr"]))
           for r in el["resonators"]]
    return ResonatorProvider(res)


def _build_table(el, base):
    return TableProvider(str(base / el["file"]), term=el["term"],
                         origin=el.get("origin", "imported"),
                         quantity=el.get("quantity", "impedance"))


def _chamber_geom(el, base):
    if "radius_m" in el:
        radius = float(el["radius_m"])
    elif "half_gap_mm" in el:
        radius = float(el["half_gap_mm"]) / 1000.0
    elif "radius" in el:
        radius = float(el["radius"])
    else:
        radius = 0.02
    return dict(radius_m=radius, layers=el.get("layers"),
                length_m=float(el.get("length", 1.0)), gamma=float(el.get("gamma", 7000.0)))


def _build_pytlwall(el, base):
    return ChamberProvider(space_charge=bool(el.get("space_charge", False)),
                           **_chamber_geom(el, base))


def _build_iw2d(el, base):
    return IW2DProvider(**_chamber_geom(el, base))


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


def _provider(el, base):
    source = el.get("source", "resonator")
    builder = SOURCE_BUILDERS.get(source)
    if builder is None:
        raise ValueError(f"element '{el.get('name')}' uses unknown source '{source}'. "
                         f"Known: {', '.join(sorted(SOURCE_BUILDERS))}.")
    return builder(el, base)


def _element(el, base, twiss):
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
                   provider=_provider(el, base), optics=optics, meta=meta)


def load_project(path) -> Project:
    cfg_path = Path(path)
    base = cfg_path.parent
    data = yaml.safe_load(cfg_path.read_text()) or {}

    twiss = madx.read_twiss(base / data["optics"]) if data.get("optics") else {}
    # inline twiss (name -> [bx, by]) as a fallback / simple case
    for k, v in (data.get("twiss") or {}).items():
        twiss.setdefault(k, {"NAME": k, "BETX": float(v[0]), "BETY": float(v[1])})

    machine = Machine(twiss=TwissTable())  # optics carried per element (Explicit)
    for group_name, elements in (data.get("groups") or {}).items():
        group = machine.add_group(group_name)
        for el in elements:
            group.add(_element(el, base, twiss))
    for el in (data.get("additional") or []):
        machine.add_additional(_element(el, base, twiss))

    grid = data.get("grid") or {}
    freqs = _grid(grid.get("frequency") or grid.get("freq"))
    times = _grid(grid.get("time"))
    return Project(name=data.get("name", cfg_path.stem), machine=machine,
                   freqs=freqs, times=times, output=data.get("output"))
