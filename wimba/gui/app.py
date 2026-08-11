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

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import (QAction, QActionGroup, QColor, QIcon, QKeySequence,
                         QPainter, QPixmap)
from PyQt6.QtWidgets import (QApplication, QDockWidget, QFileDialog, QHBoxLayout,
                             QInputDialog, QLabel, QListWidget, QListWidgetItem,
                             QMainWindow, QMessageBox, QPlainTextEdit, QScrollArea,
                             QTabBar, QTabWidget, QVBoxLayout, QWidget)

from .theme import THEMES, build_style
from .model import GGroup, from_config, from_project, new_element, new_machine
from .panels import ElementPanel, InspectorPanel, MachineTree, OpticsPanel
from .runner import RunWorker
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
    "machine":  ("Machine Explorer", Qt.DockWidgetArea.LeftDockWidgetArea),
    "optics":   ("Optics",           Qt.DockWidgetArea.LeftDockWidgetArea),
    "results":  ("Results",          Qt.DockWidgetArea.RightDockWidgetArea),
    "inspector":("Inspector",        Qt.DockWidgetArea.RightDockWidgetArea),
    "jobs":     ("Jobs",             Qt.DockWidgetArea.BottomDockWidgetArea),
    "console":  ("Console",          Qt.DockWidgetArea.BottomDockWidgetArea),
    "problems": ("Problems",         Qt.DockWidgetArea.BottomDockWidgetArea),
    "outputs":  ("Output Browser",   Qt.DockWidgetArea.BottomDockWidgetArea),
}


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


class QtLogHandler(logging.Handler):
    """Streams log records into a QPlainTextEdit, coloured by level."""

    COLORS = {"CRITICAL": "#ff5c5c", "ERROR": "#ff7b72", "WARNING": "#e0a458",
              "INFO": "#8ab4f8", "DEBUG": "#7d8590"}

    def __init__(self, widget):
        super().__init__()
        self.widget = widget
        self.setFormatter(logging.Formatter("%(levelname)-8s %(name)s: %(message)s"))

    def emit(self, record):
        msg = self.format(record).replace("<", "&lt;").replace(">", "&gt;")
        color = self.COLORS.get(record.levelname, "#c9d1d9")
        self.widget.appendHtml(f'<span style="color:{color}">{msg}</span>')


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

        configure(self.settings.value("loglevel", "info"))
        self.log = get_logger("gui")
        self.console_view = QPlainTextEdit()
        self.console_view.setReadOnly(True)
        logging.getLogger("wimba").addHandler(QtLogHandler(self.console_view))
        configure(self.settings.value("loglevel", "info"))

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
        from ..logutil import attach_file_handler
        logpath = attach_file_handler()
        self.log.info("WIMBA GUI ready. Log file: %s (always at debug level).", logpath)

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
        if index >= 2:
            w = self.center.widget(index)
            self.center.removeTab(index)
            self._elem_tabs = {k: v for k, v in self._elem_tabs.items() if v is not w}

    # ---- dock panels ----
    def _build_docks(self):
        placeholders = {
            "machine": ("\u25c8", "Machine is empty",
                        "File \u2192 Load Machine, or start a new one."),
            "optics":  ("\u25cb", "No optics yet",
                        "Load a machine, then load or enter the optics."),
            "results": ("\u2211", "No results yet",
                        "Run a calculation (or File \u2192 Open Results) to list computed quantities."),
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
        self._act(m, "Load Machine\u2026", self._load_machine, QKeySequence.StandardKey.Open)
        self._act(m, "New Machine", self._new_machine, QKeySequence.StandardKey.New)
        self._act(m, "Open Config\u2026", self._open_config)
        self._act(m, "Open Results\u2026", self._open_results)
        self._act(m, "Close Machine", self._close_machine,
                  QKeySequence.StandardKey.Close)
        m.addSeparator()
        self._act(m, "Save Project", self._todo, QKeySequence.StandardKey.Save)
        self._act(m, "Save Project As\u2026", self._todo, QKeySequence.StandardKey.SaveAs)
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
        m.addSeparator()
        self._act(m, "Calculate with pytlwall", lambda: self._comp_calc("pytlwall"))
        self._act(m, "Calculate with IW2D", lambda: self._comp_calc("IW2D"))
        self._act(m, "Load Precalculated\u2026", self._comp_load_precalc)
        self._act(m, "Calculate Wake (pytlwall)",
                  lambda: self._comp_calc("pytlwall", wake=True))
        m.addSeparator()
        self._act(m, "Clear Component Results", self._comp_clear)

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

    def _refresh_all(self):
        self._refresh_machine_panel()
        self._refresh_optics_panel()
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
        if self.machine:
            self.tree.set_machine(self.machine)
        self._update_status()

    # ---- selection ----
    def _on_pick(self, ref):
        self.selected = ref
        self.inspector.set_ref(ref)
        self._update_status()

    # ---- file actions ----
    def _load_machine(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Machine", "",
            "WIMBA input (*.yaml *.yml);;All files (*)")
        if path:
            self._load_from(path)

    def _load_from(self, path):
        try:
            self.machine = from_project(path)
        except Exception as exc:
            self.log.error("Load failed for %s: %s", path, exc)
            QMessageBox.critical(self, "Load failed", f"Could not load machine:\n{exc}")
            return
        self.log.info("Loaded machine '%s'", self.machine.name)
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
        self._refresh_all()
        self.statusBar().showMessage(f"Loaded optics \u2014 matched {n} element(s) by name", 3000)

    # ---- element panel ----
    def _open_element(self, el):
        self.log.debug("Opening element panel for '%s' (category %s, %d layer(s)).",
                       el.name, el.category, len(el.layers))
        self._open_el = el          # what 'Calculate Comparisons Only' acts on
        key = getattr(el, "uid", None) or id(el)
        if key in self._elem_tabs:
            self.center.setCurrentWidget(self._elem_tabs[key])
            return
        panel = ElementPanel(el, self._after_edit, self._calc_element)
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
        from .model import default_models, new_element
        el = new_element(name)
        el.models = default_models()
        el.layers = [{"type": "CW", "thickness": 0.002, "sigma": 1.4e6}]
        el.geometry = {"radius": 0.02, "shape": "CIRCULAR"}
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
        methods = {"pytlwall"}
        for m in (getattr(el, "models", None) or []):
            if getattr(m, "enabled", False):
                methods.add(str(getattr(m, "method", "")).split()[0].lower())
        for c in (getattr(el, "compare", None) or []):
            methods.add(str(getattr(c, "method", "")).split()[0].lower())
        for name, module in (("pytlwall", "pytlwall"), ("iw2d", "IW2D")):
            if name not in methods:
                continue
            info = _cfg.engine_location(module)
            if not info["available"]:
                continue
            ver = f" {info['version']}" if info["version"] else ""
            line = f"engine {module}{ver}: {info['path']}"
            if info.get("source"):
                line += f"  (found via {info['source']})"
            self.log.info(line)

    def _log_run_settings(self, el, source=""):
        """Say which gamma and frequency grid a calculation will use, and where
        they come from. Silent inheritance from whatever config is open is the
        easiest way to compare two runs that were never the same run."""
        own = getattr(el, "own_base", None) or {}
        opened = self._base_cfg()
        gamma = own.get("gamma") or opened.get("gamma")
        grid = (own.get("grid") or opened.get("grid") or {}).get("frequency") or {}
        origin = "the element's own config" if own else (
            f"the open config ({Path(self.config_path).name})" if self.config_path
            else "built-in defaults")
        bits = [f"gamma = {gamma}" if gamma is not None else "gamma = (default)"]
        if grid:
            bits.append(f"f = {grid.get('min'):g} .. {grid.get('max'):g} Hz, "
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
                                              "", "pytlwall config (*.cfg);;All files (*)")
        if not path:
            return
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

    def _comp_load_iw2d_cfg(self):
        QMessageBox.information(
            self, "Load IW2D Config",
            "Reading IW2D inputs is planned, but I will not guess the format: "
            "send a sample IW2D input file and the loader will be calibrated on "
            "it (as done for the CST exports).")

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
            self, "Load precalculated data", "",
            "Data or import map (*.dat *.txt *.csv *.xlsx *.xlsm *.yaml *.yml);;"
            "Spreadsheet (*.xlsx *.xlsm);;All files (*)")
        if not path:
            return
        if path.lower().endswith((".yaml", ".yml")):
            self._comp_calc("precalculated", data_file=path)
            return

        # A spreadsheet or an export carries every component in one file, with
        # named columns: take them all rather than asking which single one.
        from ..sources.precalculated_bridge import precalculated_components
        comps = precalculated_components(path)
        if len(comps) > 1:
            self.log.info("Precalculated %s: %d component(s) found -- %s",
                          Path(path).name, len(comps), ", ".join(comps))
            self._comp_calc("precalculated",
                            data_file={c: path for c in comps})
            return

        from .import_dialog import ImportMapDialog
        dlg = ImportMapDialog(path, self)
        if dlg.exec() and dlg.map_path:
            self.log.info("Import map written: %s (reusable in configs).", dlg.map_path)
            self._comp_calc("precalculated", data_file=str(dlg.map_path))

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

    def _base_cfg(self):
        if not self.config_path:
            return {}
        try:
            import yaml
            return yaml.safe_load(Path(self.config_path).read_text()) or {}
        except Exception:
            return {}

    def _calc_element(self, el, wake=False, compare_only=False):
        import tempfile

        import yaml as _yaml

        from ..naming import safe
        from .model import element_to_config
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
        self.config_path = path
        try:
            import yaml
            cfg = yaml.safe_load(Path(path).read_text()) or {}
            self.machine = from_config(path)
        except Exception as exc:
            self.log.error("Could not read config %s: %s", path, exc)
            QMessageBox.critical(self, "Open Config", f"Could not read config:\n{exc}")
            return

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

    def _calc_machine(self, wake=False):
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
        self._run_kind = "machine"
        self.worker = RunWorker(self.config_path, wake=wake,
                                fill_pipe=self.fill_pipe_action.isChecked())
        self.worker.log.connect(con.appendPlainText)
        self.worker.done.connect(self._on_calc_done)
        self.worker.failed.connect(self._on_calc_failed)
        self.statusBar().showMessage("Calculating\u2026")
        self.worker.start()

    def _on_calc_done(self, payload):
        result, info = payload["result"], payload["info"]
        st = info["stats"]
        if self._job_item:
            self._job_item.setText(f"{getattr(self, '_job_label', 'job')} \u2014 done "
                                   f"({st['computed']} computed)")
            self.log.info("Run finished: %s computed, %s skipped \u2192 %s",
                          st["computed"], st.get("skipped", 0), info["out"])
        kind = getattr(self, "_run_kind", "machine")
        if kind in ("component", "element_compare"):
            self.results_model.merge(info["out"])
            self.results_model.adopt_total_wake(getattr(self, "_job_label", ""))
        else:
            self.results_model.load(info["out"])
        if kind == "element" and len(self.results_model.sources) > 1:
            # single-element study: the element (with its wake) and its compares
            self.results_model.adopt_total_wake(getattr(self, "_job_label", ""))
        self.results_tree.set_model(self.results_model)
        self.docks["results"].raise_()
        prob = self._dock_text("problems"); prob.clear()
        prob.appendPlainText(f"{len(result.rows)} assignments \u2014 "
                             f"computed {st['computed']}, skipped {st['skipped']}.")
        for note in st.get("notes", []):
            prob.appendPlainText(f"  {note}")
            self.log.warning(note)
        if st.get("notes"):
            self.docks["problems"].raise_()
        if result.collisions:
            for c in result.collisions:
                tag = "intentional" if c.intentional else "ERROR"
                prob.appendPlainText(f"s={c.position:.3f} m: {', '.join(c.names)}  [{tag}]")
        else:
            prob.appendPlainText("No collisions.")
        self.statusBar().showMessage(
            f"Done \u2192 {info['out']} \u2014 pick quantities from the Results tree", 6000)

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
