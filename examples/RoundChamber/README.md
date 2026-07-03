# RoundChamber — single-chamber verification

Mirrors the Wake2D `RoundChamber` reference (CIRCULAR, radius 2 mm, L = 1 m,
beta = 1, one layer sigma = 2e5 S/m, gamma = 479.605) so the WIMBA output can be
checked against known values for a single chamber.

```bash
wimba run examples/RoundChamber/RoundChamber_input.yaml --wake
```

Because beta = 1 and L = 1, the WIMBA result for this chamber is exactly pytlwall's
`get_all_impedances` / `TLWallWake` for it - a direct check of the bridge.
