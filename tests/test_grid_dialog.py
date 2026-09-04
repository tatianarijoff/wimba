"""Choosing the frequencies from the window.

Until this existed the grid was the one thing a study needs that the window
could not state: it came from project.yaml, from whichever config happened to be
open, or from a default written in the code. Which is how a resonance of quality
factor 420 could be computed on a grid stepping by 7% and read 566 ohm instead
of the 110 kilo-ohm the file states.
"""
import pytest

from wimba.gui.model import (GMode, component_config, component_save_config,
                             default_models, grid_advice, new_element)

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from wimba.gui.grid_dialog import DEFAULT_GRID, GridDialog  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


# ------------------------------------------------------------- what it says
def test_a_log_grid_states_its_step_and_what_it_resolves():
    said = grid_advice({"frequency": {"min": 1e4, "max": 1e10, "n": 200,
                                      "log": True}})
    assert "7.19% per point" in said
    assert "718.9 MHz at the top" in said
    assert "Q = 3" in said                      # the Chimera case, in one line


def test_a_linear_grid_states_a_step_in_hertz():
    said = grid_advice({"frequency": {"min": 6.3e8, "max": 6.4e8, "n": 2001,
                                      "log": False}})
    assert "5 kHz per point" in said and "Q = 25600" in said


def test_no_advice_for_something_that_is_not_a_grid():
    assert grid_advice({"frequency": {"min": 1e4, "max": 1e4, "n": 200}}) == ""
    assert grid_advice({"frequency": {"min": 1e4, "max": 1e10, "n": 1}}) == ""
    assert grid_advice({}) == ""


def test_the_advice_scales_with_the_point_count():
    coarse = grid_advice({"frequency": {"min": 1e5, "max": 1e10, "n": 100,
                                        "log": True}})
    fine = grid_advice({"frequency": {"min": 1e5, "max": 1e10, "n": 2000,
                                      "log": True}})
    assert "Q = 2" in coarse and "Q = 35" in fine


# ------------------------------------------------------------- the dialog
def test_it_opens_on_the_grid_it_was_given(app):
    grid = {"frequency": {"min": 1e4, "max": 6e8, "n": 200, "log": True}}
    d = GridDialog(grid, "somewhere")
    assert d.values()["frequency"] == grid["frequency"]


def test_it_opens_on_the_default_when_nothing_is_set(app):
    d = GridDialog({}, "somewhere")
    assert d.values()["frequency"] == DEFAULT_GRID["frequency"]


def test_editing_a_field_restates_what_is_resolved(app):
    d = GridDialog({"frequency": {"min": 1e4, "max": 1e10, "n": 200,
                                  "log": True}}, "somewhere")
    before = d.advice.text()
    d.f_max.setText("6e8")
    assert d.advice.text() != before
    assert d.values()["frequency"]["max"] == 6e8


def test_a_grid_that_is_not_one_cannot_be_accepted(app):
    d = GridDialog({}, "somewhere")
    d.f_n.setText("1")
    assert not d._ok.isEnabled()
    assert d.values() == {}
    d.f_n.setText("100")
    assert d._ok.isEnabled()


def test_a_log_grid_may_not_start_at_zero(app):
    d = GridDialog({}, "somewhere")
    d.f_min.setText("0")
    assert d.values() == {} and not d._ok.isEnabled()


def test_an_unusable_time_block_is_left_out_not_refused(app):
    """A wake is not what most runs are after: the impedance grid stands."""
    d = GridDialog({}, "somewhere")
    d.t_max.setText("0")
    assert "frequency" in d.values() and "time" not in d.values()
    assert d._ok.isEnabled()


def test_yaml_1_1_exponents_open_as_numbers(app):
    # `6e8` in a hand-edited project.yaml is a string to PyYAML
    d = GridDialog({"frequency": {"min": 10000.0, "max": "6e8", "n": 200,
                                  "log": True}}, "somewhere")
    assert d.values()["frequency"]["max"] == 6e8


# ------------------------------------------------- it reaches the calculation
def _resonator():
    el = new_element("RFCAV")
    el.models = default_models("resonator")
    el.modes = [GMode(q="ZLong", Rs=1.1e5, Q=420.0, fr=6.35e8)]
    el.own_base = {"gamma": 7461.0}
    return el


def test_a_component_without_a_grid_uses_the_written_default():
    cfg = component_config(_resonator(), "resonator", base_cfg={"gamma": 7461.0})
    assert cfg["grid"]["frequency"] == DEFAULT_GRID["frequency"]


def test_the_grid_set_on_a_component_wins_over_the_open_config():
    el = _resonator()
    el.own_base["grid"] = {"frequency": {"min": 6.3e8, "max": 6.4e8, "n": 2001,
                                         "log": False}}
    cfg = component_config(el, "resonator",
                           base_cfg={"gamma": 7461.0,
                                     "grid": {"frequency": {"min": 1e5,
                                                            "max": 1e10,
                                                            "n": 100,
                                                            "log": True}}})
    assert cfg["grid"]["frequency"]["max"] == 6.4e8
    assert cfg["grid"]["frequency"]["n"] == 2001


def test_the_saved_component_carries_the_grid_it_was_given():
    el = _resonator()
    el.own_base["grid"] = {"frequency": {"min": 6.3e8, "max": 6.4e8, "n": 2001,
                                         "log": False}}
    cfg = component_save_config(el, base_cfg={"gamma": 7461.0})
    assert cfg["grid"]["frequency"]["n"] == 2001


def test_the_grid_decides_whether_a_resonance_is_seen_at_all(tmp_path):
    """The point of the whole dialog, in one assertion: the same resonator, the
    same Rs, read on two grids."""
    import csv
    import sys

    import numpy as np

    from wimba.cli import main
    from wimba.gui.model import component_config_text

    def peak(grid, name):
        el = _resonator()
        if grid:
            el.own_base["grid"] = grid
        cfg = component_save_config(el, base_cfg={"gamma": 7461.0})
        folder = tmp_path / name
        folder.mkdir(exist_ok=True)
        path = folder / "RFCAV_component.yaml"
        path.write_text(component_config_text(cfg, "resonator"))
        sys.argv = ["wimba", "run", str(path)]
        try:
            main()
        except SystemExit:
            pass
        out = folder / "RFCAV_component_output/single_elements/total.csv"
        rows = list(csv.DictReader(open(out)))
        return np.array([float(r["Re_ZLong"]) for r in rows]).max()

    coarse = peak(None, "coarse")                       # the written default
    fine = peak({"frequency": {"min": 6.3e8, "max": 6.4e8, "n": 2001,
                               "log": False}}, "fine")

    assert coarse < 0.05 * 1.1e5        # the peak is stepped over entirely
    assert fine == pytest.approx(1.1e5)  # and on the right grid it is exact
