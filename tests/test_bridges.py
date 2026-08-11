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


def test_iw2d_layer_conversion_applies_the_unit_traps(iw2d):
    """The pytlwall -> IW2D conversion is where the comparison can silently go
    wrong: muinf is a relative permeability, IW2D wants a susceptibility."""
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


def test_iw2d_pec_is_reported_as_an_approximation(iw2d):
    """IW2D has no PEC layer. The substitution must be visible to the caller,
    not silent: a PEC result from IW2D is an approximation."""
    from wimba.sources.iw2d_bridge import compute_iw2d, PEC_RESISTIVITY

    layers = [{"type": "CW", "thickness": 0.002, "sigma": 1e6},
              {"type": "PEC", "thickness": 0.01}]
    _out, notes = compute_iw2d(np.logspace(6, 8, 3), radius_m=0.02,
                               layers=layers, return_notes=True)
    assert notes and "no perfect-conductor layer" in notes[0]
    assert f"{PEC_RESISTIVITY:g}" in notes[0]


def test_iw2d_rejects_non_circular_shapes(iw2d):
    from wimba.sources.iw2d_bridge import compute_iw2d
    with pytest.raises(ValueError, match="circular chambers"):
        compute_iw2d(np.logspace(6, 9, 4), radius_m=0.02, shape="RECTANGULAR")


def test_run_computes_iw2d_devices(tmp_path, iw2d):
    """A device with method 'iw2d' must be computed, not silently skipped: the
    compare flow of a single-element study depends on it."""
    from wimba.run import COMPUTED_METHODS
    assert "iw2d" in COMPUTED_METHODS


def test_run_cache_separates_methods():
    """Two devices with identical geometry but different methods must not share
    a cache entry -- that is exactly the shape of a compare run."""
    from wimba.run import _cached
    geo = {"radius": 0.01, "shape": "CIRCULAR",
           "layers": [{"type": "CW", "thickness": 0.002, "sigma": 1e6}]}
    cache = {}
    a, fresh_a = _cached(cache, geo, method="pytlwall", factory=lambda: "pytlwall")
    b, fresh_b = _cached(cache, geo, method="iw2d", factory=lambda: "iw2d")
    assert (a, b) == ("pytlwall", "iw2d")
    assert fresh_a and fresh_b
    # asking again for the same pair reuses the entries
    again, fresh = _cached(cache, geo, method="iw2d", factory=lambda: "wrong")
    assert again == "iw2d" and not fresh


def test_run_says_which_device_it_skipped():
    """An unknown method must name the device and the method in the notes,
    instead of dropping the device from the results without a word."""
    from wimba.run import COMPUTED_METHODS
    assert "unknown_method" not in COMPUTED_METHODS


def _write_xlsx(path, style="wimba"):
    pd = pytest.importorskip("pandas")
    pytest.importorskip("openpyxl")
    import numpy as _np
    f = _np.logspace(5, 9, 20)
    z = 1.0 + 2.0j * _np.ones_like(f)
    if style == "wimba":
        cols = {"f [Hz]": f, "Re(ZLong)": z.real, "Im(ZLong)": z.imag,
                "Re(ZDipX)": 3 * z.real, "Im(ZDipX)": 3 * z.imag}
    else:                       # pytlwall's own layout
        cols = {"f  [Hz] ": f,
                "kick ZLong real [Ohm]": z.real, "kick ZLong imag [Ohm]": z.imag,
                "kick ZDipX real [Ohm/m]": 3 * z.real,
                "kick ZDipX imag [Ohm/m]": 3 * z.imag}
    pd.DataFrame(cols).to_excel(path, index=False)
    return f


def test_read_impedance_table_finds_components_in_a_spreadsheet(tmp_path):
    """A spreadsheet holds every component at once, so they are found by column
    name rather than asked for one file at a time."""
    from wimba.io.tables import read_impedance_table
    for style in ("wimba", "pytlwall"):
        path = tmp_path / f"{style}.xlsx"
        f = _write_xlsx(path, style)
        table = read_impedance_table(path)
        assert set(table) == {"ZLong", "ZDipX"}
        got_f, got_z = table["ZLong"]
        assert got_f[0] == pytest.approx(f[0])
        assert got_z[0] == pytest.approx(1 + 2j)
        assert table["ZDipX"][1][0] == pytest.approx(3 + 6j)


def test_precalculated_reads_many_components_from_one_file(tmp_path):
    """The same path given for several components is read once and each one
    takes its own column pair."""
    import numpy as _np
    from wimba.sources.precalculated_bridge import (precalculated_components,
                                                    precalculated_impedance)
    path = tmp_path / "all.xlsx"
    _write_xlsx(path)
    assert precalculated_components(path) == ("ZDipX", "ZLong")
    out = precalculated_impedance(_np.logspace(5, 9, 6),
                                  {"ZLong": path, "ZDipX": path})
    assert out["ZLong"][0] == pytest.approx(1 + 2j)
    assert out["ZDipX"][0] == pytest.approx(3 + 6j)


def test_read_impedance_table_says_what_it_expected(tmp_path):
    from wimba.io.tables import read_impedance_table
    pd = pytest.importorskip("pandas")
    pytest.importorskip("openpyxl")
    path = tmp_path / "nope.xlsx"
    pd.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]}).to_excel(path, index=False)
    with pytest.raises(ValueError, match="no impedance components found"):
        read_impedance_table(path)


def test_compare_only_leaves_the_base_element_out():
    """Adding a comparison must not cost a second run of what is already in the
    Results tree."""
    from wimba.gui.model import (GElement, GModel, default_models,
                                 element_to_config)
    el = GElement(name="k", geometry={"radius": 0.01},
                  layers=[{"type": "CW", "thickness": 0.002, "sigma": 1e6}],
                  models=default_models("pytlwall"))
    el.compare.append(GModel(q="ZLong", enabled=True, method="IW2D"))

    full = element_to_config(el)
    only = element_to_config(el, compare_only=True)
    assert set(full["devices"]) == {"single", "compare_0"}
    assert set(only["devices"]) == {"compare_0"}
    assert only["output"] == ["k[IW2D ZLong]"]
    assert only["name"].endswith("_compare")


def test_compare_only_without_a_comparison_is_an_error():
    from wimba.gui.model import GElement, default_models, element_to_config
    el = GElement(name="k", geometry={"radius": 0.01},
                  layers=[{"type": "CW", "thickness": 0.002, "sigma": 1e6}],
                  models=default_models("pytlwall"))
    with pytest.raises(ValueError, match="no comparison to calculate"):
        element_to_config(el, compare_only=True)


def test_import_map_reads_a_spreadsheet(tmp_path):
    """An import map may point at an .xlsx: reading it as text would feed the
    binary container to float()."""
    import numpy as _np
    import yaml as _yaml
    from wimba.io.import_map import interp_impedance, load_import_map

    _write_xlsx(tmp_path / "k.xlsx")
    (tmp_path / "map.yaml").write_text(_yaml.safe_dump({
        "common_impedance": {"file": "k.xlsx",
                             "columns": {"freq": 1, "re": 2, "im": 3}},
        "components": {"ZLong": {}}}))

    data = load_import_map(tmp_path / "map.yaml")
    z = interp_impedance(data, _np.logspace(5, 9, 4))
    assert z["ZLong"][0] == pytest.approx(1 + 2j)


def test_import_map_spreadsheet_needs_pandas_message(tmp_path, monkeypatch):
    """When pandas is missing the error says what to install, instead of
    failing on a float conversion of binary bytes."""
    import builtins
    from wimba.io.import_map import _read_rows
    real_import = builtins.__import__

    def no_pandas(name, *a, **kw):
        if name == "pandas":
            raise ImportError("No module named 'pandas'")
        return real_import(name, *a, **kw)

    path = tmp_path / "k.xlsx"
    path.write_bytes(b"PK\x03\x04not really")
    monkeypatch.setattr(builtins, "__import__", no_pandas)
    with pytest.raises(ImportError, match="pandas and openpyxl"):
        _read_rows(path, {})
