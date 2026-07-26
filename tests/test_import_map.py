"""Import-map descriptors, tested on real CST exports (FCC kicker excerpts):
tab-separated, '#' comment headers, frequency in GHz, Re/Im columns."""
import numpy as np
import pytest
import yaml

from wimba.io.import_map import interp_impedance, load_import_map

DATA = "tests/data"


def _map(tmp_path, body):
    p = tmp_path / "map.yaml"
    p.write_text(yaml.safe_dump(body, sort_keys=False))
    return p


def test_real_cst_file_ghz_tab_comment(tmp_path):
    body = {
        "common_impedance": {
            "file": f"{__import__('os').getcwd()}/{DATA}/fcc_kicker_zlong_1micron.txt",
            "comment": "#", "sep": "tab", "freq_unit": "GHz",
            "format": "re_im", "columns": {"freq": 1, "re": 2, "im": 3}},
        "components": {"ZLong": {}},
    }
    data = load_import_map(_map(tmp_path, body))
    f, z = data["impedance"]["ZLong"]
    assert f[0] == 0.0 and np.isclose(f[1], 0.010239144611436e9)   # GHz -> Hz
    assert np.isclose(z[1].real, 3.0195536377705)                  # real CST values
    assert np.isclose(z[1].imag, 0.56400628770914)


def test_per_component_override_and_interp(tmp_path):
    cwd = __import__("os").getcwd()
    body = {
        "common_impedance": {"comment": "#", "sep": "tab", "freq_unit": "GHz",
                             "format": "re_im", "columns": {"freq": 1, "re": 2, "im": 3}},
        "components": {
            "ZLong": {"file": f"{cwd}/{DATA}/fcc_kicker_zlong_1micron.txt"},
            "ZDipX": {"file": f"{cwd}/{DATA}/fcc_kicker_zlong_1e-10.txt"},
        },
    }
    data = load_import_map(_map(tmp_path, body))
    assert set(data["impedance"]) == {"ZLong", "ZDipX"}
    grid = np.array([0.02e9, 0.15e9])
    out = interp_impedance(data, grid)
    assert out["ZLong"].dtype == complex and len(out["ZLong"]) == 2
    assert not np.allclose(out["ZLong"], out["ZDipX"])             # different files


def test_complex_format_and_column_errors(tmp_path):
    (tmp_path / "z.dat").write_text("# columns numbered from 1\n"
                                    "1.0e6 (10.0,2.0)\n1.0e9 5.0+1.0j\n")
    body = {"common_impedance": {"file": "z.dat", "format": "complex",
                                 "columns": {"freq": 1, "z": 2}},
            "components": {"ZLong": {}}}
    data = load_import_map(_map(tmp_path, body))
    _f, z = data["impedance"]["ZLong"]
    assert z[0] == 10.0 + 2.0j and z[1] == 5.0 + 1.0j              # both spellings

    bad = {"common_impedance": {"file": "z.dat", "format": "complex",
                                "columns": {"freq": 1, "z": 9}},
           "components": {"ZLong": {}}}
    with pytest.raises(ValueError, match="numbered from 1"):
        load_import_map(_map(tmp_path, bad))


def test_map_in_run(tmp_path):
    """A precalculated device with map: imports through the run."""
    pytest.importorskip("pytlwall")
    from wimba.run import run as run_study
    cwd = __import__("os").getcwd()
    body = {"common_impedance": {"comment": "#", "sep": "tab", "freq_unit": "GHz",
                                 "format": "re_im",
                                 "columns": {"freq": 1, "re": 2, "im": 3},
                                 "file": f"{cwd}/{DATA}/fcc_kicker_zlong_1micron.txt"},
            "components": {"ZLong": {}}}
    _map(tmp_path, body)
    (tmp_path / "c.yaml").write_text(
        "name: MapRun\n"
        "grid: {frequency: {min: 2.0e7, max: 1.0e9, n: 8, log: true}}\n"
        "devices:\n  kicker:\n    source: precalculated\n    name: KICKER\n"
        "    map: map.yaml\n    weighted: true\n")
    info = run_study(tmp_path / "c.yaml", out_dir=tmp_path / "out")
    assert info["stats"]["computed"] == 1
    from wimba.output import read_totals
    _f, comps = read_totals(tmp_path / "out" / "single_elements" / "total.csv")
    assert np.any(np.abs(comps["ZLong"]) > 0)                      # imported, in the total


def test_make_descriptor_roundtrip_on_real_file(tmp_path):
    """The GUI dialog's builder: descriptor written -> read back -> real values."""
    import shutil

    from wimba.io.import_map import make_descriptor
    cwd = __import__("os").getcwd()
    data = tmp_path / "kicker.txt"
    shutil.copy(f"{cwd}/{DATA}/fcc_kicker_zlong_1micron.txt", data)

    desc = make_descriptor("impedance", "ZLong", data.name, comment="#",
                           sep="tab", unit="GHz", fmt="re_im",
                           col_x=1, col_re=2, col_im=3)
    mp = tmp_path / "kicker.map.yaml"
    mp.write_text("# columns numbered from 1\n" + yaml.safe_dump(desc))
    loaded = load_import_map(mp)
    f, z = loaded["impedance"]["ZLong"]
    assert np.isclose(f[1], 0.010239144611436e9) and np.isclose(z[1].real, 3.0195536377705)

    wdesc = make_descriptor("wake", "WLong", data.name, unit="ns", col_x=1, col_z=2)
    assert "common_wake" in wdesc and wdesc["common_wake"]["time_unit"] == "ns"


def test_load_pytlwall_cfg_roundtrip(tmp_path):
    """Her ex_CW-style cfg -> WIMBA element -> bench run matches direct pytlwall
    (conductor boundary included)."""
    pytest.importorskip("pytlwall")
    from wimba.gui.model import GElement, component_config, default_models
    from wimba.io.pytlwall_cfg import read_chamber_cfg
    from wimba.output import read_totals
    from wimba.run import run as run_study

    (tmp_path / "ex_CW.cfg").write_text(
        "[base_info]\ncomponent_name = newCW\npipe_radius_m = 0.0184\n"
        "pipe_len_m = 1.0\nbetax = 1.0\nbetay = 1.0\nchamber_shape = CIRCULAR\n"
        "[layers_info]\nnbr_layers = 1\n"
        "[layer0]\ntype= CW\nthick_m = 5e-7\nmuinf_Hz= 0\nk_Hz= inf\n"
        "sigmaDC =1e6\nepsr = 1.0\ntau = 0.0\nRQ = 0.00\n"
        "[boundary]\ntype= CW\nmuinf_Hz= 0\nk_Hz= inf\nsigmaDC =1e9\n"
        "epsr = 1.0\ntau = 0.0\nRQ = 0.00\n"
        "[frequency_info]\nfmin = 3\nfmax = 9\nfstep = 1\n"
        "[beam_info]\ngammarel = 10000\n")
    data = read_chamber_cfg(tmp_path / "ex_CW.cfg")
    assert data["gamma"] == 10000.0 and data["geometry"]["radius"] == 0.0184
    assert data["geometry"]["layers"][-1]["boundary"] is True
    assert data["geometry"]["layers"][-1]["sigma"] == 1e9        # conductor boundary
    assert data["grid"]["frequency"]["n"] == 61                  # 10 pts/decade x 6

    geo = dict(data["geometry"]); layers = geo.pop("layers"); geo.pop("name")
    el = GElement(name="newCW", geometry=geo,
                  optics={"bx": 1.0, "by": 1.0, "l": 1.0},
                  layers=layers, models=default_models("pytlwall"))
    cfg = component_config(el, "pytlwall",
                           base_cfg={"gamma": data["gamma"], "grid": data["grid"]})
    p = tmp_path / "c.yaml"
    import yaml as _y
    p.write_text(_y.safe_dump(cfg))
    run_study(p, out_dir=tmp_path / "out")
    f, comps = read_totals(tmp_path / "out" / "single_elements" / "total.csv")

    import pytlwall
    L0 = pytlwall.Layer(layer_type="CW", thick_m=5e-7, sigmaDC=1e6)
    Lb = pytlwall.Layer(layer_type="CW", thick_m=np.inf, sigmaDC=1e9, boundary=True)
    ch = pytlwall.Chamber(pipe_len_m=1.0, pipe_rad_m=0.0184, chamber_shape="CIRCULAR",
                          betax=1.0, betay=1.0, layers=[L0, Lb])
    ref = pytlwall.TlWall(chamber=ch, beam=pytlwall.Beam(gammarel=10000.0),
                          frequencies=pytlwall.Frequencies(freq_list=list(f))
                          ).get_all_impedances()["ZLong"]
    assert np.allclose(comps["ZLong"], ref, rtol=1e-9)
