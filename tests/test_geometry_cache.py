"""The geometry cache key must cover everything that changes the answer.

One geometry is solved once and the result reused, which is what makes an
11k-segment default pipe affordable. The key therefore has to include every
input to that solve: two devices that differ in something the key ignores get
each other's numbers, and nothing says so.
"""
import pytest

from wimba.run import _geo_key

BASE = {"radius": 0.002, "shape": "CIRCULAR",
        "layers": [{"type": "CW", "thickness": "inf", "sigma": 2.0e5}]}


def test_the_same_wall_is_the_same_key():
    assert _geo_key(dict(BASE)) == _geo_key(dict(BASE))


def test_the_yokoya_factors_are_part_of_it():
    """They rescale a round solve into another geometry, so a device with them
    is not the device without them."""
    plain = _geo_key(dict(BASE))
    flat = _geo_key(dict(BASE, iw2d_yokoya=[1.0, 0.411, 0.822, -0.411, 0.411]))
    assert plain != flat


def test_different_factors_are_different_keys():
    a = _geo_key(dict(BASE, iw2d_yokoya=[1.0, 0.411, 0.822, -0.411, 0.411]))
    b = _geo_key(dict(BASE, iw2d_yokoya=[1.0, 0.400, 0.810, -0.400, 0.400]))
    assert a != b


def test_the_test_beam_shift_is_part_of_it():
    """It changes the space-charge terms, so two chambers that differ only in
    it are two calculations."""
    assert _geo_key(dict(BASE)) != _geo_key(dict(BASE, test_beam_shift=0.01))
    assert (_geo_key(dict(BASE, test_beam_shift=0.001))
            != _geo_key(dict(BASE, test_beam_shift=0.01)))


def test_the_wall_still_decides_the_rest():
    assert _geo_key(dict(BASE)) != _geo_key(dict(BASE, radius=0.02))
    assert _geo_key(dict(BASE)) != _geo_key(
        dict(BASE, layers=[{"type": "CW", "thickness": "inf", "sigma": 5.9e7}]))
