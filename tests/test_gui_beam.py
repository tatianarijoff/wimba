"""The Beam panel and the wiring that carries a beam into a calculation.

The view-model half runs without Qt (model.py imports no Qt); the panel half is
skipped where PyQt6 is not installed.
"""
import pytest

from wimba.core.beam import Beam


def _machine_yaml(tmp_path, extra=""):
    (tmp_path / "m.tfs").write_text(
        '@ NAME %05s "T"\n* NAME S L BETX BETY\n$ %s %le %le %le %le\n'
        ' "C1" 100.0 1.0 130.0 85.0\n')
    path = tmp_path / "m.yaml"
    path.write_text(
        "name: Mini\n" + extra +
        "optics: m.tfs\n"
        "grid:\n  frequency: {min: 1.0e7, max: 1.0e9, n: 10, log: true}\n"
        "groups:\n  cavities:\n    - name: C1\n      source: resonator\n"
        "      resonators: [{term: zlong, Rs: 1.0e4, Q: 1.0, fr: 1.0e9}]\n")
    return path


def test_machine_file_without_a_beam_leaves_it_unset(tmp_path):
    from wimba.gui.model import from_machine_file
    assert from_machine_file(_machine_yaml(tmp_path)).beam is None


def test_machine_file_beam_block_reaches_the_view_model(tmp_path):
    from wimba.gui.model import from_machine_file
    gm = from_machine_file(_machine_yaml(
        tmp_path, "beam: {particle: proton, gamma: 479.605}\n"))
    assert gm.beam.particle == "proton"
    assert gm.beam.gamma == pytest.approx(479.605)


def test_old_style_bare_gamma_still_reaches_the_view_model(tmp_path):
    from wimba.gui.model import from_machine_file
    gm = from_machine_file(_machine_yaml(tmp_path, "gamma: 7461.0\n"))
    assert gm.beam.gamma == pytest.approx(7461.0)


# ------------------------------------------------------------------ the panel
pytest.importorskip("PyQt6")


@pytest.fixture(scope="module")
def qt_app():
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qt_app):
    from wimba.gui.model import GMachine
    from wimba.gui.panels import BeamPanel
    gm = GMachine(name="T")
    seen = []
    return gm, BeamPanel(gm, lambda: seen.append(gm.beam)), seen


def test_default_particle_is_proton_not_the_alphabetical_first(panel):
    _gm, p, _seen = panel
    assert p.particle.currentText() == "proton"


def test_a_valid_value_is_stored_and_announced(panel):
    gm, p, seen = panel
    p.value.setText("7461")
    p._edited()
    assert gm.beam.gamma == pytest.approx(7461.0)
    assert len(seen) == 1
    assert "7000" in p.derived.text()          # E in GeV appears among the derived


def test_an_invalid_value_is_not_stored(panel):
    gm, p, _seen = panel
    p.value.setText("7461"); p._edited()
    p.mode.setCurrentIndex(p.mode.findData("beta"))
    p.value.setText("0.99999"); p._edited()
    # isVisible() is False for a widget in a window that was never shown, so the
    # text is what to assert on here
    assert "Give the beam as gamma" in p.error.text()
    assert gm.beam.gamma == pytest.approx(7461.0)      # the good beam survives


def test_non_numeric_text_is_reported_plainly(panel):
    _gm, p, _seen = panel
    p.value.setText("banana"); p._edited()
    assert "not a number" in p.error.text()


def test_switching_mode_re_expresses_the_same_beam(panel):
    gm, p, _seen = panel
    p.value.setText("7461"); p._edited()
    p.mode.setCurrentIndex(p.mode.findData("energy"))
    assert float(p.value.text()) == pytest.approx(7000.45, rel=1e-4)   # GeV
    assert gm.beam.gamma == pytest.approx(7461.0, rel=1e-9)


def test_switching_to_a_mode_that_cannot_express_the_beam_keeps_it(panel):
    gm, p, _seen = panel
    p.value.setText("7461"); p._edited()
    p.mode.setCurrentIndex(p.mode.findData("beta"))
    assert "cannot be written as" in p.error.text()
    assert gm.beam.gamma == pytest.approx(7461.0)


def test_a_component_beam_is_shown_read_only(qt_app):
    from wimba.gui.model import GMachine
    from wimba.gui.panels import BeamPanel
    p = BeamPanel(GMachine(name="T"), lambda: None,
                  override=Beam(mode="gamma", value=479.605))
    assert not p.value.isEnabled() and not p.mode.isEnabled()
    assert p.value.text() == "479.605"
