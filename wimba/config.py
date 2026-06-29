"""Locate external tools (the IW2D binary, pytlwall) and store their paths.

WIMBA stays installable and usable (core, resonator, Fourier) without any
external tool: the tools are located, not bundled.

Resolution precedence for each tool, highest first:
  1. an explicit argument passed in code
  2. an environment variable (WIMBA_IW2D_BINARY, WIMBA_PYTLWALL_PATH)
  3. the config file written by ``wimba setup``
  4. otherwise a clear error

Config file location: ``$WIMBA_CONFIG`` if set, else
``$XDG_CONFIG_HOME/wimba/config.yaml``, else ``~/.config/wimba/config.yaml``.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Optional

import yaml


class ToolNotConfigured(RuntimeError):
    """Raised when a required external tool cannot be located."""


def config_path() -> Path:
    env = os.environ.get("WIMBA_CONFIG")
    if env:
        return Path(env).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / "wimba" / "config.yaml"


def load_config() -> dict:
    p = config_path()
    if not p.is_file():
        return {}
    with open(p) as fh:
        return yaml.safe_load(fh) or {}


def save_config(data: dict) -> Path:
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as fh:
        yaml.safe_dump(data, fh, sort_keys=False)
    return p


def _config_get(*keys):
    node = load_config()
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def iw2d_binary(explicit: Optional[str] = None, required: bool = True) -> Optional[Path]:
    """Resolve the IW2D binary path (explicit > env > config)."""
    candidate = (explicit
                 or os.environ.get("WIMBA_IW2D_BINARY")
                 or _config_get("tools", "iw2d", "binary"))
    if candidate:
        p = Path(candidate).expanduser()
        if p.is_file() and os.access(p, os.X_OK):
            return p
        if required:
            raise ToolNotConfigured(
                f"IW2D binary '{p}' was not found or is not executable. "
                "Fix it with `wimba setup` or the WIMBA_IW2D_BINARY variable.")
        return None
    if required:
        raise ToolNotConfigured(
            "IW2D binary is not configured. Run `wimba setup` or set WIMBA_IW2D_BINARY.")
    return None


def _ensure_pytlwall_on_path() -> None:
    path = (os.environ.get("WIMBA_PYTLWALL_PATH")
            or _config_get("tools", "pytlwall", "path"))
    if path:
        p = str(Path(path).expanduser())
        if Path(p).is_dir() and p not in sys.path:
            sys.path.insert(0, p)


def pytlwall_available() -> bool:
    """True if pytlwall can be imported (honouring a configured checkout path)."""
    _ensure_pytlwall_on_path()
    return importlib.util.find_spec("pytlwall") is not None


def require_pytlwall():
    """Import and return pytlwall, or raise a clear error."""
    if not pytlwall_available():
        raise ToolNotConfigured(
            "pytlwall is not importable. Install it (e.g. "
            "`pip install git+https://github.com/tatianarijoff/TLWallNew`) "
            "or point WIMBA_PYTLWALL_PATH / `wimba setup` at a checkout.")
    import pytlwall
    return pytlwall


def tool_status() -> dict:
    """Summary used by `wimba status` (never raises)."""
    return {
        "config_file": str(config_path()),
        "config_exists": config_path().is_file(),
        "iw2d_binary": str(iw2d_binary(required=False) or ""),
        "pytlwall_available": pytlwall_available(),
    }
