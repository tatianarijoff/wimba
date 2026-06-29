"""How an element gets the beta functions used for weighting."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


class OpticsPolicy:
    """Base policy. ``pre_weighted`` flags elements summed as-is (weight 1)."""

    pre_weighted: bool = False

    def resolve(self, twiss, name: str) -> Tuple[float, float]:
        raise NotImplementedError


@dataclass
class FromTwiss(OpticsPolicy):
    """Look up (beta_x, beta_y) in the twiss table by name.

    Defaults to the element's own name; set ``name`` to match a different key.
    """

    name: Optional[str] = None
    pre_weighted = False

    def resolve(self, twiss, name: str) -> Tuple[float, float]:
        key = self.name or name
        if twiss is None:
            raise ValueError(f"element '{key}' needs a twiss table to resolve its optics")
        return twiss.beta(key)


@dataclass
class Explicit(OpticsPolicy):
    """Optics given inline, no twiss lookup."""

    beta_x: float
    beta_y: float
    pre_weighted = False

    def resolve(self, twiss, name: str) -> Tuple[float, float]:
        return self.beta_x, self.beta_y


@dataclass
class PreWeighted(OpticsPolicy):
    """Element whose impedance already includes its beta weighting.

    Used for the 'additional' bucket: summed as-is, never re-weighted, and never
    requires a twiss entry.
    """

    pre_weighted = True

    def resolve(self, twiss, name: str) -> Tuple[float, float]:
        return 1.0, 1.0
