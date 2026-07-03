"""Per-device / totals CSV layout, and plotting the totals from file."""
import numpy as np
import pytest

from wimba.output import read_totals, write_single_element, write_totals


def test_single_element_and_totals_layout(tmp_path):
    f = np.logspace(6, 9, 12)
    a = {"ZLong": np.ones(12) + 0j, "ZDipX": 2 * np.ones(12) + 1j}
    b = {"ZLong": 3 * np.ones(12) + 0j, "ZDipX": 4 * np.ones(12) - 1j}
    write_single_element(tmp_path / "out", "collimators", "TCP.C6L7.B1", f, a)
    write_single_element(tmp_path / "out", "collimators", "TCSG.A6L7.B1", f, b)
    write_totals(tmp_path / "out", f, {k: a[k] + b[k] for k in a})

    se = tmp_path / "out" / "single_elements"
    assert (se / "collimators" / "TCP.C6L7.B1.csv").is_file()
    assert (se / "total.csv").is_file()

    fr, comps = read_totals(se / "total.csv")
    assert np.allclose(fr, f)
    assert np.allclose(comps["ZLong"], 4) and np.allclose(comps["ZDipX"], 6 + 0j)


def test_plot_totals_saves_png(tmp_path):
    pytest.importorskip("matplotlib")
    from wimba.plotting import plot_totals
    f = np.logspace(6, 9, 20)
    write_totals(tmp_path / "out", f, {"ZLong": 1 / f + 0j, "ZDipX": 10 / f + 0j})
    out = plot_totals(tmp_path / "out" / "single_elements" / "total.csv",
                      components=["ZLong"], save=tmp_path / "p.png")
    assert out.is_file() and out.stat().st_size > 0


def test_chamber_terms_beta_weighting(tmp_path):
    pytest.importorskip("pytlwall")
    from wimba.sources.pytlwall_bridge import chamber_terms
    from wimba.output import write_single_element, write_totals
    f = np.logspace(6, 9, 8)
    t1 = chamber_terms(f, radius_m=0.02, length_m=1.0, betax=1.0, betay=1.0)
    t2 = chamber_terms(f, radius_m=0.02, length_m=1.0, betax=2.0, betay=1.0)
    assert np.allclose(t2["ZDipX"], 2 * t1["ZDipX"], rtol=1e-6)   # dip scales with beta
    assert np.allclose(t2["ZLong"], t1["ZLong"], rtol=1e-9)       # long does not
    # end-to-end: two single elements -> structure + totals
    write_single_element(tmp_path / "o", "pipes", "e1", f, t1)
    write_single_element(tmp_path / "o", "pipes", "e2", f, t2)
    write_totals(tmp_path / "o", f, {c: t1[c] + t2[c] for c in t1})
    assert (tmp_path / "o" / "single_elements" / "total.csv").is_file()
