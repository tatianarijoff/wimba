<p align="center">
  <img src="img/wimba_logo.png" alt="WIMBA" width="400">
</p>

<p align="center"><em>Wake &amp; Impedance Model Builder for Accelerators</em></p>

---

WIMBA builds the **impedance and wake model of an accelerator**. You assemble the
machine element by element — collimators, beam-pipe sections, cavities, kickers —
organise them in groups, and WIMBA combines them into a single model from which
longitudinal, dipolar and quadrupolar impedances and wakes can be read out.

## What it does

- **Build the machine like a real ring.** Add elements and organise them in
  groups (`collimators`, `pipes`, …), the way you would think about the lattice.
- **Compute or import, element by element.** Each element gets its impedance from
  a swappable source: computed (e.g. resistive wall) or imported from tabulated
  data (e.g. CST / ASCII).
- **Weight by the optics.** Element impedances are weighted by the local beta
  functions and lengths, matched by name against the machine optics (MAD-X /
  twiss).
- **Keep additional elements apart.** Pre-weighted contributions — for instance
  planned additions that already carry their own weighting — are summed in but
  kept separable.
- **Read out exactly what you need.** Longitudinal, dipolar and quadrupolar
  terms, as impedance `Z(f)` and/or wake `W(t)`, at the level of a single
  element, a group, or the whole machine. Resistive-wall sources can include the
  space-charge contribution, tagged separately.

## Data model

| Level | Meaning |
|-------|---------|
| `ImpedanceTerm` | a single multipole term — `Z(f)` and/or `W(t)`, tagged by multipole identity and physical origin |
| `Element` | a physical device, with a swappable impedance source and an optics policy |
| `ElementGroup` | a named bucket of like devices |
| `Machine` | the whole ring: groups weighted by the optics, plus pre-weighted additional elements |

## Documentation

Full documentation lives in [`docs/`](docs/README.md), starting with the
[data model](docs/DATA_MODEL.md) and the [resonator source](docs/RESONATOR.md).

## Install

Use a virtual environment (recommended on Debian/Ubuntu, where the system Python
is externally managed). `[dev]` also pulls in the test tools:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

```bash
# First-time setup: locate IW2D / pytlwall  (skip if you only use the resonator)
wimba setup
wimba status

# Test the software
python -m pytest
```

See [docs/SETUP.md](docs/SETUP.md) for the quick start and tool configuration.

## Status

Core data model and analytic resonator source: implemented and tested.
In progress: resistive-wall source (with optional space charge), tabulated-data
import, optics builder from MAD-X, I/O, command-line interface and graphical
interface.
