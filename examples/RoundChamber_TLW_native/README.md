# RoundChamber_TLW_native — single-chamber verification, from a pytlwall config

One round beam pipe with a fully known geometry, written as a pytlwall
chamber `.cfg`. It exercises the route that reads pytlwall's own input: WIMBA
converts the file into a component, and computing it must give the numbers
pytlwall itself gives.

The wall: CIRCULAR, radius 2 mm, length 1 m, beta = 1, one conducting layer of
sigma = 2e5 S/m with a relaxation time of 4.2 ps, epsilon_r = 1, mu-infinity 0,
k infinite, extending to infinity, and gamma = 479.605064966. These are IW2D's
reference numbers, so all four RoundChamber examples describe one wall.

## Files provided

| file | what it is |
|------|------------|
| `RoundChamber.cfg` | a pytlwall chamber config, in the format of pytlwall's own `examples/`. Geometry and betas in `[base_info]`, the wall in `[boundary]`, gamma in `[beam_info]`, the frequency range in `[frequency_info]` |

## Load it

`Component → Load pytlwall Config…` → `RoundChamber.cfg`, then
`Calculate with pytlwall`.

That menu entry takes **this** format. A WIMBA config goes through
`File → Open Config` instead; mixing the two up is the commonest first mistake,
which is why both are here side by side.

## The single layer is the boundary

A layer that extends to infinity is the half-space outside the pipe, so it is
stated under `[boundary]` and `nbr_layers` is 0. That is pytlwall's own
convention: the boundary has no thickness of its own.

## The grid is rebuilt, not copied

`[frequency_info]` asks for 1e3 to 1e11 Hz at 100 points per decade. WIMBA lays
a single logarithmic grid across that range, while pytlwall restarts the count
inside each decade. The two therefore cover the same span and do **not** sample
the same points, so two output files never line up row by row.

Compared at frequencies that do coincide, the two agree to about one part in a
hundred thousand. Compared line against line they look like different physics.
`docs/PYTLWALL_CFG.md` has the full account.

## What WIMBA takes from the file

Geometry, layers and boundary, the betas, the length, gamma from `[beam_info]`,
the frequency range, and `test_beam_shift` if the file states one. A component
loaded this way belongs to no machine, so those values are what it is computed
with — the open config's grid and gamma do not override them.

## Where this one sits

| folder | what it holds | how it gets in |
|--------|---------------|----------------|
| `RoundChamber_TLW` | WIMBA config, `method: pytlwall` | File → Open Config |
| `RoundChamber_IW2D` | WIMBA config, `method: iw2d` | File → Open Config |
| `RoundChamber_TLW_native` (here) | pytlwall's own `.cfg` | Component → Load pytlwall Config… |
| `RoundChamber_IW2D_native` | IW2D's own input file | Component → Load IW2D Config… |
