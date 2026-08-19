"""A wrong column must be refused, not interpolated.

The case that prompted this: a pytlwall export written with
``DataFrame.to_excel(...)`` keeps the pandas index, so the first column is the
row number. A map that says ``freq: 1`` then reads 0, 1, 2, ... as frequencies.
Nothing raises, the interpolation succeeds, and the answer is wrong.
"""
import numpy as np
import pytest
import yaml

from wimba.io.import_map import check_x_column, load_import_map


def test_a_row_index_is_recognised_and_named(tmp_path):
    with pytest.raises(ValueError, match="row number"):
        check_x_column(np.arange(50.0), tmp_path / "f.xlsx", "impedance", 1)


def test_the_message_says_how_to_fix_it(tmp_path):
    with pytest.raises(ValueError) as err:
        check_x_column(np.arange(50.0), tmp_path / "f.xlsx", "impedance", 1)
    assert "index=False" in str(err.value)
    assert "try column 2" in str(err.value)


def test_a_column_that_does_not_increase_is_refused(tmp_path):
    with pytest.raises(ValueError, match="does not increase"):
        check_x_column([1e3, 1e5, 1e4], tmp_path / "f.dat", "impedance", 1)


def test_a_real_frequency_column_passes(tmp_path):
    check_x_column(np.logspace(3, 11, 40), tmp_path / "f.dat", "impedance", 1)


def test_a_time_column_may_start_at_zero(tmp_path):
    """Wake data legitimately starts at t = 0; only a 0,1,2,... run is a row
    index, and two points cannot tell the difference."""
    check_x_column([0.0, 1e-12, 2e-12], tmp_path / "w.dat", "wake", 1)


def test_the_map_reader_applies_it(tmp_path):
    """End to end: the descriptor loads the wrong column and is stopped."""
    data = tmp_path / "d.csv"
    rows = ["index,freq,re,im"]
    rows += [f"{i},{f:.6g},1.0,2.0"
             for i, f in enumerate(np.logspace(3, 6, 20))]
    data.write_text("\n".join(rows) + "\n")

    m = tmp_path / "m.yaml"
    m.write_text(yaml.safe_dump({
        "common_impedance": {"file": "d.csv", "comment": "#", "sep": ",",
                             "skip_rows": 1, "freq_unit": "Hz",
                             "format": "re_im",
                             "columns": {"freq": 1, "re": 3, "im": 4}},
        "components": {"ZLong": {}}}))
    with pytest.raises(ValueError, match="row number"):
        load_import_map(m)

    # and the same file read one column to the right is fine
    m.write_text(yaml.safe_dump({
        "common_impedance": {"file": "d.csv", "comment": "#", "sep": ",",
                             "skip_rows": 1, "freq_unit": "Hz",
                             "format": "re_im",
                             "columns": {"freq": 2, "re": 3, "im": 4}},
        "components": {"ZLong": {}}}))
    out = load_import_map(m)
    assert out["impedance"]["ZLong"][0][0] == pytest.approx(1e3)


def test_the_reader_s_reason_is_handed_back_not_swallowed(tmp_path):
    """precalculated_components used to return () for any failure, so the GUI
    could not tell 'plain three-column table' from 'unreadable'."""
    from wimba.sources.precalculated_bridge import precalculated_components

    bad = tmp_path / "bad.csv"
    bad.write_text("not,a,table\n1,2,3\n")
    comps, reason = precalculated_components(bad, return_reason=True)
    assert comps == ()
    assert reason and "bad.csv" in reason
