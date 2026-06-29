"""Validate the wake <-> impedance transforms against the analytic resonator,
which pins the sign/factor conventions to a known pair."""
import numpy as np

from wimba import Element, Resonator, ResonatorProvider
from wimba.analysis import FourierTransform as FT


def _term(term, Rs=1.0e6, Q=1.0, fr=1.0e9):
    el = Element("e", "x", 1.0, ResonatorProvider([Resonator(term, Rs, Q, fr)]))
    return el.terms()[0]


def _rel(a, b):
    return np.max(np.abs(a - b)) / np.max(np.abs(b))


def test_wake_to_impedance_longitudinal():
    wt = _term("zlong")
    t = np.linspace(0.0, 12e-9, 6000)
    f = np.linspace(0.2e9, 2.0e9, 60)
    Z = FT.impedance_from_wake(t, wt.wake(t), f, plane="z")
    assert _rel(Z, wt.impedance(f)) < 1e-3


def test_wake_to_impedance_transverse():
    wt = _term("zxdip")
    t = np.linspace(0.0, 12e-9, 6000)
    f = np.linspace(0.2e9, 2.0e9, 60)
    Z = FT.impedance_from_wake(t, wt.wake(t), f, plane="x")
    assert _rel(Z, wt.impedance(f)) < 1e-3


def test_impedance_to_wake_transverse():
    wt = _term("zxdip")
    f = np.linspace(1e6, 2.0e10, 8000)
    t = np.linspace(0.05e-9, 6.0e-9, 60)
    W = FT.wake_from_impedance(f, wt.impedance(f), t, plane="x")
    assert _rel(W, wt.wake(t)) < 5e-3


def test_impedance_to_wake_longitudinal_converges():
    # the step at t=0 makes Z ~ 1/f; a correct transform is truncation-limited,
    # so the error must shrink as the upper frequency grows
    wt = _term("zlong")
    t = np.linspace(0.05e-9, 6.0e-9, 60)
    Wa = wt.wake(t)
    errs = []
    for fmax, n in [(2.0e10, 8000), (1.0e11, 40000)]:
        f = np.linspace(1e6, fmax, n)
        W = FT.wake_from_impedance(f, wt.impedance(f), t, plane="z")
        errs.append(_rel(W, Wa))
    assert errs[1] < errs[0] < 0.1
