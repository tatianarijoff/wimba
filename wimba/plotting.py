"""Plot machine totals from a totals CSV.

Components are chosen by the caller: from a file the CLI passes them explicitly
(`--components ZLong,ZDipX`); the GUI chooses at runtime.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .output import read_totals


def plot_totals(totals_csv, components=None, part="abs", save=None):
    import matplotlib
    if save:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    freqs, comps = read_totals(totals_csv)
    if components:
        comps = {c: comps[c] for c in components if c in comps}
    if not comps:
        raise ValueError("no matching components to plot")

    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    for name, z in comps.items():
        y = np.abs(z) if part == "abs" else (z.real if part == "re" else z.imag)
        ax.loglog(freqs, np.abs(y), label=name)
    ax.set_xlabel("frequency [Hz]")
    ax.set_ylabel(f"|Z| ({part})")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    if save:
        fig.savefig(save, dpi=110)
        plt.close(fig)
        return Path(save)
    return fig
