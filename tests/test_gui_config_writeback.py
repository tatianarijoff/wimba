"""What the GUI is allowed to write into a user's config.

Two rules, both learned the hard way from a repository that kept coming up
dirty after the window had merely been opened:

* the beam is written as the user stated it -- particle, mode, and that one
  value -- never as the full set of quantities derived from it;
* a config that already says the right thing is not rewritten at all, so its
  own spelling of a number survives.

Qt-free: everything here is `patch_config` and its helpers.
"""
from types import SimpleNamespace

import pytest

from wimba.gui.model import _same_beam, beam_out, patch_config


class FakeBeam:
    """Stands in for core.Beam: to_dict() carries the derived quantities too."""

    def __init__(self, **full):
        self._full = full

    def to_dict(self):
        return dict(self._full)

    def label(self):
        return str(self._full)


def _machine(beam):
    return SimpleNamespace(beam=beam, all_elements=lambda: [])


def test_beam_out_keeps_only_what_was_stated():
    beam = FakeBeam(particle="positron", mode="energy", energy=8e10,
                    gamma=156556.09468473468, beta=0.9999999999796)
    assert beam_out(beam) == {"particle": "positron", "mode": "energy",
                              "energy": 8e10}


def test_beam_out_follows_the_mode():
    beam = FakeBeam(particle="proton", mode="gamma", gamma=7000.0,
                    energy=6.5e12, beta=0.999999989)
    assert beam_out(beam) == {"particle": "proton", "mode": "gamma",
                              "gamma": 7000.0}


def test_beam_out_drops_private_keys():
    beam = FakeBeam(particle="proton", mode="gamma", gamma=7000.0,
                    _cached="an object that must never reach YAML")
    assert "_cached" not in beam_out(beam)


def test_beam_out_passes_an_unknown_mode_through():
    beam = FakeBeam(particle="proton", mode="rigidity", rigidity=12.0)
    assert beam_out(beam)["rigidity"] == 12.0


@pytest.mark.parametrize("stated", ["8e+10", "8.0e10", 80000000000.0])
def test_same_beam_ignores_the_spelling_of_a_number(stated):
    """YAML 1.1 hands `8e+10` back as a string; it is still the same energy."""
    existing = {"particle": "positron", "mode": "energy", "energy": stated}
    assert _same_beam(existing, {"particle": "positron", "mode": "energy",
                                 "energy": 8e10})


def test_same_beam_allows_extra_keys_the_author_wrote():
    existing = {"particle": "positron", "mode": "energy", "energy": 8e10,
                "gamma": 156556.094684735}
    assert _same_beam(existing, {"particle": "positron", "mode": "energy",
                                 "energy": 8e10})


def test_same_beam_sees_a_real_change():
    existing = {"particle": "positron", "mode": "energy", "energy": 8e10}
    assert not _same_beam(existing, {"particle": "positron", "mode": "energy",
                                     "energy": 4.56e10})
    assert not _same_beam(existing, {"particle": "proton", "mode": "energy",
                                     "energy": 8e10})


def test_unchanged_beam_leaves_the_block_untouched():
    """The whole point: opening a project must not rewrite its config."""
    cfg = {"beam": {"particle": "positron", "mode": "energy",
                    "energy": "8e+10", "gamma": 156556.094684735},
           "groups": {}}
    beam = FakeBeam(particle="positron", mode="energy", energy=8e10,
                    gamma=156556.09468473468, beta=0.9999999999796)
    out = patch_config(cfg, _machine(beam))
    assert out["beam"] == cfg["beam"]          # spelling and extra key survive
    assert "beta" not in out["beam"]


def test_a_changed_beam_is_written_without_the_derived_quantities():
    cfg = {"beam": {"particle": "positron", "mode": "energy", "energy": "8e+10"},
           "groups": {}}
    beam = FakeBeam(particle="positron", mode="energy", energy=4.56e10,
                    gamma=89237.0, beta=0.99999999993)
    out = patch_config(cfg, _machine(beam))
    assert out["beam"] == {"particle": "positron", "mode": "energy",
                           "energy": 4.56e10}


def test_a_legacy_top_level_gamma_still_goes_when_the_beam_is_written():
    cfg = {"gamma": 7000.0, "groups": {}}
    beam = FakeBeam(particle="proton", mode="gamma", gamma=6800.0)
    out = patch_config(cfg, _machine(beam))
    assert "gamma" not in out
    assert out["beam"]["gamma"] == 6800.0
