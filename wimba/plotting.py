"""Plot machine totals from a totals CSV.

Default plots follow the common accelerator convention: one figure per component
showing the real and imaginary parts versus frequency (log frequency axis). The
longitudinal wake can also be plotted (obtained from the total impedance by the
Fourier transform).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .output import read_totals

DEFAULT_COMPONENTS = ["ZLong", "ZDipX", "ZDipY"]

def _autoscale_y(ax, *arrays):
    v = np.concatenate([np.asarray(a).ravel() for a in arrays])
    v = v[np.isfinite(v)]
    if v.size == 0:
        return
    vmin, vmax = float(v.min()), float(v.max())
    nz = np.abs(v[v != 0.0])
    lt = float(nz.min()) if nz.size else 1.0
    if vmin > 0.0 or vmax < 0.0:
        # single sign -> plain log axis (no empty negative half)
        ax.set_yscale("log")
    else:
        # crosses zero -> symlog, linear region just below the smallest value
        ax.set_yscale("symlog", linthresh=max(lt, max(abs(vmin), abs(vmax)) * 1e-12))



def plot_component(x, z, name, save=None, xlabel="frequency [Hz]", xlog=True):
    """One figure with Re and Im of `z` versus `x`."""
    import matplotlib
    if save:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.0, 4.2))
    draw = ax.semilogx if xlog else ax.plot
    draw(x, np.asarray(z).real, label="Re", color="#1f6f8c")
    draw(x, np.asarray(z).imag, label="Im", color="#e0a458")
    ax.axhline(0.0, color="0.6", lw=0.8)
    _autoscale_y(ax, np.asarray(z).real, np.asarray(z).imag)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(name)
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    if save:
        fig.savefig(save, dpi=110)
        plt.close(fig)
        return Path(save)
    return fig


def plot_totals(totals_csv, components=None, out_dir=None, prefix="total"):
    """One Re/Im figure per component. Returns the list of saved paths."""
    freqs, comps = read_totals(totals_csv)
    selected = components or DEFAULT_COMPONENTS
    out_dir = Path(out_dir) if out_dir else Path(totals_csv).parent
    saved = []
    for c in selected:
        if c in comps:
            saved.append(plot_component(freqs, comps[c], c, save=out_dir / f"{prefix}_{c}.png"))
    return saved


def plot_wake(times, wake, name="WLong", save=None):
    """One figure of a wake (real) versus time."""
    import matplotlib
    if save:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.0, 4.2))
    ax.plot(times, np.asarray(wake).real, color="#1f6f8c")
    ax.axhline(0.0, color="0.6", lw=0.8)
    _autoscale_y(ax, np.asarray(wake).real)
    ax.set_xlabel("time [s]")
    ax.set_ylabel(name)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    if save:
        fig.savefig(save, dpi=110)
        plt.close(fig)
        return Path(save)
    return fig


WAKE_DEFAULTS = ["WLong", "WDipX", "WDipY"]


def plot_wakes(wake_csv, components=None, out_dir=None, prefix="total"):
    """One figure per wake component (real vs time). Returns saved paths."""
    from .output import read_wake_totals
    times, comps = read_wake_totals(wake_csv)
    selected = components or WAKE_DEFAULTS
    out_dir = Path(out_dir) if out_dir else Path(wake_csv).parent
    saved = []
    for c in selected:
        if c in comps:
            saved.append(plot_wake(times, comps[c], name=c, save=out_dir / f"{prefix}_{c}.png"))
    return saved
