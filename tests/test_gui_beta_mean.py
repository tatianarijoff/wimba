"""The interface's side of the beta / beta_mean weighting.

Qt-free: this exercises the view-model, not the widgets -- which average a
machine would compute with, and that stating one is written back into the config
only when it changes.
"""
import pytest

from wimba.gui.model import METHODS, GMachine, patch_config


def test_only_imported_data_can_be_offered_as_already_weighted():
    """Offering "pytlwall (weighted)" would offer to weight it twice."""
    weighted = [m for m in METHODS if "(weighted)" in m]
    assert weighted == ["precalculated (weighted)"]


def test_a_fresh_machine_weighs_by_nothing():
    gm = GMachine(name="M")
    assert gm.mean_in_use() == ((1.0, 1.0), "none")


def test_what_wimba_computed_is_used_when_the_user_states_nothing():
    gm = GMachine(name="M")
    gm.beta_mean, gm.beta_mean_source = (40.0, 28.0), "lattice"
    assert gm.mean_in_use() == ((40.0, 28.0), "lattice")


def test_a_stated_average_wins():
    """It was written on purpose; the computed one only estimates it."""
    gm = GMachine(name="M")
    gm.beta_mean, gm.beta_mean_source = (40.0, 28.0), "lattice"
    gm.smooth_beta = (33.0, 21.0)
    assert gm.mean_in_use() == ((33.0, 21.0), "smooth_beta")


def test_clearing_it_hands_the_machine_back_to_its_own_average():
    gm = GMachine(name="M")
    gm.beta_mean, gm.beta_mean_source = (40.0, 28.0), "elements"
    gm.smooth_beta = (33.0, 21.0)
    gm.smooth_beta = None
    assert gm.mean_in_use() == ((40.0, 28.0), "elements")


# ---------------------------------------------------------------- writing back
def _machine(**kw):
    gm = GMachine(name="M", **kw)
    return gm


def test_a_stated_average_is_written_into_the_config():
    out = patch_config({"groups": {}}, _machine(smooth_beta=(33.0, 21.0)))
    assert out["smooth_beta"] == {"x": 33.0, "y": 21.0}


def test_an_unchanged_average_is_not_rewritten():
    """Same rule as the beam: the file keeps its own spelling.

    YAML 1.1 hands `3.3e1` back as a string; it is still the same number, so
    there is nothing to write.
    """
    cfg = {"smooth_beta": {"x": "3.3e1", "y": 21.0}, "groups": {}}
    out = patch_config(cfg, _machine(smooth_beta=(33.0, 21.0)))
    assert out["smooth_beta"]["x"] == "3.3e1"


def test_clearing_it_removes_the_key_rather_than_writing_a_one():
    cfg = {"smooth_beta": {"x": 33.0, "y": 21.0}, "groups": {}}
    out = patch_config(cfg, _machine(smooth_beta=None))
    assert "smooth_beta" not in out
    assert "smooth_beta" in cfg          # and the caller's own dict is untouched


def test_a_machine_that_never_had_one_gains_nothing():
    assert "smooth_beta" not in patch_config({"groups": {}}, _machine())
