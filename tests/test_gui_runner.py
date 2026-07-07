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
