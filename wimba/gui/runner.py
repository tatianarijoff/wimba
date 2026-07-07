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

    def __init__(self, config, out_dir=None, wake=False, fill_pipe=True):
        super().__init__()
        self.config = str(config)
        self.out_dir = out_dir
        self.wake = wake
        self.fill_pipe = fill_pipe

    def run(self):
        try:
            cfg = yaml.safe_load(Path(self.config).read_text()) or {}
            if not self.fill_pipe:
                cfg = dict(cfg)
                cfg.pop("default_pipe", None)

            self.log.emit(f"Assembling '{Path(self.config).name}' "
                          f"(default pipe: {'on' if self.fill_pipe else 'off'})...")
            result = load_assembly(self.config, cfg=cfg)
            devices = sum(1 for r in result.rows if r.kind == "device")
            self.log.emit(f"  {len(result.rows)} assignment(s): {devices} device(s), "
                          f"{len(result.rows) - devices} default-pipe row(s), "
                          f"{len(result.collisions)} collision(s).")

            self.log.emit("Computing...")
            info = run_study(self.config, out_dir=self.out_dir, wake=self.wake,
                             fill_pipe=self.fill_pipe)
            st = info["stats"]
            self.log.emit(f"  computed {st['computed']}, skipped {st['skipped']}, "
                          f"{st['geometries']} distinct geometr(y/ies).")
            self.log.emit(f"Done -> {info['out']}")
            self.done.emit({"result": result, "info": info})
        except Exception:
            self.failed.emit(traceback.format_exc())
