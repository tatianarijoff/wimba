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
  the `IW2D_FLINT_ARB` variable needed on Debian and Ubuntu. The `--iw2d`
  option and the `iw2d.binary` setting below configure the *command-line
  executables*, used only by the legacy file-based path.
- **pytlwall** — a Python package. If it imports, nothing to do. For a local
  checkout instead of a pip install: `wimba setup --pytlwall-path <path to pytlwall>`.

CI / scripts: add `--non-interactive` to never prompt.

## The config file

Location: `$WIMBA_CONFIG`, else `$XDG_CONFIG_HOME/wimba/config.yaml`, else
`~/.config/wimba/config.yaml`.

```yaml
tools:
  iw2d:
    binary: <path to IW2D>
  pytlwall:
    path: <path to pytlwall>        # only if not pip-installed
```

## How a tool is resolved

Highest priority first:

1. an explicit argument in code,
2. an environment variable (`WIMBA_IW2D_BINARY`, `WIMBA_PYTLWALL_PATH`),
3. the config file above,
4. otherwise a clear error telling you to run `wimba setup`.

## Installing the engines

- **pytlwall** — `pip install git+https://github.com/tatianarijoff/pytlwall`,
  or use a checkout with `--pytlwall-path`.
- **IW2D** — for the Python API, `pip install <path to IW2D>` after installing
  GSL, MPFR, Arb and cppyy; see [IW2D.md](IW2D.md). The `.x` executables are
  compiled separately and are only needed for the legacy file-based path.

## Default compute method

New GUI elements and config devices without an explicit `method:` use the
configured default (pytlwall if unset). To change it, add to the WIMBA config
file (`~/.config/wimba/config.yaml`, or `$WIMBA_CONFIG`):

```yaml
default_method: IW2D        # pytlwall | IW2D (case-insensitive)
```

The analytic resonator is not offered as a wall default: it models known
resonant modes (Rs, Q, fr), it does not compute a chamber wall from geometry -
a resonator default on a chamber element would silently compute the wrong
physics. When the chosen engine is not installed, WIMBA stops with a clear
error telling you how to install it.
