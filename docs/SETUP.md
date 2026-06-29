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

- **IW2D** — an external binary. `setup` looks on your `PATH`, or asks for the
  path. Non-interactive: `wimba setup --iw2d /path/to/IW2D`.
- **pytlwall** — a Python package. If it imports, nothing to do. For a local
  checkout instead of a pip install: `wimba setup --pytlwall-path /path/to/TLWallNew`.

CI / scripts: add `--non-interactive` to never prompt.

## The config file

Location: `$WIMBA_CONFIG`, else `$XDG_CONFIG_HOME/wimba/config.yaml`, else
`~/.config/wimba/config.yaml`.

```yaml
tools:
  iw2d:
    binary: /opt/iw2d/bin/IW2D
  pytlwall:
    path: /home/me/CERN/TLWallNew   # only if not pip-installed
```

## How a tool is resolved

Highest priority first:

1. an explicit argument in code,
2. an environment variable (`WIMBA_IW2D_BINARY`, `WIMBA_PYTLWALL_PATH`),
3. the config file above,
4. otherwise a clear error telling you to run `wimba setup`.

## Installing the engines

- **pytlwall** — `pip install git+https://github.com/tatianarijoff/TLWallNew`,
  or use a checkout with `--pytlwall-path`.
- **IW2D** — compiled separately (C++); point `wimba setup` at the resulting
  binary. See the IW2D project for build instructions.
