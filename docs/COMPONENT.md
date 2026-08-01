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
  chamber. Set your geometry in the **Geometry** tab (shape CIRCULAR /
  ELLIPTICAL / RECTANGULAR, radius or half-axes in metres) and the wall in the
  **Layers** tab: one row per layer, inside → out, with the full
  electromagnetic parameter set (thickness, sigma or a known material name,
  muinf_Hz, k_Hz, epsr, tau, RQ) and the boundary as last row (type V for
  vacuum, PEC/PMC for perfect conductors — those need no sigma).
- **Load pytlwall Config…** — if you already have a pytlwall chamber `.cfg`
  (the format of pytlwall's own examples), WIMBA reads it: geometry, layers,
  boundary, beta, gamma and the frequency grid come from the file. The grid is
  rebuilt by WIMBA from `[frequency_info]`, so it covers the same range as
  pytlwall's own but does not sample the same points; see
  **[PYTLWALL_CFG.md](PYTLWALL_CFG.md)** before comparing the two codes.

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

## Step 4 (optional) — compare with imported data

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
  material name. Unknown names are an error, never a silent default.
- *pytlwall is required…*: install it into the same environment (see
  [SETUP.md](SETUP.md)).
- The persistent log (always at debug level) lives at
  `~/.local/state/wimba/wimba.log`; the Console level is set in
  **View → Log Level**.
