"""The YAML coordinator/loader builds a working project.

Self-contained: the test writes its own MAD-X twiss and config in tmp_path, so it
never depends on the (movable) examples/ folder.
"""
from pathlib import Path

import numpy as np
import pytest

from wimba import ResultStore, cli, load_project, materialize
from wimba.io.tables import write_impedance

TFS = '''@ NAME  %05s "TWISS"
* NAME               S          L        BETX       BETY
$ %s                %le        %le        %le        %le
 "C1"            100.0        0.6      130.0       85.0
 "C2"            145.0        1.0      110.0      160.0
 "P1"            310.0       14.0       95.0      178.0
'''


def _make_config(tmp_path) -> Path:
    (tmp_path / "opt.tfs").write_text(TFS)
    f = np.logspace(8, 9.5, 50)
    write_impedance(tmp_path / "imported.dat", f, -1j * 2e3 / f, "z")  # a precomputed term
    cfg = """
name: MiniLHC
optics: opt.tfs
grid:
  frequency: {min: 1.0e8, max: 3.0e9, n: 60, log: true}
  time:      {min: 0.0,   max: 5.0e-9, n: 60}
groups:
  collimators:
    - name: C1
      source: resonator
      resonators:
        - {term: zlong, Rs: 1.0e4, Q: 1.0, fr: 1.0e9}
        - {term: zxdip, Rs: 1.0e6, Q: 1.0, fr: 1.0e9}
    - name: C2
      source: resonator
      resonators:
        - {term: zlong, Rs: 2.0e4, Q: 1.0, fr: 1.2e9}
  space_charge:
    - name: P1
      source: cst
      file: imported.dat
      term: zlong
      origin: space_charge_direct
additional:
  - name: crab
    source: cst
    file: imported.dat
    term: zlong
    origin: cst
    pre_weighted: true
"""
    path = tmp_path / "mini_input.yaml"
    path.write_text(cfg)
    return path


def test_load_coordinator(tmp_path):
    project = load_project(_make_config(tmp_path))
    assert project.name == "MiniLHC"
    assert {"collimators", "space_charge"} <= {g.name for g in project.machine.groups}
    assert len(project.machine.additional) == 1

    # optics resolved from the twiss (by name), not retyped
    c1 = project.machine.groups[0].elements[0]
    assert c1.name == "C1" and c1.meta["beta_x"] == 130.0 and c1.meta["position"] == 100.0

    materialize(project, tmp_path / "out")
    store = ResultStore(tmp_path / "out")
    zmem, zsto = project.machine.impedance(project.freqs), store.impedance()
    for k in zmem:
        assert np.allclose(zmem[k], zsto[k])
    assert "zlong" in store.impedance(origin="space_charge_direct")


def test_unknown_source_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("groups:\n  g:\n    - {name: e, source: nope}\n")
    with pytest.raises(ValueError):
        load_project(bad)


def test_cli_build(tmp_path, capsys):
    config = _make_config(tmp_path)
    rc = cli.main(["build", str(config), "--out", str(tmp_path / "out")])
    assert rc == 0
    assert (tmp_path / "out" / "MiniLHC_resume.yaml").is_file()
    assert "components" in capsys.readouterr().out
