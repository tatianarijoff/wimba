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
- **Load pytlwall Config…** — a pytlwall chamber `.cfg`, in the format of
  pytlwall's own examples. WIMBA reads geometry, layers, boundary, beta, gamma
  and the frequency grid from the file. The grid is rebuilt from
  `[frequency_info]`, so it covers the same range as pytlwall's own but does
  not sample the same points; see **[PYTLWALL_CFG.md](PYTLWALL_CFG.md)** before
  comparing the two codes. This entry takes a pytlwall `.cfg` — a WIMBA config
  is opened with **File → Open Config** instead.
- **Load IW2D Config…** — the same, for an IW2D input.

The **Models** tab shows how the component will be computed: one base method
for the impedance (all components at once) and a Wakefield line that *declares*
how the wake will be obtained.

## Step 2 — compute

Still in the **Component** menu:

- **Calculate with pytlwall** — all impedance components (`ZLong`, `ZDipX`,
  `ZDipY`, `ZQuadX`, `ZQuadY`, plus the indirect-space-charge terms as separate
  quantities and the derived `Z*+ISC` sums);
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
beam and grid. Not a pytlwall `.cfg`, because the same WIMBA file also
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
