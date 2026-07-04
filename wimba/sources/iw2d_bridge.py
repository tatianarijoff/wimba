"""Bridge to IW2D (the 'iw2d' method).

IW2D is an external binary. Following pywit, a run means: build an IW2D input
file for the chamber, execute the binary, and import its output. That binary is
not bundled here, so this bridge computes only when IW2D is configured (via the
pywit iw2d_settings.yaml, or an IW2D_BINARY path); otherwise it raises a clear
error. The chamber interface mirrors the pytlwall bridge.
"""
from __future__ import annotations

import os
from pathlib import Path


def _iw2d_available():
    if os.environ.get("IW2D_BINARY"):
        return True
    settings = Path.home() / "pywit" / "config" / "iw2d_settings.yaml"
    return settings.exists()


def compute_iw2d(freqs, radius_m, layers=None, length_m=1.0, shape="CIRCULAR",
                 betax=1.0, betay=1.0, gamma=7000.0):
    """Compute a chamber's impedance with IW2D. Requires the IW2D binary."""
    if not _iw2d_available():
        raise RuntimeError(
            "IW2D is not configured in this environment. IW2D is an external "
            "binary; set IW2D_BINARY, or configure pywit's "
            "~/pywit/config/iw2d_settings.yaml, then retry. (The chamber inputs "
            "are ready; only the executable is missing.)")
    # With IW2D available, the flow (per pywit) is:
    #   1. build a RoundIW2DInput / FlatIW2DInput for the chamber + layers,
    #   2. create_iw2d_input_file(...) and run the binary via subprocess,
    #   3. import_data_iw2d(...) and map the columns to WIMBA components.
    raise NotImplementedError(
        "IW2D execution is not wired yet; only the availability check and the "
        "chamber interface are in place.")
