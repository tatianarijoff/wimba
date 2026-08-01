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


def test_iw2d_clear_error_when_not_installed(monkeypatch):
    """Without IW2D importable the error names the C++ dependencies too: the
    usual cause is a missing GSL/MPFR/Arb, not a missing IW2D."""
    import builtins
    real_import = builtins.__import__

    def no_iw2d(name, *a, **kw):
        if name.startswith("IW2D"):
            raise ImportError("No module named 'IW2D'")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", no_iw2d)
    with pytest.raises(ImportError, match="IW2D is required"):
        compute_iw2d(np.logspace(6, 9, 4), radius_m=0.02)


def test_iw2d_layer_conversion_applies_the_unit_traps():
    """The pytlwall -> IW2D conversion is where the comparison can silently go
    wrong: muinf is a relative permeability, IW2D wants a susceptibility."""
    pytest.importorskip("IW2D")
    from IW2D.interface import (IW2DLayer, Eps1FromResistivity,
                                Mu1FromSusceptibility)
    from wimba.sources.iw2d_bridge import _one_layer

    def build(d):
        return _one_layer(d, IW2DLayer, Eps1FromResistivity, Mu1FromSusceptibility)

    # ferrite: mu_r = 460 at DC, relaxing at 20 MHz
    lay = build({"type": "CW", "thickness": 0.015, "sigma": 1e-4,
                 "epsr": 12.0, "muinf_Hz": 460.0, "k_Hz": 20e6})
    assert lay.thickness == 0.015
    assert lay.mu1.magnetic_susceptibility == pytest.approx(459.0)  # mu_r - 1
    assert abs(lay.mu1(1.0) - 460.0) < 1e-3        # chi + 1 = mu_r at low f
    # single-pole relaxation: above the cut-off the deviation from 1 falls as
    # chi*f_mu/f, so it is still ~1e-2 at 1 THz and only ~1e-5 at 1 PHz
    assert abs(lay.mu1(1e12) - 1.0) == pytest.approx(459.0 * 20e6 / 1e12, rel=1e-3)
    assert abs(lay.mu1(1e15) - 1.0) < 1e-4
    assert abs(lay.eps1(1e12).real - 12.0) < 1e-6  # epsr passes through
    # sigma became a resistivity, not a conductivity
    assert lay.eps1.dc_resistivity == pytest.approx(1e4)

    # vacuum carries no conductivity and no magnetisation
    vac = build({"type": "V", "thickness": 0.002})
    assert vac.mu1(1e6) == 1.0
    assert vac.eps1(1e6) == 1.0

    # tau reaches IW2D instead of being silently dropped
    cu = build({"type": "CW", "thickness": 0.002, "sigma": 5.96e7, "tau": 2.7e-14})
    assert cu.eps1.resistivity_relaxation_time == pytest.approx(2.7e-14)


def test_iw2d_pec_is_reported_as_an_approximation():
    """IW2D has no PEC layer. The substitution must be visible to the caller,
    not silent: a PEC result from IW2D is an approximation."""
    pytest.importorskip("IW2D")
    from wimba.sources.iw2d_bridge import compute_iw2d, PEC_RESISTIVITY

    layers = [{"type": "CW", "thickness": 0.002, "sigma": 1e6},
              {"type": "PEC", "thickness": 0.01}]
    _out, notes = compute_iw2d(np.logspace(6, 8, 3), radius_m=0.02,
                               layers=layers, return_notes=True)
    assert notes and "no perfect-conductor layer" in notes[0]
    assert f"{PEC_RESISTIVITY:g}" in notes[0]


def test_iw2d_rejects_non_circular_shapes():
    pytest.importorskip("IW2D")
    from wimba.sources.iw2d_bridge import compute_iw2d
    with pytest.raises(ValueError, match="circular chambers"):
        compute_iw2d(np.logspace(6, 9, 4), radius_m=0.02, shape="RECTANGULAR")
