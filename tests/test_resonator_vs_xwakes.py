"""Compare the WIMBA resonator source against xwakes term by term.

Skipped automatically if xwakes is not installed (it is in the `dev` extra).
"""
import numpy as np
import pytest

from wimba import Element, Resonator, ResonatorProvider

component = pytest.importorskip("xwakes.wit.component")
ComponentResonator = component.ComponentResonator

CASES = [
    ("zlong",  "z", (0, 0), (0, 0)),
    ("zxdip",  "x", (1, 0), (0, 0)),
    ("zydip",  "y", (0, 1), (0, 0)),
    ("zxquad", "x", (0, 0), (1, 0)),
    ("zyquad", "y", (0, 0), (0, 1)),
]


def _wimba_term(term, Rs, Q, fr):
    el = Element("e", "x", 1.0, ResonatorProvider([Resonator(term, Rs, Q, fr)]))
    return el.terms()[0]


@pytest.mark.parametrize("term,plane,se,te", CASES)
def test_resonator_matches_xwakes(term, plane, se, te):
    Rs, Q, fr = 1.0e6, 1.0, 1.0e9
    f = np.logspace(7, 10, 300)
    t = np.linspace(0.0, 8.0e-9, 500)

    wt = _wimba_term(term, Rs, Q, fr)
    cc = ComponentResonator(plane=plane, source_exponents=se, test_exponents=te,
                            r=Rs, q=Q, f_r=fr)

    rel_Z = np.max(np.abs(wt.impedance(f) - cc.impedance(f))) / np.max(np.abs(cc.impedance(f)))
    rel_W = np.max(np.abs(wt.wake(t) - cc.wake(t))) / np.max(np.abs(cc.wake(t)))
    assert rel_Z < 1e-9
    assert rel_W < 1e-9


def test_resonator_matches_xwakes_overdamped():
    # Q < 1/2: the complex damped frequency must reproduce the hyperbolic form
    Rs, Q, fr = 1.0e6, 0.3, 1.0e9
    t = np.linspace(0.0, 8.0e-9, 500)
    wt = _wimba_term("zxdip", Rs, Q, fr)
    cc = ComponentResonator(plane="x", source_exponents=(1, 0), test_exponents=(0, 0),
                            r=Rs, q=Q, f_r=fr)
    rel_W = np.max(np.abs(wt.wake(t) - cc.wake(t))) / np.max(np.abs(cc.wake(t)))
    assert rel_W < 1e-9
    assert not np.any(np.isnan(wt.wake(t)))
