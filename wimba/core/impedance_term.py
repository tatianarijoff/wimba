"""A single multipole term: optional Z(f) and/or W(t), tagged two ways."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from .terms import TermId

ZFunc = Callable[[np.ndarray], np.ndarray]
WFunc = Callable[[np.ndarray], np.ndarray]


@dataclass
class ImpedanceTerm:
    """One impedance/wake term.

    It carries two orthogonal tags:
      * ``tid`` - the multipole identity (plane + exponents), driving beta weighting;
      * ``origin`` - the physical origin ('resistive_wall', 'space_charge',
        'geometric', 'resonator', 'imported', ...), so contributions can be
        included/excluded and plotted separately. This is what lets space charge
        live next to resistive wall without being forced into the same bucket.

    ``z`` and ``w`` are independent: a term may provide impedance only, wake only,
    or both. Evaluation is lazy - nothing is computed until a grid is supplied.
    """

    id: str            # canonical id, e.g. 'zlong'
    tid: TermId        # multipole identity
    origin: str        # physical origin tag
    z: Optional[ZFunc] = None
    w: Optional[WFunc] = None

    @property
    def plane(self) -> str:
        return self.tid.plane

    @property
    def category(self) -> str:
        return self.tid.category

    @property
    def power(self) -> int:
        return self.tid.power

    @property
    def has_impedance(self) -> bool:
        return self.z is not None

    @property
    def has_wake(self) -> bool:
        return self.w is not None

    def impedance(self, freqs) -> np.ndarray:
        if self.z is None:
            raise ValueError(f"term '{self.id}' (origin={self.origin}) has no impedance Z(f)")
        return np.asarray(self.z(np.asarray(freqs, dtype=float)), dtype=complex)

    def wake(self, times) -> np.ndarray:
        if self.w is None:
            raise ValueError(f"term '{self.id}' (origin={self.origin}) has no wake W(t)")
        return np.asarray(self.w(np.asarray(times, dtype=float)), dtype=float)
