"""End-to-end WIMBA example.

Builds a small machine from analytic resonators, computes its longitudinal and
transverse impedance and its longitudinal wake, writes the results as plain
column .dat files, and saves plots.

Run (inside the venv):
    pip install -e ".[examples]"      # pulls in matplotlib
    python examples/resonator_machine.py

Outputs go to examples/resonator_output/ (Z_*.dat, W_*.dat, impedance.png, wake.png).
"""
from __future__ import annotations

import os

import numpy as np
import matplotlib
matplotlib.use("Agg")          # save figures without a display; drop this for interactive use
import matplotlib.pyplot as plt

from wimba import (Element, Machine, PreWeighted, Resonator, ResonatorProvider,
                   STANDARD_TERMS, TwissTable)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "resonator_output")

Z_UNITS = {"z": "Ohm", "x": "Ohm/m", "y": "Ohm/m"}


def build_machine() -> Machine:
    """A toy ring: two collimators (weighted by beta) + one pre-weighted addition."""
    m = Machine(twiss=TwissTable({"c1": (10.0, 20.0), "c2": (30.0, 40.0)}))

    coll = m.add_group("collimators")
    coll.add(Element("c1", "collimator", 1.0,
                     ResonatorProvider([Resonator("zlong", 1.0e4, 1.0, 1.0e9),
                                        Resonator("zxdip", 1.0e6, 1.0, 1.0e9)])))
    coll.add(Element("c2", "collimator", 1.0,
                     ResonatorProvider([Resonator("zlong", 2.0e4, 1.0, 1.2e9)])))

    # a pre-weighted future addition, kept apart from the optics-weighted groups
    m.add_additional(Element("crab", "additional", 1.0,
                             ResonatorProvider([Resonator("zlong", 7.0e3, 1.0, 0.8e9)]),
                             optics=PreWeighted()))
    return m


def save_impedance(path, freqs, Z, plane):
    unit = Z_UNITS[plane]
    header = (f"WIMBA impedance\n"
              f"columns: frequency[Hz]  Re(Z)[{unit}]  Im(Z)[{unit}]")
    np.savetxt(path, np.column_stack([freqs, Z.real, Z.imag]), header=header, fmt="% .8e")


def save_wake(path, times, W):
    header = ("WIMBA wake (longitudinal)\n"
              "columns: time[s]  W[V/C]")
    np.savetxt(path, np.column_stack([times, W]), header=header, fmt="% .8e")


def main():
    os.makedirs(OUT, exist_ok=True)
    m = build_machine()

    f = np.logspace(8, 9.5, 600)        # 1e8 .. ~3.2e9 Hz, avoids f = 0
    t = np.linspace(0.0, 5.0e-9, 600)   # 0 .. 5 ns

    Z = m.impedance(f)                  # all terms with an impedance: zlong, zxdip
    W = m.wake(t)                       # only terms with a wake: zlong

    # --- data files ---
    for tid, z in Z.items():
        save_impedance(os.path.join(OUT, f"Z_{tid}.dat"), f, z, STANDARD_TERMS[tid].plane)
    for tid, w in W.items():
        save_wake(os.path.join(OUT, f"W_{tid}.dat"), t, w)

    # --- impedance plot: longitudinal (Ohm) and transverse (Ohm/m) ---
    fig, ax = plt.subplots(2, 1, figsize=(7, 7), sharex=True)

    if "zlong" in Z:
        ax[0].plot(f, Z["zlong"].real, label="Re")
        ax[0].plot(f, Z["zlong"].imag, label="Im")
    ax[0].set_ylabel(r"$Z_\parallel$  [$\Omega$]")
    ax[0].set_title("longitudinal impedance")
    ax[0].legend()
    ax[0].grid(True, alpha=0.3)

    for tid, z in Z.items():
        if tid == "zlong":
            continue
        ax[1].plot(f, z.real, label=f"{tid}  Re")
        ax[1].plot(f, z.imag, label=f"{tid}  Im")
    ax[1].set_ylabel(r"$Z_\perp$  [$\Omega$/m]")
    ax[1].set_xlabel("frequency [Hz]")
    ax[1].set_xscale("log")
    ax[1].set_title("transverse impedance")
    ax[1].legend()
    ax[1].grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "impedance.png"), dpi=130)

    # --- wake plot: longitudinal ---
    fig2, ax2 = plt.subplots(figsize=(7, 4))
    for tid, w in W.items():
        ax2.plot(t * 1e9, w, label=tid)
    ax2.set_xlabel("time [ns]")
    ax2.set_ylabel(r"$W_\parallel$  [V/C]")
    ax2.set_title("longitudinal wake")
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    fig2.tight_layout()
    fig2.savefig(os.path.join(OUT, "wake.png"), dpi=130)

    print("wrote:", ", ".join(sorted(os.listdir(OUT))))


if __name__ == "__main__":
    main()
