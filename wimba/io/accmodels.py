"""Reading an acc-models FCC-ee stage: parameter table + optics compatibility.

The acc-models FCC-ee release (https://gitlab.cern.ch/acc-models/fcc/acc-models-fcc-ee)
publishes one folder per operation mode -- z, w, h, t -- each holding the lattice
and a ``parameter_table.txt`` with the official machine and beam parameters. The
same tables are collected under ``parameter_tables/<stage>_parameter_table.txt``.

Two things are read here:

* ``read_parameter_table`` turns that fixed-width text table into values and units.
* ``beam_from_parameter_table`` turns the beam energy into a WIMBA :class:`Beam`.

and one thing is checked:

* ``check_optics`` compares a twiss table against the parameter table and, if
  given, against a machine or assembly config -- circumference, gamma, particle,
  the columns the assembly needs, and the traps that produce silently wrong
  numbers rather than an error.

The release ships NO pre-computed twiss table and its MAD-X file carries no BEAM
statement, so the twiss has to be produced first; see
``examples/FCCee_Project/make_twiss.py``. Nothing in this module imports xsuite
or cpymad: WIMBA reads optics, it does not compute them.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..builders import madx

STAGES = ("z", "w", "h", "t")

#: rows whose value is a "(horizontal, vertical)" pair
_PAIR = re.compile(r"^\((.+),(.+)\)$")

#: unit suffix -> multiplier into SI-ish base units used below
_SCALE = {"1E11": 1e11, "1.0E-6": 1e-6, "1E34 Hz/cm^2": 1e34}


@dataclass
class Parameter:
    """One row of a parameter table."""
    key: str
    raw: str
    unit: str = ""

    @property
    def value(self):
        """float, (float, float) for a pair, or the raw string."""
        m = _PAIR.match(self.raw)
        if m:
            try:
                return tuple(float(x) for x in m.groups())
            except ValueError:
                return self.raw
        try:
            return float(self.raw)
        except ValueError:
            return self.raw

    @property
    def scaled(self):
        """``value`` with the unit prefix folded in, where the unit encodes one."""
        v = self.value
        f = _SCALE.get(self.unit)
        if f is None or not isinstance(v, float):
            return v
        return v * f


@dataclass
class ParameterTable:
    """An acc-models parameter table, indexed by its (lower-cased) row label."""
    path: Optional[Path] = None
    rows: dict = field(default_factory=dict)

    def __contains__(self, key):
        return key.lower() in self.rows

    def __getitem__(self, key) -> Parameter:
        try:
            return self.rows[key.lower()]
        except KeyError:
            raise KeyError(f"no row '{key}' in {self.path or 'parameter table'}") from None

    def get(self, key, default=None):
        p = self.rows.get(key.lower())
        return default if p is None else p.value

    # -- the handful of rows other code actually asks for ------------------
    @property
    def mode(self) -> str:
        return str(self.get("mode", "")).strip()

    @property
    def energy_gev(self) -> float:
        """Beam energy [GeV]. The table labels the unit GeV/c^2; it is an energy."""
        return float(self["beam energy"].value)

    @property
    def circumference_m(self) -> float:
        return float(self["circumference"].value)

    @property
    def bunch_length_m(self) -> Optional[float]:
        """Natural bunch length [m] (the 'incl. BS' row is the one with
        beamstrahlung and is the relevant one for wake convolution)."""
        p = self.rows.get("bunch length incl. bs") or self.rows.get("bunch length")
        return None if p is None else float(p.value) * 1e-3

    @property
    def bunch_population(self) -> Optional[float]:
        p = self.rows.get("bunch population")
        return None if p is None else float(p.scaled)

    @property
    def tunes(self):
        v = self.get("transverse tune")
        return v if isinstance(v, tuple) else None


def read_parameter_table(path) -> ParameterTable:
    """Read ``parameter_table.txt`` from an acc-models FCC-ee stage.

    The file is a fixed-width three-column table: a free-text label, a value and
    a unit. Labels contain spaces and dots ('bunch length incl. BS'), so the
    split is done from the right on the last two whitespace-separated fields --
    and the unit column may be empty, which is why the header line is used to
    locate where it starts.
    """
    path = Path(path)
    lines = [ln.rstrip("\n") for ln in path.read_text().splitlines() if ln.strip()]
    if not lines:
        raise ValueError(f"{path} is empty")

    header = lines[0]
    if "value" not in header:
        raise ValueError(f"{path} does not look like an acc-models parameter table "
                         f"(no 'value' column in the first line)")
    # Both data columns are RIGHT-aligned on the end of their header word, and
    # the label column is left-aligned from 0. Splitting on the end of "value"
    # is therefore the only cut that works: the unit itself ("GeV/c^2", "cm, mm")
    # starts well before the "unit" header word.
    value_end = header.index("value") + len("value")

    rows = {}
    for ln in lines[1:]:
        left, unit = ln[:value_end].rstrip(), ln[value_end:].strip()
        if not left:
            continue
        if left.endswith(")"):
            # a "(horizontal, vertical)" pair: the value contains a space
            cut = left.rfind("(")
            label, value = left[:cut].rstrip(), left[cut:]
        elif " " in left.strip():
            label, value = left.rsplit(None, 1)
        else:
            label, value = left.strip(), ""
        if not label:
            continue
        rows[label.lower()] = Parameter(label.strip(), value.strip(), unit)
    return ParameterTable(path, rows)


def stage_parameter_table(root, stage: str) -> ParameterTable:
    """Read the parameter table of one stage from an acc-models release root."""
    root = Path(root)
    for candidate in (root / "parameter_tables" / f"{stage}_parameter_table.txt",
                      root / "lattices" / stage / "parameter_table.txt"):
        if candidate.exists():
            return read_parameter_table(candidate)
    raise FileNotFoundError(f"no parameter table for stage '{stage}' under {root}")


def beam_from_parameter_table(table: ParameterTable, particle: str = "positron"):
    """Build a WIMBA :class:`~wimba.core.beam.Beam` from the table's beam energy.

    The parameter table gives the energy per beam and not the particle: an FCC-ee
    stage is one energy for two rings, so the caller says which one. The ring in
    the acc-models lattice is ``fccee_p_ring`` (positrons), and the twiss written
    by ``make_twiss.py`` records PARTICLE in its header -- prefer
    :func:`beam_from_twiss` when a twiss table is at hand.
    """
    from ..core.beam import Beam
    # Beam's energy modes are in eV; the parameter table is in GeV.
    return Beam(particle=particle, mode="energy", value=table.energy_gev * 1e9)


def beam_from_twiss(twiss_path):
    """Build a :class:`Beam` from a TFS header (PARTICLE + ENERGY).

    Preferred over :func:`beam_from_parameter_table` when a twiss table exists:
    the header records the particle the optics was actually computed for, so the
    beam cannot end up disagreeing with the lattice.
    """
    from ..core.beam import Beam
    head = read_twiss_header(twiss_path)
    particle = str(head.get("PARTICLE", "")).strip().lower()
    energy = head.get("ENERGY")
    if not particle or not isinstance(energy, float):
        raise ValueError(f"{Path(twiss_path).name} has no PARTICLE/ENERGY header; "
                         f"give the beam explicitly")
    return Beam(particle=particle, mode="energy", value=energy * 1e9)


# ---------------------------------------------------------------------------
# compatibility check
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS = ("NAME", "S", "L", "BETX", "BETY")


@dataclass
class Report:
    """Outcome of :func:`check_optics`. Falsy when anything failed."""
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    facts: dict = field(default_factory=dict)

    def __bool__(self):
        return not self.errors

    def text(self) -> str:
        out = []
        for k, v in self.facts.items():
            out.append(f"  {k:<24s} {v}")
        for w in self.warnings:
            out.append(f"  WARNING  {w}")
        for e in self.errors:
            out.append(f"  ERROR    {e}")
        out.append("  -> " + ("compatible" if self else "NOT compatible"))
        return "\n".join(out)


def read_twiss_header(path) -> dict:
    """Read the ``@ KEY %fmt VALUE`` block of a TFS file.

    ``madx.read_twiss`` skips these lines, but the header is where the particle,
    the energy and the ring length live -- exactly what has to be checked against
    the parameter table and the scenario beam.
    """
    head = {}
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        if not line.startswith("@"):
            if line.startswith("*"):
                break
            continue
        parts = line[1:].split(None, 2)
        if len(parts) < 3:
            continue
        key, _fmt, val = parts
        val = val.strip().strip('"')
        try:
            head[key.upper()] = float(val)
        except ValueError:
            head[key.upper()] = val
    return head


def _gamma_of(energy_gev: float, mass_gev: float) -> float:
    return energy_gev / mass_gev


def check_optics(twiss_path, table: Optional[ParameterTable] = None,
                 beam=None, tol_rel: float = 1e-4,
                 cell_tol: float = 1e-3, devices=None) -> Report:
    """Check that a twiss table, a parameter table and a beam describe one machine.

    ``devices`` is an optional iterable of (name, position) pairs -- the devices a
    config places on the lattice -- checked for the two failure modes that do not
    raise: a position past the end of the ring, and a position that coincides with
    a lattice element boundary, where the beta interpolation silently returns the
    neighbouring magnet's value instead of the drift's.
    """
    rep = Report()
    twiss_path = Path(twiss_path)
    head = read_twiss_header(twiss_path)
    rows = madx.read_twiss(twiss_path)

    if not rows:
        rep.errors.append(f"{twiss_path.name} has no data rows")
        return rep

    first = next(iter(rows.values()))
    missing = [c for c in REQUIRED_COLUMNS
               if madx.get(first, c) is None and c != "NAME"]
    if missing:
        rep.errors.append(f"twiss is missing column(s) {', '.join(missing)}; "
                          f"the assembly needs {', '.join(REQUIRED_COLUMNS)}")

    # --- geometry: do the row lengths tile the ring? ----------------------
    s_vals = [float(madx.get(r, "S")) for r in rows.values() if madx.get(r, "S") is not None]
    l_sum = sum(float(madx.get(r, "L") or 0.0) for r in rows.values())
    s_end = max(s_vals) if s_vals else 0.0
    rep.facts["rows"] = len(rows)
    rep.facts["S at end [m]"] = f"{s_end:.6f}"
    rep.facts["sum of L [m]"] = f"{l_sum:.6f}"

    if s_end > 0 and abs(l_sum - s_end) > max(1e-6, tol_rel * s_end):
        rep.errors.append(
            f"element lengths sum to {l_sum:.3f} m but the ring ends at {s_end:.3f} m "
            f"({100 * (l_sum / s_end - 1):+.3f}%). A default pipe built from this table "
            f"would not cover the ring. Repeated element names are the usual cause: "
            f"the reader is keyed by name, so duplicates overwrite each other")

    L_head = head.get("LENGTH")
    if isinstance(L_head, float) and s_end > 0 and abs(L_head - s_end) > max(1e-6, tol_rel * s_end):
        rep.warnings.append(f"header LENGTH {L_head:.6f} m disagrees with the last S "
                            f"{s_end:.6f} m")

    # --- beta functions ---------------------------------------------------
    bx = [float(madx.get(r, "BETX")) for r in rows.values() if madx.get(r, "BETX") is not None]
    by = [float(madx.get(r, "BETY")) for r in rows.values() if madx.get(r, "BETY") is not None]
    for label, vals in (("BETX", bx), ("BETY", by)):
        if not vals:
            continue
        bad = [v for v in vals if not math.isfinite(v) or v <= 0.0]
        if bad:
            rep.errors.append(f"{len(bad)} row(s) have a non-positive or non-finite "
                              f"{label} (min {min(bad):.6g}); a column shift in the TFS "
                              f"file is the usual cause")
    if bx and by:
        rep.facts["betx [m]"] = f"{min(bx):.4g} .. {max(bx):.4g}"
        rep.facts["bety [m]"] = f"{min(by):.4g} .. {max(by):.4g}"

    # --- particle and energy ---------------------------------------------
    particle = head.get("PARTICLE")
    mass = head.get("MASS")
    gamma_head = head.get("GAMMA")
    if particle:
        rep.facts["particle (twiss)"] = particle
    if isinstance(gamma_head, float):
        rep.facts["gamma (twiss)"] = f"{gamma_head:.6f}"
    if isinstance(gamma_head, float) and isinstance(mass, float) and mass > 0:
        e_head = head.get("ENERGY")
        if isinstance(e_head, float):
            g = _gamma_of(e_head, mass)
            if abs(g - gamma_head) > 1e-3 * gamma_head:
                rep.warnings.append(f"twiss header is internally inconsistent: "
                                    f"ENERGY/MASS gives gamma {g:.3f}, header says "
                                    f"{gamma_head:.3f}")

    if table is not None:
        rep.facts["stage"] = table.mode or "?"
        rep.facts["energy (table) [GeV]"] = f"{table.energy_gev:g}"
        C = table.circumference_m
        if s_end > 0 and abs(C - s_end) > max(1e-3, tol_rel * C):
            rep.errors.append(f"parameter table circumference {C:.6f} m does not match "
                              f"the twiss ring length {s_end:.6f} m -- optics and "
                              f"parameter table are not the same stage")
        e_head = head.get("ENERGY")
        if isinstance(e_head, float) and abs(e_head - table.energy_gev) > 1e-3 * table.energy_gev:
            rep.errors.append(f"twiss header energy {e_head:g} GeV does not match the "
                              f"parameter table {table.energy_gev:g} GeV")
        tunes = table.tunes
        q1, q2 = head.get("Q1"), head.get("Q2")
        if tunes and isinstance(q1, float) and isinstance(q2, float):
            if abs(q1 - tunes[0]) > 1e-2 or abs(q2 - tunes[1]) > 1e-2:
                rep.warnings.append(f"tunes from the twiss ({q1:.3f}, {q2:.3f}) differ from "
                                    f"the parameter table ({tunes[0]:.3f}, {tunes[1]:.3f})")
            else:
                rep.facts["tunes"] = f"({q1:.5f}, {q2:.5f}) = table"

    if beam is not None:
        g_beam = float(getattr(beam, "gamma", beam))
        rep.facts["gamma (beam)"] = f"{g_beam:.6f}"
        if isinstance(gamma_head, float) and abs(g_beam - gamma_head) > 1e-4 * gamma_head:
            rep.errors.append(f"the scenario beam has gamma {g_beam:.4f} but the optics "
                              f"was computed at gamma {gamma_head:.4f}: the beta functions "
                              f"do not belong to this energy")
        pname = str(getattr(beam, "particle", "") or "")
        pname = getattr(pname, "name", pname)
        if particle and pname and str(particle).lower() != str(pname).lower():
            rep.warnings.append(f"twiss was computed for {particle}, the beam is {pname}")

    # --- device placement -------------------------------------------------
    for name, pos in (devices or []):
        if pos is None:
            continue
        pos = float(pos)
        if pos < 0 or pos > s_end:
            rep.errors.append(f"device '{name}' sits at s={pos:g} m, outside the ring "
                              f"(0 .. {s_end:.3f} m)")
            continue
        near = [nm for nm, r in rows.items()
                if madx.get(r, "S") is not None
                and abs(float(madx.get(r, "S")) - pos) <= cell_tol
                and float(madx.get(r, "L") or 0.0) > 0.0]
        if near:
            rep.warnings.append(
                f"device '{name}' at s={pos:g} m coincides with the end of "
                f"{', '.join(near[:3])}: the beta interpolation will return that "
                f"element's value, not the surrounding drift's. Nothing will error "
                f"-- move the device off the boundary")

    return rep


def check_stage(root, stage: str, twiss_path, beam=None, devices=None) -> Report:
    """``check_optics`` with the stage's own parameter table."""
    return check_optics(twiss_path, stage_parameter_table(root, stage),
                        beam=beam, devices=devices)
