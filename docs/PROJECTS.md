<p align="center"><img src="../img/wimba_logo_small.png" alt="WIMBA" width="190"></p>

# Projects and scenarios: comparing the same machine at several energies

A machine is rarely interesting at one energy only. The LHC at injection and at
flat top, the PS at 2 GeV and at 26 GeV/c, a decelerator at both ends of its
cycle: same ring, different beam, and the question is what changes. A **project**
is where those cases live together.

    Project        one output folder, one frequency and time grid
      Scenario     a machine + the beam it is computed with
        Machine    groups of elements, or the rules that place them

Scenario sits above Machine and below Project. That is the whole idea; the rest
of this page is what follows from it.

## Why the grid belongs to the project

Two impedance curves can only be compared if they were sampled at the same
frequencies. So the grid is a property of the **project**, not of a scenario: it
is defined once and every scenario inherits it. Nothing has to remember to keep
them in step, because there is only one.

The same reasoning drives the other rule.

## Scenarios are created only by duplication

The first scenario appears when you load a machine or open a config into a new
project. Every one after that is a **copy of an existing scenario**, made with
*File → Duplicate Scenario*.

This is deliberate, not a missing feature. Two scenarios are worth plotting
together only when they started from the same machine and differ in something
you chose. Duplication is what guarantees it; loading a second, unrelated machine
into a project is refused, with the two ways forward spelled out.

The copy records where it came from (`derived_from`), so a comparison can always
say what a curve is a variation *of*.

## What may differ between scenarios

| may differ | how |
|---|---|
| the beam | the Beam panel: particle, and gamma / beta / energy / kinetic energy / momentum |
| the optics | *Load Optics…* on the duplicate |
| which elements are present | delete an element in the Machine Explorer |
| element parameters | edit them in the element panel |
| the grid | **no** — it is the project's, and shared |

## On disk

    my_project/
      project.yaml                 name, grid, the scenario list
      injection_config.yaml        one config per scenario, frozen
      injection/output/            results
      injection/img/
      flat_top_config.yaml
      flat_top/output/
      flat_top/img/

`project.yaml` records what the project is, not what it computed:

```yaml
name: CHIMERA (invented ring)
grid:
  frequency: {min: 10000.0, max: 10000000000.0, n: 200, log: true}
  time: {min: 0.0, max: 5.0e-08, n: 200}
scenarios:
- label: injection 1.2 GeV
  slug: injection
  config: injection_config.yaml
  beam: {particle: proton, mode: kinetic, kinetic: 1200000000.0,
         gamma: 2.2789, beta: 0.898585}
- label: extraction 20 GeV/c
  slug: extraction
  config: extraction_config.yaml
  beam: {particle: proton, mode: momentum, momentum: 20000000000.0,
         gamma: 21.3392, beta: 0.998901}
  derived_from: injection 1.2 GeV
```

The **label** is free text — it is what appears in the plot legend. The **slug**
is the folder name derived from it. Renaming a scenario moves both its config and
its output folder, and rewrites the `derived_from` of anything descended from it.

### The config is copied, the data is not

When a config is adopted into a project it is **frozen**: copied into the project
folder, with its relative file references (`optics`, `file`, `map`, `files`)
rewritten to absolute paths. The scenario then owns its config and can be edited
without touching the original; the large shared data — MAD-X tables, imported
`.dat` files — stays where it is and is pointed at.

References that do not resolve are left exactly as written, so a config using
absolute paths, or one whose data is missing, is copied unharmed and fails later
with its own error.

## The beam

Every scenario states its beam. There is no default: a calculation with no beam
stops with an error rather than computing at some assumed energy.

```yaml
beam:
  particle: proton        # proton | antiproton | electron | positron | lead208
  mode: momentum          # gamma | beta | energy | kinetic | momentum
  momentum: 2.0e+10       # eV/c   (energies in eV; gamma and beta dimensionless)
```

Only one number is free: the other four are derived. A bare top-level `gamma:`
is still read, as a proton beam at that gamma.

### Why an input is sometimes refused

Gamma and beta are the same degree of freedom, but not equally usable everywhere.
Writing `beta: 0.99999` gives gamma = 224 ± 67 — the number does not pin down
what would be derived from it. Writing `gamma: 1.0001` gives beta to 25%.

WIMBA refuses an input when **both** are true: the conversion is ill-conditioned
(amplification greater than 10³) **and** the digits written are too few to
survive it. So `beta: 0.9` is accepted — gamma = 2.294157 follows from it exactly
— while `beta: 0.99999` is refused with a message naming the variable to use
instead.

In practice: beta is usable up to gamma ≈ 30, gamma from gamma ≈ 1.0005 upwards,
and the two ranges overlap widely. At LHC energies no number of digits rescues
beta: pinning gamma to 10⁻⁶ at gamma = 2·10⁵ would need beta to 10⁻¹⁷, past what
a double holds.

Energy, kinetic energy and momentum are often the most natural: they are how a
machine quotes its own working points.

## Working with a project in the GUI

| menu | what it does |
|---|---|
| *File → New Project…* | choose the folder; name it |
| *File → Open Project…* | reopen, with the results of every computed scenario already loaded |
| *File → Close Project* | saves first, then clears the panels; files untouched |
| *File → Save Project* | writes `project.yaml` and each scenario's config |
| *File → Duplicate Scenario…* | the only way to add a scenario |
| *File → Rename / Remove Scenario* | folder and config follow the rename |

The **Scenarios** panel lists them with their beam and provenance; the **Beam**
panel (tabbed with Optics) edits the current one.

*Calculate → Whole Machine* needs no file dialog inside a project: it uses the
current scenario's config, routes to the `run` or the `build` pipeline according
to the dialect, and writes into `<slug>/output/`.

### Reading two scenarios on one plot

Results are filed under the scenario label, so they accumulate instead of
replacing each other. The Results tree shows one branch per scenario and the
legend reads

    injection 1.2 GeV · Total ZLong Re
    extraction 20 GeV/c · Total ZLong Re

Recomputing a scenario replaces its own curves and leaves the others alone.
Reopening a project loads whatever is already on disk, so comparing three
scenarios does not mean computing three scenarios again.

## What actually changes between two energies

Worth knowing before wondering whether something is broken: **only some sources
depend on the beam**. A resistive-wall chamber (pytlwall, IW2D) does; an analytic
resonator does not, and neither does imported tabulated data. Two scenarios that
differ only in beam therefore give identical curves for those elements — correct
physics, not a bug.

Where the difference shows most is indirect space charge, which scales as 1/γ².
Between a decelerator's injection and extraction that factor can move by more
than an order of magnitude, and the ISC columns separate while the wall terms
barely move.

## Saving edits back

What you change in the panels is written back into the scenario's config when the
project is saved, when you switch scenario, and when you duplicate.

The config is **patched**, never regenerated from the panels. The view-model is a
lossy picture of the file — a chamber loaded from a machine file arrives without
its layers, and an assembly config's rules have already been resolved into an
assignment array — so a full rewrite would quietly delete what it could not see.
Only the beam, the optics file, element removals and values you actually edited
are written; everything else in the file is left exactly as you wrote it.

## See also

- [CONFIG.md](CONFIG.md) — the machine config a scenario points at
- [SETTINGS.md](SETTINGS.md) — WIMBA's own settings file, a different thing
- [ASSEMBLE_AND_RUN.md](ASSEMBLE_AND_RUN.md) — the lattice-driven flow
- [EXAMPLES.md](EXAMPLES.md) — `examples/Chimera_Project` is a two-scenario project
