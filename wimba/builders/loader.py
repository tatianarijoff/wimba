"""Build a Machine from a YAML config file (the configurator).

The config describes the optics and the elements, grouped by kind. Each element
names a source ("engine") that produces its impedance/wake terms. New engines
register in ``SOURCE_BUILDERS`` and become available in the config with no other
change.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml

from ..core.element import Element
from ..core.machine import Machine, TwissTable
from ..core.optics import Explicit, FromTwiss, PreWeighted
from ..sources.resonator import Resonator, ResonatorProvider


def _build_resonator(el):
    resonators = [Resonator(r["term"], float(r["Rs"]), float(r["Q"]), float(r["fr"]))
                  for r in el["resonators"]]
    return ResonatorProvider(resonators)


#: source name -> function(element_dict) -> ImpedanceProvider
SOURCE_BUILDERS = {
    "resonator": _build_resonator,
}


def _grid(spec):
    if not spec:
        return None
    lo, hi, n = float(spec["min"]), float(spec["max"]), int(spec["n"])
    if spec.get("log"):
        return np.logspace(np.log10(lo), np.log10(hi), n)
    return np.linspace(lo, hi, n)


def _optics(el):
    if el.get("pre_weighted"):
        return PreWeighted()
    if "beta_x" in el and "beta_y" in el:
        return Explicit(float(el["beta_x"]), float(el["beta_y"]))
    return FromTwiss(el.get("twiss_name"))


def _provider(el):
    source = el.get("source", "resonator")
    builder = SOURCE_BUILDERS.get(source)
    if builder is None:
        raise ValueError(
            f"element '{el.get('name')}' uses unknown source '{source}'. "
            f"Known sources: {', '.join(sorted(SOURCE_BUILDERS))}.")
    return builder(el)


def _element(el):
    return Element(name=el["name"],
                   category=el.get("category", "element"),
                   length=float(el.get("length", 1.0)),
                   provider=_provider(el),
                   optics=_optics(el))


def load_machine(path):
    """Read a YAML machine config. Returns (machine, freqs, times)."""
    data = yaml.safe_load(Path(path).read_text()) or {}
    twiss = TwissTable({k: (float(v[0]), float(v[1]))
                        for k, v in (data.get("twiss") or {}).items()})
    machine = Machine(twiss=twiss)
    for group_name, elements in (data.get("groups") or {}).items():
        group = machine.add_group(group_name)
        for el in elements:
            group.add(_element(el))
    for el in (data.get("additional") or []):
        machine.add_additional(_element(el))

    grid = data.get("grid") or {}
    return machine, _grid(grid.get("freq")), _grid(grid.get("time"))
