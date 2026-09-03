<p align="center"><img src="../img/wimba_logo_small.png" alt="WIMBA" width="190"></p>

# Computing one component in the WIMBA GUI (pytlwall)

You have a component with a known geometry — a chamber, a kicker, a collimator
jaw — and you want its impedances and wakes. This is the **Component bench**:
no machine, no optics files, just your component and the engines.

## Prerequisites

```bash
pip install -e ".[gui]"                 # WIMBA + PyQt6
pip install -e <path to pytlwall>      # pytlwall (the wall engine)
python -m wimba.gui                    # launch
```

## Step 1 — define the component

Two ways, from the **Component** menu:

- **New Component…** — give it a name; a panel opens with a default circular
  chamber and a single layer of the default material. The tab appears in the
  centre of the window, not in the Machine Explorer on the left: a component
  built here belongs to no machine.

  In the **Geometry** tab pick the shape and give the aperture. The fields
  follow the shape: a radius for CIRCULAR, a horizontal and a vertical
  semi-axis for ELLIPTICAL and RECTANGULAR, all in metres. Length is in metres
  too.

  In the **Layers** tab each row is a layer, inside → out. Choose the type from
  the list — `CW` followed by a material name, `CW (custom)` to type the
  numbers yourself, or `V` and `PEC`, whose parameters are closed because
  pytlwall computes those from a formula and reads none of them. Thickness and
  k take infinity through the box beside the field; everything else is a
  number. The outermost layer is the boundary automatically, with infinite
  thickness.

  In the **Beam & Optics** tab state the energy. There is no default: a
  component with no beam will not compute, and the config it saves says so.
  The twiss betas sit beside it and are 1 unless you say otherwise.

  In the **Models** tab pick how it is computed. `pytlwall` and `IW2D` solve
  the wall you just described. `resonator` does not: it replaces the wall with
  a list of resonances, so choosing it opens a modes table and closes Geometry
  and Layers — the values there are kept, not discarded, so you can switch
  back or compare against them. One row is one resonance of one component
  (Rs, Q, f_r); rows sum. A mode missing one of its three numbers is refused
  by name rather than failing inside the engine.
- **Load pytlwall Config…** — a pytlwall chamber `.cfg`, in the format of
  pytlwall's own examples. WIMBA reads geometry, layers, boundary, beta, gamma
  and the frequency grid from the file. The grid is rebuilt from
  `[frequency_info]`, so it covers the same range as pytlwall's own but does
  not sample the same points; see **[PYTLWALL_CFG.md](PYTLWALL_CFG.md)** before
  comparing the two codes. This entry takes a pytlwall `.cfg` — a WIMBA config
  is opened with **File → Open Config** instead.
- **Load IW2D Config…** — an IW2D round-chamber input file, the tab-separated
  format of IW2D's own `examples/input_files/`. WIMBA converts the units (mm,
  ps, MHz, and resistivity to conductivity) and opens it as a component, with
  IW2D preselected as the method. See `examples/RoundChamber_IW2D_native/`.

  Two things it refuses rather than approximating: a **flat**-chamber input,
  which carries a half gap and two layer stacks a WIMBA element cannot hold,
  and **Yokoya factors** other than the circular set `1 1 1 0 0`, which
  describe another shape through an equivalent round one. Anything it keeps but
  cannot reproduce exactly — a scan mode, added frequencies — is written to the
  console rather than dropped in silence.

  Note that WIMBA does not compute through these files: it drives IW2D's Python
  API. The format is how an IW2D case is written down and passed around.

The **Models** tab shows how the component will be computed: one base method
for the impedance (all components at once) and a Wakefield line that *declares*
how the wake will be obtained.

## Step 2 — compute

Still in the **Component** menu:

- **Calculate Component** — computes it the way the Models tab says. This is
  the ordinary route: it follows the method you chose, whether that is a wall
  or a resonator.
- **Calculate with pytlwall** — all impedance components (`ZLong`, `ZDipX`,
  `ZDipY`, `ZQuadX`, `ZQuadY`, plus the indirect-space-charge terms as separate
  quantities and the derived `Z*+ISC` sums);
- **Calculate with IW2D** — the same wall through the other engine. These two
  name an engine rather than following the tab, which is what a comparison
  wants; when they disagree with the chosen method the Console says so, and the
  result carries the name of the engine that produced it.
- **Calculate Wake (pytlwall)** — the native wake (`WLong`, `WDipX`, `WDipY`),
  computed from the geometry: it does not need a previous impedance run.

Runs are asynchronous: watch **Jobs** and **Console**. Every run also writes
the exact pytlwall input it used under `<output>/pytlwall_inputs/` — open it
whenever you want to see or reproduce what was fed to the engine.

## Step 3 — read the results

Each run **adds** a labelled source to the **Results** tree —
`NAME[pytlwall]`, and later `NAME[precalculated: file]` — so calculations
accumulate for comparison. Double-click or drag any quantity into the **Plot
Workspace** (log/linear axes, curve list, PNG/CSV export) or the **Results
Table** (CSV export). **Clear Component Results** empties the bench.

## Step 4 — keep it

**Component → Save Component As…** writes the component wherever you choose —
your own working folder, not the WIMBA checkout; the file dialogs reopen where
you last saved.

What is written is a WIMBA config holding a single device: geometry, layers,
beam and grid — or, for a resonator, its modes in place of the geometry and the
layers. Not a pytlwall `.cfg`, because the same WIMBA file also
describes an IW2D or an imported component, and a chamber dump cannot. The
layer carries the numbers of its material and not the name, so the file
computes the same for someone who has never seen your material list.

That file is a real input, not an export: reopen it with **File → Open Config**,
or compute it with no interface at all.

```bash
wimba run RoundChamber_component.yaml
```

A precalculated component is refused here, with the reason: what defines it is
its data file and its import map, which is already a file in its own right.

## Comparing a wake

The same table takes wake components — `WLong`, `WDipX`, `WDipY`, `WQuadX`,
`WQuadY`, or `All wake`. Choosing one makes the calculation compute the wake as
well: without a time grid a wake comparison would come out empty, so asking for
one is taken as asking for the wake, and the grid that decision implies is
written to the console.

Where the wake comes from depends on the method, and the row says so: pytlwall
solves it natively, a precalculated entry reads it from the file, and IW2D's
impedance is transformed by WIMBA — its Python package has no wake solver.
Comparing pytlwall against IW2D on a wake therefore compares a solver with a
Fourier transform, which is worth doing and worth knowing.

## Step 5 (optional) — compare with imported data

**Component → Load Precalculated…** and pick your data file (e.g. a CST
export). For a plain text file a dialog opens with a preview: set the comment
prefix, rows to skip, separator, the frequency unit (GHz exports are common!),
the value format (Re/Im columns or one complex column) and the column numbers —
**columns are numbered from 1**. WIMBA writes a reusable `.map.yaml` descriptor
next to the data and computes; the imported curve appears next to the pytlwall
one. See [PRECALCULATED.md](PRECALCULATED.md) for the full descriptor
reference.

## Troubleshooting

- *Unknown material*: give the layer an explicit `sigma`, or use a known
  material name. Unknown names are an error, never a silent default. The known
  names are the ones listed under **Materials → Show Materials**; see
  [GUI.md](GUI.md#materials).
- *does not say at which energy to compute*: the component has no beam. Set one
  in its **Beam & Optics** tab, or add a `beam:` block to the config.
- *pytlwall is required…*: install it into the same environment (see
  [SETUP.md](SETUP.md)).
- The persistent log (always at debug level) lives at
  `~/.local/state/wimba/wimba.log`; the Console level is set in
  **View → Log Level**.
