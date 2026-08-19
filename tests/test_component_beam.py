"""A component that belongs to no machine still has to state a beam.

Built by hand in the bench, it had nowhere to put one: BeamPanel writes to a
machine, and there was no machine. The saved config then came out with no
gamma, and `wimba run` refused it - correctly, but with no way to fix it from
the interface.
"""
import pytest

from wimba.core.beam import Beam
from wimba.gui.model import (GElement, GModel, component_config,
                             component_save_config, layer_out)


def _element(**kw):
    el = GElement(
        name="MYCOMP", category="component",
        geometry={"length": 1.0, "radius": 0.02, "shape": "CIRCULAR"},
        optics={"l": 1.0}, layers=[{"type": "CW", "thickness": "inf",
                                    "sigma": 1.35e6, "boundary": True}],
        models=[GModel(q="zlong", enabled=True, method="pytlwall")])
    for key, value in kw.items():
        setattr(el, key, value)
    return el


def test_a_beam_kept_on_the_element_reaches_the_config():
    el = _element()
    beam = Beam("proton", "gamma", 7461.0)
    el.own_base["beam"] = beam.to_dict()
    el.own_base["gamma"] = beam.gamma
    cfg = component_save_config(el)
    assert cfg["gamma"] == pytest.approx(7461.0)
    assert cfg["beam"]["particle"] == "proton"


def test_without_a_beam_the_file_still_says_so():
    cfg = component_save_config(_element())
    assert cfg.get("gamma") is None


def test_the_twiss_betas_reach_the_spec():
    el = _element()
    el.optics.update({"bx": 65.0, "by": 71.5})
    spec = next(iter(component_config(el, "pytlwall")["devices"].values()))
    assert spec["beta_x"] == 65.0 and spec["beta_y"] == 71.5


def test_betas_left_empty_fall_back_to_one():
    spec = next(iter(component_config(_element(), "pytlwall")["devices"].values()))
    assert spec["beta_x"] == 1.0 and spec["beta_y"] == 1.0


def test_a_vacuum_layer_carries_no_material_figures():
    """pytlwall computes V from a formula and reads none of them; writing them
    would put numbers in the file that no calculation ever used."""
    out = layer_out({"type": "V", "thickness": 0.001, "sigma": 5.8e7,
                     "epsr": 1.0, "boundary": True})
    assert out["type"] == "V"
    assert out["thickness"] == 0.001          # thickness IS read for inner layers
    for key in ("sigma", "epsr", "tau", "k_Hz", "muinf_Hz", "RQ"):
        assert key not in out


def test_a_pec_layer_is_treated_the_same_way():
    out = layer_out({"type": "pec", "sigma": 1e9})
    assert out["type"] == "PEC" and "sigma" not in out


def test_a_cw_layer_is_still_completed():
    out = layer_out({"type": "CW", "thickness": 0.002, "sigma": 1.35e6})
    assert out["epsr"] == 1.0 and out["k_Hz"] == "inf"


def test_the_element_beam_wins_only_because_it_belongs_to_no_machine():
    """The precedence itself is right - a component loaded from a pytlwall cfg
    must compute at the energy that cfg states. What changed is who can create
    such a beam: the panel is read-only for an element inside a ring."""
    el = _element()
    beam = Beam("proton", "gamma", 450.0)
    el.own_base.update({"beam": beam.to_dict(), "gamma": beam.gamma})
    cfg = component_config(el, "pytlwall", base_cfg={"gamma": 7000.0})
    assert cfg["gamma"] == pytest.approx(450.0)


def test_single_element_config_carries_the_beam_block_too():
    """It used to write only gamma while the bench wrote the whole block, so
    the same component described itself differently depending on the button."""
    from wimba.gui.model import element_to_config
    el = _element()
    beam = Beam("electron", "energy", 45.6e9)
    el.own_base.update({"beam": beam.to_dict(), "gamma": beam.gamma})
    cfg = element_to_config(el)
    assert cfg["beam"]["particle"] == "electron"
    assert cfg["gamma"] == pytest.approx(beam.gamma)


def test_no_internal_object_leaks_into_the_file():
    el = _element()
    beam = Beam("proton", "gamma", 7461.0)
    el.own_base.update({"beam": beam.to_dict(), "gamma": beam.gamma,
                        "_beam_obj": beam})
    cfg = component_save_config(el)
    assert all(not k.startswith("_") for k in cfg.get("beam", {}))
    assert "_beam_obj" not in cfg
