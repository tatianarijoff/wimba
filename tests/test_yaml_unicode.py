"""Files WIMBA writes keep non-ASCII text as written.

PyYAML escapes it by default, so a label such as "t = 10 µm" came back as
"t = 10 \\xB5m" every time a project was saved - a diff in a tracked example
that nobody made.
"""
from wimba.gui.model import machine_config, machine_config_text, new_machine


def test_machine_file_keeps_the_micro_sign():
    text = machine_config_text(machine_config(new_machine("t = 10 µm")))
    assert "t = 10 µm" in text
    assert "\\xB5" not in text
