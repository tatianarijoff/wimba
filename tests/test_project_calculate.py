"""Calculate Project: which scenarios need computing, and the scenario ceiling.

Qt-free: the queue in app.py only walks the list these functions return.
"""
import os
import time

import pytest

from wimba.core.beam import Beam
from wimba.gui.model import (MAX_SCENARIOS, GProject, GScenario,
                             scenario_fingerprint, scenario_is_stale,
                             stale_scenarios)


def _project(tmp_path, n=2):
    p = GProject("study", str(tmp_path), grid={"frequency": {"min": 1e5, "max": 6e8}})
    for i in range(n):
        label = f"case {i}"
        sc = GScenario(label, f"case_{i}_config.yaml",
                       beam=Beam("proton", "gamma", 2.27895))
        (tmp_path / sc.config).write_text(f"name: case{i}\n")
        p.add(sc)
    return p


def _computed(p, sc):
    """Mark a scenario as the done-handlers do after a successful run."""
    out = __import__("pathlib").Path(p.dir) / sc.slug / "output"
    out.mkdir(parents=True, exist_ok=True)
    (out / "total.csv").write_text("f,ZLong\n")
    sc.computed_at = "2026-09-27T12:00:00"
    sc.computed_hash = scenario_fingerprint(p, sc)


def test_never_computed_is_stale(tmp_path):
    p = _project(tmp_path)
    assert [s.label for s in stale_scenarios(p)] == ["case 0", "case 1"]


def test_computed_and_untouched_is_up_to_date(tmp_path):
    p = _project(tmp_path)
    _computed(p, p.scenarios[0])
    assert [s.label for s in stale_scenarios(p)] == ["case 1"]


def test_editing_the_config_makes_it_stale(tmp_path):
    p = _project(tmp_path)
    sc = p.scenarios[0]
    _computed(p, sc)
    (tmp_path / sc.config).write_text("name: case0\n# thicker coating\n")
    assert scenario_is_stale(p, sc)


def test_changing_the_project_grid_makes_every_scenario_stale(tmp_path):
    p = _project(tmp_path)
    for sc in p.scenarios:
        _computed(p, sc)
    assert stale_scenarios(p) == []
    p.grid = {"frequency": {"min": 1e5, "max": 1e9}}
    assert len(stale_scenarios(p)) == 2


def test_changing_the_beam_makes_it_stale(tmp_path):
    p = _project(tmp_path)
    sc = p.scenarios[1]
    _computed(p, sc)
    sc.beam = Beam("proton", "gamma", 21.3392)
    assert scenario_is_stale(p, sc)


def test_results_deleted_from_disk_make_it_stale(tmp_path):
    p = _project(tmp_path)
    sc = p.scenarios[0]
    _computed(p, sc)
    (tmp_path / sc.slug / "output" / "total.csv").unlink()
    assert scenario_is_stale(p, sc)


def test_an_old_project_without_fingerprint_falls_back_to_the_file_date(tmp_path):
    p = _project(tmp_path, n=1)
    sc = p.scenarios[0]
    _computed(p, sc)
    sc.computed_hash = None
    cfg = tmp_path / sc.config
    old = time.mktime(time.strptime("2026-09-27 11:00:00", "%Y-%m-%d %H:%M:%S"))
    os.utime(cfg, (old, old))
    assert not scenario_is_stale(p, sc)            # file older than the result
    new = time.mktime(time.strptime("2026-09-27 13:00:00", "%Y-%m-%d %H:%M:%S"))
    os.utime(cfg, (new, new))
    assert scenario_is_stale(p, sc)                # edited after it


def test_the_fingerprint_round_trips_through_project_yaml(tmp_path):
    p = _project(tmp_path, n=1)
    _computed(p, p.scenarios[0])
    again = GProject.from_dict(p.to_dict(), tmp_path)
    assert again.scenarios[0].computed_hash == p.scenarios[0].computed_hash
    assert stale_scenarios(again) == []


def test_a_project_holds_at_most_the_ceiling(tmp_path):
    p = _project(tmp_path, n=MAX_SCENARIOS)
    assert not p.can_add()
    with pytest.raises(ValueError, match="at most"):
        p.add(GScenario("one too many", "x_config.yaml"))
    assert len(p.scenarios) == MAX_SCENARIOS


# ------------------------------------------------------------- in the GUI
def _mini_project(tmp_path):
    """Two resonator-only scenarios (no engine needed) in a project folder."""
    import yaml
    grid = {"frequency": {"min": 1.0e8, "max": 1.0e10, "n": 20, "log": True}}
    scenarios = []
    for label, rs in (("low", 1.0e4), ("high", 3.0e4)):
        cfg = (f"name: Mini\n"
               "grid:\n  frequency: {min: 1.0e+8, max: 1.0e+10, n: 20, log: true}\n"
               "groups:\n  cavities:\n    - name: c1\n      source: resonator\n"
               "      beta_x: 100.0\n      beta_y: 100.0\n"
               f"      resonators: [{{term: zlong, Rs: {rs}, Q: 1.0, fr: 1.0e+9}}]\n")
        (tmp_path / f"{label}_config.yaml").write_text(cfg)
        (tmp_path / label / "output").mkdir(parents=True)
        scenarios.append({"label": label, "slug": label, "config": f"{label}_config.yaml",
                          "beam": {"particle": "proton", "mode": "gamma", "gamma": 10.0}})
    scenarios[1]["derived_from"] = "low"
    (tmp_path / "project.yaml").write_text(
        yaml.safe_dump({"name": "mini", "grid": grid, "scenarios": scenarios}))
    return tmp_path


_RUN = """
import time
w._open_project_at(__import__('pathlib').Path({d!r}))
w._ask = lambda *a, **k: {answer!r}
w._calc_project()
t = time.time()
while w._project_run is not None and time.time() - t < 60:
    app.processEvents(); time.sleep(0.02)
for _ in range(20):
    app.processEvents(); time.sleep(0.01)
print('RUNNING', w._project_run is not None)
print('COMPUTED', [bool(s.computed_hash) for s in w.project.scenarios])
print('CURRENT', w.project.scenario.label)
print('LOADED', sorted(w.results_model.scenarios()))
"""


def _gui(code, cwd):
    pytest.importorskip("PyQt6")
    import subprocess
    import sys
    head = ("import os; os.environ['QT_QPA_PLATFORM']='offscreen'\n"
            "from PyQt6.QtWidgets import QApplication\n"
            "import wimba.gui.app as A\n"
            "app = QApplication([])\n"
            "w = A.MainWindow()\n")
    out = subprocess.run([sys.executable, "-c", head + code], capture_output=True,
                         text=True, timeout=120, cwd=cwd)
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_calculate_project_runs_every_scenario_and_returns(tmp_path):
    d = _mini_project(tmp_path)
    out = _gui(_RUN.format(d=str(d), answer="go"), d)
    assert "RUNNING False" in out
    assert "COMPUTED [True, True]" in out
    assert "LOADED ['high', 'low']" in out
    assert "CURRENT low" in out           # back on the scenario it started from


def test_a_second_calculate_project_finds_nothing_to_do(tmp_path):
    d = _mini_project(tmp_path)
    _gui(_RUN.format(d=str(d), answer="go"), d)
    import yaml
    saved = yaml.safe_load((d / "project.yaml").read_text())
    assert all(s.get("computed_hash") for s in saved["scenarios"])
    # up to date: the dialog offers Recompute All / Cancel, and Cancel does nothing
    out = _gui(_RUN.format(d=str(d), answer="cancel"), d)
    assert "RUNNING False" in out
