# RoundChamber_TLW — single-chamber verification, computed with pytlwall

One round beam pipe with a fully known geometry, used to check WIMBA's numbers
against pytlwall directly before trusting a full machine.

The wall is IW2D's own reference case, stated key by key: CIRCULAR, radius
2 mm, length 1 m, beta = 1, one conducting layer of sigma = 2e5 S/m (DC
resistivity 5e-06 Ohm.m) with a relaxation time of 4.2 ps, epsilon_r = 1,
magnetic susceptibility 0, extending to infinity, and gamma = 479.605064966.
The relaxation time matters: leaving it at zero is a different wall, and the
difference shows at the top of the frequency range.

## Files provided

| file | what it is |
|------|------------|
| `RoundChamber_TLW_config.yaml` | a WIMBA config: one inline `chamber` device with `method: pytlwall`, the wall described above, and the frequency grid 1e3 – 1e11 Hz. No optics and no default pipe, so the model is exactly this one chamber |

## Run from the shell

```bash
wimba run examples/RoundChamber_TLW/RoundChamber_TLW_config.yaml --wake
```

## Run from the GUI

`File → Open Config` → `RoundChamber_TLW_config.yaml` → `Calculate → Calculate
Whole Machine`; pick quantities from the **Results** tree.

This is a WIMBA config, so it goes in through `File → Open Config`. The entries
under the `Component` menu read the engines' own input formats instead, which
is a different thing.

## Outputs

`RoundChamber_TLW_output/single_elements/total.csv` (and `total_wake.csv` with
`--wake`), the same chamber under `round_chamber/…` since it is named in
`output:`, the plots, and `WAKE_NOTES.txt`.

Because beta = 1 and length = 1, every number equals pytlwall's
`get_all_impedances` / `TLWallWake` for that chamber — a direct check of the
bridge. The automated equivalent lives in `tests/test_pytlwall_bridge.py`.

## Where this one sits

The same wall is written three more ways, so every route into WIMBA can be
exercised on a case whose answer is already known:

| folder | what it holds | how it gets in |
|--------|---------------|----------------|
| `RoundChamber_TLW` (here) | WIMBA config, `method: pytlwall` | File → Open Config |
| `RoundChamber_IW2D` | WIMBA config, `method: iw2d` | File → Open Config |
| `RoundChamber_TLW_native` | pytlwall's own `.cfg` | Component → Load pytlwall Config… |
| `RoundChamber_IW2D_native` | IW2D's own input file | Component → Load IW2D Config… |

Running this one beside `RoundChamber_IW2D` compares two independent codes on
identical input. A circular chamber is the one shape both solve exactly, so a
difference between those curves is a difference between two field solvers and
nothing else.
