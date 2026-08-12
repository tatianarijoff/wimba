<p align="center"><img src="../img/wimba_logo_small.png" alt="WIMBA" width="190"></p>

# WIMBA settings (`wimba.yaml`)

There are two kinds of YAML in WIMBA and it is worth separating them clearly:

| file | says | reference |
|------|------|-----------|
| a **machine config** | what the machine is: optics, elements, grid, beam | [CONFIG.md](CONFIG.md), [ASSEMBLE_AND_RUN.md](ASSEMBLE_AND_RUN.md) |
| the **settings file** | how WIMBA runs on *this* computer: where the engines are, where the log goes | this page |

The settings file travels with your machine, not with your study. Nothing in it
changes a result.

## Where it is

Highest priority first:

1. `$WIMBA_CONFIG`, if set;
2. the nearest **`wimba.yaml`** found walking up from the working directory;
3. `$XDG_CONFIG_HOME/wimba/config.yaml`, else `~/.config/wimba/config.yaml`.

Point 2 is the useful one: put a `wimba.yaml` at the top of your working copy and
everything you run from inside it uses that file — easier to find and edit than
something hidden under `~/.config`.

A fresh install with no settings file anywhere gets one written for it at
`~/.config/wimba/config.yaml` on first use, from the commented default that ships
with the package. An existing file is never overwritten.

```bash
wimba config              # which file is in use, where it came from, what it says
wimba config --init       # write a commented wimba.yaml in the current folder
wimba config --init DIR   # ... or in DIR
```

In a clone, `wimba.example.yaml` at the repository root is the same starter, kept
under version control. Copy it rather than editing it:

```bash
cp wimba.example.yaml wimba.yaml
```

`wimba.yaml` and `wimba.yml` are git-ignored on purpose. Machine-specific paths
must not travel with the repository: they would be wrong on every other machine
and would leave the working tree permanently dirty.

## What it contains

```yaml
tools:
  pytlwall:
    # path: ~/CERN/impedance/pytlwall
  iw2d:
    # path: ~/CERN/impedance/IW2D

# data_dir: ~/CERN/impedance/externalData

logging:
  level: info
  to_file: true
  # dir: ./logs
  file: wimba.log
```

### `tools`

Both engines are **Python packages**. If `pip show pytlwall` (or `pip show IW2D`)
already finds them in the environment WIMBA runs in, there is nothing to
configure and both keys stay commented out.

`path:` is for a checkout that was never pip-installed: give the folder that
*contains* the package directory, and WIMBA puts it on `sys.path` before
importing.

> IW2D is imported, not executed. The bridge has used its Python API since the
> July rewrite and does not call the compiled `.x` binaries. A `binary:` key is
> still read, from the older file-based path; nothing current uses it.

`wimba status` says which build of each engine will answer, and how it was found
— worth checking when two checkouts of pytlwall are installed side by side, since
a number is only interpretable once you know which one produced it.

### `data_dir`

Where to look for large data files that a study config refers to by name — MAD-X
tables, imported `.dat`. One path or a list. A study can override it with its own
`data_dir:` key, which is usually the better place; see [DATA.md](DATA.md) for
the full resolution order.

### `logging`

| key | meaning |
|-----|---------|
| `level` | console verbosity: `critical`, `error`, `warning`, `info`, `debug` |
| `to_file` | keep a rotating file log (2 MB × 3). Default: yes |
| `dir` | where it goes. Default `$XDG_STATE_HOME/wimba`, usually `~/.local/state/wimba` |
| `file` | the file name |

The file log is **always written at debug level**, whatever the console shows:
the console is for the session, the file is for working out afterwards what
happened.

A relative `dir` resolves against the settings file's own folder, not the working
directory — `dir: ./logs` means that working copy, wherever you happen to run
from. Remember to git-ignore it.

## The environment always wins

| setting | variable |
|---------|----------|
| pytlwall checkout | `WIMBA_PYTLWALL_PATH` |
| IW2D checkout | `WIMBA_IW2D_PATH` |
| data directory | `WIMBA_DATA_DIR` |
| log level | `WIMBA_LOG_LEVEL` |
| log directory | `WIMBA_LOG_DIR` |
| file logging on/off | `WIMBA_LOG_TO_FILE` |

Explicit argument, then environment, then file — the same order everywhere. A
one-off debug run needs no edit:

```bash
WIMBA_LOG_LEVEL=debug wimba run my_config.yaml
```

## Default compute method

```yaml
default_method: IW2D        # pytlwall | IW2D (case-insensitive)
```

Used by new GUI elements and by config devices with no explicit `method:`. The
analytic resonator is not offered here: it models known resonant modes, it does
not compute a wall from geometry, so a resonator default on a chamber would
silently compute the wrong physics.

## See also

- [SETUP.md](SETUP.md) — installing the engines
- [IW2D.md](IW2D.md) — the shared libraries IW2D needs, and `IW2D_FLINT_ARB`
- [DATA.md](DATA.md) — external data files and how they are found
