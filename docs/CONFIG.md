<p align="center">
  <img src="../img/wimba_logo_small.png" alt="WIMBA" width="190">
</p>

# Machine config (YAML) reference

> This page is about the YAML that describes **a machine**. WIMBA's own settings
> file — engine paths, logging — is a different thing entirely and lives in
> [SETTINGS.md](SETTINGS.md).

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
| `name` | study name; names the resume (`<name>_resume.yaml`) |
| `output` | optional output dir (relative to the config); see BUILD.md for precedence |
| `optics` | path to a MAD-X twiss (`.tfs`); elements matched by `NAME` |
| `grid.frequency` / `grid.time` | `{min, max, n, log}` grids (time optional) |
| `beam` | the particle and its energy; see below. Required by any source that depends on it |
| `groups` | named categories, each a list of elements |
| `additional` | elements already summed/weighted, kept apart from the ring sum |

Paths (`optics`, element `file`) are resolved relative to the config file.
Instead of `optics:` you may inline `twiss: {NAME: [beta_x, beta_y]}` for quick tests.

Inside a project the grid comes from the project and is shared by every scenario;
see [PROJECTS.md](PROJECTS.md).

## The beam

```yaml
beam:
  particle: proton        # proton | antiproton | electron | positron | lead208
  mode: momentum          # gamma | beta | energy | kinetic | momentum
  momentum: 2.6e+10       # eV/c   (energies in eV; gamma and beta dimensionless)
```

Only one number is free — gamma, beta, total energy, kinetic energy and momentum
are five ways of writing the same degree of freedom — and WIMBA derives the rest.
The mode you write is what is stored, because converting a badly-conditioned
input into a canonical one only hides the problem: at LHC energies beta cannot
say what gamma is, and near rest gamma cannot say what beta is. An input that
does not determine what would be derived from it is refused, with a message
naming the variable to use instead. The rules are in [PROJECTS.md](PROJECTS.md).

**There is no default energy.** A source that needs one and is not given one
stops with an error. WIMBA used to carry `gamma = 7000` as a default in every
signature that took one, which meant a machine that never mentioned an energy was
quietly computed as if it were the LHC at top energy, with nothing in the output
saying so.

A bare top-level `gamma: 7461.0` is the older spelling and still reads, as a
proton beam at that gamma. An element may also carry its own `gamma:`, which wins
for that element.

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
file: data/crab_zlong.dat
term: zlong
origin: cst                   # how it is tagged (res, rw, sc, dsc, cst, ...)
quantity: impedance           # or "wake"
```

**`pytlwall` / `iw2d`** - a chamber computed from its geometry:

```yaml
source: pytlwall
length: 182.4
shape: ELLIPTICAL             # CIRCULAR | ELLIPTICAL | RECTANGULAR
hor_m: 0.073
ver_m: 0.035
radius_m: 0.073
space_charge: true            # indirect space charge kept in its own components
layers:                       # inside -> out
  - {type: CW, material: stainless_steel, thickness: 0.002}
  - {type: V,  thickness: inf}
```

Layers take the full electromagnetic parameter set (`type`, `thickness`, `sigma`
or a known `material`, `muinf_Hz`, `k_Hz`, `epsr`, `tau`, `RQ`). An unknown
material name is an error, never a silent default; declare your own in a
top-level `materials: {name: sigma}` block, which wins over the shipped list
for that study.

The known names live in `wimba/defaults/materials.yaml` — data, not code — and
are the same list the interface offers under Materials. Each entry carries a
note on how firm its conductivity is: grades, tempers and temperature move
these numbers, sometimes by a factor of two.

A chamber may also state `test_beam_shift` — the transverse offset of the test
particle, in metres, which pytlwall uses in the Bessel expansion of the source
field. Only the space-charge terms depend on it; the wall impedance does not.
WIMBA states no default of its own: without the key, pytlwall's own default
applies, and with it the stated value travels through every calculation of that
chamber and is written into the cfg dump. The IW2D path has no equivalent
parameter and never receives it.

Space charge is not imported by hand: it is computed per chamber alongside the
wall and kept as separate components. Import (`cst`) is for genuinely external
data, e.g. a measured or CST-simulated device.

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
`MB.A8L7.B1_rw_ZDipX.dat`); totals are `TOT_<Component>.dat`. A device usually has
one `origin`; a resistive-wall device that also carries space charge will list
more than one, and the origin tag in each file name keeps them distinct.

See [BUILD.md](BUILD.md) for the commands and how to read/aggregate the output.
