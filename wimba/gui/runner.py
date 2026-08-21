"""Background worker that runs a WIMBA study off the UI thread.

The GUI's Calculate action uses this so the window stays responsive; results are
routed into the existing panels by the main window (no separate window).
"""
from __future__ import annotations

import traceback
from pathlib import Path

import yaml
from PyQt6.QtCore import QThread, pyqtSignal

from ..assembly import load_assembly
from ..run import run as run_study


class RunWorker(QThread):
    log = pyqtSignal(str)
    done = pyqtSignal(object)      # {"result": AssemblyResult, "info": dict}
    failed = pyqtSignal(str)

    def __init__(self, config, out_dir=None, wake=False, fill_pipe=True,
                 overrides=None):
        super().__init__()
        self.config = str(config)
        self.out_dir = out_dir
        self.wake = wake
        self.fill_pipe = fill_pipe
        self.overrides = dict(overrides or {})
        # Values the GUI panels hold that must win over the file on disk - the
        # beam above all. The panel is what the user can see and change; a run
        # that silently used a different energy read from the file would be the
        # exact mismatch the Beam panel exists to prevent. The file is not
        # rewritten: an override applies to this run only.

    def _apply_overrides(self, cfg):
        if not self.overrides:
            return cfg
        cfg = dict(cfg)
        had = cfg.get("beam") or (
            {"gamma": cfg["gamma"]} if cfg.get("gamma") is not None else None)
        cfg.update(self.overrides)
        now = cfg.get("beam") or {"gamma": cfg.get("gamma")}
        if had is None:
            self.log.emit(f"  beam from the Beam panel: {now} "
                          f"(the file states none).")
        elif had != now:
            self.log.emit(f"  WARNING: the Beam panel says {now}, "
                          f"{Path(self.config).name} says {had}. Computing with "
                          f"the panel; the file on disk is unchanged.")
        return cfg

    def run(self):
        try:
            cfg = yaml.safe_load(Path(self.config).read_text()) or {}
            if not self.fill_pipe:
                cfg = dict(cfg)
                cfg.pop("default_pipe", None)

            self.log.emit(f"Assembling '{Path(self.config).name}' "
                          f"(default pipe: {'on' if self.fill_pipe else 'off'})...")
            cfg = self._apply_overrides(cfg)
            result = load_assembly(self.config, cfg=cfg)
            devices = sum(1 for r in result.rows if r.kind == "device")
            self.log.emit(f"  {len(result.rows)} assignment(s): {devices} device(s), "
                          f"{len(result.rows) - devices} default-pipe row(s), "
                          f"{len(result.collisions)} collision(s).")
            for w in getattr(result, "warnings", []):
                self.log.emit(f"  WARNING: {w}")

            self.log.emit("Computing...")
            info = run_study(self.config, cfg=cfg, out_dir=self.out_dir,
                             wake=self.wake, fill_pipe=self.fill_pipe)
            st = info["stats"]
            self.log.emit(f"  computed {st['computed']}, skipped {st['skipped']}, "
                          f"{st['geometries']} distinct geometr(y/ies).")
            self.log.emit(f"Done -> {info['out']}")
            self.done.emit({"result": result, "info": info})
        except Exception:
            self.failed.emit(traceback.format_exc())


class BuildWorker(QThread):
    """Runs the `build` pipeline (load_scenario + materialize) off the UI thread.

    The sibling of RunWorker: `run` executes a config's rules against a lattice,
    `build` computes exactly the elements a machine file lists. They write
    different layouts, which is why the Results panel reads both.
    """
    log = pyqtSignal(str)
    done = pyqtSignal(object)      # {"info": {...}}
    failed = pyqtSignal(str)

    def __init__(self, config, out_dir=None, beam=None):
        super().__init__()
        self.config = str(config)
        self.out_dir = out_dir
        self.beam = beam
        # The panel wins over the file, exactly as it does for RunWorker. Until
        # this existed the two pipelines disagreed: an assembly config was
        # computed at the energy on screen, a machine file at the energy on
        # disk. The file is not rewritten -- an override applies to this run.

    def _apply_beam(self, scenario):
        if self.beam is None:
            return
        had = getattr(scenario, "beam", None)
        if had is None:
            self.log.emit(f"  beam from the Beam panel: {self.beam.label()} "
                          f"(the file states none).")
        elif had.label() != self.beam.label():
            self.log.emit(f"  WARNING: the Beam panel says {self.beam.label()}, "
                          f"{Path(self.config).name} says {had.label()}. Building "
                          f"with the panel; the file on disk is unchanged.")
        scenario.beam = self.beam

    def run(self):
        try:
            from ..builders import load_scenario
            from ..store import materialize

            name = Path(self.config).name
            self.log.emit(f"Building '{name}'...")
            scenario = load_scenario(self.config)
            self._apply_beam(scenario)
            n_groups = len(scenario.machine.groups)
            n_el = sum(len(g.elements) for g in scenario.machine.groups)
            n_add = len(scenario.machine.additional)
            beam = f", {scenario.beam.label()}" if scenario.beam else ""
            self.log.emit(f"  {n_el} element(s) in {n_groups} group(s), "
                          f"{n_add} additional{beam}.")

            out = self.out_dir or str(Path(self.config).with_suffix("")) + "_output"
            resume = materialize(scenario, out)
            self.log.emit(f"Done -> {out}")
            self.done.emit({"info": {
                "out": str(out), "resume": str(resume),
                "stats": {"computed": n_el + n_add, "skipped": 0,
                          "elements": n_el, "additional": n_add,
                          "groups": n_groups, "notes": []}}})
        except Exception:
            self.failed.emit(traceback.format_exc())
