# SubLHC — element-driven build example

A small machine described the **build** way: named groups of elements you list
explicitly (no lattice sweep, no default pipe), each computed or imported and
weighted by name against a small synthetic twiss.

## Files provided

| file | what it is |
|------|------------|
| `SubLHC_input.yaml` | the machine **input** (for `wimba build` / GUI *Load Machine*): groups (collimators as resonators, a space-charge import, an additional pre-weighted CST term), grids |
| `SubLHC.tfs` | small synthetic MAD-X twiss (kept in git) that provides position and beta by element name |
| `data/*.dat` | tabulated impedance files imported by the `cst` elements |

## Run from the shell

```bash
wimba build examples/SubLHC/SubLHC_input.yaml     # -> SubLHC_output/
wimba show  examples/SubLHC/SubLHC_output         # summary of what was built
```

## Run from the GUI

`File → Load Machine` → `SubLHC_input.yaml`: the machine tree, element panels
(geometry, layers, models, optics) and the Optics panel populate; elements can
be added, edited, duplicated. (Computing an edited machine from the GUI arrives
with the machine→config bridge; today the GUI computes configs via *Open
Config*.)

## Outputs

`SubLHC_output/`: per-origin impedance/wake tables (`.dat`) and
`SubLHC_resume.yaml` describing what was materialised. `wimba show` prints the
groups, elements, optics and origins.
