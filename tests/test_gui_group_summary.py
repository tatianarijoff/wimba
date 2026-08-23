"""What the Inspector can say about a group.

A group carries a name and its elements and nothing else, so everything the
panel shows for one is aggregated here. Qt-free: this exercises
`summarize_elements` directly.
"""
import pytest

from wimba.gui.model import summarize_elements


class FakeModel:
    def __init__(self, q, method, enabled=True):
        self.q, self.method, self.enabled = q, method, enabled


class FakeElement:
    def __init__(self, name, category="element", optics=None, geometry=None,
                 models=()):
        self.name, self.category = name, category
        self.optics = optics or {}
        self.geometry = geometry or {}
        self.models = list(models)


def _coll(name, s, length, bx, by, method="pytlwall"):
    return FakeElement(name, optics={"s": s, "l": length, "bx": bx, "by": by},
                       models=[FakeModel("Zlong", method),
                               FakeModel("Zdipx", method)])


def test_empty_group_says_nothing_rather_than_zero():
    s = summarize_elements([])
    assert s["n"] == 0
    assert s["span"] is None and s["length"] is None
    assert s["methods"] == {} and s["attention"] == []


def test_extent_runs_from_the_first_start_to_the_last_end():
    s = summarize_elements([_coll("A", 100.0, 1.2, 80.0, 40.0),
                            _coll("B", 300.0, 0.8, 12.0, 30.0)])
    assert s["span"] == (100.0, 300.8)
    assert s["length"] == pytest.approx(2.0)


def test_length_falls_back_to_the_geometry():
    el = FakeElement("CH", optics={"s": 5.0}, geometry={"length": 3.0},
                     models=[FakeModel("Zlong", "pytlwall")])
    assert summarize_elements([el])["length"] == pytest.approx(3.0)


def test_composition_counts_elements_not_models():
    """Two quantities on one element is one pytlwall element, not two."""
    s = summarize_elements([_coll("A", 1.0, 1.0, 10.0, 10.0),
                            _coll("B", 2.0, 1.0, 10.0, 10.0, "resonator")])
    assert s["methods"] == {"pytlwall": 1, "resonator": 1}


def test_the_default_pipe_is_counted_apart_and_never_averaged_in():
    pipe = FakeElement("default resistive wall", category="default_pipe")
    s = summarize_elements([_coll("A", 100.0, 1.0, 10.0, 20.0), pipe])
    assert s["n"] == 2 and s["n_pipe"] == 1
    assert s["span"] == (100.0, 101.0)          # the pipe contributed nothing
    assert s["beta_of"] == 1
    assert s["attention"] == []                 # and raised no false alarm


def test_a_weighted_source_is_not_missing_a_beta():
    """It has no single position by construction; that is what weighted means."""
    bpm = FakeElement("BPM", optics={"bx": 1.0, "by": 1.0},
                      models=[FakeModel("Zlong", "precalculated (weighted)")])
    s = summarize_elements([bpm])
    assert s["beta_of"] == 0
    assert s["attention"] == []


def test_beta_coverage_and_range():
    s = summarize_elements([_coll("A", 1.0, 1.0, 88.0, 42.0),
                            _coll("B", 2.0, 1.0, 12.0, 30.0),
                            FakeElement("NOOPT", optics={"s": 3.0, "l": 1.0},
                                        models=[FakeModel("Zlong", "pytlwall")])])
    assert (s["beta_have"], s["beta_of"]) == (2, 3)
    assert s["beta_range"] == (12.0, 88.0)


def test_mixed_is_flagged_when_the_elements_disagree():
    same = summarize_elements([_coll("A", 1.0, 1.0, 10.0, 10.0),
                               _coll("B", 2.0, 1.0, 10.0, 10.0)])
    assert same["quantities"] == ["Zdipx", "Zlong"] and not same["mixed"]

    odd = FakeElement("C", optics={"s": 3.0, "l": 1.0, "bx": 1e1, "by": 1e1},
                      models=[FakeModel("Zlong", "pytlwall")])
    mixed = summarize_elements([_coll("A", 1.0, 1.0, 10.0, 10.0), odd])
    assert mixed["mixed"]


def test_attention_catches_the_three_quiet_failures():
    nothing_on = FakeElement("ORPHAN", optics={"s": 1.0, "l": 1.0},
                             models=[FakeModel("Zlong", "pytlwall", enabled=False)])
    fallback = _coll("RF", 2.0, 1.0, 1.0, 1.0)
    zero_len = _coll("FLANGE", 3.0, 0.0, 10.0, 10.0)
    reasons = dict(summarize_elements([nothing_on, fallback, zero_len])["attention"])
    assert "no quantity" in reasons["ORPHAN"]
    assert "fallback" in reasons["RF"]
    assert "zero length" in reasons["FLANGE"]
