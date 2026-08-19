# Beam and optics: who decides

Two numbers decide what a device's impedance comes out as, beyond its own
geometry: **the energy it is solved at** (gamma) and **the optics at its
position** (beta_x, beta_y). Both can be stated in more than one place, so both
need a rule for which statement wins.

The rules are different for the two, and that is deliberate. This page says
what they are, where they are enforced in the code, and how to see afterwards
which value was actually used.

---

## The short version

| | Where it can be stated | Which one wins |
|---|---|---|
| **gamma** | the study's `beam:` block, or `gamma:` on a single element | **the element's own**, if it has one |
| **beta_x / beta_y** | `beta_x:`/`beta_y:` on the device, or the twiss at its position | **the explicit values on the device**, if both are given |

In both cases the more local statement wins. The difference is in what that
means: a local beta is normal and expected, a local gamma is not.

---

## gamma — the energy

### The rule

`_element_gamma()` in `wimba/builders/loader.py`:

1. if the element declares `gamma:`, that is used;
2. otherwise the scenario's `beam:` is used;
3. otherwise the calculation **stops**. There is no fallback value — a chamber
   computed at an unstated energy is not a result.

### If a machine and an element disagree

Say the study declares `beam: {particle: proton, gamma: 7000}` and one device
in it carries `gamma: 450`.

**The element wins: that device is computed at 450, every other device at
7000.** Nothing fails and nothing is flagged in the results — the numbers are
each individually correct, and their sum is a total for no machine that exists.

This is legitimate in exactly one situation: the device is not really part of
that ring — a component loaded from a pytlwall config to be compared against
something, computed at the energy that config was written for.

It is a mistake in every other situation, which is why **the interface no
longer lets you create it**. In the `Beam & Optics` tab:

- for a component that belongs to no machine (built with `Component ▸ New
  Component`, or loaded from a pytlwall or IW2D config), the beam is
  **editable** — that component has no ring to inherit from, and without a beam
  it cannot be computed at all;
- for an element that belongs to a machine, the beam is shown **read-only**,
  because inside a ring there is one beam and it belongs to the ring;
- and if such an element turns out to carry a beam of its own that differs from
  the machine's — possible in a config written by hand — the panel **says so
  explicitly** rather than showing a number without comment.

The check is made against the model (`gm.all_elements()`), not against how the
panel was opened: an element picked from the tree into the Component bench with
`Component ▸ Use Selected` is still part of the ring, and still follows the
ring's beam.

### In the Component bench

A component standing alone carries its beam in its own config, and that beam
is what every calculation of it uses. When it is later placed in a machine, the
study's beam is what applies. The same component can therefore give two
different curves depending on where it was opened, and **both are correct** —
this is the single most common source of "WIMBA gave me a different answer".

---

## beta_x and beta_y — the optics

### The rule

`_resolve()` in `wimba/assembly.py`, in order:

1. **explicit** — the device spec gives both `beta_x:` and `beta_y:`. They are
   used as given, and the assembly records the source as `explicit`.
2. **interp** — the device gives a `position:`. The betas are interpolated from
   the twiss at that s.
3. **name** — the device's name is found in the twiss. Its s is read from
   there, and the betas interpolated at that point.
4. **default-1** — none of the above. Betas of 1.0 are used, and the source is
   recorded as `default-1`.

### If a machine and an element disagree

Say the twiss gives beta_x = 65 m at the position of a collimator, and the
device declares `beta_x: 100`.

**The explicit values win.** The device is computed with 100, and the assembly
table records `beta_source = explicit` for that row.

Unlike a local gamma, this is a normal thing to do: a device's beta is a
property of where that device sits, and there are good reasons to state it by
hand — the element is not in the twiss under that name, or the twiss you have
is not the optics the measurement was taken with. That is why the betas stay
**editable in the interface for every element**, machine or not.

### The case that is not a disagreement, and still bites

Case 4 above. A device that is not in the twiss, has no `position:` and no
explicit betas is computed with **beta = 1** — quietly, and with a result that
looks perfectly plausible.

WIMBA warns about it: `unlocated_warnings()` raises it for every unweighted
device that fell back to `default-1`. The warning is not raised for a device
marked `weighted: true`, where multiplying by 1 is correct by design (see
below), nor for the default pipe.

Whenever a total looks smaller than expected in the transverse planes, the
`beta_source` column of the assembly CSV is the first place to look.

---

## What the betas actually do

In `_scale()` (`wimba/run.py`), for a computed chamber:

- the **longitudinal** term is multiplied by the length only;
- every **transverse** term is multiplied by the length **and by the beta of
  its plane** — beta_x for the X components, beta_y for the Y ones.

The beta is applied directly, not divided by any ring average. Indirect space
charge is scaled the same way, in its own separate columns.

### `weighted: true`

A device marked `weighted: true` declares that **its data is already
beta-weighted** — typically an imported impedance model published as one file
per device family, summed over the ring, where no single position exists. For
those, the compute path multiplies by 1 on purpose.

Setting `weighted: true` on a device whose data is *not* already weighted
silently removes the optics weighting from it. Setting it to false on data that
*is* already weighted applies the weighting twice.

---

## How to check what was used

- **The assembly table** written next to the results lists, per device:
  `position_s`, `beta_x`, `beta_y`, `beta_source`, `weighted`. This is the
  record of what the calculation actually did, as opposed to what the config
  appears to say.
- **The console** carries the warnings for devices that could not be located.
- **The saved config** of a component (`Component ▸ Save Component As…`)
  contains the whole `beam:` block, not just a gamma, so the particle and the
  quantity that was typed are preserved.

---

## Rules of thumb

- One ring, one beam. If two devices in the same machine are computed at
  different energies, one of them is a mistake unless you can say out loud why
  it is not.
- A beta stated by hand is a claim about where the device sits. It is fine to
  make; it is not fine to leave in place after the optics change.
- Beta = 1 is a real physical statement, not a neutral placeholder. It says the
  device sits where the beta function is 1 m.
- A component computed alone and the same component computed inside a machine
  are answering two different questions. Both answers are right.
