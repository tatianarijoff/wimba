"""The per-element file store must reproduce the in-memory Machine, with the
same scoping/weighting, while reading one element at a time."""
import numpy as np

from wimba import (Element, Machine, PreWeighted, Resonator, ResonatorProvider,
                   ResultStore, TwissTable, materialize)


def _machine():
    m = Machine(twiss=TwissTable({"c1": (10.0, 20.0), "c2": (30.0, 40.0), "p1": (5.0, 5.0)}))
    coll = m.add_group("collimators")
    coll.add(Element("c1", "collimator", 1.0, ResonatorProvider([
        Resonator("zlong", 100.0, 1.0, 1e9), Resonator("zxdip", 1.0, 1.0, 1e9)])))
    coll.add(Element("c2", "collimator", 1.0, ResonatorProvider([
        Resonator("zlong", 200.0, 1.0, 1.2e9)])))
    m.add_group("pipes").add(Element("p1", "pipe", 1.0, ResonatorProvider([
        Resonator("zlong", 40.0, 1.0, 0.9e9)])))
    m.add_additional(Element("crab", "additional", 1.0,
                             ResonatorProvider([Resonator("zlong", 70.0, 1.0, 0.8e9)]),
                             optics=PreWeighted()))
    return m


def test_store_reproduces_machine(tmp_path):
    m = _machine()
    f = np.linspace(0.2e9, 2.0e9, 80)
    t = np.linspace(0.0, 5.0e-9, 80)
    materialize(m, tmp_path / "results", freqs=f, times=t)
    store = ResultStore(tmp_path / "results")

    # per-element files exist and are self-contained
    assert (tmp_path / "results" / "collimators" / "c1" / "Z__resonator__zlong.dat").is_file()
    assert set(store.groups()) == {"collimators", "pipes"}

    # whole-machine impedance and wake match the in-memory computation
    Zmem, Zsto = m.impedance(f), store.impedance()
    assert set(Zmem) == set(Zsto)
    for k in Zmem:
        assert np.allclose(Zmem[k], Zsto[k])
    Wmem, Wsto = m.wake(t), store.wake()
    assert set(Wmem) == set(Wsto)
    for k in Wmem:
        assert np.allclose(Wmem[k], Wsto[k])


def test_store_scoping(tmp_path):
    m = _machine()
    f = np.linspace(0.2e9, 2.0e9, 80)
    materialize(m, tmp_path / "results", freqs=f)
    store = ResultStore(tmp_path / "results")

    # a single group in isolation ("all the pipes")
    assert np.allclose(
        m.impedance(f, groups=["pipes"], include_additional=False)["zlong"],
        store.impedance(groups=["pipes"], include_additional=False)["zlong"])
    # by multipole, and excluding the additional bucket
    assert np.allclose(
        m.impedance(f, multipole="dip", include_additional=False)["zxdip"],
        store.impedance(multipole="dip", include_additional=False)["zxdip"])
    # additional changes the longitudinal total
    with_add = store.impedance(multipole="long")["zlong"]
    without = store.impedance(multipole="long", include_additional=False)["zlong"]
    assert not np.allclose(with_add, without)
