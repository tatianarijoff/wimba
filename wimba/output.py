"""Write computed/interpolated per-device impedance and machine totals as CSV,
and read the totals back for plotting.

Layout of an output folder:
  total.csv                            # the machine total: sum over all devices
  total_wake.csv                       # the total wake, when computed
  WAKE_NOTES.txt                       # where each wake came from, when computed
  single_elements/<group>/<name>.csv   # one device (computed or interpolated)

The totals sit at the top of the folder because they are the result of the
machine, not one element among the others. Folders written before this layout
kept them under single_elements/; `find_totals` still finds them there, so an
old output opens without being recomputed.

Each CSV: freq, then Re_<comp>, Im_<comp> for every component present.
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from .naming import safe

TOTALS = "total.csv"
WAKE_TOTALS = "total_wake.csv"
WAKE_NOTES = "WAKE_NOTES.txt"


def find_totals(out_dir, wake=False):
    """Path of the totals CSV in an output folder, or None if there is none.

    Looks at the top of the folder first, then under single_elements/, where
    folders written by earlier versions kept it. Every reader goes through
    here, so the fallback lives in one place.
    """
    name = WAKE_TOTALS if wake else TOTALS
    for path in (Path(out_dir) / name, Path(out_dir) / "single_elements" / name):
        if path.is_file():
            return path
    return None


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


def clear_single_elements(out_dir) -> list:
    """Drop the results of a previous calculation before writing new ones.

    Calculate always recomputes, and the totals are always rewritten -- but the
    per-device files are written one per device, so a device removed from the
    config since the last run left its CSV behind. Nothing errored: the Results
    panel lists whatever it finds under single_elements/, so the stale curve
    reappeared next to a total that no longer contains it.

    Only the files this module writes are removed: the .csv/.txt files under
    single_elements/ (including totals left there by the old layout), and at
    the top of the folder the three files named TOTALS, WAKE_TOTALS and
    WAKE_NOTES. The total wake matters most: it is written only when the wake
    is computed, so a run without wake would otherwise leave the previous one
    in place, next to an impedance it no longer belongs to. Anything else a
    user keeps in the output folder is left alone, and a group directory is
    removed only once it is empty. Returns the paths removed, for logging.
    """
    out = Path(out_dir)
    removed = []
    for name in (TOTALS, WAKE_TOTALS, WAKE_NOTES):
        path = out / name
        if path.is_file():
            path.unlink()
            removed.append(path)
    se = out / "single_elements"
    if not se.is_dir():
        return removed
    for path in sorted(se.rglob("*")):
        if path.is_file() and path.suffix in (".csv", ".txt"):
            path.unlink()
            removed.append(path)
    for path in sorted((p for p in se.rglob("*") if p.is_dir()), reverse=True):
        if not any(path.iterdir()):
            path.rmdir()
    return removed


def write_single_element(out_dir, group, name, freqs, terms) -> Path:
    return _write(Path(out_dir) / "single_elements" / safe(group) / f"{safe(name)}.csv",
                  freqs, terms)


def write_totals(out_dir, freqs, totals) -> Path:
    return _write(Path(out_dir) / TOTALS, freqs, totals)


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
    path = Path(out_dir) / WAKE_TOTALS
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
