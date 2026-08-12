"""Projects and scenarios: the container, its files, and the rules that keep a
comparison meaningful."""
import pytest
import yaml

from wimba.core.beam import Beam
from wimba.gui.model import (GProject, GScenario, as_number, freeze_config,
                             grid_of, slugify)


def test_slug_is_a_folder_name_not_the_label():
    assert slugify("flat top") == "flat_top"
    assert slugify("Iniezione 450 GeV") == "iniezione_450_gev"
    assert slugify("   ") == "scenario"          # never an empty folder name


def test_yaml_exponents_without_a_sign_are_still_numbers():
    """PyYAML reads 1.0e8 as a string; anything formatted with :g would raise."""
    cfg = yaml.safe_load("grid:\n  frequency: {min: 1.0e8, max: 3.0e9, n: 400}\n")
    assert isinstance(cfg["grid"]["frequency"]["min"], str)      # the trap
    grid = grid_of(cfg)
    assert grid["frequency"]["min"] == 1.0e8
    assert grid["frequency"]["n"] == 400 and isinstance(grid["frequency"]["n"], int)


def test_as_number_leaves_what_is_not_a_number_alone():
    assert as_number("abc") == "abc"
    assert as_number(True) is True


def test_labels_are_made_unique_so_folders_cannot_collide():
    p = GProject("P", "/tmp/p")
    p.add(GScenario("injection", "injection_config.yaml"))
    assert p.unique_label("injection") == "injection (2)"
    assert p.unique_label("flat top") == "flat top"


def test_a_duplicate_folder_name_is_refused():
    p = GProject("P", "/tmp/p")
    p.add(GScenario("flat top", "a.yaml"))
    with pytest.raises(ValueError, match="already exists"):
        p.add(GScenario("flat  TOP", "b.yaml"))       # same slug


def test_renaming_carries_the_lineage_with_it():
    p = GProject("P", "/tmp/p")
    p.add(GScenario("injection", "a.yaml"))
    p.add(GScenario("flat top", "b.yaml", derived_from="injection"))
    p.rename(0, "inj 450")
    assert p.scenarios[1].derived_from == "inj 450"
    assert p.scenarios[0].slug == "inj_450"


def test_a_scenario_others_were_duplicated_from_cannot_just_vanish():
    p = GProject("P", "/tmp/p")
    p.add(GScenario("injection", "a.yaml"))
    p.add(GScenario("flat top", "b.yaml", derived_from="injection"))
    with pytest.raises(ValueError, match="duplicated from"):
        p.remove(0)
    p.remove(1)
    assert p.labels() == ["injection"]


def test_project_round_trips_through_yaml(tmp_path):
    p = GProject("LHC study", str(tmp_path), grid={"frequency": {"min": 1e8}})
    p.add(GScenario("injection", "injection_config.yaml",
                    beam=Beam("proton", "gamma", 479.605)))
    p.add(GScenario("flat top", "flat_top_config.yaml",
                    beam=Beam("proton", "energy", 7.0e12),
                    derived_from="injection"))

    again = GProject.from_dict(yaml.safe_load(yaml.safe_dump(p.to_dict())), tmp_path)
    assert again.labels() == ["injection", "flat top"]
    assert again.scenarios[0].beam.gamma == pytest.approx(479.605)
    assert again.scenarios[1].beam.mode == "energy"      # the input mode survives
    assert again.scenarios[1].derived_from == "injection"


def test_freezing_a_config_keeps_its_data_reachable(tmp_path):
    """The config is copied so a scenario owns it; the data it points at is not,
    so the copy has to point at the original location."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "m.tfs").write_text("twiss")
    (src_dir / "z.dat").write_text("data")
    (src_dir / "c.yaml").write_text(
        "name: M\noptics: m.tfs\n"
        "groups:\n  g:\n    - {name: E, source: cst, term: zlong, file: z.dat}\n")

    out = freeze_config(src_dir / "c.yaml", tmp_path / "proj" / "m_config.yaml")
    cfg = yaml.safe_load(out.read_text())
    assert cfg["optics"] == str((src_dir / "m.tfs").resolve())
    assert cfg["groups"]["g"][0]["file"] == str((src_dir / "z.dat").resolve())
    assert cfg["name"] == "M"                    # everything else untouched


def test_freezing_leaves_unresolvable_references_as_written(tmp_path):
    src = tmp_path / "c.yaml"
    src.write_text("name: M\noptics: /elsewhere/m.tfs\ngroups: {}\n")
    cfg = yaml.safe_load(freeze_config(src, tmp_path / "out.yaml").read_text())
    assert cfg["optics"] == "/elsewhere/m.tfs"


# ------------------------------------------------------- the build results path
def test_results_read_the_build_layout(tmp_path):
    """`build` writes a resume plus one .dat per component; `run` writes CSVs
    under single_elements/. The Results panel has to read both, or a machine
    computed from the GUI produces files nothing can plot."""
    import numpy as np
    from wimba import Element, Explicit, Machine, Project, Resonator
    from wimba import ResonatorProvider, Scenario, materialize
    from wimba.gui.results import ResultsModel

    m = Machine()
    m.add_group("cavities").add(
        Element("c1", "rf", 1.0,
                ResonatorProvider([Resonator("zlong", 1.0e4, 1.0, 1.0e9)]),
                optics=Explicit(1.0, 1.0),
                meta={"position": 0.0, "beta_x": 1.0, "beta_y": 1.0, "info": {}}))
    proj = Project("P", freqs=np.linspace(1e8, 2e9, 32))
    materialize(proj.add(Scenario("injection", m)), tmp_path / "out")

    model = ResultsModel().load(tmp_path / "out")
    assert "Total" in model.sources
    assert "cavities/c1" in model.sources
    x, y, label = model.series("Total", "impedance", "ZLong", "Re")
    assert len(x) == 32 and np.any(y != 0)
    assert label == "Total ZLong Re"
