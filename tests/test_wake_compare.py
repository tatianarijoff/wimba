"""Wake comparisons in the Additional calculations table.

The run pipeline already read `wake_files` and a map's `wake_components`; what
was missing was the table being able to say so. The trap it opens is that a
wake comparison produces an empty column unless the calculation runs with a
time grid, so asking for one has to imply asking for the wake.
"""
import pytest

from wimba.gui.model import (ALL_IMPEDANCE, ALL_WAKE, GElement, GModel,
                             element_to_config, is_wake_component, wants_wake)


def _element(*compare):
    return GElement(
        name="C", category="component",
        geometry={"radius": 0.002, "shape": "CIRCULAR", "length": 1.0},
        optics={"l": 1.0, "bx": 1.0, "by": 1.0},
        layers=[{"type": "CW", "thickness": "inf", "sigma": 2.0e5}],
        models=[GModel(q="zlong", enabled=True, method="pytlwall")],
        own_base={"gamma": 479.605064966},
        compare=list(compare))


def test_wake_components_are_recognised():
    for q in ("WLong", "WDipX", "WDipY", "WQuadX", "WQuadY", ALL_WAKE):
        assert is_wake_component(q), q
    for q in ("ZLong", "ZQuadY", ALL_IMPEDANCE, None):
        assert not is_wake_component(q), q


def test_a_wake_file_goes_to_wake_files_not_files(tmp_path):
    """Put in `files` it would be interpolated onto the frequency grid as if it
    were an impedance - a plausible curve of the wrong quantity."""
    data = tmp_path / "w.dat"
    data.write_text("0.0 1.0\n1e-12 2.0\n")
    el = _element(GModel(q="WLong", enabled=True, method="precalculated",
                         file=str(data)))
    spec = element_to_config(el)["devices"]["compare_0"]
    assert "wake_files" in spec and "files" not in spec
    assert spec["wake_files"] == {"WLong": str(data)}


def test_an_impedance_file_still_goes_to_files(tmp_path):
    data = tmp_path / "z.dat"
    data.write_text("1e3 1.0 2.0\n")
    el = _element(GModel(q="ZLong", enabled=True, method="precalculated",
                         file=str(data)))
    spec = element_to_config(el)["devices"]["compare_0"]
    assert "files" in spec and "wake_files" not in spec


def test_a_map_is_a_map_either_way(tmp_path):
    """A descriptor names its own components, wake ones included, so it does
    not need sorting into one key or the other."""
    m = tmp_path / "m.yaml"
    m.write_text("components: {}\n")
    el = _element(GModel(q="WDipY", enabled=True, method="precalculated",
                         file=str(m)))
    spec = element_to_config(el)["devices"]["compare_0"]
    assert spec["map"] == str(m)


def test_all_wake_is_refused_for_a_single_file(tmp_path):
    """One file holds one component, whichever half of the list it is in."""
    data = tmp_path / "w.dat"
    data.write_text("0.0 1.0\n")
    el = _element(GModel(q=ALL_WAKE, enabled=True, method="precalculated",
                         file=str(data)))
    with pytest.raises(ValueError, match="one component"):
        element_to_config(el)


def test_all_wake_on_a_chamber_method_computes_everything():
    el = _element(GModel(q=ALL_WAKE, enabled=True, method="IW2D"))
    cfg = element_to_config(el)
    spec = cfg["devices"]["compare_0"]
    assert spec["method"] == "iw2d"
    # named without a component suffix, like All impedance
    assert spec["name"] == "C[IW2D]"


def test_an_element_with_a_wake_comparison_asks_for_the_wake():
    assert wants_wake(_element(GModel(q="WLong", enabled=True,
                                      method="pytlwall")))
    assert not wants_wake(_element(GModel(q="ZLong", enabled=True,
                                          method="pytlwall")))
    assert not wants_wake(_element())


def test_the_emitted_config_always_carries_a_time_grid():
    """So the wake comparison has somewhere to land."""
    cfg = element_to_config(_element(GModel(q="WLong", enabled=True,
                                            method="pytlwall")))
    assert cfg["grid"]["time"]["n"] > 0


def test_two_identical_rows_do_not_collide():
    """Two rows asking for the same method and component produced two devices
    with one name: the second overwrote the first in the results, and the
    output list carried the name twice."""
    el = _element(GModel(q=ALL_IMPEDANCE, enabled=True, method="pytlwall"),
                  GModel(q=ALL_IMPEDANCE, enabled=True, method="pytlwall"))
    cfg = element_to_config(el)
    names = [d["name"] for d in cfg["devices"].values()]
    assert len(names) == len(set(names)), names
    assert cfg["output"] == sorted(set(cfg["output"]), key=cfg["output"].index)


def test_the_yokoya_factors_do_not_leak_into_a_pytlwall_comparison():
    """The compare spec is built from the base one, which dragged an IW2D-only
    key into a pytlwall device."""
    el = _element(GModel(q=ALL_IMPEDANCE, enabled=True, method="pytlwall"))
    el.geometry["iw2d_yokoya"] = [1.0, 0.411, 0.822, -0.411, 0.411]
    cfg = element_to_config(el)
    assert "iw2d_yokoya" not in cfg["devices"]["compare_0"]
    # and it is still there for the element itself, which is IW2D-capable
    assert "iw2d_yokoya" in cfg["devices"]["single"]


def test_a_precalculated_comparison_carries_the_element_s_betas(tmp_path):
    """Without them the assembler cannot locate it and warns about a device the
    user never placed, falling back to beta = 1."""
    data = tmp_path / "z.dat"
    data.write_text("1e3 1.0 2.0\n")
    el = _element(GModel(q="ZLong", enabled=True, method="precalculated",
                         file=str(data)))
    el.optics.update({"bx": 65.0, "by": 71.5})
    spec = element_to_config(el)["devices"]["compare_0"]
    assert spec["beta_x"] == 65.0 and spec["beta_y"] == 71.5


def test_weighted_data_is_left_alone(tmp_path):
    """Already beta-weighted data must not be weighted a second time."""
    data = tmp_path / "z.dat"
    data.write_text("1e3 1.0 2.0\n")
    el = _element(GModel(q="ZLong", enabled=True,
                         method="precalculated (weighted)", file=str(data)))
    spec = element_to_config(el)["devices"]["compare_0"]
    assert spec["weighted"] is True
    assert "beta_x" not in spec
