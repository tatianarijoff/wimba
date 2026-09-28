"""Parametric projects: one layer parameter, several values, nothing else.

wimba/parametric.py generates the cases from one base config; these tests pin
what a case may and may not differ in, and what is refused before anything is
written.
"""
import shutil
from pathlib import Path

import pytest
import yaml

from wimba.assembly import load_assembly
from wimba.gui.model import GProject, MAX_SCENARIOS
from wimba.parametric import (Sweep, SweepError, case_label, create_project,
                              parse_values, problems)

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
BASE = EXAMPLES / "Chimera_Project" / "injection_config.yaml"


def _layer(cfg_path, name, i=0):
    cfg = yaml.safe_load(Path(cfg_path).read_text())
    spec = next(s for s in cfg["devices"].values() if s.get("name") == name)
    return spec["layers"][i]


def _cfg(project, sc):
    return Path(project.dir) / sc.config


# ------------------------------------------------------------------ the sweep
@pytest.mark.parametrize("bad, match", [
    ({"elements": [], "parameter": "layers[0].thickness", "values": [1e-3]}, "elements"),
    ({"elements": ["A"], "parameter": "layers[0].colour", "values": [1]}, "not one a sweep"),
    ({"elements": ["A"], "parameter": "thickness", "values": [1e-3]}, "not one a sweep"),
    ({"elements": ["A"], "parameter": "layers[0].thickness", "values": []}, "values"),
    ({"elements": ["A"], "parameter": "layers[0].thickness", "values": [1e-3, 1e-3]}, "twice"),
    ({"elements": ["A"], "parameter": "layers[0].thickness", "values": [-1]}, "greater than zero"),
    ({"elements": ["A"], "parameter": "layers[0].thickness", "values": ["inf"]}, "infinite"),
    ({"elements": ["A"], "parameter": "layers[0].sigma", "values": ["abc"]}, "not a number"),
    ({"elements": ["A"], "parameter": "layers[0].material", "values": [3]}, "names"),
])
def test_a_sweep_is_checked_before_anything_is_written(bad, match):
    with pytest.raises(SweepError, match=match):
        Sweep.from_dict(bad)


def test_no_more_cases_than_a_project_holds():
    values = [1e-3 * (i + 1) for i in range(MAX_SCENARIOS + 1)]
    with pytest.raises(SweepError, match="at most"):
        Sweep.from_dict({"elements": ["A"], "parameter": "layers[0].thickness",
                         "values": values})


def test_labels_are_what_the_legend_should_say():
    t = Sweep.from_dict({"elements": ["A"], "parameter": "layers[0].thickness",
                         "values": [1e-5, 2e-4, 1e-3, 5e-3]})
    assert [case_label(t, v) for v in t.values] == ["t = 10 \u00b5m", "t = 200 \u00b5m",
                                                    "t = 1 mm", "t = 5 mm"]
    s = Sweep.from_dict({"elements": ["A"], "parameter": "layers[1].sigma",
                         "values": [1e5, 2.5e6]})
    assert [case_label(s, v) for v in s.values] == ["\u03c3 = 1e5 S/m",
                                                    "\u03c3 = 2.5e6 S/m"]
    assert parse_values("thickness", "1e-5, 5e-5 2e-4") == [1e-5, 5e-5, 2e-4]


# ------------------------------------------------------------ generating cases
def test_a_material_sweep_writes_numbers_and_keeps_the_name_as_label(tmp_path):
    p = create_project(BASE, tmp_path / "p", {
        "elements": ["COLL.H", "COLL.V"], "parameter": "layers[0].material",
        "values": ["copper", "graphite"]})
    assert p.parametric and p.labels() == ["copper", "graphite"]
    for sc, sigma in zip(p.scenarios, (5.9e7, 1.0e5)):
        for name in ("COLL.H", "COLL.V"):
            lay = _layer(_cfg(p, sc), name)
            assert "material" not in lay and lay["label"] == sc.label
            assert lay["sigma"] == pytest.approx(sigma)
            assert lay["thickness"] in (0.025, 0.03)          # untouched
    assert problems(p) == []


def test_a_thickness_sweep_touches_only_the_listed_element(tmp_path):
    p = create_project(BASE, tmp_path / "p", {
        "elements": ["COLL.H"], "parameter": "layers[0].thickness",
        "values": [1e-5, 1e-3]})
    for sc, t in zip(p.scenarios, (1e-5, 1e-3)):
        assert _layer(_cfg(p, sc), "COLL.H")["thickness"] == pytest.approx(t)
        assert _layer(_cfg(p, sc), "COLL.H")["material"] == "chimeranium"
        assert _layer(_cfg(p, sc), "COLL.V") == _layer(BASE, "COLL.V")


def test_a_sigma_sweep_drops_the_name_but_keeps_the_other_parameters(tmp_path):
    p = create_project(BASE, tmp_path / "p", {
        "elements": ["COLL.H"], "parameter": "layers[0].sigma", "values": [1e5]})
    lay = _layer(_cfg(p, p.scenarios[0]), "COLL.H")
    assert "material" not in lay and "label" not in lay
    assert lay["sigma"] == pytest.approx(1e5) and lay["tau"] == 0.0


def test_the_project_file_records_the_sweep_and_reopens(tmp_path):
    p = create_project(BASE, tmp_path / "p", {
        "elements": ["COLL.H"], "parameter": "layers[0].thickness", "values": [1e-3]},
        name="study")
    data = yaml.safe_load((tmp_path / "p" / "project.yaml").read_text())
    assert data["kind"] == "parametric"
    assert data["sweep"]["parameter"] == "layers[0].thickness"
    again = GProject.from_dict(data, tmp_path / "p")
    assert again.parametric and again.sweep == p.sweep
    assert again.scenarios[0].beam.gamma == pytest.approx(2.278946709965436)


@pytest.mark.parametrize("sweep, match", [
    ({"elements": ["COLL.X"], "parameter": "layers[0].thickness", "values": [1e-3]},
     "no element named 'COLL.X'"),
    ({"elements": ["COLL.H"], "parameter": "layers[5].thickness", "values": [1e-3]},
     "does not exist"),
    ({"elements": ["COLL.H"], "parameter": "layers[2].sigma", "values": [1e6]},
     "no calculation reads"),
    ({"elements": ["COLL.H"], "parameter": "layers[0].material", "values": ["unobtainium"]},
     "unobtainium"),
])
def test_what_cannot_be_applied_is_refused_with_nothing_written(tmp_path, sweep, match):
    with pytest.raises(ValueError, match=match):
        create_project(BASE, tmp_path / "p", sweep)
    assert not (tmp_path / "p" / "project.yaml").exists()


def test_a_base_without_beam_is_refused(tmp_path):
    cfg = yaml.safe_load(BASE.read_text())
    cfg.pop("beam")
    base = tmp_path / "base.yaml"
    base.write_text(yaml.safe_dump(cfg))
    with pytest.raises(SweepError, match="no beam"):
        create_project(base, tmp_path / "p", {
            "elements": ["COLL.H"], "parameter": "layers[0].thickness", "values": [1e-3]})


def test_an_existing_project_folder_is_refused(tmp_path):
    spec = {"elements": ["COLL.H"], "parameter": "layers[0].thickness", "values": [1e-3]}
    create_project(BASE, tmp_path / "p", spec)
    with pytest.raises(SweepError, match="already holds a project"):
        create_project(BASE, tmp_path / "p", spec)


# ------------------------------------------------------------- staying clean
def test_problems_names_a_case_edited_beyond_the_sweep(tmp_path):
    p = create_project(BASE, tmp_path / "p", {
        "elements": ["COLL.H"], "parameter": "layers[0].thickness",
        "values": [1e-5, 1e-3]})
    path = _cfg(p, p.scenarios[1])
    path.write_text(path.read_text().replace("position: 45.6", "position: 46.0"))
    lines = problems(p)
    assert len(lines) == 1 and "t = 1 mm" in lines[0] and "devices" in lines[0]


# ----------------------------------------------------- the shipped examples
@pytest.mark.parametrize("folder", ["ChimeraMaterial_Project", "ChimeraThickness_Project"])
def test_the_example_projects_are_clean_and_load(folder, tmp_path):
    here = tmp_path / "examples"
    for name in ("Chimera_Project", folder):
        shutil.copytree(EXAMPLES / name, here / name)
    d = here / folder
    p = GProject.from_dict(yaml.safe_load((d / "project.yaml").read_text()), d)
    assert p.parametric and len(p.scenarios) == len(p.sweep["values"])
    assert problems(p) == []
    for sc in p.scenarios:
        assert (d / sc.config).read_text().count("../Chimera_Project/") >= 3
        assert len(load_assembly(d / sc.config).rows) > 100


# ------------------------------------------------------------------ the GUI
def _gui(code, cwd):
    pytest.importorskip("PyQt6")
    import subprocess
    import sys
    head = ("import os; os.environ['QT_QPA_PLATFORM']='offscreen'\n"
            "from PyQt6.QtWidgets import QApplication\n"
            "app = QApplication([])\n")
    out = subprocess.run([sys.executable, "-c", head + code], capture_output=True,
                         text=True, timeout=120, cwd=cwd)
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_the_dialog_enables_ok_only_for_a_sweep_it_can_write(tmp_path):
    out = _gui(f"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialogButtonBox
from wimba.gui.sweep_dialog import SweepDialog
d = SweepDialog()
ok = lambda: d.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
print('NOBASE', ok(), d.elements.isEnabled(), 'Start by choosing' in d.preview.text())
d.set_base({str(BASE)!r})
print('BASE', d.elements.isEnabled(), d.elements.count(), d.name.text())
print('START', ok())
d.elements.item(0).setCheckState(Qt.CheckState.Checked)
d.field.setCurrentText('thickness')
d.numbers.setText('1e-5, 1e-3')
print('NOFOLDER', ok())
d.folder.setText({str(tmp_path / 'new')!r})
print('READY', ok(), d.preview.text())
d.layer.setValue(2)
print('BOUNDARY', ok())
print('SWEEP', d.sweep()['parameter'])
""", tmp_path)
    assert "NOBASE False False True" in out           # nothing to do before a base
    assert "BASE True 2 CHIMERA_injection sweep" in out
    assert "START False" in out and "NOFOLDER False" in out
    assert "READY True 2 case(s): t = 10 \u00b5m, t = 1 mm" in out
    assert "BOUNDARY False" in out


def test_the_window_opens_a_parametric_project_and_refuses_duplicates(tmp_path):
    p = create_project(BASE, tmp_path / "p", {
        "elements": ["COLL.H"], "parameter": "layers[0].thickness",
        "values": [1e-5, 1e-3]})
    out = _gui(f"""
import wimba.gui.app as A
from PyQt6.QtWidgets import QMessageBox
seen = []
QMessageBox.information = staticmethod(lambda *a, **k: seen.append(a[2]))
w = A.MainWindow()
w._open_project_at(__import__('pathlib').Path({str(p.dir)!r}))
print('PARAMETRIC', w.project.parametric, len(w.project.scenarios))
w._duplicate_scenario()
print('REFUSED', 'generated from its sweep' in seen[-1], len(w.project.scenarios))
""", tmp_path)
    assert "PARAMETRIC True 2" in out and "REFUSED True 2" in out
