"""The Scenario/Project split: grids belong to the project, machines to scenarios."""
import numpy as np
import pytest

from wimba import (Element, Explicit, Machine, Project, Resonator,
                   ResonatorProvider, Scenario, load_project, load_scenario,
                   materialize)


def _machine(rs=1.0e4):
    m = Machine()
    g = m.add_group("cavities")
    g.add(Element("c1", "rf", 1.0,
                  ResonatorProvider([Resonator("zlong", rs, 1.0, 1.0e9)]),
                  optics=Explicit(100.0, 100.0),
                  meta={"position": 10.0, "beta_x": 100.0, "beta_y": 100.0,
                        "info": {"length": 1.0}}))
    return m


def _config(tmp_path, name="Mini"):
    path = tmp_path / f"{name}.yaml"
    path.write_text(
        f"name: {name}\n"
        "grid:\n  frequency: {min: 1.0e8, max: 1.0e10, n: 20, log: true}\n"
        "groups:\n  cavities:\n    - name: c1\n      source: resonator\n"
        "      beta_x: 100.0\n      beta_y: 100.0\n"
        "      resonators: [{term: zlong, Rs: 1.0e4, Q: 1.0, fr: 1.0e9}]\n")
    return path


def test_scenario_reads_the_grid_from_its_project(tmp_path):
    sc = load_scenario(_config(tmp_path))
    assert sc.project is not None
    assert sc.freqs is sc.project.freqs
    assert len(sc.freqs) == 20


def test_load_project_returns_a_one_scenario_project(tmp_path):
    proj = load_project(_config(tmp_path))
    assert [s.name for s in proj.scenarios] == ["Mini"]
    # the old attributes still resolve, through the single scenario
    assert proj.machine is proj.only.machine
    assert proj.freqs is not None


def test_old_project_signature_still_works():
    f = np.linspace(1e8, 1e9, 10)
    proj = Project("Legacy", _machine(), f, None)
    assert isinstance(proj.only, Scenario)
    assert proj.machine.groups[0].name == "cavities"
    assert proj.only.freqs is f


def test_two_scenarios_share_one_grid_and_keep_their_lineage():
    f = np.linspace(1e8, 1e9, 10)
    proj = Project("LHC", freqs=f)
    inj = proj.add(Scenario("injection", _machine()))
    top = proj.add(Scenario("flat_top", _machine(rs=2.0e4), derived_from="injection"))

    assert inj.freqs is top.freqs is f
    assert top.derived_from == "injection"
    with pytest.raises(ValueError):
        proj.only                       # ambiguous: name the scenario you mean
    assert proj.scenario("flat_top") is top


def test_duplicate_scenario_name_is_refused():
    proj = Project("P", freqs=np.linspace(1e8, 1e9, 4))
    proj.add(Scenario("s1", _machine()))
    with pytest.raises(ValueError):
        proj.add(Scenario("s1", _machine()))


def test_materialize_without_a_grid_says_so():
    sc = Scenario("orphan", _machine())
    with pytest.raises(ValueError, match="grids live on the project"):
        materialize(sc, "unused")


def test_materialize_writes_lineage_into_the_resume(tmp_path):
    import yaml
    proj = Project("LHC", freqs=np.linspace(1e8, 1e9, 10))
    proj.add(Scenario("injection", _machine()))
    top = proj.add(Scenario("flat top", _machine(rs=2e4), derived_from="injection"))

    resume_path = materialize(top, tmp_path / "out")
    assert resume_path.name == "flat_top_resume.yaml"        # label slugified
    resume = yaml.safe_load(resume_path.read_text())
    assert resume["name"] == "flat top"
    assert resume["derived_from"] == "injection"


def test_a_group_with_no_elements_is_allowed(tmp_path):
    """Commenting every entry out of a group leaves `groups: {name: null}`. That
    is a model under construction, not a broken file."""
    path = tmp_path / "m.yaml"
    path.write_text(
        "name: Partial\n"
        "grid:\n  frequency: {min: 1.0e+8, max: 1.0e+9, n: 4, log: true}\n"
        "groups:\n"
        "  cavities:\n    - name: c1\n      source: resonator\n"
        "      resonators: [{term: zlong, Rs: 1.0e+4, Q: 1.0, fr: 1.0e+9}]\n"
        "  kickers:\n")
    sc = load_scenario(path)
    names = {g.name: len(g.elements) for g in sc.machine.groups}
    assert names == {"cavities": 1, "kickers": 0}
