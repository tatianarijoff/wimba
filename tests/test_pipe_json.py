"""Default pipe as machine-data JSON; materials policy; the pytlwall-input
debug dump written by a run."""
import configparser
import json

import numpy as np
import pytest

from wimba.assembly import load_assembly
from wimba.io.json_io import read_pipe

PIPE = {
    "name": "test_screen", "shape": "ELLIPTICAL",
    "hor_m": 0.0232, "ver_m": 0.0184, "radius_m": 0.0184,
    "layers": [
        {"type": "CW", "thickness": 75e-6, "sigma": 2.0e9},
        {"type": "CW", "thickness": 1.0e-3, "sigma": 1.4e6},
        {"type": "V", "thickness": "inf", "boundary": True},
    ],
}
TFS = ('@ NAME %05s "T"\n* NAME S L BETX BETY\n$ %s %le %le %le %le\n'
       ' "M1" 0.0 1.0 10.0 20.0\n "M2" 10.0 1.0 30.0 40.0\n')


def test_read_pipe_json(tmp_path):
    (tmp_path / "p.json").write_text(json.dumps(PIPE))
    geo = read_pipe(tmp_path / "p.json")
    assert geo["shape"] == "ELLIPTICAL" and geo["hor"] == 0.0232
    assert len(geo["layers"]) == 3 and geo["layers"][-1]["boundary"] is True


def test_pipe_json_rejects_beam_keys(tmp_path):
    bad = dict(PIPE, betax=100.0)
    (tmp_path / "bad.json").write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="betax"):
        read_pipe(tmp_path / "bad.json")


def _machine(tmp_path, materials="", layer='{material: unobtainium, thickness: 0.002}'):
    (tmp_path / "m.tfs").write_text(TFS)
    (tmp_path / "c.yaml").write_text(
        f"name: Mat\noptics: m.tfs\n{materials}"
        "devices:\n"
        "  a:\n    source: chamber\n    name: A\n    method: pytlwall\n"
        f"    radius_m: 0.01\n    position: 5.0\n    layers: [{layer}]\n")
    return tmp_path / "c.yaml"


def test_unknown_material_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="unobtainium"):
        load_assembly(_machine(tmp_path))


def test_user_materials_resolve(tmp_path):
    cfg = _machine(tmp_path, materials="materials: {unobtainium: 3.3e7}\n")
    res = load_assembly(cfg)
    lay = next(r for r in res.rows if r.name == "A").geometry["layers"][0]
    assert lay["sigma"] == 3.3e7


def test_default_pipe_from_json_and_cfg_dump(tmp_path):
    pytest.importorskip("pytlwall")
    from wimba.run import run as run_study

    (tmp_path / "p.json").write_text(json.dumps(PIPE))
    (tmp_path / "m.tfs").write_text(TFS)
    (tmp_path / "c.yaml").write_text(
        "name: Ext\noptics: m.tfs\n"
        "grid: {frequency: {min: 1.0e6, max: 1.0e9, n: 6, log: true}}\n"
        "default_pipe: {method: pytlwall, file: p.json}\n"
        "devices: {}\n")
    res = load_assembly(tmp_path / "c.yaml")
    pipe = [r for r in res.rows if r.kind == "default_pipe"]
    assert pipe and pipe[0].geometry["shape"] == "ELLIPTICAL"

    # a run dumps the generated pytlwall input, readable for debugging
    run_study(tmp_path / "c.yaml", out_dir=tmp_path / "out")
    dumps = list((tmp_path / "out" / "pytlwall_inputs").glob("*.cfg"))
    assert dumps, "no pytlwall input dumped"
    parser = configparser.ConfigParser(inline_comment_prefixes=(";",))
    parser.read(dumps[0])
    assert parser["base_info"]["chamber_shape"] == "ELLIPTICAL"
    assert parser["layers_info"]["nbr_layers"] == "2"
    assert parser.has_section("boundary")
