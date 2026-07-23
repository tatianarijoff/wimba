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
