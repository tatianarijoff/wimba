"""The grid belongs to the project, and now the code agrees with the docs.

`project.yaml` states one grid for every scenario -- that is what makes two
scenarios comparable -- but each scenario config also carries a `grid:`, because
it is a config in its own right and `wimba run` on it has nothing else to go on.
Inside a project that copy used to be the one that computed, silently, so
editing project.yaml changed nothing and the Scenarios panel could state a span
the calculation never used.
"""
import pytest

from wimba.gui.model import grid_conflict, grid_of, grid_span

PROJECT = {"frequency": {"min": 10000.0, "max": 6.0e8, "n": 200, "log": True},
           "time": {"min": 0.0, "max": 5.0e-8, "n": 200}}


def _cfg(**freq):
    grid = {"frequency": dict(PROJECT["frequency"], **freq),
            "time": dict(PROJECT["time"])}
    return {"name": "scenario", "grid": grid}


def test_agreement_says_nothing():
    assert grid_conflict(PROJECT, _cfg()) is None


def test_a_different_maximum_is_reported_both_ways_round():
    message = grid_conflict(PROJECT, _cfg(max=1.0e10), "injection_config.yaml")
    assert "project.yaml says" in message and "6e+08" in message
    assert "injection_config.yaml says" in message and "1e+10" in message
    assert "the project's grid wins" in message
    assert "unchanged" in message              # the file is not rewritten


def test_a_different_point_count_counts_too():
    assert "points" in grid_conflict(PROJECT, _cfg(n=400))


def test_linear_against_log_is_a_conflict():
    message = grid_conflict(PROJECT, _cfg(log=False))
    assert "linear" in message and "log" in message


def test_a_time_grid_conflict_is_named_as_such():
    cfg = _cfg()
    cfg["grid"]["time"] = {"min": 0.0, "max": 1.0e-7, "n": 200}
    message = grid_conflict(PROJECT, cfg)
    assert message.startswith("the project's grid wins")
    assert "time:" in message
    assert "frequency" not in message          # only what actually differs


def test_both_grids_differing_are_both_named():
    cfg = _cfg(max=1.0e10)
    cfg["grid"]["time"] = {"min": 0.0, "max": 1.0e-7, "n": 200}
    message = grid_conflict(PROJECT, cfg)
    assert "frequency:" in message and "time:" in message


def test_a_config_with_no_grid_inherits_in_silence():
    # nothing to disagree with: the project's grid simply applies
    assert grid_conflict(PROJECT, {"name": "scenario"}) is None


def test_no_project_grid_means_no_opinion():
    # a project that has not stated one lets the config's grid stand
    assert grid_conflict({}, _cfg(max=1.0e10)) is None
    assert grid_conflict(None, _cfg(max=1.0e10)) is None


def test_yaml_1_1_exponents_are_not_a_conflict():
    """`6e8` is a string to PyYAML and `6.0e+8` is a float; the same number
    written two ways must not read as two different grids."""
    assert grid_conflict(PROJECT, _cfg(max="6e8")) is None


def test_the_span_reads_like_a_sentence():
    assert grid_span(grid_of({"grid": PROJECT})) == "10000 .. 6e+08 Hz, 200 points, log"
    assert grid_span({}) == ""


def test_freq_is_accepted_as_a_spelling_of_frequency():
    cfg = {"grid": {"freq": dict(PROJECT["frequency"])}}
    assert grid_conflict(PROJECT, cfg) is None


# --------------------------------------------------------------- the build path
qt = pytest.importorskip("PyQt6")


def test_the_build_worker_replaces_the_grid_it_was_given(tmp_path):
    from wimba.builders import load_scenario
    from wimba.gui.runner import BuildWorker

    cfg = tmp_path / "machine.yaml"
    cfg.write_text(
        "name: M\n"
        "grid:\n"
        "  frequency: {min: 10000.0, max: 10000000000.0, n: 200, log: true}\n"
        "beam: {particle: proton, gamma: 7461}\n"
        "groups:\n"
        "  cav:\n"
        "  - name: CAV.1\n"
        "    source: resonator\n"
        "    beta_x: 1.0\n"
        "    beta_y: 1.0\n"
        "    resonators:\n"
        "    - {term: zlong, Rs: 1000.0, Q: 10.0, fr: 100000000.0}\n")

    scenario = load_scenario(str(cfg))
    assert scenario.freqs.max() == 1.0e10          # what the file asks for

    worker = BuildWorker(cfg, grid={"frequency": {"min": 10000.0, "max": 6.0e8,
                                                  "n": 200, "log": True}})
    said = []
    worker.log.connect(said.append)
    worker._apply_grid(scenario)

    # logspace lands on the endpoint to rounding, not to the bit
    assert scenario.freqs.max() == pytest.approx(6.0e8)   # what the project asks for
    assert len(scenario.freqs) == 200
    assert any("project.yaml" in line for line in said)


def test_the_build_worker_says_nothing_when_the_grids_agree(tmp_path):
    from wimba.builders import load_scenario
    from wimba.gui.runner import BuildWorker

    cfg = tmp_path / "machine.yaml"
    cfg.write_text(
        "name: M\n"
        "grid:\n"
        "  frequency: {min: 10000.0, max: 600000000.0, n: 200, log: true}\n"
        "beam: {particle: proton, gamma: 7461}\n"
        "groups: {}\n")
    scenario = load_scenario(str(cfg))
    worker = BuildWorker(cfg, grid={"frequency": {"min": 10000.0, "max": 6.0e8,
                                                  "n": 200, "log": True}})
    said = []
    worker.log.connect(said.append)
    worker._apply_grid(scenario)
    assert said == []


def test_the_run_worker_announces_the_project_grid(tmp_path):
    from wimba.gui.runner import RunWorker

    cfg_file = tmp_path / "assembly.yaml"
    cfg_file.write_text("name: A\n")
    project_grid = {"frequency": {"min": 10000.0, "max": 6.0e8, "n": 200,
                                  "log": True}}
    worker = RunWorker(cfg_file, overrides={"grid": project_grid})
    said = []
    worker.log.connect(said.append)

    out = worker._apply_overrides(
        {"grid": {"frequency": {"min": 10000.0, "max": 1.0e10, "n": 200,
                                "log": True}}})

    assert out["grid"] == project_grid
    # the same shape as the beam mismatch above it: a WARNING naming both spans,
    # not a neutral sentence that reads like progress
    assert any(line.startswith("  WARNING:") for line in said)
    assert any("6e+08" in line and "1e+10" in line for line in said)


def test_the_note_lands_in_problems_not_only_in_the_console():
    """The Console is not raised when a project is opened and the bottom docks
    are tabbed, so a warning written only there is a warning nobody reads.
    Problems is the panel for things WIMBA wants the user to notice.

    Exercised on the method itself rather than on a built window: constructing
    the whole MainWindow inside the suite is not what is under test here.
    """
    from wimba.gui.app import MainWindow

    class Dock:
        def __init__(self): self.raised = False
        def raise_(self): self.raised = True

    class Text:
        def __init__(self): self.lines = []
        def appendPlainText(self, line): self.lines.append(line)

    class Log:
        def __init__(self): self.warnings = []
        def warning(self, fmt, *a): self.warnings.append(fmt % a)

    class Fake:
        def __init__(self, project_grid):
            self.project = type("P", (), {"grid": project_grid})()
            self.log = Log()
            self.problems = Text()
            self.docks = {"problems": Dock()}
        def _dock_text(self, name): return self.problems

    cfg = {"grid": {"frequency": {"min": 10000.0, "max": 1.0e10, "n": 200,
                                  "log": True}}}
    me = Fake(PROJECT)
    grid = MainWindow._project_grid(me, "injection_config.yaml", cfg)

    assert grid["frequency"]["max"] == 6.0e8          # the project's, coerced
    assert me.log.warnings and "6e+08" in me.log.warnings[0]
    assert me.problems.lines and "grid" in me.problems.lines[0]
    assert me.docks["problems"].raised

    # and nothing is said, or raised, when the two agree
    quiet = Fake(PROJECT)
    MainWindow._project_grid(quiet, "injection_config.yaml",
                             {"grid": PROJECT})
    assert quiet.log.warnings == [] and quiet.problems.lines == []
    assert not quiet.docks["problems"].raised


def test_the_calculate_paths_do_not_steal_the_problems_tab():
    """They report through their worker's Console line instead: _on_calc_done
    clears Problems, and raising it mid-run would fight the Console."""
    import inspect
    from wimba.gui.app import MainWindow
    for name in ("_calc_machine", "_build_machine"):
        src = inspect.getsource(getattr(MainWindow, name))
        assert "_project_grid(" in src
        assert "announce=False" in src
