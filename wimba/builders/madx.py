"""Minimal MAD-X TFS (twiss) reader.

Reads a TFS table into  {element_name: {COLUMN: value}}  with column names as
written by MAD-X (NAME, S, L, BETX, BETY, ...). No dependency beyond the stdlib.

The table is keyed by name because that is how devices are matched to the
lattice. Names are therefore made unique on read: MAD-X numbers its drifts
(DRIFT_0, DRIFT_1, ...) so duplicates never arise there, but a table exported
from xsuite reuses one name for every instance of a shared element -- in the
FCC-ee Z lattice 11275 rows carry only 87 distinct names, 13% of the ring.
Overwriting them silently removed that length from the default pipe, so
duplicates now get a .2/.3/... suffix and are counted in ``duplicates``.
"""
from __future__ import annotations

from pathlib import Path


def read_twiss(path, on_duplicate: str = "rename") -> dict:
    """Read a TFS table.

    ``on_duplicate`` controls what happens when the same NAME appears twice:

    * ``"rename"`` (default) keeps every row, suffixing repeats with ``.2``,
      ``.3``, ... so lengths and positions survive. A device named after the
      first occurrence still resolves to it.
    * ``"error"`` raises, for callers that require a table MAD-X could have
      written.
    * ``"last"`` is the old behaviour: later rows overwrite earlier ones.
    """
    if on_duplicate not in ("rename", "error", "last"):
        raise ValueError(f"on_duplicate must be rename, error or last, not "
                         f"'{on_duplicate}'")
    columns = None
    table: dict = {}
    seen: dict = {}
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("@"):
            continue
        if line.startswith("*"):
            columns = line[1:].split()
            continue
        if line.startswith("$"):
            continue
        if columns is None:
            continue
        parts = line.split()
        row = {}
        for col, val in zip(columns, parts):
            v = val.strip('"')
            try:
                row[col] = float(v)
            except ValueError:
                row[col] = v
        name = str(row.get("NAME", parts[0].strip('"'))).strip('"')

        if name in table:
            if on_duplicate == "error":
                raise ValueError(
                    f"{Path(path).name}: element name '{name}' appears more than "
                    f"once. Pass on_duplicate='rename' to keep both rows.")
            if on_duplicate == "last":
                table[name] = row
                continue
            seen[name] = seen.get(name, 1) + 1
            name = f"{name}.{seen[name]}"
        table[name] = row
    return table


def mean_beta(table: dict) -> tuple:
    """The lattice's average beta functions, length-weighted: sum(b*L)/sum(L).

    Averaged over the **twiss rows**, every one of them, so the result is a
    property of the lattice. Averaging over the modelled elements instead would
    bias it high, since devices tend to sit where beta is large -- and the
    answer would then change every time a device was added to the model.

    Rows with no length contribute nothing, which is right: a marker occupies no
    ring. Returns (1.0, 1.0) for a table that carries no lengths at all, so a
    caller without optics falls back to the bare beta rather than dividing by
    zero.
    """
    sx = sy = total = 0.0
    for row in table.values():
        length = get(row, "L", "LENGTH")
        bx, by = get(row, "BETX", "BETA_X"), get(row, "BETY", "BETA_Y")
        if length is None or bx is None or by is None:
            continue
        try:
            length, bx, by = float(length), float(bx), float(by)
        except (TypeError, ValueError):
            continue
        if length <= 0.0:
            continue
        sx += bx * length
        sy += by * length
        total += length
    if total <= 0.0:
        return 1.0, 1.0
    return sx / total, sy / total


def duplicates(path) -> dict:
    """{original name: number of occurrences} for names that repeat.

    Cheap pre-flight check: a non-empty result means a reader keyed by name
    would have dropped rows.
    """
    counts: dict = {}
    columns = None
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("@") or line.startswith("$"):
            continue
        if line.startswith("*"):
            columns = line[1:].split()
            continue
        if columns is None:
            continue
        parts = line.split()
        try:
            idx = columns.index("NAME")
        except ValueError:
            idx = 0
        name = parts[idx].strip('"') if idx < len(parts) else parts[0].strip('"')
        counts[name] = counts.get(name, 0) + 1
    return {k: v for k, v in counts.items() if v > 1}


def get(row: dict, *names, default=None):
    """Case-insensitive column lookup (S, s, BETX, betx, ...)."""
    lower = {k.lower(): v for k, v in row.items()}
    for n in names:
        if n.lower() in lower:
            return lower[n.lower()]
    return default
