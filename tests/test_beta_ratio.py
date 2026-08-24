"""The transverse weight is beta / beta_mean, not beta.

Weighting by the bare beta left every transverse total a factor of the average
beta too large -- tens or hundreds -- and made it an impedance times a length
rather than an impedance. These tests pin the ratio, the average it divides by,
and the two readings that follow from it: an element at the average weighs one,
and an element WIMBA cannot place is treated as sitting there.
"""
import pytest

from wimba.assembly import (WEIGHTED_METHOD, Device, assemble,
                            element_mean_beta, read_method,
                            read_smooth_beta)
from wimba.builders.madx import mean_beta
from wimba.core.terms import STANDARD_TERMS

TWISS = {
    "M1": {"NAME": "M1", "S": 0.0, "L": 4.0, "BETX": 10.0, "BETY": 40.0},
    "M2": {"NAME": "M2", "S": 4.0, "L": 6.0, "BETX": 60.0, "BETY": 20.0},
    "MARKER": {"NAME": "MARKER", "S": 10.0, "L": 0.0, "BETX": 999.0, "BETY": 999.0},
}
#  x: (10*4 + 60*6) / 10 = 40 ;  y: (40*4 + 20*6) / 10 = 28
MEAN = (40.0, 28.0)


# ---------------------------------------------------------------- the average
def test_the_average_is_length_weighted_over_the_twiss_rows():
    assert mean_beta(TWISS) == MEAN


def test_a_zero_length_row_occupies_no_ring():
    """A marker sits at one point; it cannot pull the average anywhere."""
    without = dict(TWISS)
    without.pop("MARKER")
    assert mean_beta(without) == mean_beta(TWISS)


def test_no_lengths_means_no_average():
    """Falls back to 1, leaving the bare beta rather than dividing by zero."""
    assert mean_beta({"A": {"BETX": 10.0, "BETY": 10.0}}) == (1.0, 1.0)
    assert mean_beta({}) == (1.0, 1.0)


# ---------------------------------------------------------------- the weight
def test_an_element_at_the_average_weighs_one_in_every_term():
    for tid in STANDARD_TERMS.values():
        assert tid.beta_weight(*MEAN, *MEAN) == pytest.approx(1.0)


def test_the_longitudinal_term_is_never_weighted():
    zlong = STANDARD_TERMS["zlong"]
    assert zlong.beta_weight(500.0, 0.1, *MEAN) == 1.0


def test_a_dipolar_term_scales_with_the_ratio_in_its_own_plane():
    zxdip, zydip = STANDARD_TERMS["zxdip"], STANDARD_TERMS["zydip"]
    assert zxdip.beta_weight(2 * MEAN[0], MEAN[1], *MEAN) == pytest.approx(2.0)
    assert zxdip.beta_weight(MEAN[0], 7 * MEAN[1], *MEAN) == pytest.approx(1.0)
    assert zydip.beta_weight(MEAN[0], 3 * MEAN[1], *MEAN) == pytest.approx(3.0)


def test_the_weight_is_dimensionless_so_it_does_not_scale_with_the_lattice():
    """Doubling every beta in the ring leaves every weight untouched."""
    zxdip = STANDARD_TERMS["zxdip"]
    assert (zxdip.beta_weight(80.0, 10.0, 40.0, 28.0)
            == pytest.approx(zxdip.beta_weight(160.0, 20.0, 80.0, 56.0)))


def test_without_a_mean_the_bare_beta_is_still_used():
    """The default keeps a bench component -- no lattice at all -- working."""
    assert STANDARD_TERMS["zxdip"].beta_weight(60.0, 20.0) == 60.0


# ---------------------------------------------------------------- assembly
def _dev(name, **kw):
    kw.setdefault("method", "precalculated")
    return Device(name, **kw)


def test_assemble_finds_the_average_from_the_lattice():
    res = assemble(TWISS, [], None)
    assert res.beta_mean == MEAN and res.beta_mean_source == "lattice"


def test_smooth_beta_wins_over_the_lattice():
    """It is stated on purpose; the lattice average only estimates the same thing."""
    res = assemble(TWISS, [], None, smooth_beta=(33.0, 21.0))
    assert res.beta_mean == (33.0, 21.0) and res.beta_mean_source == "smooth_beta"


def test_an_unplaceable_device_sits_at_the_average():
    res = assemble(TWISS, [_dev("NOWHERE")], None)
    row = res.rows[0]
    assert row.beta_source == "default-1"
    assert (row.beta_x, row.beta_y) == MEAN
    assert STANDARD_TERMS["zxdip"].beta_weight(row.beta_x, row.beta_y,
                                               *res.beta_mean) == pytest.approx(1.0)


def test_without_a_lattice_the_elements_are_averaged_instead_of_falling_back_to_one():
    """beta_mean = 1 m against local betas of tens is the old, wrong weighting."""
    res = assemble({}, [_dev("A", beta=(60.0, 20.0), length=1.0),
                        _dev("B", beta=(20.0, 60.0), length=3.0)], None)
    assert res.beta_mean_source == "elements"
    assert res.beta_mean == (30.0, 50.0)          # length-weighted, not a plain mean
    assert any("estimated from the modelled elements" in w for w in res.warnings)


def test_the_element_average_needs_someone_to_state_a_beta():
    assert element_mean_beta([_dev("D")]) == (1.0, 1.0)


def test_no_mean_warning_when_nothing_states_a_local_beta():
    """Every ratio is 1 anyway, so beta_mean = 1 m costs nothing here.

    The device is still reported as unplaceable -- a different problem, and one
    the assembly warned about before this change.
    """
    res = assemble({}, [_dev("D")], None)
    assert not any("smooth_beta" in w for w in res.warnings)


# ---------------------------------------------------------------- weighted:
def test_the_weighting_travels_in_the_method_name():
    assert read_method({"method": WEIGHTED_METHOD}, "BPM", "pytlwall") == \
        ("precalculated", True)
    assert read_method({"method": "iw2d"}, "COLL", "pytlwall") == ("iw2d", False)
    assert read_method({}, "COLL", "pytlwall") == ("pytlwall", False)


def test_the_old_flag_still_reads():
    assert read_method({"method": "precalculated", "weighted": "ratio"},
                       "BPM", "pytlwall") == ("precalculated", True)
    assert read_method({"method": "precalculated", "weighted": True},
                       "BPM", "pytlwall") == ("precalculated", True)


def test_a_computed_method_cannot_claim_to_be_already_weighted():
    """It would weight WIMBA's own numbers twice."""
    for method in ("pytlwall", "iw2d", "resonator"):
        with pytest.raises(ValueError, match="cannot apply to method"):
            read_method({"method": method, "weighted": "ratio"}, "COLL", "pytlwall")


def test_an_unknown_spelling_of_the_old_flag_is_refused():
    with pytest.raises(ValueError, match="not a value WIMBA knows"):
        read_method({"method": "precalculated", "weighted": "yes please"},
                    "BPM", "pytlwall")


def test_smooth_beta_needs_both_planes():
    assert read_smooth_beta({}) is None
    assert read_smooth_beta({"smooth_beta": {"x": 3.0, "y": 4.0}}) == (3.0, 4.0)
    with pytest.raises(ValueError, match="both x: and y:"):
        read_smooth_beta({"smooth_beta": {"x": 3.0}})


# ------------------------------------------------- the build path, same rules
def test_the_build_path_falls_back_to_its_own_elements(tmp_path):
    """A machine file with hand-written betas and no twiss must not use 1."""
    from wimba.builders.loader import resolve_beta_mean, machine_mean_beta
    from wimba.core.machine import Machine
    from wimba.core.element import Element, ElementGroup
    from wimba.core.optics import Explicit

    machine = Machine()
    group = machine.add_group("g")
    for name, (bx, by), length in (("A", (60.0, 20.0), 1.0),
                                   ("B", (20.0, 60.0), 3.0)):
        group.elements.append(Element(name=name, category="element",
                                      length=length, provider=None,
                                      optics=Explicit(bx, by),
                                      meta={"beta_x": bx, "beta_y": by}))
    assert machine_mean_beta(machine) == (30.0, 50.0)
    assert resolve_beta_mean({}, {}, machine) == ((30.0, 50.0), "elements")


def test_stated_smooth_beta_still_wins_in_the_build_path():
    from wimba.builders.loader import resolve_beta_mean
    got = resolve_beta_mean({"smooth_beta": {"x": 12.0, "y": 9.0}}, TWISS)
    assert got == ((12.0, 9.0), "smooth_beta")


def test_source_precalculated_decides_the_method():
    """`source:` wins over `method:`, which is what the loader then does too.

    Without this the check reads the *default* method -- pytlwall -- and refuses
    an ordinary imported device that never mentioned a method at all.
    """
    from wimba.assembly import read_method
    spec = {"source": "precalculated", "name": "KICKER", "weighted": True}
    assert read_method(spec, "kicker", "pytlwall", "precalculated") == \
        ("precalculated", True)
