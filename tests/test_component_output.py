"""Where the Component bench keeps what it computes.

It used to be a temporary folder with a random name, gone on the next reboot,
while the videos promised the engine's input would still be there months later.
A component with a file now keeps its results beside it, as a machine does.
"""
from pathlib import Path

from wimba.gui.model import component_output_dir, new_element


def test_a_component_with_no_file_has_nowhere_lasting_to_go():
    assert component_output_dir(new_element("My Component")) is None


def test_its_results_sit_beside_its_file(tmp_path):
    el = new_element("My Component")
    el.source_path = str(tmp_path / "study" / "My_Component_component.yaml")
    assert component_output_dir(el) == \
        tmp_path / "study" / "My_Component_component_output"


def test_a_fresh_element_carries_no_path():
    """New Component and Use Selected Element must not inherit a location."""
    assert new_element("X").source_path == ""


def test_the_location_follows_the_file_not_the_element_name(tmp_path):
    el = new_element("Renamed later")
    el.source_path = str(tmp_path / "kicker.yaml")
    assert component_output_dir(el) == Path(tmp_path / "kicker_output")
