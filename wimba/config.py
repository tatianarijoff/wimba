"""Locate external tools (the IW2D binary, pytlwall) and store their paths.

WIMBA stays installable and usable (core, resonator, Fourier) without any
external tool: the tools are located, not bundled.

Resolution precedence for each tool, highest first:
  1. an explicit argument passed in code
  2. an environment variable (WIMBA_IW2D_BINARY, WIMBA_PYTLWALL_PATH)
  3. the config file written by ``wimba setup``
  4. otherwise a clear error

The same precedence applies to ``$WIMBA_DATA_DIR``, an optional directory
searched for large data files (MAD-X optics tables) that are not tracked in the
repository. See ``docs/DATA.md``.

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


class DataFileNotFound(FileNotFoundError):
    """Raised when a data file referenced by a study config cannot be located."""


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


def _as_dir_list(value, base=None) -> list:
    """Normalise a data-directory setting into a list of Paths.

    Accepts a single path or a list of them. Relative entries are taken
    against ``base`` (the directory holding the study config), so a study can
    say ``data_dir: ../shared_optics`` and stay portable.
    """
    if not value:
        return []
    items = value if isinstance(value, (list, tuple)) else [value]
    out = []
    for it in items:
        if not it:
            continue
        p = Path(str(it)).expanduser()
        if not p.is_absolute() and base is not None:
            p = Path(base) / p
        # collapse '..' so paths compare and print cleanly, without following
        # symlinks (a shared optics folder is often one)
        out.append(Path(os.path.normpath(p)))
    return out


def data_dirs(explicit=None, study=None, base=None) -> list:
    """Directories searched for large data files, most specific first.

    Order:
      1. ``explicit``   -- passed in code or on the command line
      2. ``$WIMBA_DATA_DIR``  -- a per-invocation override
      3. ``study``      -- the ``data_dir:`` key of the study config
      4. ``data.dir``   -- the WIMBA config file, a machine-wide default

    The study key is the one to reach for normally: it keeps the location of a
    study's data with the study, so different studies can sit on different
    disks without anyone exporting a variable.
    """
    dirs = []
    dirs += _as_dir_list(explicit, base)
    dirs += _as_dir_list(os.environ.get("WIMBA_DATA_DIR"), base)
    dirs += _as_dir_list(study, base)
    dirs += _as_dir_list(_config_get("data", "dir"), base)
    seen, uniq = set(), []
    for d in dirs:
        if d not in seen:
            seen.add(d); uniq.append(d)
    return uniq


def data_dir(explicit: Optional[str] = None) -> Optional[Path]:
    """First configured data directory, or None. Kept for simple callers."""
    dirs = data_dirs(explicit)
    return dirs[0] if dirs else None


def resolve_data_path(reference, base=None, *, what: str = "data file",
                      study_dirs=None, explicit_dir=None) -> Path:
    """Locate a data file referenced from a study config.

    Search order:
      1. ``reference`` itself, when absolute
      2. each directory from :func:`data_dirs` -- first under the reference as
         written, then under its file name alone
      3. relative to ``base`` (normally the directory holding the config file)

    Matching by file name as well as by full reference matters: a shared optics
    folder will not mirror the directory layout of a study.

    Args:
        reference: path as written in the config, e.g. ``data/twiss.tfs``.
        base: directory the reference is relative to.
        what: noun used in the error message, e.g. ``"optics table"``.
        study_dirs: the ``data_dir:`` value of the study config.
        explicit_dir: highest-precedence override for this call.

    Returns:
        The first existing candidate, as a Path.

    Raises:
        DataFileNotFound: listing every location that was searched.
    """
    ref = Path(str(reference)).expanduser()
    tried: list = []

    def _try(cand):
        if cand not in tried:
            tried.append(cand)
            return cand.is_file()
        return False

    if ref.is_absolute():
        if _try(ref):
            return ref
    else:
        for root in data_dirs(explicit_dir, study_dirs, base):
            for cand in (root / ref, root / ref.name):
                if _try(cand):
                    return cand
        if base is not None:
            cand = Path(base) / ref
            if _try(cand):
                return cand
        elif _try(ref):
            return ref

    where = "\n".join(f"    {t}" for t in tried)
    raise DataFileNotFound(
        f"{what} '{reference}' was not found. Looked in:\n{where}\n"
        "Point the study at the data by adding a 'data_dir:' key to its config "
        "file (one path or a list, absolute or relative to the config), or set "
        "$WIMBA_DATA_DIR for a one-off override.\n"
        "Large data files are distributed separately; see docs/DATA.md.")


def require_pytlwall():
    """Import and return pytlwall, or raise a clear error."""
    if not pytlwall_available():
        raise ToolNotConfigured(
            "pytlwall is not importable. Install it (e.g. "
            "`pip install git+https://github.com/tatianarijoff/pytlwall`) "
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


def default_method() -> str:
    """The default compute method for new elements and unspecified devices.
    User-editable in the WIMBA config file:  default_method: pytlwall | IW2D
    (pytlwall if unset). Note: the analytic resonator is not a wall engine -
    it models known resonant modes, so it is not offered as a wall default."""
    return str(load_config().get("default_method", "pytlwall"))
