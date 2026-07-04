"""Load precomputed impedance/wake from files (the 'precalculated' bridge).

The data may come from any source (CST, a previous run, measurements); it is read
and interpolated onto the requested grid. `files` maps a WIMBA component name to a
path, e.g. {"ZLong": "TCP_ZLong.dat"}.
"""
from __future__ import annotations

import numpy as np

from ..io.tables import read_impedance, read_wake


def precalculated_impedance(freqs, files):
    freqs = np.asarray(freqs, dtype=float)
    out = {}
    for comp, path in files.items():
        xf, z = read_impedance(path)
        out[comp] = np.interp(freqs, xf, z.real) + 1j * np.interp(freqs, xf, z.imag)
    return out


def precalculated_wake(times, files):
    times = np.asarray(times, dtype=float)
    out = {}
    for comp, path in files.items():
        xt, w = read_wake(path)
        out[comp] = np.interp(times, xt, w)
    return out
