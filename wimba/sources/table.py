"""Import already-computed impedance/wake from a column .dat file.

Lets the config point at an existing file (e.g. a CST result, or a pre-computed
space-charge term) instead of recomputing it. The tabulated data is interpolated
onto whatever grid the query asks for.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..core.impedance_term import ImpedanceTerm
from ..core.terms import STANDARD_TERMS
from ..io.tables import read_impedance, read_wake


@dataclass
class TableProvider:
    path: str
    term: str
    origin: str = "imported"
    quantity: str = "impedance"   # "impedance" (f,ReZ,ImZ) or "wake" (t,W)

    def terms(self, element):
        tid = STANDARD_TERMS[self.term]
        if self.quantity == "impedance":
            xf, Z = read_impedance(self.path)
            def z(f, xf=xf, Z=Z):
                f = np.asarray(f, dtype=float)
                return (np.interp(f, xf, Z.real) + 1j * np.interp(f, xf, Z.imag))
            return [ImpedanceTerm(self.term, tid, self.origin, z=z, w=None)]
        xt, W = read_wake(self.path)
        def w(t, xt=xt, W=W):
            return np.interp(np.asarray(t, dtype=float), xt, W)
        return [ImpedanceTerm(self.term, tid, self.origin, z=None, w=w)]
