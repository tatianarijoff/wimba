"""Panel widgets for the WIMBA GUI, bound to the view-model in model.py.

Each panel edits the model in place and calls an ``on_change`` callback so the
controller (MainWindow) can refresh the tree, inspector and status bar.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFormLayout,
                             QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QProgressBar, QPushButton, QTableWidget,
                             QTableWidgetItem, QTabWidget, QTreeWidget,
                             QTreeWidgetItem, QVBoxLayout, QWidget)

from .model import (METHODS, QLABEL, QUANTITIES, QUNITS, GElement, GGroup,
                    GMachine, GModel, method_needs_file, new_element,
                    optics_completeness)

ROLE = Qt.ItemDataRole.UserRole


def placeholder(icon, title, text):
    w = QWidget()
    w.setStyleSheet("background:transparent;")
    lay = QVBoxLayout(w)
    lay.addStretch(1)
    for oid, txt, wrap in (("EmptyIcon", icon, False), ("EmptyTitle", title, False),
                           ("EmptyText", text, True)):
        lab = QLabel(txt); lab.setObjectName(oid)
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter); lab.setWordWrap(wrap)
        lay.addWidget(lab)
    lay.addStretch(2)
    return w


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return x if x not in ("", None) else None


# ===================================================================== tree
class MachineTree(QTreeWidget):
    picked = pyqtSignal(object)          # ref dict
    opened = pyqtSignal(object)          # GElement

    def __init__(self):
        super().__init__()
        self.setHeaderHidden(True)
        self.setIndentation(14)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.itemSelectionChanged.connect(self._sel)
        self.itemDoubleClicked.connect(self._dbl)
        self.machine = None

    def set_machine(self, gm: GMachine):
        self.machine = gm
        self.clear()
        if not gm:
            return
        root = QTreeWidgetItem([f"\u25c8  {gm.name}"])
        root.setData(0, ROLE, {"kind": "machine", "obj": gm})
        self.addTopLevelItem(root)
        for g in gm.groups:
            self._add_group(root, g)
        if gm.additional:
            ag = QTreeWidgetItem([f"\u25a3  Additional (pre-weighted)"])
            ag.setData(0, ROLE, {"kind": "group", "obj": GGroup("additional", gm.additional)})
            root.addChild(ag)
            for e in gm.additional:
                self._add_element(ag, e, GGroup("additional", gm.additional))
        root.setExpanded(True)
        for i in range(root.childCount()):
            root.child(i).setExpanded(True)

    def _add_group(self, parent, g):
        gi = QTreeWidgetItem([f"\u25a3  {g.name}   ({len(g.elements)})"])
        gi.setData(0, ROLE, {"kind": "group", "obj": g})
        parent.addChild(gi)
        for e in g.elements:
            self._add_element(gi, e, g)

    def _add_element(self, parent, e, g):
        ei = QTreeWidgetItem([f"\u2b21  {e.name}"])
        ei.setData(0, ROLE, {"kind": "element", "obj": e, "group": g})
        parent.addChild(ei)

    def _sel(self):
        items = self.selectedItems()
        if items:
            self.picked.emit(items[0].data(0, ROLE))

    def _dbl(self, item, _col):
        ref = item.data(0, ROLE)
        if ref and ref["kind"] == "element":
            self.opened.emit(ref["obj"])


# ============================================================== element panel
class ElementPanel(QWidget):
    def __init__(self, element: GElement, on_change, on_calc):
        super().__init__()
        self.el = element
        self.on_change = on_change
        self.on_calc = on_calc
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()
        tabs.addTab(self._geometry_tab(), "Geometry")
        tabs.addTab(self._layers_tab(), "Layers")
        tabs.addTab(self._models_tab(), "Models")
        tabs.addTab(self._outputs_tab(), "Outputs")
        outer.addWidget(tabs)

        foot = QWidget()
        fl = QHBoxLayout(foot)
        fl.addWidget(QLabel(f"Element  \u00b7  <b>{self.el.name}</b>"))
        fl.addStretch(1)
        btn = QPushButton("Calculate element")
        btn.clicked.connect(lambda: self.on_calc(self.el))
        fl.addWidget(btn)
        wbtn = QPushButton("Calculate wake")
        wbtn.setToolTip("Native wake from the geometry; works on its own "
                        "(impedance is computed alongside).")
        wbtn.clicked.connect(lambda: self.on_calc(self.el, True))
        fl.addWidget(wbtn)
        outer.addWidget(foot)

    def _geometry_tab(self):
        w = QWidget(); form = QFormLayout(w)
        keys = ["length", "radius", "half_gap_mm", "material"]
        for k in list(self.el.geometry):
            if k not in keys and k != "pre_weighted":
                keys.append(k)
        for k in keys:
            ed = QLineEdit("" if self.el.geometry.get(k) is None else str(self.el.geometry.get(k)))
            ed.textChanged.connect(lambda v, key=k: self._set_geom(key, v))
            form.addRow(k.replace("_", " ") + ":", ed)
        return w

    def _set_geom(self, key, value):
        self.el.geometry[key] = _num(value)
        if key == "length":
            self.el.optics["l"] = _num(value)

    LAYER_COLS = [
        ("type", "Type"), ("thickness", "Thickness [m]"), ("sigma", "\u03c3 [S/m]"),
        ("epsr", "\u03b5r"), ("tau", "\u03c4 [s]"), ("k_Hz", "k [Hz]"),
        ("muinf_Hz", "\u03bc\u221e"), ("RQ", "RQ"),
    ]

    def _layers_tab(self):
        w = QWidget(); v = QVBoxLayout(w)
        headers = [lbl for _, lbl in self.LAYER_COLS] + ["Boundary"]
        self.ltab = QTableWidget(0, len(headers))
        self.ltab.setHorizontalHeaderLabels(headers)
        self.ltab.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.ltab.verticalHeader().setVisible(False)
        for L in self.el.layers:
            self._layer_row(L)
        self.ltab.cellChanged.connect(self._layer_edit)
        v.addWidget(self.ltab)
        row = QHBoxLayout()
        add = QPushButton("+ Add layer"); add.clicked.connect(self._add_layer)
        rm = QPushButton("Remove selected"); rm.clicked.connect(self._rm_layer)
        row.addWidget(add); row.addWidget(rm); row.addStretch(1)
        v.addLayout(row)
        v.addWidget(QLabel(
            "Wall build-up from inside out. Mark the outermost layer as Boundary "
            "(its thickness is usually \u2018inf\u2019); if none is marked, a vacuum "
            "boundary is assumed. Thickness and k accept \u2018inf\u2019."))
        return w

    def _default_layer(self):
        return {"type": "CW", "thickness": 0.002, "sigma": 5.9e7, "epsr": 1.0,
                "tau": 0.0, "k_Hz": "inf", "muinf_Hz": 0.0, "RQ": 0.0, "boundary": False}

    def _layer_row(self, L):
        r = self.ltab.rowCount(); self.ltab.insertRow(r)
        for c, (key, _) in enumerate(self.LAYER_COLS):
            val = L.get(key)
            self.ltab.setItem(r, c, QTableWidgetItem("" if val is None else str(val)))
        chk = QCheckBox(); chk.setChecked(bool(L.get("boundary")))
        chk.stateChanged.connect(lambda s, LL=L: self._set_boundary(LL, bool(s)))
        cw = QWidget(); cl = QHBoxLayout(cw); cl.addWidget(chk)
        cl.setAlignment(Qt.AlignmentFlag.AlignCenter); cl.setContentsMargins(0, 0, 0, 0)
        self.ltab.setCellWidget(r, len(self.LAYER_COLS), cw)

    def _add_layer(self):
        L = self._default_layer()
        self.el.layers.append(L); self._layer_row(L)

    def _rm_layer(self):
        r = self.ltab.currentRow()
        if r >= 0:
            self.ltab.removeRow(r); del self.el.layers[r]

    def _layer_edit(self, r, c):
        if r < len(self.el.layers) and c < len(self.LAYER_COLS):
            key = self.LAYER_COLS[c][0]
            self.el.layers[r][key] = _num(self.ltab.item(r, c).text())

    def _set_boundary(self, layer, checked):
        layer["boundary"] = checked
        if checked:                                       # keep a single boundary
            for i, other in enumerate(self.el.layers):
                if other is not layer and other.get("boundary"):
                    other["boundary"] = False
                    cw = self.ltab.cellWidget(i, len(self.LAYER_COLS))
                    box = cw.findChild(QCheckBox) if cw else None
                    if box:
                        box.blockSignals(True); box.setChecked(False); box.blockSignals(False)
        self.on_change()

    def _models_tab(self):
        w = QWidget(); v = QVBoxLayout(w)
        t = QTableWidget(len(self.el.models), 5)
        t.setHorizontalHeaderLabels(["On", "Quantity", "Method", "Source / File", "Status"])
        h = t.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        t.verticalHeader().setVisible(False)
        for r, m in enumerate(self.el.models):
            chk = QCheckBox(); chk.setChecked(m.enabled)
            chk.stateChanged.connect(lambda s, mm=m: self._set_enabled(mm, s))
            cw = QWidget(); cl = QHBoxLayout(cw); cl.addWidget(chk)
            cl.setAlignment(Qt.AlignmentFlag.AlignCenter); cl.setContentsMargins(0, 0, 0, 0)
            t.setCellWidget(r, 0, cw)
            t.setItem(r, 1, QTableWidgetItem(f"{QLABEL[m.q]}  ({QUNITS[m.q]})"))
            t.item(r, 1).setFlags(Qt.ItemFlag.ItemIsEnabled)
            combo = QComboBox(); combo.addItems(METHODS); combo.setCurrentText(m.method)
            combo.currentTextChanged.connect(lambda v, mm=m, row=r: self._set_method(mm, v, row))
            t.setCellWidget(r, 2, combo)
            fed = QLineEdit(m.file)
            fed.setPlaceholderText("path to .dat" if method_needs_file(m.method) else "\u2014")
            fed.setEnabled(method_needs_file(m.method))
            fed.textChanged.connect(lambda v, mm=m: self._set_file(mm, v))
            t.setCellWidget(r, 3, fed)
            t.setItem(r, 4, QTableWidgetItem(m.status))
        self.models_table = t
        v.addWidget(t)
        v.addWidget(QLabel("Each quantity can come from a different backend. pytlwall / IW2D "
                           "compute from geometry+layers; precalculated loads a file. "
                           "\u2018(weighted)\u2019 means the result already includes beta. "
                           "The wake is not selected here: use the Calculate wake actions."))
        return w

    def _set_enabled(self, m, state):
        m.enabled = bool(state)
        self.on_change()

    def _set_method(self, m, value, row):
        m.method = value
        needs = method_needs_file(value)
        m.status = ("missing input" if needs and not m.file else "ready")
        self.models_table.item(row, 4).setText(m.status)
        fed = self.models_table.cellWidget(row, 3)
        fed.setEnabled(needs)
        self.on_change()

    def _set_file(self, m, value):
        m.file = value
        if method_needs_file(m.method):
            m.status = "loaded" if value else "missing input"
        self.on_change()

    def _outputs_tab(self):
        return placeholder("\u25d4", "Nothing computed yet",
                           "Run Calculate to produce results, or point a quantity at a file in Models.")


# ================================================================ optics panel
class OpticsPanel(QWidget):
    def __init__(self, machine: GMachine, on_change, on_load):
        super().__init__()
        self.gm = machine
        self.on_change = on_change
        v = QVBoxLayout(self)
        have, need = optics_completeness(machine)
        top = QHBoxLayout()
        bar = QProgressBar(); bar.setMaximum(max(need, 1)); bar.setValue(have)
        bar.setFormat(f"{have}/{need} with \u03b2")
        top.addWidget(bar)
        btn = QPushButton("Load Optics\u2026"); btn.clicked.connect(on_load)
        top.addWidget(btn)
        v.addLayout(top)
        msg = ("All elements have \u03b2 and position." if have == need
               else "Some elements are missing \u03b2. Load optics or enter values below.")
        lab = QLabel(msg); lab.setObjectName("EmptyText"); v.addWidget(lab)

        rows = [e for _, e in machine.all_elements()]
        t = QTableWidget(len(rows), 5)
        t.setHorizontalHeaderLabels(["Element", "s [m]", "L [m]", "\u03b2x [m]", "\u03b2y [m]"])
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        t.verticalHeader().setVisible(False)
        self._rows = rows
        for r, e in enumerate(rows):
            name = e.name + ("  (pre-weighted)" if e.optics.get("pre") else "")
            it = QTableWidgetItem(name); it.setFlags(Qt.ItemFlag.ItemIsEnabled)
            t.setItem(r, 0, it)
            for c, key in enumerate(("s", "l", "bx", "by"), start=1):
                val = e.optics.get(key)
                t.setItem(r, c, QTableWidgetItem("" if val is None else str(val)))
        t.cellChanged.connect(self._edit)
        self.table = t
        v.addWidget(t)

    def _edit(self, r, c):
        if c == 0 or r >= len(self._rows):
            return
        key = ("s", "l", "bx", "by")[c - 1]
        self._rows[r].optics[key] = _num(self.table.item(r, c).text())
        self.on_change()


# ================================================================== inspector
class InspectorPanel(QWidget):
    def __init__(self):
        super().__init__()
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self.set_ref(None)

    def _clear(self):
        while self._lay.count():
            item = self._lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def set_ref(self, ref):
        self._clear()
        if not ref:
            self._lay.addWidget(placeholder("\u24d8", "Nothing selected",
                "Select a node to see its properties and provenance."))
            return
        kind = ref["kind"]; obj = ref["obj"]
        if kind == "element":
            o = obj.optics
            form = QWidget(); f = QFormLayout(form)
            f.addRow("name:", QLabel(obj.name))
            f.addRow("category:", QLabel(obj.category))
            f.addRow("position s:", QLabel(_fmt(o.get("s"), "m")))
            f.addRow("length:", QLabel(_fmt(o.get("l") or obj.geometry.get("length"), "m")))
            f.addRow("\u03b2x, \u03b2y:", QLabel(f"{_fmt(o.get('bx'))}, {_fmt(o.get('by'))} m"))
            f.addRow("material:", QLabel(str(obj.geometry.get("material", "\u2014"))))
            f.addRow("layers:", QLabel(str(len(obj.layers))))
            on = [QLABEL[m.q].split()[0] for m in obj.models if m.enabled]
            f.addRow("quantities on:", QLabel(", ".join(on) or "\u2014"))
            self._lay.addWidget(form)
        else:
            form = QWidget(); f = QFormLayout(form)
            f.addRow("kind:", QLabel(kind))
            f.addRow("name:", QLabel(getattr(obj, "name", "\u2014")))
            if kind == "group":
                f.addRow("elements:", QLabel(str(len(obj.elements))))
            self._lay.addWidget(form)
        self._lay.addStretch(1)


def _fmt(v, unit=""):
    if v is None:
        return "\u2014"
    return f"{v}{(' ' + unit) if unit else ''}"
