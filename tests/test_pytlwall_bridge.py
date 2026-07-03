"""Single-chamber pytlwall calculation: the physics facts WIMBA relies on.

ZLong scales linearly with length, ZDipX scales linearly with beta (so computing
at beta=1 and weighting later is exact), the wall + space-charge terms are all
present, and Total = wall + ISC.
"""
import numpy as np
import pytest

pytest.importorskip("pytlwall")
from wimba.sources.pytlwall_bridge import compute_chamber

FREQS = np.logspace(5, 9, 8)


def test_zlong_linear_in_length():
    z1 = compute_chamber(FREQS, radius_m=0.02, length_m=1.0)["ZLong"]
    z2 = compute_chamber(FREQS, radius_m=0.02, length_m=2.0)["ZLong"]
    assert np.allclose(z2, 2.0 * z1, rtol=1e-6)


def test_dipole_linear_in_beta():
    z1 = compute_chamber(FREQS, radius_m=0.02, betax=1.0)["ZDipX"]
    z2 = compute_chamber(FREQS, radius_m=0.02, betax=2.0)["ZDipX"]
    assert np.allclose(z2, 2.0 * z1, rtol=1e-6)
    # longitudinal must NOT depend on beta
    zl1 = compute_chamber(FREQS, radius_m=0.02, betax=1.0)["ZLong"]
    zl2 = compute_chamber(FREQS, radius_m=0.02, betax=2.0)["ZLong"]
    assert np.allclose(zl1, zl2, rtol=1e-9)


def test_wall_and_space_charge_present():
    imp = compute_chamber(FREQS, radius_m=0.02)
    for key in ("ZLong", "ZDipX", "ZDipY", "ZQuadX", "ZQuadY",
                "ZLongISC", "ZDipISC", "ZLongDSC"):
        assert key in imp
    # pytlwall convention: total = wall + indirect space charge
    assert np.allclose(imp["ZLongTotal"], imp["ZLong"] + imp["ZLongISC"], rtol=1e-6)


def test_multilayer_collimator_like():
    layers = [{"material": "cfc", "thickness": 0.025}]
    imp = compute_chamber(FREQS, radius_m=0.003, layers=layers, length_m=1.0)
    assert np.all(np.isfinite(imp["ZLong"]))
