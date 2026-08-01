"""Column I/O for impedance and wake tables.

WIMBA writes plain `.dat`: impedance files have three columns (frequency, Re Z,
Im Z), wake files two (time, W), with a short `#` header recording columns and
units.

For reading, wider formats are accepted, because precalculated data arrives from
elsewhere: `.xlsx` and delimited text carrying many components in one file, as
pytlwall and WIMBA's own export write them. :func:`read_impedance_table` finds
the components in such a file by their column names.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

_Z_UNITS = {"z": "Ohm", "x": "Ohm/m", "y": "Ohm/m"}

#: Extensions read through pandas rather than numpy.
SPREADSHEET_SUFFIXES = (".xlsx", ".xlsm", ".xls")


def write_impedance(path, freqs, Z, plane="z"):
    unit = _Z_UNITS.get(plane, "Ohm")
    header = (f"WIMBA impedance\n"
              f"columns: frequency[Hz]  Re(Z)[{unit}]  Im(Z)[{unit}]")
    Z = np.asarray(Z, dtype=complex)
    np.savetxt(path, np.column_stack([freqs, Z.real, Z.imag]),
               header=header, fmt="% .8e")


# Column-name patterns for the layouts we read. Both capture the component name.
_RE_PARTS = (
    # WIMBA export / generic:  Re(ZLong)   Im(ZLong)
    re.compile(r"^\s*(Re|Im)\s*\(\s*([A-Za-z0-9_+]+?)\s*\)\s*$", re.I),
    # pytlwall xlsx:  <name> ZLong real [Ohm]   <name> ZLong imag [Ohm]
    re.compile(r"^\s*(?:\S+\s+)?([A-Za-z0-9_+]+)\s+(real|imag)\b", re.I),
)


def _load_table(path):
    """Read a table into (column names, 2-D float array).

    Spreadsheets go through pandas; text files are read with numpy, falling
    back to pandas when the file has a header row numpy cannot parse.
    """
    path = Path(path)
    if path.suffix.lower() in SPREADSHEET_SUFFIXES:
        try:
            import pandas as pd
        except ImportError as exc:
            raise ImportError(
                f"reading {path.name} needs pandas and openpyxl:\n"
                "    pip install pandas openpyxl") from exc
        df = pd.read_excel(path)
        return [str(c) for c in df.columns], df.to_numpy(dtype=float)

    try:
        d = np.loadtxt(path)
        return None, np.atleast_2d(d)
    except ValueError:
        import pandas as pd
        df = pd.read_csv(path, sep=None, engine="python", comment="#")
        return [str(c) for c in df.columns], df.to_numpy(dtype=float)


def _components_from_columns(names):
    """Map component name -> (real column index, imaginary column index)."""
    found = {}
    for i, raw in enumerate(names or []):
        for pat in _RE_PARTS:
            m = pat.match(raw)
            if not m:
                continue
            a, b = m.group(1), m.group(2)
            part, comp = (a, b) if a.lower() in ("re", "im") else (b, a)
            part = "re" if part.lower().startswith("re") else "im"
            found.setdefault(comp, {})[part] = i
            break
    return {c: (v["re"], v["im"]) for c, v in found.items()
            if "re" in v and "im" in v}


def read_impedance_table(path):
    """Read every impedance component present in one file.

    Recognises ``Re(ZLong)``/``Im(ZLong)`` (WIMBA's export) and
    ``<name> ZLong real [Ohm]``/``... imag ...`` (pytlwall's xlsx). The first
    column is taken as the frequency.

    Args:
        path: an .xlsx, .csv or delimited text file with a header row.

    Returns:
        dict mapping component name to ``(freqs, Z)`` with Z complex.

    Raises:
        ValueError: no Re/Im column pair could be identified.
    """
    names, data = _load_table(path)
    comps = _components_from_columns(names)
    if not comps:
        raise ValueError(
            f"no impedance components found in {Path(path).name}. Expected "
            "column pairs like 'Re(ZLong)' and 'Im(ZLong)', or "
            "'<name> ZLong real [Ohm]' and '<name> ZLong imag [Ohm]'."
            + (f" Columns present: {', '.join(map(str, names[:6]))}..."
               if names else " The file has no header row."))
    freqs = data[:, 0]
    return {c: (freqs, data[:, ir] + 1j * data[:, ii])
            for c, (ir, ii) in comps.items()}


def read_impedance(path, component=None):
    """Return (freqs, Z) for one component.

    A three-column file is read positionally, as WIMBA writes it. A file with
    named columns -- a spreadsheet, or text with a header -- is searched for
    ``component``; with several components present and none named, which one to
    take would be a guess, so it is an error.
    """
    path = Path(path)
    if path.suffix.lower() not in SPREADSHEET_SUFFIXES:
        try:
            d = np.loadtxt(path)
            return d[:, 0], d[:, 1] + 1j * d[:, 2]
        except ValueError:
            pass          # header present: fall through to the named path

    table = read_impedance_table(path)
    if component and component in table:
        return table[component]
    if len(table) == 1:
        return next(iter(table.values()))
    raise ValueError(
        f"{path.name} holds several components ({', '.join(sorted(table))}); "
        "say which one to read.")


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
