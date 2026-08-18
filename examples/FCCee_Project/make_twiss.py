#!/usr/bin/env python3
"""Generate a MAD-X style TFS twiss table from an acc-models FCC-ee lattice.

WHY THIS SCRIPT EXISTS
----------------------
WIMBA needs beta functions and element lengths along the ring: every impedance
is weighted by the local beta, and every lattice row without a named device
becomes a segment of the default resistive wall. That information comes from a
twiss table.

The acc-models FCC-ee release does not contain one. It ships the *lattice* in
three equivalent forms -- ``lattices/<stage>/fccee_<stage>.madx`` (a MAD-X
sequence), ``fccee_<stage>.json`` (an xsuite line) and
``fccee_<stage>_lattice.py`` (the same line as python) -- but no computed
optics. The MAD-X file cannot even produce one on its own: it is a bare
``sequence ... endsequence`` with the strength definitions, and carries no
``beam``, no ``use`` and no ``twiss`` command, so MAD-X has no particle, no
energy and no active sequence to work with. The release's own
``tests/test_twiss.py`` and ``requirements.txt`` confirm the intended route is
xsuite (with cpymad only as one of three equivalent loaders).

So the optics has to be computed once, outside WIMBA, and handed to it as a
file. That is what this script does.

WHY IT IS NOT PART OF THE WIMBA PACKAGE
---------------------------------------
Two reasons, both deliberate:

1. WIMBA reads optics, it does not compute them. Adding a lattice-tracking code
   to the dependency chain of an impedance tool would make every user install
   xsuite to compute a resistive wall.
2. ``tests/test_config_file.py`` walks every import under ``wimba/`` with ``ast``
   and fails on anything not declared in pyproject.toml. An ``import xtrack``
   inside the package would have to be declared as a dependency -- see point 1.

Living under ``examples/`` keeps it runnable and versioned without either
consequence.

WHAT IT READS
-------------
``<acc-models-root>/lattices/<stage>/fccee_<stage>.json`` -- the xsuite line.
The JSON is preferred over the MAD-X file because it carries ``particle_ref``:
the reference particle with its mass, charge and gamma0. For the Z stage that is
pdg_id -11 (POSITRON, the ring is named ``fccee_p_ring``), mass0 510998.95 eV,
gamma0 89236.97397029876 -- which matches the official parameter table exactly.
Nothing has to be inferred or assumed about the beam.

Stages are ``z`` (45.6 GeV), ``w`` (80), ``h`` (120), ``t`` (ttbar, 182.5).

WHAT IT WRITES
--------------
A TFS file with a MAD-X-style ``@`` header (PARTICLE, MASS, ENERGY, PC, GAMMA,
BETA, LENGTH, Q1, Q2, ALFA) and the columns WIMBA needs (NAME, KEYWORD, S, L,
BETX, BETY, ALFX, ALFY, DX, DY, MUX, MUY, X, Y, ANGLE, K1L).

The header matters as much as the table: ``wimba.io.accmodels.check_optics``
cross-checks GAMMA and ENERGY there against the acc-models parameter table and
against the beam of the scenario about to use the file, which is what catches
an optics file paired with the wrong energy.

THREE CONVENTIONS, EACH CHOSEN FOR A REASON
-------------------------------------------
1. Values at the element EXIT. MAD-X reports twiss quantities at the downstream
   end of each element; xsuite reports them at the upstream end and appends a
   final ``_end_point`` row. Row i of the output therefore takes its optics from
   twiss row i+1. Getting this backwards shifts every beta by one element --
   which no check would catch, because the numbers stay perfectly plausible.

2. Unique element names. In the xsuite line the arc drifts are shared instances:
   11275 of the 30080 rows of the Z lattice carry only 87 distinct names,
   covering 11944 m of the 90660 m ring. A table keyed by name -- which is what
   WIMBA's reader is, because that is how devices are matched to the lattice --
   would collapse those into 87 rows and quietly lose 13% of the circumference
   from the default pipe. Repeats get a ``.2``, ``.3``, ... suffix, as MAD-X
   would have numbered them itself.

3. Fields separated by an explicit space, never by column padding alone. An
   element name longer than the column width otherwise touches the next field,
   and every reader that splits on whitespace shifts that whole row by one
   column. The symptom is subtle: negative beta functions and a total length a
   few percent off, on 16 rows out of 30080.

USAGE
-----
    python make_twiss.py <acc-models-root> <stage> -o <out.tfs>

    # e.g. straight into the folder the WIMBA configs point at:
    python make_twiss.py ~/CERN/acc-models-fcc-ee z \
        -o ~/CERN/impedance/externalData/FCCee_data/fccee_z_twiss.tfs

Requires xsuite (``pip install xsuite``), as does the acc-models release itself.
Takes about 15 s per stage; the output is roughly 10 MB.

VERIFYING THE RESULT
--------------------
The script prints the tunes and gamma, which should match
``<root>/parameter_tables/<stage>_parameter_table.txt``, and the closure
``|sum(L) - S_end|``, which should be at the 1e-8 m level. For a full check
against the parameter table and a scenario beam::

    from wimba.io.accmodels import check_stage, beam_from_twiss
    rep = check_stage(root, "z", "fccee_z_twiss.tfs",
                      beam=beam_from_twiss("fccee_z_twiss.tfs"))
    print(rep.text())
"""
from __future__ import annotations

import argparse
import collections
from pathlib import Path

import numpy as np
import xtrack as xt

STAGES = {"z": "fccee_z", "w": "fccee_w", "h": "fccee_h", "t": "fccee_t"}

# element_type -> MAD-X KEYWORD
KEYWORD = {
    "Drift": "DRIFT", "RBend": "RBEND", "Bend": "SBEND",
    "Quadrupole": "QUADRUPOLE", "Sextupole": "SEXTUPOLE",
    "Octupole": "OCTUPOLE", "Multipole": "MULTIPOLE",
    "Marker": "MARKER", "Cavity": "RFCAVITY", "Solenoid": "SOLENOID",
}

PARTICLE_BY_PDG = {11: ("ELECTRON", -1.0), -11: ("POSITRON", 1.0),
                   2212: ("PROTON", 1.0), -2212: ("ANTIPROTON", -1.0)}

COLUMNS = ["NAME", "KEYWORD", "S", "L", "BETX", "BETY", "ALFX", "ALFY",
           "DX", "DY", "MUX", "MUY", "X", "Y", "ANGLE", "K1L"]
FORMATS = ["%s"] + ["%s"] + ["%le"] * 14


def unique_names(names):
    """MAD-X-like disambiguation: first occurrence keeps the name."""
    seen = collections.Counter(names)
    used = collections.Counter()
    out = []
    for n in names:
        if seen[n] == 1:
            out.append(n)
            continue
        used[n] += 1
        out.append(n if used[n] == 1 else f"{n}.{used[n]}")
    return out


def load_stage(root: Path, stage: str):
    name = STAGES[stage]
    env = xt.load(root / "lattices" / stage / f"{name}.json")
    line = env[list(env.lines.keys())[0]] if hasattr(env, "lines") else env.fccee_p_ring
    return line


def build_rows(line):
    tw = line.twiss4d()
    tt = line.get_table(attr=True)
    n = len(line.element_names)

    names = unique_names(list(line.element_names))
    keyword = [KEYWORD.get(str(t), str(t).upper()) for t in np.array(tt.element_type)[:n]]
    length = np.array(tt.length, dtype=float)[:n]
    angle = np.array(tt.angle, dtype=float)[:n] if "angle" in tt._col_names else np.zeros(n)

    def exit_of(col):
        """Value at element exit: xsuite reports at entry, so shift by one."""
        v = np.array(getattr(tw, col), dtype=float)
        return v[1:n + 1]

    cols = {
        "NAME": names, "KEYWORD": keyword,
        "S": exit_of("s"), "L": length,
        "BETX": exit_of("betx"), "BETY": exit_of("bety"),
        "ALFX": exit_of("alfx"), "ALFY": exit_of("alfy"),
        "DX": exit_of("dx"), "DY": exit_of("dy"),
        "MUX": exit_of("mux"), "MUY": exit_of("muy"),
        "X": exit_of("x"), "Y": exit_of("y"),
        "ANGLE": angle, "K1L": np.zeros(n),
    }
    return tw, tt, cols, n


def write_tfs(path: Path, line, tw, cols, n, stage: str, seq_name: str) -> Path:
    p = line.particle_ref
    pdg = int(p.pdg_id[0])
    pname, charge = PARTICLE_BY_PDG.get(pdg, (f"PDG{pdg}", 1.0))
    mass_gev = float(p.mass0) / 1e9
    pc_gev = float(p.p0c[0]) / 1e9
    energy_gev = float(p.energy0[0]) / 1e9

    head = [
        ("NAME", "%05s", '"TWISS"'),
        ("TYPE", "%05s", '"TWISS"'),
        ("SEQUENCE", "%s", f'"{seq_name.upper()}"'),
        ("ORIGIN", "%s", '"xsuite/xtrack twiss4d via make_twiss.py"'),
        ("STAGE", "%s", f'"{stage}"'),
        ("PARTICLE", "%s", f'"{pname}"'),
        ("MASS", "%le", f"{mass_gev:.12g}"),
        ("CHARGE", "%le", f"{charge:.0f}"),
        ("ENERGY", "%le", f"{energy_gev:.12g}"),
        ("PC", "%le", f"{pc_gev:.12g}"),
        ("GAMMA", "%le", f"{float(p.gamma0[0]):.12g}"),
        ("BETA", "%le", f"{float(p.beta0[0]):.16g}"),
        ("LENGTH", "%le", f"{float(cols['S'][-1]):.12g}"),
        ("Q1", "%le", f"{float(tw.qx):.12g}"),
        ("Q2", "%le", f"{float(tw.qy):.12g}"),
        ("ALFA", "%le", f"{float(tw.momentum_compaction_factor):.12g}"),
    ]

    # Fields are joined with an explicit single space, never by padding alone:
    # a name longer than the column width would otherwise touch the next field
    # and every reader that splits on whitespace would shift a whole row.
    w = 21

    def row(prefix, cells):
        return prefix + " ".join(f"{c:<{w}s}" for c in cells).rstrip() + "\n"

    with open(path, "w") as fh:
        for k, f, v in head:
            fh.write(f"@ {k:<18s} {f:<5s} {v}\n")
        fh.write(row("* ", COLUMNS))
        fh.write(row("$ ", FORMATS))
        for i in range(n):
            cells = []
            for c in COLUMNS:
                v = cols[c][i]
                cells.append(f'"{v}"' if isinstance(v, str) else f"{float(v):.12g}")
            fh.write(row("  ", cells))
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path, help="acc-models-fcc-ee release root")
    ap.add_argument("stage", choices=sorted(STAGES))
    ap.add_argument("-o", "--out", type=Path, default=None)
    args = ap.parse_args()

    line = load_stage(args.root, args.stage)
    tw, tt, cols, n = build_rows(line)
    out = args.out or Path(f"fccee_{args.stage}_twiss.tfs")
    write_tfs(out, line, tw, cols, n, args.stage, "fccee_p_ring")

    sum_l = float(np.sum(cols["L"]))
    print(f"[{args.stage}] rows={n}  sum(L)={sum_l:.6f} m  S_end={cols['S'][-1]:.6f} m  "
          f"closure={abs(sum_l - cols['S'][-1]):.2e} m")
    print(f"[{args.stage}] gamma={float(line.particle_ref.gamma0[0]):.6f}  "
          f"qx={tw.qx:.5f} qy={tw.qy:.5f}  -> {out}")


if __name__ == "__main__":
    main()
