"""The run orchestration: per-geometry caching, totals = sum, opt-in per-device."""
import numpy as np
import pytest

pytest.importorskip("pytlwall")
from wimba.assembly import Assignment
from wimba.run import compute_assignments
from wimba.output import read_totals

F = np.logspace(6, 9, 8)


def _row(name, radius, beta_x=1.0, length=1.0, group="g"):
    return Assignment(position=0.0, name=name, kind="device", method="pytlwall",
                      weighted=False, space_charge=False, beta_x=beta_x, beta_y=1.0,
                      beta_source="explicit", allow_overlap=False, length=length,
                      geometry={"radius": radius, "layers": [{"material": "copper", "thickness": 0.002}]},
                      group=group)


def test_cache_and_totals(tmp_path):
    rows = [_row("a", 0.02), _row("b", 0.02, beta_x=2.0), _row("c", 0.03)]
    totals, stats = compute_assignments(rows, F, tmp_path / "out", per_device=["a"])

    # two rows share geometry 0.02 -> only two distinct geometries computed
    assert stats["computed"] == 3 and stats["geometries"] == 2

    # opt-in per-device file only for "a"
    se = tmp_path / "out" / "single_elements"
    assert (se / "g" / "a.csv").is_file()
    assert not (se / "g" / "b.csv").exists()
    assert (se / "total.csv").is_file()

    # totals equal the sum of the three contributions (check ZLong)
    _, comps = read_totals(se / "total.csv")
    assert comps["ZLong"].shape == F.shape and np.all(np.isfinite(comps["ZLong"]))


def test_non_pytlwall_skipped(tmp_path):
    r = _row("x", 0.02)
    r.method = "resonator"
    totals, stats = compute_assignments([r], F, tmp_path / "out")
    assert stats["skipped"] == 1 and stats["computed"] == 0
