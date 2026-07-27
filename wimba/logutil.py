"""Central logging for WIMBA, with the usual levels.

Use ``get_logger(__name__)`` in any module and ``configure(level)`` once at
startup (the CLI and the GUI both call it). The GUI additionally attaches a
handler that streams records into its Console panel.
"""
from __future__ import annotations

import logging
import logging.handlers
import os

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
    chosen = LEVELS.get(str(level).lower(), logging.INFO)
    root.setLevel(logging.DEBUG)          # handlers filter; the file wants DEBUG
    for h in root.handlers:
        if not isinstance(h, logging.handlers.RotatingFileHandler):
            h.setLevel(chosen)
    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
               for h in root.handlers):
        h = logging.StreamHandler()
        h.setLevel(chosen)
        h.setFormatter(logging.Formatter(_FORMAT, _DATEFMT))
        root.addHandler(h)
    root.propagate = False
    return root


def set_level(level: str) -> None:
    configure(level)     # root stays at DEBUG; handlers filter, the file keeps all


def log_file_path():
    """Where the persistent log lives. Override dir with $WIMBA_LOG_DIR;
    default: $XDG_STATE_HOME/wimba (or ~/.local/state/wimba)."""
    from pathlib import Path
    base = os.environ.get("WIMBA_LOG_DIR")
    if not base:
        state = os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state")
        base = Path(state) / "wimba"
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p / "wimba.log"


def attach_file_handler(root_name: str = "wimba"):
    """Rotating file log (2 MB x 3), ALWAYS at DEBUG regardless of the console
    level - the console is for the session, the file is for the post-mortem."""
    path = log_file_path()
    root = logging.getLogger(root_name)
    for h in root.handlers:
        if isinstance(h, logging.handlers.RotatingFileHandler):
            return path
    fh = logging.handlers.RotatingFileHandler(path, maxBytes=2_000_000,
                                              backupCount=3, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s: %(message)s"))
    root.addHandler(fh)
    root.setLevel(logging.DEBUG)
    return path
