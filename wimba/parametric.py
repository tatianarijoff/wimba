"""Parametric projects: one machine, one layer parameter, several values.

An energy project collects cases chosen one by one, by duplication. A
parametric project is generated: it names one parameter of one layer, on one
element or on several that share the change, and the values it should take.
WIMBA writes one scenario per value from a single base config, so the cases
cannot differ in anything but that parameter - which is what makes the curves
comparable. See docs/PARAMETRIC.md.

    kind: parametric
    sweep:
      elements: [COLL.H, COLL.V]
      parameter: layers[0].material
      values: [copper, titanium, graphite]

Qt-free: the GUI, the command line and the tests use the same functions.
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from pathlib import Path

from .errors import WimbaError

# The layer fields a sweep may vary: the material as a whole, the thickness, or
# one of the six material parameters on its own.
FIELDS = ("material", "thickness", "sigma", "epsr", "tau", "k_Hz", "muinf_Hz", "RQ")
_PARAM = re.compile(r"^layers\[(\d+)\]\.(" + "|".join(FIELDS) + r")$")

# spellings the engines accept for the same quantity, removed when it is set
_ALIASES = {"sigma": ("sigmaDC",), "k_Hz": ("k",), "muinf_Hz": ("muinf",)}
_NO_MATERIAL = ("V", "PEC", "PMC")


class SweepError(WimbaError, ValueError):
    """A sweep that cannot be applied, said in terms of the config."""


@dataclass
class Sweep:
    elements: list
    parameter: str
    values: list

    @property
    def index(self) -> int:
        return int(_PARAM.match(self.parameter).group(1))

    @property
    def field(self) -> str:
        return _PARAM.match(self.parameter).group(2)

    def to_dict(self) -> dict:
        return {"elements": list(self.elements), "parameter": self.parameter,
                "values": list(self.values)}

    @classmethod
    def from_dict(cls, data) -> "Sweep":
        from .gui.model import MAX_SCENARIOS
        if not isinstance(data, dict):
            raise SweepError("sweep: expected elements, parameter and values.")
        elements = data.get("elements")
        if isinstance(elements, str):
            elements = [elements]
        if not elements or not all(isinstance(e, str) and e for e in elements):
            raise SweepError("sweep: 'elements' must name one element or more.")
        parameter = str(data.get("parameter") or "").strip()
        if not _PARAM.match(parameter):
            raise SweepError(
                f"sweep: parameter '{parameter}' is not one a sweep can vary. Write "
                f"layers[N].FIELD, N counting from 0 at the layer nearest the beam, "
                f"FIELD one of: {', '.join(FIELDS)}.")
        values = data.get("values")
        if not isinstance(values, list) or not values:
            raise SweepError("sweep: 'values' must list the values to compute.")
        if len(values) > MAX_SCENARIOS:
            raise SweepError(
                f"sweep: {len(values)} values, and a project holds at most "
                f"{MAX_SCENARIOS} cases - beyond that the curves share colours and "
                f"cannot be told apart. Split the range into two projects.")
        field = _PARAM.match(parameter).group(2)
        values = [_value(field, v) for v in values]
        if len({str(v).lower() for v in values}) != len(values):
            raise SweepError("sweep: a value appears twice; each case must differ.")
        return cls(elements=list(elements), parameter=parameter, values=values)


def _value(field, v):
    """One value of the sweep, checked the way the engines would check it."""
    if field == "material":
        if not isinstance(v, str) or not v.strip():
            raise SweepError(f"sweep: material values are names; '{v}' is not one.")
        return v.strip()
    if isinstance(v, str) and v.strip().lower() in ("inf", "infinity"):
        if field != "k_Hz":
            raise SweepError(f"sweep: {field} cannot be infinite.")
        return "inf"
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise SweepError(f"sweep: '{v}' is not a number, and {field} takes numbers.")
    if not math.isfinite(x):
        raise SweepError(f"sweep: {field} cannot be infinite.")
    if field in ("thickness", "sigma", "epsr", "k_Hz") and x <= 0:
        raise SweepError(f"sweep: {field} must be greater than zero, not {v}.")
    if x < 0:
        raise SweepError(f"sweep: {field} cannot be negative, not {v}.")
    return x


# ------------------------------------------------------------- the config side
def _dialect(cfg) -> str:
    if "devices" in cfg or "default_pipe" in cfg:
        return "assembly"
    if "groups" in cfg:
        return "machine"
    raise SweepError("the base config has neither devices: nor groups:, so it "
                     "describes no element to vary.")


def element_specs(cfg, names) -> dict:
    """name -> the config entry (the mapping itself, so edits land in `cfg`)."""
    found = {}
    if _dialect(cfg) == "assembly":
        entries = [spec for spec in (cfg.get("devices") or {}).values()]
    else:
        entries = [spec for els in (cfg.get("groups") or {}).values() for spec in els or []]
        entries += list(cfg.get("additional") or [])
    named = {spec.get("name"): spec for spec in entries if isinstance(spec, dict)}
    missing = [n for n in names if n not in named]
    if missing:
        walls = sorted(str(n) for n, spec in named.items() if n and spec.get("layers"))
        raise SweepError(
            f"sweep: no element named {', '.join(map(repr, missing))} in the base "
            f"config. Elements with layers written in it: "
            f"{', '.join(walls) or 'none'}.")
    for n in names:
        spec = named[n]
        if not spec.get("layers"):
            where = spec.get("file")
            raise SweepError(
                f"sweep: '{n}' has no layers written in the config"
                + (f" - they come from {where}, which a sweep does not edit" if where else "")
                + ". Write its layers inline to vary them.")
        found[n] = spec
    return found


def _check_layer(name, layers, sweep):
    i, field = sweep.index, sweep.field
    if i >= len(layers):
        raise SweepError(f"sweep: '{name}' has {len(layers)} layer(s); layers[{i}] "
                         f"does not exist (they count from 0, nearest the beam).")
    lay = layers[i]
    if str(lay.get("type", "CW")).upper() in _NO_MATERIAL:
        raise SweepError(f"sweep: layers[{i}] of '{name}' is a {lay.get('type')} "
                         f"layer, whose parameters no calculation reads.")
    if field == "thickness" and str(lay.get("thickness", "")).lower() == "inf":
        raise SweepError(f"sweep: layers[{i}] of '{name}' is the boundary, whose "
                         f"thickness is infinite by definition.")


def apply_value(layer, field, value, table) -> None:
    """Set one value on one layer, in place, so the layer states it unambiguously.

    A material is written as its numbers, with the name kept as `label:` for
    people - the same thing the interface writes - so a case depends on no list.
    A single material parameter set on a named layer first takes the material's
    other parameters as numbers and drops the name: a layer that said `copper` and
    carried another sigma would be two sources for one number.
    """
    from .materials import PARAMS, resolve_layers, unknown_materials_error
    if field == "material":
        entry = table.get(str(value).lower())
        if entry is None:
            raise unknown_materials_error([(value, "the sweep")])
        for key in ("material", "label", *[a for al in _ALIASES.values() for a in al]):
            layer.pop(key, None)
        for key in PARAMS:
            layer[key] = entry[key]
        layer["label"] = str(value)
        return
    if field in PARAMS and layer.get("material") is not None:
        # a thickness leaves the material alone: it is not one of its parameters
        missing = resolve_layers([layer], table, "the sweep")
        if missing:
            raise unknown_materials_error(missing)
        layer.pop("material", None)
        layer.pop("label", None)
    for alias in _ALIASES.get(field, ()):
        layer.pop(alias, None)
    layer[field] = value


def case_label(sweep: Sweep, value) -> str:
    """What the legend says for one case."""
    field = sweep.field
    if field == "material":
        return str(value)
    if field == "thickness":
        v = float(value)
        if v < 1e-3:
            return f"t = {v * 1e6:g} \u00b5m"
        if v < 1.0:
            return f"t = {v * 1e3:g} mm"
        return f"t = {v:g} m"
    if field == "sigma":
        return f"\u03c3 = {_sci(value)} S/m"
    return f"{field} = {_sci(value)}"


def _sci(value) -> str:
    """3 significant digits, exponent without padding: 1e5, 2.5e-12, 0.3."""
    if isinstance(value, str):
        return value
    text = f"{float(value):.3g}"
    if "e" in text:
        mantissa, exponent = text.split("e")
        text = f"{mantissa}e{int(exponent)}"
    return text


def _slug(i: int, label: str) -> str:
    from .gui.model import slugify
    text = label.replace("\u00b5", "u").replace("\u03c3", "sigma")
    text = "".join(c if c.isascii() else "_" for c in text)
    return f"{i + 1:02d}_{slugify(text)}"


def walls(cfg) -> dict:
    """name -> layers, for every element whose layers the config writes out:
    the elements a sweep can vary."""
    out = {}
    try:
        _dialect(cfg)
    except SweepError:
        return out
    if "devices" in cfg or "default_pipe" in cfg:
        entries = list((cfg.get("devices") or {}).values())
    else:
        entries = [e for els in (cfg.get("groups") or {}).values() for e in els or []]
        entries += list(cfg.get("additional") or [])
    for spec in entries:
        if isinstance(spec, dict) and spec.get("name") and spec.get("layers"):
            out[str(spec["name"])] = list(spec["layers"])
    return out


def parse_values(field, text) -> list:
    """Values typed as one line, separated by commas or spaces."""
    parts = [t for t in re.split(r"[,\s]+", str(text or "").strip()) if t]
    return parts if field == "material" else [_value(field, t) for t in parts]


def validate(cfg, sweep) -> Sweep:
    """Everything that can be checked before a file is written; the Sweep back."""
    from .materials import config_table, unknown_materials_error
    if not isinstance(sweep, Sweep):
        sweep = Sweep.from_dict(sweep)
    if cfg.get("beam") is None:
        raise SweepError("the base config states no beam, and every case is computed "
                         "at one energy: add a beam: block to it first.")
    for name, spec in element_specs(cfg, sweep.elements).items():
        _check_layer(name, spec["layers"], sweep)
    if sweep.field == "material":
        table = config_table(cfg.get("materials"))
        unknown = [v for v in sweep.values if str(v).lower() not in table]
        if unknown:
            raise unknown_materials_error([(v, "the sweep") for v in unknown])
    return sweep


def describe_layer(layer) -> str:
    """One layer in a few words, for the dialog: 'CW chimeranium, 25 mm'."""
    kind = str(layer.get("type", "CW")).upper()
    what = layer.get("material") or layer.get("label") or (
        f"\u03c3 {float(layer['sigma']):.3g}" if layer.get("sigma") is not None else "")
    t = layer.get("thickness")
    if str(t).lower() == "inf":
        size = "boundary"
    else:
        try:
            v = float(t)
            size = f"{v * 1e6:g} \u00b5m" if v < 1e-3 else f"{v * 1e3:g} mm"
        except (TypeError, ValueError):
            size = "?"
    return " ".join(x for x in (kind, str(what)) if x) + f", {size}"


# ------------------------------------------------------------ making a project
def create_project(base_config, directory, sweep, name=None, relative=False):
    """Write a parametric project: project.yaml plus one config per value.

    `relative=True` keeps the base config's data references relative to the
    project folder - for a project committed or moved together with its data,
    as the examples are. By default they become absolute, like any scenario.
    Returns the GProject.
    """
    import yaml

    from .core.beam import Beam
    from .gui.model import (GProject, GScenario, freeze_config, read_yaml_text,
                            write_yaml_text)
    from .materials import config_table

    base_config, directory = Path(base_config), Path(directory)
    if not isinstance(sweep, Sweep):
        sweep = Sweep.from_dict(sweep)
    if (directory / "project.yaml").exists():
        raise SweepError(f"{directory} already holds a project; choose an empty folder.")
    data = yaml.safe_load(base_config.read_text()) or {}
    sweep = validate(data, sweep)
    beam = Beam.from_dict(data["beam"])
    table = config_table(data.get("materials"))

    directory.mkdir(parents=True, exist_ok=True)
    project = GProject(name=name or f"{data.get('name', base_config.stem)} sweep",
                       dir=str(directory), grid=data.get("grid") or {},
                       kind="parametric", sweep=sweep.to_dict(),
                       base=(os.path.relpath(base_config.resolve(), directory.resolve())
                             if relative else str(base_config.resolve())))
    header = (f"Generated by a parametric project from {base_config.name}.\n"
              f"Differs from it only in {sweep.parameter} of "
              f"{', '.join(sweep.elements)}.")
    for i, value in enumerate(sweep.values):
        label = case_label(sweep, value)
        slug = _slug(i, label)
        dest = directory / f"{slug}_config.yaml"
        freeze_config(base_config, dest, relative=relative)
        cfg = read_yaml_text(dest.read_text())
        for spec in element_specs(cfg, sweep.elements).values():
            apply_value(spec["layers"][sweep.index], sweep.field, value, table)
        _case_comment(cfg, f"{header}\nThis case: {label}.")
        dest.write_text(write_yaml_text(cfg))
        for sub in ("output", "img"):
            (directory / slug / sub).mkdir(parents=True, exist_ok=True)
        project.add(GScenario(label=label, config=dest.name, beam=beam, slug=slug))
    project.current = 0
    (directory / "project.yaml").write_text(
        yaml.safe_dump(project.to_dict(), sort_keys=False, allow_unicode=True))
    return project


def _case_comment(cfg, text) -> None:
    """A comment at the top of a generated config, when the YAML keeps one."""
    setter = getattr(cfg, "yaml_set_start_comment", None)
    if setter is not None:
        setter(text)


# ------------------------------------------------------------------ checking
def problems(project) -> list:
    """Lines for Problems: cases that differ in more than the swept parameter.

    Nothing stops a user from editing one case in the panels; this is what says
    the comparison is no longer clean, and where.
    """
    import yaml

    from .materials import PARAMS
    if not getattr(project, "parametric", False) or not project.scenarios:
        return []
    try:
        sweep = Sweep.from_dict(project.sweep)
    except SweepError as exc:
        return [f"WARNING  parametric: {exc}"]
    field = sweep.field
    if field in ("material", "sigma"):
        drop = {"material", "label", *PARAMS, "sigmaDC", "k", "muinf"} \
            if field == "material" else {"material", "label", "sigma", "sigmaDC"}
    else:
        drop = {field, *_ALIASES.get(field, ())}

    def normal(sc):
        cfg = yaml.safe_load((Path(project.dir) / sc.config).read_text()) or {}
        for spec in element_specs(cfg, sweep.elements).values():
            lay = spec["layers"][sweep.index]
            for key in drop:
                lay.pop(key, None)
        beam = sc.beam.to_dict() if sc.beam is not None else None
        return cfg, beam

    out = []
    try:
        ref, ref_beam = normal(project.scenarios[0])
    except (OSError, SweepError) as exc:
        return [f"WARNING  parametric: {exc}"]
    first = project.scenarios[0].label
    for sc in project.scenarios[1:]:
        try:
            cfg, beam = normal(sc)
        except (OSError, SweepError) as exc:
            out.append(f"WARNING  parametric: '{sc.label}': {exc}")
            continue
        where = [k for k in sorted(set(cfg) | set(ref)) if cfg.get(k) != ref.get(k)]
        if beam != ref_beam:
            where.append("beam")
        if where:
            out.append(f"WARNING  parametric: '{sc.label}' differs from '{first}' in "
                       f"more than {sweep.parameter}: {', '.join(where)}. The curves "
                       f"no longer compare one parameter.")
    return out
