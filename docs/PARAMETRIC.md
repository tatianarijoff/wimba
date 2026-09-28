<p align="center"><img src="../img/wimba_logo_small.png" alt="WIMBA" width="190"></p>

# Parametric projects: one parameter, several values

A [project](PROJECTS.md) usually collects cases chosen one by one — the same ring
at injection and at extraction, each made by duplicating the last. A
**parametric project** is generated instead: it names one parameter of one layer
and the values it should take, and WIMBA writes one case per value from a single
base config. The cases then differ in that parameter and in nothing else, which
is what makes their curves comparable.

Typical questions it answers: how does the transverse impedance change if the
innermost layer of a collimator is copper, titanium or graphite? At which
thickness does a coating stop mattering? And — just as important — does any of
it show in the machine total, or is the element irrelevant next to the rest of
the ring? The whole machine is computed in every case, so both answers come out
of the same project.

## The sweep

```yaml
kind: parametric
sweep:
  elements: [COLL.H, COLL.V]
  parameter: layers[0].material
  values: [copper, aluminium, molybdenum, titanium, stainless-steel-316ln, graphite]
```

**elements** — one element, or several that take the same change. The names are
the ones in the config's `name:` fields, as the Machine Explorer shows them. Each
must have its layers written in the config: a layer that comes from a data file
is not edited by a sweep.

**parameter** — `layers[N].FIELD`. `N` counts from 0 at the layer nearest the
beam, in the order the config lists them. `FIELD` is one of:

| field | values | what a case gets |
|---|---|---|
| `material` | material names | the material's numbers, with its name kept as `label:` |
| `thickness` | metres | that thickness; the material stays as written |
| `sigma`, `epsr`, `tau`, `k_Hz`, `muinf_Hz`, `RQ` | numbers, SI units | that value; the layer's other parameters as numbers, its material name dropped |

**values** — at most ten, all different. Material names resolve as they do in any
config: the shipped catalogue, then the base config's own `materials:` block
(see [MATERIALS.md](MATERIALS.md)). Numbers are checked the way the engines
check them: a thickness or a conductivity must be greater than zero, only `k_Hz`
may be `inf`.

A case always states its value unambiguously. A `sigma` case drops the material
name because a layer that said `copper` and carried another conductivity would
give two answers to one question. A `material` case writes the numbers because a
case must compute the same for whoever opens it, with or without your list of
materials.

What cannot be applied is refused before anything is written, naming the
element and the layer: a name that is not in the config, a layer index that does
not exist, a `V` or `PEC` layer (whose parameters no calculation reads), the
boundary's thickness (infinite by definition), a material nobody defined, a base
config with no beam.

## Making one

**In the window:** *File → New Parametric Project…*. The dialog's first line
asks which config to **start from**: a parametric project is not built from
nothing, it varies a machine that already exists, and every case is a copy of
it. Everything below stays disabled until that config is chosen. Then:

- the project name and an empty folder;
- the elements, ticked from those whose layers the config writes out;
- the layer — the line beside it describes that layer of each ticked element;
- the parameter, and the values: a list to tick for materials, one line of
  numbers otherwise.

The line at the bottom says what to do next, lists the cases that will be
written, or — in red — why the sweep cannot be; OK stays disabled until it can.
The project opens as soon as it is written.

**From the shell:**

```bash
wimba sweep examples/Chimera_Project/injection_config.yaml \
    --elements COLL.H --parameter "layers[0].thickness" \
    --values 1e-5 5e-5 2e-4 1e-3 5e-3 --out my_sweep
```

`--relative` keeps the base config's data references relative to the project
folder instead of absolute — for a project committed or moved together with its
data, as the examples are.

## On disk

    my_sweep/
      project.yaml                kind: parametric, the sweep, the base config
      01_t_10_um_config.yaml      one config per value, numbered in sweep order
      01_t_10_um/output/
      02_t_50_um_config.yaml
      ...

Each case config is a copy of the base with the one change, and says so in a
comment at its top. The label — `t = 10 µm`, `copper`, `σ = 1e5 S/m` — is what
the plot legend shows.

## Computing and reading it

*Calculate → Calculate Project…* computes every case in sequence and comes back
to the one you were on (see [PROJECTS.md](PROJECTS.md#computing-every-scenario)).
The Results tree then has one branch per case. Two plots answer the two
questions:

- the element's own contribution across the cases — how much the parameter
  changes the object;
- the machine total across the cases — whether that change matters.

## Keeping the comparison clean

A parametric project has no *Duplicate Scenario*: its cases come from the sweep,
and a case added by hand could differ in anything. To add a value, create the
project again with the longer list.

Nothing stops you from editing a case in the panels. If a case ends up differing
from the first in more than the swept parameter — another element, another
beam — **Problems** says which case and where, when the project is opened and
after each calculation. The numbers are still computed; the warning is there so
the curves are not read as a one-parameter comparison when they are not.

## The examples

Two, both generated from `Chimera_Project/injection_config.yaml`:

| project | sweep |
|---|---|
| `ChimeraMaterial_Project` | `layers[0].material` of COLL.H and COLL.V: copper, aluminium, molybdenum, titanium, stainless-steel-316ln, graphite |
| `ChimeraThickness_Project` | `layers[0].thickness` of COLL.H alone — the chimeranium over its copper — from 10 µm to 5 mm |

See [EXAMPLES.md](EXAMPLES.md#chimeramaterial_project-and-chimerathickness_project).
