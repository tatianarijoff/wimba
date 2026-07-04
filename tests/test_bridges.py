"""Resonator / precalculated / iw2d bridges."""
import numpy as np
import pytest

from wimba.sources.resonator import resonator_impedance, resonator_wake
from wimba.sources.precalculated_bridge import (precalculated_impedance,
                                                precalculated_wake)
from wimba.sources.iw2d_bridge import compute_iw2d
from wimba.io.tables import write_impedance, write_wake


def test_resonator_impedance_at_resonance():
    modes = [{"Rl": 1000.0, "Ql": 1.0, "fl": 1e9,
              "Rxd": 5e5, "Qxd": 1.0, "fxd": 1e9}]
    f = np.array([1e9])                       # exactly at resonance
    z = resonator_impedance(f, modes)
    assert np.isclose(z["ZLong"][0], 1000.0)  # longitudinal peaks at Rs
    # transverse scales with beta
    z2 = resonator_impedance(f, modes, betax=2.0)
    assert np.isclose(z2["ZDipX"][0], 2.0 * z["ZDipX"][0])


def test_resonator_wake_finite_and_beta():
    modes = [{"Rl": 1000.0, "Ql": 1.5, "fl": 1e9, "Ryd": 4e5, "Qyd": 1.2, "fyd": 1e9}]
    t = np.linspace(0.0, 5e-9, 50)
    w = resonator_wake(t, modes)
    assert np.all(np.isfinite(w["WLong"])) and np.all(np.isfinite(w["WDipY"]))
    w2 = resonator_wake(t, modes, betay=3.0)
    assert np.allclose(w2["WDipY"], 3.0 * w["WDipY"])


def test_precalculated_roundtrip(tmp_path):
    f = np.logspace(6, 9, 40)
    z = 1.0 / f + 1j * 2.0 / f
    write_impedance(tmp_path / "ZLong.dat", f, z, "z")
    fq = np.logspace(6, 9, 20)
    out = precalculated_impedance(fq, {"ZLong": tmp_path / "ZLong.dat"})
    assert np.allclose(out["ZLong"].real, 1.0 / fq, rtol=1e-3)

    t = np.linspace(0, 5e-9, 30)
    write_wake(tmp_path / "WLong.dat", t, np.exp(-t / 1e-9), "z")
    wo = precalculated_wake(t, {"WLong": tmp_path / "WLong.dat"})
    assert np.allclose(wo["WLong"], np.exp(-t / 1e-9), rtol=1e-6)


def test_iw2d_clear_error_when_unconfigured(monkeypatch):
    monkeypatch.delenv("IW2D_BINARY", raising=False)
    monkeypatch.setattr("wimba.sources.iw2d_bridge._iw2d_available", lambda: False)
    with pytest.raises(RuntimeError, match="IW2D is not configured"):
        compute_iw2d(np.logspace(6, 9, 4), radius_m=0.02)
