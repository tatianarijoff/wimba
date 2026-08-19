"""The test-beam shift must travel, and must be visible.

pytlwall's Beam defaults it to 0.001. WIMBA never invented a value, which was
fine - but it also never let a config state one, so a chamber cfg written with
0.01 was read back and computed at 0.001 without a word. Only the space-charge
terms use it, so the difference hides in exactly the components people compare.
"""
import pytest
import yaml

from wimba.assembly import load_assembly


def _cfg(tmp_path, **extra):
    device = {"source": "chamber", "name": "C", "method": "pytlwall",
              "radius_m": 0.002, "length_m": 1.0, "beta_x": 1.0, "beta_y": 1.0,
              "weighted": False, "space_charge": True,
              "layers": [{"type": "CW", "thickness": "inf", "sigma": 2.0e5}]}
    device.update(extra)
    cfg = {"name": "TBS", "gamma": 479.605064966,
           "grid": {"frequency": {"min": 1.0e6, "max": 1.0e8, "n": 5,
                                  "log": True}},
           "output": ["C"], "devices": {"c": device}}
    path = tmp_path / "tbs.yaml"
    path.write_text(yaml.safe_dump(cfg))
    return path, cfg


def test_a_stated_shift_reaches_the_geometry(tmp_path):
    path, cfg = _cfg(tmp_path, test_beam_shift=0.01)
    row = load_assembly(str(path), cfg=cfg).rows[0]
    assert row.geometry["test_beam_shift"] == pytest.approx(0.01)


def test_nothing_is_invented_when_the_config_is_silent(tmp_path):
    """None means 'leave pytlwall in charge of its own default' - WIMBA must
    not substitute a number of its own, which would be a second default."""
    path, cfg = _cfg(tmp_path)
    row = load_assembly(str(path), cfg=cfg).rows[0]
    assert row.geometry.get("test_beam_shift") is None


def test_the_provider_forwards_it(tmp_path):
    from wimba.builders.loader import _build_pytlwall
    from wimba.core.beam import Beam

    el = {"name": "C", "source": "pytlwall", "radius_m": 0.002, "length": 1.0,
          "test_beam_shift": 0.01,
          "layers": [{"type": "CW", "thickness": "inf", "sigma": 2.0e5}]}
    provider = _build_pytlwall(el, tmp_path, Beam("proton", "gamma", 479.6))
    assert provider.test_beam_shift == pytest.approx(0.01)


def test_iw2d_never_receives_it(tmp_path):
    """IW2D's formalism has no test-beam shift; handing it one would be an
    unexpected keyword, and pretending it meant something would be worse."""
    from wimba.builders.loader import _build_iw2d
    from wimba.core.beam import Beam

    el = {"name": "C", "source": "iw2d", "radius_m": 0.002, "length": 1.0,
          "test_beam_shift": 0.01,
          "layers": [{"type": "CW", "thickness": "inf", "sigma": 2.0e5}]}
    provider = _build_iw2d(el, tmp_path, Beam("proton", "gamma", 479.6))
    assert not hasattr(provider, "test_beam_shift")


def test_a_pytlwall_cfg_keeps_it_through_a_round_trip(tmp_path):
    """Read it, write it, read it again: a cfg that states 0.01 must not come
    back as pytlwall's 0.001."""
    from wimba.io.pytlwall_cfg import read_chamber_cfg, write_chamber_cfg

    src = tmp_path / "in.cfg"
    src.write_text(
        "[base_info]\nchamber_shape = CIRCULAR\npipe_radius_m = 0.002\n"
        "pipe_len_m = 1.0\nbetax = 1.0\nbetay = 1.0\n\n"
        "[layers_info]\nnbr_layers = 0\n\n"
        "[boundary]\ntype = CW\nsigmaDC = 2e5\nepsr = 1.0\ntau = 0.0\n"
        "muinf_Hz = 0\nk_Hz = inf\nRQ = 0.0\n\n"
        "[beam_info]\ngammarel = 479.605064966\ntest_beam_shift = 0.01\n")
    data = read_chamber_cfg(src)
    assert data["test_beam_shift"] == pytest.approx(0.01)

    out = write_chamber_cfg(tmp_path / "out.cfg", data["geometry"],
                            gamma=data["gamma"], length_m=data["length"],
                            test_beam_shift=data["test_beam_shift"])
    assert read_chamber_cfg(out)["test_beam_shift"] == pytest.approx(0.01)


def test_a_cfg_that_states_nothing_writes_nothing(tmp_path):
    """The dump must not turn 'unstated' into 'pytlwall's default, stated'."""
    from wimba.io.pytlwall_cfg import write_chamber_cfg

    out = write_chamber_cfg(
        tmp_path / "out.cfg",
        {"shape": "CIRCULAR", "radius": 0.002,
         "layers": [{"type": "CW", "thickness": "inf", "sigma": 2.0e5,
                     "boundary": True}]},
        gamma=479.6)
    assert "test_beam_shift" not in out.read_text()


def test_the_value_actually_changes_the_space_charge(tmp_path):
    """The point of carrying it. Skipped without pytlwall, since the numbers
    come from the engine."""
    pytlwall = pytest.importorskip("pytlwall")
    import numpy as np
    from wimba.sources.pytlwall_bridge import compute_chamber

    freqs = np.array([1.0e10])
    layers = [{"type": "CW", "thickness": "inf", "sigma": 2.0e5}]
    kw = dict(layers=layers, length_m=1.0, gamma=479.605064966)
    small = compute_chamber(freqs, 0.002, test_beam_shift=1e-4, **kw)
    large = compute_chamber(freqs, 0.002, test_beam_shift=1e-2, **kw)

    # the wall impedance does not depend on it at all
    assert small["ZLong"][0] == pytest.approx(large["ZLong"][0], rel=1e-12)
    # the indirect space charge does - which is why it must not be silently
    # replaced by a default
    assert small["ZLongISC"][0] != large["ZLongISC"][0]
