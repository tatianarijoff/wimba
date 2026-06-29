"""Numerical wake <-> impedance transforms, for on-demand consistency checks.

These are *not* part of the normal build/query path: they are direct quadratures
(cost ~ N_freq x N_time) meant to be run deliberately on a specific dataset - for
instance to check that a wake and an impedance are a consistent transform pair,
or to obtain one from the other for a tabulated source that only provides the
other.

Conventions are pinned to the analytic resonator (and therefore to xwakes):

    Z(omega)  = factor * integral_0^inf  W(t) e^{-i omega t} dt
    W(t)      = (1/pi)  * integral_0^inf  Re[ (Z(omega)/factor) e^{+i omega t} ] d omega

with factor = 1 for the longitudinal plane and factor = i for the transverse
planes. The wake is assumed causal (defined for t >= 0); the impedance is assumed
sampled on positive frequencies, the negative axis being recovered from the
reality of the wake.

Accuracy is set entirely by the supplied grids: the wake must be sampled finely
and long enough to have decayed, and the impedance finely enough and up to a high
enough frequency. The transforms do not resample for you.
"""
from __future__ import annotations

import numpy as np

# np.trapz was renamed to np.trapezoid in NumPy 2.0
_trapz = getattr(np, "trapezoid", getattr(np, "trapz", None))

from ..io.tables import read_impedance, read_wake, write_impedance, write_wake


class FourierTransform:
    """Wake <-> impedance transforms by direct numerical quadrature."""

    @staticmethod
    def _factor(plane: str) -> complex:
        return 1.0 + 0j if plane == "z" else 1j

    @classmethod
    def impedance_from_wake(cls, times, wake, freqs, plane="z"):
        """Z(freqs) from a sampled causal wake W(times)."""
        times = np.asarray(times, dtype=float)
        wake = np.asarray(wake, dtype=float)
        omega = 2.0 * np.pi * np.asarray(freqs, dtype=float)
        kernel = np.exp(-1j * np.outer(omega, times))           # (n_freq, n_time)
        Z = _trapz(kernel * wake[None, :], times, axis=1)
        return cls._factor(plane) * Z

    @classmethod
    def wake_from_impedance(cls, freqs, impedance, times, plane="z"):
        """W(times) from an impedance Z(freqs) sampled on positive frequencies."""
        omega = 2.0 * np.pi * np.asarray(freqs, dtype=float)
        G = np.asarray(impedance, dtype=complex) / cls._factor(plane)
        kernel = np.exp(1j * np.outer(np.asarray(times, dtype=float), omega))  # (n_time, n_freq)
        return _trapz((G[None, :] * kernel).real, omega, axis=1) / np.pi

    # --- convenience on .dat files ---
    @classmethod
    def impedance_dat_from_wake_dat(cls, wake_path, out_path, freqs, plane="z"):
        """Read a wake .dat, transform to impedance on `freqs`, write a .dat."""
        t, w = read_wake(wake_path)
        Z = cls.impedance_from_wake(t, w, freqs, plane)
        write_impedance(out_path, freqs, Z, plane)
        return np.asarray(freqs, dtype=float), Z

    @classmethod
    def wake_dat_from_impedance_dat(cls, impedance_path, out_path, times, plane="z"):
        """Read an impedance .dat, transform to wake on `times`, write a .dat."""
        f, Z = read_impedance(impedance_path)
        w = cls.wake_from_impedance(f, Z, times, plane)
        write_wake(out_path, times, w, plane)
        return np.asarray(times, dtype=float), w
