"""Column I/O for impedance and wake tables.

WIMBA writes plain `.dat`: impedance files have three columns (frequency, Re Z,
Im Z), wake files two (time, W), with a short `#` header recording columns and
units.

For reading, wider formats are accepted, because precalculated data arrives from
elsewhere: `.xlsx` and delimited text carrying many components in one file, as
pytlwall and WIMBA's own export write them. :func:`read_impedance_table` finds
the components in such a file by their column names.

Frequency units are read too, not assumed. WIMBA writes Hz, but published models
often do not: the FCC-ee impedance model
(https://github.com/ImpedanCEI/fcc_ee_IW_model) writes GHz, with the unit in a
`#` header line -- ``# Freq(GHz) Re(Z) Im(Z)``. Reading such a file as Hz is a
silent factor 1e9 in frequency, so the unit is taken from the header where it is
declared, can be given explicitly by the caller, and its absence on a file whose
frequencies look implausible in Hz raises rather than guessing.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

_Z_UNITS = {"z": "Ohm", "x": "Ohm/m", "y": "Ohm/m"}

#: Extensions read through pandas rather than numpy.
SPREADSHEET_SUFFIXES = (".xlsx", ".xlsm", ".xls")

#: Frequency unit -> multiplier into Hz.
FREQ_UNITS = {"hz": 1.0, "khz": 1e3, "mhz": 1e6, "ghz": 1e9, "thz": 1e12}

#: Time unit -> multiplier into seconds.
TIME_UNITS = {"s": 1.0, "sec": 1.0, "ms": 1e-3, "us": 1e-6, "\u00b5s": 1e-6,
              "ns": 1e-9, "ps": 1e-12, "fs": 1e-15}

# A unit in brackets or parentheses next to a frequency/time word, e.g.
# "Freq(GHz)", "frequency [Hz]", "f [MHz]", "time (ns)".
_RE_UNIT = re.compile(r"(?:freq\w*|f|time|t)\s*[\[(]\s*([A-Za-z\u00b5]+)\s*[\])]", re.I)

#: Below this, a frequency column labelled (or assumed) Hz is not credible for an
#: impedance table -- a whole ring's revolution frequency is already ~kHz.
_MIN_CREDIBLE_HZ = 1e6


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


def _header_lines(path, limit=5):
    """The leading ``#`` comment lines of a text file."""
    out = []
    try:
        with open(path, "r", errors="replace") as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue
                if not line.startswith("#"):
                    break
                out.append(line.lstrip("#").strip())
                if len(out) >= limit:
                    break
    except OSError:
        pass
    return out


def unit_scale(text, table=None):
    """Multiplier into the base unit for a column label, or None.

    ``unit_scale("Freq(GHz)")`` -> 1e9, ``unit_scale("frequency[Hz]")`` -> 1.0.
    """
    table = FREQ_UNITS if table is None else table
    m = _RE_UNIT.search(str(text or ""))
    if not m:
        return None
    return table.get(m.group(1).lower())


def declared_frequency_scale(path, columns=None):
    """Multiplier into Hz declared by a file, or None if it declares nothing.

    Looked for first in the frequency column's own name (spreadsheets and files
    with a header row), then in the leading ``#`` comment lines.
    """
    if columns:
        s = unit_scale(columns[0])
        if s is not None:
            return s
    for line in _header_lines(path):
        s = unit_scale(line)
        if s is not None:
            return s
    return None


def _resolve_frequency_scale(path, freqs, columns=None, freq_unit=None):
    """Decide the multiplier into Hz, and refuse to guess when it matters.

    Precedence: an explicit ``freq_unit`` from the caller, then whatever the file
    declares, then Hz. The last step is only taken when the numbers are
    consistent with Hz: a table topping out below ~1 MHz is far more likely to be
    in GHz or MHz than to be a real impedance spectrum, and reading it as Hz
    would be wrong by orders of magnitude without anything going visibly amiss.
    """
    if freq_unit is not None:
        key = str(freq_unit).strip().lower()
        if key not in FREQ_UNITS:
            raise ValueError(f"unknown frequency unit {freq_unit!r}; "
                             f"use one of {', '.join(sorted(FREQ_UNITS))}")
        return FREQ_UNITS[key]

    declared = declared_frequency_scale(path, columns)
    if declared is not None:
        return declared

    fmax = float(np.max(np.abs(freqs))) if len(freqs) else 0.0
    if 0.0 < fmax < _MIN_CREDIBLE_HZ:
        raise ValueError(
            f"{Path(path).name} declares no frequency unit and its frequencies "
            f"stop at {fmax:g}, which is not credible in Hz. WIMBA will not guess "
            f"-- give the unit, e.g. 'freq_unit: GHz' in the device config, or add "
            f"a header line such as '# Freq(GHz) Re(Z) Im(Z)'.")
    return 1.0


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
        # numpy could not read it: a header row, an odd separator, mixed columns.
        # pandas sorts all of that out, but it is an optional dependency - say so
        # rather than letting a bare ImportError surface from three frames down.
        try:
            import pandas as pd
        except ImportError as exc:
            raise ImportError(
                f"{path.name} is not a plain numeric table, and reading it needs "
                "pandas:\n    pip install pandas\n"
                'or install the extra:  pip install -e ".[spreadsheets]"') from exc
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


def read_impedance_table(path, freq_unit=None):
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
    freqs = data[:, 0] * _resolve_frequency_scale(path, data[:, 0], names, freq_unit)
    return {c: (freqs, data[:, ir] + 1j * data[:, ii])
            for c, (ir, ii) in comps.items()}


def read_impedance(path, component=None, freq_unit=None):
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
        except ValueError:
            d = None      # header present: fall through to the named path
        if d is not None:
            d = np.atleast_2d(d)
            scale = _resolve_frequency_scale(path, d[:, 0], None, freq_unit)
            return d[:, 0] * scale, d[:, 1] + 1j * d[:, 2]

    table = read_impedance_table(path, freq_unit=freq_unit)
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


def read_wake(path, time_unit=None):
    """Return (times, W), honouring a declared time unit.

    As for impedance, WIMBA writes seconds but imported wakes often come in ns
    or mm/c. A unit in the header (``# time(ns)  W``) or an explicit
    ``time_unit`` is applied; with neither, seconds are assumed, which is safe
    here because a wake in seconds has no implausible range to test against.
    """
    d = np.atleast_2d(np.loadtxt(path))
    if time_unit is not None:
        key = str(time_unit).strip().lower()
        if key not in TIME_UNITS:
            raise ValueError(f"unknown time unit {time_unit!r}; "
                             f"use one of {', '.join(sorted(TIME_UNITS))}")
        scale = TIME_UNITS[key]
    else:
        scale = 1.0
        for line in _header_lines(path):
            s = unit_scale(line, TIME_UNITS)
            if s is not None:
                scale = s
                break
    return d[:, 0] * scale, d[:, 1]
