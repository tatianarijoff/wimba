"""A resonator built by hand: the modes, the config it emits, and the refusals.

The Component bench used to offer `resonator` in its method list with nowhere
to put Rs, Q and f_r, so the choice could only end in "not supported" at save
time. These tests pin the path that replaced it: modes are validated the same
way whether they were typed in the panel or written in a config, the emitted
device is the same shape as the one a JSON HOM table produces, and everything
that cannot work says why.
"""
import pytest

from wimba.assembly import MODE_TRIPLES, read_method, read_modes
from wimba.gui.model import (GElement, GMode, GModel, component_config,
                             component_save_config, default_models,
                             element_to_config, modes_from_dicts, modes_out,
                             new_element)


# --------------------------------------------------------------- read_modes
def test_a_complete_mode_survives_unchanged():
    modes = read_modes([{"Rl": 4200.0, "Ql": 1.0, "fl": 3.0e9}], "RFCAV")
    assert modes == [{"Rl": 4200.0, "Ql": 1.0, "fl": 3.0e9}]


def test_several_planes_in_one_mode_are_all_kept():
    mode = {"Rl": 1.1e5, "Ql": 420.0, "fl": 6.35e8,
            "Rxd": 2.4e5, "Qxd": 380.0, "fxd": 7.1e8}
    assert read_modes([mode], "RFCAV")[0] == mode


def test_a_single_mode_may_be_written_without_the_list():
    assert read_modes({"Rl": 1.0, "Ql": 2.0, "fl": 3.0}, "R") == \
        [{"Rl": 1.0, "Ql": 2.0, "fl": 3.0}]


def test_no_modes_says_a_resonator_is_a_spectrum():
    with pytest.raises(ValueError, match="states no modes"):
        read_modes([], "RFCAV")


def test_a_partial_triple_names_what_is_missing():
    # the compute path reads Ql and fl without checking, so this used to be a
    # KeyError from inside numpy
    with pytest.raises(ValueError) as exc:
        read_modes([{"Rl": 4200.0}], "RFCAV")
    assert "Ql" in str(exc.value) and "fl" in str(exc.value)
    assert "mode 1" in str(exc.value)


def test_zero_q_is_refused_before_it_divides():
    with pytest.raises(ValueError, match="Ql = 0.0 is not above zero"):
        read_modes([{"Rl": 1.0, "Ql": 0.0, "fl": 1.0e9}], "R")


def test_zero_frequency_is_refused():
    with pytest.raises(ValueError, match="fl = 0.0 is not above zero"):
        read_modes([{"Rl": 1.0, "Ql": 1.0, "fl": 0.0}], "R")


def test_a_mode_with_no_triple_at_all_lists_the_keys():
    with pytest.raises(ValueError) as exc:
        read_modes([{"shunt": 4200.0}], "R")
    assert "no R/Q/f triple" in str(exc.value)
    assert "Rl/Ql/fl" in str(exc.value)


def test_zero_shunt_impedance_is_a_value_not_an_omission():
    # a mode deliberately switched off: Rs = 0 contributes nothing and is not
    # an error, unlike a missing key
    assert read_modes([{"Rl": 0.0, "Ql": 1.0, "fl": 1.0e9}], "R")[0]["Rl"] == 0.0


def test_every_triple_is_the_pywit_hom_layout():
    assert MODE_TRIPLES[0] == ("Rl", "Ql", "fl")
    assert {t[0] for t in MODE_TRIPLES} == {"Rl", "Rxd", "Ryd", "Rxq", "Ryq"}


# ------------------------------------------------------------- read_method
def test_the_source_forces_the_method():
    # a resonator written without a method: line must not inherit pytlwall and
    # be handed to a wall engine
    assert read_method({}, "rf", "pytlwall", "resonator") == ("resonator", False)
    assert read_method({}, "rf", "pytlwall", "resonators_json") == ("resonator", False)


def test_a_resonator_cannot_claim_to_be_pre_weighted():
    with pytest.raises(ValueError, match="weighted"):
        read_method({"weighted": True}, "rf", "pytlwall", "resonator")


# ------------------------------------------------------ panel rows <-> file
def test_modes_out_writes_the_key_of_each_component():
    el = GElement(name="RFCAV", models=default_models("resonator"),
                  modes=[GMode(q="ZLong", Rs=4200.0, Q=1.0, fr=3.0e9),
                         GMode(q="ZDipY", Rs=8000.0, Q=350.0, fr=7.55e8)])
    assert modes_out(el) == [{"Rl": 4200.0, "Ql": 1.0, "fl": 3.0e9},
                             {"Ryd": 8000.0, "Qyd": 350.0, "fyd": 7.55e8}]


def test_modes_out_refuses_a_half_typed_field():
    # QDoubleValidator accepts "1e" while the user is still typing
    el = GElement(name="R", modes=[GMode(q="ZLong", Rs="1e", Q=1.0, fr=1.0e9)])
    with pytest.raises(ValueError, match="not a number"):
        modes_out(el)


def test_modes_out_validates_like_a_hand_written_config():
    el = GElement(name="R", modes=[GMode(q="ZLong", Rs=1.0, Q=0.0, fr=1.0e9)])
    with pytest.raises(ValueError, match="not above zero"):
        modes_out(el)


def test_a_multi_plane_mode_comes_back_as_one_row_per_plane():
    rows = modes_from_dicts([{"Rl": 1.0, "Ql": 2.0, "fl": 3.0e9,
                              "Rxd": 4.0, "Qxd": 5.0, "fxd": 6.0e9}])
    assert [(r.q, r.Rs) for r in rows] == [("ZLong", 1.0), ("ZDipX", 4.0)]


def test_rows_and_file_round_trip():
    modes = [{"Rl": 4200.0, "Ql": 1.0, "fl": 3.0e9},
             {"Rxq": 9000.0, "Qxq": 12.0, "fxq": 1.2e9}]
    el = GElement(name="R", modes=modes_from_dicts(modes))
    assert modes_out(el) == modes


# ------------------------------------------------------------ the emitters
def _resonator_component():
    el = new_element("RFCAV")
    el.models = default_models("resonator")
    el.optics = {"l": 1.8, "bx": 30.0, "by": 25.0}
    el.modes = [GMode(q="ZLong", Rs=1.1e5, Q=420.0, fr=6.35e8)]
    return el


def test_the_bench_emits_a_resonator_device():
    cfg = component_config(_resonator_component(), "resonator",
                           base_cfg={"gamma": 7461.0})
    spec = cfg["devices"]["bench"]
    assert spec["source"] == "resonator"
    assert spec["method"] == "resonator"
    assert spec["modes"] == [{"Rl": 1.1e5, "Ql": 420.0, "fl": 6.35e8}]
    assert spec["length_m"] == 1.8 and spec["beta_x"] == 30.0
    assert cfg["gamma"] == 7461.0


def test_the_emitted_device_carries_no_wall():
    spec = component_config(_resonator_component(), "resonator")["devices"]["bench"]
    for key in ("layers", "shape", "radius_m", "hor_m", "ver_m"):
        assert key not in spec


def test_a_resonator_is_never_pre_weighted():
    # only imported data can arrive already weighted; WIMBA computes this one
    spec = component_config(_resonator_component(), "resonator")["devices"]["bench"]
    assert spec["weighted"] is False


def test_saving_strips_the_method_label():
    cfg = component_save_config(_resonator_component(), base_cfg={"gamma": 7461.0})
    assert cfg["output"] == ["RFCAV"]
    assert cfg["devices"]["bench"]["name"] == "RFCAV"


def test_saving_a_resonator_with_no_modes_says_what_is_missing():
    el = new_element("EMPTY")
    el.models = default_models("resonator")
    with pytest.raises(ValueError, match="states no modes"):
        component_save_config(el)


def test_a_single_element_run_computes_a_resonator():
    cfg = element_to_config(_resonator_component(), base_cfg={"gamma": 100.0})
    assert cfg["devices"]["single"]["source"] == "resonator"
    assert cfg["devices"]["single"]["modes"]


def test_switching_method_keeps_the_wall_available_for_a_comparison():
    """The panel closes Geometry and Layers for a resonator; it does not clear
    them. So a wall comparison on the same element still has a wall to solve."""
    el = _resonator_component()
    el.geometry = {"length": 1.8, "shape": "CIRCULAR", "radius": 0.02}
    el.layers = [{"type": "CW", "sigma": 1.4e6, "thickness": "inf",
                  "boundary": True}]
    el.compare = [GModel(q="ZLong", method="pytlwall")]
    cfg = element_to_config(el, base_cfg={"gamma": 100.0})
    wall = cfg["devices"]["compare_0"]
    assert wall["source"] == "chamber"
    assert wall["radius_m"] == 0.02 and wall["layers"]


def test_a_resonator_comparison_is_refused_with_the_reason():
    el = _resonator_component()
    el.compare = [GModel(q="ZLong", method="resonator")]
    with pytest.raises(ValueError, match="nowhere to take its modes from"):
        element_to_config(el, base_cfg={"gamma": 100.0})
