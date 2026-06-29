"""Plain column .dat I/O for impedance and wake tables.

Impedance files have three columns (frequency, Re Z, Im Z); wake files have two
(time, W). A short `#` header records the columns and units.
"""
from __future__ import annotations

import numpy as np

_Z_UNITS = {"z": "Ohm", "x": "Ohm/m", "y": "Ohm/m"}


def write_impedance(path, freqs, Z, plane="z"):
    unit = _Z_UNITS.get(plane, "Ohm")
    header = (f"WIMBA impedance\n"
              f"columns: frequency[Hz]  Re(Z)[{unit}]  Im(Z)[{unit}]")
    Z = np.asarray(Z, dtype=complex)
    np.savetxt(path, np.column_stack([freqs, Z.real, Z.imag]),
               header=header, fmt="% .8e")


def read_impedance(path):
    """Return (freqs, Z) with Z complex."""
    d = np.loadtxt(path)
    return d[:, 0], d[:, 1] + 1j * d[:, 2]


def write_wake(path, times, W, plane="z"):
    unit = "V/C" if plane == "z" else "V/C/m"
    header = (f"WIMBA wake\n"
              f"columns: time[s]  W[{unit}]")
    np.savetxt(path, np.column_stack([times, np.asarray(W, dtype=float)]),
               header=header, fmt="% .8e")


def read_wake(path):
    """Return (times, W)."""
    d = np.loadtxt(path)
    return d[:, 0], d[:, 1]
