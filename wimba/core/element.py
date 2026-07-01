"""Physical devices and their grouping."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .impedance_term import ImpedanceTerm
from .optics import FromTwiss, OpticsPolicy
from .provider import ImpedanceProvider


@dataclass
class Element:
    """A physical device: collimator, beam-pipe section, cavity, kicker, ...

    ``length`` is the TOTAL device length. By the provider contract the impedance
    already includes this length, so it is never used to re-multiply Z - it is
    bookkeeping metadata. ``name`` is the join key against the twiss table.
    """

    name: str
    category: str
    length: float
    provider: ImpedanceProvider
    optics: OpticsPolicy = field(default_factory=FromTwiss)
    meta: dict = field(default_factory=dict)

    def terms(self) -> List[ImpedanceTerm]:
        return list(self.provider.terms(self))


@dataclass
class ElementGroup:
    """A named bucket of elements of the same kind ('collimators', 'pipes', ...).

    Used both for organisation (the GUI tree) and for plotting the impedance of a
    whole group via ``Machine.impedance(..., groups=[name])``.
    """

    name: str
    elements: List[Element] = field(default_factory=list)

    def add(self, element: Element) -> Element:
        self.elements.append(element)
        return element
