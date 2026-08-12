"""Import-map dialog: describe a precalculated data file from the GUI.

Shows a preview of the file and the fields of the import map (comment, rows to
skip, separator, unit, format, column numbers - numbered from 1). On OK it
writes a readable descriptor YAML next to the data file and returns its path,
so the mapping is reusable from configs and future sessions.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                             QLabel, QLineEdit, QPlainTextEdit, QSpinBox,
                             QVBoxLayout)

from ..io.import_map import make_descriptor

Z_COMPONENTS = ["ZLong", "ZDipX", "ZDipY", "ZQuadX", "ZQuadY"]
W_COMPONENTS = ["WLong", "WDipX", "WDipY", "WQuadX", "WQuadY"]
F_UNITS = ["Hz", "kHz", "MHz", "GHz", "THz"]
T_UNITS = ["s", "ms", "us", "ns", "ps"]


class ImportMapDialog(QDialog):
    def _preview_text(self):
        """First rows of the data file, as text.

        A spreadsheet is rendered column by column: reading it as text would
        show the bytes of the container instead of the numbers.
        """
        from ..io.tables import SPREADSHEET_SUFFIXES
        try:
            if self.data_path.suffix.lower() in SPREADSHEET_SUFFIXES:
                try:
                    import pandas as pd
                except ImportError:
                    return ('Reading a spreadsheet needs pandas and openpyxl:\n'
                            '    pip install -e ".[spreadsheets]"')
                df = pd.read_excel(self.data_path, nrows=10)
                lines = ["  ".join(str(c) for c in df.columns)]
                lines += ["  ".join(f"{v:.6g}" if isinstance(v, float) else str(v)
                                    for v in row)
                          for row in df.itertuples(index=False, name=None)]
                return "\n".join(lines)
            return "\n".join(self.data_path.read_text(errors="replace")
                             .splitlines()[:12])
        except Exception as exc:
            return f"(cannot preview file: {exc})"

    def __init__(self, data_path, parent=None):
        super().__init__(parent)
        self.data_path = Path(data_path)
        self.map_path = None
        self.setWindowTitle(f"Describe {self.data_path.name}")

        lay = QVBoxLayout(self)
        preview = QPlainTextEdit()
        preview.setReadOnly(True)
        head = self._preview_text()
        preview.setPlainText(head)
        preview.setMaximumHeight(150)
        lay.addWidget(QLabel(f"First lines of <b>{self.data_path.name}</b> "
                             "\u2014 columns are numbered from 1:"))
        lay.addWidget(preview)

        form = QFormLayout()
        self.kind = QComboBox(); self.kind.addItems(["Impedance", "Wake"])
        self.kind.currentTextChanged.connect(self._kind_changed)
        form.addRow("Data kind:", self.kind)
        self.component = QComboBox(); self.component.addItems(Z_COMPONENTS)
        form.addRow("Component:", self.component)
        self.comment = QLineEdit("#")
        form.addRow("Comment prefix (skips those lines):", self.comment)
        self.skip = QSpinBox(); self.skip.setRange(0, 1000)
        form.addRow("Extra rows to skip:", self.skip)
        self.sep = QComboBox(); self.sep.addItems(["auto (whitespace)", "tab", ",", ";"])
        form.addRow("Separator:", self.sep)
        self.unit = QComboBox(); self.unit.addItems(F_UNITS)
        form.addRow("x unit (frequency / time):", self.unit)
        self.fmt = QComboBox(); self.fmt.addItems(["re_im (two columns)",
                                                   "complex (one column)"])
        self.fmt.currentTextChanged.connect(self._fmt_changed)
        form.addRow("Value format:", self.fmt)
        self.col_x = QSpinBox(); self.col_x.setRange(1, 99); self.col_x.setValue(1)
        form.addRow("Column of frequency / time:", self.col_x)
        self.col_re = QSpinBox(); self.col_re.setRange(1, 99); self.col_re.setValue(2)
        form.addRow("Column of Re (or the value):", self.col_re)
        self.col_im = QSpinBox(); self.col_im.setRange(1, 99); self.col_im.setValue(3)
        form.addRow("Column of Im:", self.col_im)
        lay.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _kind_changed(self, text):
        wake = text == "Wake"
        self.component.clear()
        self.component.addItems(W_COMPONENTS if wake else Z_COMPONENTS)
        self.unit.clear()
        self.unit.addItems(T_UNITS if wake else F_UNITS)
        self.fmt.setEnabled(not wake)
        self.col_im.setEnabled(not wake)

    def _fmt_changed(self, text):
        self.col_im.setEnabled(text.startswith("re_im")
                               and self.kind.currentText() == "Impedance")

    def _accept(self):
        kind = "wake" if self.kind.currentText() == "Wake" else "impedance"
        fmt = "complex" if self.fmt.currentText().startswith("complex") else "re_im"
        sep = {"auto (whitespace)": None, "tab": "tab"}.get(self.sep.currentText(),
                                                            self.sep.currentText())
        desc = make_descriptor(kind, self.component.currentText(),
                               self.data_path.name,
                               comment=self.comment.text() or "#",
                               skip_rows=self.skip.value(), sep=sep,
                               unit=self.unit.currentText(), fmt=fmt,
                               col_x=self.col_x.value(), col_re=self.col_re.value(),
                               col_im=self.col_im.value(), col_z=self.col_re.value())
        self.map_path = self.data_path.with_name(self.data_path.stem + ".map.yaml")
        header = "# WIMBA import map (written by the GUI). Columns are numbered from 1.\n"
        self.map_path.write_text(header + yaml.safe_dump(desc, sort_keys=False))
        self.accept()
