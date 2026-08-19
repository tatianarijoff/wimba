"""No panel may force the window past the edge of the screen.

A QLabel reports a minimum width as wide as its longest unbroken line, so one
sentence of guidance under a table pushed the element panel to 1844 px: the tab,
the dock and the whole window followed it off the screen. Wrapping is not
cosmetic here, it is what keeps the window resizable.
"""
import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from wimba.gui.model import GElement, GModel  # noqa: E402

#: Comfortably under a small laptop screen, and far under the ~1844 px that
#: prompted this.
LIMIT = 700


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _element():
    return GElement(
        name="C", category="component",
        geometry={"radius": 0.002, "shape": "CIRCULAR", "length": 1.0},
        optics={"l": 1.0, "bx": 1.0, "by": 1.0},
        layers=[{"type": "CW", "thickness": "inf", "sigma": 2.0e5,
                 "boundary": True}],
        models=[GModel(q="zlong", enabled=True, method="IW2D")],
        own_base={"gamma": 479.605064966})


def test_the_element_panel_stays_narrow(app):
    from wimba.gui.panels import ElementPanel
    panel = ElementPanel(_element(), lambda *a: None, lambda *a: None)
    assert panel.minimumSizeHint().width() < LIMIT


def test_a_multilayer_element_stays_narrow(app):
    """More layers means more rows, not a wider minimum: the table scrolls."""
    from wimba.gui.panels import ElementPanel
    el = _element()
    el.layers = [{"type": "CW", "thickness": 0.002, "sigma": 5.9e7},
                 {"type": "CW", "thickness": 0.005, "sigma": 1.4e6},
                 {"type": "V", "thickness": "inf", "boundary": True}]
    panel = ElementPanel(el, lambda *a: None, lambda *a: None)
    assert panel.minimumSizeHint().width() < LIMIT


def test_the_materials_tab_stays_narrow(app):
    """Its Note column holds sentences; it must scroll, not stretch."""
    from wimba.gui.materials_tab import MaterialsTab
    assert MaterialsTab().minimumSizeHint().width() < LIMIT


def test_every_note_in_the_panels_wraps(app):
    """The guard against the next long sentence: an unwrapped label is what
    caused this, and it is invisible until someone opens the tab."""
    from PyQt6.QtWidgets import QLabel

    from wimba.gui.panels import ElementPanel
    panel = ElementPanel(_element(), lambda *a: None, lambda *a: None)
    for label in panel.findChildren(QLabel):
        if len(label.text()) > 80:
            assert label.wordWrap(), f"long label does not wrap: {label.text()[:60]}..."
