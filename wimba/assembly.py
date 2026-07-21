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


def _resolve(dev: Device, twiss: dict, beta: _Beta):
    """Return (position, beta_x, beta_y, source) for a device."""
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
    # not found anywhere: append at end of machine, beta defaults to 1 (editable)
    return None, 1.0, 1.0, "default-1"


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


def assemble(twiss: dict, devices, default_pipe: Optional[DefaultPipe],
             name="machine", tol=DEFAULT_TOL) -> AssemblyResult:
    beta = _Beta(twiss)
    rows = []
    claimed = set()

    for dev in devices:
        pos, bx, by, src = _resolve(dev, twiss, beta)
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

    return AssemblyResult(name, rows, _collisions(rows, tol))


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

    cfg_path = Path(path)
    base = cfg_path.parent
    if cfg is None:
        cfg = yaml.safe_load(cfg_path.read_text()) or {}

    twiss = madx.read_twiss(base / cfg["optics"]) if cfg.get("optics") else {}

    # user-defined materials (name -> sigma [S/m]) extend the built-in table
    from .sources.pytlwall_bridge import MATERIALS
    user_mats = {str(k).lower(): float(v) for k, v in (cfg.get("materials") or {}).items()}
    mat_table = {**MATERIALS, **user_mats}

    def _resolve_layers(layers, owner):
        unknown = []
        for lay in (layers or []):
            if str(lay.get("type", "")).upper() == "V":
                continue                       # vacuum: no conductivity needed
            if "sigma" not in lay and "sigmaDC" not in lay:
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
        method = spec.get("method", "pytlwall")
        weighted = bool(spec.get("weighted", False))
        sc = bool(spec.get("space_charge", method == "pytlwall"))
        overlap = bool(spec.get("allow_overlap", False))
        if src == "collimators_json":
            for name, geo in read_collimators(base / spec["file"]).items():
                geometry = {"radius": geo.get("halfgap", 0.02),
                            "layers": geo.get("layers"),
                            "length": geo.get("length")}
                unknown_materials += _resolve_layers(geometry["layers"], name)
                devices.append(Device(name=name, method=method, weighted=weighted,
                                      space_charge=sc, allow_overlap=overlap,
                                      length=geo.get("length"), geometry=geometry, group=gname))
        elif src == "resonators_json":
            r = read_resonators(base / spec["file"])
            devices.append(Device(name=r.get("name", "resonator"), method=method,
                                  weighted=weighted, space_charge=sc,
                                  allow_overlap=overlap, length=r.get("length"),
                                  group=gname, params={"modes": r.get("modes", [])}))
        elif src == "precalculated":
            base_dir = cfg_path.parent
            files = {c: str(base_dir / f) for c, f in (spec.get("files") or {}).items()}
            wfiles = {c: str(base_dir / f) for c, f in (spec.get("wake_files") or {}).items()}
            devices.append(Device(name=spec.get("name", gname), method="precalculated",
                                  weighted=weighted, allow_overlap=overlap,
                                  length=spec.get("length_m"), position=spec.get("position"),
                                  group=gname, params={"files": files, "wake_files": wfiles}))
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
                        "hor": _half_axis(spec, "hor"), "ver": _half_axis(spec, "ver")}
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
            geometry = read_pipe(base / dp_spec["file"])
        else:
            radius = dp_spec.get("radius_mm", 22.0) / 1000.0
            geometry = {"radius": radius,
                        "layers": dp_spec.get("layers")
                                  or [{"material": dp_spec.get("material", "stainless_steel"),
                                       "thickness": dp_spec.get("thickness_m", 0.002)}],
                        "shape": dp_spec.get("shape", "CIRCULAR"),
                        "hor": _half_axis(dp_spec, "hor"), "ver": _half_axis(dp_spec, "ver")}
        unknown_materials += _resolve_layers(geometry.get("layers"), "default_pipe")
        dp_method = dp_spec.get("method", "pytlwall")
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
    return assemble(twiss, devices, default_pipe, name=cfg.get("name", cfg_path.stem), tol=tol)
