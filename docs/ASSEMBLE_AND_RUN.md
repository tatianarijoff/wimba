<p align="center"><img src="../img/wimba_logo_small.png" alt="WIMBA" width="190"></p>

# Assemble &amp; run: from optics to the machine total

This flow takes a lattice (MAD-X twiss) plus device definitions and produces the
machine impedance. It is driven by one YAML coordinator and three commands:

```bash
wimba assemble <config.yaml>     # the assignment array (who/where/how/beta) + collisions
wimba run      <config.yaml>     # assemble + compute + total.csv + default plots
wimba plot     total.csv         # (re)plot components from a totals CSV
```

## The coordinator config

```yaml
name: LHCB1
optics: data/twiss_lhcb1_beta130cm.tfs     # MAD-X twiss (.tfs)
grid:
  frequency: {min: 1.0e5, max: 1.0e10, n: 100, log: true}

default_pipe:                              # applied to every uncovered lattice row
  method: pytlwall
  space_charge: false
  radius_mm: 22.0
  material: stainless_steel

devices:
  collimators:
    source: collimators_json
    file: data/lhc_collimators_reference_b1.json
    method: pytlwall
    space_charge: true
  rf_homs:
    source: resonators_json
    file: data/lhc_rf_cavities_homs.json
    method: resonator

output: [TCP.C6L7.B1]                      # per-device CSV only for these (opt-in)
```

| key | meaning |
|-----|---------|
| `optics` | MAD-X twiss; used to resolve beta and position |
| `grid.frequency` | `{min, max, n, log}` frequency grid |
| `default_pipe` | resistive wall for lattice rows without a named device |
| `devices` | named sources (collimator/resonator JSON, ...) with a method |
| `output` | device names to also write individually (total is always written) |

## Beta resolution

For each contribution beta is resolved, in order: by **position** `s`
(interpolated between the two adjacent twiss points); else by **name** (the twiss
row of that name); else the element is placed at the **end of the machine** with
beta = 1 (editable). The resolution used is recorded per row (`interp` / `name` /
`default-1`).

## Methods and weighting

Methods are `pytlwall`, `iw2d`, `precalculated`, `resonator`, each **plain** or
**weighted**. Plain = WIMBA applies the beta from the twiss; weighted = the result
already carries beta and is summed as-is. Space charge is a flag on the pytlwall
methods. Currently the compute engine implements `pytlwall`; the others are
recorded in the array and skipped in the computation for now.

## The default pipe, computed once

Every lattice row without a named device becomes a default-pipe contribution with
that row's length and local (interpolated) beta. All of them share one geometry,
so the chamber is computed **once** at unit length and beta = 1 and then scaled by
L and beta per row - the ~11k LHC pipe segments cost a single pytlwall call.

## `wimba assemble` — the array

Writes `<name>_assignments.csv`, one row per contribution: `position_s, name,
kind, method, weighted, space_charge, beta_x, beta_y, beta_source, allow_overlap,
length`. Two contributions at the same position (within 1 mm) are reported as a
collision - flagged as an error unless every one of them sets `allow_overlap`
(an intentional overlap).

## `wimba run` — compute and totals

Assembles, computes each contribution (weighting beta), sums, and writes:

```
<name>_output/
  single_elements/
    total.csv                         # the machine total (always)
    <group>/<device>.csv              # only devices listed under output:
  total_ZLong.png  total_ZDipX.png  total_ZDipY.png    # Re/Im per component
  total_WLong.png                     # with --wake
```

Each CSV is `freq, Re_<comp>, Im_<comp>, ...`. Default plots are one figure per
component showing real and imaginary parts vs frequency. `--wake` adds the
longitudinal wake, obtained from the total impedance by the Fourier transform
(its fidelity depends on the frequency grid).

## `wimba plot` — replot from a CSV

```bash
wimba plot <name>_output/single_elements/total.csv --components ZLong,ZDipX
```

From a file you say which components you want; in the GUI you choose at runtime.
