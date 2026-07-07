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

        configure(self.settings.value("loglevel", "info"))
        self.log = get_logger("gui")
        self.console_view = QPlainTextEdit()
        self.console_view.setReadOnly(True)
        logging.getLogger("wimba").addHandler(QtLogHandler(self.console_view))

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
        self.log.info("WIMBA GUI ready.")

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

        m = mb.addMenu("&Optics")
        self._act(m, "Load Optics\u2026", self._load_optics)
        self._act(m, "Clear Optics", self._todo)

        m = mb.addMenu("&Calculate")
        self.fill_pipe_action = QAction("Fill unmodelled lattice with resistive wall",
                                        self, checkable=True)
        self.fill_pipe_action.setChecked(True)
        m.addAction(self.fill_pipe_action)
        self.wake_action = QAction("Compute wake", self, checkable=True)
        m.addAction(self.wake_action)
        m.addSeparator()
        self._act(m, "Calculate Selected Element", self._todo, "F5")
        self._act(m, "Calculate Selected Group", self._todo)
        self._act(m, "Calculate Whole Machine", self._calc_machine)

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

    def _new_machine(self):
        name, ok = QInputDialog.getText(self, "New Machine", "Machine name:", text="Untitled")
        if not ok:
            return
        self.machine = new_machine(name or "Untitled")
        self.selected = None
        self.inspector.set_ref(None)
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
        key = id(el)
        if key in self._elem_tabs:
            self.center.setCurrentWidget(self._elem_tabs[key])
            return
        panel = ElementPanel(el, self._after_edit, self._calc_element)
        self._elem_tabs[key] = panel
        self.center.setCurrentIndex(self.center.addTab(panel, el.name))

    def _calc_element(self, el):
        self.statusBar().showMessage(
            f"Calculate '{el.name}' \u2014 backend + Jobs come in the next phase", 3000)

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

    def _calc_machine(self):
        if not self.config_path:
            self._open_config()
        if not self.config_path:
            return
        con = self._dock_text("console"); con.clear()
        self.docks["console"].raise_()
        self._job_item = QListWidgetItem(f"{Path(self.config_path).name} \u2014 running\u2026")
        self._dock_list("jobs").addItem(self._job_item)

        self.worker = RunWorker(self.config_path,
                                wake=self.wake_action.isChecked(),
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
            self._job_item.setText(f"{Path(self.config_path).name} \u2014 done "
                                   f"({st['computed']} computed)")
        self.results_model.load(info["out"])
        self.results_tree.set_model(self.results_model)
        self.docks["results"].raise_()
        prob = self._dock_text("problems"); prob.clear()
        prob.appendPlainText(f"{len(result.rows)} assignments \u2014 "
                             f"computed {st['computed']}, skipped {st['skipped']}.")
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
            self._job_item.setText(f"{Path(self.config_path).name} \u2014 FAILED")
        con = self._dock_text("console")
        con.appendPlainText("\nFAILED:\n" + tb)
        self.docks["console"].raise_()
        self.statusBar().showMessage("Calculation failed \u2014 see Console", 5000)

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
