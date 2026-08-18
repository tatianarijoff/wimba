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
- **State the beam.** A particle and one number — gamma, beta, energy, kinetic
  energy or momentum — with the others derived. There is no default energy: a
  calculation that needs one and is not given one stops rather than assuming.
- **Compare the same machine at several energies.** A *project* holds several
  *scenarios* on one shared grid, computed and plotted side by side.
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
| `Scenario` | a machine plus the beam it is computed with |
| `Project` | the scenarios being compared, and the grid they share |

## Documentation

Full documentation lives in [`docs/`](docs/README.md). Good starting points: the
[settings file](docs/SETTINGS.md), the [examples](docs/EXAMPLES.md) and how to
run them, [projects and scenarios](docs/PROJECTS.md), the
[assemble & run flow](docs/ASSEMBLE_AND_RUN.md), the
[machine config reference](docs/CONFIG.md) and the
[data model](docs/DATA_MODEL.md).

## Install

Use a virtual environment (recommended on Debian/Ubuntu, where the system Python
is externally managed). `[dev]` also pulls in the test tools:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

WIMBA reads its settings — engine paths, data directory, logging — from the
nearest `wimba.yaml` walking up from the working directory. Put one at the top of
your working copy:

```bash
cp wimba.example.yaml wimba.yaml     # or: wimba config --init
wimba config                          # which file is in use, and what it says
```

A fresh install with no settings file anywhere gets one written for it at
`~/.config/wimba/config.yaml` on first use. See
[docs/SETTINGS.md](docs/SETTINGS.md).

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
flow behind the LHC, RoundChamber and Chimera examples.

```bash
wimba assemble <config.yaml>   # the assignment array: positions, beta, methods, collisions
wimba run      <config.yaml>   # + compute + machine total + Re/Im plots (--wake for the wake)
wimba plot     <name>_output/single_elements/total.csv --components ZLong,ZDipX
```

### `build` - element-driven (exactly what you list)

You describe the machine as **named groups of elements you list explicitly**. Each
element gets its impedance from a source (analytic resonator, imported table,
computed chamber) and is weighted by the optics **matched by name**. There is no
automatic beam pipe and no full-lattice sweep: the model is exactly the elements
you wrote down.

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

Both are driven from the GUI as well, which picks the right one from the config's
own dialect.

## Comparing several energies: projects

The same ring at injection and at extraction is two **scenarios** of one
**project**. A project owns the frequency and time grid, so its scenarios are
comparable by construction; each scenario carries its own machine and its own
beam. Scenarios are created only by duplicating an existing one — two curves are
worth plotting together only when they started from the same machine and differ in
something you chose.

    my_project/
      project.yaml                 name, grid, the scenario list
      injection_config.yaml        one config per scenario
      injection/output/            its results
      extraction_config.yaml
      extraction/output/

Results are filed under the scenario label and accumulate, so both appear in the
Results tree at once and the legend says which is which. Reopening a project loads
whatever has already been computed. See
**[docs/PROJECTS.md](docs/PROJECTS.md)**, and
`examples/Chimera_Project` for a working two-scenario project.

## Running

Most compute paths use **pytlwall**; install it into the same environment (it is
not on PyPI):

```bash
pip install -e <path to pytlwall>
```

Try the single-chamber verification first (quick, and confirms the numbers):

```bash
wimba run examples/RoundChamber/RoundChamber_config.yaml --wake
```

Self-check of what WIMBA can find:

```bash
wimba status     # which build of each engine will answer, and how it was found
```

The five bundled examples are described in **[docs/EXAMPLES.md](docs/EXAMPLES.md)**,
and each example folder has its own README (files provided, shell and GUI usage,
outputs). For tool configuration see [docs/SETTINGS.md](docs/SETTINGS.md) and
[docs/SETUP.md](docs/SETUP.md).

IW2D is optional, and installs into the same environment in the same way:

```bash
pip install cppyy
pip install -e <path to IW2D>
```

after its C++ libraries (GSL, GMP, MPFR, Arb) are available from the system or
from conda. On Debian and Ubuntu also set `IW2D_FLINT_ARB=1`, since Arb is
packaged there as `flint-arb`. WIMBA imports IW2D through its Python API and does
not run the compiled executables. See [docs/IW2D.md](docs/IW2D.md).

If you bring in a pytlwall chamber `.cfg`, read
**[docs/PYTLWALL_CFG.md](docs/PYTLWALL_CFG.md)** first: it says what WIMBA takes
from the file, why the frequency grid is rebuilt rather than reused, and how to
get a pure pytlwall result when you need one.

The `examples/LHC` study needs a MAD-X optics table that is too large to track
in the repository and is distributed separately; see
**[docs/DATA.md](docs/DATA.md)**. Every other example is self-contained.

### Tests

```bash
pip install -e ".[dev]"       # pytest (+ xwakes for the resonator cross-checks)
python -m pytest              # -q for the short summary
```

Tests that need pytlwall, PyQt6, xwakes or IW2D are skipped automatically when
those are not available, so a fresh clone runs the suite green with nothing but
the `[dev]` extra.

One case is worth knowing about, because it looks like a failure and is not one.
On Debian and Ubuntu the Arb library is packaged as `flint-arb`, while IW2D asks
for `arb`, so importing IW2D fails inside its C++ loader unless it is told
otherwise. The IW2D tests are then skipped with a message pointing here. To run
them instead:

```bash
export IW2D_FLINT_ARB=1       # put it in your shell profile
python -m pytest
```

Add it to the environment WIMBA runs in as well, not just the test shell — the
same import happens when a device uses `method: iw2d`. Full detail, including
the system libraries IW2D needs, is in [docs/IW2D.md](docs/IW2D.md).

## Graphical interface

The desktop GUI (PyQt6) drives the same engine — [docs/GUI.md](docs/GUI.md) is
the guided tour of it. Install the extra and launch it:

```bash
pip install -e ".[gui]"
python -m wimba.gui        # or: wimba-gui
```

The extras: `[dev]` adds the test tools, `[gui]` the desktop interface, and
`[spreadsheets]` the ability to import impedance tables from `.xlsx`/`.xls`
(plain text needs nothing extra). numpy, PyYAML and matplotlib come with the
package itself — `wimba run` and `wimba plot` write figures, so matplotlib is
not optional.

**A single machine.** `File → Load Machine` or `Open Config` opens one; the
panels show its elements (geometry, layers with the full pytlwall parameter set,
models, optics) and its **Beam** — particle and energy, with the derived
quantities alongside. `Calculate → Whole Machine` computes it, taking the
`build` or the `run` pipeline according to the config's dialect.

**A project.** `File → New Project` chooses where results go; the first machine
you load becomes its first scenario, and `Duplicate Scenario` adds the others.
The **Scenarios** panel lists them with their beam and provenance.

After a calculation the **Results** panel lists everything that was computed -
total, per-device and aggregated default pipe; wall, indirect space-charge and
wall+ISC components; wakes - grouped by scenario when there is more than one.
Double-click or drag quantities into the **Plot Workspace** (log/linear axes,
editable curve list, PNG/CSV export) or the **Results Table** (add/remove
columns, CSV export). `File → Open Results` reopens an existing output folder
without recomputing.

## Status

Implemented and tested: the core data model; the beam definition with its
conditioning guard; scenarios and projects, with per-scenario configs written back
from the panels; the optics builder from MAD-X; the assemble/run pipeline (beta
resolution, default resistive wall, per-geometry caching, collision detection,
machine total); the build pipeline; the compute engine shared by both workflows -
pytlwall (full layer parameter set, CIRCULAR/ELLIPTICAL/RECTANGULAR chambers,
impedance and native wake, indirect space charge kept as separate components),
analytic resonator (lumped, e.g. RF HOMs) and precalculated file import; the
settings file; the command-line interface (`assemble`, `run`, `plot`, `build`,
`show`, `config`, `setup`, `status`); and the graphical interface with the
results workspace (tree of computed quantities, plot/table with export,
scenarios side by side).

IW2D is driven through its Python API for circular chambers; see
**[docs/IW2D.md](docs/IW2D.md)**, which also covers the two conventions that
differ from pytlwall (IW2D has no perfect-conductor layer, and its impedance
already includes indirect space charge).

In progress: IW2D flat geometries, direct space charge as a separate
machine-wide output, and per-machine default-pipe presets.

## License

WIMBA is released under the GNU General Public License v3 (see [LICENSE](LICENSE)).
