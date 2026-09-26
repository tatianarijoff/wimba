"""Calculate on a machine outside a project reads its file, so it asks first.

A machine built in the window has no file yet: Calculate used to open the Open
Config dialog, which looks like a bug. A machine whose panels hold edits the
file does not have was computed without them, silently. Now the first is
offered Save Machine As, the second is asked whether to save. The questions go
through MainWindow._ask, which these tests answer instead of a person.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"

HEAD = """
import os; os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
from PyQt6.QtWidgets import QApplication
import wimba.gui.app as A
from wimba.gui.model import new_machine
app = QApplication([])
w = A.MainWindow()
asked = []
def answer(key):
    def _ask(title, text, choices, default):
        asked.append(text.split(chr(10))[0])
        return key
    return _ask
"""


def _gui(code, cwd):
    pytest.importorskip("PyQt6")
    out = subprocess.run([sys.executable, "-c", HEAD + code], capture_output=True,
                         text=True, timeout=120, cwd=cwd)
    assert out.returncode == 0, out.stderr
    return out.stdout


def _chimera(tmp_path):
    src = EXAMPLES / "Chimera_Project"
    for name in ("injection_config.yaml", "chimera.tfs"):
        shutil.copy(src / name, tmp_path / name)
    shutil.copytree(src / "data", tmp_path / "data")
    return tmp_path / "injection_config.yaml"


# ------------------------------------------------ a machine with no file yet
def test_unsaved_machine_is_offered_save_as_not_open_config(tmp_path):
    out = _gui("""
w.machine = new_machine('Ring')
print('blocker', w._calc_blocker())
w._ask = answer('cancel')
opened = []
w._open_config = lambda: opened.append(1)        # the old, wrong door
w._calc_machine()
print('asked', asked)
print('open_config', len(opened), 'jobs', w._dock_list('jobs').count())
""", tmp_path)
    assert "blocker unsaved" in out
    assert "has not been saved yet" in out
    assert "open_config 0 jobs 0" in out             # cancelled: nothing started


def test_saving_from_the_question_clears_the_way(tmp_path):
    dest = tmp_path / "ring.yaml"
    out = _gui(f"""
w.machine = new_machine('Ring')
w._ask = answer('save')
w._save_machine_as = lambda: w._dump_machine_to(Path({str(dest)!r}))
print('ready', w._ready_to_calculate())
print('path', w.machine_path)
""", tmp_path)
    assert "ready True" in out
    assert str(dest) in out
    assert dest.is_file()


def test_leaving_the_save_dialog_does_not_calculate(tmp_path):
    out = _gui("""
w.machine = new_machine('Ring')
w._ask = answer('save')
w._save_machine_as = lambda: None                # the file dialog was cancelled
print('ready', w._ready_to_calculate())
""", tmp_path)
    assert "ready False" in out


# --------------------------------------------- a file, and edits it lacks
def test_opening_a_config_leaves_nothing_pending(tmp_path):
    """Building the panels must not count as an edit, or every Calculate
    right after opening would ask about edits nobody made."""
    cfg = _chimera(tmp_path)
    out = _gui(f"""
w._open_config_at({str(cfg)!r})
el = next(e for _g, e in w.machine.all_elements())
w._open_element(el)
print('dirty', w._config_dirty, 'blocker', w._calc_blocker())
""", tmp_path)
    assert "dirty False blocker None" in out


def test_panel_edits_outside_a_project_are_noticed(tmp_path):
    cfg = _chimera(tmp_path)
    out = _gui(f"""
w._open_config_at({str(cfg)!r})
w._after_edit()                                   # what every panel edit calls
print('blocker', w._calc_blocker())
w._ask = answer('cancel'); print('cancel', w._ready_to_calculate())
w._ask = answer('go');     print('go', w._ready_to_calculate(), w._config_dirty)
w._ask = answer('save');   print('save', w._ready_to_calculate(), w._config_dirty)
print('asked', asked[0])
""", tmp_path)
    assert "blocker dirty" in out
    assert "cancel False" in out
    assert "go True True" in out                      # computed as on disk, still pending
    assert "save True False" in out                   # written, then computed
    assert "not been written to injection_config.yaml" in out


def test_inside_a_project_nothing_is_asked(tmp_path):
    out = _gui(f"""
w._open_project_at(Path({str(EXAMPLES / 'Chimera_Project')!r}))
w._after_edit()
print('blocker', w._calc_blocker())
""", tmp_path)
    assert "blocker None" in out
