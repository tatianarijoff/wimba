"""Results workspace for the WIMBA GUI.

After a calculation (or opening an existing output folder) the user gets a tree
of everything that was computed - total and per-device, impedance components
(wall and space charge) and wakes. Nothing is plotted by default: quantities are
added explicitly to the Plot Workspace or to the Results Table (double-click or
drag), can be removed or renamed, and both views can be exported.

The data model (ResultsModel) is Qt-free so it can be tested headlessly; the
widgets follow the pattern of the pytlwall GUI (tree -> canvas/table with an
editable item list).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

ASSETS = Path(__file__).parent / "assets"

from ..output import read_totals, read_wake_totals

MIME = "application/x-wimba-result"


# ------------------------------------------------------------------ model
class ResultsModel:
    """What was computed, organised as source -> kind -> {quantity: array}.

    kind is "impedance" (complex, vs frequency) or "wake" (real, vs time).
    """

    def __init__(self):
        self.sources = {}          # name -> {"impedance": (x, {q: z}), "wake": (x, {q: w})}

    def clear(self):
        self.sources = {}

    @staticmethod
    def _with_sc_totals(loaded):
        """Add derived <base>+ISC = wall + indirect space charge where both are
        present (the explicit name says exactly what is summed)."""
        x, comps = loaded
        for base in ("ZLong", "ZDipX", "ZDipY", "ZQuadX", "ZQuadY"):
            isc = f"{base}ISC"
            if base in comps and isc in comps:
                comps[f"{base}+ISC"] = comps[base] + comps[isc]
        return x, comps

    def load(self, out_dir) -> "ResultsModel":
        self.clear()
        se = Path(out_dir) / "single_elements"
        total = se / "total.csv"
        if total.is_file():
            self.sources.setdefault("Total", {})["impedance"] = \
                self._with_sc_totals(read_totals(total))
        wake = se / "total_wake.csv"
        if wake.is_file():
            self.sources.setdefault("Total", {})["wake"] = read_wake_totals(wake)
        if se.is_dir():
            for group_dir in sorted(p for p in se.iterdir() if p.is_dir()):
                for csv_file in sorted(group_dir.glob("*.csv")):
                    name = f"{group_dir.name}/{csv_file.stem}"
                    self.sources.setdefault(name, {})["impedance"] = \
                        self._with_sc_totals(read_totals(csv_file))
        return self

    def series(self, source, kind, quantity, component="Re"):
        """Return (x, y, label) for one quantity/component."""
        x, comps = self.sources[source][kind]
        data = np.asarray(comps[quantity])
        if kind == "wake":
            return x, data.real, f"{source} {quantity}"
        y = {"Re": data.real, "Im": data.imag, "|Z|": np.abs(data)}[component]
        return x, y, f"{source} {quantity} {component}"


def encode(source, kind, quantity, component):
    return f"{source}|{kind}|{quantity}|{component}"


def decode(text):
    source, kind, quantity, component = text.split("|", 3)
    return source, kind, quantity, component


# ------------------------------------------------------------------- Qt UI
from PyQt6.QtCore import QMimeData, Qt, pyqtSignal                     # noqa: E402
from PyQt6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout,       # noqa: E402
                             QHeaderView, QInputDialog, QLabel,
                             QListWidget, QListWidgetItem, QMenu,
                             QMessageBox, QPushButton, QSplitter,
                             QTableWidget, QTableWidgetItem, QTreeWidget,
                             QTreeWidgetItem, QVBoxLayout, QWidget)

ROLE = Qt.ItemDataRole.UserRole


class ResultsTree(QTreeWidget):
    """Tree of computed quantities; leaves are draggable and double-clickable."""

    add_requested = pyqtSignal(str)          # encoded entry

    def __init__(self):
        super().__init__()
        self.setHeaderHidden(True)
        self.setDragEnabled(True)
        self.itemDoubleClicked.connect(self._dbl)
        self.model_ = None

    def set_model(self, model: ResultsModel):
        self.model_ = model
        self.clear()
        for source, kinds in model.sources.items():
            si = QTreeWidgetItem([source])
            self.addTopLevelItem(si)
            if "impedance" in kinds:
                zi = QTreeWidgetItem(["Impedance"])
                si.addChild(zi)
                _x, comps = kinds["impedance"]
                for q in comps:
                    qi = QTreeWidgetItem([q])
                    zi.addChild(qi)
                    for comp in ("Re", "Im", "|Z|"):
                        leaf = QTreeWidgetItem([comp])
                        leaf.setData(0, ROLE, encode(source, "impedance", q, comp))
                        qi.addChild(leaf)
            if "wake" in kinds:
                wi = QTreeWidgetItem(["Wake"])
                si.addChild(wi)
                _x, comps = kinds["wake"]
                for q in comps:
                    leaf = QTreeWidgetItem([q])
                    leaf.setData(0, ROLE, encode(source, "wake", q, "Re"))
                    wi.addChild(leaf)
            si.setExpanded(source == "Total")
        if self.topLevelItemCount():
            it = self.topLevelItem(0)
            for i in range(it.childCount()):
                it.child(i).setExpanded(True)

    def mimeData(self, items):
        md = QMimeData()
        payload = [i.data(0, ROLE) for i in items if i.data(0, ROLE)]
        if payload:
            md.setText(payload[0])
            md.setData(MIME, payload[0].encode())
        return md

    def _dbl(self, item, _col):
        ref = item.data(0, ROLE)
        if ref:
            self.add_requested.emit(ref)


class _Entry:
    def __init__(self, ref, x, y, label):
        self.ref = ref
        self.x = np.asarray(x, dtype=float)
        self.y = np.asarray(y, dtype=float)
        self.default_label = label
        self.custom_label = None
        self.visible = True

    @property
    def label(self):
        return self.custom_label or self.default_label


class PlotWorkspace(QWidget):
    """Matplotlib canvas + editable list of curves. Accepts tree drops."""

    def __init__(self, model_getter):
        super().__init__()
        self.model_getter = model_getter
        self.entries = []
        self.setAcceptDrops(True)

        from PyQt6.QtGui import QPixmap
        from PyQt6.QtWidgets import QGraphicsOpacityEffect, QStackedLayout

        import matplotlib
        matplotlib.use("QtAgg")
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from matplotlib.figure import Figure
        self.fig = Figure(figsize=(6.4, 4.2), tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.fig)
        self.canvas.setMinimumSize(120, 90)   # keep the central area resizable
        self.ax = self.fig.add_subplot(111)

        self.items = QListWidget()
        self.items.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.items.customContextMenuRequested.connect(self._menu)
        self.items.itemChanged.connect(self._toggled)
        self.items.setMaximumWidth(280)

        self.xscale = QComboBox()
        self.xscale.addItems(["log", "linear"])
        self.xscale.currentTextChanged.connect(lambda _t: self._redraw())
        self.yscale = QComboBox()
        self.yscale.addItems(["log |y|", "symlog", "linear"])
        self.yscale.currentTextChanged.connect(lambda _t: self._redraw())
        export_png = QPushButton("Export PNG\u2026")
        export_png.clicked.connect(self._export_png)
        export_csv = QPushButton("Export CSV\u2026")
        export_csv.clicked.connect(self._export_csv)
        clear = QPushButton("Clear")
        clear.clicked.connect(self._clear)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("x scale:"))
        controls.addWidget(self.xscale)
        controls.addWidget(QLabel("y scale:"))
        controls.addWidget(self.yscale)
        controls.addStretch(1)
        controls.addWidget(clear)
        controls.addWidget(export_csv)
        controls.addWidget(export_png)

        side = QVBoxLayout()
        side.addWidget(QLabel("Curves (double-click a result in the tree to add)"))
        side.addWidget(self.items, 1)

        split = QSplitter()
        left = QWidget(); lv = QVBoxLayout(left); lv.setContentsMargins(0, 0, 0, 0)
        lv.addLayout(controls); lv.addWidget(self.canvas, 1)
        right = QWidget(); right.setLayout(side)
        split.addWidget(left); split.addWidget(right)
        split.setSizes([640, 240])

        # empty state: faint WIMBA logo until the first curve is added
        empty = QWidget()
        ev = QVBoxLayout(empty)
        ev.addStretch(1)
        logo_path = ASSETS / "wimba_logo_small.png"
        if logo_path.is_file():
            logo = QLabel()
            pm = QPixmap(str(logo_path))
            logo.setPixmap(pm.scaledToWidth(260, Qt.TransformationMode.SmoothTransformation))
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            eff = QGraphicsOpacityEffect(logo); eff.setOpacity(0.25)
            logo.setGraphicsEffect(eff)
            ev.addWidget(logo)
        hint = QLabel("Drag results here from the Results tree (or double-click them)")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setObjectName("EmptyText")
        ev.addWidget(hint)
        ev.addStretch(2)

        self._stack = QStackedLayout(self)
        self._stack.addWidget(empty)      # 0: logo
        self._stack.addWidget(split)      # 1: canvas + list
        self._stack.setCurrentIndex(0)

    # --- add/remove
    def add_ref(self, ref):
        model = self.model_getter()
        if model is None:
            return
        if any(e.ref == ref for e in self.entries):
            return
        source, kind, q, comp = decode(ref)
        try:
            x, y, label = model.series(source, kind, q, comp)
        except KeyError:
            return
        e = _Entry(ref, x, y, label)
        self.entries.append(e)
        it = QListWidgetItem(e.label)
        it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        it.setCheckState(Qt.CheckState.Checked)
        it.setData(ROLE, e)
        self.items.addItem(it)
        self._stack.setCurrentIndex(1)
        self._redraw()

    def _clear(self):
        self.entries = []
        self.items.clear()
        self._stack.setCurrentIndex(0)
        self._redraw()

    def _menu(self, pos):
        it = self.items.itemAt(pos)
        if not it:
            return
        e = it.data(ROLE)
        menu = QMenu(self)
        rn = menu.addAction("Rename\u2026")
        rm = menu.addAction("Remove")
        act = menu.exec(self.items.mapToGlobal(pos))
        if act == rm:
            self.entries.remove(e)
            self.items.takeItem(self.items.row(it))
            if not self.entries:
                self._stack.setCurrentIndex(0)
            self._redraw()
        elif act == rn:
            text, ok = QInputDialog.getText(self, "Curve label", "Label:", text=e.label)
            if ok:
                e.custom_label = text or None
                it.setText(e.label)
                self._redraw()

    def _toggled(self, it):
        e = it.data(ROLE)
        if e:
            e.visible = it.checkState() == Qt.CheckState.Checked
            self._redraw()

    # --- drawing / export
    def _redraw(self):
        self.ax.clear()
        if getattr(self, "_bg", None):
            self.ax.set_facecolor(self._bg)
        vis = [e for e in self.entries if e.visible]
        mode = self.yscale.currentText()
        wakes = any(e.ref.split("|")[1] == "wake" for e in vis)
        for e in vis:
            y = np.abs(e.y) if mode == "log |y|" else e.y
            self.ax.plot(e.x, y, label=e.label)
        if vis:
            self.ax.set_xscale("linear" if wakes else self.xscale.currentText())
            if mode == "log |y|":
                self.ax.set_yscale("log")
            elif mode == "symlog":
                nz = np.concatenate([np.abs(e.y[e.y != 0]) for e in vis if np.any(e.y != 0)] or [np.array([1.0])])
                self.ax.set_yscale("symlog", linthresh=float(nz.min()))
            self.ax.set_xlabel("time [s]" if wakes else "frequency [Hz]")
            self.ax.grid(True, which="both", alpha=0.3)
            self.ax.legend(fontsize=8)
        else:
            self.ax.set_title("No curves - add results from the tree", fontsize=10)
        self.canvas.draw_idle()

    def _export_png(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export plot", "plot.png", "PNG (*.png)")
        if path:
            self.fig.savefig(path, dpi=150)

    def _export_csv(self):
        vis = [e for e in self.entries if e.visible]
        if not vis:
            QMessageBox.information(self, "Export", "Nothing to export.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export curves", "curves.csv", "CSV (*.csv)")
        if not path:
            return
        import csv as _csv
        with open(path, "w", newline="") as fh:
            w = _csv.writer(fh)
            w.writerow(["x"] + [e.label for e in vis])
            n = max(len(e.x) for e in vis)
            for i in range(n):
                row = [f"{vis[0].x[i]:.8e}" if i < len(vis[0].x) else ""]
                row += [f"{e.y[i]:.8e}" if i < len(e.y) else "" for e in vis]
                w.writerow(row)

    def set_bg(self, color):
        """Theme hook: recolor the matplotlib figure to match the app theme."""
        self._bg = color
        light = sum(int(color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4)) > 380
        fg = "#222222" if light else "#c9d1d9"
        self.fig.patch.set_facecolor(color)
        self.ax.set_facecolor(color)
        self.ax.tick_params(colors=fg)
        for spine in self.ax.spines.values():
            spine.set_color(fg)
        self.ax.xaxis.label.set_color(fg)
        self.ax.yaxis.label.set_color(fg)
        self.ax.title.set_color(fg)
        self.canvas.draw_idle()

    # --- drag & drop
    def dragEnterEvent(self, ev):
        if ev.mimeData().hasFormat(MIME) or ev.mimeData().hasText():
            ev.acceptProposedAction()

    dragMoveEvent = dragEnterEvent

    def dropEvent(self, ev):
        text = bytes(ev.mimeData().data(MIME)).decode() if ev.mimeData().hasFormat(MIME) \
            else ev.mimeData().text()
        if text:
            self.add_ref(text)
            ev.acceptProposedAction()


class ResultsTablePanel(QWidget):
    """Table of added quantities (one column each) sharing the same x axis."""

    def __init__(self, model_getter):
        super().__init__()
        self.model_getter = model_getter
        self.columns = []            # list[_Entry]
        self.x = None
        self.x_label = ""
        self.setAcceptDrops(True)

        self.table = QTableWidget(0, 0)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.horizontalHeader().customContextMenuRequested.connect(self._header_menu)
        self.table.verticalHeader().setVisible(False)

        export_csv = QPushButton("Export CSV\u2026")
        export_csv.clicked.connect(self._export_csv)
        clear = QPushButton("Clear")
        clear.clicked.connect(self._clear)
        top = QHBoxLayout()
        top.addWidget(QLabel("Double-click results in the tree (or drop them here) to add columns; "
                             "right-click a header to remove."))
        top.addStretch(1)
        top.addWidget(clear)
        top.addWidget(export_csv)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.table, 1)

    def add_ref(self, ref):
        model = self.model_getter()
        if model is None or any(e.ref == ref for e in self.columns):
            return
        source, kind, q, comp = decode(ref)
        try:
            x, y, label = model.series(source, kind, q, comp)
        except KeyError:
            return
        if self.x is not None and (len(x) != len(self.x) or not np.allclose(x, self.x)):
            QMessageBox.warning(self, "Results table",
                                "This quantity is on a different axis (frequency vs time "
                                "or a different grid); export the current table first, "
                                "then Clear to start a new one.")
            return
        if self.x is None:
            self.x = np.asarray(x, dtype=float)
            self.x_label = "time [s]" if kind == "wake" else "frequency [Hz]"
        self.columns.append(_Entry(ref, x, y, label))
        self._rebuild()

    def _rebuild(self):
        self.table.clear()
        if self.x is None:
            self.table.setRowCount(0); self.table.setColumnCount(0)
            return
        self.table.setColumnCount(1 + len(self.columns))
        self.table.setHorizontalHeaderLabels([self.x_label] + [c.label for c in self.columns])
        self.table.setRowCount(len(self.x))
        for r, xv in enumerate(self.x):
            self.table.setItem(r, 0, QTableWidgetItem(f"{xv:.6e}"))
            for c, col in enumerate(self.columns, start=1):
                self.table.setItem(r, c, QTableWidgetItem(f"{col.y[r]:.6e}"))

    def _header_menu(self, pos):
        col = self.table.horizontalHeader().logicalIndexAt(pos)
        if col <= 0:
            return
        menu = QMenu(self)
        rm = menu.addAction(f"Remove '{self.columns[col - 1].label}'")
        act = menu.exec(self.table.horizontalHeader().mapToGlobal(pos))
        if act == rm:
            del self.columns[col - 1]
            if not self.columns:
                self.x = None
            self._rebuild()

    def _clear(self):
        self.columns = []
        self.x = None
        self._rebuild()

    def _export_csv(self):
        if self.x is None:
            QMessageBox.information(self, "Export", "Nothing to export.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export table", "results.csv", "CSV (*.csv)")
        if not path:
            return
        import csv as _csv
        with open(path, "w", newline="") as fh:
            w = _csv.writer(fh)
            w.writerow([self.x_label] + [c.label for c in self.columns])
            for r, xv in enumerate(self.x):
                w.writerow([f"{xv:.8e}"] + [f"{c.y[r]:.8e}" for c in self.columns])

    def set_bg(self, color):
        """Theme hook (table follows the app stylesheet; nothing to recolor)."""

    dragEnterEvent = PlotWorkspace.dragEnterEvent
    dragMoveEvent = PlotWorkspace.dragEnterEvent
    dropEvent = PlotWorkspace.dropEvent
