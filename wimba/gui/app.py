"""WIMBA desktop GUI — Phase 1 skeleton (+ theming and branding).

A QMainWindow shell with the panels the spec asks for, laid out as dockable
widgets. This phase wires the *frame*: menus, dockable/floating/tabbable panels,
the View menu that shows/hides them, layout save / restore / reset, a Dark/Light
theme switch persisted across runs, and the WIMBA logo. Data binding and
calculation come in later phases.

Run it with:  python -m wimba.gui
"""
from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings, Qt, pyqtSignal
from PyQt6.QtGui import (QAction, QActionGroup, QColor, QIcon, QKeySequence,
                         QPainter, QPixmap)
from PyQt6.QtWidgets import (QApplication, QDockWidget, QFileDialog, QHBoxLayout,
                             QInputDialog, QLabel, QListWidget, QListWidgetItem,
                             QMainWindow, QMessageBox, QPlainTextEdit, QScrollArea,
                             QTabBar, QTabWidget, QVBoxLayout, QWidget)

from .theme import THEMES, build_style
from .model import (GGroup, GProject, GScenario, freeze_config, from_config,
                    from_machine_file, grid_of, new_element, new_machine,
                    slugify, write_config)
from .panels import (BeamPanel, ElementPanel, InspectorPanel, MachineTree,
                     OpticsPanel, ScenarioPanel)
from .runner import BuildWorker, RunWorker
from .results import (PlotWorkspace, ResultsModel, ResultsTablePanel,
                      ResultsTree)
from ..logutil import configure, get_logger, set_level

ORG = "ImpedanCEI"
APP = "WIMBA"

ASSETS = Path(__file__).parent / "assets"


def asset(name: str) -> str:
    return str(ASSETS / name)


# panels that live as docks:  id -> (title, default area)
DOCKS = {
    "scenarios":("Scenarios",        Qt.DockWidgetArea.LeftDockWidgetArea),
    "machine":  ("Machine Explorer", Qt.DockWidgetArea.LeftDockWidgetArea),
    "optics":   ("Optics",           Qt.DockWidgetArea.LeftDockWidgetArea),
    "beam":     ("Beam",             Qt.DockWidgetArea.LeftDockWidgetArea),
    "results":  ("Results",          Qt.DockWidgetArea.RightDockWidgetArea),
    "inspector":("Inspector",        Qt.DockWidgetArea.RightDockWidgetArea),
    "jobs":     ("Jobs",             Qt.DockWidgetArea.BottomDockWidgetArea),
    "console":  ("Console",          Qt.DockWidgetArea.BottomDockWidgetArea),
    "problems": ("Problems",         Qt.DockWidgetArea.BottomDockWidgetArea),
}
# The bottom row answers three different questions: what is happening now
# (Console), what has been launched in this session (Jobs), and what not to
# trust (Problems). The Console is cleared at the start of every calculation,
# which is why Jobs is not redundant with it.


def empty_state(icon: str, title: str, text: str) -> QWidget:
    """A centered empty-state placeholder used until a panel has content."""
    w = QWidget()
    w.setStyleSheet("background: transparent;")
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


class _LogBridge(QObject):
    """Carries a formatted line from whatever thread logged it to the GUI one.

    A Qt widget may only be touched from the thread that owns it. The library
    logs from inside the calculation, which runs in a worker thread, so writing
    straight into the console widget was a cross-thread GUI call: it usually
    appeared to work, then corrupted the text layout and the process died in
    the font engine during a later repaint - in the main thread, far from the
    line that caused it.

    Emitting a signal is thread-safe, and because this object lives in the GUI
    thread Qt delivers it there, queued.
    """

    message = pyqtSignal(str)

    def __init__(self, widget):
        super().__init__()
        self._widget = widget
        self.message.connect(self._append)

    def _append(self, html):
        self._widget.appendHtml(html)


class QtLogHandler(logging.Handler):
    """Streams log records into a QPlainTextEdit, coloured by level."""

    COLORS = {"CRITICAL": "#ff5c5c", "ERROR": "#ff7b72", "WARNING": "#e0a458",
              "INFO": "#8ab4f8", "DEBUG": "#7d8590"}

    def __init__(self, widget):
        super().__init__()
        self.widget = widget
        self.bridge = _LogBridge(widget)
        self.setFormatter(logging.Formatter("%(levelname)-8s %(name)s: %(message)s"))

    def emit(self, record):
        msg = self.format(record).replace("<", "&lt;").replace(">", "&gt;")
        color = self.COLORS.get(record.levelname, "#c9d1d9")
        # never touch the widget here: this runs in whichever thread logged
        self.bridge.message.emit(f'<span style="color:{color}">{msg}</span>')


class Watermark(QWidget):
    """A panel that paints the WIMBA logo faintly behind its content."""

    def __init__(self, pixmap):
        super().__init__()
        self._pm = pixmap
        self._bg = QColor("#151b23")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

    def set_bg(self, color):
        self._bg = QColor(color)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg)
        if not self._pm.isNull():
            side = int(min(self.width(), self.height()) * 0.55)
            if side > 0:
                pm = self._pm.scaled(side, side, Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
                p.setOpacity(0.06)
                p.drawPixmap((self.width() - pm.width()) // 2,
                             (self.height() - pm.height()) // 2, pm)
        p.end()


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
        self.machine = None
        self.selected = None
        self._elem_tabs = {}
        self.config_path = None
        self.worker = None
        self._job_item = None
        self.results_model = ResultsModel()
        self.component = None
        self._last_dir = ""           # where the last file dialog ended up:
        # a component is deliberately saved outside the WIMBA repository, so the
        # dialogs should reopen there rather than at whatever the current
        # working directory happens to be
        self.project = None
        self.project_path = None
        self._machine_of = None       # slug of the scenario the panels belong to
        self._config_dirty = False    # panel edits not yet written to a config

        configure(self.settings.value("loglevel", None))
        self.log = get_logger("gui")
        self.console_view = QPlainTextEdit()
        self.console_view.setReadOnly(True)
        logging.getLogger("wimba").addHandler(QtLogHandler(self.console_view))
        configure(self.settings.value("loglevel", None))

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
        self._install_excepthook()
        from .. import config as _cfg
        from ..logutil import attach_file_handler
        logpath = attach_file_handler()
        if logpath:
            self.log.info("WIMBA GUI ready. Log file: %s (always at debug level).",
                          logpath)
        else:
            self.log.info("WIMBA GUI ready. File logging is off (logging.to_file).")
        created = _cfg.ensure_user_config()
        if created:
            self.log.info("No settings file existed; wrote a starter one at %s.",
                          created)
        self.log.info("Settings: %s (%s)", _cfg.config_path(), _cfg.config_source())

    # ---- central editor area: Plot Workspace + Results Table (+ element tabs) ----
    def _build_central(self):
        self.center = QTabWidget()
        self.center.setMovable(True)
        self.center.setDocumentMode(True)
        self.center.setTabsClosable(True)
        self.center.tabCloseRequested.connect(self._close_center_tab)

        self.plot_panel = PlotWorkspace(lambda: self.results_model)
        self.results_panel = ResultsTablePanel(lambda: self.results_model)
        self.center.addTab(self.plot_panel, "Plot Workspace")
        self.center.addTab(self.results_panel, "Results Table")
        for i in range(2):                  # Plot/Results are permanent
            self.center.tabBar().setTabButton(i, QTabBar.ButtonPosition.RightSide, None)
        self.setCentralWidget(self.center)

    def _close_center_tab(self, index: int):
        if index < 2:
            return
        w = self.center.widget(index)
        confirm = getattr(w, "confirm_close", None)
        if confirm is not None and not confirm():
            return                     # unsaved edits, and the user said no
        self.center.removeTab(index)
        self._elem_tabs = {k: v for k, v in self._elem_tabs.items() if v is not w}
        if w is getattr(self, "_mat_tab", None):
            self._mat_tab = None

    # ---- dock panels ----
    def _build_docks(self):
        placeholders = {
            "scenarios": ("\u29c9", "No project open",
                        "File \u2192 New Project to choose where results go, then load a machine."),
            "machine": ("\u25c8", "Machine is empty",
                        "File \u2192 Load Machine, or start a new one."),
            "optics":  ("\u25cb", "No optics yet",
                        "Load a machine, then load or enter the optics."),
            "beam":    ("\u2192", "No beam yet",
                        "Load a machine, then set the particle and its energy."),
            "results": ("\u2211", "No results yet",
                        "Run a calculation (or File \u2192 Open Results) to list computed quantities."),
            "inspector":("\u24d8", "Nothing selected",
                        "Select a node to see its properties and provenance."),
            "jobs":    ("\u29d7", "No jobs yet",
                        "Calculations you launch appear here with live status."),
            "console": ("\u203a_", "Console is quiet",
                        "Backend commands, files read, warnings and errors stream here."),
            "problems":("\u2713", "Nothing to report yet",
                        "Collisions and optics warnings appear here after a calculation."),
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

        self.splitDockWidget(self.docks["scenarios"], self.docks["machine"], Qt.Orientation.Vertical)
        self.splitDockWidget(self.docks["machine"], self.docks["optics"], Qt.Orientation.Vertical)
        self.tabifyDockWidget(self.docks["optics"], self.docks["beam"])
        self.docks["optics"].raise_()
        self.tabifyDockWidget(self.docks["jobs"], self.docks["console"])
        self.tabifyDockWidget(self.docks["console"], self.docks["problems"])
        self.docks["jobs"].raise_()

        self.tree = MachineTree()
        self.tree.picked.connect(self._on_pick)
        self.tree.opened.connect(self._open_element)
        self.inspector = InspectorPanel()
        self.docks["inspector"].setWidget(self.inspector)
        self.docks["console"].setWidget(self.console_view)
        self.results_tree = ResultsTree()
        self.results_tree.add_requested.connect(self._add_result)
        self.docks["results"].setWidget(self.results_tree)
        self._refresh_machine_panel()
        self._refresh_optics_panel()
        self._refresh_beam_panel()
        self._refresh_scenarios_panel()

    # ---- brand (logo in the menu-bar corner) ----
    def _build_brand(self):
        brand = QWidget()
        h = QHBoxLayout(brand)
        h.setContentsMargins(6, 0, 10, 0)
        h.setSpacing(8)
        logo = QLabel()
        pm = QPixmap(asset("wimba_logo_small.png"))
        if not pm.isNull():
            logo.setPixmap(pm.scaledToHeight(28, Qt.TransformationMode.SmoothTransformation))
        name = QLabel("WIMBA")
        name.setObjectName("Brand")
        h.addWidget(logo)
        h.addWidget(name)
        self.menuBar().setCornerWidget(brand, Qt.Corner.TopRightCorner)

    # ---- menus ----
    def _build_menus(self):
        mb = self.menuBar()

        m = mb.addMenu("&File")
        self._act(m, "New Project\u2026", self._new_project)
        self._act(m, "Open Project\u2026", self._open_project)
        self._act(m, "Close Project", self._close_project)
        m.addSeparator()
        self._act(m, "Load Machine\u2026", self._load_machine, QKeySequence.StandardKey.Open)
        self._act(m, "New Machine", self._new_machine, QKeySequence.StandardKey.New)
        self._act(m, "Open Config\u2026", self._open_config)
        self._act(m, "Open Results\u2026", self._open_results)
        self._act(m, "Close Machine", self._close_machine,
                  QKeySequence.StandardKey.Close)
        m.addSeparator()
        self._act(m, "Save Project", self._save_project, QKeySequence.StandardKey.Save)
        self._act(m, "Save Project As\u2026", self._save_project_as,
                  QKeySequence.StandardKey.SaveAs)
        m.addSeparator()
        self._act(m, "Duplicate Scenario\u2026", self._duplicate_scenario)
        self._act(m, "Rename Scenario\u2026", self._rename_scenario)
        self._act(m, "Remove Scenario", self._remove_scenario)
        m.addSeparator()
        sub = m.addMenu("Export Results")
        self._act(sub, "As CSV\u2026", lambda: self._export_results("csv"))
        self._act(sub, "As TXT (tab-separated)\u2026", lambda: self._export_results("txt"))
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
        level_menu = m.addMenu("Log Level")
        lg = QActionGroup(self); lg.setExclusive(True)
        cur = str(self.settings.value("loglevel", "info"))
        for lv in ("critical", "error", "warning", "info", "debug"):
            a = QAction(lv.capitalize(), self, checkable=True)
            a.setChecked(lv == cur)
            a.triggered.connect(lambda _=False, x=lv: self._set_loglevel(x))
            lg.addAction(a); level_menu.addAction(a)
        m.addSeparator()
        self._act(m, "Save Layout", self._save_layout)
        self._act(m, "Load Saved Layout", self._restore_layout)
        self._act(m, "Reset Layout", self._reset_layout)
        self._act(m, "Restore Default Layout", self._restore_default_layout)

        m = mb.addMenu("&Machine")
        self._act(m, "Add Group", self._add_group)
        self._act(m, "Add Element", self._add_element)
        self._act(m, "Rename Selected", self._rename_selected)
        self._act(m, "Duplicate Selected", self._duplicate_selected)
        self._act(m, "Delete Selected", self._delete_selected)

        m = mb.addMenu("&Component")
        self._act(m, "Use Selected Element as Component", self._comp_use_selected)
        self._act(m, "New Component\u2026", self._comp_new)
        self._act(m, "Load pytlwall Config\u2026", self._comp_load_pytlwall_cfg)
        self._act(m, "Load IW2D Config\u2026", self._comp_load_iw2d_cfg)
        self._act(m, "Save Component As\u2026", self._comp_save)
        m.addSeparator()
        self._act(m, "Calculate with pytlwall", lambda: self._comp_calc("pytlwall"))
        self._act(m, "Calculate with IW2D", lambda: self._comp_calc("IW2D"))
        self._act(m, "Load Precalculated\u2026", self._comp_load_precalc)
        self._act(m, "Calculate Wake (pytlwall)",
                  lambda: self._comp_calc("pytlwall", wake=True))
        m.addSeparator()
        self._act(m, "Clear Component Results", self._comp_clear)

        m = mb.addMenu("Ma&terials")
        self._act(m, "Add Material\u2026", self._material_add)
        self._act(m, "Show Materials\u2026", self._material_show)
        self._act(m, "Delete Material\u2026", self._material_delete)

        m = mb.addMenu("&Optics")
        self._act(m, "Load Optics\u2026", self._load_optics)
        self._act(m, "Clear Optics", self._todo)

        m = mb.addMenu("&Calculate")
        self.fill_pipe_action = QAction("Fill unmodelled lattice with resistive wall",
                                        self, checkable=True)
        self.fill_pipe_action.setChecked(True)
        m.addAction(self.fill_pipe_action)
        m.addSeparator()
        self._act(m, "Calculate Selected Element", self._calc_selected_element, "F5")
        self._act(m, "Calculate Selected Element Wake",
                  lambda: self._calc_selected_element(wake=True), "Shift+F5")
        self._act(m, "Calculate Comparisons Only\u2026", self._calc_element_compares,
                  "Ctrl+F5")
        self._act(m, "Calculate Selected Group", self._todo)
        m.addSeparator()
        self._act(m, "Calculate Whole Machine", self._calc_machine)
        self._act(m, "Calculate Whole Machine Wake", lambda: self._calc_machine(wake=True))
        self._act(m, "Calculate Whole Machine (not weighted)",
                  lambda: self._calc_machine(weighted=False))

        m = mb.addMenu("&Results")
        for label in ("Add Selection to Comparison", "Send Basket to Plot",
                      "Send Basket to Table", "Clear Comparison Basket"):
            self._act(m, label, self._todo)
        sub = m.addMenu("Export Results")
        self._act(sub, "As CSV\u2026", lambda: self._export_results("csv"))
        self._act(sub, "As TXT (tab-separated)\u2026", lambda: self._export_results("txt"))

        m = mb.addMenu("&Help")
        self._act(m, "Documentation\u2026", self._help_browser, "F1")
        self._act(m, "Search Help for\u2026", self._help_search, "Shift+F1")
        m.addSeparator()
        self._act(m, "Keyboard Shortcuts", self._keyboard_shortcuts)
        self._act(m, "About WIMBA", self._about)

    def _help_browser(self, query=""):
        """Open the documentation browser, searching if a query is given."""
        from .help_browser import HelpBrowser
        dlg = HelpBrowser(self, query=query)
        dlg.show()          # modeless: help stays open while you work
        self._help_dialog = dlg    # keep a reference so it is not collected

    def _help_search(self):
        """Ask what to look for, then open the browser on the answer."""
        from PyQt6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(
            self, "Search Help",
            "Question or keyword (the search also follows the words the\n"
            "documents use, so 'excel' finds the spreadsheet pages):")
        if ok and text.strip():
            self._help_browser(text.strip())

    def _keyboard_shortcuts(self):
        """List the shortcuts actually bound, read from the menus themselves so
        the list cannot drift out of date."""
        from PyQt6.QtWidgets import QMessageBox
        lines = []
        for top in self.menuBar().actions():
            menu = top.menu()
            if menu is None:
                continue
            rows = []
            for act in menu.actions():
                for a in (act.menu().actions() if act.menu() else [act]):
                    key = a.shortcut().toString()
                    if key:
                        rows.append(f"    {key:<12} {a.text().replace('&', '')}")
            if rows:
                lines.append(top.text().replace("&", "") + "\n" + "\n".join(rows))
        box = QMessageBox(self)
        box.setWindowTitle("Keyboard shortcuts")
        box.setText("\n\n".join(lines) if lines
                    else "No keyboard shortcuts are bound.")
        box.exec()

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
        bg = THEMES[name]["bg"]
        if hasattr(self, "plot_panel"):
            self.plot_panel.set_bg(bg)
            self.results_panel.set_bg(bg)
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

    # ---- panel refresh ----
    def _refresh_machine_panel(self):
        if not self.machine:
            self.docks["machine"].setWidget(empty_state("\u25c8", "Machine is empty",
                "File \u2192 Load Machine, or start a new one."))
            return
        self.tree.set_machine(self.machine)
        self.docks["machine"].setWidget(self.tree)

    def _refresh_optics_panel(self):
        if not self.machine:
            self.docks["optics"].setWidget(empty_state("\u25cb", "No optics yet",
                "Load a machine, then load or enter the optics."))
            return
        self.docks["optics"].setWidget(OpticsPanel(self.machine, self._after_edit, self._load_optics))

    def _refresh_beam_panel(self):
        """The Beam panel edits the machine's beam, or shows a component's own
        beam read-only when one is open in the bench."""
        if not self.machine:
            self.docks["beam"].setWidget(empty_state("\u2192", "No beam yet",
                "Load a machine, then set the particle and its energy."))
            return
        own = (getattr(self, "component", None) or None)
        override = None
        if own is not None:
            gamma = (getattr(own, "own_base", None) or {}).get("gamma")
            if gamma is not None:
                from ..core.beam import Beam
                override = Beam(mode="gamma", value=float(gamma))
        self.docks["beam"].setWidget(
            BeamPanel(self.machine, self._on_beam_changed, override=override))

    def _on_beam_changed(self):
        beam = getattr(self.machine, "beam", None)
        if beam is not None:
            self.log.info("Beam set to %s (1-beta = %.4g)", beam.label(),
                          beam.one_minus_beta)
            self.statusBar().showMessage(f"Beam: {beam.label()}", 5000)
        self._after_edit()

    def _refresh_all(self):
        self._refresh_machine_panel()
        self._refresh_optics_panel()
        self._refresh_beam_panel()
        self._refresh_scenarios_panel()
        self._update_status()

    def _update_status(self):
        if self.machine:
            self.lbl_machine.setText(self.machine.name)
            self.lbl_out.setText("output " + (self.machine.output or f"output/{self.machine.name}/"))
        else:
            self.lbl_machine.setText("No machine")
            self.lbl_out.setText("output \u2014")
        if self.selected:
            self.lbl_sel.setText(f"{self.selected['kind']}: {getattr(self.selected['obj'], 'name', '')}")
        else:
            self.lbl_sel.setText("nothing selected")

    def _after_edit(self):
        self._config_dirty = self.project is not None
        if self.machine:
            self.tree.set_machine(self.machine)
        self._update_status()

    # ---- selection ----
    def _on_pick(self, ref):
        self.selected = ref
        self.inspector.set_ref(ref)
        self._update_status()

    # ---- project and scenarios ----
    def _refresh_scenarios_panel(self):
        if self.project is None:
            self.docks["scenarios"].setWidget(empty_state("\u29c9", "No project open",
                "File \u2192 New Project to choose where results go, then load a machine."))
            return
        self.docks["scenarios"].setWidget(
            ScenarioPanel(self.project, self._pick_scenario, self._duplicate_scenario,
                          self._rename_scenario, self._remove_scenario))

    def _project_dir(self) -> Path:
        return Path(self.project.dir)

    def _new_project(self):
        directory = QFileDialog.getExistingDirectory(
            self, "New Project \u2014 choose the folder for configs and results")
        if not directory:
            return
        d = Path(directory)
        if (d / "project.yaml").exists():
            if QMessageBox.question(
                    self, "New Project",
                    f"{d} already holds a project.yaml.\n\nOpen it instead?"
                    ) == QMessageBox.StandardButton.Yes:
                self._open_project_at(d)
            return
        name, ok = QInputDialog.getText(self, "New Project", "Project name:",
                                        text=d.name)
        if not ok:
            return
        self.project = GProject(name=name.strip() or d.name, dir=str(d))
        self.project_path = str(d / "project.yaml")
        self.log.info("New project '%s' in %s", self.project.name, d)
        # a machine already open becomes scenario 1, so New Project works either
        # before or after loading
        if self.machine is not None and self._source_config():
            self._adopt_as_scenario(self._source_config())
        self._save_project(quiet=True)
        self._refresh_all()

    def _source_config(self):
        """The file the open machine came from, whichever door it came through."""
        return self.config_path or getattr(self, "machine_path", None)

    def _adopt_as_scenario(self, source, label=None):
        """Copy the config that produced the open machine into the project and
        register it as a scenario. The copy matters: the project must keep
        working when the original file is edited or moved."""
        import yaml

        src = Path(source)
        cfg = yaml.safe_load(src.read_text()) or {}
        grid = grid_of(cfg)
        if self.project.scenarios and grid and self.project.grid and grid != self.project.grid:
            raise ValueError(
                "this config asks for a different frequency/time grid than the "
                "project's. Scenarios of one project share a grid - that is what "
                "makes their curves comparable.")
        label = self.project.unique_label(label or cfg.get("name") or src.stem)
        slug = slugify(label)
        dest = self._project_dir() / f"{slug}_config.yaml"
        self._project_dir().mkdir(parents=True, exist_ok=True)
        if src.resolve() != dest.resolve():
            freeze_config(src, dest)
        for sub in ("output", "img"):
            (self._project_dir() / slug / sub).mkdir(parents=True, exist_ok=True)
        sc = self.project.add(GScenario(label=label, config=dest.name,
                                        beam=getattr(self.machine, "beam", None)))
        self._machine_of = sc.slug
        self.project.grid = self.project.grid or grid
        self.log.info("Scenario '%s' added: %s, results in %s/", label, dest.name, slug)
        return sc

    def _duplicate_scenario(self):
        """The only way to make a second scenario."""
        if self.project is None or not self.project.scenarios:
            return
        self._capture_scenario()
        src = self.project.scenario
        label, ok = QInputDialog.getText(
            self, "Duplicate Scenario",
            f"A copy of '{src.label}', to differ from it in the beam, the optics "
            f"or which elements it holds.\n\nName for the copy:",
            text=self.project.unique_label(f"{src.label} copy"))
        if not ok:
            return
        label = self.project.unique_label(label.strip() or f"{src.label} copy")
        slug = slugify(label)
        dest = self._project_dir() / f"{slug}_config.yaml"
        import shutil
        shutil.copyfile(self._project_dir() / src.config, dest)   # already frozen
        for sub in ("output", "img"):
            (self._project_dir() / slug / sub).mkdir(parents=True, exist_ok=True)
        self.project.add(GScenario(label=label, config=dest.name, beam=src.beam,
                                   derived_from=src.label))
        self.log.info("Scenario '%s' duplicated from '%s'", label, src.label)
        self._activate_scenario()
        self._save_project(quiet=True)

    def _rename_scenario(self):
        if self.project is None or not self.project.scenarios:
            return
        sc = self.project.scenario
        label, ok = QInputDialog.getText(self, "Rename Scenario", "Name:", text=sc.label)
        if not ok or not label.strip():
            return
        old_slug, old_config = sc.slug, sc.config
        try:
            self.project.rename(self.project.current, label.strip())
        except ValueError as exc:
            QMessageBox.warning(self, "Rename Scenario", str(exc))
            return
        d = self._project_dir()
        new_config = f"{sc.slug}_config.yaml"
        if old_config != new_config and (d / old_config).exists():
            (d / old_config).rename(d / new_config)
            sc.config = new_config
        if old_slug != sc.slug and (d / old_slug).exists():
            (d / old_slug).rename(d / sc.slug)
        if self._machine_of == old_slug:
            self._machine_of = sc.slug
        self._save_project(quiet=True)
        self._refresh_scenarios_panel()

    def _remove_scenario(self):
        if self.project is None or len(self.project.scenarios) < 2:
            return
        sc = self.project.scenario
        if QMessageBox.question(
                self, "Remove Scenario",
                f"Remove '{sc.label}' from the project?\n\nIts files in "
                f"{sc.slug}/ are left on disk."
                ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.project.remove(self.project.current)
        except ValueError as exc:
            QMessageBox.warning(self, "Remove Scenario", str(exc))
            return
        self.log.info("Scenario '%s' removed from the project", sc.label)
        self._activate_scenario()
        self._save_project(quiet=True)

    def _pick_scenario(self, row):
        if self.project is None or row < 0 or row == self.project.current:
            return
        self._capture_scenario()
        self.project.current = row
        self._activate_scenario()

    def _capture_scenario(self, write: bool = False):
        """Take what the panels hold into the current scenario.

        By default this only updates the in-memory scenario: WIMBA does not
        rewrite a config the user has not asked it to save. Pass write=True from
        an explicit Save Project / Save Project As, and only from there.

        Guarded on identity: if what is loaded is not this scenario's machine,
        writing the panels into it would put one scenario's beam on another.
        """
        if self.project is None or not self.project.scenarios:
            return
        sc = self.project.scenario
        if self.machine is None or getattr(self, "_machine_of", None) != sc.slug:
            return
        sc.beam = getattr(self.machine, "beam", None)
        if not write:
            return
        path = self._project_dir() / sc.config
        if not path.exists():
            return
        try:
            write_config(path, self.machine,
                         optics=getattr(self.machine, "optics_path", None))
            self._config_dirty = False
        except Exception as exc:                 # never lose the session over a save
            self.log.error("Could not write %s: %s", path, exc)
            QMessageBox.warning(self, "Save Project",
                                f"Could not write {path.name}:\n{exc}")

    def _activate_scenario(self):
        """Load the current scenario's machine into the panels."""
        sc = self.project.scenario if self.project else None
        if sc is None:
            self._refresh_all()
            return
        path = self._project_dir() / sc.config
        try:
            import yaml
            cfg = yaml.safe_load(path.read_text()) or {}
            if "devices" in cfg or "default_pipe" in cfg:
                self.machine = from_config(str(path))
                self.config_path = str(path)
            else:
                self.machine = from_machine_file(path)
                self.machine_path = str(path)
                self.config_path = None
        except Exception as exc:
            self.log.error("Scenario '%s': %s", sc.label, exc)
            QMessageBox.critical(self, "Scenario", f"Could not open '{sc.label}':\n{exc}")
            return
        if sc.beam is not None:
            self.machine.beam = sc.beam            # the scenario's beam wins
        self._machine_of = sc.slug
        self.selected = None
        self.inspector.set_ref(None)
        self._refresh_all()
        beam = f" \u2014 {sc.beam.label()}" if sc.beam is not None else ""
        self.statusBar().showMessage(f"Scenario: {sc.label}{beam}", 5000)

    # ---- project files ----
    def _save_project(self, quiet=False):
        if self.project is None:
            if not quiet:
                QMessageBox.information(
                    self, "Save Project",
                    "There is no project yet. File \u2192 New Project first: a "
                    "project is the folder its configs and results live in.")
            return
        import yaml

        # quiet saves (after a calculation, after removing a scenario) persist
        # project.yaml, which is WIMBA's own bookkeeping. The user's config is
        # written only when the user asks for it.
        self._capture_scenario(write=not quiet)
        path = Path(self.project_path or (self._project_dir() / "project.yaml"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(self.project.to_dict(), sort_keys=False))
        self.project_path = str(path)
        self.log.info("Project saved: %s (%d scenario(s))", path,
                      len(self.project.scenarios))
        if not quiet:
            self.statusBar().showMessage(f"Project saved to {path}", 4000)

    def _save_project_as(self):
        if self.project is None:
            self._save_project()
            return
        directory = QFileDialog.getExistingDirectory(self, "Save Project As \u2014 folder")
        if not directory:
            return
        import shutil
        old = self._project_dir()
        self.project.dir = directory
        self.project_path = str(Path(directory) / "project.yaml")
        for sc in self.project.scenarios:          # carry the configs across
            src, dest = old / sc.config, Path(directory) / sc.config
            if src.exists() and src.resolve() != dest.resolve():
                shutil.copyfile(src, dest)
            for sub in ("output", "img"):
                (Path(directory) / sc.slug / sub).mkdir(parents=True, exist_ok=True)
        self._save_project()
        self._refresh_scenarios_panel()

    def _close_project(self):
        """Leave the project, keeping what is on disk.

        Unsaved panel edits are offered, not written behind the user's back: a
        config on disk is the user's file, and WIMBA changes it only on request.
        """
        if self.project is None:
            self.statusBar().showMessage("No project is open.", 3000)
            return
        if self._config_dirty:
            answer = QMessageBox.question(
                self, "Close Project",
                "The panels hold edits that have not been written to this "
                "scenario's config.\n\nSave them before closing?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel)
            if answer == QMessageBox.StandardButton.Cancel:
                return
            if answer == QMessageBox.StandardButton.Save:
                self._save_project()
        name = self.project.name
        self._save_project(quiet=True)      # project.yaml only: WIMBA's own file
        self.project = None
        self.project_path = None
        self._machine_of = None
        self._config_dirty = False
        self.log.info("Project '%s' closed; its files are untouched.", name)
        self._close_machine(confirm=False)
        self._refresh_all()
        self.statusBar().showMessage(f"Project '{name}' closed", 4000)

    def _open_project(self):
        directory = QFileDialog.getExistingDirectory(self, "Open Project \u2014 folder")
        if directory:
            self._open_project_at(Path(directory))

    def _open_project_at(self, d: Path):
        import yaml
        path = Path(d) / "project.yaml"
        if not path.exists():
            QMessageBox.warning(self, "Open Project",
                                f"No project.yaml in {d}.")
            return
        try:
            self.project = GProject.from_dict(yaml.safe_load(path.read_text()) or {}, d)
        except Exception as exc:
            self.log.error("Could not open project %s: %s", path, exc)
            QMessageBox.critical(self, "Open Project", str(exc))
            return
        self.project_path = str(path)
        self.log.info("Project '%s' opened: %s", self.project.name,
                      ", ".join(self.project.labels()) or "no scenarios yet")
        self._activate_scenario()
        self._load_computed_results()

    def _load_computed_results(self):
        """Pull back the results of every scenario that has already been computed.

        Reopening a project to compare three scenarios should not mean computing
        three scenarios again: the files are on disk, and the resume in each
        output folder says what is in them.
        """
        if self.project is None:
            return
        found = []
        for sc in self.project.scenarios:
            out = self._project_dir() / sc.slug / "output"
            if not out.is_dir() or not any(out.iterdir()):
                continue
            try:
                self.results_model.add_scenario(out, sc.label)
                found.append(sc.label)
            except Exception as exc:
                self.log.debug("No readable results for '%s': %s", sc.label, exc)
        if found:
            self.results_tree.set_model(self.results_model)
            self.log.info("Loaded existing results for %d scenario(s): %s",
                          len(found), ", ".join(found))


    def _load_allowed(self, path) -> bool:
        """Whether a machine may be loaded over what the panels currently show.

        Inside a project the panels *are* the current scenario. Loading an
        unrelated machine into them would leave the two silently out of step -
        and the next save would write the wrong beam into the wrong scenario. So
        it is refused before anything is replaced, with the two ways forward.
        """
        if self.project is None or not self.project.scenarios:
            return True
        QMessageBox.information(
            self, "Load Machine",
            f"The project '{self.project.name}' already holds "
            f"{', '.join(self.project.labels())}, and the panels show the "
            f"current one.\n\nTo add a case, use Duplicate Scenario, so it "
            f"starts from one of these and stays comparable. To work on an "
            f"unrelated machine, open or start another project.")
        self.log.info("Load refused: project '%s' already holds %s",
                      self.project.name, ", ".join(self.project.labels()))
        return False

    def _maybe_adopt(self, path):
        """The first machine loaded into an open project becomes its scenario 1."""
        if self.project is None or self.project.scenarios:
            return
        try:
            self._adopt_as_scenario(path)
        except ValueError as exc:
            QMessageBox.warning(self, "Scenario", str(exc))
            return
        self._save_project(quiet=True)

    # ---- file actions ----
    def _load_machine(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Machine", "",
            "WIMBA input (*.yaml *.yml);;All files (*)")
        if path:
            self._load_from(path)

    def _load_from(self, path):
        if not self._load_allowed(path):
            return
        try:
            self.machine = from_machine_file(path)
        except Exception as exc:
            self.log.error("Load failed for %s: %s", path, exc)
            QMessageBox.critical(self, "Load failed", f"Could not load machine:\n{exc}")
            return
        self.machine_path = str(path)
        self.log.info("Loaded machine '%s'", self.machine.name)
        self._maybe_adopt(path)
        self.selected = None
        self.inspector.set_ref(None)
        self._refresh_all()
        self.statusBar().showMessage(
            f"Loaded {self.machine.name} \u2014 root node named '{self.machine.name}'", 4000)

    def _close_machine(self, confirm=True) -> bool:
        """Put the session back to how it looks at startup.

        Clears the machine, the results, the plots, the table, the open element
        tabs and the component bench - everything that could still refer to what
        was loaded before. Returns False if a run is in progress or the user
        backed out, so callers can abandon whatever they were about to do.
        """
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.information(self, "Close Machine",
                "A calculation is still running. Wait for it to finish, then "
                "close the machine.")
            return False

        if confirm and (self.machine is not None or self.results_model.sources):
            ans = QMessageBox.question(self, "Close Machine",
                "Close the machine and clear every result?\n\n"
                "Saving a machine is not implemented yet, so any edit you made "
                "here cannot be recovered.",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel)
            if ans != QMessageBox.StandardButton.Ok:
                return False

        # element tabs (0 and 1 are the Plot Workspace and the Results Table)
        for i in range(self.center.count() - 1, 1, -1):
            self.center.removeTab(i)
        self._elem_tabs = {}

        self.results_model.clear()
        self.results_tree.set_model(self.results_model)
        self.plot_panel.clear()
        self.results_panel.clear()

        jobs = self._dock_list("jobs")
        if jobs is not None:
            jobs.clear()
        self._job_item = None

        self.machine = None
        self.selected = None
        self.component = None
        self.config_path = None
        self.inspector.set_ref(None)

        self._refresh_all()
        self.log.info("Session closed: machine, results, plots and bench cleared.")
        self.statusBar().showMessage(
            "Machine closed \u2014 File \u2192 Load Machine to begin", 4000)
        return True

    def _new_machine(self):
        name, ok = QInputDialog.getText(self, "New Machine", "Machine name:", text="Untitled")
        if not ok:
            return
        # asked first, so backing out of the confirmation costs nothing
        if not self._close_machine():
            return
        self.machine = new_machine(name or "Untitled")
        self._refresh_all()

    # ---- machine edits ----
    def _need_machine(self):
        if not self.machine:
            self.statusBar().showMessage("Load or create a machine first", 2500)
            return False
        return True

    def _current_group(self):
        if self.selected:
            if self.selected["kind"] == "group":
                return self.selected["obj"]
            if self.selected["kind"] == "element":
                return self.selected.get("group") or (self.machine.groups[0] if self.machine.groups else None)
        return self.machine.groups[0] if self.machine.groups else None

    def _add_group(self):
        if not self._need_machine():
            return
        self.machine.groups.append(GGroup(f"Group {len(self.machine.groups) + 1}", []))
        self._refresh_all()

    def _add_element(self):
        if not self._need_machine():
            return
        g = self._current_group()
        if g is None:
            self._add_group()
            g = self.machine.groups[-1]
        e = new_element(f"ELEM.{len(g.elements) + 1}")
        g.elements.append(e)
        self._refresh_all()
        self._open_element(e)

    def _rename_selected(self):
        if not self.selected:
            return
        obj = self.selected["obj"]
        name, ok = QInputDialog.getText(self, "Rename", "New name:", text=getattr(obj, "name", ""))
        if ok and name:
            obj.name = name
            self._refresh_all()

    def _duplicate_selected(self):
        if not self.selected:
            return
        import copy
        kind, obj = self.selected["kind"], self.selected["obj"]
        if kind == "element":
            g = self.selected.get("group") or self._current_group()
            c = copy.deepcopy(obj); c.name += "_copy"; g.elements.append(c)
        elif kind == "group":
            c = copy.deepcopy(obj); c.name += " copy"; self.machine.groups.append(c)
        self._refresh_all()

    def _delete_selected(self):
        if not self.selected or self.selected["kind"] == "machine":
            return
        kind, obj = self.selected["kind"], self.selected["obj"]
        if QMessageBox.question(self, "Delete", f"Delete {getattr(obj, 'name', '')}?") \
                != QMessageBox.StandardButton.Yes:
            return
        if kind == "group":
            self.machine.groups = [g for g in self.machine.groups if g is not obj]
        elif kind == "element":
            g = self.selected.get("group")
            if g:
                g.elements = [e for e in g.elements if e is not obj]
        self.selected = None
        self.inspector.set_ref(None)
        self._refresh_all()

    # ---- optics ----
    def _load_optics(self):
        if not self._need_machine():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Load Optics (MAD-X twiss)", "",
            "TFS twiss (*.tfs *.dat);;All files (*)")
        if not path:
            return
        try:
            from ..builders import madx
            tw = madx.read_twiss(path)
        except Exception as exc:
            QMessageBox.critical(self, "Load failed", f"Could not read twiss:\n{exc}")
            return
        n = 0
        for _grp, e in self.machine.all_elements():
            row = tw.get(e.name)
            if row:
                e.optics["s"] = madx.get(row, "S")
                e.optics["l"] = madx.get(row, "L")
                e.optics["bx"] = madx.get(row, "BETX")
                e.optics["by"] = madx.get(row, "BETY")
                n += 1
        # remember the file, not just the numbers it produced: a scenario that
        # differs from its sibling by the optics has to say so in its config
        self.machine.optics_path = str(path)
        self._capture_scenario()
        self._config_dirty = True
        self._refresh_all()
        self.statusBar().showMessage(
            f"Loaded optics \u2014 matched {n} element(s) by name", 3000)

    # ---- element panel ----
    def _machine_of_element(self, el):
        """The machine this element belongs to, or None if it stands alone.

        Asked of the model rather than of how the panel was opened: an element
        picked from the tree into the bench is still part of the ring, and the
        beam it is computed with has to follow the ring's.
        """
        gm = self.machine
        if gm is None:
            return None
        try:
            return gm if any(e is el for _, e in gm.all_elements()) else None
        except Exception:
            return None

    def _open_element(self, el):
        self.log.debug("Opening element panel for '%s' (category %s, %d layer(s)).",
                       el.name, el.category, len(el.layers))
        self._open_el = el          # what 'Calculate Comparisons Only' acts on
        key = getattr(el, "uid", None) or id(el)
        if key in self._elem_tabs:
            self.center.setCurrentWidget(self._elem_tabs[key])
            return
        panel = ElementPanel(el, self._after_edit, self._calc_element,
                             machine=self._machine_of_element(el))
        self._elem_tabs[key] = panel
        self.center.setCurrentIndex(self.center.addTab(panel, el.name))

    # ---- Component bench: accumulate calculations of one component ----
    def _comp_use_selected(self):
        ref = self.selected
        if not ref or ref.get("kind") != "element":
            self.statusBar().showMessage("Select an element in the Machine tree first.", 4000)
            return
        self.component = ref["obj"]
        self._open_element(self.component)
        self.log.info("Component bench: using '%s'.", self.component.name)

    def _comp_new(self):
        name, ok = QInputDialog.getText(self, "New Component", "Component name:",
                                        text="COMP")
        if not ok or not name:
            return
        from .. import materials
        from .model import default_models, new_element
        el = new_element(name)
        el.models = default_models()
        # The first layer is a named material, not a hand-written conductivity:
        # a bare 1.4e6 belongs to nothing, so the Layers tab had to show it as
        # custom and the user could not tell what they had started from.
        layer = {"type": "CW", "thickness": 0.002, "boundary": True}
        default_material = materials.default_name()
        if default_material:
            materials.apply_to(layer, default_material)
            layer["boundary"] = True         # a single layer is the boundary
            layer["thickness"] = "inf"
        el.layers = [layer]
        el.geometry = {"length": 1.0, "radius": 0.02, "shape": "CIRCULAR"}
        self.component = el
        self._open_element(el)
        self.log.info("Component bench: new component '%s' (edit geometry/layers, "
                      "then Calculate).", name)

    def _log_engines(self, el=None):
        """Say which build of each engine will answer.

        Two checkouts of pytlwall can be installed side by side, and
        WIMBA_PYTLWALL_PATH or the config file can point at either. A number is
        only interpretable once you know which one produced it.
        """
        from .. import config as _cfg
        locate = getattr(_cfg, "engine_location", None)
        if locate is None:
            # config.py in this checkout does not provide it. Provenance is
            # useful, but never useful enough to abort a calculation: the caller
            # only catches ValueError, so an AttributeError here would surface as
            # "Unexpected error" instead of computing.
            self.log.debug("engine_location() not available in wimba.config; "
                           "skipping the engine provenance line")
            return
        methods = {"pytlwall"}
        for m in (getattr(el, "models", None) or []):
            if getattr(m, "enabled", False):
                methods.add(str(getattr(m, "method", "")).split()[0].lower())
        for c in (getattr(el, "compare", None) or []):
            methods.add(str(getattr(c, "method", "")).split()[0].lower())
        for name, module in (("pytlwall", "pytlwall"), ("iw2d", "IW2D")):
            if name not in methods:
                continue
            info = locate(module)
            if not info["available"]:
                continue
            ver = f" {info['version']}" if info["version"] else ""
            line = f"engine {module}{ver}: {info['path']}"
            if info.get("source"):
                line += f"  (found via {info['source']})"
            self.log.info(line)

    def _log_run_settings(self, el, source=""):
        """Say which beam and frequency grid a calculation will use, and where
        they come from. Silent inheritance from whatever config is open is the
        easiest way to compare two runs that were never the same run."""
        own = getattr(el, "own_base", None) or {}
        opened = self._base_cfg()
        gamma = own.get("gamma") or opened.get("gamma")
        from .model import as_number
        grid = {k: as_number(v) for k, v in
                (((own.get("grid") or opened.get("grid") or {}).get("frequency")) or {}).items()}
        beam = getattr(self.machine, "beam", None) if self.machine else None
        origin = "the element's own config" if own else (
            "the Beam panel" if beam is not None else
            f"the open config ({Path(self.config_path).name})" if self.config_path
            else "built-in defaults")
        if gamma is None:
            bits = ["NO BEAM SET - this calculation will refuse to run"]
        elif own or beam is None:
            bits = [f"gamma = {gamma:g}"]
        else:
            bits = [f"{beam.label()} (1-\u03b2 = {beam.one_minus_beta:.4g})"]
        if isinstance(grid.get("min"), float) and isinstance(grid.get("max"), float):
            bits.append(f"f = {grid['min']:g} .. {grid['max']:g} Hz, "
                        f"{grid.get('n')} points")
        elif grid:
            bits.append(f"f = {grid.get('min')} .. {grid.get('max')} Hz, "
                        f"{grid.get('n')} points")
        else:
            bits.append("f = (default grid)")
        msg = f"{el.name}: " + ", ".join(bits) + f" -- from {origin}"
        if source:
            msg += f" [{source}]"
        self.log.info(msg)
        self._log_engines(el)
        self.statusBar().showMessage(msg, 8000)
        return msg

    def _comp_load_pytlwall_cfg(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load pytlwall chamber config",
                                              self._dir_hint(),
                                              "pytlwall config (*.cfg);;All files (*)")
        if not path:
            return
        self._remember_dir(path)
        from ..io.pytlwall_cfg import read_chamber_cfg
        from .model import GElement, default_models
        try:
            data = read_chamber_cfg(path)
        except Exception as exc:
            self.log.error("Could not read %s: %s", path, exc)
            QMessageBox.critical(self, "Load pytlwall Config", str(exc))
            return
        geo = data["geometry"]
        layers = geo.pop("layers", [])
        name = geo.pop("name", None) or Path(path).stem
        # the Geometry tab reads the length from the geometry, the calculation
        # from the optics: set both, or the panel shows an empty field for a
        # length the file did state
        geo["length"] = data["length"]
        if data.get("test_beam_shift") is not None:
            # stated in the cfg: it must travel, or the same file read back
            # computes the space charge with pytlwall's default instead
            geo["test_beam_shift"] = data["test_beam_shift"]
        own = {k: v for k, v in (("gamma", data["gamma"]),
                                 ("grid", data["grid"])) if v}
        el = GElement(name=name, category="component", geometry=geo,
                      optics={"bx": data["betax"], "by": data["betay"],
                              "l": data["length"]},
                      layers=layers, models=default_models("pytlwall"),
                      own_base=own)
        self.component = el
        # kept for compatibility; the element now carries its own settings, so
        # they follow it through every calculation path and cannot go stale
        self._component_base = own
        self._open_element(el)
        self.log.info("Component '%s' loaded from pytlwall config %s", name, path)
        self._log_run_settings(el, source=f"pytlwall config {Path(path).name}")

    # ---- where file dialogs open ----
    def _dir_hint(self, filename=""):
        """Start a dialog in the last directory used, not in the process's
        working directory (which is usually the WIMBA checkout - the one place
        a user's own files should not go)."""
        if not self._last_dir:
            return filename
        return str(Path(self._last_dir) / filename) if filename else self._last_dir

    def _remember_dir(self, path):
        if path:
            self._last_dir = str(Path(path).parent)

    def _comp_save(self):
        """Write the component to a file of the user's choosing.

        What is written is a WIMBA config with a single device - the same thing
        the bench already emits into a temporary directory before every
        calculation. That format covers pytlwall, IW2D and precalculated alike,
        reopens with Open Config and runs with `wimba run`.
        """
        el = self._comp_require()
        if el is None:
            return
        from ..naming import safe
        from .model import (component_config_text, component_save_config,
                            method_base)
        model = next((m for m in el.models if m.enabled), None)
        method = model.method if model else "pytlwall"
        try:
            cfg = component_save_config(el, method, base_cfg=dict(self._base_cfg()))
        except ValueError as exc:
            self.log.error("Save Component: %s", exc)
            QMessageBox.warning(self, "Save Component As", str(exc))
            return

        default = f"{safe(el.name.split('  (')[0])}_component.yaml"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save component as", self._dir_hint(default),
            "WIMBA config (*.yaml *.yml);;All files (*)")
        if not path:
            return
        if not Path(path).suffix:
            path += ".yaml"
        try:
            Path(path).write_text(component_config_text(cfg, method_base(method)))
        except OSError as exc:
            self.log.error("Could not write %s: %s", path, exc)
            QMessageBox.critical(self, "Save Component As", str(exc))
            return
        self._remember_dir(path)
        self.log.info("Component '%s' saved to %s", el.name, path)
        if cfg.get("gamma") is None:
            self.log.warning("  the file states no beam: set gamma before "
                             "computing from it.")
        self.statusBar().showMessage(f"Component saved to {path}", 6000)

    def _comp_load_iw2d_cfg(self):
        """Open an IW2D round-chamber input file as a component.

        WIMBA does not compute through these files - it drives IW2D's Python
        API - but the format is how an IW2D case is written down and handed
        around, so it is worth being able to open one.
        """
        path, _ = QFileDialog.getOpenFileName(
            self, "Load IW2D input file", self._dir_hint(),
            "IW2D input (*.txt *.dat);;All files (*)")
        if not path:
            return
        self._remember_dir(path)
        from ..io.iw2d_input import read_iw2d_input
        from .model import GElement, default_models
        try:
            data = read_iw2d_input(path)
        except Exception as exc:
            self.log.error("Could not read %s: %s", path, exc)
            QMessageBox.critical(self, "Load IW2D Config", str(exc))
            return

        geo = data["geometry"]
        layers = geo.pop("layers", [])
        name = geo.pop("name", None) or Path(path).stem
        geo["length"] = data["length"]
        own = {k: v for k, v in (("gamma", data["gamma"]),
                                 ("grid", data["grid"])) if v}
        el = GElement(name=name, category="component", geometry=geo,
                      optics={"bx": data["betax"], "by": data["betay"],
                              "l": data["length"]},
                      layers=layers, models=default_models("IW2D"),
                      own_base=own)
        self.component = el
        self._component_base = own
        self._open_element(el)
        self.log.info("Component '%s' loaded from IW2D input %s", name, path)
        for note in data.get("notes", []):
            # what the file said and WIMBA could not keep: reported, never
            # dropped in silence
            self.log.warning("  %s", note)
        self._log_run_settings(el, source=f"IW2D input {Path(path).name}")

    def _comp_require(self):
        if getattr(self, "component", None) is None:
            self.statusBar().showMessage(
                "No component: use 'Use Selected Element as Component' or "
                "'New Component' first.", 5000)
            return None
        return self.component

    def _comp_calc(self, method, wake=False, data_file=None, data_component="ZLong"):
        el = self._comp_require()
        if el is None:
            return
        if method.lower() == "iw2d":
            self.log.warning("IW2D is not wired to its binary yet: this run will "
                             "report the row as skipped (the plumbing is ready).")
        import tempfile

        import yaml as _yaml

        from ..naming import safe
        from .model import component_config
        try:
            base = dict(self._base_cfg())
            self._log_run_settings(el)
            cfg = component_config(el, method, base_cfg=base,
                                   data_file=data_file, data_component=data_component)
        except ValueError as exc:
            self.log.error("Component bench: %s", exc)
            QMessageBox.warning(self, "Component", str(exc))
            return
        run_dir = Path(tempfile.mkdtemp(prefix="wimba_component_"))
        cfg_path = run_dir / f"{safe(cfg['name'])}.yaml"
        cfg_path.write_text(_yaml.safe_dump(cfg, sort_keys=False))
        self.log.info("Component config emitted: %s", cfg_path)
        self.log.debug("Emitted config:\n%s", cfg_path.read_text())

        con = self._dock_text("console")
        self.docks["console"].raise_()
        self._job_label = cfg["output"][0]
        self._job_item = QListWidgetItem(f"{self._job_label} \u2014 running\u2026")
        self._dock_list("jobs").addItem(self._job_item)
        self._run_kind = "component"
        self.worker = RunWorker(str(cfg_path), wake=wake, fill_pipe=False)
        self.worker.log.connect(con.appendPlainText)
        self.worker.done.connect(self._on_calc_done)
        self.worker.failed.connect(self._on_calc_failed)
        self.statusBar().showMessage(f"Calculating {self._job_label}\u2026")
        self.worker.start()

    def _comp_load_precalc(self):
        el = self._comp_require()
        if el is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Load precalculated data", self._dir_hint(),
            "Data or import map (*.dat *.txt *.csv *.xlsx *.xlsm *.yaml *.yml);;"
            "Spreadsheet (*.xlsx *.xlsm);;All files (*)")
        if not path:
            return
        self._remember_dir(path)
        if path.lower().endswith((".yaml", ".yml")):
            self._comp_calc("precalculated", data_file=path)
            return

        # A spreadsheet or an export carries every component in one file, with
        # named columns: take them all rather than asking which single one.
        from ..sources.precalculated_bridge import precalculated_components
        try:
            comps, reason = precalculated_components(path, return_reason=True)
        except Exception as exc:                 # a broken file must not end the session
            self.log.error("Could not read %s: %s", path, exc)
            QMessageBox.critical(self, "Load Precalculated",
                                 f"{Path(path).name} could not be read:\n\n{exc}")
            return
        if len(comps) > 1:
            self.log.info("Precalculated %s: %d component(s) found -- %s",
                          Path(path).name, len(comps), ", ".join(comps))
            self._comp_calc("precalculated",
                            data_file={c: path for c in comps})
            return

        if reason:
            # the reader knew what was wrong: say it, then offer the manual
            # route rather than dropping the user into it unexplained
            self.log.warning("Precalculated %s: %s", Path(path).name, reason)
            answer = QMessageBox.question(
                self, "Load Precalculated",
                f"WIMBA could not read {Path(path).name} on its own:\n\n{reason}"
                f"\n\nDescribe the file by hand instead?")
            if answer != QMessageBox.StandardButton.Yes:
                return

        from .import_dialog import ImportMapDialog
        try:
            dlg = ImportMapDialog(path, self)
            if dlg.exec() and dlg.map_path:
                self.log.info("Import map written: %s (reusable in configs).",
                              dlg.map_path)
                self._comp_calc("precalculated", data_file=str(dlg.map_path))
        except Exception as exc:
            self.log.error("Import map for %s failed: %s", path, exc)
            QMessageBox.critical(self, "Load Precalculated", str(exc))

    def _comp_clear(self):
        removed = [k for k in self.results_model.sources if "[" in k]
        for k in removed:
            self.results_model.sources.pop(k, None)
        self.results_tree.set_model(self.results_model)
        self.log.info("Component bench cleared (%d source(s) removed).", len(removed))

    def _calc_element_compares(self):
        """Compute only the entries under 'Additional calculations'.

        The base element is left out and the results are merged into the tree,
        so a comparison added after the fact does not cost a second run of what
        is already there.
        """
        # the element open in the editor: from the Machine tree, or the one
        # loaded into the Component bench
        ref = self.selected
        el = (ref.get("obj") if ref and ref.get("kind") == "element" else None) \
            or getattr(self, "component", None) \
            or getattr(self, "_open_el", None)
        if el is None:
            self.statusBar().showMessage(
                "Open an element first (Machine tree, or Component \u2192 "
                "Load pytlwall Config).", 5000)
            return
        if not (getattr(el, "compare", None) or []):
            QMessageBox.information(
                self, "Calculate comparisons",
                "This element has no comparison yet. Add one under "
                "'Additional calculations' in the Models tab.")
            return
        self._calc_element(el, compare_only=True)

    def _calc_selected_element(self, wake=False):
        ref = self.selected
        if not ref or ref.get("kind") != "element":
            self.statusBar().showMessage("Select an element in the Machine tree first.", 4000)
            return
        self._calc_element(ref["obj"], wake=wake)

    # ---- Materials: the named conductivities a CW layer can be filled from ----
    def _materials_tab(self):
        """Open the Materials tab, creating it once."""
        from .materials_tab import MaterialsTab
        if getattr(self, "_mat_tab", None) is None:
            self._mat_tab = MaterialsTab(log=self.log)
            self._mat_tab.changed.connect(self._materials_changed)
            self.center.addTab(self._mat_tab, "Materials")
        self.center.setCurrentWidget(self._mat_tab)
        return self._mat_tab

    def _material_show(self):
        self._materials_tab()

    def _material_add(self):
        """Add Material opens the same table and starts a row in it.

        A dialog that took a name and a number told you nothing about what was
        already there, and the material it produced was invisible until you
        opened a layer. The table is where materials live; adding one is an
        edit to it.
        """
        self._materials_tab().add_row()

    def _material_delete(self):
        tab = self._materials_tab()
        self.statusBar().showMessage(
            "Select one of your own materials (the pink rows) and press "
            "Delete selected.", 6000)
        return tab

    def _materials_changed(self):
        """After a save, rebuild the material dropdown of every open element.

        A panel builds its list once, so a material added while a component was
        open stayed invisible until the tab was closed and reopened - which is
        exactly what looked like the material not having been added at all.
        """
        for panel in list(self._elem_tabs.values()):
            refresh = getattr(panel, "_refresh_layers", None)
            if refresh is not None:
                try:
                    refresh()
                except Exception as exc:            # a stale tab must not stop the save
                    self.log.debug("Could not refresh a panel: %s", exc)

    def _base_cfg(self):
        """Grid, materials and gamma a calculation starts from.

        The open config supplies the grid; the Beam panel supplies gamma. The
        panel wins because it is what the user can see and change - a gamma read
        from a file that no longer matches the panel would be exactly the silent
        mismatch this whole change is about.
        """
        cfg = {}
        if self.config_path:
            try:
                import yaml
                cfg = yaml.safe_load(Path(self.config_path).read_text()) or {}
            except Exception:
                cfg = {}
        beam = getattr(self.machine, "beam", None) if self.machine else None
        if beam is not None:
            cfg = dict(cfg)
            cfg["gamma"] = beam.gamma
            cfg["beam"] = beam.to_dict()
        return cfg

    def _calc_element(self, el, wake=False, compare_only=False):
        import tempfile

        import yaml as _yaml

        from ..naming import safe
        from .model import element_to_config, wants_wake
        if not wake and wants_wake(el):
            # A wake comparison yields an empty column without a time grid.
            # Asking for one is asking for the wake, so the wake is computed -
            # and the grid that decision implies is stated, not assumed.
            wake = True
            self.log.info(
                "A comparison on '%s' asks for a wake, so the wake is computed "
                "too.", el.name)
        try:
            self._log_run_settings(el)
            cfg = element_to_config(el, base_cfg=self._base_cfg(),
                                    compare_only=compare_only)
        except ValueError as exc:
            self.log.error("Cannot calculate '%s': %s", el.name, exc)
            QMessageBox.warning(self, "Calculate element", str(exc))
            return
        run_dir = Path(tempfile.mkdtemp(prefix="wimba_element_"))
        cfg_path = run_dir / f"{safe(cfg['name'])}.yaml"
        cfg_path.write_text(_yaml.safe_dump(cfg, sort_keys=False))

        con = self._dock_text("console")
        self.docks["console"].raise_()
        self.log.info("Single-element config emitted: %s", cfg_path)
        self.log.debug("Emitted config:\n%s", cfg_path.read_text())
        self._job_label = el.name
        self._job_item = QListWidgetItem(f"{self._job_label} \u2014 running\u2026")
        self._dock_list("jobs").addItem(self._job_item)

        if wake:
            self.log.info("Wake requested: the native pytlwall wake is computed from the "
                          "geometry (impedance is recomputed alongside; cached geometries "
                          "keep it cheap).")
            t = (cfg.get("grid") or {}).get("time") or {}
            if t:
                self.log.info("  time grid: %s .. %s s, %s points%s",
                              t.get("min"), t.get("max"), t.get("n"),
                              "" if "time" in (self._base_cfg().get("grid") or {})
                              else " (WIMBA's default: the open config states none)")
        # a compare-only run adds to what is already there instead of replacing it
        self._run_kind = "element_compare" if compare_only else "element"
        self.worker = RunWorker(str(cfg_path), wake=wake, fill_pipe=False)
        self.worker.log.connect(con.appendPlainText)
        self.worker.done.connect(self._on_calc_done)
        self.worker.failed.connect(self._on_calc_failed)
        self.statusBar().showMessage(f"Calculating '{el.name}'\u2026")
        self.worker.start()

    # ---- logging / robustness ----
    def _install_excepthook(self):
        def hook(exc_type, exc, tb):
            if issubclass(exc_type, KeyboardInterrupt):
                sys.__excepthook__(exc_type, exc, tb)
                return
            self.log.error("Unhandled exception:\n%s",
                           "".join(traceback.format_exception(exc_type, exc, tb)))
            try:
                self.docks["console"].raise_()
                QMessageBox.critical(self, "Unexpected error",
                                     f"{exc_type.__name__}: {exc}\n\nSee the Console for details.")
            except Exception:
                pass
        sys.excepthook = hook

    def _set_loglevel(self, level):
        set_level(level)
        self.settings.setValue("loglevel", level)
        self.log.info("Log level set to %s", level)

    # ---- config + compute (front-end over run) ----
    def _open_config(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Assembly Config", "",
            "YAML (*.yaml *.yml);;All files (*)")
        if not path:
            return
        if not self._load_allowed(path):
            return
        self.config_path = path
        try:
            import yaml
            cfg = yaml.safe_load(Path(path).read_text()) or {}
            self.machine = from_config(path)
        except Exception as exc:
            self.log.error("Could not read config %s: %s", path, exc)
            QMessageBox.critical(self, "Open Config", f"Could not read config:\n{exc}")
            return

        self._maybe_adopt(path)
        self.selected = None
        self.inspector.set_ref(None)
        self._refresh_all()

        name = cfg.get("name", Path(path).stem)
        n_dev = len(cfg.get("devices") or {})
        has_pipe = "default_pipe" in cfg
        self.fill_pipe_action.setChecked(has_pipe)
        self.docks["console"].raise_()
        self.log.info("Opened config '%s' (%s): %d device source(s), default pipe %s.",
                      name, Path(path).name, n_dev, "on" if has_pipe else "off")
        self.log.info("Machine and Optics populated. Calculate \u2192 Whole Machine to compute.")
        self.statusBar().showMessage(f"Config loaded: {name} \u2014 Calculate to compute", 6000)

    def _dock_text(self, pid):
        w = self.docks[pid].widget()
        if not isinstance(w, QPlainTextEdit):
            w = QPlainTextEdit(); w.setReadOnly(True)
            self.docks[pid].setWidget(w)
        return w

    def _dock_list(self, pid):
        w = self.docks[pid].widget()
        if not isinstance(w, QListWidget):
            w = QListWidget()
            self.docks[pid].setWidget(w)
        return w

    def _add_result(self, ref):
        """Route a double-clicked result to the active central tab."""
        if self.center.currentWidget() is self.results_panel:
            self.results_panel.add_ref(ref)
        else:
            self.center.setCurrentWidget(self.plot_panel)
            self.plot_panel.add_ref(ref)

    def _open_results(self):
        path = QFileDialog.getExistingDirectory(self, "Open a WIMBA output folder")
        if not path:
            return
        self.results_model.load(path)
        if not self.results_model.sources:
            QMessageBox.warning(self, "Open Results",
                                "No single_elements/total.csv found in that folder.")
            return
        self.results_tree.set_model(self.results_model)
        self.docks["results"].raise_()
        self.log.info("Results loaded from %s (%d source(s)).", path,
                      len(self.results_model.sources))

    def _calc_machine(self, wake=False, weighted=True):
        """Compute the whole machine.

        weighted=False sets every transverse weight to one. It is a second
        result, not a replacement: it lands in the tree under its own name so
        the two can be plotted against each other.
        """
        out_dir = None
        sc = self.project.scenario if self.project else None
        if sc is not None:
            # inside a project there is nothing to ask: the scenario names its own
            # config, and its results belong in its own folder
            path = self._project_dir() / sc.config
            out_dir = str(self._project_dir() / sc.slug / "output")
            if self._dialect(path) == "machine":
                return self._build_machine(path, out_dir, weighted=weighted)
            self.config_path = str(path)
        elif getattr(self, "machine_path", None) and not self.config_path:
            # a machine loaded outside a project: build it where it lives
            return self._build_machine(self.machine_path, None, weighted=weighted)
        if not self.config_path:
            self._open_config()
        if not self.config_path:
            return
        con = self._dock_text("console"); con.clear()
        self.docks["console"].raise_()
        self._job_label = Path(self.config_path).name
        self._job_item = QListWidgetItem(f"{self._job_label} \u2014 running\u2026")
        self._dock_list("jobs").addItem(self._job_item)

        if wake:
            self.log.info("Wake requested: computed natively from each geometry "
                          "(impedance recomputed alongside).")
        if not weighted:
            self.log.info("Computing UNWEIGHTED: every transverse weight is 1. "
                          "Already weighted sources are still summed as they are.")
            self._job_item.setText(f"{self._job_label} (not weighted) \u2014 running\u2026")
        self._run_kind = "machine"
        self._run_weighted = weighted
        beam = getattr(self.machine, "beam", None) if self.machine else None
        overrides = ({"beam": beam.to_dict(), "gamma": beam.gamma}
                     if beam is not None else None)
        if overrides is None:
            overrides = {}
        stated = getattr(self.machine, "smooth_beta", None) if self.machine else None
        if stated:
            overrides["smooth_beta"] = {"x": float(stated[0]), "y": float(stated[1])}
        self.worker = RunWorker(self.config_path, out_dir=out_dir, wake=wake,
                                fill_pipe=self.fill_pipe_action.isChecked(),
                                overrides=overrides or None, weighted=weighted)
        self.worker.log.connect(con.appendPlainText)
        self.worker.done.connect(self._on_calc_done)
        self.worker.failed.connect(self._on_calc_failed)
        self.statusBar().showMessage("Calculating\u2026")
        self.worker.start()

    def _dialect(self, path) -> str:
        """"assembly" (devices/default_pipe rules) or "machine" (listed groups).

        Which one decides the pipeline: rules are executed by assemble/run
        against a lattice, a listed machine is computed element by element by
        build. Both end in the Results panel, so the distinction stops here.
        """
        import yaml
        try:
            cfg = yaml.safe_load(Path(path).read_text()) or {}
        except Exception as exc:
            QMessageBox.critical(self, "Calculate", f"Could not read {path}:\n{exc}")
            return "unreadable"
        return "assembly" if ("devices" in cfg or "default_pipe" in cfg) else "machine"

    def _build_machine(self, path, out_dir, weighted=True):
        """Calculate for a machine file: the build pipeline, same panels."""
        path = Path(path)
        if self._dialect(path) == "unreadable":
            return
        con = self._dock_text("console"); con.clear()
        self.docks["console"].raise_()
        self._job_label = path.name
        self._job_item = QListWidgetItem(f"{self._job_label} \u2014 building\u2026")
        self._dock_list("jobs").addItem(self._job_item)
        self._run_kind = "build"
        self._run_weighted = weighted
        if not weighted:
            self.log.info("Building UNWEIGHTED: every transverse weight is 1.")
            self._job_item.setText(f"{self._job_label} (not weighted) \u2014 building\u2026")
        self.worker = BuildWorker(path, out_dir=out_dir,
                                  beam=getattr(self.machine, "beam", None)
                                  if self.machine else None,
                                  smooth_beta=getattr(self.machine, "smooth_beta", None)
                                  if self.machine else None,
                                  weighted=weighted)
        self.worker.log.connect(con.appendPlainText)
        self.worker.done.connect(self._on_build_done)
        self.worker.failed.connect(self._on_calc_failed)
        self.statusBar().showMessage("Building\u2026")
        self.worker.start()

    def _store_results(self, out_dir):
        """Put a finished machine run into the Results panel.

        Inside a project the results are filed under the scenario's label and
        ADDED to what is already there, so two scenarios can be plotted
        together. Outside a project the behaviour is unchanged: one run, one set
        of results.
        """
        sc = self.project.scenario if self.project else None
        if sc is not None and self._machine_of == sc.slug:
            # an unweighted run is a second result, not a replacement: it is
            # labelled apart so both can sit in the tree and on one figure
            label = sc.label if getattr(self, "_run_weighted", True) \
                else f"{sc.label} (not weighted)"
            self.results_model.add_scenario(out_dir, label)
            loaded = self.results_model.scenarios()
            self.log.info("Results now hold %d scenario(s): %s",
                          len(loaded), ", ".join(loaded))
        else:
            self.results_model.load(out_dir)
        self.results_tree.set_model(self.results_model)
        self.docks["results"].raise_()

    def _on_build_done(self, payload):
        info = payload["info"]
        st = info["stats"]
        if self._job_item:
            self._job_item.setText(f"{getattr(self, '_job_label', 'job')} \u2014 done "
                                   f"({st['computed']} element(s))")
        self.log.info("Build finished: %s element(s) in %s group(s) \u2192 %s",
                      st["elements"], st["groups"], info["out"])
        if self.project is not None:
            sc = self.project.scenario
            if sc is not None and self._machine_of == sc.slug:
                from datetime import datetime
                sc.computed_at = datetime.now().isoformat(timespec="seconds")
                self._save_project(quiet=True)
                self._refresh_scenarios_panel()
        self._store_results(info["out"])
        prob = self._dock_text("problems"); prob.clear()
        prob.appendPlainText(
            f"{st['elements']} element(s) in {st['groups']} group(s), "
            f"{st['additional']} additional \u2014 all computed.")
        prob.appendPlainText("Element-driven build: only what the machine lists is "
                             "computed, so there is no lattice to collide on.")
        self.statusBar().showMessage(
            f"Done \u2192 {info['out']} \u2014 pick quantities from the Results tree",
            6000)

    def _on_calc_done(self, payload):
        result, info = payload["result"], payload["info"]
        st = info["stats"]
        if self._job_item:
            self._job_item.setText(f"{getattr(self, '_job_label', 'job')} \u2014 done "
                                   f"({st['computed']} computed)")
            self.log.info("Run finished: %s computed, %s skipped \u2192 %s",
                          st["computed"], st.get("skipped", 0), info["out"])
        if self.project is not None and getattr(self, "_run_kind", "machine") == "machine":
            sc = self.project.scenario
            if sc is not None and self._machine_of == sc.slug:
                from datetime import datetime
                sc.computed_at = datetime.now().isoformat(timespec="seconds")
                self._save_project(quiet=True)
                self._refresh_scenarios_panel()
        kind = getattr(self, "_run_kind", "machine")
        if kind in ("component", "element_compare"):
            self.results_model.merge(info["out"])
            self.results_model.adopt_total_wake(getattr(self, "_job_label", ""))
        elif kind == "machine":
            self._store_results(info["out"])
        else:
            self.results_model.load(info["out"])
        if kind == "element" and len(self.results_model.sources) > 1:
            # single-element study: the element (with its wake) and its compares
            self.results_model.adopt_total_wake(getattr(self, "_job_label", ""))
        if kind != "machine":
            self.results_tree.set_model(self.results_model)
            self.docks["results"].raise_()
        prob = self._dock_text("problems"); prob.clear()
        prob.appendPlainText(f"{len(result.rows)} assignments \u2014 "
                             f"computed {st['computed']}, skipped {st['skipped']}.")
        for line in self._weighting_problems(result, st):
            prob.appendPlainText(line)
            self.log.warning(line.replace("WARNING  ", ""))
            self.docks["problems"].raise_()
        for note in st.get("notes", []):
            prob.appendPlainText(f"  {note}")
            self.log.warning(note)
        if st.get("notes"):
            self.docks["problems"].raise_()
        for w in getattr(result, "warnings", []):
            prob.appendPlainText(f"WARNING  {w}")
            self.log.warning(w)
        if getattr(result, "warnings", []):
            self.docks["problems"].raise_()
        if result.collisions:
            for c in result.collisions:
                tag = "intentional" if c.intentional else "ERROR"
                prob.appendPlainText(f"s={c.position:.3f} m: {', '.join(c.names)}  [{tag}]")
        else:
            prob.appendPlainText("No collisions.")
        self.statusBar().showMessage(
            f"Done \u2192 {info['out']} \u2014 pick quantities from the Results tree", 6000)

    def _weighting_problems(self, result, stats):
        """What the transverse weighting is, and when not to trust the total.

        The dangerous case is an unweighted calculation over a model that also
        contains already-weighted data: those sources keep their own weighting
        whatever is asked, so the total mixes weighted and unweighted terms and
        is not a quantity at all. Nothing fails, and the numbers look ordinary.
        """
        out = []
        mx, my = stats.get("beta_mean", (1.0, 1.0))
        src = stats.get("beta_mean_source", "none")
        if stats.get("weighted", True):
            out.append(f"Transverse weight: \u03b2 / \u03b2\u0304, with \u03b2\u0304 = "
                       f"({mx:.6g}, {my:.6g}) m \u2014 {src}.")
            if src == "elements":
                out.append("WARNING  \u03b2\u0304 was estimated from the modelled "
                           "elements, not from a lattice. Devices sit where \u03b2 "
                           "is large, so it is usually high.")
            return out

        out.append("Computed UNWEIGHTED: every transverse weight is 1.")
        pre = [r.name for r in result.rows if getattr(r, "weighted", False)]
        if pre:
            shown = ", ".join(pre[:3]) + (f" and {len(pre) - 3} more"
                                          if len(pre) > 3 else "")
            out.append(f"WARNING  {len(pre)} source(s) carry their own weighting "
                       f"and keep it: {shown}. The transverse total therefore adds "
                       f"weighted and unweighted terms and is not comparable with "
                       f"either. Use it per element, not as a machine total.")
        return out

    def _on_calc_failed(self, tb):
        if self._job_item:
            self._job_item.setText(f"{getattr(self, '_job_label', 'job')} \u2014 FAILED")
        con = self._dock_text("console")
        con.appendPlainText("\nFAILED:\n" + tb)
        self.docks["console"].raise_()
        self.statusBar().showMessage("Calculation failed \u2014 see Console", 5000)

    # ---- placeholder for actions wired in later phases ----
    def _export_results(self, fmt: str = "csv"):
        """Write every computed series to a directory chosen by the user.

        Args:
            fmt: ``"csv"`` (comma) or ``"txt"`` (tab-separated, the layout
                pytlwall writes, so the two codes compare column by column).

        The dialog opens on the last directory used for an export, so a series
        of exports lands together without retyping the path.
        """
        from .results import export_model, last_export_dir, remember_export_dir

        model = getattr(self, "results_model", None)
        if model is None or not getattr(model, "sources", None):
            QMessageBox.information(self, "Export Results",
                                    "Nothing has been computed yet.")
            return

        start = last_export_dir() or str(Path.home())
        out = QFileDialog.getExistingDirectory(
            self, f"Export results as {fmt.upper()} to folder", start)
        if not out:
            return

        try:
            written = export_model(model, out, fmt=fmt)
        except OSError as exc:
            self.log.error("Export Results failed: %s", exc)
            QMessageBox.warning(self, "Export Results",
                                f"Could not write to {out}:\n{exc}")
            return

        remember_export_dir(out)
        self.log.info("Exported %d file(s) to %s", len(written), out)
        self.statusBar().showMessage(
            f"Exported {len(written)} file(s) to {out}", 4000)
        if not written:
            QMessageBox.information(self, "Export Results",
                                    "Nothing to export: no series carried data.")

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
