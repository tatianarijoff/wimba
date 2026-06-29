"""Multipole identity of impedance/wake terms and the beta-weighting rule.

A term is identified by a plane ('z', 'x', 'y') and two pairs of exponents:
the *source* (driving particle offset) and the *test* (witness particle offset).
This matches the xwakes/PyWIT convention so the two libraries stay interoperable.

The beta weighting of a term, when summing devices around the ring, is

    w = beta_x ** (source_x + test_x) * beta_y ** (source_y + test_y)

which reduces to beta**0 for longitudinal (power 0) and beta**1 for the
transverse dipolar/quadrupolar terms (power 1). This single function is the one
place to revisit if the convention (e.g. a normalisation by a reference beta)
ever needs to change.
"""
from __future__ import annotations

from dataclasses import dataclass

PLANES = ("z", "x", "y")
MULTIPOLES = ("long", "dip", "quad")


@dataclass(frozen=True)
class TermId:
    """Multipole identity of a single impedance/wake term."""

    plane: str
    source: tuple[int, int]  # (sx, sy)
    test: tuple[int, int]    # (tx, ty)

    @property
    def power(self) -> int:
        """Total multipole order = sum of all exponents (0 = longitudinal)."""
        return sum(self.source) + sum(self.test)

    @property
    def category(self) -> str:
        """'long' | 'dip' | 'quad' derived from the exponents."""
        if self.power == 0:
            return "long"
        if sum(self.source) > 0:
            return "dip"
        return "quad"

    def beta_weight(self, beta_x: float, beta_y: float) -> float:
        """Weight applied to this term at a location with the given beta functions."""
        sx, sy = self.source
        tx, ty = self.test
        return beta_x ** (sx + tx) * beta_y ** (sy + ty)


#: The five standard machine-impedance terms, keyed by canonical id.
STANDARD_TERMS: dict[str, TermId] = {
    "zlong":  TermId("z", (0, 0), (0, 0)),
    "zxdip":  TermId("x", (1, 0), (0, 0)),
    "zydip":  TermId("y", (0, 1), (0, 0)),
    "zxquad": TermId("x", (0, 0), (1, 0)),
    "zyquad": TermId("y", (0, 0), (0, 1)),
}
