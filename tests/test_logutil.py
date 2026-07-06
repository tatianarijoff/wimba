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


def test_method_helpers():
    from wimba.gui.model import (METHODS, method_base, method_label,
                                 method_needs_file, method_weighted)
    assert "pytlwall" in METHODS and "pytlwall (weighted)" in METHODS
    assert len(METHODS) == 8
    assert method_base("IW2D (weighted)") == "IW2D" and method_weighted("IW2D (weighted)")
    assert not method_weighted("resonator")
    assert method_label("pytlwall", True) == "pytlwall (weighted)"
    assert method_needs_file("precalculated") and not method_needs_file("pytlwall")
