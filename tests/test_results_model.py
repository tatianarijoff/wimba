"""ResultsModel: lists what a run computed (total, wake, per-device) and serves
series for the plot/table workspace."""
import numpy as np

from wimba.output import write_single_element, write_totals, write_wake_totals
from wimba.gui.results import ResultsModel, decode, encode


def _fake_output(tmp_path):
    f = np.logspace(6, 9, 12)
    t = np.linspace(1e-12, 5e-9, 10)
    write_totals(tmp_path, f, {"ZLong": 1 / f + 2j / f, "ZLongISC": 5j / f})
    write_wake_totals(tmp_path, t, {"WLong": np.exp(-t / 1e-9)})
    write_single_element(tmp_path, "collimators", "TCP", f, {"ZLong": 3 / f + 0j})
    return f, t


def test_model_lists_sources_and_series(tmp_path):
    f, t = _fake_output(tmp_path)
    m = ResultsModel().load(tmp_path)

    assert set(m.sources) == {"Total", "collimators/TCP"}
    assert set(m.sources["Total"]) == {"impedance", "wake"}

    x, y, label = m.series("Total", "impedance", "ZLong", "Im")
    assert np.allclose(x, f) and np.allclose(y, 2 / f) and "Im" in label
    x, y, _ = m.series("Total", "impedance", "ZLongISC", "|Z|")
    assert np.allclose(y, 5 / f)                     # ISC visible as its own quantity
    x, y, _ = m.series("Total", "wake", "WLong")
    assert np.allclose(x, t) and np.allclose(y, np.exp(-t / 1e-9))
    x, y, _ = m.series("collimators/TCP", "impedance", "ZLong", "Re")
    assert np.allclose(y, 3 / f)


def test_encode_decode_roundtrip():
    ref = encode("collimators/TCP", "impedance", "ZDipX", "|Z|")
    assert decode(ref) == ("collimators/TCP", "impedance", "ZDipX", "|Z|")


def test_model_derives_wall_plus_isc(tmp_path):
    f = np.logspace(6, 9, 8)
    write_totals(tmp_path, f, {"ZLong": 1 / f + 0j, "ZLongISC": 0 + 4j / f,
                               "ZDipX": 2 / f + 0j})
    m = ResultsModel().load(tmp_path)
    _x, comps = m.sources["Total"]["impedance"]
    assert "ZLong+ISC" in comps                       # wall + ISC derived
    assert np.allclose(comps["ZLong+ISC"], 1 / f + 4j / f)
    assert "ZDipX+ISC" not in comps                   # no ISC -> no derived sum
