# External data files

Most of what WIMBA needs lives in the repository. A few files do not, because
they are too large to version sensibly: real accelerator optics tables run to
several megabytes and would stay in the git history forever.

This page lists those files, where to get them, and where to put them.

## What is missing from a fresh clone

| File | Size | Needed by |
|------|------|-----------|
| `examples/LHC/data/twiss_lhcb1_beta130cm.tfs` | 5.4 MB | the `examples/LHC` study |

Everything else — including the small optics tables used by the other examples
(`examples/SubLHC/SubLHC.tfs`, `examples/resonator/resonator.tfs`) — is
tracked and arrives with the clone.

The exclusion is deliberate; see `examples/LHC/data/*.tfs` in `.gitignore`.

> **The LHC example does not run on a fresh clone.**
> Without the twiss file, loading `examples/LHC/LHC_config.yaml` fails with
> `FileNotFoundError`. Download the file as described below, or start from
> `examples/SubLHC`, which is self-contained and exercises the same pipeline on
> a reduced lattice.

## Getting the LHC optics

Download `twiss_lhcb1_beta130cm.tfs` from the repository releases and place it
under `examples/LHC/data/`:

```bash
mkdir -p examples/LHC/data
cd examples/LHC/data
curl -LO https://github.com/tatianarijoff/wimba/releases/download/<TAG>/twiss_lhcb1_beta130cm.tfs
```

Replace `<TAG>` with the release that carries the data assets. The file is also
downloadable from the Releases page in a browser.

### Pointing a study at optics you already have

If the optics tables are already on your machine — in a shared group folder, an
`acc-models` checkout, a scratch disk — you do not need a second copy. Add a
`data_dir:` key to the study config:

```yaml
name: LHC
data_dir: ~/CERN/optics          # absolute, or relative to this file
optics: data/twiss_lhcb1_beta130cm.tfs
```

The key accepts a list as well, searched in order:

```yaml
data_dir:
  - ../shared_optics
  - /afs/cern.ch/group/optics
```

This is the normal way to do it: the location of a study's data stays with the
study, so two studies can sit on different disks and neither needs anything set
up in the shell.

Inside each directory the file is looked up twice: first under the path exactly
as the study config writes it (`data/twiss_lhcb1_beta130cm.tfs`), then by file
name alone (`twiss_lhcb1_beta130cm.tfs`). The second form is what usually
matches a shared folder, whose layout will not mirror the examples.

Full resolution order:

1. the reference itself, when it is an absolute path
2. `$WIMBA_DATA_DIR` — a per-invocation override, for a one-off run or CI
3. the study's `data_dir:` key
4. `data.dir` in the WIMBA config file — a machine-wide default
5. the reference relative to the directory holding the study config

Steps 2 to 4 follow the usual precedence, explicit then environment then
config, as with `WIMBA_IW2D_BINARY` and `WIMBA_PYTLWALL_PATH`. The environment
variable exists for overriding a run without editing files; for everyday use
prefer the `data_dir:` key.

A machine-wide default, if you want one:

```yaml
data:
  dir: /path/to/your/optics
```

When nothing matches, the error names every location searched and how to fix it:

```
optics table 'data/twiss_lhcb1_beta130cm.tfs' was not found. Looked in:
    /home/me/CERN/impedance/wimba/examples/LHC/data/twiss_lhcb1_beta130cm.tfs
Point the study at the data by adding a 'data_dir:' key to its config file
(one path or a list, absolute or relative to the config), or set
$WIMBA_DATA_DIR for a one-off override.
Large data files are distributed separately; see docs/DATA.md.
```

## What the LHC file is

MAD-X twiss table for **LHC beam 1** at **β\* = 130 cm**.

| Header key | Value |
|------------|-------|
| `SEQUENCE` | `LHCB1` |
| `PARTICLE` | `PROTON` |
| `ENERGY` | 6800 GeV |
| `GAMMA` | 7247.36468856827 |
| `LENGTH` | 26658.8831999989 m |
| `Q1` | 62.3099997974624 |
| `Q2` | 60.3200000468117 |
| data rows | 13355 |

These values are the file's fingerprint. If a calculation ever disagrees with a
published result, check them first: a different optics file will differ here
before it differs anywhere else.

### Provenance

The file comes from the `data/optics/` directory of the **`lhc_pywit_model`**
example, distributed with the original **PyWIT** repository. Two companion
tables — `twiss_lhcb2_beta130cm.tfs` and `twiss_hllhcb1_beta100cm.tfs` — are
part of the same set and can be used the same way.

Note that **`xwakes`, the package that superseded PyWIT, does not ship the LHC
model or any optics table**. Installing `xwakes` will not give you this file,
which is why WIMBA distributes it as a release asset rather than pointing
upstream.

## Adding new external data

If a study needs a file too large to track:

1. add the pattern to `.gitignore`, scoped to that study's `data/` directory;
2. attach the file to a release;
3. add a row to the table at the top of this page, with its fingerprint and
   provenance;
4. note the requirement in the example's own `README.md`.

The rule of thumb: a reader must be able to tell **which** file a result was
produced with, not merely obtain **a** file of the right name.
