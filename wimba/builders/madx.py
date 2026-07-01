"""Minimal MAD-X TFS (twiss) reader.

Reads a TFS table into  {element_name: {COLUMN: value}}  with column names as
written by MAD-X (NAME, S, L, BETX, BETY, ...). No dependency beyond the stdlib.
"""
from __future__ import annotations

from pathlib import Path


def read_twiss(path) -> dict:
    columns = None
    table: dict = {}
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
        table[name] = row
    return table


def get(row: dict, *names, default=None):
    """Case-insensitive column lookup (S, s, BETX, betx, ...)."""
    lower = {k.lower(): v for k, v in row.items()}
    for n in names:
        if n.lower() in lower:
            return lower[n.lower()]
    return default
