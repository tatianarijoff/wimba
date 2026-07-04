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

Full documentation lives in [`docs/`](docs/README.md). Good starting points: the
[examples](docs/EXAMPLES.md) and how to run them, the
[assemble & run flow](docs/ASSEMBLE_AND_RUN.md), the
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

Most compute paths use **pytlwall**; install it into the same environment (it is
not on PyPI):

```bash
pip install -e /path/to/TLWallNew
```

**Assemble & run a machine** (optics + devices → machine total):

```bash
# the assignment array only: positions, names, method, beta, collisions
wimba assemble examples/RoundChamber/RoundChamber_input.yaml

# assemble + compute + machine total + default Re/Im plots (+ wake)
wimba run examples/RoundChamber/RoundChamber_input.yaml --wake

# (re)plot chosen components from a totals CSV
wimba plot examples/RoundChamber/RoundChamber_output/single_elements/total.csv \
           --components ZLong,ZDipX
```

**Build a machine from groups of elements** (analytic / imported sources):

```bash
wimba build examples/SubLHC/SubLHC_input.yaml
wimba show  examples/SubLHC/SubLHC_output
```

**First-time tool setup / self-check:**

```bash
wimba setup      # locate IW2D / pytlwall (skip if you only use the resonator)
wimba status
```

The four bundled examples — including a single-chamber verification against known
values — are described in **[docs/EXAMPLES.md](docs/EXAMPLES.md)**. For tool
configuration see [docs/SETUP.md](docs/SETUP.md); run the tests with
`python -m pytest`.

## Status

Implemented and tested: the core data model and analytic resonator source; the
optics builder from MAD-X; the assemble/run pipeline (beta resolution, default
resistive wall, per-geometry caching, machine total, Re/Im and wake plots); the
pytlwall compute bridge (impedance and native wake); tabulated-data import; and
the command-line interface (`assemble`, `run`, `plot`, `build`, `show`, `setup`,
`status`).

In progress: wiring the resonator / precalculated / IW2D bridges into `run` (so
lumped resonators such as RF HOMs enter the total), and the graphical interface.
