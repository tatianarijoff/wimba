"""Naming conventions for output files and terms.

File names read as  <Element>_<origin>_<Component>.dat, e.g. C1_res_ZLong.dat,
C1_res_WDipX.dat. Totals live in total/ as TOT_<Component>.dat.
"""
from __future__ import annotations

# term id  ->  multipole label used in file/component names
_MULTIPOLE = {
    "zlong": "Long", "zxdip": "DipX", "zydip": "DipY",
    "zxquad": "QuadX", "zyquad": "QuadY",
}
_MULTIPOLE_REV = {v: k for k, v in _MULTIPOLE.items()}

# physical origin -> short tag used in file names
ORIGIN_SHORT = {
    "resonator": "res", "cst": "cst", "imported": "imp",
    "resistive_wall": "rw", "space_charge": "sc", "space_charge_direct": "dsc",
}


def component(term_id: str, quantity: str) -> str:
    """('zxdip', 'Z') -> 'ZDipX';  ('zlong', 'W') -> 'WLong'."""
    return f"{quantity}{_MULTIPOLE[term_id]}"


def term_of(component_label: str) -> str:
    """'ZDipX' -> 'zxdip'."""
    return _MULTIPOLE_REV[component_label[1:]]


def quantity_of(component_label: str) -> str:
    """'ZDipX' -> 'Z'."""
    return component_label[0]


def origin_short(origin: str) -> str:
    return ORIGIN_SHORT.get(origin, origin[:3])


def safe(name: str) -> str:
    return str(name).replace("/", "_").replace("\\", "_").replace(" ", "_")


def file_name(element_name: str, origin: str, term_id: str, quantity: str) -> str:
    return f"{safe(element_name)}_{origin_short(origin)}_{component(term_id, quantity)}.dat"


def total_name(term_id: str, quantity: str) -> str:
    return f"TOT_{component(term_id, quantity)}.dat"
