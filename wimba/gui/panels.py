"""Panel widgets for the WIMBA GUI, bound to the view-model in model.py.

Each panel edits the model in place and calls an ``on_change`` callback so the
controller (MainWindow) can refresh the tree, inspector and status bar.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFormLayout,
                             QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                             QLineEdit,
                             QListWidget, QListWidgetItem, QProgressBar,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QTabWidget, QTreeWidget, QTreeWidgetItem,
                             QVBoxLayout, QWidget)

from .. import materials
from ..core.beam import MODES, PARTICLES, Beam
from .model import (METHODS, MODE_COMPONENTS, MODE_UNITS, QLABEL, QUANTITIES,
                    QUNITS, GElement, GGroup,
                    summarize_elements,
                    GMachine, GMode, GModel, method_needs_file, new_element,
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
def _num_text(value) -> str:
    """A number as a field shows it, whatever it is at the moment.

    A cell edited by the user holds the text they typed, not a float: the panel
    stores it as typed so a half-written "1e" is not silently turned into
    something else. So this has to survive both, or reopening an element after
    an edit raises on the format string.
    """
    if value is None or value == "":
        return ""
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)


def _note(text):
    """A wrapping explanatory label.

    A QLabel reports a minimum width as wide as its longest unbroken line, so a
    sentence of guidance under a table quietly forces the panel, the tab and the
    whole window past the edge of the screen. Every note in this file goes
    through here.
    """
    label = QLabel(text)
    label.setWordWrap(True)
    label.setObjectName("EmptyText")
    label.setMinimumWidth(1)          # the text wraps; it does not set the width
    return label


class SearchCombo(QComboBox):
    """A dropdown you can type into, from the second letter on.

    Qt's own keyboard search jumps on the first keystroke and matches only the
    start of an entry: typing "st" for steel lands on "titanium" the moment the
    t is pressed. With a list that will keep growing, that is worse than no
    search. Here one letter does nothing, two or more match anywhere in the
    entry, and the buffer clears after a pause or on Escape.
    """

    RESET_MS = 1200

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._typed = ""
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self.RESET_MS)
        self._timer.timeout.connect(self._clear_typed)

    def _clear_typed(self):
        self._typed = ""

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._clear_typed()
            return super().keyPressEvent(event)
        if key == Qt.Key.Key_Backspace:
            self._typed = self._typed[:-1]
            self._timer.start()
            return
        text = event.text()
        if not text or not text.isprintable() or text.isspace():
            self._clear_typed()
            return super().keyPressEvent(event)

        self._typed += text.lower()
        self._timer.start()
        if len(self._typed) < 2:          # one letter searches nothing
            return
        for i in range(self.count()):
            if self._typed in self.itemText(i).lower():
                self.setCurrentIndex(i)
                return


class ElementPanel(QWidget):
    def __init__(self, element: GElement, on_change, on_calc, machine=None):
        """`machine` is the GMachine this element belongs to, or None for a
        component standing on its own in the bench. It decides one thing: who
        owns the beam."""
        super().__init__()
        self.el = element
        self.on_change = on_change
        self.on_calc = on_calc
        self.machine = machine
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()
        self.tabs = tabs
        self._wall_tabs = []          # indices that describe a wall, so the
                                      # Models tab can close them for a method
                                      # that has no wall to describe
        self._wall_tabs.append(tabs.addTab(self._geometry_tab(), "Geometry"))
        self._wall_tabs.append(tabs.addTab(self._layers_tab(), "Layers"))
        tabs.addTab(self._beam_tab(), "Beam & Optics")
        tabs.addTab(self._models_tab(), "Models")
        outer.addWidget(tabs)
        # the method may already be a resonator - an element read from a config,
        # or a component saved and reopened
        self._apply_method(self._base_model().method if self._base_model()
                           else "pytlwall")

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

    # pytlwall accepts exactly these three (Chamber.chamber_shape), and the
    # aperture is spelled differently for each: one radius for a circle, two
    # semi-axes otherwise. Showing the fields the shape does not use is how a
    # chamber ends up carrying a radius nobody meant.
    SHAPES = ["CIRCULAR", "ELLIPTICAL", "RECTANGULAR"]

    def _geometry_tab(self):
        w = QWidget()
        self.geo_form = QFormLayout(w)

        self.geo_form.addRow("length [m]:", self._geo_edit("length"))

        self.shape_box = QComboBox()
        self.shape_box.addItems(self.SHAPES)
        current = str(self.el.geometry.get("shape") or "CIRCULAR").upper()
        if current not in self.SHAPES:          # a config may say something else
            self.shape_box.addItem(current)
        self.shape_box.setCurrentText(current)
        self.shape_box.currentTextChanged.connect(self._set_shape)
        self.geo_form.addRow("shape:", self.shape_box)

        # rows that come and go with the shape
        self._aperture_rows = []
        self._build_aperture_rows(current)

        # anything else the element carries, so a config with unusual keys is
        # still editable - but never invented for an element that lacks it
        skip = {"length", "shape", "radius", "hor", "ver", "pre_weighted",
                "material"}
        for k in self.el.geometry:
            if k not in skip:
                self.geo_form.addRow(k.replace("_", " ") + ":", self._geo_edit(k))
        if "material" in self.el.geometry:
            lbl = QLabel("ignored: materials belong to the layers")
            lbl.setStyleSheet("color:#8A7B5C;")
            self.geo_form.addRow("material:", lbl)
        return w

    def _geo_edit(self, key, suffix=""):
        val = self.el.geometry.get(key)
        ed = QLineEdit("" if val is None else str(val))
        ed.textChanged.connect(lambda v, k=key: self._set_geom(k, v))
        if suffix:
            ed.setPlaceholderText(suffix)
        return ed

    def _build_aperture_rows(self, shape):
        """Insert the aperture fields for `shape` after the shape row."""
        for widget in self._aperture_rows:
            self.geo_form.removeRow(widget)
        self._aperture_rows = []
        at = 2                                   # after length and shape
        if shape == "CIRCULAR":
            fields = [("radius", "radius [m]:")]
        else:
            fields = [("hor", "horizontal semi-axis [m]:"),
                      ("ver", "vertical semi-axis [m]:")]
        for key, label in fields:
            ed = self._geo_edit(key)
            self.geo_form.insertRow(at, label, ed)
            self._aperture_rows.append(ed)
            at += 1

    def _set_shape(self, shape):
        self.el.geometry["shape"] = shape
        self._mark("geometry")
        self._build_aperture_rows(shape)

    def _beam_tab(self):
        """The energy and the optics this element is computed with.

        The beam is editable only for a component that belongs to no machine.
        Inside a ring there is one beam, and letting a single element carry a
        different one would compute a plausible number at an energy nobody
        chose - the machine's beam is shown here instead, read-only, so it is
        clear what the calculation will use.

        The betas are editable either way: they belong to the element.
        """
        w = QWidget(); v = QVBoxLayout(w)
        if self.machine is None:
            self.beam_panel = BeamPanel(_ElementBeam(self.el, self.on_change),
                                        self.on_change)
        else:
            own = _ElementBeam(self.el, self.on_change).beam
            machine_beam = getattr(self.machine, "beam", None)
            if own is not None and machine_beam is not None and \
                    abs(own.gamma - machine_beam.gamma) > 1e-9 * machine_beam.gamma:
                note = ("This element carries a beam of its own, and it differs "
                        "from the machine's. Its own wins for this element - "
                        "which is worth knowing before comparing it with the "
                        "rest of the ring.")
            else:
                note = ("Inside a machine the beam belongs to the ring, not to "
                        "one element: set it in the Beam panel and every device "
                        "follows it. One ring, one beam.")
            self.beam_panel = BeamPanel(self.machine, self.on_change,
                                        override=own or machine_beam, note=note)
        v.addWidget(self.beam_panel)

        box = QWidget(); form = QFormLayout(box)
        form.setContentsMargins(0, 8, 0, 0)
        for key, label, default in (("bx", "twiss beta x [m]", 1.0),
                                    ("by", "twiss beta y [m]", 1.0)):
            ed = QLineEdit()
            val = self.el.optics.get(key)
            ed.setText("" if val is None else str(val))
            ed.setPlaceholderText(f"{default:g} if left empty")
            validator = QDoubleValidator(); validator.setBottom(0.0)
            validator.setNotation(QDoubleValidator.Notation.ScientificNotation)
            ed.setValidator(validator)
            ed.textChanged.connect(lambda t, k=key: self._set_optics(k, t))
            form.addRow(label + ":", ed)
        v.addWidget(box)

        v.addWidget(_note(
            "The transverse terms are scaled by length and by the beta beside "
            "them; the longitudinal one only by length. Betas given here "
            "override whatever the twiss says at this element's position - see "
            "docs/BEAM_AND_OPTICS.md."))
        v.addStretch(1)
        return w

    def _set_optics(self, key, text):
        text = (text or "").strip()
        self.el.optics[key] = None if text == "" else _num(text)
        self._mark(key)
        self._mark("optics")

    def _mark(self, what):
        self.el.edited.add(what)

    def _set_geom(self, key, value):
        self.el.geometry[key] = _num(value)
        self._mark("geometry")
        if key == "length":
            self.el.optics["l"] = _num(value)
            self._mark("l")

    # pytlwall's Layer takes exactly these. Two of them may be infinite
    # (thickness, k); the rest are finite numbers, and its own configs say so
    # explicitly: k = 0 is not allowed and sigma = inf is not allowed.
    LAYER_COLS = [
        ("type", "Type"), ("thickness", "Thickness [m]"), ("sigma", "\u03c3 [S/m]"),
        ("epsr", "\u03b5r"), ("tau", "\u03c4 [s]"), ("k_Hz", "k [Hz]"),
        ("muinf_Hz", "\u03bc\u221e"), ("RQ", "RQ"),
    ]
    LAYER_TYPES = ["CW", "V", "PEC"]
    INFINITE_OK = {"thickness", "k_Hz"}

    def _layers_tab(self):
        w = QWidget(); v = QVBoxLayout(w)
        headers = [lbl for _, lbl in self.LAYER_COLS] + ["Boundary"]
        self.ltab = QTableWidget(0, len(headers))
        self.ltab.setHorizontalHeaderLabels(headers)
        # Nine columns do not fit a narrow panel. Stretch would squeeze them all
        # until nothing is readable; fixed widths plus a horizontal scrollbar
        # keep each one usable and let the panel be as narrow as the user wants.
        head = self.ltab.horizontalHeader()
        head.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        head.setStretchLastSection(False)
        for c, (key, _) in enumerate(self.LAYER_COLS):
            self.ltab.setColumnWidth(c, 150 if key == "type" else 96)
        self.ltab.setColumnWidth(len(self.LAYER_COLS), 74)      # Boundary
        self.ltab.setHorizontalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.ltab.verticalHeader().setVisible(False)
        self._sync_boundary()
        for L in self.el.layers:
            self._layer_row(L)
        for i, L in enumerate(self.el.layers):
            self._sync_row_enabled(i, L)
        v.addWidget(self.ltab)
        row = QHBoxLayout()
        add = QPushButton("+ Add layer"); add.clicked.connect(self._add_layer)
        rm = QPushButton("Remove selected"); rm.clicked.connect(self._rm_layer)
        row.addWidget(add); row.addWidget(rm); row.addStretch(1)
        v.addLayout(row)
        v.addWidget(_note(
            "Wall build-up from inside out. The outermost layer is the boundary "
            "and is marked automatically. Thickness and k can be set to infinity "
            "with the box beside the field; every other value is a number."))
        return w

    def _default_layer(self):
        """A new layer is a named material, not a row of bare numbers.

        pytlwall's own default conductivity is a round 1e6 that corresponds to
        no material at all; starting from something with a name means the user
        can recognise it, and change it on purpose.
        """
        L = {"type": "CW", "thickness": 0.002, "boundary": False}
        name = materials.default_name()
        if name:
            materials.apply_to(L, name)
            L["boundary"] = False
        else:
            L.update(materials.NEUTRAL, sigma=1.0e6)
        return L

    # ---- cells ----
    def _number_cell(self, L, key):
        """A numeric field, with an infinity box where pytlwall allows one.

        A free-text cell let a typo travel all the way into the solver. The
        field now takes numbers only, and infinity is a state you switch on
        rather than a word you spell.
        """
        box = QWidget(); lay = QHBoxLayout(box)
        lay.setContentsMargins(2, 0, 2, 0); lay.setSpacing(4)
        ed = QLineEdit()
        val = L.get(key)
        is_inf = str(val).strip().lower() in ("inf", "infinity", "+inf")
        ed.setText("" if val is None or is_inf else str(val))
        validator = QDoubleValidator()
        validator.setNotation(QDoubleValidator.Notation.ScientificNotation)
        if key in ("sigma", "thickness"):
            validator.setBottom(0.0)
        ed.setValidator(validator)
        ed.textChanged.connect(lambda t, LL=L, k=key: self._set_layer(LL, k, t))
        lay.addWidget(ed)

        if key in self.INFINITE_OK:
            chk = QCheckBox("\u221e")
            chk.setToolTip("Write this value as inf")
            chk.setChecked(is_inf)
            ed.setEnabled(not is_inf)
            chk.toggled.connect(
                lambda on, LL=L, k=key, e=ed: self._set_infinite(LL, k, e, on))
            lay.addWidget(chk)
        return box

    CUSTOM = "CW (custom)"

    def _type_items(self):
        """CW appears once per named material, then the two analytic types.

        V and PEC are not materials at all: pytlwall computes them from a
        formula and never looks at sigma, epsr or the rest. That is why their
        parameters looked identical - they are unused, not equal.
        """
        items = [(f"CW \u2014 {materials.label(n)}", ("CW", n))
                 for n in materials.names()]
        items.append((self.CUSTOM, ("CW", None)))
        items.append(("V (vacuum)", ("V", None)))
        items.append(("PEC (perfect conductor)", ("PEC", None)))
        return items

    def _type_cell(self, L):
        cb = SearchCombo()
        # the longest entry is a material name and would otherwise set the
        # column's minimum width; it elides, and the tooltip carries the rest
        cb.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        cb.setMinimumContentsLength(10)
        cb.setMinimumWidth(80)
        items = self._type_items()
        for text, _ in items:
            cb.addItem(text)
        cb.setProperty("payloads", [p for _, p in items])
        kind = str(L.get("type") or "CW").upper()
        if kind == "CW":
            found = materials.match(L)
            cb.setCurrentText(f"CW \u2014 {materials.label(found)}" if found
                              else self.CUSTOM)
            if found:
                cb.setToolTip(materials.note(found))
        else:
            cb.setCurrentText("V (vacuum)" if kind == "V"
                              else "PEC (perfect conductor)")
        cb.currentIndexChanged.connect(
            lambda i, LL=L, box=cb: self._set_type(LL, box, i))
        return cb

    def _set_type(self, layer, box, index):
        kind, material = box.property("payloads")[index]
        layer["type"] = kind
        if material:
            materials.apply_to(layer, material)
            box.setToolTip(materials.note(material))
        else:
            box.setToolTip("")
        if kind in ("V", "PEC"):
            # pytlwall computes these from a formula and reads none of the
            # material parameters. Leaving numbers behind would put values in
            # the config that no calculation ever used.
            for key in materials.PARAMS:
                layer.pop(key, None)
        self._mark("layers")
        self._refresh_layers()

    def _layer_row(self, L):
        r = self.ltab.rowCount(); self.ltab.insertRow(r)
        for c, (key, _) in enumerate(self.LAYER_COLS):
            cell = self._type_cell(L) if key == "type" else self._number_cell(L, key)
            self.ltab.setCellWidget(r, c, cell)
        chk = QCheckBox(); chk.setChecked(bool(L.get("boundary")))
        chk.setEnabled(False)                    # the outermost layer decides it
        chk.setToolTip("The outermost layer is the boundary.")
        cw = QWidget(); cl = QHBoxLayout(cw); cl.addWidget(chk)
        cl.setAlignment(Qt.AlignmentFlag.AlignCenter); cl.setContentsMargins(0, 0, 0, 0)
        self.ltab.setCellWidget(r, len(self.LAYER_COLS), cw)

    def _set_layer(self, layer, key, text):
        text = (text or "").strip()
        layer[key] = None if text == "" else _num(text)
        self._mark("layers")
        if key in materials.PARAMS:
            # The catalogue is not edited from here. A hand-changed parameter
            # means this layer is no longer that material - the entry stays as
            # it was, and the row is shown as custom.
            self._retitle_type(layer)

    def _retitle_type(self, layer):
        row = self._row_of(layer)
        if row is None:
            return
        box = self.ltab.cellWidget(row, 0)
        if not isinstance(box, QComboBox):
            return
        found = materials.match(layer)
        box.blockSignals(True)
        box.setCurrentText(f"CW \u2014 {materials.label(found)}" if found
                           else self.CUSTOM)
        box.blockSignals(False)
        box.setToolTip(materials.note(found) if found else "")

    def _row_of(self, layer):
        for i, L in enumerate(self.el.layers):
            if L is layer:
                return i
        return None

    def _refresh_layers(self):
        """Redraw the rows from the model, keeping the selection.

        The model is already correct when this runs: _sync_boundary decides what
        the layers are, this only shows them.
        """
        row = self.ltab.currentRow()
        self.ltab.setRowCount(0)
        for L in self.el.layers:
            self._layer_row(L)
        for i, L in enumerate(self.el.layers):
            self._sync_row_enabled(i, L)
        if 0 <= row < self.ltab.rowCount():
            self.ltab.setCurrentCell(row, 0)

    def _set_infinite(self, layer, key, editor, on):
        editor.setEnabled(not on)
        if on:
            layer[key] = "inf"
        else:
            layer[key] = _num(editor.text()) if editor.text().strip() else None
        self._mark("layers")

    def _add_layer(self):
        self.el.layers.append(self._default_layer())
        self._sync_boundary()
        self._refresh_layers()
        self._mark("layers")

    def _rm_layer(self):
        r = self.ltab.currentRow()
        if r >= 0:
            del self.el.layers[r]
            self._sync_boundary()
            self._refresh_layers()
            self._mark("layers")

    FINITE_THICKNESS = 0.002

    def _sync_boundary(self):
        """The outermost layer is the boundary - always, and only it.

        pytlwall's chamber has a boundary section of its own, so a wall with no
        layer marked was being computed against an implicit vacuum. Leaving the
        choice to a checkbox meant a single-layer chamber - the commonest case
        of all - was wrong by default.

        The boundary has no thickness: it is the half-space outside the wall,
        and pytlwall's own [boundary] section states no thick_m at all. It is
        written as inf. A layer that STOPS being the boundary must lose that
        infinity again - otherwise adding a second layer leaves the first one
        infinitely thick, which is not a wall at all.
        """
        last = len(self.el.layers) - 1
        for i, L in enumerate(self.el.layers):
            was = bool(L.get("boundary"))
            now = (i == last)
            L["boundary"] = now
            if now:
                L["thickness"] = "inf"
            elif was or str(L.get("thickness", "")).strip().lower() == "inf":
                L["thickness"] = self.FINITE_THICKNESS
        if self.el.layers:
            self._mark("layers")

    def _sync_row_enabled(self, row, layer):
        """Close the fields that cannot mean anything for this row.

        A V or PEC layer is computed from a formula: pytlwall reads none of
        sigma, epsr, tau, k, mu-infinity or RQ for it. Leaving them editable
        invites the reasonable question of why vacuum and a perfect conductor
        have the same numbers - they have the same numbers because nothing
        reads them.
        """
        kind = str(layer.get("type") or "CW").upper()
        material_cells = kind == "CW"
        is_boundary = bool(layer.get("boundary"))
        for c, (key, _) in enumerate(self.LAYER_COLS):
            if key == "type":
                continue
            cell = self.ltab.cellWidget(row, c)
            if cell is None:
                continue
            editor = cell.findChild(QLineEdit)
            check = cell.findChild(QCheckBox)
            if key == "thickness":
                on = not is_boundary
                if editor:
                    editor.setEnabled(on)
                    if is_boundary:
                        editor.blockSignals(True); editor.clear()
                        editor.blockSignals(False)
                if check:
                    check.blockSignals(True)
                    check.setChecked(is_boundary or
                                     str(layer.get("thickness")).lower() == "inf")
                    check.setEnabled(on)
                    check.blockSignals(False)
                if is_boundary:
                    cell.setToolTip("The boundary is the half-space outside "
                                    "the wall: its thickness is infinite.")
                continue
            if editor:
                editor.setEnabled(material_cells)
            if check:
                check.setEnabled(material_cells)
            if not material_cells:
                cell.setToolTip(f"{kind} is computed from a formula; this "
                                f"value is not read.")

    # A chamber method computes every component in one go, so asking for one of
    # them is a way of labelling the curve, not of doing less work. All
    # Impedance says that plainly and is the sensible default; the single
    # components matter for a precalculated file, which holds one of them.
    ALL_IMPEDANCE = "All impedance"
    ALL_WAKE = "All wake"
    COMPARE_COMPONENTS = [ALL_IMPEDANCE, "ZLong", "ZDipX", "ZDipY", "ZQuadX",
                          "ZQuadY",
                          # the wake half of the list. A wake comparison makes
                          # the calculation compute the wake, because without a
                          # time grid it would produce an empty column.
                          ALL_WAKE, "WLong", "WDipX", "WDipY", "WQuadX",
                          "WQuadY"]

    def _base_model(self):
        return self.el.models[0] if self.el.models else None

    def _models_tab(self):
        from .model import method_base, method_needs_file
        w = QWidget(); v = QVBoxLayout(w)

        base = QTableWidget(2, 3)
        base.setHorizontalHeaderLabels(["Variable", "Method", "Source / File"])
        h = base.horizontalHeader()
        for c in range(3):
            h.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)
        base.verticalHeader().setVisible(False)

        bm = self._base_model()
        cur = bm.method if bm else "pytlwall"
        it = QTableWidgetItem("Impedance  (all components)")
        it.setFlags(Qt.ItemFlag.ItemIsEnabled)
        base.setItem(0, 0, it)
        combo = QComboBox(); combo.addItems(METHODS); combo.setCurrentText(cur)
        combo.currentTextChanged.connect(self._set_base_method)
        base.setCellWidget(0, 1, combo)
        fed = QLineEdit(bm.file if bm else "")
        fed.setPlaceholderText("path to .dat" if method_needs_file(cur) else "\u2014")
        fed.setEnabled(method_needs_file(cur))
        fed.textChanged.connect(self._set_base_file)
        base.setCellWidget(0, 2, fed)
        self._base_file_edit = fed

        it = QTableWidgetItem("Wakefield")
        it.setFlags(Qt.ItemFlag.ItemIsEnabled)
        base.setItem(1, 0, it)
        self._wake_label = QTableWidgetItem(self._wake_text(cur))
        self._wake_label.setFlags(Qt.ItemFlag.ItemIsEnabled)
        base.setItem(1, 1, self._wake_label)
        wk = QTableWidgetItem("\u2014")
        wk.setFlags(Qt.ItemFlag.ItemIsEnabled)
        base.setItem(1, 2, wk)
        base.setMaximumHeight(96)
        v.addWidget(base)

        v.addWidget(self._modes_box())

        v.addWidget(_note("<b>Additional calculations \u2014 compare</b>  "
                          "(same element, other methods: plotted side by side)"))
        self.cmp_table = QTableWidget(0, 3)
        self.cmp_table.setHorizontalHeaderLabels(["Component", "Method", "Source / File"])
        ch = self.cmp_table.horizontalHeader()
        for c in range(3):
            ch.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)
        self.cmp_table.verticalHeader().setVisible(False)
        for entry in self.el.compare:
            self._cmp_row(entry)
        v.addWidget(self.cmp_table, 1)
        row = QHBoxLayout()
        add = QPushButton("+ Add"); add.clicked.connect(self._cmp_add)
        rm = QPushButton("Remove selected"); rm.clicked.connect(self._cmp_rm)
        row.addWidget(add); row.addWidget(rm); row.addStretch(1)
        v.addLayout(row)
        v.addWidget(_note(
            "The base method computes every component (and its wake). Compare "
            "entries add the same element with another method, for one "
            "component or for all of them. Choosing a wake component makes the "
            "calculation compute the wake too \u2014 without a time grid a wake "
            "comparison would come out empty."))
        return w

    # ---------------- resonator modes ----------------
    #: Column order of the modes table. Rs carries the unit of its component,
    #: so the header says the component and the cell tooltip says the unit.
    MODE_COLS = [("q", "Component"), ("Rs", "Rs"), ("Q", "Q"), ("fr", "f_r [Hz]")]

    def _modes_box(self):
        """The editor for a resonator: what defines the element, in place of a
        geometry.

        Read-only inside a machine, for the same reason the beam is: the modes
        came from the config the machine was loaded from, and editing them here
        would change a number the file still states.
        """
        box = QGroupBox("Resonator modes")
        v = QVBoxLayout(box)
        self.modes_tab = QTableWidget(0, len(self.MODE_COLS))
        self.modes_tab.setHorizontalHeaderLabels([lbl for _, lbl in self.MODE_COLS])
        head = self.modes_tab.horizontalHeader()
        for c in range(len(self.MODE_COLS)):
            head.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)
        self.modes_tab.verticalHeader().setVisible(False)
        self.modes_tab.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        for mode in self.el.modes:
            self._mode_row(mode)
        v.addWidget(self.modes_tab, 1)

        self._mode_buttons = QWidget()
        row = QHBoxLayout(self._mode_buttons)
        row.setContentsMargins(0, 0, 0, 0)
        add = QPushButton("+ Add mode"); add.clicked.connect(self._mode_add)
        rm = QPushButton("Remove selected"); rm.clicked.connect(self._mode_rm)
        row.addWidget(add); row.addWidget(rm); row.addStretch(1)
        v.addWidget(self._mode_buttons)

        self._mode_note = _note(
            "One row is one resonance of one component; rows sum. Rs is an "
            "impedance longitudinally and an impedance per metre "
            "transversally, Q is the quality factor, f_r the resonant "
            "frequency. Geometry and Layers are closed while the method is "
            "resonator \u2014 nothing reads them \u2014 but they are kept, so "
            "switching back to a wall finds the wall as you left it.")
        v.addWidget(self._mode_note)
        self.modes_box = box
        return box

    def _mode_row(self, mode: GMode):
        r = self.modes_tab.rowCount()
        self.modes_tab.insertRow(r)
        editable = self.machine is None

        comp = QComboBox(); comp.addItems(list(MODE_COMPONENTS))
        comp.setCurrentText(mode.q if mode.q in MODE_COMPONENTS else "ZLong")
        comp.setEnabled(editable)
        comp.currentTextChanged.connect(
            lambda val, m=mode: self._set_mode(m, "q", val))
        self.modes_tab.setCellWidget(r, 0, comp)

        for c, (key, _lbl) in enumerate(self.MODE_COLS[1:], start=1):
            ed = QLineEdit(_num_text(getattr(mode, key)))
            val = QDoubleValidator()
            val.setNotation(QDoubleValidator.Notation.ScientificNotation)
            if key in ("Q", "fr"):
                val.setBottom(0.0)      # both divide: zero is not a value
            ed.setValidator(val)
            ed.setReadOnly(not editable)
            if key == "Rs":
                ed.setToolTip("Shunt impedance: \u03a9 for ZLong, \u03a9/m for "
                              "the transverse components")
            ed.textChanged.connect(
                lambda t, m=mode, k=key: self._set_mode(m, k, t))
            self.modes_tab.setCellWidget(r, c, ed)

    def _set_mode(self, mode: GMode, key, value):
        if key == "q":
            mode.q = value
            self._mode_units()
        else:
            setattr(mode, key, value)
        self.el.edited.add("modes")
        self.on_change()

    def _mode_units(self):
        """Keep the Rs tooltip honest when a row changes component."""
        for r in range(self.modes_tab.rowCount()):
            comp = self.modes_tab.cellWidget(r, 0)
            ed = self.modes_tab.cellWidget(r, 1)
            if comp is not None and ed is not None:
                ed.setToolTip(f"Shunt impedance [{MODE_UNITS.get(comp.currentText(), '')}]")

    def _mode_add(self):
        mode = GMode()
        self.el.modes.append(mode)
        self._mode_row(mode)
        self.el.edited.add("modes")
        self.on_change()

    def _mode_rm(self):
        rows = sorted({i.row() for i in self.modes_tab.selectedIndexes()},
                      reverse=True)
        for r in rows:
            if 0 <= r < len(self.el.modes):
                del self.el.modes[r]
            self.modes_tab.removeRow(r)
        if rows:
            self.el.edited.add("modes")
            self.on_change()

    def _apply_method(self, method):
        """Show what the chosen method actually reads, and close what it does not.

        The four methods are not four ways of computing one element: they are
        four kinds of element. pytlwall and IW2D solve a wall, so they read the
        geometry and the layers; a resonator is a mode spectrum and reads
        neither; precalculated reads a file. Leaving all the panels open for
        every method is how a user fills in a chamber and then wonders why the
        numbers do not depend on it.
        """
        from .model import method_base
        base = method_base(method).lower()
        is_res = base == "resonator"
        self.modes_box.setVisible(is_res)
        self._mode_buttons.setVisible(is_res and self.machine is None)
        if is_res and self.machine is not None:
            self._mode_note.setText(
                "These modes come from the config this machine was loaded "
                "from, so they are shown and not edited. A resonator of your "
                "own goes in the Component bench (Component \u25b8 New "
                "Component).")
        for i in self._wall_tabs:
            self.tabs.setTabEnabled(i, not is_res)
            self.tabs.setTabToolTip(
                i, "A resonator has no wall: nothing here is read while the "
                   "method is resonator." if is_res else "")
        if is_res and self.tabs.currentIndex() in self._wall_tabs:
            # opening an element whose method is already resonator would
            # otherwise land the user on a tab that is greyed out and says
            # nothing about why
            self.tabs.setCurrentIndex(self.tabs.count() - 1)      # Models
        if is_res and not self.el.modes and self.machine is None:
            # an empty table says nothing about what is missing; one blank row
            # is the shape of the answer
            self._mode_add()

    @staticmethod
    def _wake_text(method):
        """What will actually produce the wake, not what the engine could do.

        IW2D's algorithm does compute wakes - with a Filon-type method, in its
        C++ executables - but its Python package does not: the legacy
        wake_roundchamber / wake_flatchamber wrappers are stubs and the
        supported API has no wake call at all. WIMBA drives that package, so an
        IW2D wake is a Fourier transform of the impedance, and the panel says
        so instead of promising a native one.
        """
        from .model import method_base
        b = method_base(method).lower()
        if b == "precalculated":
            return "from wake file if given, else FFT of the impedance"
        if b == "iw2d":
            return "WIMBA FFT of the impedance (IW2D's Python package computes "\
                   "no wake)"
        return f"native from {method_base(method)}"

    def _set_base_method(self, value):
        from .model import method_needs_file
        for m in self.el.models:
            m.method = value
        self._wake_label.setText(self._wake_text(value))
        self._base_file_edit.setEnabled(method_needs_file(value))
        self._apply_method(value)
        self.on_change()

    def _set_base_file(self, value):
        for m in self.el.models:
            m.file = value
        self.on_change()

    def _cmp_row(self, entry):
        from .model import method_needs_file
        r = self.cmp_table.rowCount(); self.cmp_table.insertRow(r)
        comp = QComboBox(); comp.addItems(self.COMPARE_COMPONENTS)
        comp.setCurrentText(entry.q or self.ALL_IMPEDANCE)
        comp.setToolTip(
            "All impedance / All wake compute every component at once; a "
            "single one is what a precalculated file holds.\n"
            "Choosing a wake makes the calculation compute the wake as well.")
        comp.currentTextChanged.connect(lambda v, e=entry: setattr(e, "q", v))
        self.cmp_table.setCellWidget(r, 0, comp)
        meth = QComboBox(); meth.addItems(METHODS); meth.setCurrentText(entry.method)
        self.cmp_table.setCellWidget(r, 1, meth)
        # where this row's wake would come from is not guessable from the
        # method name: pytlwall solves it, IW2D's Python package does not
        comp.currentTextChanged.connect(
            lambda _v, c=comp, m=meth: self._cmp_wake_note(c, m))
        meth.currentTextChanged.connect(
            lambda _v, c=comp, m=meth: self._cmp_wake_note(c, m))
        self._cmp_wake_note(comp, meth)
        cell = QWidget(); cl = QHBoxLayout(cell); cl.setContentsMargins(0, 0, 0, 0)
        fed = QLineEdit(entry.file)
        fed.setEnabled(method_needs_file(entry.method))
        fed.setPlaceholderText("path to .dat / .yaml map"
                               if method_needs_file(entry.method) else "\u2014")
        fed.textChanged.connect(lambda v, e=entry: setattr(e, "file", v))
        browse = QPushButton("\u2026"); browse.setMaximumWidth(28)
        browse.setEnabled(method_needs_file(entry.method))
        browse.clicked.connect(lambda _=False, e=entry, f=fed: self._cmp_browse(e, f))
        cl.addWidget(fed, 1); cl.addWidget(browse)
        self.cmp_table.setCellWidget(r, 2, cell)

        def _meth_changed(v, e=entry, f=fed, b=browse):
            e.method = v
            f.setEnabled(method_needs_file(v))
            b.setEnabled(method_needs_file(v))
            f.setPlaceholderText("path to .dat / .yaml map"
                                 if method_needs_file(v) else "\u2014")
            self.on_change()
        meth.currentTextChanged.connect(_meth_changed)

    def _cmp_wake_note(self, comp, meth):
        """Say in the row where its wake comes from.

        pytlwall computes the wake natively; IW2D's Python package has no wake
        solver, so WIMBA transforms its impedance. Comparing the two on a wake
        is comparing a solver with a Fourier transform - worth doing, not worth
        discovering afterwards.
        """
        from .model import is_wake_component, method_base
        if not is_wake_component(comp.currentText()):
            comp.setStyleSheet("")
            return
        base = method_base(meth.currentText()).lower()
        if base == "iw2d":
            comp.setToolTip("Wake from WIMBA's FFT of the IW2D impedance: "
                            "IW2D's Python package computes no wake.")
        elif base == "precalculated":
            comp.setToolTip("Wake read from the file, interpolated onto the "
                            "time grid.")
        else:
            comp.setToolTip(f"Wake computed natively by {method_base(meth.currentText())}.")

    def _cmp_browse(self, entry, fed):
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Precalculated data", "",
            "Data or import map (*.dat *.txt *.csv *.xlsx *.xlsm *.yaml *.yml);;"
            "Spreadsheet (*.xlsx *.xlsm);;All files (*)")
        if not path:
            return
        if not path.lower().endswith((".yaml", ".yml")):
            # a spreadsheet or an export with named columns describes itself:
            # no import map is needed to find the component
            from ..sources.precalculated_bridge import precalculated_components
            comps = precalculated_components(path)
            if entry.q in comps:
                entry.file = path
                fed.setText(path)
                self.on_change()
                return
            from .import_dialog import ImportMapDialog
            dlg = ImportMapDialog(path, self)
            if not (dlg.exec() and dlg.map_path):
                return
            path = str(dlg.map_path)
        entry.file = path
        fed.setText(path)
        self.on_change()

    def _cmp_add(self):
        entry = GModel(q="ZLong", enabled=True, method="precalculated")
        self.el.compare.append(entry)
        self._cmp_row(entry)
        self.on_change()

    def _cmp_rm(self):
        r = self.cmp_table.currentRow()
        if r >= 0:
            self.cmp_table.removeRow(r)
            del self.el.compare[r]
            self.on_change()


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
        v.addWidget(_note(msg))
        v.addWidget(self._mean_box())

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

    # ---- the average the transverse weights are divided by ------------------

    #: How each source of the average reads in the panel.
    _MEAN_SOURCE = {
        "smooth_beta": "stated below",
        "lattice": "averaged over the optics file",
        "elements": "estimated from the elements themselves",
        "none": "no optics and none stated",
    }

    def _mean_box(self):
        """Show the average beta, and let the user state one of their own.

        Every transverse weight is beta over this, so it belongs beside the
        optics rather than beside the beam: it is a property of the lattice. The
        computed value is shown and never edited -- it is derived, and typing
        over it would only mean it was no longer what it says it is. Stating a
        value is a separate act, in the two fields below it.
        """
        box = QGroupBox("Average \u03b2  \u2014  every transverse weight is \u03b2 / \u03b2\u0304")
        f = QFormLayout(box)
        computed = self.gm.beta_mean
        lab = QLabel(f"{computed[0]:.6g}, {computed[1]:.6g} m   "
                     f"({self._MEAN_SOURCE.get(self.gm.beta_mean_source, '')})")
        lab.setEnabled(False)                      # derived: readable, not editable
        f.addRow("WIMBA's own:", lab)

        row = QHBoxLayout()
        self.sb_x, self.sb_y = QLineEdit(), QLineEdit()
        for w, i in ((self.sb_x, 0), (self.sb_y, 1)):
            w.setPlaceholderText("\u2014")
            # a beta is a positive length: no letters, no sign, no zero. The
            # validator refuses them as they are typed, so the panel never holds
            # a value the calculation would have to reject later.
            v = QDoubleValidator()
            v.setBottom(0.0)
            v.setNotation(QDoubleValidator.Notation.ScientificNotation)
            w.setValidator(v)
            if self.gm.smooth_beta:
                w.setText(f"{self.gm.smooth_beta[i]:.6g}")
            w.editingFinished.connect(self._smooth_edited)
            row.addWidget(w)
        holder = QWidget(); holder.setLayout(row)
        f.addRow("\u03b2\u0304x, \u03b2\u0304y (yours, used when set):", holder)
        return box

    def _smooth_edited(self):
        """Both fields, or neither: one plane alone is not an average.

        What the calculation ends up dividing by is said on the Console, not
        here: the two values are already on screen a line above, and repeating
        them under the fields only says the same thing a third time.
        """
        import logging

        log = logging.getLogger("wimba.gui")
        x, y = _num(self.sb_x.text()), _num(self.sb_y.text())
        for value, plane in ((x, "\u03b2\u0304x"), (y, "\u03b2\u0304y")):
            if value is not None and float(value) <= 0.0:
                log.warning("%s must be a positive length; ignoring %s.", plane, value)
                return
        if x is None and y is None:
            if self.gm.smooth_beta is None:
                return
            self.gm.smooth_beta = None
            log.info("Average \u03b2 cleared: computing with WIMBA's own, "
                     "%.6g, %.6g m (%s).", self.gm.beta_mean[0],
                     self.gm.beta_mean[1], self.gm.beta_mean_source)
        elif x is None or y is None:
            log.warning("Both \u03b2\u0304x and \u03b2\u0304y are needed: the two planes "
                        "have different tunes, so different averages.")
            return
        else:
            self.gm.smooth_beta = (float(x), float(y))
            log.info("Average \u03b2 set: computing with \u03b2\u0304 = %.6g, %.6g m "
                     "(yours).", float(x), float(y))
        self.on_change()

    def _edit(self, r, c):
        if c == 0 or r >= len(self._rows):
            return
        key = ("s", "l", "bx", "by")[c - 1]
        el = self._rows[r]
        el.optics[key] = _num(self.table.item(r, c).text())
        el.edited.add(key)          # user-set, so it may be written to the config
        self.on_change()


# ================================================================== scenarios
class ScenarioPanel(QWidget):
    """The scenarios in the open project, and the buttons that manage them.

    New scenarios exist only as duplicates of an existing one. That is a
    deliberate restriction, not a missing feature: two scenarios are only worth
    plotting together when they started from the same machine and differ in
    something the user chose, and duplication is what guarantees it.
    """

    def __init__(self, project, on_pick, on_duplicate, on_rename, on_remove):
        super().__init__()
        v = QVBoxLayout(self)
        head = QLabel(f"Project: {project.name}")
        head.setObjectName("EmptyTitle")
        v.addWidget(head)
        where = QLabel(project.dir); where.setObjectName("EmptyText")
        where.setWordWrap(True); v.addWidget(where)

        self.list = QListWidget()
        for sc in project.scenarios:
            bits = []
            if sc.beam is not None:
                bits.append(sc.beam.label())
            if sc.derived_from:
                bits.append(f"from {sc.derived_from}")
            if sc.computed_at:
                bits.append("computed")
            text = sc.label + (f"   \u2014 {', '.join(bits)}" if bits else "")
            self.list.addItem(QListWidgetItem(text))
        if project.scenarios:
            self.list.setCurrentRow(project.current)
        self.list.currentRowChanged.connect(on_pick)
        v.addWidget(self.list)

        row = QHBoxLayout()
        for label, slot, enabled in (("Duplicate", on_duplicate, bool(project.scenarios)),
                                     ("Rename", on_rename, bool(project.scenarios)),
                                     ("Remove", on_remove, len(project.scenarios) > 1)):
            b = QPushButton(label); b.clicked.connect(slot); b.setEnabled(enabled)
            row.addWidget(b)
        v.addLayout(row)

        if not project.scenarios:
            hint = _note("Load a machine or open a config: it becomes Scenario 1.")
            hint.setObjectName("EmptyText"); hint.setWordWrap(True)
            v.addWidget(hint)
        else:
            grid = project.grid.get("frequency") or {}
            if grid:
                span = " .. ".join(f"{v:g}" if isinstance(v, float) else str(v)
                                   for v in (grid.get("min"), grid.get("max")))
                lab = QLabel(f"Shared grid: {span} Hz, {grid.get('n')} points "
                             f"\u2014 the same for every scenario, which is what "
                             f"makes them comparable.")
                lab.setObjectName("EmptyText"); lab.setWordWrap(True)
                v.addWidget(lab)
        return


# ====================================================================== beam
# what each mode is called on screen, and the unit shown next to the field
_MODE_LABELS = [("gamma", "\u03b3 (relativistic)", ""),
                ("beta", "\u03b2 (v/c)", ""),
                ("energy", "total energy", "GeV"),
                ("kinetic", "kinetic energy", "GeV"),
                ("momentum", "momentum", "GeV/c")]
_GeV = {"energy", "kinetic", "momentum"}     # entered in GeV, stored in eV


class _ElementBeam:
    """Lets BeamPanel edit a lone component's beam.

    BeamPanel writes to `machine.beam`; a component built in the bench has no
    machine, which is why a manually created component could not be given an
    energy at all and its saved config came out with no beam. The element keeps
    its own in `own_base`, where component_config already looks for it - so a
    component that carries a beam wins over whatever the open config says,
    which is the rule the bench follows everywhere else.
    """

    def __init__(self, element: GElement, on_change):
        self._el = element
        self._on_change = on_change

    @property
    def beam(self):
        cached = self._el.own_base.get("_beam_obj")
        if cached is not None:
            return cached
        data = self._el.own_base.get("beam")
        if data:
            try:
                return Beam.from_dict(data)
            except (ValueError, KeyError):
                return None
        gamma = self._el.own_base.get("gamma")
        if gamma is None:
            return None
        try:
            return Beam("proton", "gamma", float(gamma))
        except ValueError:
            return None

    @beam.setter
    def beam(self, beam):
        self._el.own_base["_beam_obj"] = beam
        self._el.own_base["beam"] = beam.to_dict()
        self._el.own_base["gamma"] = beam.gamma
        self._el.edited.add("beam")


class BeamPanel(QWidget):
    """Particle and one number: the beam a calculation is run with.

    Only one of gamma / beta / energy / kinetic / momentum is editable at a time -
    they are the same degree of freedom - and the rest are shown derived. The
    field turns red with the reason when the value cannot pin down what would be
    derived from it (beta at LHC energies, gamma at ELENA energies); nothing is
    stored until it is valid, so a machine never silently carries a beam that the
    core would refuse.
    """

    def __init__(self, machine: GMachine, on_change, override: Beam = None,
                 note: str = ""):
        super().__init__()
        self.gm = machine
        self.on_change = on_change
        self.override = override          # a component's own beam, if it has one
        self._loading = True

        v = QVBoxLayout(self)
        form = QFormLayout()

        self.particle = QComboBox()
        self.particle.addItems(sorted(PARTICLES))
        self.particle.setCurrentText("proton")     # the list is alphabetical, and
        form.addRow("Particle", self.particle)     # "antiproton" is a poor default

        self.mode = QComboBox()
        for key, label, unit in _MODE_LABELS:
            self.mode.addItem(f"{label} [{unit}]" if unit else label, key)
        form.addRow("Given as", self.mode)

        self.value = QLineEdit()
        self.value.setPlaceholderText("e.g. 7461")
        form.addRow("Value", self.value)
        v.addLayout(form)

        self.error = QLabel(); self.error.setObjectName("BeamError")
        self.error.setWordWrap(True); self.error.setVisible(False)
        v.addWidget(self.error)

        self.derived = QLabel(); self.derived.setObjectName("EmptyText")
        self.derived.setWordWrap(True)
        v.addWidget(self.derived)

        if override is not None:
            for w in (self.particle, self.mode, self.value):
                w.setEnabled(False)          # read-only: not this machine's beam
            v.addWidget(_note(
                note or "This component carries its own beam, from the config "
                        "it was loaded with. That beam wins over the machine's "
                        "for every calculation of this component."))
        v.addStretch(1)

        self._load(override or getattr(machine, "beam", None))
        self._loading = False
        self.particle.currentTextChanged.connect(self._edited)
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.value.editingFinished.connect(self._edited)
        self.value.textEdited.connect(self._preview)

    # ---- state ----
    def _load(self, beam):
        if beam is None:
            self._show_derived(None)
            return
        self.particle.setCurrentText(beam.particle)
        idx = self.mode.findData(beam.mode)
        self.mode.setCurrentIndex(idx if idx >= 0 else 0)
        self.value.setText(_beam_text(beam))
        self._show_derived(beam)

    def _mode_changed(self):
        """Switching mode re-expresses the beam it already has, rather than
        clearing it: asking for beta after entering gamma is a question, not an
        edit.

        Some of those questions have no good answer - beta cannot express an LHC
        beam - and then the honest reply is to say so and keep the beam that is
        already set, rather than storing a number that means something else.
        """
        if self._loading:
            return
        current = getattr(self.gm, "beam", None)
        mode = self.mode.currentData()
        if current is None:
            self._edited()
            return
        value = {"gamma": current.gamma, "beta": current.beta,
                 "energy": current.energy_eV, "kinetic": current.kinetic_eV,
                 "momentum": current.momentum_eV}[mode]
        shown = value / 1.0e9 if mode in _GeV else value
        self.value.setText(f"{shown:.12g}")
        beam, err = self._parse()
        if beam is None:
            label = dict((k, l) for k, l, _ in _MODE_LABELS)[mode]
            self._show_derived(current, f"This beam cannot be written as {label}: "
                                        f"{err} Still using {current.label()}.")
            return
        self._edited()

    def _preview(self, _text=""):
        """Live feedback while typing, without storing anything."""
        beam, err = self._parse()
        self._show_derived(beam, err, transient=True)

    def _edited(self):
        beam, err = self._parse()
        self._show_derived(beam, err)
        if beam is None:
            return
        self.gm.beam = beam
        if not self._loading:
            self.on_change()

    def _parse(self):
        text = self.value.text().strip()
        if not text:
            return None, ""
        mode = self.mode.currentData()
        try:
            value = float(text)
        except ValueError:
            return None, f"'{text}' is not a number."
        shown = text
        if mode in _GeV:
            value *= 1.0e9                      # GeV on screen, eV inside
            shown = None                        # digit count refers to the GeV form
        try:
            return Beam(self.particle.currentText(), mode, value, text=shown), ""
        except ValueError as exc:
            return None, str(exc)

    def _show_derived(self, beam, err="", transient=False):
        self.error.setVisible(bool(err))
        self.error.setText(err)
        if beam is None:
            self.derived.setText(
                "No beam set: calculations will refuse to run until one is."
                if not err else "")
            return
        one_minus = beam.one_minus_beta
        beta = (f"\u03b2 = {beam.beta:.12g}" if one_minus > 1e-6
                else f"1 \u2212 \u03b2 = {one_minus:.4g}")
        self.derived.setText(
            f"\u03b3 = {beam.gamma:.10g}   {beta}\n"
            f"E = {beam.energy_eV / 1e9:.6g} GeV   "
            f"T = {beam.kinetic_eV / 1e9:.6g} GeV   "
            f"p = {beam.momentum_eV / 1e9:.6g} GeV/c"
            + ("   (not stored yet)" if transient else ""))


def _beam_text(beam) -> str:
    value = beam.value / 1.0e9 if beam.mode in _GeV else beam.value
    return beam.text or f"{value:.12g}"


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
            # no chamber-level material: materials belong to the layers, and the
            # Geometry panel stopped offering that field
            f.addRow("layers:", QLabel(str(len(obj.layers))))
            on = [QLABEL[m.q].split()[0] for m in obj.models if m.enabled]
            f.addRow("quantities on:", QLabel(", ".join(on) or "\u2014"))
            self._lay.addWidget(form)
        else:
            form = QWidget(); f = QFormLayout(form)
            f.addRow("kind:", QLabel(kind))
            f.addRow("name:", QLabel(getattr(obj, "name", "\u2014")))
            if kind == "group":
                self._summary(f, obj.elements)
            elif kind == "machine":
                groups = getattr(obj, "groups", [])
                f.addRow("groups:", QLabel(str(len(groups))))
                beam = getattr(obj, "beam", None)
                f.addRow("beam:", QLabel(beam.label() if beam else
                                         "\u2014 not stated"))
                self._summary(f, [e for _g, e in obj.all_elements()])
            self._lay.addWidget(form)
        self._lay.addStretch(1)

    def _summary(self, f, elements):
        """The aggregates for a set of elements.

        A group carries nothing but a name and its members, so what is worth
        knowing about one -- where it sits, how much ring it covers, what it is
        made of, whether the optics reached it -- has to be summed up from them.
        """
        pipes = [e for e in elements
                 if getattr(e, "category", "") == "default_pipe"]
        if pipes and len(pipes) == len(elements):
            return self._pipe_summary(f, pipes[0])

        s = summarize_elements(elements)
        count = str(s["n"] - s["n_pipe"])
        if s["n_pipe"]:
            count += "   (plus the default pipe, summarized on its own)"
        f.addRow("elements:", QLabel(count))

        if s["span"]:
            lo, hi = s["span"]
            f.addRow("extent:", QLabel(f"{lo:.6g} \u2192 {hi:.6g} m"))
        if s["length"] is not None:
            f.addRow("modelled length:", QLabel(f"{s['length']:.6g} m"))
        if s["methods"]:
            f.addRow("made of:", QLabel(", ".join(
                f"{n} {name}" for name, n in sorted(s["methods"].items()))))

        if s["beta_of"]:
            line = f"{s['beta_have']} of {s['beta_of']}"
            if s["beta_range"]:
                lo, hi = s["beta_range"]
                line += f"   (\u03b2 {lo:.4g} \u2013 {hi:.4g} m)"
            f.addRow("with \u03b2x and \u03b2y:", QLabel(line))

        if s["quantities"]:
            names = ", ".join(QLABEL[q].split()[0] for q in s["quantities"])
            if s["mixed"]:
                names += "   (mixed: not every element has the same set)"
            f.addRow("quantities on:", QLabel(names))

        if s["attention"]:
            first = "; ".join(f"{n} \u2014 {why}" for n, why in s["attention"][:2])
            more = len(s["attention"]) - 2
            f.addRow("worth checking:", QLabel(
                first + (f"; and {more} more" if more > 0 else "")))

    def _pipe_summary(self, f, pipe):
        """The default pipe is one rule, not a list of elements.

        Averaging it with anything would mean nothing -- it has no position, no
        length and no beta, because it stands for every lattice row no device
        claimed. So it gets its own reading: what it is made of, and the reason
        the geometric rows are empty.
        """
        enabled = [m for m in getattr(pipe, "models", []) if m.enabled]
        from .model import method_base
        methods = sorted({method_base(m.method or "") for m in enabled} - {""})
        f.addRow("chamber:", QLabel(pipe.name))
        f.addRow("computed with:", QLabel(", ".join(methods) or "\u2014"))
        f.addRow("layers:", QLabel(str(len(getattr(pipe, "layers", [])))))
        on = sorted({m.q for m in enabled})
        f.addRow("quantities on:", QLabel(
            ", ".join(QLABEL[q].split()[0] for q in on) or "\u2014"))
        note = QLabel("One rule over every lattice row no device claimed, so it "
                      "has no single position, length or \u03b2. The count of "
                      "segments it stands for is in the group's name.")
        note.setWordWrap(True)
        f.addRow("", note)


def _fmt(v, unit=""):
    if v is None:
        return "\u2014"
    return f"{v}{(' ' + unit) if unit else ''}"
