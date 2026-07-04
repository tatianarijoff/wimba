<p align="center"><img src="../img/wimba_logo_small.png" alt="WIMBA" width="190"></p>

# Examples

WIMBA ships four examples, each self-contained in its own folder under
`examples/`. They exercise the two ways of building a model:

- the **assemble / run** flow — start from the optics (a MAD-X twiss) and a set of
  device definitions, let WIMBA place the default resistive wall everywhere else,
  compute, and read out the machine total (`wimba assemble` / `wimba run`);
- the **build** flow — describe the machine as named groups of elements whose
  impedance is computed (resonator) or imported (tabulated data), weighted by the
  optics (`wimba build`).

Most compute paths need **pytlwall** in the environment
(`pip install -e /path/to/TLWallNew`); the resonator and tabulated-import paths do
not.

| Example | Flow | Needs pytlwall | What it is for |
|---------|------|:---:|----------------|
| [RoundChamber](#roundchamber) | run | yes | verify a single chamber (known analytic geometry) |
| [LHC](#lhc) | assemble / run | yes | a full realistic machine from real LHC data |
| [SubLHC](#sublhc) | build | no | the group/element build flow end to end |
| [resonator](#resonator) | script | no | the analytic resonator source, standalone |

---

## RoundChamber

`examples/RoundChamber/` — a single-chamber **verification**. A round beam pipe
(CIRCULAR, radius 2 mm, length 1 m, beta = 1, one conducting layer of
sigma = 2e5 S/m, gamma = 479.605) defined inline in the config with a `chamber`
source, so the whole model is one chamber with a known geometry.

```bash
wimba run examples/RoundChamber/RoundChamber_input.yaml --wake
```

Produces, under `RoundChamber_output/`, `single_elements/total.csv` (and the same
chamber under `single_elements/round_chamber/…`), the impedance plots
`total_ZLong.png`, `total_ZDipX.png`, `total_ZDipY.png` and, with `--wake`, the
wake plots `total_W*.png`.

Because beta = 1 and length = 1, WIMBA's numbers here are exactly pytlwall's
`get_all_impedances` / `TLWallWake` for that chamber — a direct check of the
bridge against a single, well-defined geometry. Run this first when you want to
confirm the values are right before trusting a full machine.

## LHC

`examples/LHC/` — a **full, realistic machine** assembled from the real pywit LHC
model: the MAD-X twiss (whole lattice), the collimator reference (JSON) and the
RF-cavity HOMs (JSON).

```bash
# the assignment array only (positions, names, method, beta, collisions)
wimba assemble examples/LHC/LHC_input.yaml         # -> LHCB1_assignments.csv

# assemble + compute + machine total + default plots (+ wake)
wimba run examples/LHC/LHC_input.yaml --wake
```

`run` resolves beta by position (interpolated) then by name, puts the default
resistive wall on every uncovered lattice row, computes with pytlwall (one
calculation per distinct geometry — the ~11k pipe segments share one, so it runs
in a few seconds), and writes `LHCB1_output/single_elements/total.csv`, the one
device listed under `output:` in the config, and the plots.

Notes:
- The twiss `data/twiss_lhcb1_beta130cm.tfs` is ~5 MB and is **not** in the repo;
  copy it from the pywit model into `examples/LHC/data/` before running.
- The RF-cavity HOMs (`resonator` method) are now computed and enter the total,
  as lumped contributions (weighted by beta, not by length). The remaining methods
  not yet wired into `run` are `iw2d` and `precalculated`; rows with those are
  reported as skipped in the run summary.

Full explanation of the config, beta resolution, default-pipe caching and output
layout: [ASSEMBLE_AND_RUN.md](ASSEMBLE_AND_RUN.md).

## SubLHC

`examples/SubLHC/` — a small, self-contained machine that exercises the **build**
flow: named groups of elements whose impedance is analytic (resonator) or imported
from tabulated data, weighted by a small synthetic twiss (`SubLHC.tfs`, kept in the
repo).

```bash
wimba build examples/SubLHC/SubLHC_input.yaml       # -> SubLHC_output/
wimba show  examples/SubLHC/SubLHC_output           # summarise the result
```

`build` materialises the machine into `SubLHC_output/`: per-origin impedance/wake
tables plus a `SubLHC_resume.yaml`. No external engine is required (resonator +
tabulated import), so this one runs anywhere. See [BUILD.md](BUILD.md) and
[CONFIG.md](CONFIG.md) for the config format.

## resonator

`examples/resonator/resonator_machine.py` — a short **script** (not a config) that
builds a machine of analytic resonators directly through the Python API and writes
impedance/wake tables and figures. Useful as a minimal, dependency-free reference
for the resonator source.

```bash
python examples/resonator/resonator_machine.py
```

It writes `Z_*.dat`, `W_*.dat`, `impedance.png` and `wake.png` next to the script
(these are generated artefacts and are git-ignored).
