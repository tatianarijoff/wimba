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


class _Beam:
    """Enough of wimba.core.beam.Beam for the writers under test."""
    def __init__(self, gamma=7461.0):
        self.gamma, self.mode = gamma, "gamma"

    def to_dict(self):
        return {"particle": "proton", "gamma": self.gamma}


def _machine(*elements, name="TESTRING", group="devices", beam=None):
    gm = new_machine(name)
    gm.groups = [GGroup(name=group, elements=list(elements))]
    gm.beam = beam
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


# ----------------------------------------------------- elements added here ---
# An element created in the window has no entry to patch. It used to vanish on
# save without a word, which is the failure mode worth the most tests: you find
# out about it the next time you open the file, long after the session is gone.

def _added(name="NEW"):
    el = _wall(name)
    el.added = True
    return el


def test_an_added_element_reaches_a_machine_file():
    from wimba.gui.model import patch_config

    gm = _machine(_wall("OLD"), beam=_Beam(), *[_added()])
    cfg = {"name": "M",
           "groups": {"devices": [{"name": "OLD", "source": "pytlwall",
                                   "length": 1.0}]}}
    out = patch_config(cfg, gm)
    assert [e["name"] for e in out["groups"]["devices"]] == ["OLD", "NEW"]
    assert out["groups"]["devices"][1]["source"] == "pytlwall"


def test_an_added_element_reaches_an_assembly_config():
    from wimba.gui.model import patch_config

    gm = _machine(_wall("OLD"), _added())
    cfg = {"name": "M",
           "devices": {"old": {"name": "OLD", "source": "chamber",
                               "method": "pytlwall"}},
           "default_pipe": {"method": "pytlwall"}}
    out = patch_config(cfg, gm)
    assert set(out["devices"]) == {"old", "new"}
    spec = out["devices"]["new"]
    assert spec["name"] == "NEW"
    assert spec["source"] == "chamber"        # the assembly dialect's spelling
    assert "length_m" in spec and "length" not in spec


def test_an_element_that_cannot_be_written_stops_the_whole_save():
    """Refusing beats dropping it quietly: the file stays as it was, and the
    message names what is wrong."""
    from wimba.gui.model import GMode, default_models, new_element, patch_config

    bad = new_element("RF")
    bad.added = True
    bad.models = default_models("resonator")
    for m in bad.models:
        m.enabled = True                      # a resonator with no modes
    gm = _machine(_wall("OLD"), beam=_Beam(), *[bad])
    cfg = {"name": "M", "groups": {"devices": [{"name": "OLD"}]}}
    with pytest.raises(ValueError, match="RF"):
        patch_config(cfg, gm)

    bad.modes = [GMode(q="ZLong", Rs=1.0e5, Q=100.0, fr=1.0e9)]
    out = patch_config(cfg, gm)               # fixed, and now it goes in
    assert [e["name"] for e in out["groups"]["devices"]] == ["OLD", "RF"]


def test_saving_twice_does_not_append_the_element_twice():
    from wimba.gui.model import clear_added, patch_config

    gm = _machine(_wall("OLD"), beam=_Beam(), *[_added()])
    cfg = {"name": "M", "groups": {"devices": [{"name": "OLD"}]}}
    first = patch_config(cfg, gm)
    clear_added(gm)                           # what write_config does on success
    second = patch_config(first, gm)
    assert [e["name"] for e in second["groups"]["devices"]] == ["OLD", "NEW"]


def test_an_element_from_a_file_driven_entry_is_not_treated_as_new():
    """A `file:` entry expands to names patch_config cannot see, so matching by
    name would append a duplicate. Only the window's own flag counts."""
    from wimba.gui.model import patch_config

    gm = _machine(_wall("BPMS.1"))            # no `added` flag
    cfg = {"name": "M",
           "devices": {"bpms": {"source": "precalculated", "files": {}}},
           "default_pipe": {"method": "pytlwall"}}
    out = patch_config(cfg, gm)
    assert set(out["devices"]) == {"bpms"}


# ------------------------------------------- a config that moves to a new dir ---
# `optics:` and every `file:` are relative to the config, so a copy saved
# elsewhere points at files that are not there. The copy states where the data
# lives rather than absolutising the references, which would pin the file to one
# machine, or copying a twiss that may be enormous.

def test_a_config_saved_elsewhere_says_where_its_data_is(tmp_path):
    from wimba.gui.model import data_dir_for_move

    src = tmp_path / "study" / "SubLHC.yaml"
    cfg = {"optics": "SubLHC.tfs",
           "groups": {"g": [{"name": "E", "source": "table", "file": "z.dat"}]}}
    assert data_dir_for_move(src, tmp_path / "away" / "copy.yaml", cfg) == \
        [str((tmp_path / "study").resolve())]


def test_saving_beside_the_original_needs_no_data_dir(tmp_path):
    from wimba.gui.model import data_dir_for_move

    src = tmp_path / "SubLHC.yaml"
    cfg = {"optics": "SubLHC.tfs"}
    assert data_dir_for_move(src, tmp_path / "copy.yaml", cfg) == []


def test_absolute_references_need_no_data_dir(tmp_path):
    from wimba.gui.model import data_dir_for_move

    cfg = {"optics": "/data/SubLHC.tfs"}
    assert data_dir_for_move(tmp_path / "a.yaml", tmp_path / "b" / "c.yaml", cfg) == []


def test_an_existing_data_dir_is_extended_and_kept_first(tmp_path):
    """The user put it there; the move adds to it rather than replacing it."""
    from wimba.gui.model import data_dir_for_move

    src = tmp_path / "study" / "m.yaml"
    cfg = {"optics": "m.tfs", "data_dir": "/opt/shared"}
    assert data_dir_for_move(src, tmp_path / "away" / "m.yaml", cfg) == \
        ["/opt/shared", str((tmp_path / "study").resolve())]


def test_a_reference_nested_in_a_device_counts_too(tmp_path):
    from wimba.gui.model import data_dir_for_move

    src = tmp_path / "study" / "m.yaml"
    cfg = {"devices": {"d": {"files": {"ZLong": "a.dat"}}}}
    assert data_dir_for_move(src, tmp_path / "away" / "m.yaml", cfg) != []


def test_a_refused_save_as_leaves_no_file_behind(tmp_path):
    """Copying first and patching after left a file at the destination when the
    patch was refused: it looked saved, and held the state before the edits."""
    from wimba.gui.model import GGroup, new_machine, save_config_as

    src = tmp_path / "study" / "m.yaml"
    src.parent.mkdir()
    src.write_text("name: M\ngroups:\n  g:\n    - {name: OLD, source: pytlwall}\n")
    gm = new_machine("M")
    gm.groups = [GGroup(name="g", elements=[_wall("OLD")])]
    gm.beam = _Beam()

    broken = _wall("MYELEM.2")
    broken.geometry.pop("radius")               # the case she hit
    broken.added = True
    gm.groups[0].elements.append(broken)

    dest = tmp_path / "away" / "copy.yaml"
    with pytest.raises(ValueError, match="MYELEM.2"):
        save_config_as(src, dest, gm)
    assert not dest.exists()
    assert broken.added is True                 # still new, so the retry writes it

    broken.geometry["radius"] = 0.03
    save_config_as(src, dest, gm)
    assert "MYELEM.2" in dest.read_text()
    assert broken.added is False


def test_save_as_elsewhere_writes_the_data_dir_and_keeps_comments(tmp_path):
    pytest.importorskip("ruamel.yaml")
    from wimba.gui.model import GGroup, new_machine, save_config_as

    src = tmp_path / "study" / "m.yaml"
    src.parent.mkdir()
    src.write_text("name: M\noptics: m.tfs   # the lattice this study uses\n"
                   "groups:\n  g:\n    - {name: OLD, source: pytlwall}\n")
    gm = new_machine("M")
    gm.groups = [GGroup(name="g", elements=[_wall("OLD")])]

    dest = tmp_path / "away" / "copy.yaml"
    save_config_as(src, dest, gm)
    text = dest.read_text()
    assert "the lattice this study uses" in text     # a patch, not a rewrite
    assert "optics: m.tfs" in text                   # reference left readable
    assert str((tmp_path / "study").resolve()) in text


# ------------------------------------------------- the energy a new element needs

def _with_added(beam=None, own=None):
    from wimba.gui.model import GGroup, new_machine
    gm = new_machine("M")
    new = _wall("ELEM.2")
    new.added = True
    if own:
        new.own_base = own
    gm.groups = [GGroup(name="g", elements=[_wall("OLD"), new])]
    gm.beam = beam
    return gm


PER_ELEMENT = {"name": "M",
               "groups": {"g": [{"name": "OLD", "source": "pytlwall",
                                 "gamma": 7461.0}]}}


def test_a_machine_beam_makes_the_config_state_one_beam_for_everyone():
    """With an energy in the panels, patch_config writes it once at the top and
    the new element needs none of its own."""
    from wimba.gui.model import patch_config

    out = patch_config(dict(PER_ELEMENT), _with_added(beam=_Beam(7461.0)))
    assert out["beam"]["gamma"] == 7461.0
    assert out["groups"]["g"][1]["name"] == "ELEM.2"


def test_an_element_added_to_a_per_element_config_carries_its_own_energy():
    """The case that produced a file which saved cleanly and would not load: no
    beam anywhere at the top, an energy on every element, and none on the new
    one."""
    from wimba.gui.model import patch_config

    out = patch_config(dict(PER_ELEMENT), _with_added(own={"gamma": 479.6}))
    assert "beam" not in out                     # the file's own kind is kept
    assert out["groups"]["g"][1]["gamma"] == 479.6


def test_a_wall_with_no_energy_stops_the_save_instead_of_the_next_load():
    """The case from the log: SubLHC needs no beam because nothing in it is a
    wall, so the first wall added to it had no energy, saved cleanly, and failed
    on the next load."""
    from wimba.gui.model import patch_config

    cfg = {"name": "M", "groups": {"g": [{"name": "RF", "source": "resonator"}]}}
    with pytest.raises(ValueError, match="wall"):
        patch_config(cfg, _with_added())


def test_an_element_that_needs_no_energy_is_written_without_one():
    """Only a wall is computed at a gamma. A config of resonators states no
    beam and is complete as it stands; adding another resonator to it must not
    start asking for an energy nobody needs."""
    from wimba.gui.model import GMode, default_models, new_element, patch_config

    res = new_element("RF.2")
    res.added = True
    res.models = default_models("resonator")
    for m in res.models:
        m.enabled = True
    res.modes = [GMode(q="ZLong", Rs=1.0e5, Q=100.0, fr=1.0e9)]
    gm = _machine(res)
    cfg = {"name": "M", "groups": {"devices": [{"name": "RF.1",
                                                "source": "resonator"}]}}
    # RF.1 has no counterpart in this machine, so it is removed as usual; what
    # matters here is what the appended entry does and does not carry
    out = patch_config(cfg, gm)
    added = out["groups"]["devices"][-1]
    assert added["name"] == "RF.2" and "gamma" not in added
    assert added["source"] == "resonator"


def test_a_config_that_states_a_beam_needs_no_per_element_energy():
    from wimba.gui.model import patch_config

    cfg = {"name": "M", "beam": {"particle": "proton", "gamma": 7461.0},
           "groups": {"g": [{"name": "OLD", "source": "pytlwall"}]}}
    out = patch_config(cfg, _with_added(beam=_Beam(7461.0)))
    assert "gamma" not in out["groups"]["g"][1]


# --------------------------------------------- an element read back from a config

class _CoreElement:
    """A core Element as the assembler hands it to the GUI layer."""
    def __init__(self, info, length=1.4):
        self.name, self.category, self.length = "My Component", "element", length
        self.meta = {"position": None, "beta_x": 1.0, "beta_y": 1.0, "info": info}


LAYERS = [{"type": "CW", "sigma": 3.81e7, "thickness": "inf", "boundary": False},
          {"type": "CW", "sigma": 1.4e6, "thickness": "inf", "boundary": True}]


def test_layers_are_in_the_layers_tab_and_nowhere_else(monkeypatch):
    """They used to be in both places: correctly in the Layers tab, and again as
    a Python repr inside an editable Geometry field."""
    from wimba.gui import model as m

    monkeypatch.setattr(m, "_models_from_provider", lambda e: m.default_models("pytlwall"))
    monkeypatch.setattr(m, "_modes_from_provider", lambda e: [])
    el = m._element_from(_CoreElement(
        {"shape": "CIRCULAR", "radius": 0.02, "layers": LAYERS}))

    assert "layers" not in el.geometry
    assert [lay["sigma"] for lay in el.layers] == [3.81e7, 1.4e6]


def test_the_length_is_where_the_geometry_tab_reads_it(monkeypatch):
    from wimba.gui import model as m

    monkeypatch.setattr(m, "_models_from_provider", lambda e: m.default_models("pytlwall"))
    monkeypatch.setattr(m, "_modes_from_provider", lambda e: [])
    el = m._element_from(_CoreElement({"shape": "CIRCULAR", "radius": 0.02}))
    assert el.geometry["length"] == 1.4 and el.optics["l"] == 1.4


def test_an_option_nobody_set_gets_no_field(monkeypatch):
    """The Geometry tab builds a row per key it finds, so a None would become a
    blank box that looks like something the user forgot to fill in."""
    from wimba.gui import model as m

    monkeypatch.setattr(m, "_models_from_provider", lambda e: m.default_models("pytlwall"))
    monkeypatch.setattr(m, "_modes_from_provider", lambda e: [])
    el = m._element_from(_CoreElement(
        {"shape": "CIRCULAR", "radius": 0.02, "iw2d_yokoya": None,
         "test_beam_shift": None, "method": "pytlwall", "source": "chamber",
         "name": "My Component"}))

    assert sorted(el.geometry) == ["length", "radius", "shape"]


def test_a_stated_option_keeps_its_field(monkeypatch):
    from wimba.gui import model as m

    monkeypatch.setattr(m, "_models_from_provider", lambda e: m.default_models("pytlwall"))
    monkeypatch.setattr(m, "_modes_from_provider", lambda e: [])
    el = m._element_from(_CoreElement(
        {"shape": "CIRCULAR", "radius": 0.02, "test_beam_shift": 0.003}))
    assert el.geometry["test_beam_shift"] == 0.003


def test_the_row_path_from_config_is_normalised_the_same_way():
    """from_config builds its elements from assembly rows, not from _element_from,
    and that is the path Open Component takes - so it is the one that showed the
    layers twice."""
    from wimba.gui.model import _panel_geometry

    raw = {"shape": "CIRCULAR", "radius": 0.02, "layers": LAYERS,
           "iw2d_yokoya": None, "method": "pytlwall"}
    geo = _panel_geometry(raw, length=1.4)
    assert sorted(geo) == ["length", "radius", "shape"]
    assert geo["length"] == 1.4
    assert raw["layers"] is LAYERS          # the caller still reads them from here
