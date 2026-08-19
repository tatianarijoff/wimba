"""The aperture a chamber spec carries follows the shape it declares.

pytlwall accepts CIRCULAR, ELLIPTICAL and RECTANGULAR (Chamber.chamber_shape).
A circle is stated with one radius, the other two with a horizontal and a
vertical semi-axis - `pipe_hor_m` / `pipe_ver_m` in pytlwall's own configs.
Before this, every shape was required to carry a radius, which made a
rectangular chamber impossible to state from the interface.
"""
import pytest

from wimba.gui.model import (GElement, GModel, component_config,
                             element_to_config)


def _element(**geometry):
    geo = {"length": 1.0}
    geo.update(geometry)
    return GElement(
        name="TESTPIPE", category="component", geometry=geo,
        optics={"l": 1.0, "bx": 1.0, "by": 1.0},
        layers=[{"type": "CW", "thickness": 0.002, "sigma": 1.4e6}],
        models=[GModel(q="zlong", enabled=True, method="pytlwall")],
        own_base={"gamma": 479.6})


def _spec(cfg):
    return next(iter(cfg["devices"].values()))


def test_a_circle_is_stated_with_a_radius():
    spec = _spec(component_config(_element(radius=0.02), "pytlwall"))
    assert spec["shape"] == "CIRCULAR"
    assert spec["radius_m"] == 0.02
    assert "hor_m" not in spec and "ver_m" not in spec


def test_a_rectangle_is_stated_with_two_semi_axes():
    el = _element(shape="RECTANGULAR", hor=0.0315, ver=0.0115)
    spec = _spec(component_config(el, "pytlwall"))
    assert spec["shape"] == "RECTANGULAR"
    assert spec["hor_m"] == 0.0315 and spec["ver_m"] == 0.0115


def test_an_ellipse_needs_both_axes_not_a_radius():
    el = _element(shape="ELLIPTICAL", hor=0.03, ver=0.01)
    spec = _spec(component_config(el, "pytlwall"))
    assert spec["shape"] == "ELLIPTICAL"
    assert spec["hor_m"] == 0.03 and spec["ver_m"] == 0.01


def test_a_rectangle_without_axes_is_refused_with_the_reason():
    el = _element(shape="RECTANGULAR", radius=0.02)
    with pytest.raises(ValueError, match="semi-axis"):
        component_config(el, "pytlwall")


def test_a_circle_without_a_radius_is_still_refused():
    with pytest.raises(ValueError, match="no radius"):
        component_config(_element(), "pytlwall")


def test_a_stale_axis_does_not_travel_with_a_circle():
    """Switching a shape back to CIRCULAR must not leave hor/ver in the spec:
    pytlwall would take them and the plot would not match the form."""
    el = _element(radius=0.02, hor=0.0315, ver=0.0115)   # shape defaults circular
    spec = _spec(component_config(el, "pytlwall"))
    assert spec["radius_m"] == 0.02
    assert "hor_m" not in spec and "ver_m" not in spec


def test_the_shape_is_normalised_to_upper_case():
    el = _element(shape="rectangular", hor=0.03, ver=0.01)
    assert _spec(component_config(el, "pytlwall"))["shape"] == "RECTANGULAR"


def test_single_element_calculation_follows_the_same_rule():
    el = _element(shape="RECTANGULAR", hor=0.03, ver=0.01)
    spec = _spec(element_to_config(el))
    assert spec["hor_m"] == 0.03 and "radius_m" not in spec
