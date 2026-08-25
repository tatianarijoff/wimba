"""A file that is not there is a message, not a traceback."""
from pathlib import Path

import pytest

from wimba.cli import main
from wimba.config import DataFileNotFound, ToolNotConfigured
from wimba.errors import ConfigFileNotFound, WimbaError, check_input_file


@pytest.fixture
def example(tmp_path, monkeypatch):
    """A folder holding SubLHC_input.yaml, the file people mistype."""
    folder = tmp_path / "examples" / "SubLHC"
    folder.mkdir(parents=True)
    (folder / "SubLHC_input.yaml").write_text("name: SubLHC\n")
    monkeypatch.chdir(tmp_path)
    return folder


def test_missing_config_is_one_line_and_names_the_absolute_path(example, capsys):
    code = main(["build", "examples/SubLHC/SubLHC.yaml"])
    err = capsys.readouterr().err

    assert code == 2
    assert "Traceback" not in err
    assert "does not exist" in err
    # the resolved location, not just what was typed: a relative path in an
    # error message is only readable if you also know the working directory
    assert str(example / "SubLHC.yaml") in err
    # and the file that is actually there
    assert "SubLHC_input.yaml" in err


def test_directory_instead_of_file(example, capsys):
    code = main(["build", "examples/SubLHC"])
    err = capsys.readouterr().err

    assert code == 2
    assert "is a directory" in err
    assert "SubLHC_input.yaml" in err


def test_missing_folder_says_so(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code = main(["build", "nowhere/x.yaml"])
    err = capsys.readouterr().err

    assert code == 2
    assert "does not exist" in err
    assert str(tmp_path / "nowhere") in err


def test_the_check_covers_the_assembly_commands_too(example, capsys):
    for command in ("run", "assemble"):
        assert main([command, "examples/SubLHC/nope.yaml"]) == 2
        assert "assembly config" in capsys.readouterr().err


def test_a_deeper_missing_file_also_avoids_the_traceback(tmp_path, monkeypatch, capsys):
    """`show` fails inside the store, not in the loader, and still exits cleanly."""
    monkeypatch.chdir(tmp_path)
    code = main(["show", "no_such_results"])

    assert code == 2
    assert "Traceback" not in capsys.readouterr().err


def test_traceback_flag_lets_the_error_through(example):
    with pytest.raises(ConfigFileNotFound):
        main(["--traceback", "build", "examples/SubLHC/SubLHC.yaml"])


def test_an_existing_file_passes_through(example):
    path = example / "SubLHC_input.yaml"
    assert check_input_file(path) == Path(path)


def test_config_not_found_is_still_a_file_not_found_error():
    """Callers that already catch FileNotFoundError keep working."""
    assert issubclass(ConfigFileNotFound, FileNotFoundError)


def test_the_existing_user_facing_errors_are_wimba_errors():
    """So the CLI prints them as a line too, rather than crashing on a missing
    engine or an unresolvable data file."""
    assert issubclass(ToolNotConfigured, WimbaError)
    assert issubclass(DataFileNotFound, WimbaError)
