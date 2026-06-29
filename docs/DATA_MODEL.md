<p align="center">
  <img src="../img/wimba_logo_small.png" alt="WIMBA" width="190">
</p>

# Data model

WIMBA represents an accelerator impedance/wake model on four levels. The lower
two describe *what* a contribution is; the upper two describe *how*
contributions are organised and summed into a machine.

| Level | Object | Role |
|-------|--------|------|
| term | `ImpedanceTerm` | one multipole term: `Z(f)` and/or `W(t)` |
| device | `Element` | a physical device with a swappable impedance source |
| group | `ElementGroup` | a named bucket of like devices |
| machine | `Machine` | the whole ring + the optics that weights it |

The core (`wimba/core/`) knows none of the physics: it never mentions resistive
wall, CST or resonators. Concrete sources live in `wimba/sources/` and depend on
the core, never the other way round.

## `ImpedanceTerm`

A single multipole term carries **two orthogonal tags**:

- its **multipole identity** `tid` (a `TermId`: plane + exponents), which drives
  the beta weighting;
- its **physical origin** `origin` (`"resistive_wall"`, `"space_charge"`,
  `"geometric"`, `"resonator"`, `"imported"`, …), so contributions can be
  filtered, included/excluded and plotted separately. This is what lets space
  charge sit next to resistive wall without being forced into the same bucket.

`z` (impedance) and `w` (wake) are independent callables: a term may provide one,
the other, or both. Evaluation is **lazy** — `term.impedance(freqs)` /
`term.wake(times)` compute numbers only when given a grid.

### The five standard terms

A `TermId` has a `plane` (`'z'`, `'x'`, `'y'`) and two exponent pairs,
`source = (sx, sy)` and `test = (tx, ty)`:

| id | plane | source | test | power | category |
|----|-------|--------|------|-------|----------|
| `zlong`  | z | (0,0) | (0,0) | 0 | long |
| `zxdip`  | x | (1,0) | (0,0) | 1 | dip  |
| `zydip`  | y | (0,1) | (0,0) | 1 | dip  |
| `zxquad` | x | (0,0) | (1,0) | 1 | quad |
| `zyquad` | y | (0,0) | (0,1) | 1 | quad |

`power` is the total exponent order; `category` is derived as `long` when
`power == 0`, `dip` when the source exponents are non-zero, `quad` otherwise.

## Beta weighting

When a device is summed into the ring, its term is weighted by the local beta
functions:

$$w = \beta_x^{\,s_x + t_x}\; \beta_y^{\,s_y + t_y}.$$

This gives $\beta^0 = 1$ for the longitudinal term (no beta dependence) and
$\beta^1$ for the transverse dipolar and quadrupolar terms — the standard
linear-in-beta weighting. The rule lives in one place, `TermId.beta_weight`, so
the convention can be revisited there alone (for instance to normalise by a
reference beta).

## `Element`

A physical device — collimator, beam-pipe section, cavity, kicker:

```python
Element(name, category, length, provider, optics=FromTwiss())
```

- `name` is the join key against the twiss table.
- `category` is the kind of device, used for grouping.
- `length` is the **total** device length. By the provider contract the
  impedance already includes the length, so `length` is never used to
  re-multiply `Z` — it is bookkeeping metadata.
- `provider` is the swappable impedance source (see below).
- `optics` decides how the betas are obtained.

`element.terms()` simply delegates to `provider.terms(element)`.

### Impedance source (provider)

`ImpedanceProvider` is a protocol with a single method,
`terms(element) -> list[ImpedanceTerm]`. Each source in `wimba/sources/` knows
one physics or one file format and returns the device's terms **total-device and
un-weighted in beta** — the beta weighting is applied later by `Machine`. This
is the seam that makes "compute or import, per element" possible: the same
collimator can be served by a resistive-wall provider or by a CST importer
without the core noticing.

### Optics policy

| policy | betas come from | pre-weighted |
|--------|-----------------|--------------|
| `FromTwiss(name=None)` | the twiss table, by `name` (default: the element's own name) | no |
| `Explicit(beta_x, beta_y)` | given inline | no |
| `PreWeighted()` | not needed (weight is 1) | yes |

`PreWeighted` is used for elements whose impedance already includes their beta
weighting: they are summed as-is and never looked up in the twiss.

## `ElementGroup`

A named bucket of elements of the same kind (`"collimators"`, `"pipes"`, …),
used both for organisation (the GUI tree) and for plotting the impedance of a
whole group in isolation.

## `Machine`

The whole ring holds **two populations**:

- `groups` — elements weighted by beta via name lookup in `twiss`;
- `additional` — pre-weighted elements, summed as-is, kept separable.

```python
m = Machine(twiss=...)
g = m.add_group("collimators")     # create a group
g.add(element)                     # add elements to it
m.add_additional(element)          # add a pre-weighted element apart
```

### Querying

Two methods select along two axes — which terms, and which quantity:

```python
m.impedance(freqs, *, plane=None, multipole=None, origin=None,
            groups=None, include_additional=True)   # -> {term_id: complex array}
m.wake(times,  *, plane=None, multipole=None, origin=None,
       groups=None, include_additional=True)        # -> {term_id: real array}
```

- `plane` / `multipole` / `origin` filter which terms enter the sum.
- `groups` restricts to named groups (default: all groups).
- `include_additional` toggles the pre-weighted bucket; to plot a single group in
  isolation, pass `include_additional=False`.

The result is a dictionary keyed by term id, each value the beta-weighted sum
over all selected elements on the given grid. Evaluation is lazy, so only the
selected terms are ever computed.

### TwissTable

`TwissTable` is currently a minimal stub: it maps an element name to a single
`(beta_x, beta_y)` pair. A name that occurs several times around the ring is not
yet handled — the planned extension maps a name to a list of occurrences and
sums their contributions. The optics builder from MAD-X will populate it.

## End-to-end example

```python
import numpy as np
from wimba import (Machine, TwissTable, Element,
                   Resonator, ResonatorProvider, PreWeighted)

m = Machine(twiss=TwissTable({"c1": (10.0, 20.0), "c2": (30.0, 40.0)}))

coll = m.add_group("collimators")
coll.add(Element("c1", "collimator", 1.0,
                 ResonatorProvider([Resonator("zlong", 100.0, 1.0, 1e9),
                                    Resonator("zxdip",   1.0, 1.0, 1e9)])))
coll.add(Element("c2", "collimator", 1.0,
                 ResonatorProvider([Resonator("zlong", 200.0, 1.0, 1e9)])))

# a pre-weighted future addition, kept apart
m.add_additional(Element("crab", "additional", 1.0,
                         ResonatorProvider([Resonator("zlong", 70.0, 1.0, 1e9)]),
                         optics=PreWeighted()))

f = np.linspace(0.1e9, 2e9, 400)

z_long = m.impedance(f, multipole="long")                          # {'zlong': ...}
z_dip  = m.impedance(f, multipole="dip")                           # {'zxdip': ...}, beta_x-weighted
z_coll = m.impedance(f, groups=["collimators"], include_additional=False)
```
