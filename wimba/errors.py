"""Errors that are a message to the user, not a bug report.

A missing file, a config that names an unknown source, an engine that is not
installed: none of these are faults in WIMBA, and none of them are worth six
frames of stack trace. They all derive from :class:`WimbaError`, which the
command line catches and prints as a single line before exiting with status 2.
``wimba --traceback ...`` turns that off when the stack is what you actually
want.

Anything *not* derived from :class:`WimbaError` keeps its traceback, because
then the traceback is the point.
"""
from __future__ import annotations

import difflib
from pathlib import Path


class WimbaError(Exception):
    """Base for errors meant to be read by the user of the command."""


class ConfigFileNotFound(WimbaError, FileNotFoundError):
    """A config named on the command line (or by the GUI) is not there.

    Also a `FileNotFoundError`, so callers that already catch that keep working.
    """


CONFIG_SUFFIXES = (".yaml", ".yml")


def _neighbours(folder: Path, wanted: str) -> list:
    """Config files in `folder`, closest names first."""
    try:
        names = sorted(p.name for p in folder.iterdir()
                       if p.is_file() and p.suffix.lower() in CONFIG_SUFFIXES)
    except OSError:
        return []
    close = difflib.get_close_matches(wanted, names, n=3, cutoff=0.5)
    return close or names[:5]


def check_input_file(path, what: str = "config file") -> Path:
    """Return `path` as a Path, or raise a readable error saying why not.

    The error names the absolute location that was searched -- a relative path
    in a message is useless unless the reader also knows the working directory
    it was resolved against -- and, when the folder holds config files with
    similar names, offers them. Mistyping the name of a file that is right there
    is the common case; `SubLHC.yaml` for `SubLHC_input.yaml` is the one that
    prompted this.
    """
    given = Path(path).expanduser()
    absolute = given if given.is_absolute() else (Path.cwd() / given)

    if given.is_file():
        return given

    lines = [f"    looked at: {absolute}"]

    if given.is_dir():
        found = _neighbours(given, given.name)
        if found:
            lines.append(f"    config files there: {', '.join(found)}")
        raise ConfigFileNotFound(
            f"{what} '{path}' is a directory, not a file.\n" + "\n".join(lines))

    folder = absolute.parent
    if not folder.is_dir():
        lines.append(f"    the folder {folder} does not exist either")
    else:
        found = _neighbours(folder, given.name)
        if found:
            label = "did you mean" if len(found) == 1 else "config files there"
            lines.append(f"    {label}: {', '.join(found)}")

    raise ConfigFileNotFound(
        f"{what} '{path}' does not exist.\n" + "\n".join(lines))


def read_config_text(path, what: str = "config file") -> str:
    """The text of a config file, or a readable error instead of a traceback."""
    return check_input_file(path, what).read_text()
