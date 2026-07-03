"""Readers for the pywit/LHC-model JSON data files.

These just load the JSON and expose it in a predictable shape; normalisation into
WIMBA terms happens where the data is used.
"""
from __future__ import annotations

import json
from pathlib import Path


def read_collimators(path) -> dict:
    """name -> {halfgap, length, layers, ...}."""
    return json.loads(Path(path).read_text())


def read_resonators(path) -> dict:
    """{name, length, modes:[{Rl,Ql,fl, Rxd,Qxd,fxd, Ryd,Qyd,fyd}, ...]}."""
    return json.loads(Path(path).read_text())
