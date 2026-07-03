"""Run a study: assemble -> compute -> write the total (+ requested per-device) -> plot.

Only the machine total is written by default; a device gets its own file under
single_elements/<group>/<name>.csv when its name is listed under `output:`.
Chambers sharing a geometry are computed once (unit length, beta = 1) and scaled by
L and beta per occurrence, so the default pipe costs one calculation. With wake
enabled, the wake is the real pytlwall wake (TLWallWake), not a Fourier transform.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml

from .assembly import load_assembly
from .output import write_single_element, write_totals, write_wake_totals
from .sources.pytlwall_bridge import (COMPONENTS, WAKE_COMPONENTS, chamber_wake,
                                      compute_chamber)

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


def _cached(cache, geo, factory):
    key = _geo_key(geo)
    fresh = key not in cache
    if fresh:
        cache[key] = factory()
    return cache[key], fresh


def _scale(base, row, comps, long_name):
    L = row.length or 1.0
    out = {}
    for c in comps:
        if c == long_name:
            out[c] = base[c] * L
        else:
            beta = row.beta_x if c.endswith("X") else row.beta_y
            out[c] = base[c] * L * beta
    return out


def compute_assignments(rows, freqs, out_dir, per_device=(), gamma=7000.0, times=None):
    zcache, wcache = {}, {}
    ztot = {c: np.zeros(len(freqs), dtype=complex) for c in COMPONENTS}
    wtot = ({c: np.zeros(len(times)) for c in WAKE_COMPONENTS}
            if times is not None else None)
    stats = {"computed": 0, "skipped": 0, "geometries": 0,
             "wake_native": set(), "wake_fft": set()}
    want = set(per_device)

    for row in rows:
        if row.method not in COMPUTED_METHODS:
            stats["skipped"] += 1
            continue
        geo = row.geometry or {"radius": 0.02}

        zbase, fresh = _cached(zcache, geo,
                               lambda g=geo: compute_chamber(freqs, g.get("radius", 0.02),
                                                             g.get("layers"), length_m=1.0,
                                                             betax=1.0, betay=1.0, gamma=gamma))
        if fresh:
            stats["geometries"] += 1
        zterms = _scale(zbase, row, COMPONENTS, "ZLong")
        if row.space_charge:
            L = row.length or 1.0
            zterms["ZLong"] = zterms["ZLong"] + zbase["ZLongISC"] * L
            zterms["ZDipX"] = zterms["ZDipX"] + zbase["ZDipISC"] * L * row.beta_x
            zterms["ZDipY"] = zterms["ZDipY"] + zbase["ZDipISC"] * L * row.beta_y
            zterms["ZQuadX"] = zterms["ZQuadX"] + zbase["ZQuadISC"] * L * row.beta_x
            zterms["ZQuadY"] = zterms["ZQuadY"] + zbase["ZQuadISC"] * L * row.beta_y
        for c in COMPONENTS:
            ztot[c] = ztot[c] + zterms[c]
        stats["computed"] += 1
        if row.name in want:
            write_single_element(out_dir, row.group or row.kind, row.name, freqs, zterms)

        if times is not None:
            wbase, _ = _cached(wcache, geo,
                               lambda g=geo: chamber_wake(times, g.get("radius", 0.02),
                                                         g.get("layers"), length_m=1.0,
                                                         betax=1.0, betay=1.0, gamma=gamma))
            wterms = _scale(wbase, row, WAKE_COMPONENTS, "WLong")
            for c in WAKE_COMPONENTS:
                wtot[c] = wtot[c] + wterms[c]
            stats["wake_native"].add(row.method)

    write_totals(out_dir, freqs, ztot)
    if times is not None:
        write_wake_totals(out_dir, times, wtot)
    return ztot, wtot, stats


def _write_wake_note(out_dir, stats):
    native = sorted(stats.get("wake_native") or [])
    fft = sorted(stats.get("wake_fft") or [])
    lines = [
        "WIMBA - wake provenance",
        "",
        "Computed natively by pytlwall (TLWallWake): " + (", ".join(native) or "(none)"),
        "",
        "Wake computed with the Fourier transform for the following methods:",
        "  " + (", ".join(fft) if fft else "(none)"),
        "",
        "These Fourier-transform cases are meant to be replaced by native wake",
        "calculations method by method.",
    ]
    (Path(out_dir) / "single_elements" / "WAKE_NOTES.txt").write_text("\n".join(lines) + "\n")


def run(config, out_dir=None, plot=None, wake=False, gamma=7000.0):
    cfg = yaml.safe_load(Path(config).read_text()) or {}
    result = load_assembly(config)
    freqs = _grid(cfg)
    out = Path(out_dir) if out_dir else Path(config).parent / f"{result.name}_output"
    per_device = cfg.get("output") or []
    times = np.linspace(1.0e-12, 5.0e-9, 500) if wake else None

    ztot, wtot, stats = compute_assignments(result.rows, freqs, out,
                                            per_device=per_device, gamma=gamma, times=times)

    from .plotting import plot_totals, DEFAULT_COMPONENTS
    plots = plot_totals(out / "single_elements" / "total.csv",
                        components=plot or DEFAULT_COMPONENTS, out_dir=out)
    wake_plots = []
    if wake:
        from .plotting import plot_wakes
        wake_plots = plot_wakes(out / "single_elements" / "total_wake.csv", out_dir=out)
        _write_wake_note(out, stats)

    return {"out": out, "stats": stats, "plots": plots, "wake_plots": wake_plots,
            "n_rows": len(result.rows)}
