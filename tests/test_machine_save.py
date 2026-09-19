"""Saving a machine that has no file behind it, and working without optics.

Two rules are under test here, and they are the two the GUI now leans on:

  * a machine with no file is written IN FULL, in the machine dialect, and what
    comes back out of the loader is the machine that went in;
  * a beta is never omitted, because an element with no ``beta_x`` whose name is
    not in the twiss is read back as PRE-WEIGHTED - a silent change of meaning
    for a wall WIMBA computes.

Qt is not needed: everything here is the model layer.
"""
import textwrap

import pytest

yaml = pytest.importorskip("yaml")

from wimba.gui.model import (GGroup, GMode, default_models, is_unweighted,
                             machine_config, machine_config_text, new_element,
                             new_machine)


def _wall(name="TCP", bx=None, by=None, length=1.2):
    el = new_element(name)
    el.geometry = {"shape": "CIRCULAR", "radius": 0.02, "length": length}
    el.layers = [{"type": "CW", "sigma": 1.35e6, "thickness": "inf",
                  "boundary": True}]
    el.models = default_models("pytlwall")
    for m in el.models:
        m.enabled = True
    if bx is not None:
        el.optics = {"bx": bx, "by": by if by is not None else bx, "l": length}
    return el


def _machine(*elements, name="TESTRING", group="devices"):
    gm = new_machine(name)
    gm.groups = [GGroup(name=group, elements=list(elements))]
    return gm


def test_machine_config_round_trips_through_yaml():
    cfg = machine_config(_machine(_wall()))
    data = yaml.safe_load(machine_config_text(cfg))
    el = data["groups"]["devices"][0]
    assert el["name"] == "TCP"
    assert el["source"] == "pytlwall"          # the machine dialect's spelling,
    assert el["length"] == pytest.approx(1.2)  # not the assembly one
    assert "length_m" not in el
    assert data["grid"]["frequency"]["n"] > 0


def test_a_beta_is_always_written():
    """Omitting it would make the loader read the element as pre-weighted."""
    el = machine_config(_machine(_wall()))["groups"]["devices"][0]
    assert el["beta_x"] == 1.0 and el["beta_y"] == 1.0
    assert "pre_weighted" not in el


def test_stated_betas_survive():
    el = machine_config(_machine(_wall(bx=30.0, by=12.5)))["groups"]["devices"][0]
    assert (el["beta_x"], el["beta_y"]) == (30.0, 12.5)


def test_preweighted_element_says_so_instead_of_carrying_a_beta():
    el = _wall(name="BPMS")
    el.optics["pre"] = True
    spec = machine_config(_machine(el))["groups"]["devices"][0]
    assert spec["pre_weighted"] is True
    assert "beta_x" not in spec


def test_resonator_uses_the_machine_dialect_spelling():
    el = new_element("RF")
    el.models = default_models("resonator")
    for m in el.models:
        m.enabled = True
    el.modes = [GMode(q="ZLong", Rs=1.1e5, Q=420.0, fr=6.35e8)]
    spec = machine_config(_machine(el))["groups"]["devices"][0]
    assert spec["source"] == "resonator"
    assert spec["resonators"] == [{"term": "ZLong", "Rs": 1.1e5, "Q": 420.0,
                                   "fr": 6.35e8}]
    assert "modes" not in spec


def test_resonator_without_modes_is_refused_by_name():
    el = new_element("RF")
    el.models = default_models("resonator")
    for m in el.models:
        m.enabled = True
    with pytest.raises(ValueError, match="RF"):
        machine_config(_machine(el))


def test_header_declares_the_unweighted_case():
    text = machine_config_text(machine_config(_machine(_wall())))
    assert "NO OPTICS FILE" in text
    assert "UNWEIGHTED" in text
    assert "no beam" in text                      # and the missing energy


def test_header_is_quiet_once_there_is_an_optics_file():
    gm = _machine(_wall(bx=30.0))
    gm.optics_path = "twiss.tfs"
    text = machine_config_text(machine_config(gm))
    assert "NO OPTICS FILE" not in text
    assert yaml.safe_load(text)["optics"] == "twiss.tfs"


def test_is_unweighted_follows_the_betas_not_just_the_file():
    assert is_unweighted(_machine(_wall())) is True
    assert is_unweighted(_machine(_wall(bx=30.0))) is False
    gm = _machine(_wall())
    gm.optics_path = "twiss.tfs"
    assert is_unweighted(gm) is False


def test_the_default_pipe_pseudo_element_is_never_written():
    """It stands for a rule in an assembly config; a rule is not an element."""
    pipe = _wall(name="default pipe")
    pipe.category = "default_pipe"
    cfg = machine_config(_machine(_wall(), pipe))
    assert [e["name"] for e in cfg["groups"]["devices"]] == ["TCP"]


# --------------------------------------------------------------- no optics ---

def test_no_optics_collapses_the_per_device_warnings():
    """One statement when nothing could be located, N when the lattice exists."""
    from wimba.assembly import unlocated_warnings

    class Row:
        def __init__(self, name, source, kind="device", weighted=False):
            self.name, self.beta_source = name, source
            self.kind, self.weighted = kind, weighted

    rows = [Row("A", "default-1"), Row("B", "default-1"), Row("C", "default-1")]
    out = unlocated_warnings(rows, has_lattice=False)
    assert len(out) == 1
    assert "no optics" in out[0] and "unweighted" in out[0]

    # The same rows WITH a lattice are three mistakes, not one mode: a device
    # nobody could place in a twiss that exists is the case the per-device
    # wording was written for, and collapsing those would hide them.
    out = unlocated_warnings(rows, has_lattice=True)
    assert len(out) == 3
    assert "'B'" in out[1]

    out = unlocated_warnings([Row("A", "interp"), Row("B", "default-1")],
                             has_lattice=True)
    assert len(out) == 1 and "'B'" in out[0]


def test_a_machine_written_without_optics_reloads_as_the_same_machine(tmp_path):
    """The round trip that matters: window -> file -> loader."""
    loader = pytest.importorskip("wimba.builders.loader")
    path = tmp_path / "testring.yaml"
    path.write_text(machine_config_text(machine_config(_machine(_wall(length=2.5)))))

    data = yaml.safe_load(path.read_text())
    # The machine states no beam, and the loader is right to refuse a chamber at
    # an unstated energy; what is under test here is the geometry and the beta,
    # so the energy is given on the element and no Beam is needed.
    data["groups"]["devices"][0]["gamma"] = 7461.0
    machine = loader._build_machine(data, tmp_path, None)
    (element,) = [e for g in machine.groups for e in g.elements]
    assert element.name == "TCP"
    assert element.length == pytest.approx(2.5)
    # the element must NOT have become pre-weighted for want of a twiss
    assert element.meta["beta_x"] == 1.0
    assert element.meta["info"].get("pre_weighted") is not True


def test_text_is_valid_yaml_under_a_comment_header():
    text = machine_config_text(machine_config(_machine(_wall())))
    assert text.startswith("# WIMBA machine:")
    assert yaml.safe_load(text)["name"] == "TESTRING"
    assert textwrap.dedent(text) == text          # no accidental indentation
