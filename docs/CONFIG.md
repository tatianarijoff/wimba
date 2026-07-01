<p align="center">
  <img src="../img/wimba_logo_small.png" alt="WIMBA" width="190">
</p>

# Input config (YAML) reference

The input file is a **coordinator**: it says *where* to find things and how to
group them - it does not repeat information that already lives elsewhere. Optics
(position, length, beta) are read from a MAD-X twiss file, matched by element
name; each element only names its source (an analytic resonator, a pytlwall cfg,
or a pre-computed `.dat`) and any device-specific info MAD-X doesn't carry.

Name the file after the study, e.g. `SubLHC_input.yaml`, `FODO_input.yaml`.

## Minimal example

```yaml
name: SubLHC
optics: SubLHC.tfs
grid:
  frequency: {min: 1.0e8, max: 3.0e9, n: 400, log: true}
groups:
  collimators:
    - name: TCP.C6L7.B1        # a MAD-X element name
      source: resonator
      resonators:
        - {term: zlong, Rs: 1.0e4, Q: 1.0, fr: 1.0e9}
```

## Top-level keys

| key | meaning |
|-----|---------|
| `name` | study name; names the output (`<name>_output/`, `<name>_resume.yaml`) |
| `optics` | path to a MAD-X twiss (`.tfs`); elements matched by `NAME` |
| `grid.frequency` / `grid.time` | `{min, max, n, log}` grids (time optional) |
| `groups` | named categories, each a list of elements |
| `additional` | elements already summed/weighted, kept apart from the ring sum |

Paths (`optics`, element `file`) are resolved relative to the config file.
Instead of `optics:` you may inline `twiss: {NAME: [beta_x, beta_y]}` for quick tests.

## Elements

```yaml
- name: TCP.C6L7.B1       # MAD-X name -> position, length, beta come from optics
  category: collimator    # optional label (also the group intent)
  source: resonator       # which engine builds the terms
  info: {material: CFC}    # optional, free-form, device-specific (variable)
  # ... source-specific fields ...
```

Optics resolution, in order: `pre_weighted: true` -> summed as-is (weight 1);
else inline `beta_x`/`beta_y`; else the MAD-X row for `name`. Position and length
always come from MAD-X when available.

### Sources

**`resonator`** - analytic terms:

```yaml
source: resonator
resonators:
  - {term: zlong, Rs: 1.0e4, Q: 1.0, fr: 1.0e9}   # term in
  - {term: zxdip, Rs: 1.0e6, Q: 1.0, fr: 1.0e9}   # zlong/zxdip/zydip/zxquad/zyquad
```

**`cst` / `table`** - import an already-computed `.dat`:

```yaml
source: cst
file: data/TCP_SC_zlong.dat
term: zlong
origin: space_charge_direct   # how it is tagged (res, rw, sc, dsc, cst, ...)
quantity: impedance           # or "wake"
```

*(The `tlwall` engine - a single pytlwall chamber via a `cfg:` reference,
producing resistive-wall and space-charge terms - registers the same way.)*

## What `build` produces (the resume)

`wimba build` writes `<name>_output/` containing per-element files, a `total/`
folder, and `<name>_resume.yaml`. The resume opens with the grids and the list of
components, then the totals, then per element its optics/info and what was
computed:

```yaml
name: SubLHC
grid: {frequency: {min: 1.0e8, max: 3.0e9, n: 400}, time: {min: 0.0, max: 5.0e-9, n: 400}}
components: [ZDipX, ZDipY, ZLong, ZQuadX, ZQuadY]
total:
  ZLong: total/TOT_ZLong.dat
  ZDipX: total/TOT_ZDipX.dat
  # ... WLong, WDipX, ...
groups:
  collimators:
    - name: TCP.C6L7.B1
      optics: {position: 100.0, beta_x: 130.0, beta_y: 85.0}   # position + beta
      info: {length: 0.6, material: CFC, half_gap_mm: 3.0}     # variable per device
      origin: resonator
      impedance:
        ZLong: collimators/TCP.C6L7.B1/TCP.C6L7.B1_res_ZLong.dat
        ZDipX: collimators/TCP.C6L7.B1/TCP.C6L7.B1_res_ZDipX.dat
        # ...
      wake:
        WLong: collimators/TCP.C6L7.B1/TCP.C6L7.B1_res_WLong.dat
        # ...
```

File names read `<Element>_<origin>_<Component>.dat` (e.g. `TCP.C6L7.B1_res_ZLong.dat`,
`TCP.SC.B1_dsc_ZLong.dat`); totals are `TOT_<Component>.dat`. A device usually has
one `origin`; a resistive-wall device that also carries space charge will list
more than one, and the origin tag in each file name keeps them distinct.

See [BUILD.md](BUILD.md) for the commands and how to read/aggregate the output.
