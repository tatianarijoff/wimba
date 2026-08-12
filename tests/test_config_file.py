"""The settings file: where it is found, what it controls."""
import os

import pytest
import yaml

from wimba import config as cfg
from wimba import logutil


@pytest.fixture
def clean_env(monkeypatch):
    for var in ("WIMBA_CONFIG", "WIMBA_LOG_LEVEL", "WIMBA_LOG_DIR",
                "WIMBA_LOG_TO_FILE", "WIMBA_PYTLWALL_PATH", "WIMBA_IW2D_BINARY"):
        monkeypatch.delenv(var, raising=False)


def test_a_wimba_yaml_above_the_working_dir_is_found(tmp_path, monkeypatch, clean_env):
    (tmp_path / "wimba.yaml").write_text("logging: {level: debug}\n")
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    monkeypatch.chdir(deep)
    assert cfg.local_config_path() == tmp_path / "wimba.yaml"
    assert cfg.config_path() == tmp_path / "wimba.yaml"
    assert "wimba.yaml" in cfg.config_source()


def test_without_one_the_user_config_is_used(tmp_path, monkeypatch, clean_env):
    monkeypatch.chdir(tmp_path)
    assert cfg.config_path() == cfg.user_config_path()


def test_the_env_variable_wins(tmp_path, monkeypatch, clean_env):
    (tmp_path / "wimba.yaml").write_text("logging: {level: debug}\n")
    elsewhere = tmp_path / "other.yaml"
    elsewhere.write_text("logging: {level: error}\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WIMBA_CONFIG", str(elsewhere))
    assert cfg.config_path() == elsewhere
    assert cfg.logging_settings()["level"] == "error"


def test_logging_settings_come_from_the_file(tmp_path, monkeypatch, clean_env):
    (tmp_path / "wimba.yaml").write_text(
        "logging: {level: debug, to_file: false, dir: ./logs, file: run.log}\n")
    monkeypatch.chdir(tmp_path)
    s = cfg.logging_settings()
    assert s["level"] == "debug" and s["to_file"] is False
    assert s["dir"] == "./logs" and s["file"] == "run.log"


def test_the_environment_overrides_the_file(tmp_path, monkeypatch, clean_env):
    (tmp_path / "wimba.yaml").write_text("logging: {level: debug, to_file: true}\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WIMBA_LOG_LEVEL", "warning")
    monkeypatch.setenv("WIMBA_LOG_TO_FILE", "0")
    s = cfg.logging_settings()
    assert s["level"] == "warning" and s["to_file"] is False


def test_a_relative_log_dir_is_taken_from_the_config_file(tmp_path, monkeypatch, clean_env):
    """`dir: ./logs` means the working copy the config sits in, not wherever the
    command happened to be run from."""
    (tmp_path / "wimba.yaml").write_text("logging: {dir: ./logs}\n")
    deep = tmp_path / "examples" / "run"
    deep.mkdir(parents=True)
    monkeypatch.chdir(deep)
    assert logutil.log_file_path() == tmp_path / "logs" / "wimba.log"


def test_file_logging_can_be_switched_off(tmp_path, monkeypatch, clean_env):
    (tmp_path / "wimba.yaml").write_text("logging: {to_file: false}\n")
    monkeypatch.chdir(tmp_path)
    assert logutil.attach_file_handler("wimba.test_off") is None


def test_the_template_is_valid_yaml_and_not_overwritten(tmp_path):
    path = cfg.write_template(tmp_path)
    data = yaml.safe_load(path.read_text())
    assert data["logging"]["level"] == "info" and data["logging"]["to_file"] is True
    assert "tools" in data
    with pytest.raises(FileExistsError):
        cfg.write_template(tmp_path)


def test_engine_location_reports_a_missing_engine_without_raising(clean_env):
    info = cfg.engine_location("iw2d")
    assert set(info) == {"available", "path", "version", "source"}


def test_tool_status_fills_in_the_per_engine_entries(clean_env):
    """cmd_status reads these keys; they used to be absent, so `wimba status`
    said "not importable" whatever was installed."""
    s = cfg.tool_status()
    for key in ("pytlwall", "iw2d"):
        assert isinstance(s.get(key), dict) and "available" in s[key]
    assert "logging" in s and "config_source" in s


def test_a_fresh_install_gets_a_config_written_for_it(tmp_path, monkeypatch, clean_env):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.chdir(tmp_path)
    created = cfg.ensure_user_config()
    assert created is not None and created.is_file()
    assert yaml.safe_load(created.read_text())["logging"]["level"] == "info"


def test_an_existing_config_is_never_overwritten(tmp_path, monkeypatch, clean_env):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.chdir(tmp_path)
    path = cfg.user_config_path()
    path.parent.mkdir(parents=True)
    path.write_text("logging: {level: debug}\n")
    assert cfg.ensure_user_config() is None
    assert "debug" in path.read_text()


def test_a_local_wimba_yaml_stops_the_user_config_being_created(tmp_path, monkeypatch,
                                                                clean_env):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    (tmp_path / "wimba.yaml").write_text("logging: {level: warning}\n")
    monkeypatch.chdir(tmp_path)
    assert cfg.ensure_user_config() is None
    assert not cfg.user_config_path().exists()


def test_the_shipped_defaults_file_is_what_init_writes(tmp_path):
    written = cfg.write_template(tmp_path).read_text()
    assert written == cfg.DEFAULTS.read_text()


def test_an_iw2d_checkout_path_is_put_on_sys_path(tmp_path, monkeypatch, clean_env):
    """The bridge imports the IW2D *package*; a checkout that is not pip-installed
    needs its folder on sys.path, exactly as pytlwall does."""
    import sys
    checkout = tmp_path / "IW2Dsrc"
    checkout.mkdir()
    (tmp_path / "wimba.yaml").write_text(f"tools: {{iw2d: {{path: {checkout}}}}}\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "path", list(sys.path))
    cfg._ensure_iw2d_on_path()
    assert str(checkout) in sys.path


def test_engine_location_for_iw2d_reports_the_package_not_the_binary(tmp_path,
                                                                     monkeypatch,
                                                                     clean_env):
    (tmp_path / "wimba.yaml").write_text(
        "tools: {iw2d: {binary: /nowhere/IW2D}}\n")
    monkeypatch.chdir(tmp_path)
    info = cfg.engine_location("iw2d")
    assert info["path"] != "/nowhere/IW2D"      # the legacy key is not what it reports


def test_the_template_documents_the_iw2d_path_key():
    """And shows no path to the compiled binary: the bridge imports the Python
    package, so an executable path in the example is the one thing a reader
    would copy and then wonder why nothing works."""
    text = cfg.template_text()
    assert "path: ~/CERN/impedance/IW2D" in text
    assert "WIMBA_IW2D_PATH" in text
    assert "cpp/IW2D" not in text


# ------------------------------------------------- declared vs actual imports
def _dist(spec: str) -> str:
    """Distribution name out of a requirement string."""
    import re as _re
    return _re.split(r"[\[<>=!;\s]", spec.strip(), 1)[0].lower()


def _dists_for(module: str) -> set:
    """Which distributions provide this import name, per the installed metadata."""
    from importlib.metadata import packages_distributions
    return set(packages_distributions().get(module, []))


def _import_names(dist: str) -> set:
    """The import names a distribution provides. Falls back to its own name when
    the distribution is not installed here."""
    from importlib.metadata import packages_distributions
    names = {m.lower() for m, ds in packages_distributions().items()
             if dist in {d.lower() for d in ds}}
    return names or {dist}



def test_every_third_party_import_is_declared(tmp_path):
    """A dependency that is imported but never declared works on the machine that
    wrote it and fails on every other one. This walks the package instead of
    trusting the pyproject to have kept up."""
    import ast
    import sys
    import tomllib
    from pathlib import Path

    root = Path(cfg.__file__).resolve().parent.parent
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    declared = {"wimba"}
    for spec in (project["dependencies"]
                 + [d for v in project["optional-dependencies"].values() for d in v]):
        declared.add(_dist(spec))
    # engines WIMBA locates itself rather than depending on
    declared |= {"pytlwall", "iw2d"}

    seen = set()
    for path in (root / "wimba").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                seen |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                seen.add(node.module.split(".")[0])
    external = {m for m in seen
                if m not in sys.stdlib_module_names and m != "__future__"}
    # the import name is not the distribution name: `import yaml` comes from
    # pyyaml, `import PIL` from pillow. Ask the installed metadata rather than
    # keeping a hand-written table that goes stale.
    undeclared = {m for m in external
                  if not ({d.lower() for d in _dists_for(m)} | {m.lower()}) & declared}
    assert not undeclared, f"imported but not declared in pyproject.toml: {undeclared}"


def test_nothing_is_declared_that_is_never_imported():
    """The mirror image: pyqtgraph sat in the gui extra for months without a
    single import. A dependency nobody uses is still a dependency everybody
    installs."""
    import ast
    import tomllib
    from pathlib import Path

    root = Path(cfg.__file__).resolve().parent.parent
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    seen = set()
    for path in (root / "wimba").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                seen |= {a.name.split(".")[0].lower() for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                seen.add(node.module.split(".")[0].lower())
    # test-only and build-only tools are not imported by the package itself
    exempt = {"pytest", "xwakes", "openpyxl", "setuptools"}
    declared = {}
    for extra, specs in project["optional-dependencies"].items():
        for spec in specs:
            declared[_dist(spec)] = extra
    for spec in project["dependencies"]:
        declared[_dist(spec)] = "core"
    unused = {d: e for d, e in declared.items()
              if d not in exempt and not _import_names(d) & seen}
    assert not unused, f"declared but never imported: {unused}"
