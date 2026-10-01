"""A machine built in the window saves the first time it is asked to.

Machine > Add Element used to create an element with a length and nothing else,
so the Save Machine As that Calculate offers refused it ("no radius in its
geometry") and the save appeared to do nothing. And Close Machine forgot the
file of a machine opened with Load Machine, so the NEXT machine looked saved.
"""
import subprocess
import sys

import pytest
import yaml

from wimba.gui.model import (GGroup, machine_config, machine_config_text, new_chamber,
                             new_machine)

HEAD = """
import os; os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox
import wimba.gui.app as A
app = QApplication([])
w = A.MainWindow()
QInputDialog.getText = staticmethod(lambda *a, **k: (k.get('text', 'X'), True))
QMessageBox.warning = staticmethod(lambda *a, **k: print('WARN', a[2]))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
"""


def _gui(code, cwd):
    pytest.importorskip("PyQt6")
    out = subprocess.run([sys.executable, "-c", HEAD + code], capture_output=True,
                         text=True, timeout=120, cwd=cwd)
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_new_chamber_is_complete_and_serialises():
    el = new_chamber("PIPE")
    assert el.geometry["radius"] == 0.02 and el.geometry["shape"] == "CIRCULAR"
    assert len(el.layers) == 1
    assert el.layers[0]["boundary"] is True and el.layers[0]["thickness"] == "inf"
    gm = new_machine("Ring")
    gm.groups = [GGroup("chambers", [el])]
    machine_config(gm)                      # must not raise


def test_header_names_the_file_not_the_machine():
    gm = new_machine("Ring")
    text = machine_config_text(machine_config(gm), "my_ring.yaml")
    assert "wimba build my_ring.yaml" in text
    assert yaml.safe_load(text)["name"] == "Ring"


def test_calculate_offers_save_as_and_the_file_is_written(tmp_path):
    dest = tmp_path / "my_ring"             # typed without the extension
    out = _gui(f"""
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ({str(dest)!r}, 'YAML'))
w._new_machine(); w._add_element()
w._ask = lambda *a: 'save'
print('ready', w._ready_to_calculate())
print('path', w.machine_path)
""", tmp_path)
    assert "WARN" not in out
    assert "ready True" in out
    saved = tmp_path / "my_ring.yaml"
    assert saved.is_file() and f"path {saved}" in out
    data = yaml.safe_load(saved.read_text())
    (el,) = next(iter(data["groups"].values()))
    assert el["radius_m"] == 0.02


def test_close_machine_forgets_the_loaded_file(tmp_path):
    first = tmp_path / "first.yaml"
    gm = new_machine("First")
    first.write_text(machine_config_text(machine_config(gm), first.name))
    out = _gui(f"""
w.machine_path = {str(first)!r}
w._close_machine(confirm=False)
w._new_machine()
print('blocker', w._calc_blocker(), 'source', w._source_config())
""", tmp_path)
    assert "blocker unsaved source None" in out
