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
[precalculated data import](docs/PRECALCULATED.md), the
[data model](docs/DATA_MODEL.md) and the [resonator source](docs/RESONATOR.md).

## Install

Use a virtual environment (recommended on Debian/Ubuntu, where the system Python
is externally managed). `[dev]` also pulls in the test tools:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Two ways to build a model

WIMBA has two workflows. Both produce impedance/wake models, but they start from
different descriptions of the machine - the difference is **what you hand to
WIMBA**.

### `assemble` / `run` - lattice-driven (covers the whole ring)

You give the **optics** (a MAD-X twiss for the full lattice), a few **named
devices** (collimators, a cavity, a single chamber...), and one **default
resistive wall**. WIMBA sweeps every lattice location, assigns each either one of
your devices or the default pipe, resolves the local beta **by position**
(interpolated from the twiss, then by name), flags collisions, and sums everything
into the machine total.

Use it when you want a **realistic model of the entire ring**, where the beam pipe
contributes everywhere and only some locations carry special devices. This is the
flow behind the LHC and RoundChamber examples.

```bash
wimba assemble <config.yaml>   # the assignment array: positions, beta, methods, collisions
wimba run      <config.yaml>   # + compute + machine total + Re/Im plots (--wake for the wake)
wimba plot     <name>_output/single_elements/total.csv --components ZLong,ZDipX
```

### `build` - element-driven (exactly what you list)

You describe the machine as **named groups of elements you list explicitly**. Each
element gets its impedance from a source (analytic resonator, imported table) and
is weighted by the optics **matched by name**. There is no automatic beam pipe and
no full-lattice sweep: the model is exactly the elements you wrote down.

Use it when you have a **defined set of impedance contributions** to combine and
weight, without covering the whole ring. This is the flow behind the SubLHC
example.

```bash
wimba build <config.yaml>      # materialise the machine into <name>_output/
wimba show  <name>_output      # summarise it
```

### Which one?

|  | `assemble` / `run` | `build` |
|---|---|---|
| you provide | optics + a few devices + a default pipe | a hand-listed set of elements |
| the beam pipe | default resistive wall on every lattice segment | not added automatically |
| beta weighting | by position (interpolated), then by name | by name |
| covers | the whole lattice | exactly what you list |
| collision check | yes | no |
| output | machine total (+ opt-in per-device) and plots | per-origin tables + a resume |
| typical use | realistic full-machine model | combine a defined set of sources |

## Running

Most compute paths use **pytlwall**; install it into the same environment (it is
not on PyPI):

```bash
pip install -e /path/to/TLWallNew
```

Try the single-chamber verification first (quick, and confirms the numbers):

```bash
wimba run examples/RoundChamber/RoundChamber_input.yaml --wake
```

First-time tool setup / self-check:

```bash
wimba setup      # locate IW2D / pytlwall (skip if you only use the resonator)
wimba status
```

The four bundled examples are described in **[docs/EXAMPLES.md](docs/EXAMPLES.md)**,
and each example folder has its own README (files provided, shell and GUI usage,
outputs). For tool configuration see [docs/SETUP.md](docs/SETUP.md).

### Tests

```bash
pip install -e ".[dev]"       # pytest (+ xwakes for the resonator cross-checks)
python -m pytest              # -q for the short summary
```

Tests that need pytlwall or PyQt6 are skipped automatically when those are not
installed.

## Graphical interface

The desktop GUI (PyQt6) drives the same engine. Install the extra and launch it:

```bash
pip install -e ".[gui]"
python -m wimba.gui        # or: wimba-gui
```

In the GUI you can load a machine or an assembly config (`File → Load
Machine` / `Open Config`), inspect elements (geometry, layers with the full
pytlwall parameter set, models, optics), and run `Calculate → Whole
Machine`. After a calculation the **Results** panel lists everything that was
computed - total, per-device and aggregated default pipe; wall, indirect
space-charge and wall+ISC impedance components; wakes. Double-click or drag
quantities into the **Plot Workspace** (log/linear axes, editable curve list,
PNG/CSV export) or the **Results Table** (add/remove columns, CSV export).
`File → Open Results` reopens an existing output folder without
recomputing.

## Status

Implemented and tested: the core data model; the optics builder from MAD-X; the
assemble/run pipeline (beta resolution, default resistive wall, per-geometry
caching, collision detection, machine total); the compute engine shared by both
workflows - pytlwall (full layer parameter set, CIRCULAR/ELLIPTICAL/RECTANGULAR
chambers, impedance and native wake, indirect space charge kept as separate
components), analytic resonator (lumped, e.g. RF HOMs) and precalculated file
import; the command-line interface (`assemble`, `run`, `plot`, `build`, `show`,
`setup`, `status`); and the graphical interface with the results workspace
(tree of computed quantities, plot/table with export).

In progress: IW2D execution (the bridge is in place, the external binary is not
wired yet), direct space charge as a separate machine-wide output, saving an
edited machine back to a config, and per-machine default-pipe presets.

## License

WIMBA is released under the GNU General Public License v3 (see [LICENSE](LICENSE)).
