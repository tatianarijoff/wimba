"""A machine opened outside a project shows what was already computed for it.

Projects reload every computed scenario when they are opened. A config or a
machine file opened on its own did not, so reopening the GUI on an example
computed the day before showed an empty Results panel although the files were
on disk. These tests pin down where WIMBA looks and that the GUI loads it.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from wimba.gui.model import existing_output_dirs
from wimba.output import write_totals
from wimba.run import default_output_dir

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def _totals(folder):
    f = np.logspace(6, 9, 6)
    write_totals(folder, f, {"ZLong": 1 / f + 0j})


# ------------------------------------------------------------ where to look
def test_default_output_dir_is_named_after_the_config(tmp_path):
    cfg = tmp_path / "ring_config.yaml"
    cfg.write_text("name: RING\n")
    assert default_output_dir(cfg) == tmp_path / "RING_output"
    cfg.write_text("devices: {}\n")                     # no name: the file stem
    assert default_output_dir(cfg) == tmp_path / "ring_config_output"


def test_assembly_config_finds_its_run_folder(tmp_path):
    cfg = tmp_path / "ring_config.yaml"
    cfg.write_text("name: RING\n")
    assert existing_output_dirs(cfg, "assembly") == []  # nothing computed yet
    _totals(tmp_path / "RING_output")
    assert existing_output_dirs(cfg, "assembly") == [tmp_path / "RING_output"]


def test_machine_file_finds_either_default(tmp_path):
    """The GUI build and `wimba build` name the folder differently; both are
    found, and a folder the file states itself comes first."""
    m = tmp_path / "Sub_input.yaml"
    m.write_text("name: Sub\n")
    (tmp_path / "Sub_output").mkdir()                   # wimba build
    assert existing_output_dirs(m, "machine") == [tmp_path / "Sub_output"]
    (tmp_path / "Sub_input_output").mkdir()             # the GUI build
    assert existing_output_dirs(m, "machine") == [tmp_path / "Sub_input_output",
                                                  tmp_path / "Sub_output"]
    m.write_text("name: Sub\noutput: results/here\n")
    (tmp_path / "results" / "here").mkdir(parents=True)
    assert existing_output_dirs(m, "machine")[0] == tmp_path / "results" / "here"


# ------------------------------------------------------------- in the GUI
def _gui(code, cwd):
    pytest.importorskip("PyQt6")
    head = ("import os; os.environ['QT_QPA_PLATFORM']='offscreen'\n"
            "from PyQt6.QtWidgets import QApplication\n"
            "import wimba.gui.app as A\n"
            "app = QApplication([])\n"
            "w = A.MainWindow()\n")
    out = subprocess.run([sys.executable, "-c", head + code], capture_output=True,
                         text=True, timeout=120, cwd=cwd)
    assert out.returncode == 0, out.stderr
    return out.stdout


def _chimera(tmp_path):
    """The Chimera injection config, copied without its project."""
    src = EXAMPLES / "Chimera_Project"
    for name in ("injection_config.yaml", "chimera.tfs"):
        shutil.copy(src / name, tmp_path / name)
    shutil.copytree(src / "data", tmp_path / "data")
    return tmp_path / "injection_config.yaml"


def test_open_config_shows_earlier_results(tmp_path):
    cfg = _chimera(tmp_path)
    _totals(tmp_path / "CHIMERA_injection_output")
    out = _gui(f"w._open_config_at({str(cfg)!r})\n"
               "print(sorted(w.results_model.sources))\n", tmp_path)
    assert "['Total']" in out


def test_open_config_old_layout_is_read_too(tmp_path):
    """A folder computed before the totals moved up still opens."""
    cfg = _chimera(tmp_path)
    se = tmp_path / "CHIMERA_injection_output" / "single_elements"
    se.mkdir(parents=True)
    f = np.logspace(6, 9, 4)
    (se / "total.csv").write_text("freq,Re_ZLong,Im_ZLong\n" +
                                  "".join(f"{x:.8e},1.0,0.0\n" for x in f))
    out = _gui(f"w._open_config_at({str(cfg)!r})\n"
               "print(sorted(w.results_model.sources))\n", tmp_path)
    assert "['Total']" in out


def test_open_config_without_results_leaves_the_panel_empty(tmp_path):
    cfg = _chimera(tmp_path)
    out = _gui(f"w._open_config_at({str(cfg)!r})\n"
               "print('N', len(w.results_model.sources))\n", tmp_path)
    assert "N 0" in out
