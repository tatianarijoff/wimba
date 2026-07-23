# Precalculated elements — importing tabulated impedance / wake data

A **precalculated** element takes its impedance (and optionally its wake) from
files you already have — CST or Wake2D exports, results from another code, a
colleague's tables. WIMBA imports the data, interpolates it onto the run grid,
and sums it into the machine like any other element.

Semantics: the data are taken **as-is for the whole element** — no length
scaling. If the element is *plain* (not `weighted`), WIMBA applies the local
beta to the transverse components; `weighted: true` means the data already
include it.

## Pointing at the data

Two ways, per device:

**1. Simple files** — one plain table per component (`f  Re  Im`, whitespace
separated, frequency in Hz):

```yaml
devices:
  kicker:
    source: precalculated
    name: KICKER
    files:
      ZLong: data/kicker_zlong.dat
      ZDipX: data/kicker_zdipx.dat
    wake_files: {}                # optional, same idea (t  W)
    weighted: true
```

**2. An import map** — a small YAML descriptor next to the data, for everything
the simple form cannot say: files with headers and comments, tab or custom
separators, frequency in GHz, several components in one file with arbitrary
column order, complex-number columns, per-component files:

```yaml
devices:
  kicker:
    source: precalculated
    name: KICKER
    map: data/kicker_map.yaml
    weighted: true
```

## The import map (`map:`) reference

**Columns are numbered from 1**, as you read the file. Everything in a
`common_*` block is the default; each component entry overrides only what
differs.

```yaml
# columns are numbered from 1
common_impedance:
  file: ZlongReIM_FCCkicker_shielded1micron.txt
  comment: "#"            # skip lines starting with this (default "#")
  skip_rows: 0            # additionally skip the first N lines
  sep: tab                # tab | any literal string | omit = any whitespace
  freq_unit: GHz          # Hz (default) | kHz | MHz | GHz | THz
  z_scale: 1.0            # optional multiplier (unit or sign-convention fixes)
  format: re_im           # re_im (two columns) | complex (one column)
  columns: {freq: 1, re: 2, im: 3}

components:
  ZLong: {}                                        # inherits everything
  # ZDipX: {file: other.dat, columns: {freq: 1, re: 4, im: 5}}
  # ZQuadX: {file: zq.dat, format: complex, columns: {freq: 1, z: 2}}

common_wake:              # same idea for wakes
  time_unit: ns           # s (default) | ms | us | ns | ps
  w_scale: 1.0
  columns: {time: 1, w: 2}
wake_components: {}
  # WLong: {file: wlong.dat}
```

Notes:
- `format: complex` accepts `1.2e3+4.5e2j`, `1.2e3+4.5e2i` and `(1.2e3,4.5e2)`.
- The example above reads a real CST export (tab-separated, `#` headers,
  frequency in **GHz** — forgetting `freq_unit` would shift everything by 10^9).
- Unknown columns or formats raise a clear error, never a silent guess.

## Wake provenance

If the map defines `wake_components` (or the device has `wake_files`), the wake
is imported. Otherwise, when a wake is requested, WIMBA computes it as the
**Fourier transform of the imported impedance** and records that in
`<output>/single_elements/WAKE_NOTES.txt` — you always know where a wake came
from.

## Running from the shell

```bash
wimba run my_config.yaml            # impedance
wimba run my_config.yaml --wake     # + wake (imported or FFT, see the notes file)
```

Add the device name to `output:` in the config to get its own CSV under
`single_elements/<group>/<name>.csv` (and its own entry in the GUI Results
tree).

## Using it from the GUI

- **Open Config** on a config containing precalculated devices: they are
  computed with `Calculate → Calculate Whole Machine` like everything else.
- **Compare on a single element** (the quickest way to check imported data
  against a computation): open an element, tab **Models → Additional
  calculations — compare → + Add**, choose the component (e.g. `ZLong`), method
  `precalculated`, and as *Source / File* either a plain `.dat` or an import-map
  `.yaml`. `Calculate element` computes the base method and the imported data
  side by side; drag both curves from the Results tree into one plot.
- Using `precalculated` as the *base* method of a GUI-edited element arrives
  with the machine→config bridge (today the base method is pytlwall).
