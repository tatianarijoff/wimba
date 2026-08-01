# IW2D in WIMBA

**ImpedanceWake2D** computes the impedance of a multilayer structure — round or
flat, infinitely long — from the analytic electromagnetic fields of a
point-charge beam at any velocity. It is developed at CERN and is the natural
second opinion on a pytlwall result: the same physical problem, an independent
implementation.

WIMBA drives it through its **Python API**, not through the command-line
executables.

## Installing IW2D

Install it into **the same virtual environment as WIMBA**, exactly as with
pytlwall. IW2D's Python package is a binding over a C++ core loaded at import
time through `cppyy`, so the one extra step compared with pytlwall is providing
that core's shared libraries. Building the `.x` executables by hand is not
required.

On Debian or Ubuntu:

```bash
sudo apt-get install libgsl-dev libgmp-dev libmpfr-dev libflint-dev libflint-arb-dev

cd <wimba>
source .venv/bin/activate
pip install cppyy
pip install -e <path to IW2D>
```

> **Debian and Ubuntu name the Arb library `flint-arb`, not `arb`.**
> IW2D loads `arb` unless told otherwise, so on these distributions set
> ```bash
> export IW2D_FLINT_ARB=1
> ```
> before importing it. Without this the import fails on a library that is
> installed and present. Add it to your shell profile, or to the environment
> WIMBA runs in, so it is not forgotten between sessions.

IW2D loads `gslcblas`, `gsl`, `gmp`, `mpfr` and `arb`/`flint-arb`. If your
distribution packages them under other names, or you prefer not to touch the
system, conda provides the same set:

```bash
conda install -c conda-forge gsl mpfr arb cppyy
```

which can also be used alongside a venv, provided both are active. IW2D
additionally ships GMP and MPFR sources under `IW2D/External_libs/` with a
`compile_ext_libs.sh` script, for environments where neither route is
available.

Check the result from inside the WIMBA environment:

```python
from wimba.sources.iw2d_bridge import iw2d_available
print(iw2d_available())
```

If this is `False`, the cause is almost always one of the shared libraries
rather than IW2D itself — on Debian and Ubuntu, most often the `IW2D_FLINT_ARB`
variable above. On lxplus and hpc-batch a ROOT installation can confuse
`cppyy`; IW2D's own README documents that workaround.

## Using it

`method: iw2d` on an element, exactly like `pytlwall`:

```yaml
devices:
  kicker:
    source: single
    method: iw2d
```

Or directly:

```python
from wimba.sources.iw2d_bridge import compute_iw2d
import numpy as np

out = compute_iw2d(np.logspace(2, 10, 200), radius_m=0.01,
                   layers=[{"type": "CW", "thickness": 0.002, "sigma": 5.96e7}],
                   length_m=1.0, gamma=7000.0)
out["ZLong"]        # complex array
```

The layer dictionaries are the same ones the pytlwall bridge accepts, so one
element definition can be computed both ways and the results compared.

Only **circular** chambers are wired. IW2D does handle flat geometries, through
a different input object; that path is not implemented yet and a non-circular
shape raises a clear error rather than computing something else.

## Two conventions that will bite

These are not bugs on either side. They are different definitions, and a
comparison that ignores them will show a disagreement that is not there.

### IW2D has no perfect conductor

IW2D's outermost layer is semi-infinite by construction: there is no PEC. Its
documentation suggests approximating one with a very low resistivity, warning
that numerical issues may follow.

The bridge does exactly that — `PEC_RESISTIVITY = 1e-15` Ω·m — and **says so**.
Ask for the notes and they come back with the result:

```python
out, notes = compute_iw2d(freqs, radius_m=0.01, layers=layers,
                          return_notes=True)
for n in notes:
    print(n)
```

Treat an IW2D result on a PEC-bounded chamber as an approximation, not as an
equivalent calculation.

There is an upside. Because IW2D has no notion of a PEC boundary, it cannot
contain any PEC-specific branch — which makes it a genuinely independent
witness on questions where such a branch is what is in dispute.

### IW2D returns the wall impedance, including indirect space charge

From IW2D's own documentation: the impedance it computes contains the indirect
space-charge term, because that term is essential to the low-frequency
behaviour and cannot easily be separated from the resistive part.

pytlwall keeps the two apart. So the comparable quantities are:

| IW2D | pytlwall |
|------|----------|
| `Zlong` | `ZLong + ZLongISC` |
| `Zxdip`, `Zydip` | `ZDipX + ZDipXISC`, `ZDipY + ZDipYISC` |

In WIMBA those sums are already computed and exported, under the names
`ZLong+ISC`, `ZDipX+ISC` and so on. Comparing IW2D's `Zlong` against pytlwall's
bare `ZLong` produces a systematic discrepancy at low frequency — all of it an
artefact of the convention.

## Parameter mapping

Handled inside the bridge; listed here because it is where a hand-written
comparison goes wrong.

| WIMBA / pytlwall | IW2D | conversion |
|------------------|------|------------|
| `sigma` [S/m] | resistivity [Ω·m] | reciprocal |
| `thickness` [m] | thickness [m] | none in the Python API |
| `k_Hz` [Hz] | relaxation frequency [Hz] | none in the Python API |
| `epsr` | relative permittivity | none |
| `muinf_Hz` | magnetic **susceptibility** | χ = µ_r − 1 |
| — | outermost thickness | forced to infinity |

The last two deserve care. `muinf_Hz` is pytlwall's name for a relative
permeability: IW2D wants the susceptibility, so 460 becomes 459. On a strongly
magnetic material the error is invisible; on a weakly magnetic one it is fatal.
And IW2D's last layer is semi-infinite whatever the input says, so the bridge
extends it rather than letting a finite thickness be silently ignored.

The command-line input files use different units again — thickness in mm,
relaxation frequency in MHz — but WIMBA does not go through them.

### Yokoya factors

IW2D takes them explicitly. The bridge defaults to the round-chamber set:

```
long, xdip, ydip, xquad, yquad  =  1, 1, 1, 0, 0
```

Note `xquad = yquad = 0`: for a circular chamber the quadrupolar terms are
exactly zero. Override with the `yokoya=` argument if a non-circular geometry is
being represented by an equivalent round one.

## Comparing the three codes

For a cross-check on the same element:

1. Compute with `method: pytlwall` and with `method: iw2d`, on one grid.
2. Compare **`ZLong+ISC`** against IW2D's `ZLong`, not the bare terms.
3. If a PEC boundary is involved, read the notes: the IW2D side is an
   approximation there.
4. For measured or CST reference data, import it through
   **Component → Load Precalculated…** so all three appear in the same Results
   tree and can be exported together.

The tab-separated export (**Export Results → As TXT**) writes the layout
pytlwall uses, so the three sets of numbers line up column by column.

## See also

- [PYTLWALL_CFG.md](PYTLWALL_CFG.md) — loading a pytlwall config, and why the
  frequency grid is rebuilt
- [SETUP.md](SETUP.md) — tool configuration
