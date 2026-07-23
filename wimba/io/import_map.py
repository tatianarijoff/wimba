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
    comment = spec.get("comment", "#")
    skip = int(spec.get("skip_rows", 0))
    sep = _sep_of(spec)
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


def load_import_map(path) -> dict:
    """Read a descriptor -> {"impedance": {comp: (x, z)}, "wake": {comp: (x, w)}}."""
    path = Path(path)
    data = yaml.safe_load(path.read_text()) or {}
    base = path.parent
    out = {"impedance": {}, "wake": {}}
    for comp, entry in (data.get("components") or {}).items():
        out["impedance"][comp] = _load_entry(base, data.get("common_impedance") or {},
                                             entry, "impedance")
    for comp, entry in (data.get("wake_components") or {}).items():
        out["wake"][comp] = _load_entry(base, data.get("common_wake") or {},
                                        entry, "wake")
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
