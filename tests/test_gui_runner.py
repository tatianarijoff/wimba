"""Smoke test for the GUI worker module: it imports and exposes RunWorker with
its signals. Widget interaction is verified manually (needs a display)."""
import pytest


def test_run_worker_api():
    pytest.importorskip("PyQt6")
    import wimba.gui.runner as r
    assert hasattr(r, "RunWorker")
    for sig in ("log", "done", "failed"):
        assert hasattr(r.RunWorker, sig)


def test_app_imports():
    pytest.importorskip("PyQt6")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import wimba.gui.app as app
    assert hasattr(app, "MainWindow")


def test_mainwindow_instantiates():
    """Actually construct the MainWindow (offscreen, in a subprocess so Qt
    teardown cannot abort pytest). Catches wiring bugs that a bare import
    misses, e.g. theme hooks calling missing panel methods."""
    import subprocess, sys
    pytest.importorskip("PyQt6")
    code = (
        "import os; os.environ['QT_QPA_PLATFORM']='offscreen'\n"
        "from PyQt6.QtWidgets import QApplication\n"
        "import wimba.gui.app as A\n"
        "app = QApplication([])\n"
        "w = A.MainWindow()\n"
        "print('OK')\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert "OK" in out.stdout
