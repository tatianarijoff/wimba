"""A machine file with no `grid:` computes on WIMBA's default, and says so."""
from pathlib import Path

import numpy as np
import yaml

from wimba.builders import load_scenario
from wimba.grids import DEFAULT_GRID, default_grid, describe
from wimba.store import materialize

MACHINE = {
    "name": "MyRing",
    "beam": {"particle": "proton", "gamma": 100.0},
    "groups": {"cavities": [
        {"name": "CAV", "source": "resonator", "length": 1.0,
         "beta_x": 1.0, "beta_y": 1.0,
         "resonators": [{"term": "zlong", "Rs": 1.0e4, "Q": 1.0, "fr": 1.0e9}]}]},
}


def _write(tmp_path, data):
    p = Path(tmp_path) / "my_ring.yaml"
    p.write_text(yaml.safe_dump(data))
    return p


def test_no_grid_uses_the_default(tmp_path):
    sc = load_scenario(_write(tmp_path, MACHINE))
    f = DEFAULT_GRID["frequency"]
    assert sc.project.grid_default is True
    assert len(sc.freqs) == f["n"]
    assert np.isclose(sc.freqs[0], f["min"]) and np.isclose(sc.freqs[-1], f["max"])
    assert len(sc.times) == DEFAULT_GRID["time"]["n"]


def test_no_grid_computes_and_the_resume_says_default(tmp_path):
    sc = load_scenario(_write(tmp_path, MACHINE))
    resume = materialize(sc, tmp_path / "out")
    data = yaml.safe_load(Path(resume).read_text())
    assert data["grid_source"] == "default"
    assert data["grid"]["frequency"]["n"] == DEFAULT_GRID["frequency"]["n"]


def test_a_stated_grid_is_kept_and_not_flagged(tmp_path):
    data = dict(MACHINE, grid={"frequency": {"min": 1e8, "max": 3e9, "n": 50, "log": True}})
    sc = load_scenario(_write(tmp_path, data))
    assert sc.project.grid_default is False
    assert len(sc.freqs) == 50
    # only a frequency grid stated: no wake asked for, and no default slipped in
    assert sc.times is None
    resume = yaml.safe_load(Path(materialize(sc, tmp_path / "out")).read_text())
    assert "grid_source" not in resume


def test_default_is_a_copy_and_the_gui_shares_it():
    g = default_grid()
    g["frequency"]["n"] = 1
    assert DEFAULT_GRID["frequency"]["n"] != 1
    from wimba.gui.model import DEFAULT_MACHINE_GRID
    assert DEFAULT_MACHINE_GRID is DEFAULT_GRID


def test_describe_names_both_grids():
    text = describe(DEFAULT_GRID)
    assert "Hz" in text and "log" in text and " s " in text
