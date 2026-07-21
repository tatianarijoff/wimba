# LHC Beam 1 — full-machine example

A realistic model of LHC Beam 1 assembled from the pywit LHC model data:
optics-driven, with the default resistive wall (the arc beam screen) on every
lattice segment that is not a named device.

## Files provided

| file | what it is |
|------|------------|
| `LHC_config.yaml` | the assembly **config** (for `wimba run` / GUI *Open Config*): optics, frequency grid, gamma, user material conductivities, device sources, default pipe reference, requested per-device outputs |
| `lhc_beam_screen.cfg` | the **default resistive wall**, as an external pytlwall-chamber-style file: elliptical 23.2 x 18.4 mm half-axes, 75 um co-laminated copper (cryogenic sigma) on 1 mm stainless steel, vacuum boundary. No beta/beam keys: the machine decides those |
| `data/twiss_lhcb1_beta130cm.tfs` | MAD-X twiss of the full lattice (~13k rows) - **not in git** (~5 MB): copy it from the pywit model into `data/` before running |
| `data/lhc_collimators_reference_b1.json` | 55 collimators: half-gap, length, wall build-up by material name |
| `data/lhc_rf_cavities_homs.json` | RF-cavity higher-order modes (Rl/Ql/fl + transverse), computed as lumped resonators |

## Run from the shell

```bash
wimba run examples/LHC/LHC_config.yaml            # impedance
wimba run examples/LHC/LHC_config.yaml --wake     # + wakes (native pytlwall + resonator)
wimba assemble examples/LHC/LHC_config.yaml       # only the assignment array + collisions
wimba plot examples/LHC/LHCB1_output/single_elements/total.csv --components ZLong,ZLongISC
```

## Run from the GUI

```bash
python -m wimba.gui
```

1. `File → Open Config` → `LHC_config.yaml` (Machine and Optics panels populate);
2. `Calculate → Calculate Whole Machine` (async; log in Console, collisions in
   Problems);
3. the **Results** panel lists everything computed: double-click or drag
   quantities into the **Plot Workspace** (x/y scales, curve list, PNG/CSV
   export) or the **Results Table** (columns, CSV export);
4. `File → Open Results` reopens `LHCB1_output/` later without recomputing.

## Outputs

By default (`LHCB1_output/`):
- `single_elements/total.csv` — the machine total: `ZLong, ZDipX, ZDipY, ZQuadX,
  ZQuadY`, their indirect-space-charge counterparts (`ZLongISC`, ...) kept as
  separate columns, plus `total_wake.csv` with `--wake`;
- per-device CSVs for the names listed under `output:` in the config — here
  `collimators/TCP.C6L7.B1.csv`, `rf_homs/RF.csv`, and the special name
  `default_pipe` which writes **one aggregated CSV** summing all ~11k pipe
  segments;
- `total_Z*.png` (and `total_W*.png` with `--wake`), `WAKE_NOTES.txt` with the
  wake provenance;
- `LHCB1_assignments.csv` from `wimba assemble` (position, name, method, beta,
  beta source, collisions).

To get more:
- add any device name to `output:` → its own CSV appears (and in the GUI tree);
- in the GUI, the derived `Z*Total = wall + ISC` quantities are available per
  source; ISC can be plotted on its own;
- declare missing material conductivities under `materials:` — unknown materials
  are an error, never a silent default.
