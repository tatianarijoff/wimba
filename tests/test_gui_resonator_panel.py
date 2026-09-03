"""The Models tab has to show what the chosen method actually reads.

`resonator` was selectable long before there was anywhere to type Rs, Q and
f_r, so the only thing the choice could produce was a refusal at save time.
These tests drive the real widget: the modes table appears, the wall tabs
close without losing the wall, and an element that belongs to a machine shows
its modes without letting them be edited.
"""
import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication, QComboBox  # noqa: E402

from wimba.gui.model import (GMode, default_models, from_machine_file,  # noqa: E402
                             modes_out, new_element)
from wimba.gui.panels import ElementPanel  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _wall_component(name="COMP"):
    el = new_element(name)
    el.models = default_models("pytlwall")
    el.geometry = {"length": 1.0, "radius": 0.02, "shape": "CIRCULAR"}
    el.layers = [{"type": "CW", "sigma": 1.4e6, "thickness": "inf",
                  "boundary": True}]
    return el


def _method_combo(panel):
    """The base-method combo of the Models tab (the only one listing methods)."""
    for w in panel.findChildren(QComboBox):
        if w.count() and w.itemText(0) == "pytlwall":
            return w
    raise AssertionError("no method combo in the Models tab")


def test_a_wall_method_shows_no_modes(app):
    p = ElementPanel(_wall_component(), lambda *a: None, lambda *a: None)
    p.tabs.setCurrentIndex(p.tabs.count() - 1)
    p.show()
    assert not p.modes_box.isVisible()
    assert all(p.tabs.isTabEnabled(i) for i in p._wall_tabs)


def test_choosing_resonator_opens_the_modes_table(app):
    el = _wall_component()
    p = ElementPanel(el, lambda *a: None, lambda *a: None)
    p.tabs.setCurrentIndex(p.tabs.count() - 1)
    p.show()
    _method_combo(p).setCurrentText("resonator")
    assert p.modes_box.isVisible()
    # an empty table says nothing about what is missing
    assert p.modes_tab.rowCount() == 1
    assert not any(p.tabs.isTabEnabled(i) for i in p._wall_tabs)


def test_the_wall_survives_the_round_trip(app):
    """Closed, not cleared: a comparison against pytlwall still has a wall."""
    el = _wall_component()
    p = ElementPanel(el, lambda *a: None, lambda *a: None)
    combo = _method_combo(p)
    combo.setCurrentText("resonator")
    combo.setCurrentText("pytlwall")
    assert el.geometry["radius"] == 0.02
    assert len(el.layers) == 1
    assert all(p.tabs.isTabEnabled(i) for i in p._wall_tabs)


def test_a_mode_typed_in_the_panel_reaches_the_config(app):
    el = _wall_component()
    p = ElementPanel(el, lambda *a: None, lambda *a: None)
    _method_combo(p).setCurrentText("resonator")
    p.modes_tab.cellWidget(0, 0).setCurrentText("ZDipY")
    p.modes_tab.cellWidget(0, 1).setText("1.9e5")
    p.modes_tab.cellWidget(0, 2).setText("350")
    p.modes_tab.cellWidget(0, 3).setText("7.55e8")
    assert modes_out(el) == [{"Ryd": 190000.0, "Qyd": 350.0, "fyd": 7.55e8}]


def test_reopening_an_element_mid_edit_does_not_raise(app):
    """The cell keeps the text as typed, so a half-written number is stored as
    a string; formatting it as a float is how the panel used to crash on the
    second open."""
    el = _wall_component()
    p = ElementPanel(el, lambda *a: None, lambda *a: None)
    _method_combo(p).setCurrentText("resonator")
    p.modes_tab.cellWidget(0, 1).setText("1e")
    again = ElementPanel(el, lambda *a: None, lambda *a: None)
    assert again.modes_tab.cellWidget(0, 1).text() == "1e"
    with pytest.raises(ValueError, match="not a number"):
        modes_out(el)


def test_adding_and_removing_rows_follows_the_element(app):
    el = _wall_component()
    p = ElementPanel(el, lambda *a: None, lambda *a: None)
    _method_combo(p).setCurrentText("resonator")
    p._mode_add()
    assert p.modes_tab.rowCount() == len(el.modes) == 2
    p.modes_tab.selectRow(0)
    p._mode_rm()
    assert p.modes_tab.rowCount() == len(el.modes) == 1


def test_an_element_in_a_machine_shows_its_modes_read_only(app):
    gm = from_machine_file("examples/resonator/resonator_input.yaml")
    el = gm.groups[0].elements[0]
    p = ElementPanel(el, lambda *a: None, lambda *a: None, machine=gm)
    p.show()
    assert p.modes_tab.rowCount() == len(el.modes) == 2
    assert not p._mode_buttons.isVisible()
    assert not p.modes_tab.cellWidget(0, 0).isEnabled()       # component combo
    assert p.modes_tab.cellWidget(0, 1).isReadOnly()          # Rs


def test_opening_a_resonator_does_not_land_on_a_dead_tab(app):
    gm = from_machine_file("examples/resonator/resonator_input.yaml")
    p = ElementPanel(gm.groups[0].elements[0], lambda *a: None, lambda *a: None,
                     machine=gm)
    assert p.tabs.currentIndex() not in p._wall_tabs
