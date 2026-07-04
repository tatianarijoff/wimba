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
