# RoundChamber_IW2D — single-chamber verification, computed with IW2D

One round beam pipe with a fully known geometry, computed with IW2D. Its
answer is known independently, which is what makes it a check rather than a
calculation: an identical config computed with pytlwall sits in
`RoundChamber_TLW`, and two independent codes on the same input should agree.

The wall is IW2D's own reference case, stated key by key: CIRCULAR, radius
2 mm, length 1 m, beta = 1, one conducting layer of sigma = 2e5 S/m (DC
resistivity 5e-06 Ohm.m) with a relaxation time of 4.2 ps, epsilon_r = 1,
magnetic susceptibility 0, extending to infinity, and gamma = 479.605064966.

## Files provided

| file | what it is |
|------|------------|
| `RoundChamber_IW2D_config.yaml` | a WIMBA config: one inline `chamber` device with `method: iw2d`, the wall described above, and the frequency grid 1e3 – 1e11 Hz. Identical to the pytlwall example in every respect but the method |

## Run from the shell

```bash
wimba run examples/RoundChamber_IW2D/RoundChamber_IW2D_config.yaml
```

## Run from the GUI

`File → Open Config` → `RoundChamber_IW2D_config.yaml` → `Calculate → Calculate
Whole Machine`.

This is a WIMBA config. `Component → Load IW2D Config…` is for IW2D's own input
format, which is a different file — the same wall is written that way in
`RoundChamber_IW2D_native`.

## Reading the comparison

Two conventions differ between the engines, and both change what you should
compare against what. `docs/IW2D.md` sets them out; the short version:

- **IW2D returns the wall impedance**, which already contains the indirect
  space charge. The comparable pytlwall quantity is therefore
  `ZLong + ZLongISC`, not `ZLong` alone.
- **IW2D has no perfect conductor.** A `PEC` layer is approximated by a very
  low resistivity, and WIMBA says so in the console when it does it. This
  chamber has no PEC layer, so it does not arise here.

Two more things worth knowing before comparing decimals:

- **The wake is not IW2D's.** IW2D computes wakes in its C++ executables, but
  the Python package WIMBA drives does not: its wake wrappers are stubs. A wake
  from this config is WIMBA's Fourier transform of the IW2D impedance, and the
  interface says so wherever it offers one.
- **The grids do not line up.** WIMBA builds one logarithmic grid across the
  range; other codes sample differently. Compare at frequencies that coincide,
  not row against row.

## Why a circular chamber

It is the one shape both engines solve **exactly**. Nothing here is a form
factor or an equivalent-round approximation, so a difference between the two
curves is a difference between two field solvers.

That is not true of the other shapes. From a config the IW2D path covers
circular chambers; for elliptical and rectangular ones pytlwall applies its own
Yokoya tables to a round solve. Comparing two engines that both rescale a round
result by a table measures the tables, not the physics.

## Where this one sits

| folder | what it holds | how it gets in |
|--------|---------------|----------------|
| `RoundChamber_TLW` | WIMBA config, `method: pytlwall` | File → Open Config |
| `RoundChamber_IW2D` (here) | WIMBA config, `method: iw2d` | File → Open Config |
| `RoundChamber_TLW_native` | pytlwall's own `.cfg` | Component → Load pytlwall Config… |
| `RoundChamber_IW2D_native` | IW2D's own input file | Component → Load IW2D Config… |
