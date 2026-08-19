"""A layer written to a config carries every parameter pytlwall needs.

A component saved from the bench was coming out with three keys - type,
thickness, sigma - and computing only because the solver filled the rest in
from its own defaults. The file then said less than the calculation used, and
anyone reading it could not tell which permittivity or relaxation had been
applied.
"""
import pytest

from wimba.gui.model import (GElement, GModel, component_config, layer_out,
                             component_save_config)


def _element(layers):
    return GElement(
        name="PROVA", category="component",
        geometry={"length": 1.0, "radius": 0.02, "shape": "CIRCULAR"},
        optics={"l": 1.0, "bx": 1.0, "by": 1.0}, layers=layers,
        models=[GModel(q="zlong", enabled=True, method="pytlwall")],
        own_base={"gamma": 479.6})


def test_a_sparse_layer_is_completed_with_pytlwall_defaults():
    out = layer_out({"type": "CW", "thickness": 0.002, "sigma": 1.4e6})
    assert out["epsr"] == 1.0
    assert out["tau"] == 0.0
    assert out["k_Hz"] == "inf"
    assert out["muinf_Hz"] == 0.0
    assert out["RQ"] == 0.0


def test_the_physics_is_never_invented():
    """Thickness and conductivity are the wall itself. A default there would be
    a number nobody chose."""
    out = layer_out({"type": "CW"})
    assert "thickness" not in out
    assert "sigma" not in out


def test_values_the_user_gave_are_not_overwritten():
    out = layer_out({"type": "CW", "epsr": 4.5, "tau": 1e-13, "k_Hz": 3.2e9,
                     "muinf_Hz": 1.0, "RQ": 0.5})
    assert (out["epsr"], out["tau"], out["k_Hz"]) == (4.5, 1e-13, 3.2e9)
    assert (out["muinf_Hz"], out["RQ"]) == (1.0, 0.5)


def test_empty_cells_do_not_survive_as_blanks():
    out = layer_out({"type": "CW", "thickness": 0.002, "sigma": None, "epsr": ""})
    assert "sigma" not in out
    assert out["epsr"] == 1.0          # blank falls back to the default


def test_the_layer_type_is_normalised():
    assert layer_out({"type": "cw"})["type"] == "CW"
    assert layer_out({})["type"] == "CW"


def test_a_saved_component_carries_complete_layers():
    el = _element([{"type": "CW", "thickness": 0.002, "sigma": 1.4e6,
                    "boundary": True}])
    spec = next(iter(component_save_config(el)["devices"].values()))
    lay = spec["layers"][0]
    for key in ("type", "thickness", "sigma", "epsr", "tau", "k_Hz",
                "muinf_Hz", "RQ"):
        assert key in lay, f"{key} missing from the saved layer"
    assert lay["boundary"] is True


def test_infinity_survives_the_round_trip_as_a_word():
    el = _element([{"type": "CW", "thickness": "inf", "sigma": 1e9,
                    "k_Hz": "inf", "boundary": True}])
    spec = next(iter(component_config(el, "pytlwall")["devices"].values()))
    assert spec["layers"][0]["thickness"] == "inf"
    assert spec["layers"][0]["k_Hz"] == "inf"
