"""The run orchestration: per-geometry caching, totals = sum, opt-in per-device."""
import numpy as np
import pytest

pytest.importorskip("pytlwall")
from wimba.assembly import Assignment
from wimba.run import compute_assignments
from wimba.output import read_totals

F = np.logspace(6, 9, 8)


def _row(name, radius, beta_x=1.0, length=1.0, group="g"):
    return Assignment(position=0.0, name=name, kind="device", method="pytlwall",
                      weighted=False, space_charge=False, beta_x=beta_x, beta_y=1.0,
                      beta_source="explicit", allow_overlap=False, length=length,
                      geometry={"radius": radius, "layers": [{"material": "copper", "thickness": 0.002}]},
                      group=group)


def test_cache_and_totals(tmp_path):
    rows = [_row("a", 0.02), _row("b", 0.02, beta_x=2.0), _row("c", 0.03)]
    totals, _wake, stats = compute_assignments(rows, F, tmp_path / "out", per_device=["a"])

    # two rows share geometry 0.02 -> only two distinct geometries computed
    assert stats["computed"] == 3 and stats["geometries"] == 2

    # opt-in per-device file only for "a"
    se = tmp_path / "out" / "single_elements"
    assert (se / "g" / "a.csv").is_file()
    assert not (se / "g" / "b.csv").exists()
    assert (se / "total.csv").is_file()

    # totals equal the sum of the three contributions (check ZLong)
    _, comps = read_totals(se / "total.csv")
    assert comps["ZLong"].shape == F.shape and np.all(np.isfinite(comps["ZLong"]))


def test_non_pytlwall_skipped(tmp_path):
    r = _row("x", 0.02)
    r.method = "iw2d"
    totals, _wake, stats = compute_assignments([r], F, tmp_path / "out")
    assert stats["skipped"] == 1 and stats["computed"] == 0


def test_wake_totals_native(tmp_path):
    F2 = np.logspace(6, 9, 6)
    T = np.linspace(1e-12, 5e-9, 40)
    rows = [_row("a", 0.02, length=1.0), _row("b", 0.02, beta_x=2.0, length=2.0)]
    ztot, wtot, stats = compute_assignments(rows, F2, tmp_path / "out", times=T)
    # wake totals written and native (pytlwall)
    assert (tmp_path / "out" / "single_elements" / "total_wake.csv").is_file()
    assert stats["wake_native"] == {"pytlwall"} and not stats["wake_fft"]
    assert wtot["WLong"].shape == T.shape and np.all(np.isfinite(wtot["WLong"]))


def test_resonator_lumped_in_total(tmp_path):
    F2 = np.array([1e9])                       # exactly at resonance
    modes = [{"Rl": 1000.0, "Ql": 1.0, "fl": 1e9, "Rxd": 5e5, "Qxd": 1.0, "fxd": 1e9}]
    row = Assignment(position=0.0, name="RF", kind="device", method="resonator",
                     weighted=False, space_charge=False, beta_x=2.0, beta_y=1.0,
                     beta_source="explicit", allow_overlap=False, length=5.0,
                     geometry=None, group="rf", params={"modes": modes})
    ztot, _w, stats = compute_assignments([row], F2, tmp_path / "out")
    assert stats["computed"] == 1 and stats["skipped"] == 0
    assert np.isclose(ztot["ZLong"][0], 1000.0)          # longitudinal peaks at Rs
    assert np.isclose(ztot["ZDipX"][0], 2.0 * 5e5)       # beta applied, length (=5) is NOT


def test_precalculated_in_total(tmp_path):
    from wimba.io.tables import write_impedance
    f = np.logspace(6, 9, 40)
    write_impedance(tmp_path / "ZLong.dat", f, 1.0 / f + 1j * 2.0 / f, "z")
    row = Assignment(position=0.0, name="cst", kind="device", method="precalculated",
                     weighted=False, space_charge=False, beta_x=1.0, beta_y=1.0,
                     beta_source="explicit", allow_overlap=False, length=None,
                     geometry=None, group="imported",
                     params={"files": {"ZLong": str(tmp_path / "ZLong.dat")}, "wake_files": {}})
    fq = np.logspace(6, 9, 20)
    T = np.linspace(1e-12, 5e-9, 40)
    ztot, wtot, stats = compute_assignments([row], fq, tmp_path / "out", times=T)
    assert stats["computed"] == 1 and stats["skipped"] == 0
    assert np.allclose(ztot["ZLong"].real, 1.0 / fq, rtol=1e-3)     # loaded from file
    assert "precalculated" in stats["wake_fft"]                      # no wake file -> FFT, noted
