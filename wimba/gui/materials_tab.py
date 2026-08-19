"""The Materials tab: every named material, in one table you can edit.

A dialog was the wrong shape for this. There are ten columns of numbers and a
list that grows, so it belongs in the centre of the window like any other
document, with both scrollbars and room to read.

Two blocks, in this order:

* the user's own materials, from custom_materials.yaml, on a pink alternation.
  These are editable, can be added and deleted, and are what Save writes.
* the ones WIMBA ships with, on a green alternation. Read-only: they belong to
  the package, and a value typed for one chamber has no business becoming
  everyone else's copper. Give it a different name and it lands in the block
  above, where it overrides the catalogue entry for you alone.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QDoubleValidator, QFont, QValidator
from PyQt6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView,
                             QInputDialog, QLabel, QLineEdit, QMessageBox,
                             QPushButton, QStyledItemDelegate, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from .. import materials

# custom rows: two shades of pink; catalogue rows: two of green
CUSTOM_ROWS = ("#FDEFF3", "#F7DDE5")
STOCK_ROWS = ("#EEF6EE", "#DEECDF")
HEADING = "#F2F4F7"
IMPLIED_TEXT = "#7A8794"   # a value nobody stated, shown as it will be used

COLUMNS = [
    ("name", "Name"), ("label", "Label"), ("sigma", "\u03c3 [S/m]"),
    ("epsr", "\u03b5r"), ("tau", "\u03c4 [s]"), ("k_Hz", "k [Hz]"),
    ("muinf_Hz", "\u03bc\u221e"), ("RQ", "RQ"), ("origin", "From"),
    ("note", "Note"),
]
EDITABLE = ("name", "label", "sigma", "epsr", "tau", "k_Hz", "muinf_Hz",
            "RQ", "note")


def _text(value):
    return "" if value is None else str(value)


class _NumberDelegate(QStyledItemDelegate):
    """Numbers only, in the columns that hold numbers.

    A plain table item takes any text, so a conductivity could be saved as the
    word "copper" and only fail much later, inside the solver. The editor
    refuses it while it is being typed instead.

    `inf` is accepted for k, and only there: pytlwall's own configs say k = 0
    is not allowed and an infinite conductivity is not allowed, so the two
    exceptions do not mirror each other.
    """

    def __init__(self, allow_inf=False, positive=False, parent=None):
        super().__init__(parent)
        self.allow_inf = allow_inf
        self.positive = positive

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        validator = QDoubleValidator(editor)
        validator.setNotation(QDoubleValidator.Notation.ScientificNotation)
        if self.positive:
            validator.setBottom(0.0)
        if self.allow_inf:
            editor.setValidator(_InfOrNumber(validator, editor))
            editor.setPlaceholderText("a number, or inf")
        else:
            editor.setValidator(validator)
        return editor


class _InfOrNumber(QValidator):
    """A number, or the word inf being spelled out."""

    def __init__(self, numbers, parent=None):
        super().__init__(parent)
        self.numbers = numbers

    def validate(self, text, pos):
        low = text.strip().lower()
        if low in ("i", "in", "inf"):
            return (QValidator.State.Acceptable if low == "inf"
                    else QValidator.State.Intermediate), text, pos
        return self.numbers.validate(text, pos)


class MaterialsTab(QWidget):
    """Editable list of materials. `changed` fires when a save lands, so open
    element panels can rebuild their dropdowns."""

    changed = pyqtSignal()

    def __init__(self, log=None):
        super().__init__()
        self.log = log
        self._dirty = False

        v = QVBoxLayout(self)

        bar = QHBoxLayout()
        add = QPushButton("+ Add material")
        add.clicked.connect(self.add_row)
        rm = QPushButton("Delete selected")
        rm.clicked.connect(self._delete_row)
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.save)
        bar.addWidget(add)
        bar.addWidget(rm)
        bar.addStretch(1)
        self.status = QLabel()
        self.status.setObjectName("EmptyText")
        bar.addWidget(self.status)
        bar.addWidget(self.save_btn)
        v.addLayout(bar)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels([lbl for _, lbl in COLUMNS])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        # a spreadsheet, not a form: the columns keep their width and the view
        # scrolls, rather than squeezing ten numbers into the window
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        head.setStretchLastSection(True)
        self.table.setHorizontalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setVerticalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel)
        for c, (key, _) in enumerate(COLUMNS):
            if key in materials.PARAMS:
                self.table.setItemDelegateForColumn(
                    c, _NumberDelegate(allow_inf=(key == "k_Hz"),
                                       positive=(key == "sigma"), parent=self))
        self.table.itemChanged.connect(self._edited)
        v.addWidget(self.table)

        note = QLabel(
            "Adding a material here is a permanent choice: Save writes it to "
            "custom_materials.yaml and it is offered from then on. For a value "
            "you only need once, do not add anything \u2014 pick CW (custom) in "
            "the layer and type the numbers there.\n\n"
            "Values in grey italics were not written down for that material: "
            "they are the defaults the calculation uses, shown so no column "
            "looks empty when it is not.\n\n"
            "Your own materials are on top. The ones below ship with WIMBA and "
            "cannot be edited: to change one, add a row with the same name and "
            "it overrides the catalogue entry for you, and for nobody else. "
            "Either way what goes into a layer is the numbers, so a config you "
            "send elsewhere carries the values and not the name.")
        note.setObjectName("EmptyText")
        note.setWordWrap(True)
        v.addWidget(note)

        self.reload()

    # ---------------------------------------------------------------- filling
    def reload(self):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self._custom_rows = 0
        for name, entry in materials.custom_entries().items():
            self._append(name, entry, custom=True)
        for name, entry in materials.catalogue_entries().items():
            self._append(name, entry, custom=False)
        self.table.blockSignals(False)
        self.table.resizeColumnsToContents()
        self._set_dirty(False)

    def _append(self, name, entry, custom):
        r = self.table.rowCount()
        self.table.insertRow(r)
        if custom:
            colour = CUSTOM_ROWS[self._custom_rows % 2]
            self._custom_rows += 1
        else:
            colour = STOCK_ROWS[(r - self._custom_rows) % 2]
        effective = materials.parameters(name)
        for c, (key, _) in enumerate(COLUMNS):
            implied = False
            if key == "name":
                value = name
            elif key == "origin":
                value = "yours" if custom else "WIMBA"
            elif key in materials.PARAMS:
                # An entry usually states only its conductivity; the rest come
                # from pytlwall's neutral defaults. Leaving those cells blank
                # made the table look like data was missing, when what is
                # missing is only the mention. Show what the calculation will
                # actually use, and mark the ones nobody wrote down.
                value = effective.get(key)
                implied = key not in entry
            else:
                value = entry.get(key)
            item = QTableWidgetItem(_text(value))
            item.setBackground(QBrush(QColor(colour)))
            if implied:
                font = QFont(item.font())
                font.setItalic(True)
                item.setFont(font)
                item.setForeground(QBrush(QColor(IMPLIED_TEXT)))
                item.setToolTip("Not stated for this material: this is the "
                                "default the calculation uses.")
            if not custom or key == "origin":
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if not custom:
                    item.setToolTip("Ships with WIMBA. Add a row with the same "
                                    "name to override it.")
            self.table.setItem(r, c, item)

    def _is_custom(self, row):
        return row < self._custom_rows

    # ----------------------------------------------------------------- edits
    def add_row(self):
        name, ok = QInputDialog.getText(self, "Add material", "Name:")
        name = (name or "").strip()
        if not ok or not name:
            return
        if name in self._names():
            QMessageBox.warning(
                self, "Add material",
                f"'{name}' is already in the table. Edit that row instead \u2014 "
                f"two rows with one name would make the value depend on which "
                f"one was read first.")
            return
        self.table.blockSignals(True)
        self.table.insertRow(self._custom_rows)
        colour = CUSTOM_ROWS[self._custom_rows % 2]
        for c, (key, _) in enumerate(COLUMNS):
            if key == "name":
                value = name
            elif key == "origin":
                value = "yours"
            elif key == "sigma":
                value = ""                      # the one number you must supply
            elif key in materials.PARAMS:
                value = _text(materials.NEUTRAL.get(key))
            else:
                value = ""
            item = QTableWidgetItem(value)
            item.setBackground(QBrush(QColor(colour)))
            if key == "origin":
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(self._custom_rows, c, item)
        self._custom_rows += 1
        self.table.blockSignals(False)
        self._restripe()
        self.table.setCurrentCell(self._custom_rows - 1, 2)   # straight to sigma
        self.table.editItem(self.table.item(self._custom_rows - 1, 2))
        self._set_dirty(True)

    def _delete_row(self):
        r = self.table.currentRow()
        if r < 0:
            return
        if not self._is_custom(r):
            QMessageBox.information(
                self, "Delete material",
                "Only your own materials can be deleted. The ones below ship "
                "with WIMBA, and configs already name them.")
            return
        name = self.table.item(r, 0).text()
        if QMessageBox.question(self, "Delete material",
                                f"Remove '{name}'?") != QMessageBox.StandardButton.Yes:
            return
        self.table.removeRow(r)
        self._custom_rows -= 1
        self._restripe()
        self._set_dirty(True)

    def _edited(self, item):
        if self._is_custom(item.row()):
            self._set_dirty(True)

    def _restripe(self):
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            if self._is_custom(r):
                colour = CUSTOM_ROWS[r % 2]
            else:
                colour = STOCK_ROWS[(r - self._custom_rows) % 2]
            for c in range(self.table.columnCount()):
                cell = self.table.item(r, c)
                if cell is not None:
                    cell.setBackground(QBrush(QColor(colour)))
        self.table.blockSignals(False)

    def _names(self):
        return [self.table.item(r, 0).text().strip()
                for r in range(self.table.rowCount())
                if self.table.item(r, 0)]

    # ------------------------------------------------------------------ save
    def _collect(self):
        """The custom rows as entries, refusing what pytlwall would refuse."""
        entries, problems = {}, []
        for r in range(self._custom_rows):
            name = self.table.item(r, 0).text().strip()
            if not name:
                problems.append(f"row {r + 1} has no name.")
                continue
            entry = {}
            for c, (key, label) in enumerate(COLUMNS):
                if key in ("name", "origin"):
                    continue
                text = (self.table.item(r, c).text() or "").strip()
                if not text:
                    continue
                if key in ("label", "note"):
                    entry[key] = text
                    continue
                if text.lower() in ("inf", "infinity"):
                    entry[key] = "inf"
                    continue
                try:
                    entry[key] = float(text)
                except ValueError:
                    problems.append(f"'{name}': {label} is not a number ({text}).")
            sigma = entry.get("sigma")
            if sigma is None:
                problems.append(f"'{name}' has no conductivity.")
            elif sigma == "inf":
                problems.append(f"'{name}': pytlwall does not allow an infinite "
                                f"conductivity.")
            elif isinstance(sigma, float) and sigma <= 0:
                problems.append(f"'{name}': conductivity must be greater than zero.")
            if entry.get("k_Hz") == 0:
                problems.append(f"'{name}': pytlwall does not allow k = 0; use inf "
                                f"for a non-dispersive material.")
            entries[name] = entry
        return entries, problems

    def save(self) -> bool:
        entries, problems = self._collect()
        if problems:
            QMessageBox.warning(self, "Save materials",
                                "Nothing was saved:\n\n\u2022 " +
                                "\n\u2022 ".join(problems))
            return False
        path = materials.save_custom(entries)
        if self.log:
            self.log.info("Materials: %d saved to %s", len(entries), path)
        self.status.setText(f"Saved to {path}")
        self.reload()
        self.changed.emit()
        return True

    # ----------------------------------------------------------------- state
    def _set_dirty(self, dirty):
        self._dirty = dirty
        self.save_btn.setEnabled(dirty)
        if dirty:
            self.status.setText("Unsaved changes")

    def is_dirty(self) -> bool:
        return self._dirty

    def confirm_close(self) -> bool:
        """True when the tab may close: nothing pending, or the user decided."""
        if not self._dirty:
            return True
        answer = QMessageBox.question(
            self, "Materials",
            "This table has unsaved changes. Save before closing?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Save:
            return self.save()
        return answer == QMessageBox.StandardButton.Discard
