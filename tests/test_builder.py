"""The coordinator config loads MAD-X optics and wires the sources."""
from pathlib import Path

import numpy as np
import pytest

from wimba import ResultStore, load_project, materialize, cli

CONFIG = Path(__file__).resolve().parent.parent / "examples" / "SubLHC_input.yaml"


def test_load_coordinator(tmp_path):
    project = load_project(CONFIG)
    assert project.name == "SubLHC"
    names = {g.name for g in project.machine.groups}
    assert {"collimators", "pipes", "space_charge"} <= names
    assert len(project.machine.additional) == 1

    # optics were read from the MAD-X file (not retyped in the config)
    tcp = project.machine.groups[0].elements[0]
    assert tcp.name == "TCP.C6L7.B1"
    assert tcp.meta["beta_x"] == 130.0 and tcp.meta["position"] == 100.0

    materialize(project, tmp_path / "out")
    store = ResultStore(tmp_path / "out")
    Zm, Zs = project.machine.impedance(project.freqs), store.impedance()
    for k in Zm:
        assert np.allclose(Zm[k], Zs[k])

    # the imported direct space-charge term is tagged and summed under long
    dsc = store.impedance(origin="space_charge_direct")
    assert "zlong" in dsc


def test_unknown_source_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("groups:\n  g:\n    - {name: e, source: nope}\n")
    with pytest.raises(ValueError):
        load_project(bad)


def test_cli_build(tmp_path, capsys):
    rc = cli.main(["build", str(CONFIG), "--out", str(tmp_path / "out")])
    assert rc == 0
    assert (tmp_path / "out" / "SubLHC_resume.yaml").is_file()
    assert "components" in capsys.readouterr().out
