"""Reader for a default-pipe configuration file, in the style of a pytlwall
chamber .cfg: [base_info] with the geometry, [layerN] sections with the full
electromagnetic parameter set, and an optional [boundary]. Deliberately NO beam
or optics information (beta, offsets, gamma): those belong to the machine.
"""
from __future__ import annotations

import configparser
from pathlib import Path

_LAYER_KEYS = {
    "type": ("type", str),
    "thick_m": ("thickness", str),      # kept as str so 'inf' passes through
    "sigmadc": ("sigma", float),
    "muinf_hz": ("muinf_Hz", float),
    "k_hz": ("k_Hz", str),
    "epsr": ("epsr", float),
    "tau": ("tau", float),
    "rq": ("RQ", float),
}
_FORBIDDEN = ("betax", "betay", "test_beam_shift", "gammarel")


def _layer_from(section) -> dict:
    lay = {}
    for cfg_key, (our_key, cast) in _LAYER_KEYS.items():
        if cfg_key in section:
            raw = section[cfg_key]
            lay[our_key] = raw if cast is str else cast(raw)
    if "thickness" in lay and str(lay["thickness"]).lower() != "inf":
        lay["thickness"] = float(lay["thickness"])
    return lay


def read_pipe_cfg(path) -> dict:
    """Parse a pipe .cfg into a WIMBA geometry dict
    {radius, shape, hor, ver, layers=[..., boundary]}."""
    parser = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
    read = parser.read(Path(path))
    if not read:
        raise FileNotFoundError(f"pipe config not found: {path}")

    base = parser["base_info"] if parser.has_section("base_info") else {}
    for key in _FORBIDDEN:
        if key in base:
            raise ValueError(
                f"'{key}' does not belong in a default-pipe config ({path}): "
                "beta/beam parameters are decided by the machine.")

    geometry = {
        "shape": base.get("chamber_shape", "CIRCULAR").upper(),
        "radius": float(base["pipe_radius_m"]) if "pipe_radius_m" in base else None,
        "hor": float(base["pipe_hor_m"]) if "pipe_hor_m" in base else None,
        "ver": float(base["pipe_ver_m"]) if "pipe_ver_m" in base else None,
        "name": base.get("component_name"),
    }
    if geometry["radius"] is None:
        geometry["radius"] = geometry["ver"] or geometry["hor"]
    if geometry["radius"] is None:
        raise ValueError(f"pipe config {path}: give pipe_radius_m "
                         "(or pipe_hor_m / pipe_ver_m).")

    layers = []
    n = int(parser["layers_info"].get("nbr_layers", 0)) if parser.has_section("layers_info") \
        else 0
    for i in range(n):
        sec = f"layer{i}"
        if not parser.has_section(sec):
            raise ValueError(f"pipe config {path}: [{sec}] declared but missing.")
        layers.append(_layer_from(parser[sec]))
    if parser.has_section("boundary"):
        b = _layer_from(parser["boundary"])
        b.setdefault("thickness", "inf")
        b["boundary"] = True
        layers.append(b)
    if not layers:
        raise ValueError(f"pipe config {path}: no layers defined.")
    geometry["layers"] = layers
    return geometry
