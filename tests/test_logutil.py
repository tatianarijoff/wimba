"""Logging levels, and the GUI loader rejecting assemble configs (the crash fix)."""
import logging

import pytest

from wimba.logutil import LEVELS, configure, get_logger, set_level


def test_levels_and_logger_names():
    assert set(LEVELS) == {"critical", "error", "warning", "info", "debug"}
    assert get_logger("mymod").name == "wimba.mymod"
    assert get_logger("wimba.x").name == "wimba.x"


def test_configure_and_set_level():
    configure("warning")
    assert logging.getLogger("wimba").level == logging.WARNING
    set_level("debug")
    assert logging.getLogger("wimba").level == logging.DEBUG


def test_from_project_rejects_assemble_config(tmp_path):
    # model.py has no Qt import, so this runs without a display
    from wimba.gui.model import from_project
    cfg = tmp_path / "assemble.yaml"
    cfg.write_text("name: X\noptics: x.tfs\ndefault_pipe: {method: pytlwall}\n"
                   "devices:\n  d: {source: chamber, radius_m: 0.02}\n")
    with pytest.raises(ValueError, match="assemble/run config"):
        from_project(cfg)


def test_from_config_populates_machine(tmp_path):
    from wimba.gui.model import from_config
    (tmp_path / "m.tfs").write_text(
        '@ NAME %05s "T"\n* NAME S L BETX BETY\n$ %s %le %le %le %le\n'
        ' "C1" 100.0 0.6 130.0 85.0\n "C2" 145.0 1.0 110.0 160.0\n')
    (tmp_path / "c.yaml").write_text(
        "name: Mini\noptics: m.tfs\ndefault_pipe: {method: pytlwall, radius_mm: 22}\n"
        "devices:\n  collimators:\n    source: chamber\n    name: C1\n"
        "    method: pytlwall\n    radius_m: 0.01\n    beta_x: 130\n    beta_y: 85\n"
        "    position: 100.0\n")
    gm = from_config(str(tmp_path / "c.yaml"))
    assert gm.name == "Mini"
    names = {g.name for g in gm.groups}
    assert "collimators" in names and "default resistive wall" in names
    c1 = gm.groups[0].elements[0]
    assert c1.name == "C1" and c1.optics["bx"] == 130.0 and c1.optics["s"] == 100.0
    pipe = next(g for g in gm.groups if g.name == "default resistive wall").elements[0]
    assert pipe.geometry.get("radius") == 0.022          # the pipe shows its geometry
    assert pipe.layers and "sigma" in pipe.layers[0]     # ... and its wall build-up


def test_method_helpers():
    from wimba.gui.model import (METHODS, method_base, method_label,
                                 method_needs_file, method_weighted)
    assert "pytlwall" in METHODS and "pytlwall (weighted)" in METHODS
    assert len(METHODS) == 8
    assert method_base("IW2D (weighted)") == "IW2D" and method_weighted("IW2D (weighted)")
    assert not method_weighted("resonator")
    assert method_label("pytlwall", True) == "pytlwall (weighted)"
    assert method_needs_file("precalculated") and not method_needs_file("pytlwall")


def test_element_to_config_and_run(tmp_path):
    """The single-element emitter produces a runnable config: grid/gamma
    inherited, geometry/layers/beta from the element; the run computes it."""
    pytest.importorskip("pytlwall")
    import numpy as np
    import yaml

    from wimba.gui.model import GElement, default_models, element_to_config
    from wimba.run import run as run_study

    el = GElement(name="lhc_default_pipe  (\u00d711188 lattice segments)",
                  category="default_pipe",
                  geometry={"shape": "ELLIPTICAL", "radius": 0.0184,
                            "hor": 0.0232, "ver": 0.0184},
                  optics={"bx": 2.0, "by": 1.0, "l": 1.0},
                  layers=[{"type": "CW", "thickness": 75e-6, "sigma": 2.0e9},
                          {"type": "CW", "thickness": 1.0e-3, "sigma": 1.4e6},
                          {"type": "V", "thickness": "inf", "boundary": True}],
                  models=default_models("pytlwall"))
    cfg = element_to_config(el, base_cfg={"gamma": 7000.0,
                                          "grid": {"frequency": {"min": 1e6, "max": 1e9,
                                                                 "n": 6, "log": True}}})
    assert cfg["name"] == "lhc_default_pipe_single"          # suffix stripped
    spec = cfg["devices"]["single"]
    assert spec["shape"] == "ELLIPTICAL" and spec["beta_x"] == 2.0
    assert len(spec["layers"]) == 3

    path = tmp_path / "single.yaml"
    path.write_text(yaml.safe_dump(cfg))
    info = run_study(path, out_dir=tmp_path / "out")
    assert info["stats"]["computed"] == 1
    per_dev = tmp_path / "out" / "single_elements" / "single" / "lhc_default_pipe.csv"
    assert per_dev.is_file()                                  # element has its own output


def test_element_to_config_rejects_non_pytlwall():
    from wimba.gui.model import GElement, default_models, element_to_config
    el = GElement(name="RF", geometry={"radius": 0.02},
                  models=default_models("resonator"))
    with pytest.raises(ValueError, match="resonator"):
        element_to_config(el)


def test_models_fill_no_wake_no_duplicates():
    """The Models table lists each impedance quantity once (no wake row - the
    wake has its own Calculate actions), for both loaded and new elements."""
    from wimba.gui.model import QUANTITIES, default_models

    ms = default_models("pytlwall")
    qs = [m.q for m in ms]
    assert "wake" not in qs
    assert len(qs) == len(set(qs)) == len(QUANTITIES) - 1
