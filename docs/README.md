<p align="center">
  <img src="../img/wimba_logo_small.png" alt="WIMBA" width="190">
</p>

# WIMBA documentation

- [Data model](DATA_MODEL.md) — the architecture and the core objects
  (`ImpedanceTerm`, `Element`, `ElementGroup`, `Machine`), beta weighting and how
  to query a machine.
- [Resonator source](RESONATOR.md) — the analytic resonator source: Chao
  formulas (matching xwakes), conventions and limitations.
- [Fourier transforms](FOURIER.md) — on-demand wake ↔ impedance transforms for
  consistency checks.

Planned, as the corresponding code lands:

- Resistive-wall source (via pytlwall, with optional space charge)
- Tabulated-data import (CST / ASCII)
- Optics builder from MAD-X
- Command-line interface and graphical interface
