"""Reader for IW2D's own input files.

IW2D's command-line format is one parameter per line, description and value
separated by a tab. WIMBA does not compute through these files - it drives
IW2D's Python API directly - but the format is how an IW2D case is written
down and passed around, so being able to open one and get a WIMBA element out
of it is worth having.

Read against IW2D's own legacy reader (``IW2D/legacy/roundchamber.py``) rather
than against the prose in its README, because the reader is where the unit
conversions actually live:

====================================  ===========================
in the file                           to WIMBA
====================================  ===========================
inner radius, thickness [mm]          x 1e-3
relaxation time for resistivity [ps]  x 1e-12
relaxation frequency of perm. [MHz]   x 1e6
DC resistivity [Ohm.m]                sigma = 1 / rho
magnetic susceptibility               ``muinf_Hz``, unchanged
====================================  ===========================

The susceptibility is the one that used to be got wrong: pytlwall's
``muinf_Hz`` is already a susceptibility (``mur = 1 + muinf/(1 + j f/k)``), and
IW2D asks for the same quantity, so nothing is added or subtracted.

What this reader refuses rather than approximates is listed in
:func:`read_iw2d_input`.
"""
from __future__ import annotations

import math
from pathlib import Path

#: The five Yokoya factors of a circular chamber - long, xdip, ydip, xquad,
#: yquad. Anything else describes a non-circular chamber through an equivalent
#: round one, which WIMBA has no key for yet.
CIRCULAR_YOKOYA = (1.0, 1.0, 1.0, 0.0, 0.0)


def _parse(path) -> dict:
    """The file as a dict, keyed by the description text without its colon.

    Every non-blank line must contain a tab: that is IW2D's own rule, and it is
    why the format admits no comment lines.
    """
    text = Path(path).read_text()
    out = {}
    for n, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        if "\t" not in line:
            raise ValueError(
                f"{Path(path).name}, line {n}: no tab. IW2D's format needs a "
                f"tab between each parameter description and its value, and "
                f"has no comment lines - a line starting with # or ; is a "
                f"parse error, not a comment.")
        key, value = line.split("\t", 1)
        out[key.strip().rstrip(":").strip()] = value.strip()
    return out


def _number(raw, what):
    """A float, accepting IW2D's spelling of infinity."""
    if raw is None or raw == "":
        raise ValueError(f"{what} is missing.")
    if raw.strip().lower() in ("infinity", "inf", "+infinity"):
        return math.inf
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"{what} is not a number: {raw!r}") from None


def _get(data, key, what=None):
    if key not in data:
        raise ValueError(
            f"'{key}' is missing. IW2D matches parameters by their exact "
            f"description text, so a reworded line is an absent one.")
    return _number(data[key], what or key)


def _layer(data, i):
    """Layer i (1-based), in WIMBA's terms."""
    p = f"Layer {i} "
    rho = _get(data, p + "DC resistivity (Ohm.m)")
    thick = _get(data, p + "thickness in mm")
    lay = {"thickness": "inf" if math.isinf(thick) else thick * 1e-3}

    if math.isinf(rho):
        # infinite resistivity is IW2D's way of writing vacuum
        lay["type"] = "V"
        return lay

    lay["type"] = "CW"
    lay["sigma"] = 1.0 / rho
    lay["tau"] = _get(data, p + "relaxation time for resistivity (ps)") * 1e-12
    lay["epsr"] = _get(data, p + "real part of dielectric constant")
    lay["muinf_Hz"] = _get(data, p + "magnetic susceptibility")
    fmu = _get(data, p + "relaxation frequency of permeability (MHz)")
    lay["k_Hz"] = "inf" if math.isinf(fmu) else fmu * 1e6
    return lay


def _grid(data, notes):
    """WIMBA's frequency grid from IW2D's frequency *scan*.

    The file describes how to sample, not which points: two exponents, a mode,
    a number of points per decade, and optionally a refinement window. WIMBA
    holds a list of frequencies, so the scan is rebuilt as a logarithmic grid
    over the same range - the same thing that happens with a pytlwall cfg, and
    the reason two codes' output files never line up row by row.
    """
    if "start frequency exponent (10^) in Hz" not in data:
        return None
    fmin = _get(data, "start frequency exponent (10^) in Hz")
    fmax = _get(data, "stop frequency exponent (10^) in Hz")
    per_decade = _get(data, "Number of points per decade (for log)")

    mode = int(_get(data, "linear (1) or logarithmic (0) or both (2) "
                          "frequency scan"))
    if mode != 0:
        notes.append(
            "the file asks for a "
            + ("linear" if mode == 1 else "linear and logarithmic")
            + " frequency scan; WIMBA rebuilt it as a logarithmic grid over "
              "the same range, so the sampled points are not IW2D's.")
    if data.get("added frequencies [Hz]") or data.get("added frequencies (Hz)"):
        notes.append("the extra frequencies listed in the file were not kept: "
                     "WIMBA's grid is described by a range and a count.")

    n = int(round((fmax - fmin) * per_decade)) + 1
    return {"frequency": {"min": 10.0 ** fmin, "max": 10.0 ** fmax,
                          "n": n, "log": True}}


def _yokoya(data, notes):
    """The five factors, kept as they are written.

    They are not a property of the geometry but of the IW2D calculation: on a
    round solve they stand in for another shape. The file does not say which
    shape, so the element stays CIRCULAR and carries the factors - which is
    exactly what the file means.
    """
    raw = data.get("Yokoya factors long, xdip, ydip, xquad, yquad")
    if not raw:
        return None
    try:
        factors = [float(v) for v in raw.split()]
    except ValueError:
        raise ValueError(f"the Yokoya factors are not five numbers: {raw!r}") \
            from None
    if len(factors) != 5:
        raise ValueError(f"expected five Yokoya factors, got {len(factors)}.")
    if any(abs(a - b) > 1e-9 for a, b in zip(factors, CIRCULAR_YOKOYA)):
        notes.append(
            f"the file states Yokoya factors {factors}, not the circular set "
            f"{list(CIRCULAR_YOKOYA)}: it describes another shape through an "
            f"equivalent round chamber. They were kept as iw2d_yokoya and are "
            f"read by the IW2D path only.")
    return factors


def read_iw2d_input(path) -> dict:
    """One IW2D round-chamber input file, in WIMBA's terms.

    Returns the same shape as :func:`wimba.io.pytlwall_cfg.read_chamber_cfg`,
    plus ``notes``: geometry (with the layers innermost first and the last one
    marked as the boundary), betas, length, gamma and the frequency grid.

    Refused rather than approximated:

    * a **flat** chamber input. It carries a half gap, a top/bottom symmetry
      flag and a second stack of layers; WIMBA's element has one stack, so a
      flat file is a different problem, not a variant of this one.
    Reported through ``notes`` rather than refused: Yokoya factors other than
    the circular set (kept as ``iw2d_yokoya``), a scan mode WIMBA cannot
    reproduce point for point, and any explicitly added frequencies.
    """
    data = _parse(path)
    notes: list[str] = []

    flat_keys = [k for k in data if "half gap" in k.lower()
                 or "top bottom symmetry" in k.lower()
                 or "upper layers" in k.lower() or "lower layers" in k.lower()]
    if flat_keys:
        raise ValueError(
            "this is a flat-chamber input (it states "
            f"'{flat_keys[0]}'). WIMBA reads IW2D's round-chamber files; a "
            "flat one has a half gap and separate upper and lower layer "
            "stacks, which a WIMBA element cannot hold today.")

    n_layers = int(_get(data, "Number of layers"))
    if n_layers < 1:
        raise ValueError("the file declares no layers.")

    layers = [_layer(data, i) for i in range(1, n_layers + 1)]
    # IW2D's outermost layer is semi-infinite by construction, and that is
    # exactly WIMBA's boundary.
    layers[-1]["boundary"] = True
    if layers[-1].get("thickness") != "inf":
        notes.append("the outermost layer did not state an infinite thickness; "
                     "it is the boundary and was extended, as IW2D does.")
        layers[-1]["thickness"] = "inf"

    radius = _get(data, "Layer 1 inner radius in mm") * 1e-3
    geometry = {"name": data.get("Comments for the output files names", "").strip("_")
                        or data.get("Machine", "") or None,
                "shape": "CIRCULAR", "radius": radius,
                "hor": None, "ver": None, "layers": layers}

    factors = _yokoya(data, notes)
    if factors is not None:
        geometry["iw2d_yokoya"] = factors

    for key in ("Machine", "Comments for the output files names"):
        if data.get(key):
            notes.append(f"'{key}' is used by IW2D only to name its output "
                         f"files and has no effect here.")

    return {"geometry": geometry,
            "betax": 1.0, "betay": 1.0,
            "length": _get(data, "Impedance Length in m"),
            "gamma": _get(data, "Relativistic Gamma"),
            "grid": _grid(data, notes),
            "notes": notes}
