"""Reader for precalculated import descriptors.

A descriptor is a small YAML next to the data that says what is in which
columns of which files - so the Models table stays one line ("precalculated" +
the descriptor path) while the complexity lives here, readable and reusable.

Structure (columns are numbered from 1, as you read the file):

    common_impedance:            # defaults for every impedance component
      file: data.txt
      comment: "#"               # skip lines starting with this (default "#")
      skip_rows: 0               # additionally skip the first N lines
      sep: tab                   # tab | any literal string | omit = whitespace
      freq_unit: GHz             # Hz (default) | kHz | MHz | GHz | THz
      z_scale: 1.0               # optional multiplier (units / sign convention)
      format: re_im              # re_im (two columns) | complex (one column)
      columns: {freq: 1, re: 2, im: 3}     # numbered from 1
    components:                  # per-component entries; keys override common
      ZLong: {}
      ZDipX: {file: other.dat, columns: {freq: 1, re: 4, im: 5}}

    common_wake:                 # same idea for wakes (time_unit: s|ms|us|ns|ps,
      ...                        # w_scale, format, columns {time, w})
    wake_components:
      WLong: {...}

Data are taken as-is for the whole element (no length scaling; beta only if the
device is plain, applied by WIMBA downstream).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml

FREQ_UNIT = {"hz": 1.0, "khz": 1e3, "mhz": 1e6, "ghz": 1e9, "thz": 1e12}
TIME_UNIT = {"s": 1.0, "ms": 1e-3, "us": 1e-6, "ns": 1e-9, "ps": 1e-12}


def _sep_of(spec):
    sep = spec.get("sep")
    if sep is None:
        return None                      # any whitespace
    return "\t" if str(sep).lower() == "tab" else str(sep)


def _parse_complex(token: str) -> complex:
    t = token.strip().replace(" ", "")
    if t.startswith("(") and t.endswith(")") and "," in t:
        re_s, im_s = t[1:-1].split(",", 1)
        return complex(float(re_s), float(im_s))
    return complex(t.replace("i", "j"))


def _read_rows(path: Path, spec: dict):
    """Rows of a data file, as lists of string tokens.

    Spreadsheets are read through pandas and their cells turned into tokens, so
    the column-index machinery below works the same either way. Reading an
    .xlsx as text would feed the binary container to float().
    """
    from .tables import SPREADSHEET_SUFFIXES

    comment = spec.get("comment", "#")
    skip = int(spec.get("skip_rows", 0))
    sep = _sep_of(spec)

    if path.suffix.lower() in SPREADSHEET_SUFFIXES:
        try:
            import pandas as pd
        except ImportError as exc:
            raise ImportError(
                f"reading {path.name} needs pandas and openpyxl:\n"
                "    pip install pandas openpyxl") from exc
        df = pd.read_excel(path, skiprows=skip or None)
        rows = [[("" if v != v else str(v)) for v in row]      # v != v: NaN
                for row in df.itertuples(index=False, name=None)]
        if not rows:
            raise ValueError(f"{path}: the spreadsheet has no data rows.")
        return rows

    rows = []
    for i, raw in enumerate(path.read_text(errors="replace").splitlines()):
        if i < skip:
            continue
        line = raw.strip()
        if not line or (comment and line.startswith(comment)):
            continue
        rows.append(line.split(sep) if sep else line.split())
    if not rows:
        raise ValueError(f"{path}: no data rows found (comment='{comment}', "
                         f"skip_rows={skip}).")
    return rows


def _col(row, index_1based, path):
    i = int(index_1based) - 1
    if i < 0 or i >= len(row):
        raise ValueError(f"{path}: column {index_1based} not present "
                         f"(row has {len(row)} columns; columns are numbered from 1).")
    return row[i]


def _load_entry(base_dir: Path, common: dict, entry: dict, kind: str):
    spec = {**common, **(entry or {})}
    spec["columns"] = {**(common.get("columns") or {}), **((entry or {}).get("columns") or {})}
    if "file" not in spec:
        raise ValueError(f"import map: no 'file' for a {kind} component "
                         "(set it in the common block or the component entry).")
    path = base_dir / spec["file"]
    rows = _read_rows(path, spec)
    cols = spec["columns"]

    if kind == "impedance":
        x_key, unit = "freq", FREQ_UNIT[str(spec.get("freq_unit", "Hz")).lower()]
        scale = float(spec.get("z_scale", 1.0))
    else:
        x_key, unit = "time", TIME_UNIT[str(spec.get("time_unit", "s")).lower()]
        scale = float(spec.get("w_scale", 1.0))
    if x_key not in cols:
        raise ValueError(f"import map: columns.{x_key} missing "
                         "(columns are numbered from 1).")

    x, y = [], []
    fmt = str(spec.get("format", "re_im")).lower()
    for row in rows:
        x.append(float(_col(row, cols[x_key], path)) * unit)
        if kind == "wake":
            y.append(float(_col(row, cols.get("w", 2), path)) * scale)
        elif fmt == "complex":
            y.append(_parse_complex(_col(row, cols.get("z", 2), path)) * scale)
        elif fmt == "re_im":
            y.append(complex(float(_col(row, cols.get("re", 2), path)),
                             float(_col(row, cols.get("im", 3), path))) * scale)
        else:
            raise ValueError(f"import map: unknown format '{fmt}' (re_im | complex).")
    order = np.argsort(x)
    return np.asarray(x)[order], np.asarray(y)[order]


def check_x_column(x, path, kind, column):
    """Refuse an x column that cannot be a frequency or a time.

    The commonest mistake is off by one column, and the commonest reason is a
    spreadsheet written by ``DataFrame.to_excel`` without ``index=False``: the
    first column is then the row number, and a map that says ``freq: 1`` picks
    0, 1, 2, ... The values interpolate happily and the result is wrong in
    silence, which is why this is an error and not a warning.
    """
    x = np.asarray(x, dtype=float)
    what = "frequency" if kind == "impedance" else "time"
    name = Path(path).name

    if x.size == 0:
        raise ValueError(f"{name}: column {column} is empty.")
    if not np.all(np.isfinite(x)):
        raise ValueError(f"{name}: column {column} holds non-numeric values "
                         f"where a {what} was expected.")
    if np.any(np.diff(x) <= 0):
        raise ValueError(
            f"{name}: column {column} does not increase, so it cannot be a "
            f"{what}. Check the column numbers in the map - they count from 1.")
    if x[0] < 0:
        raise ValueError(f"{name}: column {column} starts below zero, so it "
                         f"cannot be a {what}.")
    if (x.size > 2 and x[0] == 0.0
            and np.allclose(x, np.arange(x.size), rtol=0, atol=1e-9)):
        raise ValueError(
            f"{name}: column {column} is 0, 1, 2, ... - a row number, not a "
            f"{what}. A spreadsheet written with pandas keeps the index unless "
            f"you pass index=False, which shifts every column by one: try "
            f"column {column + 1}, or rewrite the file with "
            f"df.to_excel(..., index=False).")


def load_import_map(path) -> dict:
    """Read a descriptor -> {"impedance": {comp: (x, z)}, "wake": {comp: (x, w)}}."""
    path = Path(path)
    data = yaml.safe_load(path.read_text()) or {}
    base = path.parent
    out = {"impedance": {}, "wake": {}}
    for comp, entry in (data.get("components") or {}).items():
        common = data.get("common_impedance") or {}
        x, z = _load_entry(base, common, entry, "impedance")
        check_x_column(x, base / (entry.get("file") or common.get("file", path.name)),
                       "impedance",
                       int((entry.get("columns") or common.get("columns")
                            or {}).get("freq", 1)))
        out["impedance"][comp] = (x, z)
    for comp, entry in (data.get("wake_components") or {}).items():
        common = data.get("common_wake") or {}
        x, w = _load_entry(base, common, entry, "wake")
        check_x_column(x, base / (entry.get("file") or common.get("file", path.name)),
                       "wake",
                       int((entry.get("columns") or common.get("columns")
                            or {}).get("time", 1)))
        out["wake"][comp] = (x, w)
    if not out["impedance"] and not out["wake"]:
        raise ValueError(f"{path}: the map defines no components.")
    return out


def interp_impedance(data: dict, freqs) -> dict:
    """Interpolate mapped impedance components onto the run frequency grid."""
    freqs = np.asarray(freqs, dtype=float)
    out = {}
    for comp, (x, z) in data.get("impedance", {}).items():
        out[comp] = (np.interp(freqs, x, z.real) + 1j * np.interp(freqs, x, z.imag))
    return out


def interp_wake(data: dict, times) -> dict:
    times = np.asarray(times, dtype=float)
    return {comp: np.interp(times, x, w)
            for comp, (x, w) in data.get("wake", {}).items()}


def make_descriptor(kind: str, component: str, file: str, comment: str = "#",
                    skip_rows: int = 0, sep: str | None = None, unit: str = "Hz",
                    fmt: str = "re_im", col_x: int = 1, col_re: int = 2,
                    col_im: int = 3, col_z: int = 2, scale: float = 1.0) -> dict:
    """Build an import-map descriptor dict for ONE component of one file.
    kind: "impedance" | "wake". Columns are numbered from 1."""
    entry = {"file": str(file), "comment": comment}
    if skip_rows:
        entry["skip_rows"] = int(skip_rows)
    if sep:
        entry["sep"] = sep
    if kind == "impedance":
        entry["freq_unit"] = unit
        entry["format"] = fmt
        if float(scale) != 1.0:
            entry["z_scale"] = float(scale)
        entry["columns"] = ({"freq": int(col_x), "z": int(col_z)} if fmt == "complex"
                            else {"freq": int(col_x), "re": int(col_re),
                                  "im": int(col_im)})
        return {"common_impedance": entry, "components": {component: {}}}
    entry["time_unit"] = unit
    if float(scale) != 1.0:
        entry["w_scale"] = float(scale)
    entry["columns"] = {"time": int(col_x), "w": int(col_z)}
    return {"common_wake": entry, "wake_components": {component: {}}}
