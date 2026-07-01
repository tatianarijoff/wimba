<p align="center">
  <img src="../img/wimba_logo_small.png" alt="WIMBA" width="190">
</p>

# Building a machine: `wimba build` and `wimba show`

You describe the accelerator once in a YAML file, then WIMBA computes each element
and writes the results to disk. Two commands do the work.

## Quick start

```bash
wimba build examples/machine.yaml --out results   # compute and write per-element files
wimba show results                                 # see what was computed
```

That's it. `build` reads the config, computes **each element** on a common grid,
and writes its impedance/wake to files; `show` prints a summary of the result.

## `wimba build`

```bash
wimba build <config.yaml> --out <dir>
```

For every element it writes one file per term under a per-element folder:

```
results/
  manifest.yaml                              # structure, grid, beta per element
  collimators/
    c1/  Z__resonator__zlong.dat  Z__resonator__zxdip.dat  W__resonator__zlong.dat ...
    c2/  Z__resonator__zlong.dat ...
  pipes/
    p1/  Z__resonator__zlong.dat ...
  additional/
    crab/ Z__resonator__zlong.dat ...
```

File names read as `Q__origin__term`: `Q` is `Z` (impedance) or `W` (wake),
`origin` is where it comes from (`resonator`, later `resistive_wall`,
`space_charge`, ...), `term` is the multipole (`zlong`, `zxdip`, ...). Each file
is a self-contained column table, so you can plot one on its own:

```python
import numpy as np
f, reZ, imZ = np.loadtxt("results/collimators/c1/Z__resonator__zlong.dat", unpack=True)
```

## `wimba show`

```bash
wimba show <dir>
```

Lists groups, elements, the terms and origins each one has, and its beta (or
`pre-weighted`):

```
Results in results
  collimators:
    c1: terms[zlong, zxdip] origins[resonator] beta=(10.0, 20.0)
    c2: terms[zlong] origins[resonator] beta=(30.0, 40.0)
  pipes:
    p1: terms[zlong] origins[resonator] beta=(5.0, 5.0)
  additional:
    crab: terms[zlong] origins[resonator] pre-weighted
```

## Summing the contributions

The per-element files are the primary product; sums are done on demand, reading
one element at a time (never the whole lattice in memory):

```python
from wimba import ResultStore
store = ResultStore("results")

store.impedance()                                    # whole machine, per term
store.impedance(groups=["pipes"])                    # only the pipes
store.impedance(multipole="long")                    # only longitudinal
store.impedance(origin="resonator", include_additional=False)
store.wake(groups=["collimators"])                   # wakes, collimators only
```

Each call returns `{term_id: array}`, summed and beta-weighted exactly as the
in-memory machine would, but read from the files.

## Doing it in Python instead of the CLI

```python
from wimba import load_machine, materialize, ResultStore
machine, freqs, times = load_machine("examples/machine.yaml")
materialize(machine, "results", freqs=freqs, times=times)
store = ResultStore("results")
```

See [CONFIG.md](CONFIG.md) for the full YAML format.
