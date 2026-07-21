# resonator — analytic source, minimal example

The smallest possible machine: two cavities described by analytic resonators
(shunt impedance, quality factor, resonant frequency), weighted by a tiny
inline optics. No external engines and no imported data.

## Files provided

| file | what it is |
|------|------------|
| `resonator_input.yaml` | the machine **input** (build flow, for `wimba build` / GUI *Load Machine*): two elements with per-quantity resonator terms, grids |
| `resonator.tfs` | tiny MAD-X-style twiss providing position and beta by element name |

## Run from the shell

```bash
wimba build examples/resonator/resonator_input.yaml
wimba show  examples/resonator/resonator_output
```

## Run from the GUI

`File → Load Machine` → `resonator_input.yaml`: inspect the two cavities, their
resonator terms in the Models tab, and the optics.

## Outputs

`resonator_output/`: per-origin impedance/wake tables (`.dat`) and the resume.
Useful as the minimal reference for the resonator source and the build flow.
