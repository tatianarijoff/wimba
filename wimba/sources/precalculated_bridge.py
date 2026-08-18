"""Load precomputed impedance/wake from files (the 'precalculated' bridge).

The data may come from any source (CST, a previous run, measurements); it is read
and interpolated onto the requested grid. `files` maps a WIMBA component name to a
path, e.g. {"ZLong": "TCP_ZLong.dat"}.

Frequency and time units are taken from the file when it declares them and can be
overridden per device with `freq_unit` / `time_unit`; see wimba.io.tables.
"""
from __future__ import annotations

import numpy as np

from ..io.tables import read_impedance, read_impedance_table, read_wake


def precalculated_impedance(freqs, files, freq_unit=None):
    """Interpolate precomputed impedances onto ``freqs``.

    ``files`` maps a component name to a path. The same path may appear for
    several components -- a spreadsheet or a WIMBA export holds them all -- in
    which case it is read once and the right column pair is taken for each.

    ``freq_unit`` overrides whatever the files declare; leave it None to let each
    file speak for itself.
    """
    freqs = np.asarray(freqs, dtype=float)
    out, tables = {}, {}
    for comp, path in files.items():
        key = str(path)
        if key not in tables:
            try:
                tables[key] = read_impedance_table(path, freq_unit=freq_unit)
            except (ValueError, OSError):
                tables[key] = None          # plain three-column file
        table = tables[key]
        if table is not None and comp in table:
            xf, z = table[comp]
        else:
            xf, z = read_impedance(path, component=comp, freq_unit=freq_unit)
        out[comp] = np.interp(freqs, xf, z.real) + 1j * np.interp(freqs, xf, z.imag)
    return out


def precalculated_components(path):
    """Component names available in one precalculated file, or () if it is a
    plain three-column table with nothing to choose from."""
    try:
        return tuple(sorted(read_impedance_table(path)))
    except (ValueError, OSError, ImportError):
        return ()


def precalculated_wake(times, files, time_unit=None):
    times = np.asarray(times, dtype=float)
    out = {}
    for comp, path in files.items():
        xt, w = read_wake(path, time_unit=time_unit)
        out[comp] = np.interp(times, xt, w)
    return out
