"""A recompute replaces the previous results; it does not pile up on them.

Calculate always recomputes -- that is the intended behaviour and is not in
question here. What is tested is the folder it writes into: the totals were
always rewritten, but a device dropped from the config since the last run used
to leave its per-device CSV behind, and the Results panel lists what it finds.
The user then saw a curve for an element that is no longer in the model, next
to a total that (correctly) no longer contains it.

Resonators are used so the test needs no external engine.
"""
import numpy as np

from wimba.assembly import Assignment
from wimba.output import clear_single_elements, read_totals
from wimba.run import compute_assignments

F = np.logspace(6, 9, 8)
GAMMA = 7000.0


def _resonator(name, rs, group="g"):
    """One lumped resonator mode, weight and length irrelevant to the point."""
    return Assignment(position=0.0, name=name, kind="device", method="resonator",
                      weighted=False, space_charge=False, beta_x=1.0, beta_y=1.0,
                      beta_source="explicit", allow_overlap=False, length=1.0,
                      geometry=None, group=group,
                      params={"modes": [{"plane": "long", "Rs": rs,
                                         "Q": 100.0, "fr": 1.0e8}]})


def _sources(out):
    """What the Results panel would list: every per-device CSV, plus the total."""
    se = out / "single_elements"
    return sorted(f"{p.parent.name}/{p.stem}" for p in se.rglob("*.csv"))


def test_removed_device_does_not_survive_a_recompute(tmp_path):
    out = tmp_path / "out"
    rows = [_resonator("KEEP", 1.0e3), _resonator("GONE", 5.0e3)]
    compute_assignments(rows, F, out, per_device=["KEEP", "GONE"], gamma=GAMMA)
    assert _sources(out) == ["g/GONE", "g/KEEP", "single_elements/total"]

    # the user removes one device from the config and presses Calculate again
    totals, _w, _s = compute_assignments(rows[:1], F, out,
                                         per_device=["KEEP"], gamma=GAMMA)

    assert _sources(out) == ["g/KEEP", "single_elements/total"]

    # and what is left agrees: the total is exactly the surviving device
    _f, kept = read_totals(out / "single_elements" / "g" / "KEEP.csv")
    _f, tot = read_totals(out / "single_elements" / "total.csv")
    assert np.allclose(tot["ZLong"], kept["ZLong"])
    assert np.allclose(tot["ZLong"], totals["ZLong"])


def test_renamed_group_leaves_no_empty_directory(tmp_path):
    """A group that loses all its devices should not stay in the tree."""
    out = tmp_path / "out"
    compute_assignments([_resonator("A", 1.0e3, group="old")], F, out,
                        per_device=["A"], gamma=GAMMA)
    compute_assignments([_resonator("A", 1.0e3, group="new")], F, out,
                        per_device=["A"], gamma=GAMMA)

    se = out / "single_elements"
    assert not (se / "old").exists()
    assert (se / "new" / "A.csv").is_file()


def test_clear_leaves_foreign_files_alone(tmp_path):
    """Only what WIMBA writes is removed; a user's own file is not ours to delete."""
    se = tmp_path / "out" / "single_elements"
    (se / "g").mkdir(parents=True)
    (se / "g" / "OLD.csv").write_text("freq,Re_ZLong,Im_ZLong\n")
    (se / "notes.md").write_text("mine\n")
    (se / "figure.png").write_bytes(b"\x89PNG")

    removed = clear_single_elements(tmp_path / "out")

    assert [p.name for p in removed] == ["OLD.csv"]
    assert (se / "notes.md").is_file() and (se / "figure.png").is_file()
    assert not (se / "g").exists()          # emptied by us, so it goes


def test_clear_on_a_folder_that_was_never_computed(tmp_path):
    assert clear_single_elements(tmp_path / "nothing_here") == []
