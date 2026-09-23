<p align="center">
  <img src="img/wimba_logo.png" alt="WIMBA" width="260">
</p>

# Video guide

Short screencasts that show WIMBA on screen: what to type, what to click and what
comes out. Each video is self-contained — watch the section you need, in any order.
The written documentation stays the reference; the videos are the quickest way in.

Videos are grouped by subject, not numbered: **Installation**, then
**The interface**, then **Build a component**, then **Machines**.

---

## Installation

Everything needed to go from an empty folder to a working WIMBA, on Linux or macOS
(on Windows only the virtual-environment activation line differs).

### ▶ [WIMBA — Installation](https://youtu.be/1fZkL5RX1Ps)

What it covers:

- what the acronym means and what WIMBA computes (impedance **and** wake);
- what you install yourself (Python 3.10+, git), what `pip` brings in for you,
  and what stays separate — the two resistive-wall engines, **pytlwall** and
  **IW2D**, which are two independent implementations of the same physics;
- cloning the repository and installing it in a virtual environment;
- the settings file: what actually belongs in it, and why an engine installed
  with `pip` needs no entry at all;
- the right first test, so you know the install is sound before trusting a result.

Read alongside: [`docs/SETUP.md`](docs/SETUP.md) ·
[`docs/SETTINGS.md`](docs/SETTINGS.md) · [`docs/IW2D.md`](docs/IW2D.md)

---

## The interface

Two videos on the graphical interface: the first opens the window and gets one
curve on the plot, the second stays inside the results.

### ▶ [WIMBA GUI — Introduction](https://youtu.be/n21qZ52sYlw)

What it covers:

- the same engine seen from the front — the window is the library, not a second
  program;
- the four regions of the window and the question each one answers;
- the Inspector and the element tabs, and when you need one rather than the other;
- launching a calculation and following it;
- the Results tree, and the first curve on the plot;
- the documentation available inside the window (`F1`).

### ▶ [WIMBA GUI — Results](https://youtu.be/X-ragYy_qts)

What it covers:

- the plot: adding and removing curves, comparing what has been computed;
- the three scales, and why a symmetric-log scale exists at all;
- the Results table;
- exporting what is on screen;
- the bottom row — Console, Jobs and Problems — and what Problems actually reports.

Read alongside: [`docs/GUI.md`](docs/GUI.md) · [`docs/PROJECTS.md`](docs/PROJECTS.md)

---

## Build a component

The Component bench: one element on its own, described, computed and compared —
no lattice, no project. This is the shortest route to a number you can check.

### ▶ [Build a component — Introduction](https://youtu.be/lbzsTEVwnts)

What it covers:

- creating a new component and naming it, and where it lives while you work on it;
- shape and aperture;
- the boundary rule — where the chamber ends and the outside world begins;
- layers and materials, including the custom, vacuum and perfect-conductor cases.

### ▶ [Build a component — Beam, optics and models](https://youtu.be/WzIE-hC5EaQ)

What it covers:

- the optics: the beta functions belong to the element;
- the beam: gamma is the canonical input, and when a beta is enough;
- the calculation methods, seen as different kinds of element rather than as a
  list of options;
- saving the component, with the written configuration on screen — the same file
  reopens in the interface and runs from the command line.

### ▶ [Build a component — Compute and compare](https://youtu.be/iE6CPjF7VIw)

What it covers:

- picking up a saved component again with Component ▸ Open Component;
- computing it the way the Models tab says, and naming an engine instead when
  the point is a comparison;
- results that accumulate, each labelled with the engine that produced it, so two
  answers to the same question sit side by side;
- additional calculations on the same element, and what a comparison can and
  cannot hold;
- the wake: where it comes from for each method, and why that matters when you
  compare them;
- where everything is kept — beside the component, one folder per engine, with
  the exact input each engine was given — and how to take a curve elsewhere.

Read alongside: [`docs/COMPONENT.md`](docs/COMPONENT.md) ·
[`docs/PYTLWALL_CFG.md`](docs/PYTLWALL_CFG.md)

---

## Machines

A whole machine rather than one element: many devices, an optics, a beam, and a
total that adds them up.

### ▶ [Machines — Two files, two menus](https://youtu.be/sJJVVdWg0B8)

What it covers:

- the two kinds of file WIMBA reads a machine from: a **machine file**, which
  lists the elements, and a **config file**, which states rules — an optics file,
  named devices and where they sit, and what to do with the rest of the ring;
- telling them apart from the keys inside them — you never declare which kind
  you have;
- the two entries in the File menu, Load Machine and Open Config, and why WIMBA
  refuses a file opened through the wrong one;
- the tree after loading: your own file in one case, a resolved result in the
  other.

### ▶ [Machines — Reading it, and changing it](https://youtu.be/U6IyhQTOUSc)

What it covers:

- the tree and the Inspector: what WIMBA resolved from your rules, device by
  device, and where each value came from;
- editing a value — WIMBA never writes to your file unless you ask, and
  File ▸ Save Machine writes back only what you changed, comments intact;
- adding a device, and why an element is born in the file;
- position is optional: with one, the beta comes from the optics at that point;
  without one, WIMBA looks the name up in the optics, and falls back to β = 1,
  saying so, when the name is not there either;
- the cell-boundary trap — the same device a few centimetres apart can see two
  very different betas.

Read alongside: [`docs/GUI.md`](docs/GUI.md) ·
[`docs/CONFIG.md`](docs/CONFIG.md) ·
[`docs/ASSEMBLE_AND_RUN.md`](docs/ASSEMBLE_AND_RUN.md)

---

Documentation index: [`docs/README.md`](docs/README.md)
