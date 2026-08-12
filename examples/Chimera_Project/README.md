# CHIMERA — an accelerator that does not exist

Everything here is invented: the lattice, the chamber dimensions, the materials,
the cavity modes, the kicker "CST export". The point is to exercise the whole
WIMBA machinery end to end without waiting for anyone to send real machine data.

**Do not quote a number out of this project.** CHIMERA is not a machine, and the
name is deliberately unmistakable so nobody mistakes it for one.

## What it contains, and what each piece exercises

| piece | what it is | exercises |
|---|---|---|
| `chimera.tfs` | 24-cell FODO ring, 300 m, β between 8 and 30 m | optics by position |
| `default_pipe` | elliptical 45 × 28 mm, coating + steel + vacuum | the 166 uncovered rows collapsing to one solve |
| `COLL.H` | rectangular, 8 mm half-gap, invented alloy + copper | named chamber, 3 layers, user material |
| `COLL.V` | rectangular, 6 mm half-gap, graphite + copper | a second geometry, so the cache has to tell them apart |
| `KICK.EXT` | five synthetic "CST" files, already β-weighted | the precalculated source, `weighted: true` |
| `RFCAV` | three HOM modes from JSON | the resonator source |
| two scenarios | γ = 2.279 and γ = 21.34 | one grid, two energies |

The two collimators use **invented materials** (`chimeranium`, `ferrite_x9`)
declared in the `materials:` block, because WIMBA treats an unknown material as
an error rather than defaulting silently — worth seeing that path work.

## The scenarios

| | γ | β | 1/γ² |
|---|---|---|---|
| injection, 1.2 GeV kinetic | 2.27895 | 0.898585 | 0.1925 |
| extraction, 20 GeV/c | 21.3392 | 0.998901 | 0.0022 |

Both collimators have `space_charge: true`, and 1/γ² moves by a factor 87
between the two, so the ISC columns should separate clearly while the wall terms
move much less. That is the comparison the scenarios exist for.

## What was checked here, and what was not

Assembled, both scenarios: **172 rows — 4 devices and 168 default-pipe rows, no
collisions**, betas interpolated from the twiss:

    COLL.H     s=  40.1  βx=21.87  βy=16.13   interp
    COLL.V     s=  45.6  βx=12.42  βy=25.58   interp
    KICK.EXT   s= 152.3  βx=23.43  βy=14.57   interp
    RFCAV      s= 226.7  βx=26.22  βy=11.78   by name

Computed for real, through the full run pipeline: the kicker and the RF cavity,
with the chambers removed (no pytlwall in the environment that wrote this). Both
produced all five components, the total came out over 200 frequency points, and
the per-device CSVs were written. So the precalculated and resonator paths are
known to work on this data.

**Not computed here:** the two collimators and the default pipe, which need
pytlwall. That is the first thing to try.

## Running it

GUI: *File → Open Project*, pick a scenario, *Calculate → Whole Machine*.
Results go to `<scenario>/output/`.

CLI:

    wimba run injection_config.yaml  --out injection/output
    wimba run extraction_config.yaml --out extraction/output

Add `--wake` for the time domain; the grid already carries a time range.

## A note on the lattice

The devices sit at 40.1, 45.6, 152.3 and 226.7 m — deliberately **not** on cell
boundaries. The first draft put them at 40, 45, 150 and 225, which are multiples
of the 12.5 m cell, so each device shared its position with a quadrupole and the
beta interpolation picked the quadrupole's row instead. Nothing was broken, but
the numbers were quietly wrong. If you build your own lattice by hand, that is
the trap.
