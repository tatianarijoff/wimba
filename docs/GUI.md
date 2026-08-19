[//]: # (WIMBA — Wake & Impedance Model Builder for Accelerators)

# The graphical interface

The desktop GUI drives exactly the same engine as the command line. Nothing it
computes is computed differently, and nothing it writes is a format of its own:
a config saved from the panels is the same YAML `wimba run` reads. If you know
one, you know the other.

This page is the map. It says what each panel is for, which menu entry does
what, and where the detailed page for each workflow lives. The three workflows
themselves are documented separately, because each is long enough to deserve
its own page:

| you want to | read |
|---|---|
| compute one chamber, no machine | [COMPONENT.md](COMPONENT.md) |
| compute a whole machine | [ASSEMBLE_AND_RUN.md](ASSEMBLE_AND_RUN.md), [BUILD.md](BUILD.md) |
| compare the same machine at several energies | [PROJECTS.md](PROJECTS.md) |

## Starting it

```bash
pip install -e ".[gui]"
python -m wimba.gui        # or: wimba-gui
```

The `[gui]` extra brings PyQt6 and ruamel.yaml. On first run WIMBA creates
`~/.config/wimba/config.yaml` if no settings file exists anywhere; see
[SETTINGS.md](SETTINGS.md) for what goes in it and how a `wimba.yaml` next to
your work overrides it.

## The window

Docks can be moved, stacked and closed from the **View** menu; the layout below
is the default.

**Scenarios** (top left) — only meaningful inside a project. Lists the
scenarios with their beam and their provenance, and carries Duplicate, Rename
and Remove. The line underneath states the shared grid, which is the thing that
makes two scenarios comparable.

**Machine Explorer** (left) — the tree of what is loaded: groups, then
elements. The default resistive wall appears as a single entry with the number
of lattice segments it stands for, because it is one rule and not one element
per segment.

**Optics / Beam** (bottom left, tabbed) — the optics table lists the elements
with their position, length and beta functions, and reports how many of them
have both. The Beam tab defines the particle and the energy; see
[The beam](#the-beam) below.

**Centre** — the workspace. `Plot Workspace` and `Results Table` are always
there; opening an element adds a tab for it, with `Geometry`, `Layers`,
`Beam & Optics` and `Models`, and the two Calculate buttons at the bottom.
`Materials ▸ Show Materials` opens a `Materials` tab here too — see
[Materials](#materials).

In the `Geometry` tab the aperture follows the shape: one radius for a
CIRCULAR chamber, a horizontal and a vertical semi-axis for an ELLIPTICAL or
RECTANGULAR one, both in metres. The fields the shape does not use are not
shown, so a radius cannot travel with a rectangle that ignores it.

In the `Layers` tab each row is a layer, inside → out. The type is chosen from
a list: `CW` followed by a material name, `CW (custom)` when you want to type
the numbers yourself, or `V` and `PEC`, whose parameters are closed because
pytlwall computes them from a formula and reads none of them. Thickness and k
may be set to infinity with the box beside the field; every other value is a
number. The outermost layer is the boundary — marked automatically, with
infinite thickness, because it is the half-space outside the wall.

**Results** (right) — everything a calculation produced: the machine total,
each device, the aggregated default pipe, and for chambers the wall, the
indirect space-charge and the wall+ISC components separately. Impedance and
wake. Inside a project the entries carry their scenario label. Double-click or
drag into the Plot Workspace or the Results Table.

**Inspector** (bottom right) — the selected element's resolved values: its
position, length, betas, material, how many layers it has. This is where you
check what WIMBA actually decided, as opposed to what the config asked for.

**Jobs / Console / Problems / Output Browser** (bottom) — Jobs shows
calculations with live status, Console the log, Problems the assembly warnings
(see [What Problems tells you](#what-problems-tells-you)), Output Browser the
files on disk.

## The File menu

| entry | what it does |
|---|---|
| **Load Machine** | opens a machine file — the `groups:` dialect, the elements you listed |
| **Open Config** | opens an assembly config — the `devices:`/`default_pipe:` dialect, rules WIMBA executes |
| **New Project** | asks where results go; the first machine you load becomes scenario one |
| **Open Project** | opens an existing `project.yaml` and reloads every scenario that already has output |
| **Save Project** / **Save Project As** | writes `project.yaml` and each scenario's config |
| **Close Project** | saves, then clears the panels; files are untouched |
| **Open Results** | reopens an output folder without recomputing anything |

### Load Machine or Open Config?

This is the distinction worth getting right first, and it is not about the file
extension — both are YAML. It is about what the file contains.

A **machine file** lists elements. You wrote out what is in the ring, one entry
at a time, under `groups:`. WIMBA computes what you listed and nothing else:
there is no automatic beam pipe. `examples/SubLHC` is one.

An **assembly config** states rules. `devices:` says how to find the devices —
often from an external file that expands into many elements — and
`default_pipe:` says that every lattice row not claimed by a device becomes a
segment of resistive wall. WIMBA resolves those rules against the optics and
tells you what came out. `examples/LHC` is one.

The two menu entries are not interchangeable and WIMBA will say so: pointing
*Load Machine* at an assembly config gives an explicit error naming *Open
Config*. If you ever wonder which you have, look for the keys: `groups:` means
machine, `devices:` or `default_pipe:` means config.

One consequence catches people out. Opening a config still fills the Machine
Explorer with groups — but those groups are *derived* from the resolved
assignment array, not read from the file, and all the default-pipe rows are
collapsed into one synthetic entry. That entry has no position, no length and
no beta, because it stands for thousands of rows and there is no single value
to show. An almost-empty Optics table on a config whose only content is a
default pipe is the interface being accurate, not failing.

## The beam

Gamma is the canonical quantity. You may enter the energy, the kinetic energy,
the momentum or beta instead and WIMBA derives the rest, showing the derived
values live underneath.

An input is refused when the conversion from it is ill-conditioned *and* you
wrote too few digits to pin gamma down — `beta = 0.99999` is refused with a
message telling you to enter gamma, while `beta = 0.9` is accepted, because for
a non-relativistic machine beta is the natural variable. [PROJECTS.md](PROJECTS.md#why-an-input-is-sometimes-refused)
explains the rule.

There is no default energy. A chamber calculation without a beam raises rather
than quietly assuming one.

An element tab has a `Beam & Optics` tab of its own. For a component that
belongs to no machine — built with `Component ▸ New Component`, or loaded from
a pytlwall or IW2D config — the beam is **editable** there: it has no ring to
inherit from, and without a beam it cannot be computed at all. For an element
that belongs to a machine the same panel is **read-only**: inside a ring there
is one beam and it belongs to the ring. The twiss betas are editable either
way, because they belong to the element.

Which value wins when a machine and an element each state their own is set out
in [BEAM_AND_OPTICS.md](BEAM_AND_OPTICS.md).

## Calculating

`Calculate → Whole Machine` runs the pipeline the loaded file's dialect calls
for: `build` for a machine file, `assemble`/`run` for an assembly config. You
do not choose, and the Console says which one it took.

Inside a project the results go to `<scenario slug>/output` without asking, and
the scenario is stamped with the time it was computed.

The buttons at the bottom of an element tab — `Calculate element` and
`Calculate wake` — compute that element alone.

## Materials

`Materials ▸ Show Materials` opens a table of every named material a `CW` layer
can be filled from: conductivity, permittivity, relaxation, permeability and
roughness, one column each. Choosing a material in a layer writes its **numbers**
into that layer, never its name, so a config you send elsewhere carries the
values and computes the same for someone who has never seen your list.

Your own materials are at the top and are editable; the ones WIMBA ships with
are below and are not. To change one of those, add a row with the same name: it
overrides the catalogue entry for you and for nobody else. Values shown in grey
italics were not written down for that material — they are the defaults the
calculation uses, shown so that no column reads as missing data.

`Materials ▸ Add Material` starts a row in the same table. It is a **permanent**
choice: `Save` writes it to `custom_materials.yaml` — see
`custom_materials.example.yaml` at the top of the repository — and it is offered
from then on. For a conductivity you need once, add nothing: pick `CW (custom)`
in the layer and type the numbers there.

A study can also carry its own names, in the config's `materials:` block; those
win over the catalogue for that study. That is the right place for a name that
has to travel with a file.

## What Problems tells you

Two kinds of entry, and both are worth reading before trusting a number.

**Collisions** are two devices claiming the same lattice position.

**Warnings** currently cover one case: a device WIMBA could not locate. If a
device has no `position:`, no explicit `beta:`, and a name that is not an
element of the twiss, WIMBA falls back to beta = 1. For a device whose data is
already a ring total that is correct — there is no single place where all 2220
BPMs sit, and such a device carries `weighted: true`. For a device with
`weighted: false` it means the local optics was silently replaced by 1: nothing
fails, the result stays plausible, and only this warning tells you.

## Editing and saving

Panel edits are written back into the scenario's own config, and the write is a
patch rather than a fresh dump: WIMBA changes the beam, the optics file,
element removals and the values you actually edited, and leaves every other
line of the file exactly as you wrote it — **comments included**. Your reasoning
about why a number is what it is survives a Save.

What it will not do is invent the parts the interface cannot see. A pytlwall
element loaded from a machine file arrives with its layers still inside the
provider, and an assembly config's rules have already been resolved into an
assignment array; neither can be reconstructed from what the panels hold, so
neither is rewritten. If you need to change a rule, edit the config in a text
editor.

## See also

- [SETUP.md](SETUP.md) — installing WIMBA and the engines
- [SETTINGS.md](SETTINGS.md) — `wimba.yaml`, engine paths, `data_dir`, logging
- [CONFIG.md](CONFIG.md) — the machine config format, key by key
- [BEAM_AND_OPTICS.md](BEAM_AND_OPTICS.md) — which gamma and which betas a
  device is computed with, and how to check afterwards
- [DATA_MODEL.md](DATA_MODEL.md) — ImpedanceTerm, Element, ElementGroup, Machine
- [EXAMPLES.md](EXAMPLES.md) — what is in `examples/` and what each one shows
