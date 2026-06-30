"""Per-element result store with lazy, memory-bounded aggregation.

Large lattices should not live in memory. `materialize()` computes each element
once on a common grid and writes one file per (quantity, origin, term) under a
per-element folder, plus a manifest. `ResultStore` then reads those files **one
element at a time** and sums only what a query asks for - the whole machine, a
single group ("all the pipes"), a single element, a given origin or multipole -
without holding the whole lattice in memory.

Per-element terms are stored beta-free; the element's beta (resolved from the
optics at materialise time) is recorded in the manifest and applied as a weight
during aggregation, exactly as the in-memory Machine does. Pre-weighted elements
(e.g. an externally summed model dropped into `additional`) are summed as-is.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml

from .core.terms import STANDARD_TERMS
from .io.tables import read_impedance, read_wake, write_impedance, write_wake


def _safe(name: str) -> str:
    return str(name).replace("/", "_").replace("\\", "_").replace(" ", "_")


def materialize(machine, out_dir, freqs=None, times=None):
    """Compute each element once and write its terms to per-element files."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"version": 1, "groups": {}, "additional": []}

    def dump(element, base_dir):
        el_dir = base_dir / _safe(element.name)
        el_dir.mkdir(parents=True, exist_ok=True)
        entries = []
        for term in element.terms():
            if term.has_impedance and freqs is not None:
                fn = f"Z__{term.origin}__{term.id}.dat"
                write_impedance(el_dir / fn, freqs, term.impedance(freqs), term.plane)
                entries.append({"quantity": "Z", "origin": term.origin,
                                "term": term.id, "file": str((el_dir / fn).relative_to(out))})
            if term.has_wake and times is not None:
                fn = f"W__{term.origin}__{term.id}.dat"
                write_wake(el_dir / fn, times, term.wake(times), term.plane)
                entries.append({"quantity": "W", "origin": term.origin,
                                "term": term.id, "file": str((el_dir / fn).relative_to(out))})
        rec = {"name": element.name, "terms": entries}
        if element.optics.pre_weighted:
            rec["pre_weighted"] = True
        else:
            bx, by = element.optics.resolve(machine.twiss, element.name)
            rec["beta_x"], rec["beta_y"] = float(bx), float(by)
        return rec

    for group in machine.groups:
        gdir = out / _safe(group.name)
        manifest["groups"][group.name] = [dump(el, gdir) for el in group.elements]
    manifest["additional"] = [dump(el, out / "additional") for el in machine.additional]

    with open(out / "manifest.yaml", "w") as fh:
        yaml.safe_dump(manifest, fh, sort_keys=False)
    return out


class ResultStore:
    """Lazy reader/aggregator over a materialised results directory."""

    def __init__(self, out_dir):
        self.dir = Path(out_dir)
        with open(self.dir / "manifest.yaml") as fh:
            self.manifest = yaml.safe_load(fh)

    def groups(self):
        return list(self.manifest["groups"])

    def elements(self, group=None):
        if group is None:
            names = [r["name"] for elems in self.manifest["groups"].values() for r in elems]
            names += [r["name"] for r in self.manifest["additional"]]
            return names
        return [r["name"] for r in self.manifest["groups"][group]]

    def _records(self, groups, include_additional):
        chosen = (self.manifest["groups"] if groups is None
                  else {g: self.manifest["groups"][g] for g in groups})
        for elems in chosen.values():
            yield from elems
        if include_additional:
            yield from self.manifest["additional"]

    def _weight(self, rec, term_id):
        if rec.get("pre_weighted"):
            return 1.0
        return STANDARD_TERMS[term_id].beta_weight(rec["beta_x"], rec["beta_y"])

    def _accumulate(self, quantity, reader, plane, multipole, origin, groups, include_additional):
        out = {}
        for rec in self._records(groups, include_additional):
            for e in rec["terms"]:
                if e["quantity"] != quantity:
                    continue
                tid = STANDARD_TERMS[e["term"]]
                if plane is not None and tid.plane != plane:
                    continue
                if multipole is not None and tid.category != multipole:
                    continue
                if origin is not None and e["origin"] != origin:
                    continue
                _, values = reader(self.dir / e["file"])
                contrib = self._weight(rec, e["term"]) * values
                out[e["term"]] = out.get(e["term"], np.zeros_like(contrib)) + contrib
        return out

    def impedance(self, *, plane=None, multipole=None, origin=None,
                  groups=None, include_additional=True):
        return self._accumulate("Z", read_impedance, plane, multipole, origin,
                                groups, include_additional)

    def wake(self, *, plane=None, multipole=None, origin=None,
             groups=None, include_additional=True):
        return self._accumulate("W", read_wake, plane, multipole, origin,
                                groups, include_additional)
