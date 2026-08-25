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
from .errors import read_config_text
from .logutil import get_logger
from .builders.loader import read_beam
from .naming import safe
from .io.pytlwall_cfg import write_chamber_cfg
from .output import write_single_element, write_totals, write_wake_totals
from .sources.pytlwall_bridge import (COMPONENTS, WAKE_COMPONENTS, chamber_wake,
                                      compute_chamber)
from .sources.iw2d_bridge import compute_iw2d
from .sources.resonator import resonator_impedance, resonator_wake
from .sources.precalculated_bridge import precalculated_impedance, precalculated_wake

COMPUTED_METHODS = ("pytlwall", "iw2d", "resonator", "precalculated")


def _grid(cfg):
    g = (cfg.get("grid") or {}).get("frequency") or {}
    lo, hi, n = float(g.get("min", 1e5)), float(g.get("max", 1e10)), int(g.get("n", 50))
    if g.get("log", True):
        return np.logspace(np.log10(lo), np.log10(hi), n)
    return np.linspace(lo, hi, n)


def _geo_key(geo):
    def _num(x, default=0.0):
        try:
            return round(float(x), 9)
        except (TypeError, ValueError):
            return str(x)                      # e.g. thickness 'inf'
    layers = tuple(tuple(sorted((k, _num(v)) for k, v in l.items()))
                   for l in (geo.get("layers") or []))
    # Anything that changes the numbers belongs in the key. The Yokoya factors
    # and the test-beam shift do, and leaving them out meant two devices with
    # the same wall but different factors shared one cached result: the second
    # was served the first's answer, silently.
    yokoya = tuple(_num(v) for v in (geo.get("iw2d_yokoya") or ()))
    return (round(float(geo.get("radius", 0.02)), 9), geo.get("shape", "CIRCULAR"),
            geo.get("hor"), geo.get("ver"), layers, yokoya,
            _num(geo.get("test_beam_shift"), None)
            if geo.get("test_beam_shift") is not None else None)


def _cached(cache, geo, factory, method="pytlwall"):
    # the method is part of the key: a compare run asks two different codes for
    # the same geometry, and without it the second would be served the first's
    # cached result
    key = (method,) + _geo_key(geo)
    fresh = key not in cache
    if fresh:
        cache[key] = factory()
    return cache[key], fresh


def _mean(row, mean, weighted=True):
    """What _scale should divide the betas by.

    Returning the row's own betas makes the ratio 1, which is how an already
    weighted row -- and an unweighted calculation -- passes through _scale
    untouched without _scale needing to know about either.
    """
    if row.weighted or not weighted:
        return row.beta_x, row.beta_y
    return mean


def _ratio(row, mean, weighted=True):
    """The transverse weights for one row: beta / beta_mean, per plane.

    (1, 1) when the row's data is already weighted, and when the caller asked
    for an unweighted calculation -- in the first case because applying it again
    would double it, in the second because that is what unweighted means.
    """
    if row.weighted or not weighted:
        return 1.0, 1.0
    return row.beta_x / mean[0], row.beta_y / mean[1]


def _scale(base, row, comps, long_name, mean=(1.0, 1.0)):
    """Length, then the transverse weight -- which is a ratio, not a beta.

    beta / beta_mean is dimensionless, so a scaled transverse component is still
    an impedance. Multiplying by the bare beta, as this did, left every
    transverse result a factor of the average beta too large.
    """
    L = row.length or 1.0
    out = {}
    for c in comps:
        if c == long_name:
            out[c] = base[c] * L
        else:
            beta = row.beta_x if c.endswith("X") else row.beta_y
            ref = mean[0] if c.endswith("X") else mean[1]
            out[c] = base[c] * L * (beta / ref)
    return out


def compute_assignments(rows, freqs, out_dir, per_device=(), gamma=None,
                        times=None, beta_mean=(1.0, 1.0), weighted=True):
    zcache, wcache = {}, {}
    ztot = {c: np.zeros(len(freqs), dtype=complex) for c in COMPONENTS}
    wtot = ({c: np.zeros(len(times)) for c in WAKE_COMPONENTS}
            if times is not None else None)
    stats = {"computed": 0, "skipped": 0, "geometries": 0,
             "wake_native": set(), "wake_fft": set()}
    want = set(per_device)
    pipe_acc = ({c: np.zeros(len(freqs), dtype=complex) for c in COMPONENTS}
                if "default_pipe" in want else None)

    for row in rows:
        zterms, wterms = None, None

        if row.method == "pytlwall":
            geo = row.geometry
            if not geo or geo.get("radius") is None:
                raise ValueError(
                    f"device '{row.name}' uses pytlwall but has no geometry/radius; "
                    "check its config (radius_m / radius_mm or halfgap).")
            zbase, fresh = _cached(zcache, geo, method="pytlwall",
                                   factory=lambda g=geo: compute_chamber(freqs, g.get("radius", 0.02),
                                                                 g.get("layers"), length_m=1.0,
                                                                 shape=g.get("shape", "CIRCULAR"),
                                                                 hor_m=g.get("hor"), ver_m=g.get("ver"),
                                                                 betax=1.0, betay=1.0, gamma=gamma,
                                                                 test_beam_shift=g.get("test_beam_shift")))
            if fresh:
                stats["geometries"] += 1
                write_chamber_cfg(Path(out_dir) / "pytlwall_inputs" /
                                  f"{stats['geometries']:02d}_{safe(geo.get('name') or row.name)}.cfg",
                                  geo, gamma=gamma,
                                  test_beam_shift=geo.get("test_beam_shift"))
                if geo.get("test_beam_shift") is not None:
                    # a number that changes a result should never be invisible
                    stats.setdefault("notes", []).append(
                        f"{row.name}: test_beam_shift = "
                        f"{geo['test_beam_shift']} (from the config; only the "
                        f"space-charge terms use it)")
            zterms = _scale(zbase, row, COMPONENTS, "ZLong", _mean(row, beta_mean, weighted))
            if row.space_charge:
                # indirect space charge: kept as separate components (ZLongISC, ...),
                # NOT folded into the wall columns; the full impedance is wall + ISC.
                L = row.length or 1.0
                zterms["ZLongISC"] = zbase["ZLongISC"] * L
                zterms["ZDipXISC"] = zbase["ZDipISC"] * L * row.beta_x
                zterms["ZDipYISC"] = zbase["ZDipISC"] * L * row.beta_y
                zterms["ZQuadXISC"] = zbase["ZQuadISC"] * L * row.beta_x
                zterms["ZQuadYISC"] = zbase["ZQuadISC"] * L * row.beta_y
            if times is not None:
                wbase, _ = _cached(wcache, geo, method="pytlwall",
                                   factory=lambda g=geo: chamber_wake(times, g.get("radius", 0.02),
                                                             g.get("layers"), length_m=1.0,
                                                             shape=g.get("shape", "CIRCULAR"),
                                                             hor_m=g.get("hor"), ver_m=g.get("ver"),
                                                             betax=1.0, betay=1.0, gamma=gamma,
                                                             test_beam_shift=g.get("test_beam_shift")))
                wterms = _scale(wbase, row, WAKE_COMPONENTS, "WLong", _mean(row, beta_mean, weighted))
                stats["wake_native"].add("pytlwall")

        elif row.method == "iw2d":
            geo = row.geometry
            if not geo or geo.get("radius") is None:
                raise ValueError(
                    f"device '{row.name}' uses iw2d but has no geometry/radius; "
                    "check its config (radius_m / radius_mm or halfgap).")
            shape = str(geo.get("shape", "CIRCULAR")).upper()
            yokoya = geo.get("iw2d_yokoya")
            if shape != "CIRCULAR" and not yokoya:
                raise ValueError(
                    f"device '{row.name}' is {shape} and asks for IW2D. IW2D "
                    "solves round and flat chambers; any other shape is "
                    "represented by a round solve rescaled with Yokoya "
                    "factors, which this device does not state. Add "
                    "'iw2d_yokoya: [long, xdip, ydip, xquad, yquad]', or "
                    "compute it with pytlwall, which carries its own tables.")
            zbase, fresh = _cached(
                zcache, geo, method="iw2d",
                factory=lambda g=geo: compute_iw2d(freqs, g.get("radius", 0.02),
                                                   g.get("layers"), length_m=1.0,
                                                   shape="CIRCULAR",
                                                   betax=1.0, betay=1.0,
                                                   gamma=gamma,
                                                   yokoya=g.get("iw2d_yokoya")))
            if fresh:
                stats["geometries"] += 1
                _out, notes = compute_iw2d(freqs[:1], geo.get("radius", 0.02),
                                           geo.get("layers"), length_m=1.0,
                                           gamma=gamma, yokoya=yokoya,
                                           return_notes=True)
                if shape != "CIRCULAR":
                    stats.setdefault("notes", []).append(
                        f"{row.name}: {shape} computed by IW2D as a round "
                        f"chamber rescaled with the Yokoya factors "
                        f"{list(yokoya)} — an approximation, and the factors "
                        f"are the ones this config states, not WIMBA's.")
                for note in notes:
                    stats.setdefault("notes", []).append(f"{row.name}: {note}")
            zterms = _scale(zbase, row, COMPONENTS, "ZLong", _mean(row, beta_mean, weighted))
            # IW2D returns the wall impedance, which already contains the
            # indirect space charge: there is no separate ISC component to add,
            # and asking for one would double-count it.
            if row.space_charge:
                stats.setdefault("notes", []).append(
                    f"{row.name}: space_charge is ignored for iw2d -- its "
                    "impedance already includes the indirect space charge, so "
                    "it compares against pytlwall's ZLong + ZLongISC.")
            if times is not None:
                # the bridge does not drive IW2D's own wake solver yet
                from .analysis import FourierTransform
                ft = FourierTransform()
                wterms = {c: np.zeros(len(times)) for c in WAKE_COMPONENTS}
                for zc, (wc, plane) in (("ZLong", ("WLong", "z")),
                                        ("ZDipX", ("WDipX", "x")),
                                        ("ZDipY", ("WDipY", "y")),
                                        ("ZQuadX", ("WQuadX", "x")),
                                        ("ZQuadY", ("WQuadY", "y"))):
                    if zc in zterms:
                        try:
                            w = ft.wake_from_impedance(freqs, zterms[zc], times,
                                                       plane=plane)
                            wterms[wc] = np.asarray(w).real
                        except Exception:
                            pass
                stats["wake_fft"].add("iw2d")

        elif row.method == "resonator":
            modes = (row.params or {}).get("modes", [])
            # lumped: the weight applies, the length does NOT
            bx, by = _ratio(row, beta_mean, weighted)
            zterms = resonator_impedance(freqs, modes, betax=bx, betay=by)
            if times is not None:
                wterms = resonator_wake(times, modes, betax=bx, betay=by)
                stats["wake_native"].add("resonator")

        elif row.method == "precalculated":
            params = row.params or {}
            files, wfiles = params.get("files", {}), params.get("wake_files", {})
            funit, tunit = params.get("freq_unit"), params.get("time_unit")
            map_data = None
            if params.get("map"):
                from .io.import_map import (interp_impedance, interp_wake,
                                            load_import_map)
                map_data = load_import_map(params["map"])
            bx, by = _ratio(row, beta_mean, weighted)   # data used as-is if already weighted

            def _bw(component):
                return bx if component.endswith("X") else (by if component.endswith("Y") else 1.0)

            if map_data is not None:
                loaded = interp_impedance(map_data, freqs)
            else:
                loaded = precalculated_impedance(freqs, files, freq_unit=funit)
            zterms = {c: np.zeros(len(freqs), dtype=complex) for c in COMPONENTS}
            for c, v in loaded.items():
                if c in zterms:
                    zterms[c] = v * _bw(c)

            if times is not None:
                wterms = {c: np.zeros(len(times)) for c in WAKE_COMPONENTS}
                if map_data is not None and map_data.get("wake"):
                    for c, v in interp_wake(map_data, times).items():
                        if c in wterms:
                            wterms[c] = v * _bw(c)
                    stats["wake_native"].add("precalculated")
                elif wfiles:
                    for c, v in precalculated_wake(times, wfiles, time_unit=tunit).items():
                        if c in wterms:
                            wterms[c] = v * _bw(c)
                    stats["wake_native"].add("precalculated")
                else:
                    # no native wake for this data -> Fourier transform of the impedance
                    from .analysis import FourierTransform
                    ft = FourierTransform()
                    zw = {"ZLong": ("WLong", "z"), "ZDipX": ("WDipX", "x"),
                          "ZDipY": ("WDipY", "y"), "ZQuadX": ("WQuadX", "x"),
                          "ZQuadY": ("WQuadY", "y")}
                    for zc, (wc, plane) in zw.items():
                        if zc in loaded:
                            try:
                                w = ft.wake_from_impedance(freqs, zterms[zc], times, plane=plane)
                                wterms[wc] = np.asarray(w).real
                            except Exception:
                                pass
                    stats["wake_fft"].add("precalculated")

        else:
            # say WHICH device was dropped and why: a device that vanishes from
            # the results without a word is the hardest kind of bug to notice
            stats["skipped"] += 1
            stats.setdefault("notes", []).append(
                f"{row.name}: skipped -- method '{row.method}' is not one of "
                f"{', '.join(COMPUTED_METHODS)}.")
            continue

        for c, v in zterms.items():
            if c not in ztot:
                ztot[c] = np.zeros(len(freqs), dtype=complex)
            ztot[c] = ztot[c] + v
        stats["computed"] += 1
        if row.name in want:
            write_single_element(out_dir, row.group or row.kind, row.name, freqs, zterms)
        if pipe_acc is not None and row.kind == "default_pipe":
            for c, v in zterms.items():
                if c not in pipe_acc:
                    pipe_acc[c] = np.zeros(len(freqs), dtype=complex)
                pipe_acc[c] = pipe_acc[c] + v
        if times is not None and wterms is not None:
            for c in WAKE_COMPONENTS:
                wtot[c] = wtot[c] + wterms[c]

    if pipe_acc is not None:
        write_single_element(out_dir, "default_pipe", "default_pipe", freqs, pipe_acc)
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


def run(config, out_dir=None, plot=None, wake=False, gamma=None, fill_pipe=True,
        cfg=None, weighted=True):
    """Compute a study.

    `config` is the file the study is named after and the path every relative
    reference in it resolves against. `cfg` optionally supplies its *contents*
    already in memory: the GUI uses this so a beam typed in the Beam panel is
    what gets computed, instead of a stale one re-read from disk behind the
    user's back. The file itself is never written.
    """
    if cfg is None:
        cfg = yaml.safe_load(read_config_text(config, "assembly config")) or {}
    if not fill_pipe:                      # GUI toggle: compute only the listed devices
        cfg = dict(cfg)
        cfg.pop("default_pipe", None)
    result = load_assembly(config, cfg=cfg)
    for w in result.warnings:
        get_logger(__name__).warning(w)
    freqs = _grid(cfg)
    out = Path(out_dir) if out_dir else Path(config).parent / f"{result.name}_output"
    per_device = cfg.get("output") or []
    beam = read_beam(cfg)
    if beam is not None:
        gamma = beam.gamma
    elif gamma is None:
        raise ValueError(
            f"'{Path(config).name}' does not say at which energy to compute. Add a "
            "beam, e.g.\n  beam: {particle: proton, gamma: 7461}\n"
            "(a bare 'gamma:' still works too).")
    times = np.linspace(1.0e-12, 5.0e-9, 500) if wake else None

    log = get_logger(__name__)
    mx, my = result.beta_mean
    if weighted:
        log.info("Transverse weight: beta / beta_mean, with beta_mean = "
                 "(%.6g, %.6g) m from %s.", mx, my, result.beta_mean_source)
    else:
        log.info("Computing UNWEIGHTED: every transverse weight is 1. Already "
                 "weighted devices are still summed as they are.")
    ztot, wtot, stats = compute_assignments(result.rows, freqs, out,
                                            per_device=per_device, gamma=gamma,
                                            times=times, beta_mean=result.beta_mean,
                                            weighted=weighted)
    stats["beta_mean"] = (mx, my)
    stats["beta_mean_source"] = result.beta_mean_source
    stats["weighted"] = weighted

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
