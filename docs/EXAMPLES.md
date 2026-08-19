<p align="center"><img src="../img/wimba_logo_small.png" alt="WIMBA" width="190"></p>

# Examples

WIMBA ships five examples, each self-contained in its own folder under
`examples/`. They exercise the two ways of building a model:

- the **assemble / run** flow — start from the optics (a MAD-X twiss) and a set of
  device definitions, let WIMBA place the default resistive wall everywhere else,
  compute, and read out the machine total (`wimba assemble` / `wimba run`);
- the **build** flow — describe the machine as named groups of elements whose
  impedance is computed (resonator) or imported (tabulated data), weighted by the
  optics (`wimba build`).

Each example folder has its own README with the full detail (files
provided, shell and GUI usage, default and optional outputs); this page is the
overview. Most compute paths need **pytlwall** in the environment
(`pip install -e <path to pytlwall>`); the resonator and tabulated-import paths do
not.

| Example | Flow | Needs pytlwall | What it is for |
|---------|------|:---:|----------------|
| [RoundChamber_TLW](#roundchamber_tlw) | run | yes | verify a single chamber (known analytic geometry) |
| [RoundChamber_IW2D](#roundchamber_iw2d) | run | IW2D | the same chamber through the other engine |
| [RoundChamber_TLW_native](#roundchamber_tlw_native) | component bench | yes | the same chamber in pytlwall's own `.cfg` format |
| [RoundChamber_IW2D_native](#roundchamber_iw2d_native) | — | — | the same chamber in IW2D's own input format; not readable yet |
| [LHC](#lhc) | assemble / run | yes | a full realistic machine from real LHC data |
| [SubLHC](#sublhc) | build | no | the group/element build flow end to end |
| [resonator](#resonator) | script | no | the analytic resonator source, standalone |
| [Chimera_Project](#chimera_project) | assemble / run | yes | a project with two scenarios; an invented machine |

---

## RoundChamber_TLW

`examples/RoundChamber_TLW/` — a single-chamber **verification**. A round beam pipe
(CIRCULAR, radius 2 mm, length 1 m, beta = 1, one conducting layer of
sigma = 2e5 S/m, gamma = 479.605) defined inline in the config with a `chamber`
source, so the whole model is one chamber with a known geometry.

```bash
wimba run examples/RoundChamber_TLW/RoundChamber_TLW_config.yaml --wake
```

Produces, under `RoundChamber_TLW_output/`, `single_elements/total.csv` (and the same
chamber under `single_elements/round_chamber/…`), the impedance plots
`total_ZLong.png`, `total_ZDipX.png`, `total_ZDipY.png` and, with `--wake`, the
wake plots `total_W*.png`.

Because beta = 1 and length = 1, WIMBA's numbers here are exactly pytlwall's
`get_all_impedances` / `TLWallWake` for that chamber — a direct check of the
bridge against a single, well-defined geometry. Run this first when you want to
confirm the values are right before trusting a full machine.

## RoundChamber_TLW_native

`examples/RoundChamber_TLW_native/` — the RoundChamber wall written as a **pytlwall
chamber `.cfg`** rather than a WIMBA config. Same numbers, other format.

It is here because the two are opened by different menu entries, and that is
the commonest first mistake: `RoundChamber.cfg` goes through **Component →
Load pytlwall Config…**, while a WIMBA config goes through **File → Open
Config**.

WIMBA reads geometry, layers, betas, length, gamma and the frequency range, but
**rebuilds** the grid: it lays one logarithmic grid across the range, where
pytlwall restarts the count in each decade. Same span, different points, so two
output files never line up row by row — see
[PYTLWALL_CFG.md](PYTLWALL_CFG.md).

## RoundChamber_IW2D

`examples/RoundChamber_IW2D/` — the same chamber with `method: iw2d`.

```bash
wimba run examples/RoundChamber_IW2D/RoundChamber_IW2D_config.yaml
```

Two independent codes on the same input should give the same answer; running
this beside RoundChamber is the cheapest check that they do. It is a WIMBA
config, so in the interface it opens with **File → Open Config** —
`Component → Load IW2D Config…` reads IW2D's own input format and is not
implemented yet. IW2D covers circular chambers in WIMBA today; the two
conventions that differ from pytlwall are in [IW2D.md](IW2D.md).

## RoundChamber_IW2D_native

`examples/RoundChamber_IW2D_native/` — the same wall in IW2D's own input
format. **WIMBA cannot read it yet**: `Component → Load IW2D Config…` says so
rather than guessing at the format. The file is here as the sample that reader
will be written and tested against, and as a record of the wall all four
examples share.

Its README carries what a reader will have to decide — the Yokoya factors, the
frequency *scan* that WIMBA can only rebuild as a grid, and the flat-chamber
keys WIMBA's single layer stack has no place for — plus the unit conversions,
taken from IW2D's own legacy reader.

## LHC

`examples/LHC/` — a **full, realistic machine** assembled from the real pywit LHC
model: the MAD-X twiss (whole lattice), the collimator reference (JSON) and the
RF-cavity HOMs (JSON).

```bash
# the assignment array only (positions, names, method, beta, collisions)
wimba assemble examples/LHC/LHC_config.yaml         # -> LHCB1_assignments.csv

# assemble + compute + machine total + default plots (+ wake)
wimba run examples/LHC/LHC_config.yaml --wake
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
wimba build examples/SubLHC/SubLHC_config.yaml       # -> SubLHC_output/
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
wimba build examples/resonator/resonator_input.yaml
```

It writes `Z_*.dat`, `W_*.dat`, `impedance.png` and `wake.png` next to the script
(these are generated artefacts and are git-ignored).

## Chimera_Project

`examples/Chimera_Project/` — a **project with two scenarios**, and the only
example that is not a machine: CHIMERA does not exist. The lattice, the chamber
dimensions, the materials, the cavity modes and the kicker "CST export" are all
invented, so the whole pipeline can be exercised without waiting for real machine
data. **Do not quote a number out of it.**

Open it with *File → Open Project* and pick the folder, or from the shell:

```bash
wimba run examples/Chimera_Project/injection_config.yaml  --out injection/output
wimba run examples/Chimera_Project/extraction_config.yaml --out extraction/output
```

What it puts through its paces:

| piece | exercises |
|---|---|
| 24-cell FODO twiss, 300 m | beta resolution by position |
| elliptical default pipe, three layers, from JSON | 168 uncovered rows collapsing to one solve |
| two rectangular collimators, three layers, invented materials | named chambers, the `materials:` block |
| a kicker as five pre-weighted `.dat` files | the precalculated source |
| an RF cavity from JSON | the resonator source |
| injection γ = 2.279 vs extraction γ = 21.34 | two scenarios on one grid |

The devices sit at 40.1, 45.6, 152.3 and 226.7 m — deliberately **not** on cell
boundaries. Placed on a multiple of the 12.5 m cell they would share a position
with a quadrupole, and the beta interpolation would take the quadrupole's row: no
error, no collision, just quietly wrong numbers. Worth knowing if you build a
lattice by hand.
