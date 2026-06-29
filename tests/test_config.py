"""Tool-location config: precedence, errors, and the setup/status CLI."""
from pathlib import Path

import pytest

from wimba import cli
from wimba import config as cfg


@pytest.fixture
def tmp_cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("WIMBA_CONFIG", str(tmp_path / "config.yaml"))
    monkeypatch.delenv("WIMBA_IW2D_BINARY", raising=False)
    monkeypatch.delenv("WIMBA_PYTLWALL_PATH", raising=False)
    return tmp_path / "config.yaml"


def _fake_exe(p: Path) -> Path:
    p.write_text("#!/bin/sh\n")
    p.chmod(0o755)
    return p


def test_config_roundtrip(tmp_cfg):
    cfg.save_config({"tools": {"iw2d": {"binary": "/x/IW2D"}}})
    assert tmp_cfg.is_file()
    assert cfg.load_config()["tools"]["iw2d"]["binary"] == "/x/IW2D"


def test_iw2d_precedence(tmp_path, tmp_cfg, monkeypatch):
    cfg_bin = _fake_exe(tmp_path / "IW2D_cfg")
    env_bin = _fake_exe(tmp_path / "IW2D_env")
    exp_bin = _fake_exe(tmp_path / "IW2D_exp")
    cfg.save_config({"tools": {"iw2d": {"binary": str(cfg_bin)}}})
    assert cfg.iw2d_binary() == cfg_bin                       # from config
    monkeypatch.setenv("WIMBA_IW2D_BINARY", str(env_bin))
    assert cfg.iw2d_binary() == env_bin                       # env beats config
    assert cfg.iw2d_binary(explicit=str(exp_bin)) == exp_bin  # explicit beats env


def test_iw2d_missing_raises(tmp_cfg):
    with pytest.raises(cfg.ToolNotConfigured):
        cfg.iw2d_binary()
    assert cfg.iw2d_binary(required=False) is None


def test_iw2d_bad_path_raises(tmp_cfg):
    cfg.save_config({"tools": {"iw2d": {"binary": "/no/such/IW2D"}}})
    with pytest.raises(cfg.ToolNotConfigured):
        cfg.iw2d_binary()


def test_cli_setup_writes_and_reports(tmp_path, tmp_cfg, capsys):
    binary = _fake_exe(tmp_path / "IW2D")
    rc = cli.main(["setup", "--non-interactive", "--iw2d", str(binary)])
    assert rc == 0
    assert cfg.load_config()["tools"]["iw2d"]["binary"] == str(binary)
    assert "IW2D binary" in capsys.readouterr().out


def test_cli_status_without_config(tmp_cfg, capsys):
    assert cli.main(["status"]) == 0
    assert "not configured" in capsys.readouterr().out
