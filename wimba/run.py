"""Run a study: assemble -> compute -> write the total (+ requested per-device) -> plot.

By default only the machine total is written. A device is written on its own under
single_elements/<group>/<name>.csv only if its name is listed under `output:` in the
config. Chambers sharing a geometry are computed once (beta-free, unit length) and
scaled by L and beta per occurrence - so the default pipe costs one calculation.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml

from .assembly import load_assembly
from .output import write_single_element, write_totals
from .sources.pytlwall_bridge import COMPONENTS, compute_chamber

COMPUTED_METHODS = ("pytlwall",)   # iw2d / resonator / precalculated: coming next


def _grid(cfg):
    g = (cfg.get("grid") or {}).get("frequency") or {}
    lo, hi, n = float(g.get("min", 1e5)), float(g.get("max", 1e10)), int(g.get("n", 50))
    if g.get("log", True):
        return np.logspace(np.log10(lo), np.log10(hi), n)
    return np.linspace(lo, hi, n)


def _geo_key(geo):
    layers = tuple((l.get("material"), round(float(l.get("thickness", 0.0)), 9))
                   for l in (geo.get("layers") or []))
    return (round(float(geo.get("radius", 0.02)), 9), layers)


def _base(cache, freqs, geo, gamma):
    key = _geo_key(geo)
    if key not in cache:
        cache[key] = compute_chamber(freqs, geo.get("radius", 0.02), geo.get("layers"),
                                     length_m=1.0, betax=1.0, betay=1.0, gamma=gamma)
    return cache[key], key


def _row_terms(base, row):
    L = row.length or 1.0
    t = {"ZLong":  base["ZLong"] * L,
         "ZDipX":  base["ZDipX"] * L * row.beta_x,
         "ZDipY":  base["ZDipY"] * L * row.beta_y,
         "ZQuadX": base["ZQuadX"] * L * row.beta_x,
         "ZQuadY": base["ZQuadY"] * L * row.beta_y}
    if row.space_charge:
        t["ZLong"] += base["ZLongISC"] * L
        t["ZDipX"] += base["ZDipISC"] * L * row.beta_x
        t["ZDipY"] += base["ZDipISC"] * L * row.beta_y
        t["ZQuadX"] += base["ZQuadISC"] * L * row.beta_x
        t["ZQuadY"] += base["ZQuadISC"] * L * row.beta_y
    return t


def compute_assignments(rows, freqs, out_dir, per_device=(), gamma=7000.0):
    cache = {}
    totals = {c: np.zeros(len(freqs), dtype=complex) for c in COMPONENTS}
    stats = {"computed": 0, "skipped": 0, "geometries": 0}
    want = set(per_device)
    for row in rows:
        if row.method not in COMPUTED_METHODS:
            stats["skipped"] += 1
            continue
        geo = row.geometry or {"radius": 0.02}
        before = len(cache)
        base, _ = _base(cache, freqs, geo, gamma)
        if len(cache) > before:
            stats["geometries"] += 1
        terms = _row_terms(base, row)
        for c in COMPONENTS:
            totals[c] = totals[c] + terms[c]
        stats["computed"] += 1
        if row.name in want:
            write_single_element(out_dir, row.group or row.kind, row.name, freqs, terms)
    write_totals(out_dir, freqs, totals)
    return totals, stats


def run(config, out_dir=None, plot=None, part="abs", gamma=7000.0):
    cfg = yaml.safe_load(Path(config).read_text()) or {}
    result = load_assembly(config)
    freqs = _grid(cfg)
    out = Path(out_dir) if out_dir else Path(config).parent / f"{result.name}_output"
    per_device = cfg.get("output") or []
    totals, stats = compute_assignments(result.rows, freqs, out, per_device=per_device, gamma=gamma)
    saved = None
    if plot:
        from .plotting import plot_totals
        saved = plot_totals(out / "single_elements" / "total.csv",
                            components=plot, part=part, save=out / "total.png")
    return {"out": out, "stats": stats, "plot": saved, "n_rows": len(result.rows)}
