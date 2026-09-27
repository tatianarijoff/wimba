# Materials: where a name comes from

A layer of a resistive wall can say what it is made of in two ways: with its
numbers (`sigma`, and `epsr`, `tau`, `muinf_Hz`, `k_Hz`, `RQ` when they matter)
or with a **name**, `material: copper`. A number means the same thing on every
computer. A name only means something if the reader can look it up — so WIMBA is
strict about where names may be looked up.

**The rule: a config must compute the same for whoever opens it.**

## Three places a material can live

| where | who has it | read when a config is computed? |
|---|---|---|
| the catalogue, `wimba/defaults/materials.yaml` | everyone who installed WIMBA | yes |
| the config's own `materials:` block | everyone who has the file | yes — and it wins over the catalogue |
| your `custom_materials.yaml` | you, on this computer | **no** |

`custom_materials.yaml` serves the interface: the layer dropdown and the
*Materials* tab. It never takes part in computing a config, in either dialect.
A file that depended on it would compute for its author and fail — or worse,
compute something else — for everyone else.

## What the interface writes

Choosing a material in a layer writes its **numbers** into that layer, not its
name. A config saved by WIMBA therefore needs no list at all to be computed,
whoever opens it. The name is only a way of typing the numbers.

## Using a name in a config you write

A name in a layer is resolved from the catalogue, then from the config's own
`materials:` block, which wins. The block takes two forms, which can be mixed:

```yaml
materials:
  moc: 1.0e+6                  # short form: the conductivity alone
  chimeranium:                 # full form: any of the six parameters
    sigma: 3.2e+6
    tau: 1.0e-12
    note: invented for this example
```

What a definition does not write takes the neutral values: `epsr` 1, `tau` 0,
`muinf_Hz` 0, `k_Hz` inf, `RQ` 0. `sigma` is required and must be greater than
zero. `label` and `note` are accepted and read only by people; anything else —
`thickness`, for instance, which belongs to the layer and not to the material —
is refused.

A name brings **all** its parameters with it, not just the conductivity. A value
the layer states itself wins: `material: copper` with `sigma: 5.0e+7` is copper
at 5.0e7 S/m.

Names are compared without regard to case. A `V` or `PEC` layer ignores any
material, since its parameters are never read. A `CW` layer with neither a
material nor a `sigma` is an error: nothing says what it is made of.

## When a name cannot be found

It is an error, never a default. If the name is one of your own materials, the
message says so and gives the lines to paste:

```
error: unknown material(s) in this config:
  - 'my-alloy' (in COLL.H) is one of YOUR materials, in custom_materials.yaml. A config does not read that file, so whoever you send it to would not have it.

Copy the definition into the config, at the top level:

materials:
  my-alloy: {sigma: 2000000.0, tau: 1.0e-12}

Or give the layer its numbers directly (sigma, and tau, epsr, muinf_Hz, k_Hz, RQ if they matter). See docs/MATERIALS.md.
```

Paste those lines at the top level of the config — beside `name:` and `beam:`,
not inside a device — and compute again. If the config already has a
`materials:` block, add only the indented line to it.

## Sending and receiving a material

- **Sending.** Put the definition in the config's `materials:` block. It then
  travels with the file, and the receiver needs nothing else.
- **Receiving.** A config with its own block computes as it is. To offer one of
  its materials in *your* layer dropdown too, add it in the *Materials* tab
  (`Materials ▸ Add Material`) with the same fields; it is written to your
  `custom_materials.yaml`.

## Redefining a catalogue material

- **For one study:** a same-named entry in that config's `materials:` block. It
  travels with the file.
- **For yourself, in the interface:** a same-named entry in
  `custom_materials.yaml`. The dropdown then fills layers with your values —
  as numbers, so what you save still computes the same elsewhere. A config that
  says `material: copper` is still computed with the catalogue's copper.

## Coming from an earlier version

Earlier versions resolved a config's names from `custom_materials.yaml` too, and
from the conductivity alone. Two things change:

- a config that named one of your custom materials now stops with the message
  above — paste the lines it gives;
- a named material with more than a conductivity (the catalogue's
  `magnetic-example`, for instance) now brings its permeability as well; before,
  it computed as non-magnetic.

In the machine dialect an unknown name used to be computed at σ = 1e6 without a
word; it is now the same error as in the assembly dialect.

## See also

- [CONFIG.md](CONFIG.md) — the layer fields in a config
- [GUI.md](GUI.md#materials) — the *Materials* tab
- `custom_materials.example.yaml` at the top of the repository
