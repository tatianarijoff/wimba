"""Write computed/interpolated per-device impedance and machine totals as CSV,
and read the totals back for plotting.

Layout:
  single_elements/<group>/<name>.csv   # one device (computed or interpolated)
  single_elements/total.csv            # sum over all devices

Each CSV: freq, then Re_<comp>, Im_<comp> for every component present.
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from .naming import safe


def _write(path: Path, freqs, terms) -> Path:
    comps = list(terms)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["freq"] + [f"{p}_{c}" for c in comps for p in ("Re", "Im")])
        for i, f in enumerate(freqs):
            row = [f"{float(f):.8e}"]
            for c in comps:
                v = complex(terms[c][i])
                row += [f"{v.real:.8e}", f"{v.imag:.8e}"]
            w.writerow(row)
    return path


def write_single_element(out_dir, group, name, freqs, terms) -> Path:
    return _write(Path(out_dir) / "single_elements" / safe(group) / f"{safe(name)}.csv",
                  freqs, terms)


def write_totals(out_dir, freqs, totals) -> Path:
    return _write(Path(out_dir) / "single_elements" / "total.csv", freqs, totals)


def read_totals(path):
    """Return (freqs, {component: complex array}) from a totals/per-device CSV."""
    path = Path(path)
    with open(path) as fh:
        rows = list(csv.reader(fh))
    head = rows[0]
    data = np.array([[float(x) for x in r] for r in rows[1:]], dtype=float)
    freqs = data[:, 0]
    comps = {}
    i = 1
    while i < len(head):
        comps[head[i][3:]] = data[:, i] + 1j * data[:, i + 1]
        i += 2
    return freqs, comps


def write_wake_totals(out_dir, times, wakes) -> Path:
    comps = list(wakes)
    path = Path(out_dir) / "single_elements" / "total_wake.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["time"] + comps)
        for i, t in enumerate(times):
            w.writerow([f"{float(t):.8e}"] +
                       [f"{float(np.asarray(wakes[c])[i].real):.8e}" for c in comps])
    return path


def read_wake_totals(path):
    path = Path(path)
    with open(path) as fh:
        rows = list(csv.reader(fh))
    head = rows[0]
    data = np.array([[float(x) for x in r] for r in rows[1:]], dtype=float)
    return data[:, 0], {head[i]: data[:, i] for i in range(1, len(head))}
