<p align="center">
  <img src="../img/wimba_logo_small.png" alt="WIMBA" width="190">
</p>

# Building a study: `wimba build` and `wimba show`

Describe the study once in an input coordinator (see [CONFIG.md](CONFIG.md)),
then WIMBA computes each element and writes the results to disk.

## Quick start

```bash
wimba build examples/SubLHC_input.yaml     # -> examples/SubLHC/output/
wimba show  examples/SubLHC/output
```

## `wimba build`

```bash
wimba build <input.yaml> [--out <dir>]
```

**Where the output goes**, in order of precedence:

1. `--out <dir>` on the command line;
2. the `output:` key in the YAML (relative paths are resolved next to the config);
3. default: `<config_dir>/<name>/output`.

So `examples/SubLHC_input.yaml` (name `SubLHC`) writes to `examples/SubLHC/output/`.

It computes **each element** on the common grid and writes:

```
examples/SubLHC/output/
  SubLHC_resume.yaml                    # grids, components, totals, per element
  collimators/
    TCP.C6L7.B1/  TCP.C6L7.B1_res_ZLong.dat  TCP.C6L7.B1_res_ZDipX.dat  ... _WLong.dat ...
    TCSG.A6L7.B1/ ...
  pipes/
    MB.A8L7.B1/   MB.A8L7.B1_res_ZLong.dat ...
  space_charge/
    TCP.SC.B1/    TCP.SC.B1_dsc_ZLong.dat
  additional/
    crab/         crab_cst_ZLong.dat
  total/
    TOT_ZLong.dat  TOT_ZDipX.dat  ...  TOT_WLong.dat  ...
```

File names read `<Element>_<origin>_<Component>.dat`. Each file is a self-contained
column table, so you can plot one on its own:

```python
import numpy as np
f, reZ, imZ = np.loadtxt("examples/SubLHC/output/total/TOT_ZLong.dat", unpack=True)
```

Resistive wall and space charge (longitudinal, dipolar, quadrupolar) will be
produced per chamber by the pytlwall engine (`source: tlwall`); until then the
collimators/pipe use analytic resonators and the space-charge entry is a
placeholder imported from a file.

## `wimba show`

Prints the grids, the components, and per element its optics/info, origin, and the
components computed - a quick map of the output without opening files.

## Summing on demand

The per-element files are the primary product; `total/` holds the beta-weighted
machine totals. For anything in between, `ResultStore` reads one element at a time:

```python
from wimba import ResultStore
store = ResultStore("examples/SubLHC/output")

store.impedance()                                 # whole machine, per component
store.impedance(groups=["pipes"])                 # only the pipes
store.impedance(multipole="dip")                  # only dipolar
store.impedance(origin="space_charge_direct")     # only direct space charge
store.impedance(include_additional=False)         # exclude pre-weighted extras
store.wake(groups=["collimators"])
```

## In Python instead of the CLI

```python
from wimba import load_project, materialize, ResultStore
project = load_project("examples/SubLHC_input.yaml")
materialize(project, "examples/SubLHC/output")
store = ResultStore("examples/SubLHC/output")
```
