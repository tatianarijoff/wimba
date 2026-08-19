# RoundChamber_IW2D_native — single-chamber verification, from an IW2D input file

One round beam pipe with a fully known geometry, written as an IW2D input
file. It exercises the route that reads IW2D's own format: WIMBA converts the
units, builds a component from the file, and computes it with IW2D.

The wall: CIRCULAR, radius 2 mm, length 1 m, DC resistivity 5e-06 Ohm.m
(sigma = 2e5 S/m), relaxation time 4.2 ps, epsilon_r = 1, magnetic
susceptibility 0, the layer extending to infinity, gamma = 479.605064966.

## Files provided

| file | what it is |
|------|------------|
| `RoundChamber_IW2D_input.txt` | an IW2D round-chamber input file, in the tab-separated format of IW2D's own `examples/input_files/`. Written here rather than copied from the IW2D distribution, with the frequency range set to 1e3 – 1e11 Hz to match the other three examples |

## Load it

`Component → Load IW2D Config…` → `RoundChamber_IW2D_input.txt`, then
`Calculate with IW2D`.

WIMBA does not *compute* through this format — it drives IW2D's Python API
either way. The file is how an IW2D case is written down and passed around, so
being able to open one is what matters. To state the same wall as a WIMBA
config instead, use `RoundChamber_IW2D`.

## Editing it by hand

The format admits **no comments**. IW2D's reader splits every non-blank line on
a tab and raises if there is none, and its documentation asks that the
description text of each parameter be kept identical. A line starting with `#`
or `;` is a parse error, not a comment. Change only what follows the tab.

## Units

The file is not in SI. WIMBA takes these conversions from IW2D's own legacy
reader (`IW2D/legacy/roundchamber.py`) rather than from prose:

| in the file | to SI |
|-------------|-------|
| inner radius, thickness [mm] | × 1e-3 |
| relaxation time [ps] | × 1e-12 |
| relaxation frequency of permeability [MHz] | × 1e6 |
| DC resistivity [Ohm.m] | sigma = 1/rho |
| magnetic susceptibility | WIMBA's `muinf_Hz`, unchanged |

The radii are **cumulative**: layer *n*'s inner radius is the first inner radius
plus the thicknesses of the layers inside it. And infinite resistivity is how
the format writes vacuum, which becomes a layer of type `V`.

## What the reader does with the rest

The file carries things a WIMBA element has no place for. Dropping them in
silence would produce a faithful-looking translation of something else, so each
is either kept, reported or refused:

- **Yokoya factors** — `1 1 1 0 0` here, the circular case, meaning no
  rescaling. Any other value describes a different shape through an equivalent
  round chamber: WIMBA keeps them as `iw2d_yokoya`, uses them on the IW2D path
  only, and says so in the console.
- **The frequency scan** — start and stop exponents, linear/logarithmic/both,
  points per decade, and a refinement window. WIMBA holds a grid, not a scan,
  so it rebuilds a logarithmic grid over the same range and reports when the
  file asked for something else. Two codes' output files therefore never line
  up row by row.
- **Wake sampling, the machine name, the output comment** — run control and
  file naming, not physics. Reported, then ignored.
- **Flat-chamber keys** — a flat input adds top/bottom symmetry, a half gap and
  a second layer stack. A WIMBA element has one stack, so such a file is
  refused by name rather than read as if it were round.

## About the wake

IW2D computes wakes with a Filon-type method in its C++ executables, but the
Python package WIMBA drives does not: `wake_roundchamber` and
`wake_flatchamber` are stubs. A wake for an IW2D component is therefore WIMBA's
Fourier transform of the impedance, and the interface says so wherever it
offers one.

## Where this one sits

| folder | what it holds | how it gets in |
|--------|---------------|----------------|
| `RoundChamber_TLW` | WIMBA config, `method: pytlwall` | File → Open Config |
| `RoundChamber_IW2D` | WIMBA config, `method: iw2d` | File → Open Config |
| `RoundChamber_TLW_native` | pytlwall's own `.cfg` | Component → Load pytlwall Config… |
| `RoundChamber_IW2D_native` (here) | IW2D's own input file | Component → Load IW2D Config… |
