"""Assemble a machine's impedance assignments from optics + device definitions.

Every lattice location gets an impedance assignment: either a user-defined device
(precalculated file, resonator, or a pytlwall/IW2D geometry) or the default
resistive wall applied per lattice row. Beta is resolved by position (interpolated
from the twiss), else by name, else the element is appended at the end of the
machine with an editable beta defaulting to 1.

The result is an array (one row per contribution) with position, name, how it is
computed, and beta - written to <name>_assignments.csv - plus collision detection
so that two contributions at the same position are reported (as an error unless
they are declared overlapping via allow_overlap).
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from .builders import madx

BASE_METHODS = ("pytlwall", "iw2d", "precalculated", "resonator")
#: The one method whose data can arrive already weighted. It is a method of its
#: own rather than a flag on another one, so "iw2d, already weighted" -- which
#: would mean WIMBA weighting its own numbers twice -- cannot be written at all.
WEIGHTED_METHOD = "precalculated_weighted"
METHODS = BASE_METHODS + (WEIGHTED_METHOD,)
DEFAULT_TOL = 1e-3   # metres


@dataclass
class Device:
    """A user-defined impedance contribution at a location."""
    name: str
    method: str = "pytlwall"          # one of BASE_METHODS
    weighted: bool = False            # True = result already beta-weighted
    space_charge: bool = False        # only meaningful for pytlwall
    position: Optional[float] = None  # explicit s [m]; else resolved by name
    beta: Optional[tuple] = None      # explicit (bx, by) override
    allow_overlap: bool = False
    length: Optional[float] = None
    geometry: Optional[dict] = None
    group: str = ""
    params: Optional[dict] = None


@dataclass
class DefaultPipe:
    """The default resistive wall applied to uncovered lattice rows (plain)."""
    method: str = "pytlwall"           # one of BASE_METHODS
    space_charge: bool = True          # ISC comes free from pytlwall; off only if asked
    weighted: bool = False            # default pipe is plain: beta applied by WIMBA
    geometry: Optional[dict] = None


@dataclass
class Assignment:
    position: Optional[float]
    name: str
    kind: str                          # "device" | "default_pipe"
    method: str
    weighted: bool
    space_charge: bool
    beta_x: float
    beta_y: float
    beta_source: str                   # "interp" | "name" | "explicit" | "default-1"
    allow_overlap: bool
    length: Optional[float] = None
    geometry: Optional[dict] = None
    group: str = ""
    params: Optional[dict] = None


@dataclass
class Collision:
    position: float
    names: list
    intentional: bool


@dataclass
class AssemblyResult:
    name: str
    rows: list = field(default_factory=list)
    collisions: list = field(default_factory=list)
    #: Assembly problems that are not collisions -- see :func:`unlocated_warnings`.
    warnings: list = field(default_factory=list)
    #: (mean_x, mean_y) every transverse weight is divided by, and where they
    #: came from: "smooth_beta" (stated by the user), "lattice" (averaged over
    #: the twiss rows) or "none" (no lattice: the bare beta is used).
    beta_mean: tuple = (1.0, 1.0)
    beta_mean_source: str = "none"


class _Beta:
    """Interpolates (beta_x, beta_y) at any s from the twiss points."""

    def __init__(self, twiss: dict):
        pts = []
        for row in twiss.values():
            s = madx.get(row, "S")
            bx = madx.get(row, "BETX")
            by = madx.get(row, "BETY")
            if s is not None and bx is not None:
                pts.append((float(s), float(bx), float(by if by is not None else bx)))
        pts.sort()
        self.ok = len(pts) > 0
        self.s = np.array([p[0] for p in pts]) if self.ok else np.array([])
        self.bx = np.array([p[1] for p in pts]) if self.ok else np.array([])
        self.by = np.array([p[2] for p in pts]) if self.ok else np.array([])

    def at(self, s):
        if not self.ok:
            return 1.0, 1.0
        return float(np.interp(s, self.s, self.bx)), float(np.interp(s, self.s, self.by))

    def end(self):
        return float(self.s[-1]) if self.ok else 0.0


def _resolve(dev: Device, twiss: dict, beta: _Beta, mean=(1.0, 1.0)):
    """Return (position, beta_x, beta_y, source) for a device.

    A device that cannot be placed is given the lattice average rather than a
    bare 1: not knowing where something sits is not the same as knowing it sits
    where beta is one metre, and the average makes its weight exactly 1 -- which
    is the honest reading of "somewhere in this ring".
    """
    if dev.beta is not None:
        pos = dev.position
        if pos is None and dev.name in twiss:
            pos = madx.get(twiss[dev.name], "S")
        return pos, float(dev.beta[0]), float(dev.beta[1]), "explicit"
    if dev.position is not None:
        bx, by = beta.at(dev.position)
        return float(dev.position), bx, by, "interp"
    if dev.name in twiss:
        s = float(madx.get(twiss[dev.name], "S"))
        bx, by = beta.at(s)
        return s, bx, by, "name"
    # not found anywhere: append at end of machine, weight 1 (editable)
    return None, float(mean[0]), float(mean[1]), "default-1"


def unlocated_warnings(rows):
    """Flag devices that were never located in the lattice AND need a beta.

    ``_resolve`` falls back to beta = 1 for a device it cannot place: no
    ``position:``, no explicit ``beta:``, and a name that is not in the twiss.
    That is legitimate for a *lumped* device whose data is already summed over
    the ring -- an imported impedance model publishes one file per device family,
    and there is no single place where all 2220 BPMs sit. Such a device carries
    ``weighted: true``, and the compute path multiplies by 1 by design.

    It is almost never legitimate for a device with ``weighted: false``, where
    WIMBA is supposed to apply the local beta and instead applies 1. Nothing
    fails, and the result stays plausible -- which is exactly why it has to be
    said out loud rather than left in the ``beta_source`` column for someone to
    notice.
    """
    out = []
    for r in rows:
        if r.kind == "default_pipe" or r.beta_source != "default-1" or r.weighted:
            continue
        out.append(
            f"device '{r.name}' was not found in the lattice (no position:, no "
            f"beta:, and the name is not a twiss element), so it was computed at "
            f"the average optics -- weight 1 -- instead of its own. Give it a "
            f"position: or an explicit beta:, or set weighted: ratio if its data "
            f"is already weighted by beta over the average, or is a ring total.")
    return out


def mean_warnings(rows, mean, source):
    """Say when the average is an estimate rather than the lattice's own.

    ``beta_mean = 1`` can no longer reinstate the bare-beta weighting: with no
    twiss the average falls back to the modelled elements, and it only stays 1
    when nothing states a beta at all -- in which case every ratio is 1 and
    there is nothing to warn about. What is worth saying is that the average
    came from the elements, since they are not a sample of the ring.
    """
    if source != "elements":
        return []
    return [f"no optics file and no smooth_beta:, so the average beta was "
            f"estimated from the modelled elements themselves "
            f"({mean[0]:.4g}, {mean[1]:.4g}) m. Devices sit where beta is large, "
            f"so this is usually an overestimate: state smooth_beta: {{x: ..., "
            f"y: ...}} from the tunes, or give an optics file."]


#: The (R, Q, f) key triples a resonator mode may carry, in the layout pywit
#: uses for HOMs: one longitudinal, two dipolar, two quadrupolar. A mode is a
#: resonance of the object, so the same mode may speak in several planes at
#: once; each triple it carries becomes one resonator in the compute path.
MODE_TRIPLES = (("Rl", "Ql", "fl"), ("Rxd", "Qxd", "fxd"), ("Ryd", "Qyd", "fyd"),
                ("Rxq", "Qxq", "fxq"), ("Ryq", "Qyq", "fyq"))


def read_modes(modes, owner: str) -> list:
    """Validate a resonator's modes and return them as plain dicts.

    Both routes into a resonator device come through here - the JSON file and
    the ``modes:`` written straight into the config - so a hand-written mode is
    checked exactly like an imported one.

    What is refused, and why it has to be refused here: the compute path adds a
    resonator for every triple whose R is set, then reads that triple's Q and f
    without looking. So ``{Rl: 5000}`` alone raises a KeyError somewhere in
    numpy, and ``{Rl: 5000, Ql: 0, fl: 1e9}`` divides by zero inside the damped
    frequency. Named here instead, while it is still obvious which mode of which
    device is at fault.
    """
    if isinstance(modes, dict):          # a single mode written without the list
        modes = [modes]
    if not modes:
        raise ValueError(
            f"resonator '{owner}' states no modes. A resonator is a mode "
            f"spectrum: give at least one, as Rs, Q and the resonant frequency "
            f"(keys {', '.join(k[0] for k in MODE_TRIPLES)} and their Q/f "
            f"partners), either under 'modes:' or in a JSON file.")
    out = []
    for i, mode in enumerate(modes, start=1):
        if not isinstance(mode, dict):
            raise ValueError(f"resonator '{owner}', mode {i}: expected a mapping "
                             f"of R/Q/f keys, got {type(mode).__name__}.")
        clean, planes = {}, 0
        for rk, qk, fk in MODE_TRIPLES:
            present = [k for k in (rk, qk, fk) if mode.get(k) is not None]
            if not present:
                continue
            missing = [k for k in (rk, qk, fk) if mode.get(k) is None]
            if missing:
                raise ValueError(
                    f"resonator '{owner}', mode {i}: {', '.join(present)} given "
                    f"without {', '.join(missing)}. A resonance needs all three "
                    f"of shunt impedance, quality factor and frequency.")
            q, f = float(mode[qk]), float(mode[fk])
            if q <= 0.0:
                raise ValueError(f"resonator '{owner}', mode {i}: {qk} = {q} is "
                                 f"not above zero.")
            if f <= 0.0:
                raise ValueError(f"resonator '{owner}', mode {i}: {fk} = {f} is "
                                 f"not above zero.")
            clean[rk], clean[qk], clean[fk] = float(mode[rk]), q, f
            planes += 1
        if not planes:
            raise ValueError(
                f"resonator '{owner}', mode {i}: no R/Q/f triple. Known keys: "
                + "; ".join("/".join(t) for t in MODE_TRIPLES) + ".")
        for extra in ("name", "note"):          # kept: they document the mode
            if mode.get(extra) is not None:
                clean[extra] = mode[extra]
        out.append(clean)
    return out


def read_method(spec: dict, name: str, default: str, source=None):
    """(method, already_weighted) from a device's ``source:``, ``method:`` and
    the older ``weighted:`` flag.

    ``method: precalculated_weighted`` says the imported numbers already carry
    the dimensionless beta over mean-beta weighting, so WIMBA applies nothing
    further. Every other method is computed by WIMBA, which does the weighting
    itself.

    ``source:`` has the last word on whether a device is imported data:
    ``source: precalculated`` forces the method whatever ``method:`` says, and
    without this the check below would read the *default* method -- pytlwall --
    and refuse a perfectly ordinary imported device.

    ``weighted: ratio`` (and the older ``weighted: true``) still reads, as the
    spelling that came before the method existed.
    """
    method = str(spec.get("method", default)).lower().strip()
    if str(source or "").lower().strip() == "precalculated":
        method = "precalculated"
    if str(source or "").lower().strip() in ("resonator", "resonators_json"):
        # same reasoning: the source says what the device *is*, so a resonator
        # written without a method: line must not inherit the default one and
        # be handed to a wall engine that has no geometry to solve.
        method = "resonator"
    flag = spec.get("weighted")

    if method == WEIGHTED_METHOD:
        if flag not in (None, True, False):
            pass                       # harmless duplication of the same claim
        return "precalculated", True

    if flag in (None, False):
        return method, False

    if isinstance(flag, str) and flag.strip().lower() not in ("ratio", "beta", "true"):
        raise ValueError(
            f"device '{name}': weighted: '{flag}' is not a value WIMBA knows. "
            f"Use method: {WEIGHTED_METHOD} when the data is already weighted by "
            f"beta over the average beta.")
    if method != "precalculated":
        raise ValueError(
            f"device '{name}': weighted: cannot apply to method '{method}'. "
            f"WIMBA weights what it computes itself, so this would weight it "
            f"twice. Only imported data can arrive already weighted -- "
            f"method: {WEIGHTED_METHOD}.")
    return "precalculated", True


def read_smooth_beta(cfg):
    """``smooth_beta:`` from an assembly config, or None."""
    block = cfg.get("smooth_beta")
    if block is None:
        return None
    if isinstance(block, (list, tuple)):
        return float(block[0]), float(block[1])
    if isinstance(block, dict):
        if "x" not in block or "y" not in block:
            raise ValueError("smooth_beta: needs both x: and y: -- the two "
                             "planes have different tunes and so different "
                             "average betas.")
        return float(block["x"]), float(block["y"])
    raise ValueError("smooth_beta: expects {x: ..., y: ...}")


def _collisions(rows, tol):
    placed = sorted((r for r in rows if r.position is not None and r.kind == "device"),
                    key=lambda r: r.position)
    groups = []
    for r in placed:
        if groups and abs(r.position - groups[-1][0]) <= tol:
            groups[-1][1].append(r)
        else:
            groups.append((r.position, [r]))
    out = []
    for pos, grp in groups:
        if len(grp) > 1:
            out.append(Collision(pos, [x.name for x in grp],
                                  all(x.allow_overlap for x in grp)))
    return out


def element_mean_beta(devices) -> tuple:
    """The average over the devices that state a beta, weighted by their length.

    The fallback when there is no lattice to average over. It is an estimate of
    the same quantity and usually a high one -- devices tend to sit where beta is
    large, and the elements of a model are not a sample of the ring -- so it is
    recorded as its own source rather than passed off as the lattice average. A
    twiss file, when there is one, wins.

    Better than falling back to 1: a beta_mean of one metre against local betas
    of a hundred reinstates the bare-beta weighting this whole change removes.
    """
    sx = sy = total = 0.0
    for dev in devices:
        if getattr(dev, "beta", None) is None:
            continue
        length = float(getattr(dev, "length", None) or 1.0)
        sx += float(dev.beta[0]) * length
        sy += float(dev.beta[1]) * length
        total += length
    if total <= 0.0:
        return 1.0, 1.0
    return sx / total, sy / total


def assemble(twiss: dict, devices, default_pipe: Optional[DefaultPipe],
             name="machine", tol=DEFAULT_TOL, smooth_beta=None) -> AssemblyResult:
    if smooth_beta is not None:
        mean, mean_src = (float(smooth_beta[0]), float(smooth_beta[1])), "smooth_beta"
    else:
        mean = madx.mean_beta(twiss)
        mean_src = "lattice"
        if mean == (1.0, 1.0):
            mean = element_mean_beta(devices)
            mean_src = "elements" if mean != (1.0, 1.0) else "none"
    beta = _Beta(twiss)
    rows = []
    claimed = set()

    for dev in devices:
        pos, bx, by, src = _resolve(dev, twiss, beta, mean)
        sc = bool(dev.space_charge and dev.method == "pytlwall")
        if dev.name in twiss:
            claimed.add(dev.name)
        if pos is not None:                       # claim twiss rows at this position
            for nm, row in twiss.items():
                s = madx.get(row, "S")
                if s is not None and abs(float(s) - pos) <= tol:
                    claimed.add(nm)
        rows.append(Assignment(pos, dev.name, "device", dev.method, dev.weighted,
                               sc, bx, by, src, dev.allow_overlap, dev.length,
                               dev.geometry, dev.group, dev.params))

    if default_pipe is not None:
        for nm, row in sorted(twiss.items(),
                              key=lambda kv: (madx.get(kv[1], "S") if madx.get(kv[1], "S") is not None else 0.0)):
            if nm in claimed:
                continue
            s = madx.get(row, "S")
            L = madx.get(row, "L")
            if s is None or not L or float(L) <= 0.0:
                continue
            s = float(s)
            bx, by = beta.at(s)
            sc = bool(default_pipe.space_charge and default_pipe.method == "pytlwall")
            rows.append(Assignment(s, nm, "default_pipe", default_pipe.method,
                                   default_pipe.weighted, sc, bx, by, "interp",
                                   False, float(L), default_pipe.geometry, "default_pipe"))

    return AssemblyResult(name, rows, _collisions(rows, tol),
                          unlocated_warnings(rows) + mean_warnings(rows, mean, mean_src),
                          mean, mean_src)


CSV_COLUMNS = ["position_s", "name", "kind", "method", "weighted", "space_charge",
               "beta_x", "beta_y", "beta_source", "allow_overlap", "length"]


def write_csv(result: AssemblyResult, path) -> Path:
    path = Path(path)
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_COLUMNS)
        for r in sorted(result.rows, key=lambda r: (r.position is None, r.position or 0.0)):
            w.writerow(["" if r.position is None else f"{r.position:.6g}",
                        r.name, r.kind, r.method, int(r.weighted), int(r.space_charge),
                        f"{r.beta_x:.6g}", f"{r.beta_y:.6g}", r.beta_source,
                        int(r.allow_overlap),
                        "" if r.length is None else f"{r.length:.6g}"])
    return path


def load_twiss(path) -> dict:
    return madx.read_twiss(path)


def _half_axis(spec, name):
    """Read a half-axis: <name>_m or <name>_mm; None if absent."""
    if f"{name}_m" in spec:
        return float(spec[f"{name}_m"])
    if f"{name}_mm" in spec:
        return float(spec[f"{name}_mm"]) / 1000.0
    return None


def load_assembly(path, tol=DEFAULT_TOL, cfg=None) -> AssemblyResult:
    """Build an assignment array from a YAML coordinator that references a MAD-X
    twiss, device JSONs, and a default pipe."""
    import yaml
    from .io.json_io import read_collimators, read_resonators

    from .errors import read_config_text

    cfg_path = Path(path)
    base = cfg_path.parent
    if cfg is None:
        cfg = yaml.safe_load(read_config_text(cfg_path, "assembly config")) or {}

    from .config import resolve_data_path

    def _data(reference, what="data file"):
        """Locate a file referenced by this config.

        Every reference in the config goes through here, not just the optics:
        device tables, collimator and resonator JSON, the default-pipe geometry.
        Data that ships with an example stays relative to the config, as before,
        because resolve_data_path falls back to `base`; data too large or too
        external to track -- an imported impedance model, a twiss -- is found via
        `data_dir:` without absolute paths in a committed file.
        """
        return resolve_data_path(reference, base, what=what,
                                 study_dirs=cfg.get("data_dir"))

    twiss = (madx.read_twiss(_data(cfg["optics"], "optics table"))
             if cfg.get("optics") else {})

    # user-defined materials (name -> sigma [S/m]) extend the built-in table
    from .materials import sigma_table
    user_mats = {str(k).lower(): float(v) for k, v in (cfg.get("materials") or {}).items()}
    # A study's own materials: block wins over the shipped catalogue, so a name
    # can be redefined for one machine without touching anyone else's.
    mat_table = {**sigma_table(), **user_mats}

    def _resolve_layers(layers, owner):
        unknown = []
        for lay in (layers or []):
            if str(lay.get("type", "")).upper() in ("V", "PEC", "PMC"):
                continue          # vacuum / perfect conductors: no sigma needed
            if lay.get("sigma") is None and lay.get("sigmaDC") is None:
                mat = lay.get("material")
                key = str(mat).lower() if mat is not None else None
                if key in mat_table:
                    lay["sigma"] = mat_table[key]
                else:
                    unknown.append(f"'{mat}' (in {owner})")
        return unknown

    unknown_materials = []
    devices = []
    for gname, spec in (cfg.get("devices") or {}).items():
        src = spec.get("source")
        from .config import default_method as _dm
        method, weighted = read_method(spec, gname, _dm(), src)
        sc = bool(spec.get("space_charge", method == "pytlwall"))
        overlap = bool(spec.get("allow_overlap", False))
        if src == "collimators_json":
            for name, geo in read_collimators(_data(spec["file"], "collimator file")).items():
                geometry = {"radius": geo.get("halfgap", 0.02),
                            "layers": geo.get("layers"),
                            "length": geo.get("length")}
                unknown_materials += _resolve_layers(geometry["layers"], name)
                devices.append(Device(name=name, method=method, weighted=weighted,
                                      space_charge=sc, allow_overlap=overlap,
                                      length=geo.get("length"), geometry=geometry, group=gname))
        elif src in ("resonator", "resonators_json"):
            # Two ways to say the same thing: a JSON file, which is how a
            # measured or simulated HOM table arrives, and `modes:` in the
            # config itself, which is how a couple of resonances written by
            # hand arrive. Both end in the same Device, so nothing downstream
            # can tell them apart.
            name = spec.get("name")
            length = spec.get("length_m", spec.get("length"))
            modes = spec.get("modes")
            if spec.get("file"):
                r = read_resonators(_data(spec["file"], "resonator file"))
                if modes:
                    raise ValueError(
                        f"resonator '{name or gname}' states both a file and "
                        f"its own modes:. Keep one - two mode lists for one "
                        f"device is a comparison, and a comparison is two "
                        f"devices.")
                modes = r.get("modes", [])
                name = name or r.get("name")
                length = length if length is not None else r.get("length")
            beta = None
            if "beta_x" in spec and "beta_y" in spec:
                beta = (float(spec["beta_x"]), float(spec["beta_y"]))
            devices.append(Device(name=name or "resonator", method=method,
                                  weighted=weighted, space_charge=sc,
                                  allow_overlap=overlap, length=length,
                                  position=spec.get("position"), beta=beta,
                                  group=gname,
                                  params={"modes": read_modes(modes, name or gname)}))
        elif src == "precalculated":
            files = {c: str(_data(f, "impedance table"))
                     for c, f in (spec.get("files") or {}).items()}
            wfiles = {c: str(_data(f, "wake table"))
                      for c, f in (spec.get("wake_files") or {}).items()}
            params = {"files": files, "wake_files": wfiles}
            # Units are read from each file's header when it declares one
            # (# Freq(GHz) ...); these keys override that, for files that don't.
            for key in ("freq_unit", "time_unit"):
                if spec.get(key):
                    params[key] = str(spec[key])
            if "map" in spec:
                params["map"] = str(_data(spec["map"], "import map"))
            devices.append(Device(name=spec.get("name", gname), method="precalculated",
                                  weighted=weighted, allow_overlap=overlap,
                                  length=spec.get("length_m"), position=spec.get("position"),
                                  group=gname, params=params))
        elif src == "chamber":
            if "radius_m" in spec:
                radius = float(spec["radius_m"])
            elif "radius_mm" in spec:
                radius = float(spec["radius_mm"]) / 1000.0
            else:
                radius = 0.02
            beta = None
            if "beta_x" in spec and "beta_y" in spec:
                beta = (float(spec["beta_x"]), float(spec["beta_y"]))
            geometry = {"radius": radius, "layers": spec.get("layers"),
                        "shape": spec.get("shape", "CIRCULAR"),
                        "hor": _half_axis(spec, "hor"), "ver": _half_axis(spec, "ver"),
                        # read by the IW2D path only; pytlwall has its own tables
                        "iw2d_yokoya": spec.get("iw2d_yokoya"),
                        # read by the pytlwall path only
                        "test_beam_shift": spec.get("test_beam_shift")}
            unknown_materials += _resolve_layers(geometry["layers"], spec.get("name", gname))
            devices.append(Device(name=spec.get("name", gname), method=method,
                                  weighted=weighted, space_charge=sc, allow_overlap=overlap,
                                  length=float(spec.get("length_m", 1.0)), beta=beta,
                                  position=spec.get("position"), geometry=geometry, group=gname))
        else:
            raise ValueError(f"unknown device source '{src}'")

    dp_spec = cfg.get("default_pipe")
    default_pipe = None
    if dp_spec:
        if "file" in dp_spec:
            from .io.json_io import read_pipe
            geometry = read_pipe(_data(dp_spec["file"], "default pipe geometry"))
        else:
            radius = dp_spec.get("radius_mm", 22.0) / 1000.0
            geometry = {"radius": radius,
                        "layers": dp_spec.get("layers")
                                  or [{"material": dp_spec.get("material", "stainless_steel"),
                                       "thickness": dp_spec.get("thickness_m", 0.002)}],
                        "shape": dp_spec.get("shape", "CIRCULAR"),
                        "hor": _half_axis(dp_spec, "hor"),
                        "ver": _half_axis(dp_spec, "ver"),
                        "iw2d_yokoya": dp_spec.get("iw2d_yokoya"),
                        "test_beam_shift": dp_spec.get("test_beam_shift")}
        unknown_materials += _resolve_layers(geometry.get("layers"), "default_pipe")
        from .config import default_method as _dm
        dp_method = str(dp_spec.get("method", _dm())).lower()
        default_pipe = DefaultPipe(method=dp_method,
                                   space_charge=bool(dp_spec.get("space_charge",
                                                                 dp_method == "pytlwall")),
                                   geometry=geometry)
    if unknown_materials:
        raise ValueError(
            "unknown materials with no conductivity on record: "
            + ", ".join(sorted(set(unknown_materials)))
            + ". Define them under 'materials:' in the config (name: sigma_S_per_m) "
              "or give the layer an explicit 'sigma'.")
    return assemble(twiss, devices, default_pipe, name=cfg.get("name", cfg_path.stem),
                    tol=tol, smooth_beta=read_smooth_beta(cfg))
