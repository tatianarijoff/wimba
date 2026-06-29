"""The whole accelerator: weighted groups + pre-weighted additional, with
selective impedance/wake queries."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

from .element import Element, ElementGroup
from .impedance_term import ImpedanceTerm


@dataclass
class TwissTable:
    """Minimal optics table: element name -> (beta_x, beta_y).

    A name may occur several times around the ring; for now one entry per name.
    Extension: map name -> list of occurrences and sum their contributions.
    """

    betas: Dict[str, Tuple[float, float]] = field(default_factory=dict)

    def beta(self, name: str) -> Tuple[float, float]:
        if name not in self.betas:
            raise KeyError(f"name '{name}' not found in twiss table")
        return self.betas[name]


def _match(term: ImpedanceTerm, plane, multipole, origin) -> bool:
    if plane is not None and term.plane != plane:
        return False
    if multipole is not None and term.category != multipole:
        return False
    if origin is not None and term.origin != origin:
        return False
    return True


@dataclass
class Machine:
    """Two populations of elements:

      * ``groups``    - weighted by beta via name lookup in ``twiss``;
      * ``additional`` - pre-weighted, summed as-is, kept separable.

    Queries (``impedance`` / ``wake``) select along two axes: which terms
    (plane / multipole / origin) and which quantity (Z vs W). Evaluation is lazy.
    """

    twiss: Optional[TwissTable] = None
    groups: List[ElementGroup] = field(default_factory=list)
    additional: List[Element] = field(default_factory=list)

    # --- construction ---
    def add_group(self, name: str) -> ElementGroup:
        g = ElementGroup(name=name)
        self.groups.append(g)
        return g

    def group(self, name: str) -> ElementGroup:
        for g in self.groups:
            if g.name == name:
                return g
        raise KeyError(f"no group named '{name}'")

    def add_additional(self, element: Element) -> Element:
        self.additional.append(element)
        return element

    # --- weighting ---
    def _weight(self, element: Element, term: ImpedanceTerm) -> float:
        if element.optics.pre_weighted:
            return 1.0
        bx, by = element.optics.resolve(self.twiss, element.name)
        return term.tid.beta_weight(bx, by)

    def _selected_elements(self, groups, include_additional) -> Iterable[Element]:
        chosen = self.groups if groups is None else [
            g if isinstance(g, ElementGroup) else self.group(g) for g in groups
        ]
        for g in chosen:
            yield from g.elements
        # 'additional' is a separate bucket, toggled only by include_additional:
        # to plot a single group in isolation, pass include_additional=False.
        if include_additional:
            yield from self.additional

    # --- queries ---
    def impedance(self, freqs, *, plane=None, multipole=None, origin=None,
                  groups=None, include_additional=True) -> Dict[str, np.ndarray]:
        """Beta-weighted machine impedance, summed per term id.

        Returns ``{term_id: complex_array}`` over the given frequency grid,
        restricted to the selected terms / groups.
        """
        freqs = np.asarray(freqs, dtype=float)
        return self._accumulate(freqs, "impedance", plane, multipole, origin,
                                groups, include_additional)

    def wake(self, times, *, plane=None, multipole=None, origin=None,
             groups=None, include_additional=True) -> Dict[str, np.ndarray]:
        """Beta-weighted machine wake, summed per term id, over a time grid."""
        times = np.asarray(times, dtype=float)
        return self._accumulate(times, "wake", plane, multipole, origin,
                                groups, include_additional)

    def _accumulate(self, grid, quantity, plane, multipole, origin,
                    groups, include_additional) -> Dict[str, np.ndarray]:
        has = "has_impedance" if quantity == "impedance" else "has_wake"
        out: Dict[str, np.ndarray] = {}
        for el in self._selected_elements(groups, include_additional):
            for term in el.terms():
                if not getattr(term, has) or not _match(term, plane, multipole, origin):
                    continue
                contrib = self._weight(el, term) * getattr(term, quantity)(grid)
                out[term.id] = out.get(term.id, np.zeros_like(contrib)) + contrib
        return out
