"""The guard against a device that was never located in the lattice.

`_resolve` falls back to beta = 1 for a device with no position:, no explicit
beta:, and a name absent from the twiss. With `weighted: true` that is the
intended behaviour for a lumped ring total. With `weighted: false` it silently
replaces the local optics with 1, and the result stays plausible -- so it is
reported.
"""
from wimba.assembly import Device, DefaultPipe, assemble, unlocated_warnings

TWISS = {
    "MQ.1": {"NAME": "MQ.1", "S": 10.0, "L": 1.0, "BETX": 30.0, "BETY": 12.0},
    "MQ.2": {"NAME": "MQ.2", "S": 20.0, "L": 1.0, "BETX": 90.0, "BETY": 40.0},
}


def _dev(name, **kw):
    kw.setdefault("method", "precalculated")
    return Device(name=name, **kw)


def test_unlocated_plain_device_is_reported():
    res = assemble(TWISS, [_dev("NOWHERE", weighted=False)], None)
    assert len(res.warnings) == 1
    text = res.warnings[0]
    assert "NOWHERE" in text
    assert "beta = 1" in text
    assert "weighted: true" in text          # the message says how to fix it


def test_unlocated_weighted_device_is_silent():
    """A ring total has nowhere to sit; beta = 1 is the point, not a mistake."""
    res = assemble(TWISS, [_dev("BPM", weighted=True)], None)
    assert res.warnings == []
    assert res.rows[0].beta_x == 1.0


def test_device_placed_by_position_is_silent():
    res = assemble(TWISS, [_dev("COLL", position=15.0, weighted=False)], None)
    assert res.warnings == []
    assert 30.0 < res.rows[0].beta_x < 90.0   # interpolated, not 1


def test_device_found_by_name_is_silent():
    res = assemble(TWISS, [_dev("MQ.2", weighted=False)], None)
    assert res.warnings == []
    assert res.rows[0].beta_x == 90.0


def test_explicit_beta_is_silent():
    res = assemble(TWISS, [_dev("NOWHERE", beta=(55.0, 33.0), weighted=False)], None)
    assert res.warnings == []
    assert res.rows[0].beta_x == 55.0


def test_default_pipe_rows_are_never_flagged():
    res = assemble(TWISS, [], DefaultPipe(geometry={}))
    assert res.warnings == []
    assert len(res.rows) == 2


def test_several_devices_give_several_warnings():
    res = assemble(TWISS, [_dev("A", weighted=False), _dev("B", weighted=False),
                           _dev("C", weighted=True)], None)
    assert len(res.warnings) == 2


def test_helper_is_usable_on_its_own():
    res = assemble(TWISS, [_dev("NOWHERE", weighted=False)], None)
    assert unlocated_warnings(res.rows) == res.warnings
