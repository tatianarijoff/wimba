"""Per-element result store with a resume file, totals, and lazy aggregation.

`materialize(project, out_dir)` computes each element once on the project grid and
writes:
  * per-element files  <Element>_<origin>_<Component>.dat  (impedance and wake),
  * a total/ folder with TOT_<Component>.dat (the beta-weighted machine totals),
  * <name>_resume.yaml listing the grids, the components produced, the totals,
    and, per element, its optics/info and what was computed.

`ResultStore` reads the resume and sums on demand, one element at a time.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml

from . import naming
from .core.terms import STANDARD_TERMS
from .io.tables import read_impedance, read_wake, write_impedance, write_wake


class _Flow(dict):
    """A dict rendered on a single line in the resume."""


yaml.SafeDumper.add_representer(
    _Flow, lambda d, data: d.represent_mapping("tag:yaml.org,2002:map", data, flow_style=True))


def _grid_spec(arr):
    if arr is None or len(arr) == 0:
        return None
    return _Flow({"min": float(arr[0]), "max": float(arr[-1]), "n": int(len(arr))})


def materialize(project, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    machine, freqs, times = project.machine, project.freqs, project.times

    resume = {"name": project.name,
              "grid": _Flow({"frequency": _grid_spec(freqs), "time": _grid_spec(times)}),
              "components": [], "total": {}, "groups": {}, "additional": []}
    seen_terms = set()

    def dump(element, base_dir):
        el_dir = base_dir / naming.safe(element.name)
        el_dir.mkdir(parents=True, exist_ok=True)
        imp, wak, origins = {}, {}, set()
        for term in element.terms():
            origins.add(term.origin)
            seen_terms.add(term.id)
            if term.has_impedance and freqs is not None:
                comp = naming.component(term.id, "Z")
                fn = naming.file_name(element.name, term.origin, term.id, "Z")
                write_impedance(el_dir / fn, freqs, term.impedance(freqs), term.plane)
                imp[comp] = str((el_dir / fn).relative_to(out))
            if term.has_wake and times is not None:
                comp = naming.component(term.id, "W")
                fn = naming.file_name(element.name, term.origin, term.id, "W")
                write_wake(el_dir / fn, times, term.wake(times), term.plane)
                wak[comp] = str((el_dir / fn).relative_to(out))

        m = element.meta
        entry = {"name": element.name,
                 "optics": _Flow({"position": m.get("position"),
                                  "beta_x": m.get("beta_x"), "beta_y": m.get("beta_y")}),
                 "info": _Flow(m.get("info", {})),
                 "origin": sorted(origins)[0] if len(origins) == 1 else sorted(origins),
                 "impedance": imp, "wake": wak}
        return entry

    for group in machine.groups:
        gdir = out / naming.safe(group.name)
        resume["groups"][group.name] = [dump(el, gdir) for el in group.elements]
    resume["additional"] = [dump(el, out / "additional") for el in machine.additional]

    # totals: the beta-weighted machine sums, written to total/
    tot_dir = out / "total"
    tot_dir.mkdir(exist_ok=True)
    total = {}
    if freqs is not None:
        for tid, Z in machine.impedance(freqs).items():
            fn = naming.total_name(tid, "Z")
            write_impedance(tot_dir / fn, freqs, Z, STANDARD_TERMS[tid].plane)
            total[naming.component(tid, "Z")] = f"total/{fn}"
    if times is not None:
        for tid, W in machine.wake(times).items():
            fn = naming.total_name(tid, "W")
            write_wake(tot_dir / fn, times, W, STANDARD_TERMS[tid].plane)
            total[naming.component(tid, "W")] = f"total/{fn}"
    resume["total"] = total
    resume["components"] = sorted(naming.component(t, "Z") for t in seen_terms)

    resume_path = out / f"{project.name}_resume.yaml"
    with open(resume_path, "w") as fh:
        yaml.safe_dump(resume, fh, sort_keys=False)
    return resume_path


class ResultStore:
    """Lazy reader/aggregator over a materialised results directory."""

    def __init__(self, out_dir):
        self.dir = Path(out_dir)
        matches = list(self.dir.glob("*_resume.yaml"))
        if not matches:
            raise FileNotFoundError(f"no *_resume.yaml found in {self.dir}")
        with open(matches[0]) as fh:
            self.resume = yaml.safe_load(fh)

    def groups(self):
        return list(self.resume["groups"])

    def elements(self, group=None):
        if group is None:
            names = [r["name"] for elems in self.resume["groups"].values() for r in elems]
            return names + [r["name"] for r in self.resume["additional"]]
        return [r["name"] for r in self.resume["groups"][group]]

    def _records(self, groups, include_additional):
        chosen = (self.resume["groups"] if groups is None
                  else {g: self.resume["groups"][g] for g in groups})
        for elems in chosen.values():
            yield from elems
        if include_additional:
            yield from self.resume["additional"]

    def _weight(self, rec, term_id):
        if rec["optics"].get("beta_x") is None:
            return 1.0
        return STANDARD_TERMS[term_id].beta_weight(rec["optics"]["beta_x"],
                                                   rec["optics"]["beta_y"])

    def _origin_ok(self, rec, want):
        if want is None:
            return True
        o = rec["origin"]
        return want == o if isinstance(o, str) else want in o

    def _accumulate(self, section, reader, plane, multipole, origin, groups, include_additional):
        out = {}
        for rec in self._records(groups, include_additional):
            if not self._origin_ok(rec, origin):
                continue
            for comp, relpath in rec[section].items():
                tid = STANDARD_TERMS[naming.term_of(comp)]
                if plane is not None and tid.plane != plane:
                    continue
                if multipole is not None and tid.category != multipole:
                    continue
                _, values = reader(self.dir / relpath)
                term_id = naming.term_of(comp)
                out[term_id] = out.get(term_id, np.zeros_like(values)) + \
                    self._weight(rec, term_id) * values
        return out

    def impedance(self, *, plane=None, multipole=None, origin=None,
                  groups=None, include_additional=True):
        return self._accumulate("impedance", read_impedance, plane, multipole,
                                origin, groups, include_additional)

    def wake(self, *, plane=None, multipole=None, origin=None,
             groups=None, include_additional=True):
        return self._accumulate("wake", read_wake, plane, multipole,
                                origin, groups, include_additional)
