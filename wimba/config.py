"""Locate external tools (the IW2D binary, pytlwall) and store their paths.

WIMBA stays installable and usable (core, resonator, Fourier) without any
external tool: the tools are located, not bundled.

Resolution precedence for each tool, highest first:
  1. an explicit argument passed in code
  2. an environment variable (WIMBA_IW2D_PATH, WIMBA_PYTLWALL_PATH,
     WIMBA_IW2D_BINARY for the legacy file-based IW2D path)
  3. the config file written by ``wimba setup``
  4. otherwise a clear error

The same precedence applies to ``$WIMBA_DATA_DIR``, an optional directory
searched for large data files (MAD-X optics tables) that are not tracked in the
repository. See ``docs/DATA.md``.

Config file location, highest first:
  1. ``$WIMBA_CONFIG``
  2. the nearest ``wimba.yaml`` found walking up from the current directory -
     put one at the top of a working copy and everything run from inside it uses
     it, which is easier to find and edit than a file hidden under ``~/.config``
  3. ``$XDG_CONFIG_HOME/wimba/config.yaml``, else ``~/.config/wimba/config.yaml``

``wimba config --init`` writes a commented starter file; ``wimba config --show``
says which file is in use and what it resolves to.
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


LOCAL_NAMES = ("wimba.yaml", "wimba.yml")


def user_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / "wimba" / "config.yaml"


def local_config_path(start=None) -> Optional[Path]:
    """The nearest wimba.yaml at or above `start` (default: the current dir)."""
    here = Path(start or Path.cwd()).expanduser().resolve()
    if here.is_file():
        here = here.parent
    for folder in (here, *here.parents):
        for name in LOCAL_NAMES:
            candidate = folder / name
            if candidate.is_file():
                return candidate
    return None


def config_path() -> Path:
    """The config file in use. Falls back to the user-level path when none exists
    yet, so `save_config` still has somewhere to write."""
    env = os.environ.get("WIMBA_CONFIG")
    if env:
        return Path(env).expanduser()
    return local_config_path() or user_config_path()


def config_source() -> str:
    """Where the settings are coming from, for `wimba config --show` and the GUI."""
    if os.environ.get("WIMBA_CONFIG"):
        return "the WIMBA_CONFIG variable"
    if local_config_path():
        return "a wimba.yaml found next to (or above) the working directory"
    if user_config_path().is_file():
        return "the user config"
    return "built-in defaults (no config file yet)"


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


def logging_settings() -> dict:
    """Level, whether to keep a file log, and where it goes.

    Environment beats config, as everywhere else, so a one-off debug run needs no
    edit: WIMBA_LOG_LEVEL, WIMBA_LOG_DIR, WIMBA_LOG_TO_FILE.
    """
    cfg = _config_get("logging") or {}
    level = os.environ.get("WIMBA_LOG_LEVEL") or cfg.get("level") or "info"
    to_file = os.environ.get("WIMBA_LOG_TO_FILE")
    if to_file is None:
        to_file = cfg.get("to_file", True)
    else:
        to_file = str(to_file).strip().lower() not in ("0", "false", "no", "off")
    directory = os.environ.get("WIMBA_LOG_DIR") or cfg.get("dir")
    return {"level": str(level).lower(), "to_file": bool(to_file),
            "dir": str(directory) if directory else None,
            "file": cfg.get("file") or "wimba.log"}


def _find_spec(name):
    """importlib.util.find_spec, but never raising.

    It raises ValueError on an already-imported module whose __spec__ is None -
    which real installs do not produce, but namespace tricks and test doubles do.
    Reporting provenance must not be able to break a run."""
    try:
        return importlib.util.find_spec(name)
    except (ImportError, ValueError, AttributeError):
        return None


def engine_location(module: str) -> dict:
    """Which build of an engine will answer, and how it was found.

    Two checkouts of pytlwall can sit side by side; a number is only
    interpretable once you know which one produced it.
    """
    name = str(module).lower()
    if name == "iw2d":
        _ensure_iw2d_on_path()
        source = ("WIMBA_IW2D_PATH" if os.environ.get("WIMBA_IW2D_PATH")
                  else str(config_path()) if _config_get("tools", "iw2d", "path")
                  else None)
        spec = _find_spec("IW2D")
        if spec is None:
            return {"available": False, "path": None, "version": None,
                    "source": source}
        mod = sys.modules.get("IW2D")
        return {"available": True,
                "path": (spec.origin or (spec.submodule_search_locations[0]
                                         if spec.submodule_search_locations else None)),
                "version": getattr(mod, "__version__", None) if mod else None,
                "source": source}
    _ensure_pytlwall_on_path()
    spec = _find_spec(name)
    if spec is None:
        return {"available": False, "path": None, "version": None, "source": None}
    version = None
    mod = sys.modules.get(name)
    if mod is not None:
        version = getattr(mod, "__version__", None)
    source = None
    if os.environ.get("WIMBA_PYTLWALL_PATH"):
        source = "WIMBA_PYTLWALL_PATH"
    elif _config_get("tools", "pytlwall", "path"):
        source = str(config_path())
    return {"available": True,
            "path": (spec.origin or (spec.submodule_search_locations[0]
                                     if spec.submodule_search_locations else None)),
            "version": version, "source": source}


DEFAULTS = Path(__file__).parent / "defaults" / "config.yaml"


def template_text() -> str:
    """The shipped starter config, as text.

    It is a real file in the package rather than a string in the source, so the
    same bytes are what `wimba config --init` copies, what a fresh install gets,
    and what `wimba.example.yaml` in the repository shows - one place to edit
    when a setting is added.
    """
    return DEFAULTS.read_text()


def ensure_user_config() -> Optional[Path]:
    """Create the user-level config from the template when there is none at all.

    So a fresh install has a file to open and edit instead of documentation
    telling it what it could have written. Returns the path when it creates one,
    None when a config already exists (of any kind) - it never touches one.
    """
    if os.environ.get("WIMBA_CONFIG") or local_config_path():
        return None
    path = user_config_path()
    if path.is_file():
        return None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(template_text())
    except OSError:
        return None            # a read-only home is not a reason to fail
    return path


def write_template(directory=None) -> Path:
    """Write the commented starter config, without overwriting an existing one."""
    folder = Path(directory or Path.cwd()).expanduser()
    path = folder / "wimba.yaml"
    if path.exists():
        raise FileExistsError(f"{path} already exists; edit it instead.")
    folder.mkdir(parents=True, exist_ok=True)
    path.write_text(template_text())
    return path


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


def _ensure_iw2d_on_path() -> None:
    """Put a non-installed IW2D checkout on sys.path, as for pytlwall.

    The bridge imports the IW2D *Python package* (a cppyy binding over the C++
    core); it has not called an executable since the July rewrite. `iw2d.binary`
    below is the older file-based path and is kept only for that.
    """
    path = (os.environ.get("WIMBA_IW2D_PATH")
            or _config_get("tools", "iw2d", "path"))
    if path:
        p = str(Path(path).expanduser())
        if Path(p).is_dir() and p not in sys.path:
            sys.path.insert(0, p)


def iw2d_available() -> bool:
    """True if the IW2D Python package can be imported (honouring a configured
    checkout path). Importing it loads the C++ core through cppyy, so a failure
    usually means GSL/GMP/MPFR/Arb are missing rather than IW2D itself."""
    _ensure_iw2d_on_path()
    try:
        import IW2D  # noqa: F401
    except Exception:
        return False
    return True


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
    return _find_spec("pytlwall") is not None


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
    """Summary used by `wimba status` (never raises).

    The per-engine entries were being read by the CLI but never filled in, so
    `wimba status` reported "not importable" even with pytlwall installed.
    """
    return {
        "config_file": str(config_path()),
        "config_exists": config_path().is_file(),
        "config_source": config_source(),
        "iw2d_binary": str(iw2d_binary(required=False) or ""),
        "pytlwall_available": pytlwall_available(),
        "iw2d_importable": iw2d_available(),
        "pytlwall": engine_location("pytlwall"),
        "iw2d": engine_location("iw2d"),
        "logging": logging_settings(),
    }


def default_method() -> str:
    """The default compute method for new elements and unspecified devices.
    User-editable in the WIMBA config file:  default_method: pytlwall | IW2D
    (pytlwall if unset). Note: the analytic resonator is not a wall engine -
    it models known resonant modes, so it is not offered as a wall default."""
    return str(load_config().get("default_method", "pytlwall"))
