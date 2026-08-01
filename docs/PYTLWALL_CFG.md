<p align="center"><img src="../img/wimba_logo_small.png" alt="WIMBA" width="190"></p>
# Loading a pytlwall config into WIMBA

**Component → Load pytlwall Config…**

WIMBA can read a pytlwall chamber `.cfg` — the format of pytlwall's own
examples — and compute that component. This page describes exactly what is
taken from the file, what is not, and why the frequency grid is one of the
things WIMBA rebuilds. Read it before comparing a WIMBA result with a pytlwall
result: the two will agree, but not necessarily on the same frequencies.

## What the command does

1. Reads the configuration file and builds a component from it.
2. Computes the frequency grid **in WIMBA**, from the `[frequency_info]`
   section.
3. Calls pytlwall through its Python API, passing that grid as an array of
   frequencies, and receives the impedances back.
4. Puts the result in the **Results** tree, where it can be plotted, tabulated
   and exported like any other source.

pytlwall performs the whole electromagnetic calculation. WIMBA decides *at
which frequencies* it is performed.

## What is read from the file

| Section | Used for |
|---------|----------|
| `[base_info]` | shape, radius or half-axes, length, `betax`, `betay` |
| `[layers_info]`, `[layer0]` … | the wall build-up, inside → out |
| `[boundary]` | the closing layer (`V`, `PEC`, `PMC`, `CW`) |
| `[beam_info]` | `gammarel` |
| `[frequency_info]` | `fmin`, `fmax`, `fstep` — see below |

The `[output]`, `[output1]`, `[img_output1]` … sections are **ignored**: they
tell pytlwall which files and plots to write, and in WIMBA that job belongs to
the Results workspace and to *Export Results*.

A component loaded this way carries its own `gammarel` and frequency grid.
They win over the configuration currently open in the GUI, because such a
component belongs to no machine and has nothing to conform to. Before each
calculation WIMBA states which values are in use and where they come from, in
the console and in the status bar:

```
ferrite_kicker: gamma = 7000.0, f = 100 .. 1e+10 Hz, 8001 points
                -- from the element's own config [pytlwall config kicker.cfg]
```

## Why the grid is rebuilt in WIMBA

WIMBA does not hand the `.cfg` to pytlwall and let it run. It reads the chamber
from the file and calls pytlwall's Python API with an explicit array of
frequencies. The grid is therefore WIMBA's, always — even when the numbers in
it come from the file.

This is deliberate, and it follows from what WIMBA is for:

- **A machine total has to be a sum.** Impedances from different elements can
  only be added if they are sampled at the same frequencies. If each source
  chose its own grid, no total could be formed without interpolating, and
  interpolation would silently degrade the result.
- **Sources must be comparable.** A pytlwall wall, an analytic resonator, a
  tabulated CST import and an IW2D run have to land on one plot and in one
  table. Only a shared grid makes that meaningful.
- **The grid is a property of the study, not of a component.** When a component
  is part of a machine, the machine's grid is the right one. The exception —
  a component loaded from its own config — is exactly what this page is about.

## Consequence: the two grids differ

pytlwall and WIMBA read the same `fmin`, `fmax` and `fstep` but build different
grids from them. Neither is wrong; they are different conventions.

| | pytlwall | WIMBA |
|---|---|---|
| spacing | **linear within each decade** | **logarithmic** over the whole range |
| points per decade | 9 × 10<sup>fstep−1</sup> | 10<sup>fstep</sup> |

With `fmin = 2`, `fmax = 4`, `fstep = 3`:

```
pytlwall   1800 points:   100, 101, 102, 103, ...     (step 1 in the first decade)
WIMBA      2001 points:   100, 100.23, 100.46, ...    (constant ratio)
```

Both cover 10² – 10⁴ Hz and both describe the same curve. But a row-by-row
comparison of the two output files is meaningless: row *n* is a different
frequency in each. Compare **at matching frequencies**, or overlay the curves
on a plot.

## If you want a pure pytlwall calculation

When the result has to be pytlwall's own — same grid, same file layout, for a
validation or a report — do not route it through WIMBA. Run pytlwall directly:

```bash
python -m pytlwall -a my_chamber.cfg
```

and then bring the numbers in through **Component → Load Precalculated…**,
which imports a computed impedance instead of recomputing it. The result joins
the Results tree alongside the others and can be plotted, tabulated and
exported normally, labelled `NAME[precalculated: file]` so it stays
distinguishable from anything WIMBA computed itself.

This is the honest route for a cross-check: the imported curve is pytlwall's,
untouched, on pytlwall's own grid.

## Verified agreement

On a four-layer ferrite kicker — titanium coating, ceramic, vacuum gap, ferrite
on a PEC boundary — the two codes were compared at matching frequencies:

| quantity | max relative difference |
|----------|------------------------|
| `ZLong` | 2.9·10⁻⁴ |
| `ZDipX`, `ZDipY` | 2.2·10⁻⁵ |
| `ZQuadX`, `ZQuadY` | 2.9·10⁻⁴ |

At the frequencies where the two grids coincide exactly the values agree to
every digit printed; the residual above comes from interpolating one grid onto
the other, and is largest where the curve bends most sharply.

## See also

- [COMPONENT.md](COMPONENT.md) — the Component bench, step by step
- [EXAMPLES.md](EXAMPLES.md) — the bundled examples
