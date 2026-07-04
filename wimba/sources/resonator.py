"""Analytic resonator source.

Impedance and wake follow the standard resonator (Chao) formulas and match
xwakes / pywit term by term, including the sign convention. The wake uses a
complex damped frequency so the overdamped case (Q < 1/2) is handled by the same
expression; the value at t = 0 is the full one (the beam-loading factor 1/2 is a
sampling-time concern, applied where the wake is binned, not here).

Self-contained (numpy only): it also serves as a reference to validate the core
without an external impedance engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import numpy as np

from ..core.impedance_term import ImpedanceTerm
from ..core.terms import STANDARD_TERMS


@dataclass
class Resonator:
    """One resonator contributing to a given standard term.

    Rs is the shunt impedance (Ohm for longitudinal, Ohm/m for transverse).
    """

    term: str   # key of STANDARD_TERMS, e.g. 'zlong', 'zxdip'
    Rs: float
    Q: float
    fr: float   # resonant frequency [Hz]


@dataclass
class ResonatorProvider:
    resonators: List[Resonator] = field(default_factory=list)

    def terms(self, element) -> List[ImpedanceTerm]:
        out: List[ImpedanceTerm] = []
        for r in self.resonators:
            tid = STANDARD_TERMS[r.term]
            longitudinal = tid.plane == "z"
            out.append(ImpedanceTerm(
                id=r.term, tid=tid, origin="resonator",
                z=(_z_long if longitudinal else _z_trans)(r.Rs, r.Q, r.fr),
                w=(_w_long if longitudinal else _w_trans)(r.Rs, r.Q, r.fr),
            ))
        return out


def _z_long(Rs, Q, fr):
    def z(f):
        f = np.asarray(f, dtype=float)
        return Rs / (1.0 + 1j * Q * (f / fr - fr / f))
    return z


def _z_trans(Rs, Q, fr):
    def z(f):
        f = np.asarray(f, dtype=float)
        return (fr / f) * Rs / (1.0 + 1j * Q * (f / fr - fr / f))
    return z


def _damped(Q, fr):
    """Return (omega_r, alpha, omega_bar, root) with a complex root so the same
    expression covers underdamped (Q > 1/2) and overdamped (Q < 1/2)."""
    omega_r = 2.0 * np.pi * fr
    alpha = omega_r / (2.0 * Q)
    root = np.sqrt(1.0 - 1.0 / (4.0 * Q ** 2) + 0j)
    return omega_r, alpha, omega_r * root, root


def _w_long(Rs, Q, fr):
    omega_r, alpha, omega_bar, _ = _damped(Q, fr)
    def w(t):
        t = np.asarray(t, dtype=float)
        out = np.zeros_like(t)
        m = t >= 0
        out[m] = (omega_r * Rs * np.exp(-alpha * t[m])
                  * (np.cos(omega_bar * t[m])
                     - alpha * np.sin(omega_bar * t[m]) / omega_bar) / Q).real
        return out
    return w


def _w_trans(Rs, Q, fr):
    omega_r, alpha, omega_bar, root = _damped(Q, fr)
    def w(t):
        t = np.asarray(t, dtype=float)
        out = np.zeros_like(t)
        m = t >= 0
        out[m] = (omega_r * Rs * np.exp(-alpha * t[m])
                  * np.sin(omega_bar * t[m]) / (Q * root)).real
        return out
    return w


# ---------------------------------------------------------------------------
# Uniform compute interface for the assemble/run flow.
# Same signature style as the external-tool bridges, but the logic is native
# (the formulas above) - so this lives in the source, not in a "_bridge".
# Modes follow the pywit HOM layout: each may carry a longitudinal resonator
# (Rl, Ql, fl), transverse dipolar (Rxd/..., Ryd/...) and quadrupolar
# (Rxq/..., Ryq/...) ones.
# ---------------------------------------------------------------------------

Z_COMPONENTS = ("ZLong", "ZDipX", "ZDipY", "ZQuadX", "ZQuadY")
W_COMPONENTS = ("WLong", "WDipX", "WDipY", "WQuadX", "WQuadY")

# (R key, Q key, f key, Z component, W component, kind)
_MODE_MAP = [
    ("Rl",  "Ql",  "fl",  "ZLong",  "WLong",  "long"),
    ("Rxd", "Qxd", "fxd", "ZDipX",  "WDipX",  "trans"),
    ("Ryd", "Qyd", "fyd", "ZDipY",  "WDipY",  "trans"),
    ("Rxq", "Qxq", "fxq", "ZQuadX", "WQuadX", "trans"),
    ("Ryq", "Qyq", "fyq", "ZQuadY", "WQuadY", "trans"),
]


def _beta(component, betax, betay):
    if component.endswith("X"):
        return betax
    if component.endswith("Y"):
        return betay
    return 1.0


def resonator_impedance(freqs, modes, betax=1.0, betay=1.0):
    freqs = np.asarray(freqs, dtype=float)
    out = {c: np.zeros(len(freqs), dtype=complex) for c in Z_COMPONENTS}
    for m in modes:
        for rk, qk, fk, zc, _wc, kind in _MODE_MAP:
            if m.get(rk):
                z = (_z_long if kind == "long" else _z_trans)(float(m[rk]), float(m[qk]), float(m[fk]))
                out[zc] = out[zc] + z(freqs) * _beta(zc, betax, betay)
    return out


def resonator_wake(times, modes, betax=1.0, betay=1.0):
    times = np.asarray(times, dtype=float)
    out = {c: np.zeros(len(times)) for c in W_COMPONENTS}
    for m in modes:
        for rk, qk, fk, _zc, wc, kind in _MODE_MAP:
            if m.get(rk):
                w = (_w_long if kind == "long" else _w_trans)(float(m[rk]), float(m[qk]), float(m[fk]))
                out[wc] = out[wc] + w(times) * _beta(wc, betax, betay)
    return out
