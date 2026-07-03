# LHC Beam 1 example

Real data from the pywit LHC model: the MAD-X twiss (full lattice), the collimator
reference (JSON), and the RF-cavity HOMs (JSON).

## Run it

```bash
wimba run examples/LHC/LHC_input.yaml            # total + default plots (Re/Im)
wimba run examples/LHC/LHC_input.yaml --wake     # also the longitudinal wake
```

It assembles every lattice location (beta by position, then by name; the default
resistive wall everywhere else), computes the impedance with pytlwall (one
calculation per distinct geometry - the ~11k pipe segments share one), and writes:

- `LHCB1_output/single_elements/total.csv` — the machine total;
- `LHCB1_output/single_elements/collimators/TCP.C6L7.B1.csv` — the one device
  listed under `output:` in the config (per-device output is opt-in);
- `LHCB1_output/total_ZLong.png`, `total_ZDipX.png`, `total_ZDipY.png` — real and
  imaginary parts of each component; with `--wake`, also `total_WLong.png`.

To only build the assignment array (positions, names, method, beta, collisions)
without computing:

```bash
wimba assemble examples/LHC/LHC_input.yaml       # -> LHCB1_assignments.csv
```

Full explanation of the config, the beta resolution, the default-pipe caching and
the output layout: see [docs/ASSEMBLE_AND_RUN.md](../../docs/ASSEMBLE_AND_RUN.md).

## Data
- `data/twiss_lhcb1_beta130cm.tfs` — copy from the pywit model (not in git, ~5 MB)
- `data/lhc_collimators_reference_b1.json`
- `data/lhc_rf_cavities_homs.json`

Requires pytlwall in the environment (`pip install -e /path/to/TLWallNew`).
