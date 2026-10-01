"""The sampling a machine is computed on when its file states none.

A machine file read on its own carries its grid in a top-level `grid:` block.
When that block is absent, WIMBA does not refuse - the grid is a sampling choice,
not a property of the machine the way the energy is - but it uses ONE default,
defined here, and every place that reports or writes a grid reads it from here:
the loader that computes with it, the Console that states it, and Save Machine
that writes it into a machine built in the window.
"""
from __future__ import annotations

from copy import deepcopy

#: frequency in Hz, time in s; `log` spaces the frequency points logarithmically
DEFAULT_GRID = {
    "frequency": {"min": 1.0e5, "max": 1.0e10, "n": 200, "log": True},
    "time": {"min": 1.0e-12, "max": 5.0e-9, "n": 200},
}


def default_grid() -> dict:
    """A copy, so no caller can edit the default for everyone else."""
    return deepcopy(DEFAULT_GRID)


def describe(grid: dict) -> str:
    """One line for the Console: what is sampled, over which span, how densely."""
    parts = []
    f = (grid or {}).get("frequency")
    if f:
        spacing = "log" if f.get("log") else "linear"
        parts.append(f"f {float(f['min']):.3g}-{float(f['max']):.3g} Hz "
                     f"({int(f['n'])} {spacing} points)")
    t = (grid or {}).get("time")
    if t:
        parts.append(f"t {float(t['min']):.3g}-{float(t['max']):.3g} s "
                     f"({int(t['n'])} points)")
    return ", ".join(parts)
