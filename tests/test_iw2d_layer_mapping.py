"""How a WIMBA layer becomes an IW2D layer.

The two engines are only worth comparing if the same wall reaches both. These
tests pin the conversions that are easy to get backwards - and one that was.
"""
import pytest

from wimba.sources.iw2d_bridge import _one_layer


class _Eps1FromResistivity:
    def __init__(self, dc_resistivity, resistivity_relaxation_time,
                 re_dielectric_constant):
        self.seen = dict(rho=dc_resistivity, tau=resistivity_relaxation_time,
                         epsr=re_dielectric_constant)
        _seen.update(self.seen)


class _Mu1FromSusceptibility:
    def __init__(self, magnetic_susceptibility,
                 permeability_relaxation_frequency):
        _seen.update(chi=magnetic_susceptibility,
                     k=permeability_relaxation_frequency)


class _IW2DLayer:
    def __init__(self, thickness, eps1, mu1):
        _seen.update(thickness=thickness)


_seen: dict = {}


def build(layer):
    """Run the bridge's conversion with stand-ins for IW2D's own classes, so
    the mapping can be checked without IW2D installed."""
    _seen.clear()
    _one_layer(layer, _IW2DLayer, _Eps1FromResistivity, _Mu1FromSusceptibility)
    return dict(_seen)


def test_a_non_magnetic_wall_is_not_turned_into_a_hole():
    """pytlwall computes mur = 1 + muinf/(1 + j f/k), so muinf IS the
    susceptibility. Subtracting one made the default muinf = 0 into chi = -1,
    a relative permeability of zero, on every ordinary metal."""
    assert build({"type": "CW", "sigma": 2.0e5,
                  "thickness": "inf"})["chi"] == pytest.approx(0.0)


def test_a_magnetic_layer_keeps_its_susceptibility():
    seen = build({"type": "CW", "sigma": 1.0e6, "muinf_Hz": 500.0,
                  "k_Hz": 1.0e4, "thickness": 0.001})
    assert seen["chi"] == pytest.approx(500.0)
    assert seen["k"] == pytest.approx(1.0e4)


def test_conductivity_becomes_resistivity():
    seen = build({"type": "CW", "sigma": 2.0e5, "thickness": "inf"})
    assert seen["rho"] == pytest.approx(5.0e-6)


def test_the_relaxation_time_passes_through_in_seconds():
    """IW2D's own RoundChamber input states 4.2 ps for this wall."""
    seen = build({"type": "CW", "sigma": 2.0e5, "tau": 4.2e-12,
                  "thickness": "inf"})
    assert seen["tau"] == pytest.approx(4.2e-12)


def test_a_vacuum_layer_is_empty_space_not_a_magnet():
    seen = build({"type": "V", "thickness": "inf"})
    assert seen["chi"] == pytest.approx(0.0)
    assert seen["epsr"] == pytest.approx(1.0)
