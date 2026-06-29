"""Analytic resonator source.

Longitudinal: closed-form Z(f) and W(t) (standard Chao forms).
Transverse dipolar/quadrupolar: closed-form Z(f); W(t) to be added later.

Self-contained (numpy only) so the core can be validated without pytlwall.
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
            if tid.plane == "z":
                out.append(ImpedanceTerm(id=r.term, tid=tid, origin="resonator",
                                         z=_z_long(r.Rs, r.Q, r.fr),
                                         w=_w_long(r.Rs, r.Q, r.fr)))
            else:
                out.append(ImpedanceTerm(id=r.term, tid=tid, origin="resonator",
                                         z=_z_trans(r.Rs, r.Q, r.fr), w=None))
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


def _w_long(Rs, Q, fr):
    wr = 2.0 * np.pi * fr
    alpha = wr / (2.0 * Q)
    wbar = np.sqrt(max(wr * wr - alpha * alpha, 0.0))
    def w(t):
        t = np.asarray(t, dtype=float)
        out = np.zeros_like(t)
        pos = t > 0
        out[pos] = (2.0 * alpha * Rs * np.exp(-alpha * t[pos])
                    * (np.cos(wbar * t[pos]) - (alpha / wbar) * np.sin(wbar * t[pos])))
        out[t == 0] = alpha * Rs
        return out
    return w
