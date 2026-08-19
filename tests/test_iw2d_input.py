"""Reading IW2D's own input files.

The format is one parameter per line, description and value separated by a tab,
and it is not in SI. These tests pin the conversions against IW2D's own legacy
reader, and pin the two cases the reader refuses rather than approximating.
"""
import math

import pytest

from wimba.io.iw2d_input import read_iw2d_input

REFERENCE = """Machine:\tWIMBA
Relativistic Gamma:\t479.605064966
Impedance Length in m:\t1.
Number of layers:\t1
Layer 1 inner radius in mm:\t2.
Layer 1 DC resistivity (Ohm.m):\t5e-06
Layer 1 relaxation time for resistivity (ps):\t4.2
Layer 1 real part of dielectric constant:\t1
Layer 1 magnetic susceptibility:\t0.0
Layer 1 relaxation frequency of permeability (MHz):\tInfinity
Layer 1 thickness in mm:\tInfinity
start frequency exponent (10^) in Hz:\t3
stop frequency exponent (10^) in Hz:\t11
linear (1) or logarithmic (0) or both (2) frequency scan:\t0
sampling frequency exponent (10^) in Hz (for linear):\t8
Number of points per decade (for log):\t4
when both, fmin of the refinement (in THz):\t0.1
when both, fmax of the refinement (in THz):\t5.
when both, number of points in the refinement:\t50
added frequencies [Hz]:\t
Yokoya factors long, xdip, ydip, xquad, yquad:\t1 1 1 0 0
Comments for the output files names:\t_wimba_roundchamber
"""


def write(tmp_path, text=REFERENCE, **replace):
    for old, new in replace.items():
        text = text.replace(old, new)
    path = tmp_path / "input.txt"
    path.write_text(text)
    return path


def test_the_reference_wall_comes_back_in_si(tmp_path):
    d = read_iw2d_input(write(tmp_path))
    assert d["gamma"] == pytest.approx(479.605064966)
    assert d["length"] == pytest.approx(1.0)
    assert d["geometry"]["shape"] == "CIRCULAR"
    assert d["geometry"]["radius"] == pytest.approx(0.002)      # mm -> m

    lay = d["geometry"]["layers"][0]
    assert lay["type"] == "CW"
    assert lay["sigma"] == pytest.approx(2.0e5)                 # 1 / 5e-06
    assert lay["tau"] == pytest.approx(4.2e-12)                 # ps -> s
    assert lay["epsr"] == pytest.approx(1.0)
    assert lay["k_Hz"] == "inf"
    assert lay["thickness"] == "inf"
    assert lay["boundary"] is True


def test_the_susceptibility_is_not_shifted(tmp_path):
    """IW2D asks for chi and pytlwall's muinf_Hz is already chi. A layer that
    said 0 must not arrive as -1, which is what a mu_r reading would give."""
    d = read_iw2d_input(write(tmp_path))
    assert d["geometry"]["layers"][0]["muinf_Hz"] == pytest.approx(0.0)

    d = read_iw2d_input(write(tmp_path,
                              **{"Layer 1 magnetic susceptibility:\t0.0":
                                 "Layer 1 magnetic susceptibility:\t500"}))
    assert d["geometry"]["layers"][0]["muinf_Hz"] == pytest.approx(500.0)


def test_the_permeability_frequency_comes_from_megahertz(tmp_path):
    d = read_iw2d_input(write(
        tmp_path,
        **{"Layer 1 relaxation frequency of permeability (MHz):\tInfinity":
           "Layer 1 relaxation frequency of permeability (MHz):\t10"}))
    assert d["geometry"]["layers"][0]["k_Hz"] == pytest.approx(1.0e7)


def test_infinite_resistivity_is_vacuum(tmp_path):
    d = read_iw2d_input(write(
        tmp_path, **{"Layer 1 DC resistivity (Ohm.m):\t5e-06":
                     "Layer 1 DC resistivity (Ohm.m):\tInfinity"}))
    lay = d["geometry"]["layers"][0]
    assert lay["type"] == "V"
    assert "sigma" not in lay


def test_the_scan_becomes_a_grid_over_the_same_range(tmp_path):
    d = read_iw2d_input(write(tmp_path))
    grid = d["grid"]["frequency"]
    assert grid["min"] == pytest.approx(1e3)
    assert grid["max"] == pytest.approx(1e11)
    assert grid["log"] is True
    assert grid["n"] == 33                     # (11 - 3) * 4 + 1


def test_a_scan_wimba_cannot_reproduce_is_reported(tmp_path):
    """Mode 2 is a logarithmic scan with a refined window. WIMBA holds a grid,
    so it says what it did rather than pretending the points are IW2D's."""
    d = read_iw2d_input(write(
        tmp_path, **{"linear (1) or logarithmic (0) or both (2) frequency "
                     "scan:\t0":
                     "linear (1) or logarithmic (0) or both (2) frequency "
                     "scan:\t2"}))
    assert any("frequency scan" in n for n in d["notes"])


def test_a_flat_chamber_input_is_refused_by_name(tmp_path):
    text = REFERENCE.replace("Number of layers:\t1",
                             "Number of upper layers in the chamber wall:\t1\n"
                             "Top bottom symmetry (yes or no):\tyes\n"
                             "Number of layers:\t1")
    with pytest.raises(ValueError, match="flat-chamber"):
        read_iw2d_input(write(tmp_path, text))


def test_non_circular_yokoya_factors_are_kept_and_reported(tmp_path):
    """They describe another shape through an equivalent round one. The file
    does not say which shape, so the element stays circular and carries the
    factors - dropping them would compute a round chamber under its name."""
    d = read_iw2d_input(write(
        tmp_path,
        **{"yquad:\t1 1 1 0 0": "yquad:\t1 0.411 0.822 -0.411 0.411"}))
    assert d["geometry"]["iw2d_yokoya"] == pytest.approx(
        [1.0, 0.411, 0.822, -0.411, 0.411])
    assert any("Yokoya" in n for n in d["notes"])


def test_the_circular_set_is_kept_too(tmp_path):
    """So that a config always states what it was computed with, rather than
    leaving the reader to assume the default."""
    d = read_iw2d_input(write(tmp_path))
    assert d["geometry"]["iw2d_yokoya"] == pytest.approx([1.0, 1.0, 1.0, 0.0, 0.0])


def test_five_numbers_are_required(tmp_path):
    with pytest.raises(ValueError, match="five"):
        read_iw2d_input(write(tmp_path, **{"yquad:\t1 1 1 0 0": "yquad:\t1 1 1"}))


def test_a_line_without_a_tab_is_an_error_not_a_comment(tmp_path):
    with pytest.raises(ValueError, match="no tab"):
        read_iw2d_input(write(tmp_path, REFERENCE + "# a comment\n"))


def test_a_reworded_description_is_reported_as_missing(tmp_path):
    """IW2D matches on the exact sentence, so a helpfully edited line is an
    absent parameter — better said than silently defaulted."""
    with pytest.raises(ValueError, match="missing"):
        read_iw2d_input(write(tmp_path,
                              **{"Relativistic Gamma:": "Relativistic gamma:"}))


def test_the_shipped_example_reads(tmp_path):
    from pathlib import Path
    example = (Path(__file__).resolve().parents[1] / "examples" /
               "RoundChamber_IW2D_native" / "RoundChamber_IW2D_input.txt")
    if not example.is_file():
        pytest.skip("example not present")
    d = read_iw2d_input(example)
    assert d["gamma"] == pytest.approx(479.605064966)
    assert d["geometry"]["layers"][0]["tau"] == pytest.approx(4.2e-12)


def test_a_single_element_can_be_computed_with_iw2d(tmp_path):
    """The bench used to refuse anything but pytlwall, so a component loaded
    from an IW2D file could be opened and not computed."""
    from wimba.gui.model import GElement, GModel, element_to_config
    el = GElement(name="C", category="component",
                  geometry={"radius": 0.002, "shape": "CIRCULAR", "length": 1.0,
                            "iw2d_yokoya": [1.0, 0.411, 0.822, -0.411, 0.411]},
                  optics={"l": 1.0, "bx": 1.0, "by": 1.0},
                  layers=[{"type": "CW", "thickness": "inf", "sigma": 2e5}],
                  models=[GModel(q="zlong", enabled=True, method="IW2D")],
                  own_base={"gamma": 479.605064966})
    spec = next(iter(element_to_config(el)["devices"].values()))
    assert spec["method"] == "iw2d"
    assert spec["iw2d_yokoya"] == pytest.approx([1.0, 0.411, 0.822, -0.411, 0.411])


def test_the_factors_reach_the_provider(tmp_path):
    """Plumbing check: config -> assembly -> geometry dict the bridge reads."""
    import yaml
    from wimba.assembly import load_assembly
    cfg = {"name": "Y", "gamma": 479.6,
           "grid": {"frequency": {"min": 1e6, "max": 1e8, "n": 5, "log": True}},
           "output": ["C"],
           "devices": {"c": {"source": "chamber", "name": "C", "method": "iw2d",
                             "radius_m": 0.002, "length_m": 1.0,
                             "beta_x": 1.0, "beta_y": 1.0, "weighted": False,
                             "iw2d_yokoya": [1.0, 0.411, 0.822, -0.411, 0.411],
                             "layers": [{"type": "CW", "thickness": "inf",
                                         "sigma": 2e5}]}}}
    path = tmp_path / "y.yaml"
    path.write_text(yaml.safe_dump(cfg))
    result = load_assembly(str(path), cfg=cfg)
    assert result.rows[0].geometry["iw2d_yokoya"] == pytest.approx(
        [1.0, 0.411, 0.822, -0.411, 0.411])


def test_pytlwall_never_receives_the_iw2d_only_key(tmp_path):
    """The factors are IW2D's. pytlwall applies its own tables, so handing it
    these would be ignored at best and applied twice at worst — and the build
    flow crashed on the unexpected argument."""
    from wimba.builders.loader import _build_pytlwall
    from wimba.core.beam import Beam

    el = {"name": "C1", "source": "pytlwall", "radius_m": 0.02, "length": 1.0,
          "iw2d_yokoya": [1.0, 0.411, 0.822, -0.411, 0.411],
          "layers": [{"material": "copper", "thickness": 0.002}]}
    provider = _build_pytlwall(el, tmp_path, Beam("proton", "gamma", 7000.0))
    assert not hasattr(provider, "yokoya")


def test_iw2d_does_receive_it(tmp_path):
    from wimba.builders.loader import _build_iw2d
    from wimba.core.beam import Beam

    el = {"name": "C1", "source": "iw2d", "radius_m": 0.02, "length": 1.0,
          "iw2d_yokoya": [1.0, 0.411, 0.822, -0.411, 0.411],
          "layers": [{"type": "CW", "thickness": "inf", "sigma": 2e5}]}
    provider = _build_iw2d(el, tmp_path, Beam("proton", "gamma", 7000.0))
    assert provider.yokoya == pytest.approx((1.0, 0.411, 0.822, -0.411, 0.411))
