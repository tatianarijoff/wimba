"""File > New Parametric Project: one layer parameter, several values.

The first thing the dialog asks is the config every case starts from: a
parametric project is not built from nothing, it varies a machine that already
exists, and saying so on the first line is what keeps the step from looking
like "open a file". Everything below it stays disabled until that config is
chosen and readable.

The dialog only collects the choice and shows what it would generate; the
checks and the writing are wimba.parametric's, the same functions the command
line and the tests use. OK stays disabled until the sweep would be accepted, and
the line under the fields says why when it would not.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                             QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QPushButton, QSpinBox,
                             QStackedWidget, QVBoxLayout, QWidget)

from .. import parametric as P
from ..materials import config_table
from .model import MAX_SCENARIOS


class SweepDialog(QDialog):
    def __init__(self, base_config=None, parent=None, start_dir=""):
        super().__init__(parent)
        self.base, self.cfg, self.walls = None, {}, {}
        self._start_dir = start_dir
        self.setWindowTitle("New Parametric Project")
        self.setMinimumWidth(600)

        lay = QVBoxLayout(self)
        form = QFormLayout()

        row = QHBoxLayout()
        self.base_edit = QLineEdit()
        self.base_edit.setReadOnly(True)
        self.base_edit.setPlaceholderText("the machine every case is a copy of")
        pick_base = QPushButton("Choose\u2026")
        pick_base.clicked.connect(self._choose_base)
        row.addWidget(self.base_edit, 1)
        row.addWidget(pick_base)
        holder = QWidget(); holder.setLayout(row)
        form.addRow("Start from config", holder)
        head = QLabel(
            f"Every case is a copy of this machine with one layer parameter "
            f"changed. At most {MAX_SCENARIOS} values.")
        head.setWordWrap(True)
        head.setStyleSheet("color: #60717F;")
        form.addRow("", head)

        self.name = QLineEdit()
        form.addRow("Project name", self.name)

        row = QHBoxLayout()
        self.folder = QLineEdit()
        self.folder.setPlaceholderText("an empty folder for the project")
        pick = QPushButton("Choose\u2026")
        pick.clicked.connect(self._choose_folder)
        row.addWidget(self.folder, 1)
        row.addWidget(pick)
        holder = QWidget(); holder.setLayout(row)
        form.addRow("Folder", holder)

        self.elements = QListWidget()
        self.elements.setMaximumHeight(110)
        form.addRow("Elements", self.elements)

        self.layer = QSpinBox()
        self.layer.setRange(0, 0)
        self.layer_note = QLabel()
        self.layer_note.setWordWrap(True)
        row = QHBoxLayout(); row.addWidget(self.layer); row.addWidget(self.layer_note, 1)
        holder = QWidget(); holder.setLayout(row)
        form.addRow("Layer (0 = nearest the beam)", holder)

        self.field = QComboBox()
        self.field.addItems(P.FIELDS)
        form.addRow("Parameter", self.field)

        self.values_stack = QStackedWidget()
        self.materials = QListWidget()
        self.materials.setMaximumHeight(150)
        self.numbers = QLineEdit()
        self.numbers.setPlaceholderText("e.g. 1e-5, 5e-5, 2e-4  (SI units)")
        self.values_stack.addWidget(self.materials)
        # one line at the top, not a line stretched to the height of the list
        numbers_page = QWidget()
        numbers_lay = QVBoxLayout(numbers_page)
        numbers_lay.setContentsMargins(0, 0, 0, 0)
        numbers_lay.addWidget(self.numbers)
        numbers_lay.addStretch(1)
        self.values_stack.addWidget(numbers_page)
        form.addRow("Values", self.values_stack)
        lay.addLayout(form)

        self.preview = QLabel()
        self.preview.setWordWrap(True)
        lay.addWidget(self.preview)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                        | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)

        for signal in (self.elements.itemChanged, self.materials.itemChanged):
            signal.connect(self._update)
        self.layer.valueChanged.connect(self._update)
        self.field.currentIndexChanged.connect(self._update)
        self.numbers.textChanged.connect(self._update)
        self.folder.textChanged.connect(self._update)
        # everything that describes the sweep waits for the base config
        self._needs_base = [self.name, self.folder, pick, self.elements, self.layer,
                            self.field, self.values_stack]
        if base_config:
            self.set_base(base_config)
        else:
            self._update()

    # ---- the machine every case starts from ----
    def _choose_base(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "The config every case starts from", self._start_dir,
            "WIMBA config (*.yaml *.yml);;All files (*)")
        if path:
            self.set_base(path)

    def set_base(self, path):
        """Read the base config and fill the fields that depend on it."""
        path = Path(path)
        try:
            cfg = yaml.safe_load(path.read_text()) or {}
            table = sorted(config_table(cfg.get("materials")))
        except Exception as exc:
            self.base, self.cfg, self.walls = None, {}, {}
            self.base_edit.setText(str(path))
            self._fill([], [])
            self._update(error=f"Could not read {path.name}: {exc}")
            return
        self.base, self.cfg, self.walls = path, cfg, P.walls(cfg)
        self.base_edit.setText(str(path))
        self.name.setText(f"{cfg.get('name', path.stem)} sweep")
        self._fill(self.walls.items(), table)
        self._update()

    def _fill(self, walls, materials):
        for widget in (self.elements, self.materials):
            widget.blockSignals(True)
            widget.clear()
        for name, layers in walls:
            item = QListWidgetItem(f"{name}    ({len(layers)} layers)")
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.elements.addItem(item)
        for name in materials:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.materials.addItem(item)
        for widget in (self.elements, self.materials):
            widget.blockSignals(False)

    # ---- reading the fields ----
    def _checked(self, widget, role=None):
        out = []
        for i in range(widget.count()):
            item = widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                out.append(item.data(role) if role is not None else item.text())
        return out

    def chosen_elements(self):
        return self._checked(self.elements, Qt.ItemDataRole.UserRole)

    def sweep(self) -> dict:
        field = self.field.currentText()
        if field == "material":
            values = self._checked(self.materials)
        else:
            values = P.parse_values(field, self.numbers.text())
        return {"elements": self.chosen_elements(),
                "parameter": f"layers[{self.layer.value()}].{field}",
                "values": values}

    def directory(self) -> Path:
        return Path(self.folder.text().strip()).expanduser()

    def project_name(self) -> str:
        return self.name.text().strip() or f"{self.base.stem} sweep"

    def base_config(self):
        return self.base

    # ---- keeping it honest ----
    def _choose_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Folder for the parametric project")
        if d:
            self.folder.setText(d)

    def _update(self, *_, error=None):
        ready = self.base is not None
        for widget in self._needs_base:
            widget.setEnabled(ready)
        chosen = self.chosen_elements()
        depth = min((len(self.walls[n]) for n in chosen), default=1)
        self.layer.setMaximum(max(0, depth - 1))
        i = self.layer.value()
        self.layer_note.setText("   ".join(
            f"{n}: {P.describe_layer(self.walls[n][i])}" for n in chosen
            if i < len(self.walls[n])))
        self.values_stack.setCurrentIndex(0 if self.field.currentText() == "material" else 1)
        ok, text, kind = (False, error, "error") if error else self._verdict()
        self.preview.setText(text)
        # red only for what is wrong; the next step to take is a hint, in grey
        self.preview.setStyleSheet({"error": "color: #B3261E;",
                                    "hint": "color: #60717F;"}.get(kind, ""))
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(ok)

    def _verdict(self):
        if self.base is None:
            return False, ("Start by choosing the config every case is a copy of: "
                           "a parametric project varies a machine that already "
                           "exists."), "hint"
        if not self.walls:
            return False, ("This config writes out no element with layers, so there "
                           "is nothing a sweep can vary."), "error"
        if not self.chosen_elements():
            return False, "Tick the element (or elements) whose layer changes.", "hint"
        values = (self._checked(self.materials) if self.field.currentText() == "material"
                  else self.numbers.text().strip())
        if not values:
            return False, "Give the values, one case each.", "hint"
        try:
            sweep = P.validate(self.cfg, self.sweep())
        except (P.SweepError, ValueError) as exc:
            return False, str(exc), "error"
        labels = [P.case_label(sweep, v) for v in sweep.values]
        cases = f"{len(labels)} case(s): " + ", ".join(labels)
        if not self.folder.text().strip():
            return False, f"{cases}. Now choose an empty folder for the project.", "hint"
        if (self.directory() / "project.yaml").exists():
            return False, "That folder already holds a project; choose an empty one.", \
                "error"
        return True, cases, "ok"
