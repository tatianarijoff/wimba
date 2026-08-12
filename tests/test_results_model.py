"""ResultsModel: lists what a run computed (total, wake, per-device) and serves
series for the plot/table workspace."""
import numpy as np
import pytest

# wimba.gui.results imports PyQt6 at module level: skip the whole module when
# the gui extra is not installed, as the other GUI tests do.
pytest.importorskip("PyQt6")

from wimba.output import write_single_element, write_totals, write_wake_totals   # noqa: E402
from wimba.gui.results import ResultsModel, decode, encode                       # noqa: E402


def _fake_output(tmp_path):
    f = np.logspace(6, 9, 12)
    t = np.linspace(1e-12, 5e-9, 10)
    write_totals(tmp_path, f, {"ZLong": 1 / f + 2j / f, "ZLongISC": 5j / f})
    write_wake_totals(tmp_path, t, {"WLong": np.exp(-t / 1e-9)})
    write_single_element(tmp_path, "collimators", "TCP", f, {"ZLong": 3 / f + 0j})
    return f, t


def test_model_lists_sources_and_series(tmp_path):
    f, t = _fake_output(tmp_path)
    m = ResultsModel().load(tmp_path)

    assert set(m.sources) == {"Total", "collimators/TCP"}
    assert set(m.sources["Total"]) == {"impedance", "wake"}

    x, y, label = m.series("Total", "impedance", "ZLong", "Im")
    assert np.allclose(x, f) and np.allclose(y, 2 / f) and "Im" in label
    x, y, _ = m.series("Total", "impedance", "ZLongISC", "|Z|")
    assert np.allclose(y, 5 / f)                     # ISC visible as its own quantity
    x, y, _ = m.series("Total", "wake", "WLong")
    assert np.allclose(x, t) and np.allclose(y, np.exp(-t / 1e-9))
    x, y, _ = m.series("collimators/TCP", "impedance", "ZLong", "Re")
    assert np.allclose(y, 3 / f)


def test_encode_decode_roundtrip():
    ref = encode("collimators/TCP", "impedance", "ZDipX", "|Z|")
    assert decode(ref) == ("collimators/TCP", "impedance", "ZDipX", "|Z|")


def test_model_derives_wall_plus_isc(tmp_path):
    f = np.logspace(6, 9, 8)
    write_totals(tmp_path, f, {"ZLong": 1 / f + 0j, "ZLongISC": 0 + 4j / f,
                               "ZDipX": 2 / f + 0j})
    m = ResultsModel().load(tmp_path)
    _x, comps = m.sources["Total"]["impedance"]
    assert "ZLong+ISC" in comps                       # wall + ISC derived
    assert np.allclose(comps["ZLong+ISC"], 1 / f + 4j / f)
    assert "ZDipX+ISC" not in comps                   # no ISC -> no derived sum


def test_adopt_total_wake(tmp_path):
    """Bench/element runs: the total's wake moves onto the element source and
    'Total' disappears (the total IS the element there)."""
    f = np.logspace(6, 9, 8)
    t = np.linspace(1e-12, 5e-9, 6)
    write_totals(tmp_path, f, {"ZLong": 1 / f + 0j})
    write_wake_totals(tmp_path, t, {"WLong": np.exp(-t / 1e-9)})
    write_single_element(tmp_path, "bench", "COMP[pytlwall]", f, {"ZLong": 1 / f + 0j})

    m = ResultsModel().load(tmp_path)
    m.adopt_total_wake("COMP[pytlwall]")
    assert "Total" not in m.sources
    assert "wake" in m.sources["bench/COMP[pytlwall]"]
    _x, w = m.sources["bench/COMP[pytlwall]"]["wake"]
    assert "WLong" in w


def test_export_model_writes_one_file_per_source_and_kind(tmp_path):
    """Export Results writes every computed series to a chosen directory:
    impedances as Re/Im column pairs, wakes as one column per quantity."""
    import csv
    from wimba.gui.results import ResultsModel, export_model

    out = tmp_path / "run"
    _fake_output(out)
    model = ResultsModel().load(out)
    assert model.sources, "fixture produced no sources"

    dest = tmp_path / "chosen elsewhere"
    written = export_model(model, dest)
    assert written, "nothing written"
    assert all(p.parent == dest for p in written)

    for path in written:
        with open(path, newline="") as fh:
            rows = list(csv.reader(fh))
        header, body = rows[0], rows[1:]
        assert body, f"{path.name} has no data rows"
        assert all(len(r) == len(header) for r in body)
        if "__impedance" in path.name:
            assert header[0] == "f [Hz]"
            assert sum(h.startswith("Re(") for h in header) == \
                   sum(h.startswith("Im(") for h in header)
        elif "__wake" in path.name:
            assert header[0] == "t [s]"
        float(body[0][0])


def test_export_model_txt_is_tab_separated(tmp_path):
    """The TXT variant uses tabs, matching the layout pytlwall writes, so the
    two codes can be compared column by column."""
    import csv
    from wimba.gui.results import ResultsModel, export_model

    out = tmp_path / "run"
    _fake_output(out)
    model = ResultsModel().load(out)

    csv_files = export_model(model, tmp_path / "as_csv", fmt="csv")
    txt_files = export_model(model, tmp_path / "as_txt", fmt="txt")

    assert {p.suffix for p in csv_files} == {".csv"}
    assert {p.suffix for p in txt_files} == {".txt"}
    assert [p.stem for p in csv_files] == [p.stem for p in txt_files]

    raw = txt_files[0].read_text()
    assert "\t" in raw.splitlines()[0]
    assert "," not in raw.splitlines()[0]

    # same content, different delimiter
    with open(csv_files[0], newline="") as fh:
        as_csv = list(csv.reader(fh))
    with open(txt_files[0], newline="") as fh:
        as_txt = list(csv.reader(fh, delimiter="\t"))
    assert as_csv == as_txt


def test_export_model_rejects_unknown_format(tmp_path):
    from wimba.gui.results import ResultsModel, export_model
    out = tmp_path / "run"
    _fake_output(out)
    with pytest.raises(ValueError, match="unknown export format"):
        export_model(ResultsModel().load(out), tmp_path / "x", fmt="xlsx")


def test_export_model_creates_missing_directory(tmp_path):
    """A directory typed into the dialog that does not exist yet is created."""
    from wimba.gui.results import ResultsModel, export_model
    out = tmp_path / "run"
    _fake_output(out)
    dest = tmp_path / "new" / "nested"
    assert not dest.exists()
    assert export_model(ResultsModel().load(out), dest)
    assert dest.is_dir()


# ------------------------------------------- results from several scenarios
def _write_run_output(root, scale=1.0):
    """The layout the run pipeline writes: single_elements/total.csv plus one
    CSV per device."""
    import numpy as np
    se = root / "single_elements"
    (se / "grp").mkdir(parents=True)
    f = np.logspace(6, 9, 12)
    for path in (se / "total.csv", se / "grp" / "dev.csv"):
        with open(path, "w") as fh:
            fh.write("freq,Re_ZLong,Im_ZLong\n")          # the layout run writes
            for fi in f:
                fh.write(f"{fi},{scale * fi:.6e},{-scale * fi:.6e}\n")
    return root


def test_two_scenarios_live_side_by_side(tmp_path):
    """The reason this exists: both scenarios write "Total" and the same device
    names, so without a label the second calculation erases the first and there
    is nothing left to compare."""
    from wimba.gui.results import ResultsModel

    a = _write_run_output(tmp_path / "inj", scale=1.0)
    b = _write_run_output(tmp_path / "ext", scale=3.0)

    m = ResultsModel()
    m.add_scenario(a, "injection")
    m.add_scenario(b, "extraction")

    assert m.scenarios() == ["injection", "extraction"]
    assert len(m.sources) == 4                      # 2 sources x 2 scenarios
    _x, y_inj, lab = m.series("injection \u00b7 Total", "impedance", "ZLong", "Re")
    _x, y_ext, _l = m.series("extraction \u00b7 Total", "impedance", "ZLong", "Re")
    assert "injection" in lab                       # the legend says which is which
    assert y_ext == pytest.approx(3.0 * y_inj)


def test_recomputing_a_scenario_replaces_it_and_leaves_the_others(tmp_path):
    from wimba.gui.results import ResultsModel
    import numpy as np

    a = _write_run_output(tmp_path / "inj", scale=1.0)
    b = _write_run_output(tmp_path / "ext", scale=3.0)
    m = ResultsModel().add_scenario(a, "injection").add_scenario(b, "extraction")

    again = _write_run_output(tmp_path / "inj2", scale=7.0)
    m.add_scenario(again, "injection")

    assert len(m.sources) == 4                      # replaced, not duplicated
    _x, y, _l = m.series("injection \u00b7 Total", "impedance", "ZLong", "Re")
    assert np.max(y) == pytest.approx(7.0e9, rel=1e-6)
    _x, y_ext, _l = m.series("extraction \u00b7 Total", "impedance", "ZLong", "Re")
    assert np.max(y_ext) == pytest.approx(3.0e9, rel=1e-6)   # untouched
