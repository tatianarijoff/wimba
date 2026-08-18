"""Saving a Component bench component to a file the user chooses.

Qt-free: the dialog lives in the GUI, but what it writes is produced by pure
functions in gui/model.py, which is where the behaviour worth guarding is.
"""
import pytest
import yaml

from wimba.gui.model import (GElement, GModel, component_config,
                             component_config_text, component_save_config)


def _chamber(method="pytlwall"):
    return GElement(
        name="TESTPIPE", category="component",
        geometry={"radius": 0.02, "shape": "CIRCULAR"},
        optics={"l": 1.5, "bx": 1.0, "by": 1.0},
        layers=[{"type": "CW", "thickness": 0.002, "sigma": 1.4e6}],
        models=[GModel(q="zlong", enabled=True, method=method)],
        own_base={"gamma": 479.6},
    )


def test_saved_config_is_a_runnable_single_device_config():
    cfg = component_save_config(_chamber())
    assert list(cfg["devices"]) and len(cfg["devices"]) == 1
    spec = next(iter(cfg["devices"].values()))
    assert spec["source"] == "chamber" and spec["method"] == "pytlwall"
    assert spec["radius_m"] == 0.02 and spec["length_m"] == 1.5
    assert cfg["gamma"] == 479.6
    assert "default_pipe" not in cfg          # a component is not a machine


def test_method_label_is_stripped_from_the_saved_names():
    """The label keeps accumulated bench runs apart in the Results tree. In a
    file it would be baked into every result ever computed from it."""
    bench = component_config(_chamber(), "pytlwall")
    assert next(iter(bench["devices"].values()))["name"].endswith("[pytlwall]")

    cfg = component_save_config(_chamber())
    assert next(iter(cfg["devices"].values()))["name"] == "TESTPIPE"
    assert cfg["output"] == ["TESTPIPE"]


def test_iw2d_components_save_too():
    """The whole point of saving the WIMBA config rather than a pytlwall .cfg:
    a pytlwall chamber dump cannot express this element at all."""
    cfg = component_save_config(_chamber(method="IW2D"))
    spec = next(iter(cfg["devices"].values()))
    assert spec["method"] == "iw2d"
    assert spec["name"] == "TESTPIPE"


def test_weighted_method_is_carried_through():
    cfg = component_save_config(_chamber(method="pytlwall (weighted)"))
    spec = next(iter(cfg["devices"].values()))
    assert spec["weighted"] is True
    assert spec["name"] == "TESTPIPE"       # label stripped, weighting kept


def test_explicit_method_overrides_the_enabled_model():
    cfg = component_save_config(_chamber(method="pytlwall"), method="IW2D")
    assert next(iter(cfg["devices"].values()))["method"] == "iw2d"


def test_precalculated_without_a_file_is_refused_with_advice():
    el = _chamber(method="precalculated")
    with pytest.raises(ValueError, match="import map"):
        component_save_config(el)


def test_element_own_gamma_wins_over_the_open_config():
    cfg = component_save_config(_chamber(), base_cfg={"gamma": 7000.0})
    assert cfg["gamma"] == 479.6


def test_text_is_valid_yaml_under_its_header():
    cfg = component_save_config(_chamber())
    text = component_config_text(cfg, "pytlwall")
    assert text.startswith("# WIMBA component: TESTPIPE (pytlwall)")
    assert yaml.safe_load(text) == cfg


def test_a_component_with_no_beam_says_so_in_the_file():
    el = _chamber()
    el.own_base = {}
    cfg = component_save_config(el)
    assert cfg.get("gamma") is None
    assert "no gamma" in component_config_text(cfg)
