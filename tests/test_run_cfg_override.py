"""`run(config, cfg=...)`: the contents win over the file on disk.

This is what lets the GUI compute with the beam its panel is showing. Without
it the panel and the run can disagree in silence - the file is re-read, and a
gamma typed but never saved simply does not exist.
"""
import inspect

import pytest
import yaml

from wimba import plotting as plot_mod
from wimba import run as run_mod


def _config(tmp_path, beam=None):
    cfg = {
        "name": "OVERRIDE",
        "grid": {"frequency": {"min": 1.0e6, "max": 1.0e8, "n": 5, "log": True}},
        "output": ["PIPE"],
        "devices": {"pipe": {
            "source": "chamber", "name": "PIPE", "method": "pytlwall",
            "radius_m": 0.02, "shape": "CIRCULAR", "length_m": 1.0,
            "beta_x": 1.0, "beta_y": 1.0, "weighted": False,
            "layers": [{"type": "CW", "thickness": 0.002, "sigma": 1.4e6}]}},
    }
    if beam is not None:
        cfg["beam"] = beam
    path = tmp_path / "override_config.yaml"
    path.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return path, cfg


@pytest.fixture
def gamma_seen(monkeypatch):
    """Run without computing or plotting: report the gamma that reached the
    solver. `run` imports plot_totals inside the function, so the patch has to
    land on wimba.plotting, not on a name in wimba.run."""
    seen = {}

    def _fake(rows, freqs, out_dir, per_device=(), gamma=None, times=None, **kw):
        seen["gamma"] = gamma
        seen.update(kw)                      # beta_mean, weighted
        return None, None, {"computed": 0, "skipped": 0, "geometries": 0}

    monkeypatch.setattr(run_mod, "compute_assignments", _fake)
    monkeypatch.setattr(plot_mod, "plot_totals", lambda *a, **k: [])
    return seen


def test_run_accepts_a_config_already_in_memory():
    assert "cfg" in inspect.signature(run_mod.run).parameters


def test_a_file_without_a_beam_still_computes_when_one_is_supplied(tmp_path,
                                                                   gamma_seen):
    """The failure the GUI hit: the file states no beam, the user typed one."""
    path, _ = _config(tmp_path)

    with pytest.raises(ValueError, match="at which energy"):
        run_mod.run(str(path), out_dir=str(tmp_path / "out"))

    cfg = yaml.safe_load(path.read_text())
    cfg["beam"] = {"particle": "proton", "gamma": 7000.0}
    run_mod.run(str(path), cfg=cfg, out_dir=str(tmp_path / "out"))
    assert gamma_seen["gamma"] == pytest.approx(7000.0)


def test_the_supplied_beam_wins_over_the_one_in_the_file(tmp_path, gamma_seen):
    """The dangerous case: both exist and disagree. The file must not win."""
    path, cfg = _config(tmp_path, beam={"particle": "proton", "gamma": 450.0})

    cfg = dict(cfg, beam={"particle": "proton", "gamma": 7000.0})
    run_mod.run(str(path), cfg=cfg, out_dir=str(tmp_path / "out"))
    assert gamma_seen["gamma"] == pytest.approx(7000.0)

    # and the file is not rewritten behind the user's back
    assert yaml.safe_load(path.read_text())["beam"]["gamma"] == 450.0


def test_without_an_override_the_file_is_still_what_computes(tmp_path, gamma_seen):
    path, _ = _config(tmp_path, beam={"particle": "proton", "gamma": 450.0})
    run_mod.run(str(path), out_dir=str(tmp_path / "out"))
    assert gamma_seen["gamma"] == pytest.approx(450.0)
