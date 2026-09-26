"""Per-device / totals CSV layout, and plotting the totals from file."""
import numpy as np
import pytest

from wimba.output import (clear_single_elements, find_totals, read_totals,
                          write_single_element, write_totals, write_wake_totals)


def test_single_element_and_totals_layout(tmp_path):
    f = np.logspace(6, 9, 12)
    a = {"ZLong": np.ones(12) + 0j, "ZDipX": 2 * np.ones(12) + 1j}
    b = {"ZLong": 3 * np.ones(12) + 0j, "ZDipX": 4 * np.ones(12) - 1j}
    write_single_element(tmp_path / "out", "collimators", "TCP.C6L7.B1", f, a)
    write_single_element(tmp_path / "out", "collimators", "TCSG.A6L7.B1", f, b)
    write_totals(tmp_path / "out", f, {k: a[k] + b[k] for k in a})

    se = tmp_path / "out" / "single_elements"
    assert (se / "collimators" / "TCP.C6L7.B1.csv").is_file()
    assert (tmp_path / "out" / "total.csv").is_file()   # the machine's result, on top
    assert not (se / "total.csv").exists()

    fr, comps = read_totals(tmp_path / "out" / "total.csv")
    assert np.allclose(fr, f)
    assert np.allclose(comps["ZLong"], 4) and np.allclose(comps["ZDipX"], 6 + 0j)


def test_plot_totals_saves_png(tmp_path):
    pytest.importorskip("matplotlib")
    from wimba.plotting import plot_totals
    f = np.logspace(6, 9, 20)
    write_totals(tmp_path / "out", f, {"ZLong": 1 / f + 0j, "ZDipX": 10 / f + 0j})
    paths = plot_totals(tmp_path / "out" / "total.csv",
                        components=["ZLong", "ZDipX"], out_dir=tmp_path)
    assert len(paths) == 2 and all(p.is_file() and p.stat().st_size > 0 for p in paths)


def test_chamber_terms_beta_weighting(tmp_path):
    pytest.importorskip("pytlwall")
    from wimba.sources.pytlwall_bridge import chamber_terms
    from wimba.output import write_single_element, write_totals
    f = np.logspace(6, 9, 8)
    t1 = chamber_terms(f, radius_m=0.02, length_m=1.0, betax=1.0, betay=1.0,
                       gamma=7000.0)
    t2 = chamber_terms(f, radius_m=0.02, length_m=1.0, betax=2.0, betay=1.0,
                       gamma=7000.0)
    assert np.allclose(t2["ZDipX"], 2 * t1["ZDipX"], rtol=1e-6)   # dip scales with beta
    assert np.allclose(t2["ZLong"], t1["ZLong"], rtol=1e-9)       # long does not
    # end-to-end: two single elements -> structure + totals
    write_single_element(tmp_path / "o", "pipes", "e1", f, t1)
    write_single_element(tmp_path / "o", "pipes", "e2", f, t2)
    write_totals(tmp_path / "o", f, {c: t1[c] + t2[c] for c in t1})
    assert (tmp_path / "o" / "total.csv").is_file()


# ----------------------------------------- where the totals live, old and new
def _legacy_output(out):
    """A folder written before the totals moved up: everything under
    single_elements/."""
    f = np.logspace(6, 9, 5)
    se = out / "single_elements"
    se.mkdir(parents=True)
    (se / "total.csv").write_text(
        "freq,Re_ZLong,Im_ZLong\n" + "".join(f"{x:.8e},1.0,0.0\n" for x in f))
    (se / "total_wake.csv").write_text("time,WLong\n1e-12,1.0\n2e-12,0.5\n")
    return out


def test_find_totals_prefers_the_top_of_the_folder(tmp_path):
    f = np.logspace(6, 9, 5)
    write_totals(tmp_path, f, {"ZLong": np.ones(5) + 0j})
    write_wake_totals(tmp_path, np.array([1e-12, 2e-12]), {"WLong": np.ones(2)})
    assert find_totals(tmp_path) == tmp_path / "total.csv"
    assert find_totals(tmp_path, wake=True) == tmp_path / "total_wake.csv"


def test_find_totals_still_reads_an_old_folder(tmp_path):
    """An output computed before the move opens without being recomputed."""
    out = _legacy_output(tmp_path / "old")
    assert find_totals(out) == out / "single_elements" / "total.csv"
    assert find_totals(out, wake=True) == out / "single_elements" / "total_wake.csv"
    _f, comps = read_totals(find_totals(out))
    assert np.allclose(comps["ZLong"], 1.0)


def test_find_totals_on_an_empty_folder(tmp_path):
    assert find_totals(tmp_path) is None
    assert find_totals(tmp_path / "missing", wake=True) is None


def test_clear_removes_totals_in_both_places(tmp_path):
    """Recomputing an old folder must not leave its totals behind under
    single_elements/, where they would sit next to the new ones on top."""
    out = _legacy_output(tmp_path / "out")
    write_totals(out, np.logspace(6, 9, 5), {"ZLong": np.ones(5) + 0j})
    (out / "WAKE_NOTES.txt").write_text("provenance\n")
    (out / "my_notes.txt").write_text("mine\n")

    removed = {p.relative_to(out).as_posix() for p in clear_single_elements(out)}

    assert removed == {"total.csv", "WAKE_NOTES.txt", "single_elements/total.csv",
                       "single_elements/total_wake.csv"}
    assert (out / "my_notes.txt").is_file()          # not ours: left alone
    assert find_totals(out) is None


def test_cli_plot_accepts_the_output_folder(tmp_path, capsys):
    pytest.importorskip("matplotlib")
    from wimba.cli import main
    f = np.logspace(6, 9, 20)
    write_totals(tmp_path / "out", f, {"ZLong": 1 / f + 0j})
    assert main(["plot", str(tmp_path / "out"), "--components", "ZLong"]) == 0
    assert (tmp_path / "out" / "total_ZLong.png").is_file()


def test_cli_plot_on_a_folder_without_totals(tmp_path, capsys):
    from wimba.cli import main
    (tmp_path / "empty").mkdir()
    assert main(["plot", str(tmp_path / "empty")]) == 2
    assert "no total.csv" in capsys.readouterr().err
