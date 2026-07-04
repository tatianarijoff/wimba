"""Central logging for WIMBA, with the usual levels.

Use ``get_logger(__name__)`` in any module and ``configure(level)`` once at
startup (the CLI and the GUI both call it). The GUI additionally attaches a
handler that streams records into its Console panel.
"""
from __future__ import annotations

import logging

LEVELS = {
    "critical": logging.CRITICAL,
    "error":    logging.ERROR,
    "warning":  logging.WARNING,
    "info":     logging.INFO,
    "debug":    logging.DEBUG,
}

_FORMAT = "%(asctime)s  %(levelname)-8s %(name)s: %(message)s"
_DATEFMT = "%H:%M:%S"


def get_logger(name: str = "wimba") -> logging.Logger:
    if not name.startswith("wimba"):
        name = f"wimba.{name}"
    return logging.getLogger(name)


def configure(level: str = "info") -> logging.Logger:
    """Set the WIMBA log level and ensure a console (stderr) handler exists."""
    root = logging.getLogger("wimba")
    root.setLevel(LEVELS.get(str(level).lower(), logging.INFO))
    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
               for h in root.handlers):
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter(_FORMAT, _DATEFMT))
        root.addHandler(h)
    root.propagate = False
    return root


def set_level(level: str) -> None:
    logging.getLogger("wimba").setLevel(LEVELS.get(str(level).lower(), logging.INFO))
