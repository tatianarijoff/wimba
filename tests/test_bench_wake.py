"""A wake computed on the Component bench has to reach the Results tree.

It did not, for any element whose name had a space in it: the run writes its
files under names passed through naming.safe, so "My Component" came back as
"My_Component", adopt_total_wake looked for the name as typed, found nothing,
and dropped 'Total' - with the wake in it - regardless.
"""
import numpy as np
import pytest

# ResultsModel is Qt-free, but the module it lives in is not (see the note in
# gui/results.py); run.py and naming need nothing of the kind.
pytest.importorskip("PyQt6.QtWidgets")

from wimba.gui.results import ResultsModel  # noqa: E402
from wimba.naming import safe  # noqa: E402

T = np.linspace(1e-12, 5e-9, 5)
WAKE = (T, {"WLong": np.arange(5.0)})
IMP = (np.array([1e6, 1e7]), {"ZLong": np.array([1 + 1j, 2 + 2j])})


def _model(element_name, group="single"):
    m = ResultsModel()
    m.sources = {"Total": {"impedance": IMP, "wake": WAKE},
                 f"{group}/{safe(element_name)}": {"impedance": IMP}}
    return m


def test_a_name_with_a_space_still_receives_its_wake():
    m = _model("My Component")
    m.adopt_total_wake("My Component")
    key = f"single/{safe('My Component')}"
    assert "wake" in m.sources[key]
    assert "Total" not in m.sources


def test_a_bench_label_with_the_engine_in_brackets_matches_too():
    label = "My Component[pytlwall]"
    m = _model(label, group="bench")
    m.adopt_total_wake(label)
    assert "wake" in m.sources[f"bench/{safe(label)}"]


def test_an_unmatched_wake_is_kept_rather_than_thrown_away():
    """Losing a computed result without a word is worse than showing it under
    the less precise name."""
    m = _model("Something Else")
    m.adopt_total_wake("My Component")
    assert "wake" in m.sources["Total"]


def test_a_total_with_no_wake_is_still_dropped():
    m = ResultsModel()
    m.sources = {"Total": {"impedance": IMP},
                 "single/My_Component": {"impedance": IMP}}
    m.adopt_total_wake("My Component")
    assert "Total" not in m.sources


# ----------------------------------------------------------- the time grid ---
# run() sampled every wake on a fixed 500-point grid whatever the config said,
# while the GUI announced the config's grid as the one in use.

def test_the_config_time_grid_is_the_one_used():
    from wimba.run import _time_grid

    t = _time_grid({"grid": {"time": {"min": 2e-12, "max": 1e-9, "n": 37}}})
    assert len(t) == 37
    assert t[0] == pytest.approx(2e-12) and t[-1] == pytest.approx(1e-9)


def test_without_one_the_default_is_the_one_the_gui_announces():
    from wimba.run import DEFAULT_TIME_GRID, _time_grid

    t = _time_grid({"grid": {"frequency": {"min": 1e5, "max": 1e10, "n": 100}}})
    assert len(t) == DEFAULT_TIME_GRID["n"] == 200
