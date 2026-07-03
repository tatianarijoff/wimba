"""Assembly: beta resolution (position -> name -> end), default pipe per row,
space-charge gating, collision detection, CSV output."""
import csv

from wimba.assembly import (Assignment, DefaultPipe, Device, assemble,
                            write_csv)

TWISS = {
    "M1": {"NAME": "M1", "S": 0.0,  "L": 1.0, "BETX": 10.0, "BETY": 20.0},
    "M2": {"NAME": "M2", "S": 10.0, "L": 1.0, "BETX": 30.0, "BETY": 40.0},
    "M3": {"NAME": "M3", "S": 20.0, "L": 1.0, "BETX": 50.0, "BETY": 60.0},
}


def _row(res, name):
    return next(r for r in res.rows if r.name == name)


def test_beta_resolution_modes():
    devices = [
        Device("TCP", method="pytlwall", space_charge=True, position=5.0),  # interp
        Device("M2", method="resonator"),                                   # by name
        Device("CRAB", method="precalculated", weighted=True),              # end, beta 1
    ]
    res = assemble(TWISS, devices, DefaultPipe(method="iw2d"), name="Test")

    tcp = _row(res, "TCP")
    assert tcp.beta_source == "interp"
    assert abs(tcp.beta_x - 20.0) < 1e-9 and abs(tcp.beta_y - 30.0) < 1e-9  # midway M1->M2
    assert tcp.space_charge is True                                        # pytlwall

    m2 = _row(res, "M2")
    assert m2.beta_source == "name" and abs(m2.beta_x - 30.0) < 1e-9

    crab = _row(res, "CRAB")
    assert crab.beta_source == "default-1"
    assert crab.position is None and crab.beta_x == 1.0 and crab.weighted is True


def test_space_charge_only_pytlwall():
    res = assemble(TWISS, [Device("X", method="resonator", space_charge=True, position=5.0)],
                   None)
    assert _row(res, "X").space_charge is False


def test_default_pipe_covers_uncovered_rows():
    # a device claims M2 by name; default pipe should cover M1 and M3 only
    res = assemble(TWISS, [Device("M2", method="pytlwall")], DefaultPipe(method="iw2d"))
    pipes = [r for r in res.rows if r.kind == "default_pipe"]
    assert {p.name for p in pipes} == {"M1", "M3"}
    for p in pipes:
        assert p.weighted is False and p.method == "iw2d"          # plain
    # default pipe beta is the local interpolated value at that row
    assert abs(_row(res, "M1").beta_x - 10.0) < 1e-9


def test_collision_detection():
    dev = [Device("A", position=5.0), Device("B", position=5.0)]
    res = assemble(TWISS, dev, None)
    assert len(res.collisions) == 1 and res.collisions[0].intentional is False

    dev2 = [Device("A", position=5.0, allow_overlap=True),
            Device("B", position=5.0, allow_overlap=True)]
    res2 = assemble(TWISS, dev2, None)
    assert res2.collisions[0].intentional is True

    # distinct positions -> no collision
    res3 = assemble(TWISS, [Device("A", position=5.0), Device("B", position=6.0)], None)
    assert res3.collisions == []


def test_csv_roundtrip(tmp_path):
    res = assemble(TWISS, [Device("TCP", position=5.0, method="pytlwall")],
                   DefaultPipe(), name="Test")
    path = write_csv(res, tmp_path / "Test_assignments.csv")
    with open(path) as fh:
        rows = list(csv.DictReader(fh))
    assert {"position_s", "name", "method", "beta_x", "beta_source"} <= set(rows[0])
    tcp = next(r for r in rows if r["name"] == "TCP")
    assert tcp["method"] == "pytlwall" and tcp["beta_source"] == "interp"
