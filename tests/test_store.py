"""The store writes per-element files, a resume, and totals, and the lazy
aggregator reproduces the in-memory machine."""
import numpy as np

from wimba import (Element, Explicit, Machine, PreWeighted, Project, Resonator,
                   ResonatorProvider, ResultStore, TwissTable, materialize)


def _project():
    m = Machine(twiss=TwissTable())
    coll = m.add_group("collimators")
    coll.add(Element("c1", "collimator", 1.0,
                     ResonatorProvider([Resonator("zlong", 1e4, 1.0, 1e9),
                                        Resonator("zxdip", 1e6, 1.0, 1e9)]),
                     optics=Explicit(130.0, 85.0),
                     meta={"position": 100.0, "beta_x": 130.0, "beta_y": 85.0,
                           "info": {"length": 0.6, "material": "CFC"}}))
    coll.add(Element("c2", "collimator", 1.0,
                     ResonatorProvider([Resonator("zlong", 2e4, 1.0, 1.2e9)]),
                     optics=Explicit(110.0, 160.0),
                     meta={"position": 145.0, "beta_x": 110.0, "beta_y": 160.0,
                           "info": {"length": 1.0}}))
    m.add_additional(Element("crab", "rf", 1.0,
                             ResonatorProvider([Resonator("zlong", 7e3, 1.0, 0.8e9)]),
                             optics=PreWeighted(),
                             meta={"position": None, "beta_x": None, "beta_y": None,
                                   "info": {"pre_weighted": True}}))
    f = np.linspace(0.2e9, 2.0e9, 60)
    t = np.linspace(0.0, 5.0e-9, 60)
    return Project("Demo", m, f, t)


def test_resume_totals_and_aggregation(tmp_path):
    p = _project()
    materialize(p, tmp_path / "out")

    # resume + totals exist and are named after the project
    assert (tmp_path / "out" / "Demo_resume.yaml").is_file()
    assert (tmp_path / "out" / "total" / "TOT_ZLong.dat").is_file()
    assert (tmp_path / "out" / "collimators" / "c1" / "c1_res_ZDipX.dat").is_file()

    store = ResultStore(tmp_path / "out")
    assert set(store.resume["components"]) == {"ZLong", "ZDipX"}

    # lazy aggregation reproduces the in-memory machine (with beta weighting)
    Zmem, Zsto = p.machine.impedance(p.freqs), store.impedance()
    assert set(Zmem) == set(Zsto)
    for k in Zmem:
        assert np.allclose(Zmem[k], Zsto[k])
    Wmem, Wsto = p.machine.wake(p.times), store.wake()
    for k in Wmem:
        assert np.allclose(Wmem[k], Wsto[k])

    # the total files equal the aggregated totals
    _, tot = np.loadtxt(tmp_path / "out" / "total" / "TOT_ZLong.dat", unpack=True)[:1], None
    f, reZ, imZ = np.loadtxt(tmp_path / "out" / "total" / "TOT_ZLong.dat", unpack=True)
    assert np.allclose(reZ + 1j * imZ, Zsto["zlong"], rtol=1e-4)


def test_scoping_and_origin(tmp_path):
    p = _project()
    materialize(p, tmp_path / "out")
    store = ResultStore(tmp_path / "out")

    # exclude the pre-weighted additional
    with_add = store.impedance(multipole="long")["zlong"]
    without = store.impedance(multipole="long", include_additional=False)["zlong"]
    assert not np.allclose(with_add, without)
    # single group
    assert np.allclose(
        p.machine.impedance(p.freqs, groups=["collimators"], include_additional=False)["zxdip"],
        store.impedance(groups=["collimators"], include_additional=False)["zxdip"])
