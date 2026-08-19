"""Named materials for CW layers.

What reaches a config is always the numbers; the name is only a way of typing
them. So the tests care about two things: that choosing a material fills the
right figures, and that editing a figure by hand never edits the catalogue.
"""
import pytest
import yaml

from wimba import materials
from wimba.materials import sigma_table


def test_the_catalogue_loads_and_has_a_usable_default():
    assert materials.names()
    default = materials.default_name()
    assert default in materials.names()
    assert materials.parameters(default)["sigma"] > 0


def test_every_entry_is_complete_after_the_neutral_defaults():
    for name in materials.names():
        p = materials.parameters(name)
        for key in materials.PARAMS:
            assert key in p, f"{name} is missing {key}"
        assert p["k_Hz"] != 0, f"{name}: pytlwall does not allow k = 0"
        assert p["sigma"] != float("inf"), \
            f"{name}: pytlwall does not allow infinite conductivity"


def test_every_entry_says_how_firm_its_value_is():
    """Conductivity depends on grade and temperature. A name without a caveat
    invites being quoted as an authority."""
    for name in materials.names():
        assert materials.note(name).strip(), f"{name} has no note"


def test_applying_a_material_fills_the_layer_but_not_its_thickness():
    layer = {"type": "CW", "thickness": 0.003}
    materials.apply_to(layer, "copper")
    assert layer["sigma"] == pytest.approx(5.9e7)
    assert layer["thickness"] == 0.003        # how thick is not what it is made of
    assert layer["epsr"] == 1.0 and layer["muinf_Hz"] == 0.0


def test_a_layer_is_recognised_as_its_material():
    layer = {"type": "CW", "thickness": 0.002}
    materials.apply_to(layer, "stainless-steel-316LN")
    assert materials.match(layer) == "stainless-steel-316LN"


def test_editing_a_parameter_makes_the_layer_custom_not_a_new_material():
    layer = {"type": "CW", "thickness": 0.002}
    materials.apply_to(layer, "copper")
    layer["sigma"] = 4.0e7
    assert materials.match(layer) is None
    assert materials.parameters("copper")["sigma"] == pytest.approx(5.9e7)


def test_v_and_pec_are_not_materials():
    layer = {"type": "V", "thickness": "inf"}
    assert materials.match(layer) is None
    layer = {"type": "PEC"}
    assert materials.match(layer) is None


def test_an_unknown_name_is_refused_rather_than_silently_empty():
    with pytest.raises(KeyError):
        materials.parameters("unobtainium")


def test_a_layer_missing_the_neutral_keys_still_matches():
    """A config that states only sigma is the common case: the rest is
    pytlwall's default, which is exactly what the catalogue assumes."""
    assert materials.match({"type": "CW", "sigma": 5.9e7}) == "copper"


def test_no_name_resolves_to_two_different_conductivities():
    """The interface and a config must agree. A name that means 5.8e7 when
    chosen from the dropdown and 5.9e7 when written in a file is worse than no
    catalogue at all."""
    table = sigma_table()
    for name in materials.names():
        assert table[name.lower()] == pytest.approx(
            materials.parameters(name)["sigma"]), \
            f"{name} resolves differently for a config than in the interface"


def test_the_names_configs_have_always_resolved_still_resolve():
    """These came from a hardcoded table in sources/pytlwall_bridge.py. Moving
    them into the data file must not change one number, or a config written
    years ago starts computing something else."""
    frozen = {"cu": 5.9e7, "copper": 5.9e7, "stainless_steel": 1.4e6,
              "ss": 1.4e6, "ss304": 1.4e6, "graphite": 1.0e5, "cfc": 1.0e5,
              "mogr": 1.0e6, "inermet180": 4.0e6, "inermet": 4.0e6,
              "beam_screen": 5.9e7, "w": 1.8e7, "mo": 1.9e7}
    table = sigma_table()
    for name, sigma in frozen.items():
        assert name in table, f"{name} no longer resolves"
        assert table[name] == pytest.approx(sigma), f"{name} changed value"



def test_both_engines_resolve_a_named_material_identically():
    """The list is not pytlwall's: IW2D layers name the same materials, and a
    wall that says copper must be the same wall whichever engine computes it."""
    from wimba.sources import iw2d_bridge, pytlwall_bridge
    for name in ("copper", "stainless_steel", "graphite"):
        assert pytlwall_bridge._sigma(name) == pytest.approx(
            materials.sigma_of(name))
        assert iw2d_bridge is not None      # imported without a pytlwall/IW2D install


def test_an_unnamed_material_falls_back_to_the_same_number_everywhere():
    from wimba.sources import pytlwall_bridge
    assert pytlwall_bridge._sigma(None) == pytest.approx(materials.DEFAULT_SIGMA)
    assert materials.sigma_of("something-nobody-defined") == pytest.approx(
        materials.DEFAULT_SIGMA)


def test_a_custom_file_layers_over_the_catalogue(tmp_path, monkeypatch):
    """The user's own file replaces an entry by name and adds new ones. The
    packaged catalogue is never written to."""
    custom = tmp_path / "custom_materials.yaml"
    custom.write_text(
        "materials:\n"
        "  copper:\n"
        "    sigma: 5.75e+7\n"
        "    note: our sample\n"
        "  my-alloy:\n"
        "    sigma: 2.0e+6\n"
        "    note: measured here\n")
    monkeypatch.setenv("WIMBA_MATERIALS", str(custom))
    materials.reload()
    try:
        assert materials.parameters("copper")["sigma"] == pytest.approx(5.75e7)
        assert materials.origin("copper") == "custom file"
        assert materials.parameters("my-alloy")["sigma"] == pytest.approx(2.0e6)
        # and it reaches a calculation, not just the dropdown
        assert sigma_table()["my-alloy"] == pytest.approx(2.0e6)
    finally:
        monkeypatch.delenv("WIMBA_MATERIALS", raising=False)
        materials.reload()
    assert materials.parameters("copper")["sigma"] == pytest.approx(5.9e7)


def test_a_broken_custom_file_does_not_take_the_catalogue_down(tmp_path,
                                                               monkeypatch):
    bad = tmp_path / "custom_materials.yaml"
    bad.write_text("materials:\n  oops: [this is not a mapping\n")
    monkeypatch.setenv("WIMBA_MATERIALS", str(bad))
    materials.reload()
    try:
        assert materials.parameters("copper")["sigma"] == pytest.approx(5.9e7)
    finally:
        monkeypatch.delenv("WIMBA_MATERIALS", raising=False)
        materials.reload()


def test_the_example_file_is_readable_and_never_the_one_in_use():
    """It ships as a starter; if WIMBA ever loaded it, everyone would inherit
    somebody's prototype copper.

    The example lives at the top of the repository, next to wimba.example.yaml
    - two levels above wimba/defaults/, not one. Looking one level up found
    nothing and skipped, so this test passed by not running.
    """
    import yaml as _yaml
    from pathlib import Path as _Path
    example = _Path(materials.CATALOGUE).parents[2] / "custom_materials.example.yaml"
    if not example.is_file():
        pytest.skip("running from an installed package, not a checkout")
    data = _yaml.safe_load(example.read_text())
    assert data["materials"]
    assert materials.custom_path() != example


def test_a_layer_built_from_a_material_carries_numbers_not_the_name():
    """What travels is the config, not the catalogue. A colleague who has never
    seen your custom_materials.yaml must still compute the same wall."""
    from wimba.gui.model import layer_out
    layer = {"type": "CW", "thickness": 0.002}
    materials.apply_to(layer, "copper")
    written = layer_out(layer)
    assert "material" not in written
    assert written["sigma"] == pytest.approx(materials.parameters("copper")["sigma"])
    for key in ("epsr", "tau", "k_Hz", "muinf_Hz", "RQ"):
        assert key in written


def test_saving_writes_only_the_user_file(tmp_path, monkeypatch):
    """Save writes custom_materials.yaml. The packaged catalogue is untouched:
    it belongs to WIMBA, and everyone pulls it."""
    target = tmp_path / "custom_materials.yaml"
    monkeypatch.chdir(tmp_path)          # so nothing above the repo leaks in
    monkeypatch.setenv("WIMBA_MATERIALS", str(target))
    packaged_before = materials.CATALOGUE.read_text()
    materials.reload()
    try:
        materials.save_custom({"my-alloy": {"sigma": 2.5e6, "note": "measured"}})
        materials.reload()
        assert materials.parameters("my-alloy")["sigma"] == pytest.approx(2.5e6)
        assert materials.origin("my-alloy") == "custom file"
        assert sigma_table()["my-alloy"] == pytest.approx(2.5e6)
        # what was written is the user's file, and it says what we put in it
        written = yaml.safe_load(target.read_text())
        assert written["materials"]["my-alloy"]["sigma"] == pytest.approx(2.5e6)
    finally:
        monkeypatch.delenv("WIMBA_MATERIALS", raising=False)
        materials.reload()
    assert materials.CATALOGUE.read_text() == packaged_before


def test_the_user_file_is_listed_first(tmp_path, monkeypatch):
    """The Materials tab shows your own materials on top; names() is what feeds
    it, so the order is what has to be right.

    This used to skip unless the machine running the tests happened to have a
    custom file - which meant it never ran anywhere. It makes its own now.
    """
    custom = tmp_path / "custom_materials.yaml"
    custom.write_text("materials:\n"
                      "  zzz-alloy:\n    sigma: 1.0e+6\n"
                      "  aaa-alloy:\n    sigma: 2.0e+6\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WIMBA_MATERIALS", str(custom))
    materials.reload()
    try:
        names = materials.names()
        mine = [n for n in names if materials.origin(n) == "custom file"]
        assert set(mine) == {"zzz-alloy", "aaa-alloy"}
        # first, and in the file's own order - not sorted behind WIMBA's back
        assert names[:2] == ["zzz-alloy", "aaa-alloy"]
    finally:
        monkeypatch.delenv("WIMBA_MATERIALS", raising=False)
        materials.reload()
