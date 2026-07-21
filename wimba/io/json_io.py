"""Readers for the pywit/LHC-model JSON data files.

These just load the JSON and expose it in a predictable shape; normalisation into
WIMBA terms happens where the data is used.
"""
from __future__ import annotations

import json
from pathlib import Path


def read_collimators(path) -> dict:
    """name -> {halfgap, length, layers, ...}."""
    return json.loads(Path(path).read_text())


def read_resonators(path) -> dict:
    """{name, length, modes:[{Rl,Ql,fl, Rxd,Qxd,fxd, Ryd,Qyd,fyd}, ...]}."""
    return json.loads(Path(path).read_text())


_PIPE_FORBIDDEN = ("betax", "betay", "beta_x", "beta_y", "gamma", "gammarel",
                   "test_beam_shift")


def read_pipe(path) -> dict:
    """Default-pipe description from a machine-data JSON: geometry + wall
    build-up (layers with the full electromagnetic parameter set). Beam/optics
    keys are rejected: the machine decides those. WIMBA builds the pytlwall
    input itself from this data."""
    data = json.loads(Path(path).read_text())
    for key in _PIPE_FORBIDDEN:
        if key in data:
            raise ValueError(
                f"'{key}' does not belong in a pipe JSON ({path}): beam/optics "
                "parameters are decided by the machine.")
    geometry = {
        "name": data.get("name"),
        "shape": str(data.get("shape", "CIRCULAR")).upper(),
        "radius": data.get("radius_m"),
        "hor": data.get("hor_m"),
        "ver": data.get("ver_m"),
        "layers": data.get("layers") or [],
    }
    if geometry["radius"] is None:
        geometry["radius"] = geometry["ver"] or geometry["hor"]
    if geometry["radius"] is None:
        raise ValueError(f"pipe JSON {path}: give radius_m (or hor_m / ver_m).")
    if not geometry["layers"]:
        raise ValueError(f"pipe JSON {path}: no layers defined.")
    return geometry
