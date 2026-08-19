"""Log lines must reach the console widget on the GUI thread.

The library logs from inside the calculation, which runs in a worker thread.
The handler used to call `widget.appendHtml` there and then: a Qt widget
touched from another thread. It looked fine for a while and then the process
died with a segmentation fault inside the font engine, during a repaint in the
main thread - nowhere near the code that caused it.
"""
import logging
import threading

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QCoreApplication, QThread  # noqa: E402

from wimba.gui.app import QtLogHandler  # noqa: E402


class FakeWidget:
    """Records which thread actually did the appending."""

    def __init__(self):
        self.threads = []
        self.lines = []

    def appendHtml(self, html):
        self.threads.append(threading.get_ident())
        self.lines.append(html)


@pytest.fixture
def app():
    """Whatever application object the session already has, or a bare one.

    Another test may have built a QApplication before us; creating a second one
    is an error, and destroying theirs would break them.
    """
    existing = QCoreApplication.instance()
    yield existing or QCoreApplication([])


def drain(app, widget, timeout_ms=2000):
    """Run the event loop until the queued line arrives, or give up.

    A single processEvents() is not enough in a full test session: whether the
    posted event is dispatched on the first pass depends on what else is in the
    queue, so a one-shot check fails for reasons that have nothing to do with
    the thing being tested.
    """
    waited = 0
    while waited < timeout_ms:
        app.processEvents()
        if widget.lines:
            return True
        QThread.msleep(10)
        waited += 10
    return False


def test_a_line_logged_from_a_worker_is_appended_on_the_gui_thread(app):
    widget = FakeWidget()
    handler = QtLogHandler(widget)
    log = logging.getLogger("wimba.test.threading")
    log.setLevel(logging.INFO)
    log.addHandler(handler)
    try:
        main = threading.get_ident()

        class Worker(QThread):
            def run(self):
                log.info("from the worker")

        worker = Worker()
        worker.start()
        worker.wait(5000)

        # THE regression guard: the worker must never have touched the widget
        assert all(t == main for t in widget.threads), \
            "the console widget was written from the worker thread"

        assert drain(app, widget), "the line never arrived on the GUI thread"
        assert all(t == main for t in widget.threads)
        assert "from the worker" in widget.lines[-1]
    finally:
        log.removeHandler(handler)


def test_a_line_logged_on_the_gui_thread_still_arrives(app):
    widget = FakeWidget()
    handler = QtLogHandler(widget)
    log = logging.getLogger("wimba.test.threading.direct")
    log.setLevel(logging.INFO)
    log.addHandler(handler)
    try:
        log.warning("straight from the main thread")
        assert drain(app, widget)
        assert any("straight from the main thread" in l for l in widget.lines)
    finally:
        log.removeHandler(handler)


def test_the_level_colour_survives(app):
    widget = FakeWidget()
    handler = QtLogHandler(widget)
    log = logging.getLogger("wimba.test.threading.colour")
    log.setLevel(logging.DEBUG)
    log.addHandler(handler)
    try:
        log.error("red please")
        assert drain(app, widget)
        assert QtLogHandler.COLORS["ERROR"] in widget.lines[-1]
    finally:
        log.removeHandler(handler)
