"""Core data-model tests: beta weighting, two populations, selection."""
import numpy as np

from wimba import (Element, Machine, PreWeighted, Resonator, ResonatorProvider,
                   TwissTable)


def _long_el(name, Rs, Q=1.0, fr=1e9, category="collimator"):
    return Element(name, category, 1.0, ResonatorProvider([Resonator("zlong", Rs, Q, fr)]))


def test_longitudinal_no_beta_weighting():
    # longitudinal -> power 0 -> plain sum, no beta involved
    m = Machine(twiss=TwissTable({"c1": (10.0, 20.0), "c2": (30.0, 40.0)}))
    g = m.add_group("collimators")
    g.add(_long_el("c1", 100.0))
    g.add(_long_el("c2", 200.0))
    Z = m.impedance(np.array([1e9]), multipole="long")   # at resonance Z = Rs (real)
    assert set(Z) == {"zlong"}
    assert np.isclose(Z["zlong"][0].real, 300.0)
    assert np.isclose(Z["zlong"][0].imag, 0.0)


def test_transverse_beta_weighting():
    # zxdip weights with beta_x
    m = Machine(twiss=TwissTable({"k1": (50.0, 5.0)}))
    m.add_group("kickers").add(
        Element("k1", "kicker", 1.0, ResonatorProvider([Resonator("zxdip", 1.0, 1.0, 1e9)])))
    Z = m.impedance(np.array([1e9]), multipole="dip")    # at resonance Z = Rs = 1
    assert np.isclose(Z["zxdip"][0].real, 50.0)          # 1 * beta_x


def test_additional_pre_weighted_kept_separate():
    m = Machine(twiss=TwissTable({"c1": (10.0, 20.0)}))
    m.add_group("collimators").add(_long_el("c1", 100.0))
    # pre-weighted -> summed as-is, no twiss entry needed
    m.add_additional(Element("future_crab", "additional", 1.0,
                             ResonatorProvider([Resonator("zlong", 70.0, 1.0, 1e9)]),
                             optics=PreWeighted()))
    f = np.array([1e9])
    with_add = m.impedance(f, multipole="long")["zlong"][0].real
    without = m.impedance(f, multipole="long", include_additional=False)["zlong"][0].real
    assert np.isclose(without, 100.0)
    assert np.isclose(with_add, 170.0)


def test_selection_quantity_and_terms():
    m = Machine(twiss=TwissTable({"c1": (10.0, 20.0)}))
    m.add_group("collimators").add(
        Element("c1", "collimator", 1.0, ResonatorProvider([
            Resonator("zlong", 100.0, 1.0, 1e9),
            Resonator("zxdip", 1.0, 1.0, 1e9),
        ])))
    f, t = np.array([1e9]), np.array([0.0, 1e-9])
    assert set(m.impedance(f, multipole="long")) == {"zlong"}        # only long Z
    W = m.wake(t, multipole="long")                                  # only long W
    assert set(W) == {"zlong"} and W["zlong"][0] > 0                 # W(0) = alpha*Rs > 0
    assert set(m.impedance(f)) == {"zlong", "zxdip"}                 # all terms
    assert set(m.wake(t)) == {"zlong"}                               # transverse has no W -> skipped


def test_group_scope():
    m = Machine(twiss=TwissTable({"c1": (10.0, 20.0), "p1": (10.0, 20.0)}))
    m.add_group("collimators").add(_long_el("c1", 100.0))
    m.add_group("pipes").add(_long_el("p1", 40.0, category="pipe"))
    f = np.array([1e9])
    only_coll = m.impedance(f, groups=["collimators"], include_additional=False)["zlong"][0].real
    everything = m.impedance(f)["zlong"][0].real
    assert np.isclose(only_coll, 100.0)
    assert np.isclose(everything, 140.0)


if __name__ == "__main__":
    for _n, _f in list(globals().items()):
        if _n.startswith("test_") and callable(_f):
            _f()
            print(f"ok  {_n}")
    print("all passed")
