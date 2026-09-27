"""File > New Parametric Project: one layer parameter, several values.

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
    def __init__(self, base_config, parent=None):
        super().__init__(parent)
        self.base = Path(base_config)
        self.cfg = yaml.safe_load(self.base.read_text()) or {}
        self.walls = P.walls(self.cfg)
        self.setWindowTitle("New Parametric Project")
        self.setMinimumWidth(560)

        lay = QVBoxLayout(self)
        head = QLabel(
            f"Every case is a copy of <b>{self.base.name}</b> that differs from it in "
            f"one layer parameter only. At most {MAX_SCENARIOS} values.")
        head.setWordWrap(True)
        lay.addWidget(head)

        form = QFormLayout()
        self.name = QLineEdit(f"{self.cfg.get('name', self.base.stem)} sweep")
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
        for name, layers in self.walls.items():
            item = QListWidgetItem(f"{name}    ({len(layers)} layers)")
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.elements.addItem(item)
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
        for name in sorted(config_table(self.cfg.get("materials"))):
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.materials.addItem(item)
        self.materials.setMaximumHeight(150)
        self.numbers = QLineEdit()
        self.numbers.setPlaceholderText("e.g. 1e-5, 5e-5, 2e-4  (SI units)")
        self.values_stack.addWidget(self.materials)
        self.values_stack.addWidget(self.numbers)
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
        if not self.walls:
            self.preview.setText("This config writes out no element with layers, "
                                 "so there is nothing a sweep can vary.")
        self._update()

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

    # ---- keeping it honest ----
    def _choose_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Folder for the parametric project")
        if d:
            self.folder.setText(d)

    def _update(self, *_):
        chosen = self.chosen_elements()
        depth = min((len(self.walls[n]) for n in chosen), default=1)
        self.layer.setMaximum(max(0, depth - 1))
        i = self.layer.value()
        self.layer_note.setText("   ".join(
            f"{n}: {P.describe_layer(self.walls[n][i])}" for n in chosen
            if i < len(self.walls[n])))
        self.values_stack.setCurrentIndex(0 if self.field.currentText() == "material" else 1)
        ok, text = self._verdict()
        self.preview.setText(text)
        self.preview.setStyleSheet("" if ok else "color: #B3261E;")
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(ok)

    def _verdict(self):
        if not self.chosen_elements():
            return False, "Tick the element (or elements) whose layer changes."
        try:
            sweep = P.validate(self.cfg, self.sweep())
        except (P.SweepError, ValueError) as exc:
            return False, str(exc)
        if not self.folder.text().strip():
            return False, "Choose an empty folder for the project."
        if (self.directory() / "project.yaml").exists():
            return False, "That folder already holds a project; choose an empty one."
        labels = [P.case_label(sweep, v) for v in sweep.values]
        return True, f"{len(labels)} case(s): " + ", ".join(labels)
