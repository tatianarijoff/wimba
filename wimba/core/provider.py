"""The pluggable strategy that gives an element its impedance/wake terms."""
from __future__ import annotations

from typing import List, Protocol, TYPE_CHECKING, runtime_checkable

from .impedance_term import ImpedanceTerm

if TYPE_CHECKING:
    from .element import Element


@runtime_checkable
class ImpedanceProvider(Protocol):
    """Yields the terms of an element.

    Implementations live in ``wimba/sources/`` - resistive wall via pytlwall
    (optionally emitting space-charge terms too), CST/ASCII import, analytic
    resonator, geometric collimator, ...

    Contract: the provider returns the *total-device* terms with the device
    length already included (so Z is never re-multiplied by length later) and
    *un-weighted* in beta. Beta weighting is applied downstream by ``Machine``.
    """

    def terms(self, element: "Element") -> List[ImpedanceTerm]: ...
