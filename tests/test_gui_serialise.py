"""Writing the panels back into a scenario's config.

The rule under test throughout: the file is patched, never regenerated. What the
GUI does not own has to survive untouched, because the view-model is a lossy
picture of the config.
"""
import pytest
import yaml

from wimba.core.beam import Beam
from wimba.gui.model import (GElement, GGroup, GMachine, patch_config,
                             write_config)


def _machine(*elements, beam=None):
    gm = GMachine(name="M", beam=beam)
    gm.groups.append(GGroup("g", list(elements)))
    return gm


def _element(name, **optics):
    return GElement(name=name, optics=optics)


MACHINE_CFG = {
    "name": "M", "optics": "m.tfs",
    "grid": {"frequency": {"min": 1.0e7, "max": 1.0e9, "n": 8}},
    "groups": {"g": [{"name": "A", "source": "pytlwall", "radius_m": 0.02,
                      "layers": [{"material": "copper", "thickness": 0.002}]},
                     {"name": "B", "source": "resonator",
                      "resonators": [{"term": "zlong", "Rs": 1e4, "Q": 1, "fr": 1e9}]}]},
}

ASSEMBLY_CFG = {
    "name": "S", "optics": "m.tfs",
    "default_pipe": {"method": "pytlwall", "radius_mm": 22},
    "devices": {"coll": {"source": "chamber", "name": "A", "radius_m": 0.01,
                         "beta_x": 130, "beta_y": 85},
                "kick": {"source": "chamber", "name": "B", "radius_m": 0.02}},
}


def test_the_beam_is_written_and_the_old_gamma_key_goes_away():
    cfg = dict(MACHINE_CFG, gamma=7000.0)
    out = patch_config(cfg, _machine(_element("A"), _element("B"),
                                     beam=Beam("proton", "gamma", 479.605)))
    assert out["beam"]["gamma"] == pytest.approx(479.605)
    assert "gamma" not in out          # one authority for the energy, not two


def test_nothing_the_gui_does_not_own_is_touched():
    out = patch_config(MACHINE_CFG, _machine(_element("A"), _element("B")))
    a = out["groups"]["g"][0]
    assert a["layers"] == [{"material": "copper", "thickness": 0.002}]
    assert a["radius_m"] == 0.02 and out["grid"] == MACHINE_CFG["grid"]


def test_layers_are_not_wiped_by_a_view_model_that_never_had_them():
    """An element loaded from a machine file arrives with layers=[]; writing that
    back would delete the real ones."""
    el = GElement(name="A", layers=[])
    out = patch_config(MACHINE_CFG, _machine(el, _element("B")))
    assert out["groups"]["g"][0]["layers"] == MACHINE_CFG["groups"]["g"][0]["layers"]


def test_removing_an_element_removes_its_entry():
    out = patch_config(MACHINE_CFG, _machine(_element("A")))
    names = [e["name"] for e in out["groups"]["g"]]
    assert names == ["A"]


def test_removing_an_element_removes_its_device_in_an_assembly_config():
    out = patch_config(ASSEMBLY_CFG, _machine(_element("A")))
    assert set(out["devices"]) == {"coll"}
    assert out["default_pipe"] == ASSEMBLY_CFG["default_pipe"]    # a rule, kept


def test_the_default_pipe_element_is_not_mistaken_for_a_missing_element():
    pipe = GElement(name="lhc_default_pipe", category="default_pipe")
    out = patch_config(ASSEMBLY_CFG, _machine(_element("A"), _element("B"), pipe))
    assert set(out["devices"]) == {"coll", "kick"}


def test_an_entry_whose_elements_cannot_be_named_is_never_dropped():
    """A file-driven device expands to many elements at load time; this function
    cannot see their names, so it must not judge it."""
    cfg = dict(ASSEMBLY_CFG,
               devices={"colls": {"source": "collimators", "file": "colls.txt"}})
    out = patch_config(cfg, _machine(_element("A")))
    assert set(out["devices"]) == {"colls"}


def test_only_values_the_user_edited_are_written():
    shown = _element("A", bx=130.0, by=85.0)          # displayed, not edited
    out = patch_config(MACHINE_CFG, _machine(shown, _element("B")))
    assert "beta_x" not in out["groups"]["g"][0]

    edited = _element("A", bx=999.0, by=85.0)
    edited.edited.add("bx")
    out = patch_config(MACHINE_CFG, _machine(edited, _element("B")))
    assert out["groups"]["g"][0]["beta_x"] == 999.0
    assert "beta_y" not in out["groups"]["g"][0]


def test_an_edited_length_follows_the_spelling_already_in_the_file():
    el = _element("A", l=2.5); el.edited.add("l")
    machine_out = patch_config(MACHINE_CFG, _machine(el, _element("B")))
    assert machine_out["groups"]["g"][0]["length"] == 2.5

    cfg = {"devices": {"coll": {"source": "chamber", "name": "A", "length_m": 1.0}}}
    assembly_out = patch_config(cfg, _machine(el))
    assert assembly_out["devices"]["coll"]["length_m"] == 2.5


def test_edited_geometry_and_layers_reach_the_entry():
    el = GElement(name="A", geometry={"radius": 0.03, "shape": "ELLIPTICAL",
                                      "hor": 0.03, "ver": 0.01},
                  layers=[{"material": "steel", "thickness": 0.001, "sigma": None}])
    el.edited.update({"geometry", "layers"})
    out = patch_config(MACHINE_CFG, _machine(el, _element("B")))
    a = out["groups"]["g"][0]
    assert a["radius_m"] == 0.03 and a["shape"] == "ELLIPTICAL"
    assert a["hor_m"] == 0.03 and a["ver_m"] == 0.01
    assert a["layers"] == [{"material": "steel", "thickness": 0.001}]   # None dropped


def test_a_new_optics_file_replaces_the_old_one():
    out = patch_config(MACHINE_CFG, _machine(_element("A"), _element("B")),
                       optics="/data/twiss_7tev.tfs")
    assert out["optics"] == "/data/twiss_7tev.tfs"


def test_write_config_leaves_an_unchanged_file_alone(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump(MACHINE_CFG, sort_keys=False))
    before = path.stat().st_mtime_ns
    write_config(path, _machine(_element("A"), _element("B")))
    assert path.stat().st_mtime_ns == before


def test_write_config_applies_the_change_on_disk(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump(MACHINE_CFG, sort_keys=False))
    write_config(path, _machine(_element("A"), beam=Beam("proton", "gamma", 7461.0)))
    cfg = yaml.safe_load(path.read_text())
    assert [e["name"] for e in cfg["groups"]["g"]] == ["A"]
    assert cfg["beam"]["gamma"] == 7461.0
