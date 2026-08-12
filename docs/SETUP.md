<p align="center">
  <img src="../img/wimba_logo_small.png" alt="WIMBA" width="190">
</p>

# Setup & quick start

## In a hurry

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest
```

That is everything you need for the core, the analytic resonator and the Fourier
tools. External engines are only required for resistive-wall sources — if you
don't use them, you are already done.

## What comes with the package, and what does not

| | |
|---|---|
| always installed | `numpy`, `PyYAML`, `matplotlib` |
| `[dev]` | `pytest`, `xwakes` — the test suite and the resonator cross-checks |
| `[gui]` | `PyQt6` — the desktop interface |
| `[spreadsheets]` | `pandas`, `openpyxl` — importing tables from `.xlsx`/`.xls` |
| not a dependency | **pytlwall** and **IW2D**: WIMBA locates them, see below |

matplotlib is not an extra because `wimba run` and `wimba plot` write figures,
and those are core commands. The two engines are deliberately not dependencies:
neither is on PyPI in the form WIMBA uses, and a study that only combines
resonators and imported tables needs neither.

For the engines, run once:

```bash
wimba setup     # locate IW2D / pytlwall, write the config
wimba status    # show what was found
```

## `wimba setup`

Locates the tools and records where they are. It does **not** bundle or compile
them. Run it once; edit the config by hand later if a path changes.

- **IW2D** — a Python package over a C++ core, installed into the same
  environment as WIMBA and pytlwall:
  `pip install cppyy && pip install -e <path to IW2D>`, after the GSL, GMP,
  MPFR and Arb system libraries. Nothing needs configuring here: WIMBA imports
  it rather than executing a binary. See [IW2D.md](IW2D.md), which also covers
  the `IW2D_FLINT_ARB` variable needed on Debian and Ubuntu.
- **pytlwall** — a Python package. If it imports, nothing to do. For a local
  checkout instead of a pip install: `wimba setup --pytlwall-path <path to pytlwall>`.

Neither engine needs `wimba setup` when it is pip-installed. The command is for
recording the path of a checkout that is not.

CI / scripts: add `--non-interactive` to never prompt.

## The settings file

Full reference: **[SETTINGS.md](SETTINGS.md)**. In short, WIMBA reads the nearest
`wimba.yaml` walking up from the working directory, so one at the top of your
working copy covers everything you run inside it:

```bash
wimba config --init     # write a commented starter here
wimba config            # which file is in use, and what it resolves to
```

```yaml
tools:
  pytlwall:
    path: <folder containing the pytlwall package>   # only if not pip-installed
  iw2d:
    path: <folder containing the IW2D package>       # only if not pip-installed
```

Both keys give the folder that *contains* the package, not a binary: WIMBA
imports both engines. A `binary:` key under `iw2d` is still read, from the older
file-based path, but nothing in the current bridge uses it.

A fresh install with no settings file anywhere gets one written at
`~/.config/wimba/config.yaml` on first use.

## How a tool is resolved

Highest priority first:

1. an explicit argument in code,
2. an environment variable (`WIMBA_PYTLWALL_PATH`, `WIMBA_IW2D_PATH`),
3. the settings file above,
4. otherwise a clear error telling you how to install it.

## Installing the engines

- **pytlwall** — `pip install git+https://github.com/tatianarijoff/pytlwall`,
  or use a checkout with `--pytlwall-path`.
- **IW2D** — for the Python API, `pip install <path to IW2D>` after installing
  GSL, MPFR, Arb and cppyy; see [IW2D.md](IW2D.md). The `.x` executables are
  compiled separately and are only needed for the legacy file-based path.

## Default compute method

New GUI elements and config devices without an explicit `method:` use the
configured default (pytlwall if unset). To change it, add to the settings file:

```yaml
default_method: IW2D        # pytlwall | IW2D (case-insensitive)
```

The analytic resonator is not offered as a wall default: it models known
resonant modes (Rs, Q, fr), it does not compute a chamber wall from geometry -
a resonator default on a chamber element would silently compute the wrong
physics. When the chosen engine is not installed, WIMBA stops with a clear
error telling you how to install it.
