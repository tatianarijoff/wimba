"""Single-chamber pytlwall calculation: the physics facts WIMBA relies on.

ZLong scales linearly with length, ZDipX scales linearly with beta (so computing
at beta=1 and weighting later is exact), the wall + space-charge terms are all
present, and Total = wall + ISC.
"""
import numpy as np
import pytest

pytest.importorskip("pytlwall")
from wimba.sources.pytlwall_bridge import compute_chamber

FREQS = np.logspace(5, 9, 8)


def test_zlong_linear_in_length():
    z1 = compute_chamber(FREQS, radius_m=0.02, length_m=1.0)["ZLong"]
    z2 = compute_chamber(FREQS, radius_m=0.02, length_m=2.0)["ZLong"]
    assert np.allclose(z2, 2.0 * z1, rtol=1e-6)


def test_dipole_linear_in_beta():
    z1 = compute_chamber(FREQS, radius_m=0.02, betax=1.0)["ZDipX"]
    z2 = compute_chamber(FREQS, radius_m=0.02, betax=2.0)["ZDipX"]
    assert np.allclose(z2, 2.0 * z1, rtol=1e-6)
    # longitudinal must NOT depend on beta
    zl1 = compute_chamber(FREQS, radius_m=0.02, betax=1.0)["ZLong"]
    zl2 = compute_chamber(FREQS, radius_m=0.02, betax=2.0)["ZLong"]
    assert np.allclose(zl1, zl2, rtol=1e-9)


def test_wall_and_space_charge_present():
    imp = compute_chamber(FREQS, radius_m=0.02)
    for key in ("ZLong", "ZDipX", "ZDipY", "ZQuadX", "ZQuadY",
                "ZLongISC", "ZDipISC", "ZLongDSC"):
        assert key in imp
    # pytlwall convention: total = wall + indirect space charge
    assert np.allclose(imp["ZLongTotal"], imp["ZLong"] + imp["ZLongISC"], rtol=1e-6)


def test_multilayer_collimator_like():
    layers = [{"material": "cfc", "thickness": 0.025}]
    imp = compute_chamber(FREQS, radius_m=0.003, layers=layers, length_m=1.0)
    assert np.all(np.isfinite(imp["ZLong"]))


def test_build_flow_computes_pytlwall(tmp_path):
    """A 'build' machine with a pytlwall element now computes (not left empty),
    using the same engine as run."""
    from wimba import ResultStore, load_project, materialize
    from wimba.sources.pytlwall_bridge import compute_chamber

    (tmp_path / "m.tfs").write_text(
        '@ NAME %05s "T"\n* NAME S L BETX BETY\n$ %s %le %le %le %le\n'
        ' "C1" 100.0 1.0 130.0 85.0\n')
    (tmp_path / "c.yaml").write_text(
        "name: WallBuild\noptics: m.tfs\n"
        "grid:\n  frequency: {min: 1.0e7, max: 1.0e9, n: 10, log: true}\n"
        "  time: {min: 0.0, max: 5.0e-9, n: 10}\n"
        "groups:\n  pipes:\n    - name: C1\n      source: pytlwall\n"
        "      radius_m: 0.02\n      length: 1.0\n"
        "      layers: [{material: copper, thickness: 0.002}]\n")

    proj = load_project(tmp_path / "c.yaml")
    materialize(proj, tmp_path / "out")
    store = ResultStore(tmp_path / "out")
    z = store.impedance()
    assert "zlong" in z and np.any(np.abs(z["zlong"]) > 0)          # actually computed
    # longitudinal has beta power 0, length 1 -> equals the raw chamber
    expected = compute_chamber(proj.freqs, radius_m=0.02,
                               layers=[{"material": "copper", "thickness": 0.002}],
                               length_m=1.0)["ZLong"]
    assert np.allclose(z["zlong"], expected, rtol=1e-6)


def test_full_layer_parameters_and_boundary_match_pytlwall():
    """Full pytlwall layer parameters pass through, including an explicit
    conductor boundary (not the default vacuum)."""
    import pytlwall
    from wimba.sources.pytlwall_bridge import compute_chamber

    f = np.logspace(3, 10, 20)
    layers = [
        {"type": "CW", "thickness": 5e-7, "sigma": 1e6, "epsr": 1.0, "tau": 0.0, "muinf_Hz": 0.0},
        {"type": "CW", "thickness": "inf", "sigma": 1e9, "boundary": True},   # conductor boundary
    ]
    wimba_z = compute_chamber(f, radius_m=0.0184, layers=layers, length_m=1.0,
                              gamma=10000.0)["ZLong"]

    L0 = pytlwall.Layer(layer_type="CW", thick_m=5e-7, sigmaDC=1e6)
    Lb = pytlwall.Layer(layer_type="CW", thick_m=np.inf, sigmaDC=1e9, boundary=True)
    ch = pytlwall.Chamber(pipe_len_m=1.0, pipe_rad_m=0.0184, chamber_shape="CIRCULAR",
                          betax=1.0, betay=1.0, layers=[L0, Lb])
    ref = pytlwall.TlWall(chamber=ch, beam=pytlwall.Beam(gammarel=10000.0),
                          frequencies=pytlwall.Frequencies(freq_list=list(f))
                          ).get_all_impedances()["ZLong"]
    assert np.allclose(wimba_z, ref, rtol=1e-9)
