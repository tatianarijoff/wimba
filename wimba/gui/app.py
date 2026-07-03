"""WIMBA desktop GUI — Phase 1 skeleton (+ theming and branding).

A QMainWindow shell with the panels the spec asks for, laid out as dockable
widgets. This phase wires the *frame*: menus, dockable/floating/tabbable panels,
the View menu that shows/hides them, layout save / restore / reset, a Dark/Light
theme switch persisted across runs, and the WIMBA logo. Data binding and
calculation come in later phases.

Run it with:  python -m wimba.gui
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QAction, QActionGroup, QIcon, QKeySequence, QPixmap
from PyQt6.QtWidgets import (QApplication, QDockWidget, QHBoxLayout, QLabel,
                             QMainWindow, QMessageBox, QTabBar, QTabWidget,
                             QVBoxLayout, QWidget)

from .theme import THEMES, build_style

ORG = "ImpedanCEI"
APP = "WIMBA"

ASSETS = Path(__file__).parent / "assets"


def asset(name: str) -> str:
    return str(ASSETS / name)


# panels that live as docks:  id -> (title, default area)
DOCKS = {
    "machine":  ("Machine Explorer", Qt.DockWidgetArea.LeftDockWidgetArea),
    "optics":   ("Optics",           Qt.DockWidgetArea.LeftDockWidgetArea),
    "inspector":("Inspector",        Qt.DockWidgetArea.RightDockWidgetArea),
    "jobs":     ("Jobs",             Qt.DockWidgetArea.BottomDockWidgetArea),
    "console":  ("Console",          Qt.DockWidgetArea.BottomDockWidgetArea),
    "problems": ("Problems",         Qt.DockWidgetArea.BottomDockWidgetArea),
    "outputs":  ("Output Browser",   Qt.DockWidgetArea.BottomDockWidgetArea),
}


def empty_state(icon: str, title: str, text: str) -> QWidget:
    """A centered empty-state placeholder used until a panel has content."""
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.addStretch(1)
    for oid, txt, wrap in (("EmptyIcon", icon, False),
                           ("EmptyTitle", title, False),
                           ("EmptyText", text, True)):
        lab = QLabel(txt)
        lab.setObjectName(oid)
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lab.setWordWrap(wrap)
        lay.addWidget(lab)
    lay.addStretch(2)
    return w


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WIMBA — Wake & Impedance Model Builder for Accelerators")
        self.setWindowIcon(QIcon(asset("wimba_logo_small.png")))
        self.resize(1360, 860)
        self.setDockNestingEnabled(True)
        self.settings = QSettings(ORG, APP)
        self.docks: dict[str, QDockWidget] = {}
        self._theme_actions: dict[str, QAction] = {}

        self._build_central()
        self._build_docks()
        self._build_menus()
        self._build_brand()
        self._build_status()

        # theme first (from saved preference), then capture the pristine layout
        self._apply_theme(self.settings.value("theme", "dark"))
        self._default_state = self.saveState()
        self._default_geometry = self.saveGeometry()
        self._restore_layout()

    # ---- central editor area: Plot Workspace + Results Table (+ element tabs) ----
    def _build_central(self):
        self.center = QTabWidget()
        self.center.setMovable(True)
        self.center.setDocumentMode(True)
        self.center.setTabsClosable(True)
        self.center.tabCloseRequested.connect(self._close_center_tab)

        self.plot_panel = empty_state("\u223f", "No curves plotted",
            "Drag a result here from an element's Outputs, the basket, or the table.")
        self.results_panel = empty_state("\u25a6", "No datasets in table",
            "Drag result chips here to compare elements and methods side by side.")
        self.center.addTab(self.plot_panel, "Plot Workspace")
        self.center.addTab(self.results_panel, "Results Table")
        for i in range(2):                  # Plot/Results are permanent
            self.center.tabBar().setTabButton(i, QTabBar.ButtonPosition.RightSide, None)
        self.setCentralWidget(self.center)

    def _close_center_tab(self, index: int):
        if index >= 2:
            self.center.removeTab(index)

    # ---- dock panels ----
    def _build_docks(self):
        placeholders = {
            "machine": ("\u25c8", "Machine is empty",
                        "File \u2192 Load Machine, or start a new one."),
            "optics":  ("\u25cb", "No optics yet",
                        "Load a machine, then load or enter the optics."),
            "inspector":("\u24d8", "Nothing selected",
                        "Select a node to see its properties and provenance."),
            "jobs":    ("\u29d7", "No jobs yet",
                        "Calculations you launch appear here with live status."),
            "console": ("\u203a_", "Console is quiet",
                        "Backend commands, files read, warnings and errors stream here."),
            "problems":("\u2713", "No problems detected",
                        "Machine, optics and quantity configuration look consistent."),
            "outputs": ("\u25a2", "No output yet",
                        "Outputs appear once a machine is loaded and computed."),
        }
        for pid, (title, area) in DOCKS.items():
            dock = QDockWidget(title, self)
            dock.setObjectName("dock_" + pid)      # required for saveState()
            dock.setFeatures(
                QDockWidget.DockWidgetFeature.DockWidgetMovable |
                QDockWidget.DockWidgetFeature.DockWidgetFloatable |
                QDockWidget.DockWidgetFeature.DockWidgetClosable)
            ic, ti, tx = placeholders[pid]
            dock.setWidget(empty_state(ic, ti, tx))
            self.addDockWidget(area, dock)
            self.docks[pid] = dock

        self.splitDockWidget(self.docks["machine"], self.docks["optics"], Qt.Orientation.Vertical)
        self.tabifyDockWidget(self.docks["jobs"], self.docks["console"])
        self.tabifyDockWidget(self.docks["console"], self.docks["problems"])
        self.tabifyDockWidget(self.docks["problems"], self.docks["outputs"])
        self.docks["jobs"].raise_()

    # ---- brand (logo in the menu-bar corner) ----
    def _build_brand(self):
        brand = QWidget()
        h = QHBoxLayout(brand)
        h.setContentsMargins(6, 0, 10, 0)
        h.setSpacing(8)
        logo = QLabel()
        pm = QPixmap(asset("wimba_logo_small.png"))
        if not pm.isNull():
            logo.setPixmap(pm.scaledToHeight(20, Qt.TransformationMode.SmoothTransformation))
        name = QLabel("WIMBA")
        name.setObjectName("Brand")
        h.addWidget(logo)
        h.addWidget(name)
        self.menuBar().setCornerWidget(brand, Qt.Corner.TopRightCorner)

    # ---- menus ----
    def _build_menus(self):
        mb = self.menuBar()

        m = mb.addMenu("&File")
        self._act(m, "Load Machine\u2026", self._todo, QKeySequence.StandardKey.Open)
        self._act(m, "New Machine", self._todo, QKeySequence.StandardKey.New)
        m.addSeparator()
        self._act(m, "Save Project", self._todo, QKeySequence.StandardKey.Save)
        self._act(m, "Save Project As\u2026", self._todo, QKeySequence.StandardKey.SaveAs)
        m.addSeparator()
        self._act(m, "Export Results\u2026", self._todo)
        m.addSeparator()
        self._act(m, "Quit", self.close, QKeySequence.StandardKey.Quit)

        m = mb.addMenu("&View")
        for pid in DOCKS:
            act = self.docks[pid].toggleViewAction()
            act.setText(self.docks[pid].windowTitle())
            m.addAction(act)
        m.addSeparator()
        self._act(m, "Show Plot Workspace", lambda: self.center.setCurrentWidget(self.plot_panel))
        self._act(m, "Show Results Table", lambda: self.center.setCurrentWidget(self.results_panel))
        m.addSeparator()
        theme_menu = m.addMenu("Theme")
        group = QActionGroup(self)
        group.setExclusive(True)
        for name, label in (("dark", "Dark"), ("light", "Light")):
            a = QAction(label, self, checkable=True)
            a.triggered.connect(lambda _=False, n=name: self._apply_theme(n))
            group.addAction(a)
            theme_menu.addAction(a)
            self._theme_actions[name] = a
        m.addSeparator()
        self._act(m, "Save Layout", self._save_layout)
        self._act(m, "Load Saved Layout", self._restore_layout)
        self._act(m, "Reset Layout", self._reset_layout)
        self._act(m, "Restore Default Layout", self._restore_default_layout)

        m = mb.addMenu("&Machine")
        for label in ("Add Group", "Add Element", "Rename Selected",
                      "Duplicate Selected", "Delete Selected"):
            self._act(m, label, self._todo)

        m = mb.addMenu("&Optics")
        self._act(m, "Load Optics\u2026", self._todo)
        self._act(m, "Clear Optics", self._todo)

        m = mb.addMenu("&Calculate")
        self._act(m, "Selected Element", self._todo, "F5")
        self._act(m, "Selected Group", self._todo)
        self._act(m, "Whole Machine", self._todo)

        m = mb.addMenu("&Results")
        for label in ("Add Selection to Comparison", "Send Basket to Plot",
                      "Send Basket to Table", "Export Results as CSV\u2026",
                      "Clear Comparison Basket"):
            self._act(m, label, self._todo)

        m = mb.addMenu("&Help")
        self._act(m, "About WIMBA", self._about)
        self._act(m, "Keyboard Shortcuts", self._todo)

    def _act(self, menu, text, slot, shortcut=None):
        act = QAction(text, self)
        if shortcut is not None:
            act.setShortcut(shortcut)
        act.triggered.connect(slot)
        menu.addAction(act)
        return act

    # ---- status bar ----
    def _build_status(self):
        sb = self.statusBar()
        self.lbl_machine = QLabel("No machine")
        self.lbl_sel = QLabel("nothing selected")
        self.lbl_out = QLabel("output \u2014")
        sb.addWidget(self.lbl_machine)
        sb.addWidget(QLabel("  \u2502  "))
        sb.addWidget(self.lbl_sel)
        sb.addPermanentWidget(self.lbl_out)
        sb.showMessage("Ready \u2014 File \u2192 Load Machine to begin", 4000)

    # ---- theme ----
    def _apply_theme(self, name):
        if name not in THEMES:
            name = "dark"
        self.theme = name
        QApplication.instance().setStyleSheet(build_style(THEMES[name]))
        self.settings.setValue("theme", name)
        if name in self._theme_actions:
            self._theme_actions[name].setChecked(True)

    # ---- layout persistence ----
    def _save_layout(self):
        self.settings.setValue("state", self.saveState())
        self.settings.setValue("geometry", self.saveGeometry())
        self.statusBar().showMessage("Layout saved", 2000)

    def _restore_layout(self):
        geo = self.settings.value("geometry")
        state = self.settings.value("state")
        if geo is not None:
            self.restoreGeometry(geo)
        if state is not None:
            self.restoreState(state)
            self.statusBar().showMessage("Saved layout restored", 2000)

    def _restore_default_layout(self):
        self.restoreState(self._default_state)
        self.statusBar().showMessage("Default layout restored", 2000)

    def _reset_layout(self):
        self.settings.remove("state")
        self.settings.remove("geometry")
        self.restoreGeometry(self._default_geometry)
        self.restoreState(self._default_state)
        self.statusBar().showMessage("Layout reset to default", 2000)

    # ---- about ----
    def _about(self):
        box = QMessageBox(self)
        box.setWindowTitle("About WIMBA")
        pm = QPixmap(asset("wimba_logo_small.png"))
        if not pm.isNull():
            box.setIconPixmap(pm.scaledToWidth(132, Qt.TransformationMode.SmoothTransformation))
        box.setText("<b>WIMBA</b><br>Wake &amp; Impedance Model Builder for Accelerators")
        box.setInformativeText("Coordinates impedance and wakefield results from "
                               "pytlwall, IW2D, CST and analytic resonators.")
        box.exec()

    # ---- placeholder for actions wired in later phases ----
    def _todo(self):
        self.statusBar().showMessage("Not wired yet \u2014 coming in the next phase", 2500)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP)
    app.setOrganizationName(ORG)
    app.setWindowIcon(QIcon(asset("wimba_logo_small.png")))
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
