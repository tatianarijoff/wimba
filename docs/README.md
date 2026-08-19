<p align="center">
  <img src="../img/wimba_logo_small.png" alt="WIMBA" width="190">
</p>

# WIMBA documentation

**Start here**

- [Setup & quick start](SETUP.md) — install, locating IW2D / pytlwall.
- [Settings](SETTINGS.md) — `wimba.yaml`: engine paths, data directory, logging.
  Not to be confused with a machine config.

**The interface**

- [The graphical interface](GUI.md) — what each panel is for, what every File
  menu entry does, Load Machine vs Open Config, and what Problems is telling
  you. Start here if you use the GUI.
- [One component](COMPONENT.md) — computing a single chamber in the Component
  bench, with no machine around it.

**Building and computing a model**

- [Projects and scenarios](PROJECTS.md) — one machine at several energies:
  the project, the scenarios under it, the beam, and how two results end up on
  one plot.
- [Machine config reference](CONFIG.md) — the YAML that describes a machine,
  field by field, including the `beam:` block.
- [Assemble & run](ASSEMBLE_AND_RUN.md) — optics + devices → machine total
  (assemble/run/plot).
- [Beam and optics: who decides](BEAM_AND_OPTICS.md) — which gamma and which
  betas a device is computed with when a machine and an element each state
  their own, and how to check afterwards which values were used.
- [Building a machine](BUILD.md) — `wimba build` and `wimba show`; output
  layout, resume and totals.
- [Examples](EXAMPLES.md) — the five bundled examples and how to run them.

**Sources**

- [Resonator source](RESONATOR.md) — the analytic resonator: Chao formulas
  (matching xwakes), conventions and limitations.
- [Precalculated data](PRECALCULATED.md) — importing tabulated impedance / wake
  (CST, ASCII), and the import-map descriptor.
- [IW2D](IW2D.md) — installing it, the two conventions that differ from
  pytlwall, and the parameter mapping.
- [pytlwall configs](PYTLWALL_CFG.md) — loading a chamber `.cfg`, and why the
  frequency grid is rebuilt rather than reused.

**Reference**

- [Data model](DATA_MODEL.md) — the core objects (`ImpedanceTerm`, `Element`,
  `ElementGroup`, `Machine`), beta weighting, and how to query a machine.
- [Fourier transforms](FOURIER.md) — on-demand wake ↔ impedance transforms for
  consistency checks.
- [External data](DATA.md) — files too large to track, where to get them and
  where to put them.

## Reading these pages as HTML

The Markdown sources are the originals. To read them in a browser, with tables
and a stylesheet:

```bash
wimba docs
```

writes `docs/html/`, one page per document plus an index, and copies any images
they refer to. The folder is regenerated from the sources and is not tracked.

The same conversion drives **Help → Documentation** (F1) inside the
application: Qt renders Markdown but discards tables, and these pages are
largely tables.
