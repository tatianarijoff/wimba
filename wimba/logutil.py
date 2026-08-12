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


def configure(level: str = None) -> logging.Logger:
    """Set the WIMBA log level and ensure a console (stderr) handler exists.

    With no level given, the config file decides (`logging.level`), so the
    setting lives in one editable place instead of at each call site.
    """
    root = logging.getLogger("wimba")
    if level is None:
        level = settings().get("level", "info")
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


def settings() -> dict:
    """Logging settings from the config file (and the environment above it)."""
    try:
        from .config import logging_settings
        return logging_settings()
    except Exception:          # logging must never be what breaks a session
        return {"level": "info", "to_file": True, "dir": None, "file": "wimba.log"}


def log_file_path():
    """Where the persistent log lives.

    `logging.dir` in the config file, or $WIMBA_LOG_DIR above it; default
    $XDG_STATE_HOME/wimba (usually ~/.local/state/wimba). A relative directory is
    taken from the config file's own folder, so `dir: ./logs` in a working copy
    means that working copy, not wherever the command happened to be run.
    """
    from pathlib import Path
    cfg = settings()
    base = cfg.get("dir")
    if base:
        base = Path(base).expanduser()
        if not base.is_absolute():
            try:
                from .config import config_path
                base = (config_path().parent / base).resolve()
            except Exception:
                base = base.resolve()
    else:
        state = os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state")
        base = Path(state) / "wimba"
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p / (cfg.get("file") or "wimba.log")


def attach_file_handler(root_name: str = "wimba"):
    """Rotating file log (2 MB x 3), ALWAYS at DEBUG regardless of the console
    level - the console is for the session, the file is for the post-mortem.

    Returns None when `logging.to_file` is off in the config.
    """
    if not settings().get("to_file", True):
        return None
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
