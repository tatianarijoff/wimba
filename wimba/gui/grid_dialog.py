"""Edit the grid a study is sampled on.

The grid was the one thing a study needs that the window could not state: it
came from `project.yaml`, from whichever config was open, or - for a component
built by hand - from a default written in the code. So changing it meant
leaving the window, editing a file and coming back, and the default was easy to
compute against without ever having decided it.

Where it is written depends on what is open, and the dialog says so rather than
guessing: inside a project the grid belongs to the project, because scenarios
are comparable only when they were sampled alike; a component of the bench
belongs to no project and carries its own.
"""
from __future__ import annotations

from PyQt6.QtGui import QDoubleValidator, QIntValidator
from PyQt6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
                             QGroupBox, QLabel, QLineEdit, QVBoxLayout)

from .model import as_number, grid_advice

#: what a study is sampled on when nothing has said otherwise - the same
#: default `component_config` writes, kept here so the dialog opens on the
#: values a calculation would actually use
DEFAULT_GRID = {"frequency": {"min": 1.0e5, "max": 1.0e10, "n": 100, "log": True},
                "time": {"min": 0.0, "max": 5.0e-9, "n": 200}}


def _number(value, default="") -> str:
    value = as_number(value)
    if value is None or value == "":
        return default
    return f"{value:g}" if isinstance(value, float) else str(value)


class GridDialog(QDialog):
    """Frequency and time grid, with a line about what the sampling can see."""

    def __init__(self, grid: dict, target: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Frequency & Time Grid")
        self.setMinimumWidth(520)
        grid = grid or DEFAULT_GRID
        freq = grid.get("frequency") or grid.get("freq") or {}
        time = grid.get("time") or {}

        outer = QVBoxLayout(self)
        where = QLabel(target)
        where.setWordWrap(True)
        outer.addWidget(where)

        box = QGroupBox("Frequency")
        form = QFormLayout(box)
        self.f_min = self._num(_number(freq.get("min"), "1e5"))
        self.f_max = self._num(_number(freq.get("max"), "1e10"))
        self.f_n = self._int(_number(freq.get("n"), "100"))
        self.f_log = QCheckBox("logarithmic")
        self.f_log.setChecked(bool(freq.get("log", True)))
        form.addRow("min [Hz]", self.f_min)
        form.addRow("max [Hz]", self.f_max)
        form.addRow("points", self.f_n)
        form.addRow("", self.f_log)
        outer.addWidget(box)

        self.advice = QLabel()
        self.advice.setWordWrap(True)
        self.advice.setObjectName("EmptyText")
        outer.addWidget(self.advice)

        box = QGroupBox("Time (used by wake calculations)")
        form = QFormLayout(box)
        self.t_min = self._num(_number(time.get("min"), "0"))
        self.t_max = self._num(_number(time.get("max"), "5e-9"))
        self.t_n = self._int(_number(time.get("n"), "200"))
        form.addRow("min [s]", self.t_min)
        form.addRow("max [s]", self.t_max)
        form.addRow("points", self.t_n)
        outer.addWidget(box)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)
        self._ok = buttons.button(QDialogButtonBox.StandardButton.Ok)

        for w in (self.f_min, self.f_max, self.f_n):
            w.textChanged.connect(self._restate)
        self.f_log.toggled.connect(self._restate)
        self._restate()

    def _num(self, text):
        edit = QLineEdit(text)
        validator = QDoubleValidator()
        validator.setNotation(QDoubleValidator.Notation.ScientificNotation)
        edit.setValidator(validator)
        return edit

    def _int(self, text):
        edit = QLineEdit(text)
        edit.setValidator(QIntValidator(2, 10_000_000))
        return edit

    def _restate(self):
        """Say what this sampling resolves, and refuse a grid that is not one."""
        grid = self.values(quiet=True)
        message = grid_advice(grid) if grid else ""
        self.advice.setText(message or "min, max and points do not describe a "
                                       "grid yet.")
        self._ok.setEnabled(bool(message))

    def values(self, quiet: bool = False) -> dict:
        """The grid as a config writes it, or {} while it is not a grid yet.

        A time block that does not describe a grid is left out rather than
        refused: a wake is not what most runs are after, and an impedance study
        should not be held up by the fields underneath it.
        """
        try:
            freq = {"min": float(self.f_min.text()),
                    "max": float(self.f_max.text()),
                    "n": int(self.f_n.text()),
                    "log": self.f_log.isChecked()}
        except (TypeError, ValueError):
            return {}
        if freq["n"] < 2 or freq["max"] <= freq["min"]:
            return {}
        if freq["log"] and freq["min"] <= 0:
            return {}
        out = {"frequency": freq}
        try:
            time = {"min": float(self.t_min.text()),
                    "max": float(self.t_max.text()),
                    "n": int(self.t_n.text())}
        except (TypeError, ValueError):
            return out
        if time["n"] >= 2 and time["max"] > time["min"]:
            out["time"] = time
        return out
