"""Logging levels, and the GUI loader rejecting assemble configs (the crash fix)."""
import logging

import pytest

from wimba.logutil import LEVELS, configure, get_logger, set_level


def test_levels_and_logger_names():
    assert set(LEVELS) == {"critical", "error", "warning", "info", "debug"}
    assert get_logger("mymod").name == "wimba.mymod"
    assert get_logger("wimba.x").name == "wimba.x"


def test_configure_and_set_level():
    configure("warning")
    import logging.handlers
    root = logging.getLogger("wimba")
    assert root.level == logging.DEBUG          # root open: handlers filter
    assert all(h.level == logging.WARNING for h in root.handlers
               if not isinstance(h, logging.handlers.RotatingFileHandler))
    set_level("debug")
    assert logging.getLogger("wimba").level == logging.DEBUG


def test_from_machine_file_rejects_assemble_config(tmp_path):
    # model.py has no Qt import, so this runs without a display
    from wimba.gui.model import from_machine_file
    cfg = tmp_path / "assemble.yaml"
    cfg.write_text("name: X\ngamma: 7000.0\noptics: x.tfs\ndefault_pipe: {method: pytlwall}\n"
                   "devices:\n  d: {source: chamber, radius_m: 0.02}\n")
    with pytest.raises(ValueError, match="assemble/run config"):
        from_machine_file(cfg)


def test_from_config_populates_machine(tmp_path):
    from wimba.gui.model import from_config
    (tmp_path / "m.tfs").write_text(
        '@ NAME %05s "T"\n* NAME S L BETX BETY\n$ %s %le %le %le %le\n'
        ' "C1" 100.0 0.6 130.0 85.0\n "C2" 145.0 1.0 110.0 160.0\n')
    (tmp_path / "c.yaml").write_text(
        "name: Mini\ngamma: 7000.0\noptics: m.tfs\ndefault_pipe: {method: pytlwall, radius_mm: 22}\n"
        "devices:\n  collimators:\n    source: chamber\n    name: C1\n"
        "    method: pytlwall\n    radius_m: 0.01\n    beta_x: 130\n    beta_y: 85\n"
        "    position: 100.0\n")
    gm = from_config(str(tmp_path / "c.yaml"))
    assert gm.name == "Mini"
    names = {g.name for g in gm.groups}
    assert "collimators" in names
    assert any(n.startswith("default resistive wall") for n in names)
    c1 = gm.groups[0].elements[0]
    assert c1.name == "C1" and c1.optics["bx"] == 130.0 and c1.optics["s"] == 100.0
    grp = next(g for g in gm.groups if g.name.startswith("default resistive wall"))
    assert "\u00d7" in grp.name                          # multiplicity lives on the group
    pipe = grp.elements[0]
    assert "(" not in pipe.name                          # element name stays clean
    assert pipe.geometry.get("radius") == 0.022          # the pipe shows its geometry
    assert pipe.layers and "sigma" in pipe.layers[0]     # ... and its wall build-up


def test_method_helpers():
    from wimba.gui.model import (METHODS, method_base, method_label,
                                 method_needs_file, method_weighted)
    # only imported data can arrive already weighted: for everything else WIMBA
    # does the weighting itself, so offering "(weighted)" would offer to do it twice
    assert "pytlwall" in METHODS and "pytlwall (weighted)" not in METHODS
    assert "precalculated (weighted)" in METHODS
    assert len(METHODS) == 5
    assert method_base("precalculated (weighted)") == "precalculated"
    assert method_weighted("precalculated (weighted)")
    assert not method_weighted("resonator")
    assert method_label("precalculated", True) == "precalculated (weighted)"
    assert method_needs_file("precalculated") and not method_needs_file("pytlwall")


def test_element_to_config_and_run(tmp_path):
    """The single-element emitter produces a runnable config: grid/gamma
    inherited, geometry/layers/beta from the element; the run computes it."""
    pytest.importorskip("pytlwall")
    import numpy as np
    import yaml

    from wimba.gui.model import GElement, default_models, element_to_config
    from wimba.run import run as run_study

    el = GElement(name="lhc_default_pipe  (\u00d711188 lattice segments)",
                  category="default_pipe",
                  geometry={"shape": "ELLIPTICAL", "radius": 0.0184,
                            "hor": 0.0232, "ver": 0.0184},
                  optics={"bx": 2.0, "by": 1.0, "l": 1.0},
                  layers=[{"type": "CW", "thickness": 75e-6, "sigma": 2.0e9},
                          {"type": "CW", "thickness": 1.0e-3, "sigma": 1.4e6},
                          {"type": "V", "thickness": "inf", "boundary": True}],
                  models=default_models("pytlwall"))
    cfg = element_to_config(el, base_cfg={"gamma": 7000.0,
                                          "grid": {"frequency": {"min": 1e6, "max": 1e9,
                                                                 "n": 6, "log": True}}})
    assert cfg["name"] == "lhc_default_pipe_single"          # suffix stripped
    spec = cfg["devices"]["single"]
    assert spec["shape"] == "ELLIPTICAL" and spec["beta_x"] == 2.0
    assert len(spec["layers"]) == 3

    path = tmp_path / "single.yaml"
    path.write_text(yaml.safe_dump(cfg))
    info = run_study(path, out_dir=tmp_path / "out")
    assert info["stats"]["computed"] == 1
    per_dev = tmp_path / "out" / "single_elements" / "single" / "lhc_default_pipe.csv"
    assert per_dev.is_file()                                  # element has its own output


def test_element_to_config_rejects_non_pytlwall():
    from wimba.gui.model import GElement, default_models, element_to_config
    el = GElement(name="RF", geometry={"radius": 0.02},
                  models=default_models("resonator"))
    with pytest.raises(ValueError, match="resonator"):
        element_to_config(el)


def test_models_fill_no_wake_no_duplicates():
    """The Models table lists each impedance quantity once (no wake row - the
    wake has its own Calculate actions), for both loaded and new elements."""
    from wimba.gui.model import QUANTITIES, default_models

    ms = default_models("pytlwall")
    qs = [m.q for m in ms]
    assert "wake" not in qs
    assert len(qs) == len(set(qs)) == len(QUANTITIES) - 1


def test_element_compare_entries_end_to_end(tmp_path):
    """Additional calculations: the emitter adds compare devices; the run
    computes base + compares side by side (single-element study)."""
    pytest.importorskip("pytlwall")
    import numpy as np
    import yaml

    from wimba.gui.model import GElement, GModel, default_models, element_to_config
    from wimba.io.tables import write_impedance
    from wimba.run import run as run_study

    f = np.logspace(6, 9, 30)
    write_impedance(tmp_path / "zlong_cst.dat", f, 7.0 / f + 1j / f, "z")

    el = GElement(name="PIPE", geometry={"radius": 0.02},
                  optics={"bx": 1.0, "by": 1.0, "l": 1.0},
                  layers=[{"type": "CW", "thickness": 0.002, "sigma": 1.4e6}],
                  models=default_models("pytlwall"))
    el.compare.append(GModel(q="ZLong", enabled=True, method="precalculated",
                             file=str(tmp_path / "zlong_cst.dat")))

    cfg = element_to_config(el, base_cfg={"gamma": 7000.0,
                                          "grid": {"frequency":
                                                   {"min": 1e6, "max": 1e9, "n": 8,
                                                    "log": True}}})
    assert "compare_0" in cfg["devices"]
    assert cfg["output"] == ["PIPE", "PIPE[precalculated ZLong]"]

    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump(cfg))
    info = run_study(path, out_dir=tmp_path / "out")
    assert info["stats"]["computed"] == 2                     # base + compare
    se = tmp_path / "out" / "single_elements"
    assert (se / "single" / "PIPE.csv").is_file()
    assert (se / "compare_0" / "PIPE_precalculated_ZLong_.csv").is_file() or \
           any(se.glob("compare_0/*.csv"))                    # compare has its own CSV


def test_component_bench_accumulates(tmp_path):
    """Component bench: component_config labels sources by method, and merge
    accumulates runs so different calculations sit side by side."""
    pytest.importorskip("pytlwall")
    import numpy as np
    import yaml

    from wimba.gui.model import GElement, component_config, default_models
    from wimba.gui.results import ResultsModel
    from wimba.io.tables import write_impedance
    from wimba.run import run as run_study

    el = GElement(name="COMP", geometry={"radius": 0.02},
                  optics={}, layers=[{"type": "CW", "thickness": 0.002,
                                      "sigma": 1.4e6}],
                  models=default_models("pytlwall"))
    grid = {"gamma": 7000.0,
            "grid": {"frequency": {"min": 1e6, "max": 1e9, "n": 8, "log": True}}}

    cfg1 = component_config(el, "pytlwall", base_cfg=grid)
    assert cfg1["output"] == ["COMP[pytlwall]"]
    p1 = tmp_path / "c1.yaml"; p1.write_text(yaml.safe_dump(cfg1))
    run_study(p1, out_dir=tmp_path / "o1")

    f = np.logspace(6, 9, 20)
    write_impedance(tmp_path / "z.dat", f, 5.0 / f + 0j, "z")
    cfg2 = component_config(el, "precalculated", base_cfg=grid,
                            data_file=str(tmp_path / "z.dat"))
    assert cfg2["output"][0].startswith("COMP[precalculated: ")
    p2 = tmp_path / "c2.yaml"; p2.write_text(yaml.safe_dump(cfg2))
    run_study(p2, out_dir=tmp_path / "o2")

    m = ResultsModel().load(tmp_path / "o1")
    m.merge(tmp_path / "o2")                      # accumulate, not replace
    names = [k for k in m.sources if "[" in k]
    assert any("pytlwall]" in n for n in names)
    assert any("precalculated" in n for n in names)

    cfg3 = component_config(el, "IW2D", base_cfg=grid)
    assert cfg3["devices"]["bench"]["method"] == "iw2d"   # plumbing ready for the binary


def test_file_logging(tmp_path, monkeypatch):
    """The rotating file log captures DEBUG regardless of console level."""
    import logging

    from wimba.logutil import attach_file_handler, log_file_path
    monkeypatch.setenv("WIMBA_LOG_DIR", str(tmp_path))
    path = attach_file_handler()
    assert path == log_file_path()
    logging.getLogger("wimba.gui").debug("post-mortem line")
    for h in logging.getLogger("wimba").handlers:
        h.flush()
    assert "post-mortem line" in path.read_text()


def test_element_uids_are_session_unique():
    """Elements carry a session uid: names are descriptors, identity is the
    uid (homonyms and renames cannot confuse the GUI)."""
    from pathlib import Path
    from wimba.gui.model import GElement, from_config
    a, b = GElement(name="X"), GElement(name="X")
    assert a.uid != b.uid
    # SubLHC is self-contained: its optics table is tracked in the repository,
    # unlike the LHC example, whose twiss file is distributed separately
    # (see docs/DATA.md). Resolved from this file so the test does not depend
    # on the working directory.
    cfg = Path(__file__).resolve().parents[1] / "examples/SubLHC/SubLHC_input.yaml"
    gm = from_config(str(cfg))
    uids = [el.uid for g in gm.groups for el in g.elements]
    assert len(uids) == len(set(uids))


def test_resolve_data_path_uses_study_data_dir(tmp_path, monkeypatch):
    """A study points at its own data with a 'data_dir:' key: no environment
    variable, and two studies can sit on different disks."""
    from wimba.config import resolve_data_path
    monkeypatch.delenv("WIMBA_DATA_DIR", raising=False)
    shared = tmp_path / "shared_optics"; shared.mkdir()
    (shared / "twiss.tfs").write_text("@ NAME %05s \"TWISS\"\n")
    study = tmp_path / "study"; study.mkdir()

    # absolute, relative to the config, and a list of candidates all work
    assert resolve_data_path("data/twiss.tfs", study,
                             study_dirs=str(shared)) == shared / "twiss.tfs"
    assert resolve_data_path("data/twiss.tfs", study,
                             study_dirs="../shared_optics") == shared / "twiss.tfs"
    assert resolve_data_path("data/twiss.tfs", study,
                             study_dirs=["/nowhere", str(shared)]) == shared / "twiss.tfs"


def test_resolve_data_path_env_overrides_study(tmp_path, monkeypatch):
    """$WIMBA_DATA_DIR stays available as a per-invocation override, ahead of
    the study key."""
    from wimba.config import resolve_data_path
    a = tmp_path / "a"; a.mkdir(); (a / "twiss.tfs").write_text("a")
    b = tmp_path / "b"; b.mkdir(); (b / "twiss.tfs").write_text("b")
    monkeypatch.setenv("WIMBA_DATA_DIR", str(a))
    got = resolve_data_path("data/twiss.tfs", tmp_path, study_dirs=str(b))
    assert got == a / "twiss.tfs"


def test_resolve_data_path_falls_back_to_config_dir(tmp_path, monkeypatch):
    """With nothing configured, the reference resolves against the directory
    holding the study config, as before."""
    from wimba.config import resolve_data_path
    monkeypatch.delenv("WIMBA_DATA_DIR", raising=False)
    cfgdir = tmp_path / "study"; (cfgdir / "data").mkdir(parents=True)
    (cfgdir / "data" / "twiss.tfs").write_text("x")
    assert resolve_data_path("data/twiss.tfs", cfgdir) == cfgdir / "data" / "twiss.tfs"


def test_resolve_data_path_error_lists_what_was_tried(tmp_path, monkeypatch):
    """A missing data file names every location searched and says how to fix
    it, instead of a bare FileNotFoundError."""
    from wimba.config import resolve_data_path, DataFileNotFound
    monkeypatch.delenv("WIMBA_DATA_DIR", raising=False)
    with pytest.raises(DataFileNotFound) as exc:
        resolve_data_path("data/missing.tfs", tmp_path, what="optics table")
    msg = str(exc.value)
    assert "optics table" in msg
    assert "data_dir:" in msg
    assert "docs/DATA.md" in msg
    assert str(tmp_path / "data" / "missing.tfs") in msg


def test_element_own_grid_wins_over_open_machine_config():
    """An element loaded from its own pytlwall config belongs to no machine, so
    its gamma and frequency grid win over whatever config is open in the GUI --
    in both the single-element and the Component bench paths."""
    from wimba.gui.model import (GElement, component_config, default_models,
                                 element_to_config)

    machine = {"gamma": 7000.0,
               "grid": {"frequency": {"min": 1e5, "max": 1e10, "n": 100, "log": True}}}
    own = {"gamma": 1e5,
           "grid": {"frequency": {"min": 1e2, "max": 1e10, "n": 8001, "log": True}}}
    el = GElement(name="ferrite_kicker", geometry={"radius": 0.01},
                  layers=[{"type": "CW", "thickness": 0.002, "sigma": 1e6}],
                  models=default_models("pytlwall"), own_base=own)

    for cfg in (element_to_config(el, base_cfg=machine),
                component_config(el, "pytlwall", base_cfg=machine)):
        assert cfg["gamma"] == 1e5
        assert cfg["grid"]["frequency"]["min"] == 1e2
        assert cfg["grid"]["frequency"]["n"] == 8001


def test_element_without_own_config_inherits_the_machine():
    """An element that came from a machine still inherits the machine's grid and
    gamma: the override applies only to elements carrying their own config."""
    from wimba.gui.model import (GElement, component_config, default_models,
                                 element_to_config)
    machine = {"gamma": 7000.0,
               "grid": {"frequency": {"min": 1e5, "max": 1e10, "n": 100, "log": True}}}
    el = GElement(name="pipe", geometry={"radius": 0.02},
                  layers=[{"type": "CW", "thickness": 0.002, "sigma": 1e6}],
                  models=default_models("pytlwall"))

    for cfg in (element_to_config(el, base_cfg=machine),
                component_config(el, "pytlwall", base_cfg=machine)):
        assert cfg["gamma"] == 7000.0
        assert cfg["grid"]["frequency"]["n"] == 100


def test_pytlwall_cfg_grid_reaches_the_element(tmp_path):
    """End to end: the [frequency_info] of a pytlwall config survives into the
    config actually handed to the compute engine."""
    from wimba.gui.model import GElement, default_models, element_to_config
    from wimba.io.pytlwall_cfg import read_chamber_cfg

    cfg_file = tmp_path / "kicker.cfg"
    cfg_file.write_text(
        "[base_info]\ncomponent_name = k\nchamber_shape = CIRCULAR\n"
        "pipe_radius_m = 0.01\npipe_len_m = 1.0\nbetax = 1.0\nbetay = 1.0\n\n"
        "[layers_info]\nnbr_layers = 1\n\n"
        "[layer0]\ntype = CW\nthick_m = 0.002\nsigmaDC = 1e6\n\n"
        "[boundary]\ntype = PEC\n\n"
        "[beam_info]\ngammarel = 7000.0\n\n"
        "[frequency_info]\nfmin = 2\nfmax = 10\nfstep = 3\n")

    data = read_chamber_cfg(str(cfg_file))
    geo = dict(data["geometry"]); layers = geo.pop("layers", []); geo.pop("name", None)
    own = {k: v for k, v in (("gamma", data["gamma"]), ("grid", data["grid"])) if v}
    el = GElement(name="k", geometry=geo, layers=layers,
                  optics={"bx": data["betax"], "by": data["betay"], "l": data["length"]},
                  models=default_models("pytlwall"), own_base=own)

    out = element_to_config(el, base_cfg={"gamma": 1.0,
                                          "grid": {"frequency": {"min": 1e5, "max": 1e10,
                                                                 "n": 100, "log": True}}})
    assert out["gamma"] == 7000.0
    assert out["grid"]["frequency"]["min"] == 100.0
    assert out["grid"]["frequency"]["max"] == 1e10
