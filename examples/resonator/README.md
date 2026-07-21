# resonator — analytic source, standalone script

The smallest possible example: a few analytic resonators driven directly from
the Python API, no config files and no external engines.

## Files provided

| file | what it is |
|------|------------|
| `resonator_machine.py` | a short script building a machine of analytic resonators (shunt impedance, Q, resonant frequency) and writing impedance/wake tables and figures |

## Run

```bash
python examples/resonator/resonator_machine.py
```

## Outputs

`Z_*.dat`, `W_*.dat`, `impedance.png`, `wake.png` next to the script (generated
artefacts, git-ignored). Useful as a minimal reference for the resonator source
and the table I/O.
