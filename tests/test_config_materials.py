"""Which material names a config may use, and what they bring with them.

The rule (docs/MATERIALS.md): a config resolves names from the shipped catalogue
and from its own `materials:` block - never from the user's
custom_materials.yaml, which lives on one computer. The same rule in both
dialects, and an unknown name is always an error.
"""
import pytest
import yaml

from wimba import materials
from wimba.assembly import load_assembly
from wimba.builders import load_scenario

TFS = ('@ NAME %05s "T"\n* NAME S L BETX BETY\n$ %s %le %le %le %le\n'
       ' "M1" 0.0 1.0 10.0 20.0\n "M2" 10.0 1.0 30.0 40.0\n')


def _assembly(tmp_path, layer, block=None, name="c.yaml"):
    (tmp_path / "m.tfs").write_text(TFS)
    cfg = {"name": "N", "optics": "m.tfs",
           "devices": {"a": {"source": "chamber", "name": "A", "method": "pytlwall",
                             "radius_m": 0.01, "position": 5.0,
                             "layers": [layer, {"type": "V", "thickness": "inf"}]}}}
    if block is not None:
        cfg["materials"] = block
    (tmp_path / name).write_text(yaml.safe_dump(cfg))
    return tmp_path / name


def _layer(result):
    return next(r for r in result.rows if r.name == "A").geometry["layers"][0]


def _machine(tmp_path, layer, block=None):
    data = {"name": "M",
            "grid": {"frequency": {"min": 1.0e6, "max": 1.0e9, "n": 5, "log": True}},
            "beam": {"particle": "proton", "mode": "gamma", "gamma": 10.0},
            "groups": {"walls": [{"name": "W", "source": "pytlwall", "length": 1.0,
                                  "radius_m": 0.02, "beta_x": 1.0, "beta_y": 1.0,
                                  "layers": [layer]}]}}
    if block is not None:
        data["materials"] = block
    path = tmp_path / "machine.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


@pytest.fixture
def my_alloy(tmp_path, monkeypatch):
    """A custom_materials.yaml with one material of the user's own."""
    custom = tmp_path / "custom_materials.yaml"
    custom.write_text("materials:\n  my-alloy: {sigma: 2.0e+6, tau: 1.0e-12}\n"
                      "  copper: {sigma: 5.0e+7}\n")
    monkeypatch.setenv("WIMBA_MATERIALS", str(custom))
    materials.reload()
    yield custom
    monkeypatch.delenv("WIMBA_MATERIALS", raising=False)
    materials.reload()


# ---------------------------------------------------------------- the block
def test_the_block_takes_the_short_and_the_full_form():
    table = materials.study_materials({"moc": 1.0e6,
                                       "Chimeranium": {"sigma": 3.2e6, "tau": 1e-12}})
    assert table["moc"]["sigma"] == pytest.approx(1.0e6)
    assert table["moc"]["tau"] == 0.0                     # neutral, not written
    assert table["chimeranium"]["tau"] == pytest.approx(1e-12)   # names lower-cased


def test_the_block_refuses_what_a_material_cannot_set():
    with pytest.raises(ValueError, match="thickness"):
        materials.study_materials({"x": {"sigma": 1e6, "thickness": 0.002}})
    with pytest.raises(ValueError, match="sigma"):
        materials.study_materials({"x": {"tau": 1e-12}})
    with pytest.raises(ValueError, match="greater than zero"):
        materials.study_materials({"x": 0})


def test_the_block_wins_over_the_catalogue():
    table = materials.config_table({"copper": {"sigma": 4.0e7}})
    assert table["copper"]["sigma"] == pytest.approx(4.0e7)


# ------------------------------------------------------ the assembly dialect
def test_a_full_definition_reaches_the_layer(tmp_path):
    cfg = _assembly(tmp_path, {"type": "CW", "material": "chimeranium",
                               "thickness": 0.025},
                    {"chimeranium": {"sigma": 3.2e6, "tau": 1e-12, "epsr": 2.0}})
    lay = _layer(load_assembly(cfg))
    assert lay["sigma"] == pytest.approx(3.2e6)
    assert lay["tau"] == pytest.approx(1e-12) and lay["epsr"] == pytest.approx(2.0)


def test_a_value_the_layer_states_wins_over_its_material(tmp_path):
    cfg = _assembly(tmp_path, {"type": "CW", "material": "copper",
                               "thickness": 0.002, "sigma": 5.0e7})
    assert _layer(load_assembly(cfg))["sigma"] == pytest.approx(5.0e7)


def test_a_config_does_not_read_your_custom_file(tmp_path, my_alloy):
    cfg = _assembly(tmp_path, {"type": "CW", "material": "my-alloy", "thickness": 0.002})
    with pytest.raises(ValueError) as err:
        load_assembly(cfg)
    text = str(err.value)
    assert "one of YOUR materials" in text
    assert "materials:" in text and "my-alloy: {sigma: 2000000.0" in text


def test_the_lines_the_error_offers_can_be_pasted_as_they_are(tmp_path, my_alloy):
    cfg = _assembly(tmp_path, {"type": "CW", "material": "my-alloy", "thickness": 0.002})
    with pytest.raises(ValueError) as err:
        load_assembly(cfg)
    snippet = str(err.value).split("at the top level:\n\n", 1)[1].split("\n\n")[0]
    pasted = yaml.safe_load(snippet)
    # spelt so YAML 1.1 reads numbers, not strings (1e-12 alone is a string)
    assert isinstance(pasted["materials"]["my-alloy"]["tau"], float)
    data = yaml.safe_load(cfg.read_text())
    data.update(pasted)
    cfg.write_text(yaml.safe_dump(data))
    lay = _layer(load_assembly(cfg))
    assert lay["sigma"] == pytest.approx(2.0e6) and lay["tau"] == pytest.approx(1e-12)


def test_your_own_copper_does_not_change_a_config(tmp_path, my_alloy):
    """custom_materials.yaml redefines copper for the interface, not for a file."""
    assert materials.parameters("copper")["sigma"] == pytest.approx(5.0e7)
    cfg = _assembly(tmp_path, {"type": "CW", "material": "copper", "thickness": 0.002})
    assert _layer(load_assembly(cfg))["sigma"] == pytest.approx(5.9e7)


def test_a_cw_layer_that_names_nothing_is_an_error(tmp_path):
    cfg = _assembly(tmp_path, {"type": "CW", "thickness": 0.002})
    with pytest.raises(ValueError, match="neither a material nor a sigma"):
        load_assembly(cfg)


# ------------------------------------------------------- the machine dialect
def test_the_machine_dialect_refuses_an_unknown_name(tmp_path):
    """It used to compute such a layer at sigma = 1e6 without a word."""
    path = _machine(tmp_path, {"type": "CW", "material": "unobtainium",
                               "thickness": 0.002})
    with pytest.raises(ValueError, match="unobtainium"):
        load_scenario(path)


def test_the_machine_dialect_reads_its_own_block(tmp_path):
    path = _machine(tmp_path, {"type": "CW", "material": "chimeranium",
                               "thickness": 0.002},
                    {"chimeranium": {"sigma": 3.2e6, "muinf_Hz": 3.0}})
    wall = load_scenario(path).machine.groups[0].elements[0]
    lay = wall.provider.layers[0]
    assert lay["sigma"] == pytest.approx(3.2e6) and lay["muinf_Hz"] == pytest.approx(3.0)
    # the interface still sees the layer as the file writes it
    assert wall.provider.layers_as_written[0] == {"type": "CW", "material": "chimeranium",
                                                  "thickness": 0.002}
