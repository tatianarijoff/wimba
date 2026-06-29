<p align="center">
  <img src="wimba_logo_small.png" alt="WIMBA" width="190">
</p>

# WIMBA documentation

- [Data model](DATA_MODEL.md) — the architecture and the core objects
  (`ImpedanceTerm`, `Element`, `ElementGroup`, `Machine`), beta weighting and how
  to query a machine.
- [Resonator source](RESONATOR.md) — the analytic resonator source: Chao
  formulas, conventions and limitations.

Planned, as the corresponding code lands:

- Resistive-wall source (via pytlwall, with optional space charge)
- Tabulated-data import (CST / ASCII)
- Optics builder from MAD-X
- Input / output formats
- Command-line interface and graphical interface
