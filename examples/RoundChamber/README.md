# RoundChamber — single-chamber verification

One round beam pipe with a fully known geometry, used to check WIMBA's numbers
against pytlwall directly before trusting a full machine.

## Files provided

| file | what it is |
|------|------------|
| `RoundChamber_input.yaml` | the config: one inline `chamber` device (CIRCULAR, radius 2 mm, length 1 m, beta = 1, one conducting layer sigma = 2e5 S/m, infinite thickness), gamma = 479.605, frequency grid. No optics and no default pipe: the model is exactly this one chamber |

## Run from the shell

```bash
wimba run examples/RoundChamber/RoundChamber_input.yaml --wake
```

## Run from the GUI

`File → Open Config` → `RoundChamber_input.yaml` → `Calculate → Calculate Whole
Machine`; pick quantities from the **Results** tree.

## Outputs

`RoundChamber_output/single_elements/total.csv` (and `total_wake.csv` with
`--wake`), the same chamber under `round_chamber/…` (it is listed in `output:`),
plots and `WAKE_NOTES.txt`.

Because beta = 1 and length = 1, every number equals pytlwall's
`get_all_impedances` / `TLWallWake` for that chamber — a direct check of the
bridge (the automated equivalent lives in `tests/test_pytlwall_bridge.py`).
