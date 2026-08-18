"""Repeated element names in a TFS table.

MAD-X numbers its drifts (DRIFT_0, DRIFT_1, ...) so a twiss it writes has unique
names. A table exported from an xsuite line does not: shared element instances
reuse one name. In the FCC-ee Z lattice 11275 of 30080 rows carry only 87
distinct names, 11944 m of the 90660 m ring -- and a reader keyed by name
dropped 13% of the circumference from the default pipe without failing.
"""
import pytest

from wimba.builders import madx

HEADER = ('@ NAME     %05s "TWISS"\n'
          '* NAME                  S            L            BETX         BETY\n'
          '$ %s                    %le          %le          %le          %le\n')

ROWS = [('"drift_a"', 1.0, 1.0, 10.0, 20.0),
        ('"MQ.1"',    2.0, 1.0, 30.0, 40.0),
        ('"drift_a"', 3.0, 1.0, 50.0, 60.0),
        ('"drift_a"', 4.0, 1.0, 70.0, 80.0)]


@pytest.fixture
def tfs(tmp_path):
    p = tmp_path / "dup.tfs"
    body = "".join(f'  {n:<22s}{s:<13g}{l:<13g}{bx:<13g}{by:<13g}\n'
                   for n, s, l, bx, by in ROWS)
    p.write_text(HEADER + body)
    return p


def test_rename_keeps_every_row_and_the_total_length(tfs):
    t = madx.read_twiss(tfs)
    assert len(t) == len(ROWS)
    assert sum(float(madx.get(r, "L")) for r in t.values()) == pytest.approx(4.0)
    assert set(t) == {"drift_a", "MQ.1", "drift_a.2", "drift_a.3"}


def test_first_occurrence_keeps_the_bare_name(tfs):
    """A device named after the first occurrence must still resolve to it."""
    t = madx.read_twiss(tfs)
    assert float(madx.get(t["drift_a"], "S")) == pytest.approx(1.0)
    assert float(madx.get(t["drift_a.3"], "S")) == pytest.approx(4.0)


def test_last_reproduces_the_old_lossy_behaviour(tfs):
    t = madx.read_twiss(tfs, on_duplicate="last")
    assert len(t) == 2                                    # this is the bug, on purpose
    assert float(madx.get(t["drift_a"], "S")) == pytest.approx(4.0)


def test_error_refuses_a_table_madx_could_not_have_written(tfs):
    with pytest.raises(ValueError, match="appears more than once"):
        madx.read_twiss(tfs, on_duplicate="error")


def test_unknown_policy_is_rejected(tfs):
    with pytest.raises(ValueError, match="on_duplicate must be"):
        madx.read_twiss(tfs, on_duplicate="whatever")


def test_duplicates_is_a_cheap_preflight_check(tfs):
    assert madx.duplicates(tfs) == {"drift_a": 3}


def test_no_duplicates_reports_nothing(tmp_path):
    p = tmp_path / "clean.tfs"
    p.write_text(HEADER + '  "MQ.1"   1 1 10 20\n  "MQ.2"   2 1 30 40\n')
    assert madx.duplicates(p) == {}
    assert len(madx.read_twiss(p)) == 2
