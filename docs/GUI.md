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
have both. Above it sits the **average beta**, because every transverse weight
is β/β̄ — see [The average beta](#the-average-beta). The Beam tab defines the
particle and the energy; see [The beam](#the-beam) below.

**Centre** — the workspace. `Plot Workspace` and `Results Table` are always
there; opening an element adds a tab for it, with `Geometry`, `Layers`,
`Beam & Optics` and `Models`, and the two Calculate buttons at the bottom.
`Materials ▸ Show Materials` opens a `Materials` tab here too — see
[Materials](#materials).

In the `Geometry` tab the aperture follows the shape: one radius for a
CIRCULAR chamber, a horizontal and a vertical semi-axis for an ELLIPTICAL or
RECTANGULAR one, both in metres. The fields the shape does not use are not
shown, so a radius cannot travel with a rectangle that ignores it.

Only imported data can arrive already weighted, so `precalculated (weighted)`
is the one weighted method offered: for pytlwall, IW2D and the resonator WIMBA
does the weighting itself, and claiming it was done already would do it twice.

In the `Layers` tab each row is a layer, inside → out. The type is chosen from
a list: `CW` followed by a material name, `CW (custom)` when you want to type
the numbers yourself, or `V` and `PEC`, whose parameters are closed because
pytlwall computes them from a formula and reads none of them. Thickness and k
may be set to infinity with the box beside the field; every other value is a
number. The outermost layer is the boundary — marked automatically, with
infinite thickness, because it is the half-space outside the wall.

The `Models` tab is where the method is chosen, and the tab follows the choice.
The four methods are not four ways of computing one element: they are four
kinds of element. pytlwall and IW2D solve a **wall**, so they read the geometry
and the layers. `precalculated` reads a **file**. A resonator is a **mode
spectrum** and reads neither — so choosing `resonator` opens a table of modes
and closes `Geometry` and `Layers`, which nothing would read. Closed, not
cleared: the wall stays as you left it, and switching back finds it there.

Each row of the modes table is one resonance of one component: the component
(`ZLong`, `ZDipX`, `ZDipY`, `ZQuadX`, `ZQuadY`), its shunt impedance Rs — an
impedance longitudinally, an impedance per metre transversally — its quality
factor and its resonant frequency. Rows sum, so a mode that speaks in several
planes is written as several rows; a config that carries it as one mode with
several triples comes back split the same way. Rs is the shunt impedance of the
whole object, not a value per metre: the length of a resonator device says how
much lattice it covers, and does not scale its impedance. The transverse
weighting applies as it does everywhere else, β/β̄.

The modes of an element that belongs to a machine are shown and not edited, for
the same reason the beam is: they come from the config the machine was loaded
from. A resonator of your own is built in the Component bench.

**Results** (right) — everything a calculation produced: the machine total,
each device, the aggregated default pipe, and for chambers the wall, the
indirect space-charge and the wall+ISC components separately. Impedance and
wake. Inside a project the entries carry their scenario label.

Drag an entry into the Plot Workspace or the Results Table, or double-click it:
a double click goes to the Results Table when that tab is the one in front, and
to the Plot Workspace otherwise.

**Inspector** (bottom right) — the resolved values of whatever is selected in
the Machine Explorer, on a single click.

For an **element**: its category, position, length, betas, how many layers it
has and which quantities are switched on. This is what WIMBA actually decided,
as opposed to what the config asked for.

For a **group**, or for the machine itself, the same question answered by
aggregation, since a group is nothing but its members: how many elements, where
they start and end along the ring, how much length they model between them,
what they are made of by method, how many of them have both betas and the range
those betas span, and which quantities are on — marked *mixed* when the elements
do not agree, which is how a group quietly produces an incomplete total. A last
line names anything worth a second look: an element with no quantity switched
on, one computed at beta = 1, one with no length. That is the Problems panel's
question asked before the calculation rather than after it.

The default pipe is its own group, and gets its own reading: what chamber it
is, which engine computes it, its layers and its quantities — and a line saying
why the geometric rows are empty. It stands for every lattice row no device
claimed, so it has no single position, length or beta, and the number of
segments it collects is in the group's name. In the machine's own summary it is
counted apart from the elements for the same reason. A weighted source is not
counted as missing its optics either — its data already includes them.

The Inspector is also the only readout for a group or for the machine root,
since double-clicking opens a tab for an element and does nothing for the rest.

**Jobs / Console / Problems** (bottom, tabbed) — three panels answering three
different questions.

*Console* is what is happening now: the backend commands, the files read, the
warnings and the errors. It is **cleared at the start of every calculation**, so
it always describes the current one.

*Jobs* is what you have launched in this session — one line per calculation,
updated to `done` with the number of quantities computed, or to `FAILED`. It is
one calculation at a time, not a queue; it exists because the Console is wiped
each run and this list is what survives.

*Problems* is what not to trust: collisions and optics warnings, written after a
calculation and raised automatically when there is something in it. See
[What Problems tells you](#what-problems-tells-you).

## The menus

### File

| entry | what it does |
|---|---|
| **Load Machine** | opens a machine file — the `groups:` dialect, the elements you listed |
| **New Machine** | starts an empty machine, to be filled from the **Machine** menu |
| **Open Config** | opens an assembly config — the `devices:`/`default_pipe:` dialect, rules WIMBA executes |
| **Open Results** | reopens an output folder without recomputing anything |
| **Close Machine** | clears the machine and its panels |
| **New Project** | asks where results go; the first machine you load becomes scenario one |
| **Open Project** | opens an existing `project.yaml` and reloads every scenario that already has output |
| **Save Project** / **Save Project As** | writes `project.yaml` and each scenario's config |
| **Close Project** | saves, then clears the panels; files are untouched |
| **Duplicate / Rename / Remove Scenario** | the same three actions as the buttons in the Scenarios dock |
| **Export Results** | writes everything the Results tree holds, as CSV or as tab-separated TXT |

### The others

| menu | what is in it |
|---|---|
| **View** | show or hide each dock, jump to the Plot Workspace or the Results Table, switch theme (dark / light), set the log level, and save, reload or reset the window layout |
| **Machine** | Add Group, Add Element, and Rename, Duplicate or Delete what is selected — this is how a machine is built from nothing |
| **Component** | the component bench: see [COMPONENT.md](COMPONENT.md) |
| **Materials** | Add, Show and Delete a material: see [Materials](#materials) |
| **Optics** | Load Optics — the same button as the one in the Optics dock |
| **Calculate** | see [Calculating](#calculating) |
| **Results** | Export Results, as in the File menu |
| **Help** | see [The documentation, inside the window](#the-documentation-inside-the-window) |

Two entries are placeholders and say so when used: `Calculate ▸ Calculate
Selected Group` and `Optics ▸ Clear Optics`. The four comparison-basket entries
of the **Results** menu are placeholders too — build a comparison by dragging
into the Plot Workspace instead.

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

## The average beta

Every transverse weight is the ratio β/β̄: the element's own beta over the
machine's average. That is what makes the weight dimensionless, so a transverse
total is an impedance rather than an impedance times a length, and an element
sitting at the average optics contributes with weight one. The longitudinal
term is never weighted.

The box above the optics table shows two things. **WIMBA's own** is derived and
not editable: the length-weighted average over the twiss rows when an optics
file is loaded, otherwise the same average over the modelled elements' own
betas, otherwise 1. The panel says which of the three it is, because an average
estimated from the elements is usually high — devices sit where beta is large,
and a model's elements are not a sample of the ring.

**Yours** is the pair of fields underneath: β̄x and β̄y as you obtain them from
the tunes in smooth approximation, R/Q. They take positive lengths only —
letters, signs and zero are refused as you type. State both or neither: the two
planes have different tunes and so different averages. When they are filled they
win; clear them and the machine's own average takes over again. Either way the
Console says which average the next calculation will divide by. Saving writes
the pair to the config as `smooth_beta:`, and clearing them removes that key
rather than writing a 1.

Inside a project this belongs to the scenario, since the optics changes with the
energy.

`Calculate ▸ Whole Machine (not weighted)` computes the same elements with every
transverse weight set to one. It is a second result, labelled apart in the tree
so the two can be plotted together — not a replacement. One caution, and
Problems says it too: a source that carries its own weighting keeps it whatever
you ask, so an unweighted run over a model containing one adds weighted and
unweighted terms, and its machine total is not a quantity. Read it per element.

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
`Calculate wake` — compute that element alone; `Calculate ▸ Calculate Selected
Element` (`F5`), `… Wake` (`Shift+F5`) and `… Comparisons Only` (`Ctrl+F5`) do
the same from the tree.

At the top of the **Calculate** menu sits a checkbox, *Fill unmodelled lattice
with resistive wall*, ticked by default. It is the `default_pipe` rule, and
turning it off changes the result: only the named devices are computed, and the
thousands of lattice rows that would otherwise become resistive wall are left
out. It applies to an assembly config; a machine file has no lattice to fill.

The Beam panel wins over what the file says, on both pipelines, and the Console
prints a warning when the two disagree. The file itself is not rewritten: the
override applies to that run only.

## Reading the results

The **Plot Workspace** holds any number of curves. Each one can be switched off
without removing it, the x axis is logarithmic or linear and the y axis
logarithmic in `|y|`, symlog or linear — symlog is the one to reach for when a
quantity changes sign. `Export PNG` writes the figure, `Export CSV` writes the
curves that are on.

The **Results Table** takes the same drops and shows the numbers column by
column, and exports them as CSV.

Whole sets go out through `File ▸ Export Results` (or the same entry in the
**Results** menu), as CSV or as tab-separated TXT: that writes what the Results
tree holds, not what you happened to drag into a panel.

## The documentation inside the window

`Help ▸ Documentation` (`F1`) opens these pages in a searchable browser without
leaving the application; `Help ▸ Search Help for…` (`Shift+F1`) opens it on a
query. The search knows that the words you would type are not always the words
the documents use — asking for *excel* finds the pages about spreadsheets, *PEC*
finds the passage on perfect conductors — and a hit in a heading outranks one in
a paragraph. The index is built from the files on disk each time the browser
opens, so an edited page is current with no rebuild step.

`Open in web browser` on the same window generates the HTML documentation, if it
is not there already, and opens the page outside the application.

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

The panel is written when a calculation finishes, not when a file is loaded, and
it comes to the front by itself when there is something in it. Two kinds of
entry, and both are worth reading before trusting a number.

**Collisions** are two devices claiming the same lattice position.

**Warnings** currently cover one case: a device WIMBA could not locate. If a
device has no `position:`, no explicit `beta:`, and a name that is not an
element of the twiss, WIMBA falls back to beta = 1. For a device whose data is
already a ring total that is correct — there is no single place where all 2220
BPMs sit, and such a device carries `weighted: true`. For a device with
`weighted: false` it means the local optics was silently replaced by 1: nothing
fails, the result stays plausible, and only this warning tells you.

## Editing and saving

**WIMBA does not write your config unless you ask it to.** Opening a project,
switching between scenarios, loading an optics file, running a calculation —
none of these touches the YAML on disk. Only `File ▸ Save Project` and
`File ▸ Save Project As` do. Closing a project with unsaved panel edits asks
first, and takes no for an answer. (`project.yaml` is different: it is WIMBA's
own bookkeeping — which scenarios exist, when each was last computed — and is
kept current on its own.)

When you do save, the write is a patch rather than a fresh dump: WIMBA changes
the beam, the optics file, element removals and the values you actually edited,
and leaves every other line of the file exactly as you wrote it — **comments
included**. Your reasoning about why a number is what it is survives a Save.

The beam is written the way you stated it — the particle, the mode, and that one
value. The quantities derived from it are not written: three keys that have to
agree, where one would do, are three keys that can disagree after the first hand
edit. And a config that already states the right beam is not rewritten at all,
so `8e+10` stays `8e+10`.

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
