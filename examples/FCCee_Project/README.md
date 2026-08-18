# FCC-ee — four operation modes as four scenarios

One project, one frequency grid, four scenarios: the Z, W, H and ttbar modes of
the FCC-ee collider. Same ring, same vacuum chamber, four different optics and
four different energies.

Built on the official CERN lattice release, **acc-models-fcc-ee `LCC_107.0.1`**
(<https://gitlab.cern.ch/acc-models/fcc/acc-models-fcc-ee/-/releases>).

Unlike `Chimera_Project`, nothing here is invented. Every number is either taken
from the release, computed from it, or cited from a published paper — and the
few that are neither are tagged `[FILL IN]` and left out of the model rather
than guessed.

---

## Why this example is different from the others

`LHC` and `SubLHC` come with their optics. This one does not, and cannot: **the
acc-models release contains no computed twiss table.** It ships the lattice in
three equivalent forms — a MAD-X sequence, an xsuite JSON and an xsuite python
file — but the MAD-X file is a bare `sequence ... endsequence` with no `beam`,
no `use` and no `twiss`, so MAD-X alone has no particle, no energy and no active
sequence to work with. The release's own `tests/test_twiss.py` and
`requirements.txt` show the intended route is xsuite.

So the optics is computed once, outside WIMBA, by `make_twiss.py` in this
folder. That script is documented at length in its own module docstring — what
it reads, what it writes, and the three conventions it has to get right. Read it
before changing it.

---

## Running the example

**1. Get the two external inputs.** Install xsuite (`pip install xsuite`), then
put both of these in the folder you keep external data in — neither is tracked
in this repository:

- the acc-models FCC-ee release (the lattice), and
- the published impedance model,
  `git clone https://github.com/ImpedanCEI/fcc_ee_IW_model`

**2. Generate the four optics files** into the folder you keep external data in.

First, be sure which folder to pass. `<acc-models-root>` is the folder that
**contains** `lattices/` — the top of the unpacked release, the one holding the
`VERSION` file. It is *not* `lattices/`, and *not* `lattices/z/`:

```
acc-models-fcc-ee-LCC_107.0.1/     <-- pass THIS path
├── VERSION                            (if you can see this file, you are in the right place)
├── lattices/
│   ├── z/
│   │   ├── fccee_z.json               (what the script actually opens)
│   │   ├── fccee_z.madx
│   │   └── parameter_table.txt
│   ├── w/ , h/ , t/
├── parameter_tables/
└── tests/
```

Then, with `ACC=~/CERN/acc-models-fcc-ee-LCC_107.0.1` and
`OUT=~/CERN/impedance/externalData/FCCee_data`:

```
python make_twiss.py $ACC z -o $OUT/fccee_z_twiss.tfs
python make_twiss.py $ACC w -o $OUT/fccee_w_twiss.tfs
python make_twiss.py $ACC h -o $OUT/fccee_h_twiss.tfs
python make_twiss.py $ACC t -o $OUT/fccee_t_twiss.tfs
```

About 15 s and ~10 MB per stage.

If you pass the wrong folder the script stops immediately and prints the path
you should have used — it does not start loading and then fail. Pointing it at
`$ACC/lattices` is the easy mistake, and it is the one it names explicitly.

**3. Point the configs at those folders.** Same convention as
`examples/LHC/LHC_config.yaml`, with `data_dir:` given as a list: the twiss and
the impedance tables are referenced by bare file name, and `data_dir` says where
to look.

```yaml
data_dir:
- ~/CERN/impedance/externalData/FCCee_data/
- ~/CERN/impedance/externalData/FCCee_data/fcc_ee_IW_model-main/FCCee_IW_2026/FCCee_IW_2026_V1/Coll_taper_3deg/Impedances/Devices/
optics: fccee_z_twiss.tfs
```

Edit those two lines in each of the four `fccee_*_config.yaml` files; nothing
else in them is machine-specific. `~` is expanded; a relative path is resolved
against the config file's own folder, which is *not* what you want here.

The second entry is also the switch between model variants: point it at
`FCCee_IW_2026_V0/Coll_taper_15deg/...` and the whole config reads the other
release, without touching 55 file names.

**4. Open `project.yaml`** in the GUI (*File > Open Project*), or run one
scenario from the command line:

```
wimba run examples/FCCee_Project/fccee_z_config.yaml --wake
```

The acc-models data is never committed. It is public and it lives upstream;
duplicating 80 MB of it into this repository would be a mistake.

---

## What the model contains

**The beam pipe resistive wall, computed here, plus eleven imported device
families.**

The resistive wall is WIMBA's own `default_pipe`: 22 778 lattice segments for
the Z stage, covering 100.0000 % of the 90 660.256 m ring, each weighted by its
own interpolated beta, no collisions.

Everything else comes from the published FCC-ee impedance model,
[github.com/ImpedanCEI/fcc_ee_IW_model](https://github.com/ImpedanCEI/fcc_ee_IW_model),
version `FCCee_IW_2026 / V1 / Coll_taper_3deg`:

| device | what it is | components |
|---|---|---|
| `bpm` | 2220 arc BPMs (CST) | long, dipx/y, quadx/y |
| `rf_cavities` | 33 cryomodules = 132 double-cell 400 MHz cavities | long, dipx/y |
| `collimators` | 40 collimators, 3 cm, 3° taper (IW2D + analytic tapers) | long, dipx/y, quadx/y |
| `kickers` | injection/extraction kickers | long, dipx/y, quadx/y |
| `stripkickers18` / `stripkickers26` | stripline kickers, 18 and 26 mm | long, dipx/y (+quad for 18) |
| `sr_absorbers` | 13 140 SR absorbers | long, dipx/y |
| `flanges` | 13 140 vacuum flanges | long, dipx/y |
| `ems`, `int_mod`, `ir` | emittance station, interconnection modules, 4 IRs | long, dipx/y |

Not every family has quadrupolar data; the configs list only the files that
exist. One file is spelled `Z_quady_stripkickers18.txt` where its siblings say
`stripkickers18mm` — that is the real name, and the config points at it.

### Two things about these files that are not optional

**They are ring totals, so `weighted: true` on every device.** Each file is
already summed over all elements of its family, so WIMBA must not multiply it by
one local beta function. This was determined numerically, not assumed: at 1 GHz
the model's `pipe_rw` gives 3939 Ω against 3941 Ω from the thick-wall analytic
formula for the whole ring, and 4.176e5 against 4.179e5 Ω/m transverse. Both
un-weighted, both ring-wide.

**The frequency is in GHz, and the files say so.** WIMBA reads the unit from the
`# Freq(GHz) Re(Z) Im(Z)` header. A file that declares no unit and whose
frequencies stop below 1 MHz is now refused rather than read as Hz — that
mistake is a silent factor 1e9. Use `freq_unit:` on a device to declare it by
hand.

### Beam pipe: computed or imported, never both

The model also ships its own `pipe_rw`. Using it *and* the pytlwall
`default_pipe` would double-count the single largest contribution, so the
configs keep the computed one and leave `pipe_rw` commented out at the bottom of
each file. Swap them by deleting the `default_pipe:` block and uncommenting.

This choice has a consequence worth stating plainly: **every imported device is
pure geometry and therefore identical at all four energies.** The computed
`default_pipe` is the only part that responds to gamma and to the optics, so it
is what makes the four scenarios differ at all. Reproduce the published model
instead and the four scenarios become byte-identical — which is correct physics,
not a bug (the same situation as SubLHC).

Comparing the two is the interesting exercise the example sets up: the same
chamber, two independent codes, one weighted segment by segment with local betas
and one summed over the ring.

### Still to confirm with the model's authors

Three things I could not settle from the repository, all worth asking before
quoting a number from this example:

1. The transverse totals are not beta-weighted. At which beta should they be
   read for stability? β_avg,x = C/(2πQ₁) = 86.8 m for the Z stage.
2. `Impedances/Devices/Z_long.txt` is not the sum of the twelve device files —
   at 1 GHz the sum gives ≈ 1.03e5 + 4.68e4j Ω against −245 + 2987j — although
   the repository's notebook treats it as the total.
3. The model is built on optics **LCCv106**; this project uses **LCC_107.0.1**.

### Chamber geometry

In `data/fccee_default_pipe.json`, with the provenance of every number recorded
in its `_provenance` block:

| | value | source |
|---|---|---|
| shape | CIRCULAR | chosen deliberately to avoid the current-dependent tune shift from the quadrupolar RW wake — FCC FSR Vol. 2 §3.2.3 |
| radius | 30 mm | 60 mm ID, FSR Vol. 2 §3.2.3 (was 70 mm early in the study) |
| material | OFS copper, σ = 5.88e7 S/m | FSR Vol. 2 §3.2.3; ρ = 1.7e-8 Ω·m as in arXiv:2003.10009 |
| wall thickness | 2 mm | **`[FILL IN]`** — not found in a public source |
| NEG coating | 150 nm | thickness published (arXiv:2204.04616), conductivity **`[FILL IN]`** — layer left commented out |

Two traps worth knowing:

- The published impedance papers use a **35 mm** radius, from the 70 mm ID era.
  A cross-check against their `k_loss` numbers must use 0.035, not 0.030.
- The NEG layer is the single most impactful unknown in this model. Minimising
  its thickness is the central result of PRAB 21, 111002 (2018) — its
  conductivity is not something to guess.

---

## Design decisions recorded here

### Space charge is off

**Where:** the `default_pipe:` block of all four `fccee_*_config.yaml` files:

```yaml
default_pipe:
  method: pytlwall
  space_charge: false
  file: data/fccee_default_pipe.json
```

**Why:** indirect space charge scales as 1/γ², and these are the most
ultrarelativistic machines WIMBA has been pointed at.

| stage | energy | γ | 1/γ² |
|---|---|---|---|
| z | 45.6 GeV | 89 237 | 1.26e-10 |
| w | 80 GeV | 156 556 | 4.08e-11 |
| h | 120 GeV | 234 834 | 1.81e-11 |
| t | 182.5 GeV | 357 144 | 7.84e-12 |

Compare `PS_Project`, where 1/γ² moves from 0.102 to 0.0013, or the AD, where it
goes from 0.065 to 0.989 and indirect space charge overtakes the wall term
entirely. Here the ISC contribution is ten orders of magnitude down and carries
no physics — leaving it on would only cost compute time and invite someone to
read noise as a result.

**Consequence for scenario comparison:** the contrast between these four
scenarios comes almost entirely from the **optics**, not from the beam. This is
the opposite of the AD, and it is the reason this example is worth having: it
exercises the case where the optics file is what changes.

### The frequency grid is sized on the shortest bunch

The grid belongs to the project and is locked across scenarios, so it has to
cover the most demanding one: ttbar, σ_z = 2.69 mm → σ_t = 8.98 ps →
1/(2πσ_t) = 17.7 GHz. `f_min = 1e3 Hz` sits below the revolution frequency
(3306.77 Hz).

`f_max = 5e10 Hz`, not 1e11: the imported impedance model stops at 50 GHz, and
above that WIMBA would be extrapolating someone else's data. 50 GHz is still
almost three times what the shortest bunch needs, so nothing is lost.

Bunch lengths across the four modes, from the parameter tables (incl.
beamstrahlung): 15.08 / 6.04 / 5.45 / 2.69 mm.

### Same ring, different operation mode

The scenario rules allow a duplicate to change the beam *and* the optics file,
which is exactly what a stage change is. No code change was needed. What was
missing was a check that the two still agree — see below.

---

## Checking an optics file

`wimba.io.accmodels` reads the acc-models parameter tables and cross-checks them
against a twiss table and a beam:

```python
from wimba.io.accmodels import check_stage, beam_from_twiss

tw = "~/CERN/impedance/externalData/FCCee_data/fccee_z_twiss.tfs"
rep = check_stage("<acc-models-root>", "z", tw, beam=beam_from_twiss(tw))
print(rep.text())
```

It verifies the columns the assembly needs, that Σ L closes on the ring length,
that no beta is non-positive, the particle, and gamma three ways — twiss header,
parameter table, scenario beam. For devices it also flags a position outside the
ring, and a position coinciding with a lattice element boundary, where the beta
interpolation silently returns that magnet's value instead of the surrounding
drift's (the trap documented in `Chimera_Project`).

Pairing the Z optics with the ttbar parameter table, for instance, produces:

```
ERROR    twiss header energy 45.6 GeV does not match the parameter table 182.5 GeV
WARNING  tunes from the twiss (166.160, 162.200) differ from the parameter table (346.132, 262.281)
```

### Validation of the generated optics

Tunes computed from the lattice against the official parameter tables, and ring
closure:

| stage | Q1, Q2 computed | Q1, Q2 published | γ | \|Σ L − S_end\| |
|---|---|---|---|---|
| z | 166.160, 162.200 | 166.16, 162.2 | 89 236.974 | 1.2e-8 m |
| w | 211.160, 158.200 | 211.16, 158.201 | 156 556.095 | 1.2e-8 m |
| h | 346.160, 262.200 | 346.161, 262.202 | 234 834.142 | 1.2e-8 m |
| t | 346.131, 262.276 | 346.132, 262.281 | 357 143.591 | 1.2e-8 m |

γ is not derived from the energy: it is read from `particle_ref` in the
acc-models JSON, and it matches the parameter table to all digits.

---

## One thing that had to be fixed in WIMBA for this to work

`madx.read_twiss` indexes the table by element name, because that is how devices
are matched to the lattice. In a MAD-X twiss that is safe — MAD-X numbers its
drifts `DRIFT_0`, `DRIFT_1`, … — but in the xsuite line the arc drifts are
**shared instances**: 11 275 of the 30 080 Z rows carry only 87 distinct names,
covering 11 944 m of the ring. Keyed by name they collapsed to 87 rows and
**13 % of the circumference vanished from the default pipe with no error at
all.**

`read_twiss` now takes `on_duplicate="rename"` (the default; repeats get a `.2`,
`.3`, … suffix so lengths survive and a device named after the first occurrence
still resolves to it), `"error"`, or `"last"` for the old behaviour. A companion
`madx.duplicates(path)` reports repeated names as a cheap pre-flight check.
