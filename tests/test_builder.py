"""The YAML configurator builds a working Machine and the example config loads."""
from pathlib import Path

import numpy as np
import pytest

from wimba import ResultStore, load_machine, materialize
from wimba import cli

CONFIG = Path(__file__).resolve().parent.parent / "examples" / "machine.yaml"


def test_load_example_machine(tmp_path):
    machine, freqs, times = load_machine(CONFIG)
    assert {g.name for g in machine.groups} == {"collimators", "pipes"}
    assert len(machine.additional) == 1
    assert freqs is not None and times is not None

    # the store must reproduce the loaded machine
    materialize(machine, tmp_path / "r", freqs=freqs, times=times)
    store = ResultStore(tmp_path / "r")
    Zm, Zs = machine.impedance(freqs), store.impedance()
    assert set(Zm) == set(Zs)
    for k in Zm:
        assert np.allclose(Zm[k], Zs[k])


def test_unknown_source_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("groups:\n  g:\n    - {name: e, source: nope}\n")
    with pytest.raises(ValueError):
        load_machine(bad)


def test_cli_build_creates_results(tmp_path, capsys):
    rc = cli.main(["build", str(CONFIG), "--out", str(tmp_path / "out")])
    assert rc == 0
    assert (tmp_path / "out" / "manifest.yaml").is_file()
    assert "collimators" in capsys.readouterr().out
