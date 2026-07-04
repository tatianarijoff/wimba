<p align="center">
  <img src="../img/wimba_logo_small.png" alt="WIMBA" width="190">
</p>

# WIMBA documentation

- [Setup & quick start](SETUP.md) — install, `wimba setup`, locating IW2D /
  pytlwall. **Start here.**
- [Data model](DATA_MODEL.md) — the architecture and the core objects
  (`ImpedanceTerm`, `Element`, `ElementGroup`, `Machine`), beta weighting and how
  to query a machine.
- [Examples](EXAMPLES.md) — the four bundled examples and how to run them.
- [Assemble & run](ASSEMBLE_AND_RUN.md) — optics + devices -> machine total (assemble/run/plot).
- [Building a machine](BUILD.md) — `wimba build` and `wimba show`; output layout, resume and totals.
- [Machine config reference](CONFIG.md) — the YAML format, field by field.
- [Resonator source](RESONATOR.md) — the analytic resonator source: Chao
  formulas (matching xwakes), conventions and limitations.
- [Fourier transforms](FOURIER.md) — on-demand wake ↔ impedance transforms for
  consistency checks.

Planned, as the corresponding code lands:

- Resistive-wall source (via pytlwall, with optional space charge)
- Tabulated-data import (CST / ASCII)
- Optics builder from MAD-X
- Graphical interface
