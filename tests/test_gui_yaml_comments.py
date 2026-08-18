"""A config's comments must survive being written back by the GUI.

A user's config is not a generated file: its comments are where the reasoning
lives -- why space charge is off, where a number came from, which alternative
block to uncomment. PyYAML throws that text away on safe_load/safe_dump, and a
Save Project silently stripped it. This is what caught it: an FCC-ee scenario
config came back 62 lines shorter, all of them comments, including a
commented-out alternative block that was part of the documentation.
"""
import pytest

from wimba.gui.model import read_yaml_text, write_yaml_text

pytest.importorskip("ruamel.yaml",
                    reason="comment preservation needs the gui extra")

CONFIG = """\
# FCC-ee Z 45.6 GeV -- acc-models LCC_107.0.1
#
# Optics is NOT in the release: generate it first.
name: FCCee_z
optics: fccee_z_twiss.tfs

beam:
  particle: positron
  gamma: 89236.973970299   # from particle_ref, matches the parameter table

default_pipe:
  method: pytlwall
  space_charge: false   # 1/gamma^2 = 1.3e-10, indirect space charge is negligible
  file: data/fccee_default_pipe.json

# Alternative to the pytlwall default_pipe above -- never both:
#  pipe_rw:
#    source: precalculated
#    weighted: true
"""


def test_untouched_config_round_trips_with_its_comments():
    out = write_yaml_text(read_yaml_text(CONFIG))
    assert out.count("#") == CONFIG.count("#")
    assert "space charge is negligible" in out
    assert "#  pipe_rw:" in out            # the commented-out alternative survives


def test_an_edit_keeps_every_other_comment():
    data = read_yaml_text(CONFIG)
    data["beam"]["gamma"] = 156556.094685
    out = write_yaml_text(data)
    assert "gamma: 156556.094685" in out
    assert out.count("#") == CONFIG.count("#")
    assert "acc-models LCC_107.0.1" in out
    assert "#  pipe_rw:" in out


def test_key_order_is_preserved():
    out = write_yaml_text(read_yaml_text(CONFIG))
    assert out.index("name:") < out.index("optics:") < out.index("beam:")


def test_values_survive_the_round_trip():
    data = read_yaml_text(CONFIG)
    assert data["name"] == "FCCee_z"
    assert data["default_pipe"]["space_charge"] is False
    assert data["beam"]["gamma"] == pytest.approx(89236.973970299)


def test_write_config_keeps_comments(tmp_path):
    """The real entry point, not just the helpers."""
    from wimba.gui.model import GMachine, write_config
    p = tmp_path / "scenario_config.yaml"
    p.write_text(CONFIG)
    write_config(p, GMachine(name="FCCee_z"))
    after = p.read_text()
    assert after.count("#") == CONFIG.count("#")
    assert "#  pipe_rw:" in after


def test_patch_config_does_not_mutate_its_input():
    """It is a pure function: the GUI keeps the config it hands over."""
    from wimba.gui.model import GElement, GGroup, GMachine, patch_config
    cfg = read_yaml_text(CONFIG)
    before = write_yaml_text(cfg)
    machine = GMachine(name="FCCee_z",
                       groups=[GGroup(name="g", elements=[GElement(name="BPM")])])
    patch_config(cfg, machine)
    assert write_yaml_text(cfg) == before


def test_freeze_config_keeps_comments(tmp_path):
    src = tmp_path / "src.yaml"
    src.write_text(CONFIG)
    from wimba.gui.model import freeze_config
    out = freeze_config(src, tmp_path / "proj" / "frozen.yaml").read_text()
    assert out.count("#") == CONFIG.count("#")
    assert "#  pipe_rw:" in out
    assert out.lstrip().startswith("# FCC-ee Z")


def test_comment_after_the_beam_block_survives_a_beam_edit():
    """ruamel hangs a mapping's trailing comments on its last key, so replacing
    the whole beam node used to take the block written under it."""
    from wimba.core.beam import Beam
    from wimba.gui.model import GMachine, patch_config
    cfg = read_yaml_text(CONFIG + "\n# a note written under the beam block\nname2: x\n")
    out = write_yaml_text(
        patch_config(cfg, GMachine(name="x", beam=Beam(particle="positron",
                                                       mode="gamma", value=1000.0))))
    assert "a note written under the beam block" in out
    assert "gamma: 1000.0" in out
