<p align="center">
  <img src="../img/wimba_logo_small.png" alt="WIMBA" width="190">
</p>

# Machine config (YAML) reference

This file describes the **accelerator**: its optics and its elements, grouped by
kind. It is read by `wimba build` (or `load_machine` in Python). It is separate
from the tool config written by `wimba setup`, which only records where IW2D /
pytlwall live.

## Minimal example

```yaml
grid:
  freq: {min: 1.0e8, max: 3.0e9, n: 400, log: true}

twiss:
  c1: [10.0, 20.0]

groups:
  collimators:
    - name: c1
      source: resonator
      resonators:
        - {term: zlong, Rs: 1.0e4, Q: 1.0, fr: 1.0e9}
```

## Top-level sections

| section | required | meaning |
|---------|----------|---------|
| `grid` | for `build` | the frequency / time grids every element is computed on |
| `twiss` | optional | element name → `[beta_x, beta_y]`, used for beta weighting |
| `groups` | yes | named buckets of elements (`collimators`, `pipes`, ...) |
| `additional` | optional | pre-weighted elements kept apart from the groups |

### `grid`

```yaml
grid:
  freq: {min: 1.0e8, max: 3.0e9, n: 400, log: true}   # impedance grid
  time: {min: 0.0,   max: 5.0e-9, n: 400}              # wake grid (optional)
```

| field | meaning |
|-------|---------|
| `min`, `max` | range endpoints (Hz for `freq`, s for `time`) |
| `n` | number of points |
| `log` | `true` for logarithmic spacing (default linear) |

If `time` is omitted, only impedances are written; if `freq` is omitted, only
wakes are written.

### `twiss`

```yaml
twiss:
  c1: [10.0, 20.0]      # beta_x, beta_y at element c1
  p1: [5.0, 5.0]
```

An element without inline betas looks itself up here **by name**. A name not
needed here can be omitted (e.g. pre-weighted elements).

## Elements

Each entry in a group (or in `additional`) is an element:

```yaml
- name: c1               # required; also the twiss lookup key
  category: collimator   # optional, default "element"; used for grouping/labels
  length: 1.0            # optional, default 1.0 (metres)
  source: resonator      # which engine produces the terms (default "resonator")
  # ... source-specific fields ...
  # ... optics (see below) ...
```

### Optics: how an element gets its beta

Pick one; checked in this order:

| if you write... | WIMBA uses |
|-----------------|------------|
| `pre_weighted: true` | the impedance as-is (beta already included), weight 1 |
| `beta_x: ...` and `beta_y: ...` | those betas directly |
| *(nothing)* | a lookup in `twiss` by the element's `name` |
| `twiss_name: OTHER` | a lookup in `twiss` by `OTHER` instead of `name` |

`pre_weighted` is for contributions already summed/weighted elsewhere — e.g. an
externally computed model dropped into `additional`.

## Sources (engines)

### `resonator`

Analytic resonator terms.

```yaml
source: resonator
resonators:
  - {term: zlong, Rs: 1.0e4, Q: 1.0, fr: 1.0e9}
  - {term: zxdip, Rs: 1.0e6, Q: 1.0, fr: 1.0e9}
```

| field | meaning |
|-------|---------|
| `term` | one of `zlong`, `zxdip`, `zydip`, `zxquad`, `zyquad` |
| `Rs` | shunt impedance (Ω for `zlong`, Ω/m for transverse) |
| `Q` | quality factor |
| `fr` | resonant frequency (Hz) |

*(More engines — `resistive_wall` via pytlwall, tabulated `cst` import — register
the same way and add their own fields here as they land.)*

## Full annotated example

```yaml
grid:
  freq: {min: 1.0e8, max: 3.0e9, n: 400, log: true}
  time: {min: 0.0,   max: 5.0e-9, n: 400}

twiss:
  c1: [10.0, 20.0]
  c2: [30.0, 40.0]
  p1: [5.0, 5.0]

groups:
  collimators:
    - name: c1
      category: collimator
      source: resonator
      resonators:
        - {term: zlong, Rs: 1.0e4, Q: 1.0, fr: 1.0e9}
        - {term: zxdip, Rs: 1.0e6, Q: 1.0, fr: 1.0e9}
    - name: c2
      category: collimator
      source: resonator
      resonators:
        - {term: zlong, Rs: 2.0e4, Q: 1.0, fr: 1.2e9}
  pipes:
    - name: p1
      category: pipe
      source: resonator
      resonators:
        - {term: zlong, Rs: 4.0e1, Q: 1.0, fr: 0.9e9}

additional:
  - name: crab
    source: resonator
    pre_weighted: true
    resonators:
      - {term: zlong, Rs: 7.0e3, Q: 1.0, fr: 0.8e9}
```
