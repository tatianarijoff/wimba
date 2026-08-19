"""The named materials a CW layer can be filled from.

The catalogue is data, not code: `wimba/defaults/materials.yaml`. What reaches
a config is always the numbers - a material name is a way of typing them, and
nothing downstream ever has to know the name existed.

Editing a parameter by hand does not redefine the material: the layer simply
stops matching any entry and is shown as custom. The catalogue is only changed
through Materials > Add Material, and a material added there is written into
the config being edited, never back into this file.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml

CATALOGUE = Path(__file__).resolve().parent / "defaults" / "materials.yaml"

# A user's own materials, layered on top of the catalogue. Same convention as
# wimba.yaml: the nearest one walking up from the working directory, so a file
# at the top of a working copy covers everything run inside it. It is not part
# of the package and is not committed - see custom_materials.example.yaml.
CUSTOM_NAMES = ("custom_materials.yaml", "custom_materials.yml")


# What a CW layer gets when the catalogue says nothing else. These are
# pytlwall's own defaults (pytlwall/layer.py) for everything except sigma,
# which the material supplies.
NEUTRAL = {"epsr": 1.0, "tau": 0.0, "k_Hz": "inf", "muinf_Hz": 0.0, "RQ": 0.0}

# The parameters a material fixes. `thickness` is deliberately not one of them:
# how thick the wall is has nothing to do with what it is made of.
PARAMS = ("sigma", "epsr", "tau", "k_Hz", "muinf_Hz", "RQ")


def _number(value):
    """YAML 1.1 only reads 5.8e+7 as a float, not 5.8e7 - and the file is meant
    to be edited by people, not by a parser. Coerce here so the spelling in the
    catalogue never decides whether a conductivity is a number or a word.
    `inf` stays the word it is: pytlwall reads it that way."""
    if isinstance(value, str):
        if value.strip().lower() in ("inf", "infinity", "+inf"):
            return "inf"
        try:
            return float(value)
        except ValueError:
            return value
    return value


def custom_path(start=None) -> Optional[Path]:
    """The user's custom_materials.yaml, if there is one.

    `$WIMBA_MATERIALS` names it outright; otherwise the nearest one at or above
    the working directory, then the user config directory.
    """
    env = os.environ.get("WIMBA_MATERIALS")
    if env:
        # An explicit instruction wins even when the file does not exist yet:
        # that is where Save is meant to create it.
        return Path(env).expanduser()
    here = Path(start or Path.cwd()).expanduser().resolve()
    if here.is_file():
        here = here.parent
    for folder in (here, *here.parents):
        for name in CUSTOM_NAMES:
            candidate = folder / name
            if candidate.is_file():
                return candidate
    fallback = Path.home() / ".config" / "wimba" / "custom_materials.yaml"
    return fallback if fallback.is_file() else None


def _read(path: Path) -> dict:
    """One materials file: {name: {...}}, with the numbers coerced."""
    try:
        data = yaml.safe_load(Path(path).read_text()) or {}
    except (OSError, yaml.YAMLError):
        return {"default": None, "materials": {}}
    entries = {}
    for name, entry in (data.get("materials") or {}).items():
        entries[name] = {k: (_number(v) if k in PARAMS else v)
                         for k, v in (entry or {}).items()}
    return {"default": data.get("default"), "materials": entries}


@lru_cache(maxsize=1)
def _catalogue() -> dict:
    """The shipped catalogue with the user's file layered over it.

    A custom entry with the name of a catalogue one replaces it: someone who
    has measured their own copper should be able to say so once. The catalogue
    is never written to - it belongs to the package.
    """
    base = _read(CATALOGUE)
    path = custom_path()
    if path is None:
        return base
    extra = _read(path)
    merged = dict(base["materials"])
    for name, entry in extra["materials"].items():
        merged[name] = {**merged.get(name, {}), **entry,
                        "custom_from": str(path)}
    return {"default": extra.get("default") or base["default"],
            "materials": merged}


def reload() -> None:
    """Forget the loaded files, so an edited custom_materials.yaml is picked up
    without restarting."""
    _catalogue.cache_clear()


def _entry(name: str) -> Optional[dict]:
    return _catalogue()["materials"].get(name)


def names() -> list[str]:
    """Every material that can be chosen, the user's own first."""
    entries = _catalogue()["materials"]
    mine = [n for n, e in entries.items() if e.get("custom_from")]
    return mine + [n for n in entries if n not in mine]


def origin(name: str) -> str:
    entry = _entry(name)
    if entry is None:
        return "unknown"
    return "custom file" if entry.get("custom_from") else "catalogue"



def label(name: str) -> str:
    return (_entry(name) or {}).get("label") or name


def note(name: str) -> str:
    return (_entry(name) or {}).get("note", "")


def default_name() -> Optional[str]:
    """The material a new layer starts from. The custom file may name its own."""
    entries = _catalogue()["materials"]
    wanted = _catalogue()["default"]
    if wanted in entries:
        return wanted
    return names()[0] if entries else None


def parameters(name: str) -> dict:
    """The six numbers for `name`, completed with the neutral defaults."""
    entry = _entry(name)
    if entry is None:
        raise KeyError(f"unknown material: {name}")
    out = dict(NEUTRAL)
    out.update({k: v for k, v in entry.items() if k in PARAMS})
    return out


def apply_to(layer: dict, name: str) -> dict:
    """Fill `layer` with the material's parameters, in place.

    The name itself is deliberately not written: what travels in a config is
    the numbers, so a file computes the same for someone who has never seen
    your custom_materials.yaml.
    """
    layer.update(parameters(name))
    layer["type"] = "CW"
    return layer


def _same(a, b) -> bool:
    if isinstance(a, str) or isinstance(b, str):
        return str(a).strip().lower() == str(b).strip().lower()
    if a is None or b is None:
        return a is b
    return abs(float(a) - float(b)) <= 1e-9 * max(1.0, abs(float(b)))


def match(layer: dict) -> Optional[str]:
    """Which material this layer's numbers correspond to, if any.

    Used to show a layer read from a config as its material rather than as a
    row of anonymous figures. A layer that matches nothing is custom, which is
    a perfectly good thing for a layer to be.
    """
    if str(layer.get("type") or "CW").upper() != "CW":
        return None
    for name in names():
        wanted = parameters(name)
        if all(_same(layer.get(k, NEUTRAL.get(k)), v) for k, v in wanted.items()):
            return name
    return None


def sigma_table() -> dict:
    """name -> conductivity, for resolving `material:` in a config.

    This is what used to be the MATERIALS dict inside sources/pytlwall_bridge.py.
    It lives in the catalogue file now: a list of materials is data, and having
    it in two places meant the same name could resolve to two conductivities
    depending on which one you happened to reach.

    Keys are lower-cased, as the resolver compares them.
    """
    out = {}
    for name in names():
        sigma = (_entry(name) or {}).get("sigma")
        if sigma is not None:
            out[str(name).lower()] = float(sigma)
    return out


DEFAULT_SIGMA = 1.0e6          # pytlwall's own, for a layer that names nothing


def sigma_of(material) -> float:
    """The conductivity of a named material, or pytlwall's default."""
    if material is None:
        return DEFAULT_SIGMA
    return sigma_table().get(str(material).lower(), DEFAULT_SIGMA)


# ------------------------------------------------------------------ writing
def custom_entries() -> dict:
    """Just the entries that come from the user's file, name -> fields."""
    out = {}
    for name, entry in _catalogue()["materials"].items():
        if entry.get("custom_from"):
            out[name] = {k: v for k, v in entry.items() if k != "custom_from"}
    return out


def catalogue_entries() -> dict:
    """The packaged ones, which are never written to."""
    return {name: entry for name, entry in _catalogue()["materials"].items()
            if not entry.get("custom_from")}


def save_target(start=None) -> Path:
    """Where Save writes: the custom file in use, or a new one at the top of
    the working directory if there is none yet."""
    path = custom_path(start)
    if path is not None:
        return path
    return Path(start or Path.cwd()).expanduser().resolve() / "custom_materials.yaml"


def save_custom(entries: dict, path=None) -> Path:
    """Write the user's materials, replacing the file's `materials:` block.

    Only the user's own file is ever written. The packaged catalogue belongs to
    WIMBA, and a value typed for one chamber has no business becoming everyone
    else's copper.
    """
    path = Path(path or save_target())
    header = ("# Your own materials, layered on top of the ones WIMBA ships\n"
              "# with. Written by Materials > Save; edit by hand if you prefer.\n"
              "# A name used here replaces the catalogue entry of the same name.\n"
              "#\n"
              "# What reaches a calculation is always the numbers: a config\n"
              "# produced by WIMBA carries them, never the material name.\n\n")
    body = {"materials": {
        name: {k: v for k, v in entry.items() if v not in (None, "")}
        for name, entry in entries.items()}}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + yaml.safe_dump(body, sort_keys=False,
                                            default_flow_style=False))
    reload()
    return path
