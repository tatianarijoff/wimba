"""The beam: one degree of freedom, and a guard against writing it the wrong way."""
import numpy as np
import pytest

from wimba import Beam, Project, Scenario, materialize
from wimba.core.beam import PARTICLES, particle


def test_gamma_and_beta_are_the_same_number():
    b = Beam("proton", "gamma", 7461.0)
    assert b.beta == pytest.approx((1 - 1 / 7461.0 ** 2) ** 0.5)
    assert b.one_minus_beta == pytest.approx(1 / (2 * 7461.0 ** 2), rel=1e-3)


def test_energy_modes_agree_with_gamma():
    m = PARTICLES["proton"].mass_eV
    by_energy = Beam("proton", "energy", 7.0e12)
    by_gamma = Beam("proton", "gamma", 7.0e12 / m)
    assert by_energy.gamma == pytest.approx(by_gamma.gamma)
    assert by_energy.kinetic_eV == pytest.approx(7.0e12 - m)
    # p c = gamma beta m c^2
    assert by_energy.momentum_eV == pytest.approx(by_energy.gamma * by_energy.beta * m)


def test_kinetic_and_momentum_round_trip():
    b = Beam("proton", "kinetic", 1.4e9)                 # PSB at extraction
    assert Beam("proton", "gamma", b.gamma).kinetic_eV == pytest.approx(1.4e9)
    assert Beam("proton", "momentum", b.momentum_eV).gamma == pytest.approx(b.gamma)


@pytest.mark.parametrize("mode,value", [
    ("gamma", 7461.0),        # LHC flat top
    ("gamma", 479.605),       # LHC injection
    ("gamma", 27.7),          # SPS injection
    ("beta", 0.9),            # exact as written: gamma follows from it
    ("beta", 0.99),
    ("beta", 0.999),
    ("beta", 0.0146),         # ELENA
    ("energy", 7.0e12),
])
def test_well_posed_inputs_are_accepted(mode, value):
    assert Beam("proton", mode, value).gamma >= 1.0


@pytest.mark.parametrize("mode,value,wanted", [
    ("beta", 0.99999, "gamma"),      # beta cannot say what gamma is up here
    ("beta", 0.9999, "gamma"),
    ("gamma", 1.0001, "beta"),       # gamma cannot say what beta is down there
    ("gamma", 1.000107, "beta"),     # ELENA written the wrong way round
])
def test_ill_posed_inputs_are_refused_and_say_which_variable_to_use(mode, value, wanted):
    with pytest.raises(ValueError) as exc:
        Beam("proton", mode, value)
    assert f"Give the beam as {wanted}" in str(exc.value)


def test_more_digits_do_not_rescue_beta_at_lhc_energies():
    """Not a precision problem that typing can fix: pinning gamma to 1e-6 at
    gamma = 2e5 would need beta to 1e-17, past what a double holds."""
    with pytest.raises(ValueError):
        Beam("proton", "beta", 0.99999999999)


def test_the_guard_uses_the_digits_the_user_typed():
    # same float, written with more digits: still refused, and the message says so
    with pytest.raises(ValueError):
        Beam("proton", "beta", 0.99999, text="0.99999")


def test_particles_and_charges():
    assert particle("Proton") is PARTICLES["proton"]
    assert PARTICLES["electron"].charge == -1
    assert PARTICLES["lead208"].mass_number == 208
    with pytest.raises(ValueError, match="unknown particle"):
        Beam("muon", "gamma", 10.0)


def test_round_trip_through_a_dict_keeps_the_mode():
    b = Beam("proton", "beta", 0.0146)
    d = b.to_dict()
    assert d["mode"] == "beta" and d["beta"] == 0.0146
    again = Beam.from_dict(d)
    assert again.mode == "beta" and again.gamma == pytest.approx(b.gamma)


def test_from_dict_accepts_a_bare_gamma_and_infers_the_mode():
    assert Beam.from_dict(7461.0).gamma == 7461.0
    assert Beam.from_dict({"gamma": 479.605}).mode == "gamma"
    assert Beam.from_dict({"particle": "electron", "beta": 0.9}).particle == "electron"


def test_label_switches_variable_with_the_regime():
    assert "\u03b3" in Beam("proton", "gamma", 7461.0).label()
    assert "\u03b2" in Beam("proton", "beta", 0.0146).label()


def test_beam_reaches_the_resume(tmp_path):
    import yaml
    from wimba import Element, Explicit, Machine, Resonator, ResonatorProvider

    m = Machine()
    m.add_group("g").add(Element("c1", "rf", 1.0,
                                 ResonatorProvider([Resonator("zlong", 1e4, 1.0, 1e9)]),
                                 optics=Explicit(1.0, 1.0),
                                 meta={"position": 0.0, "beta_x": 1.0, "beta_y": 1.0,
                                       "info": {}}))
    proj = Project("P", freqs=np.linspace(1e8, 1e9, 8))
    sc = proj.add(Scenario("injection", m, beam=Beam("proton", "gamma", 479.605)))

    resume = yaml.safe_load(materialize(sc, tmp_path / "out").read_text())
    assert resume["beam"]["gamma"] == pytest.approx(479.605)
    assert resume["beam"]["particle"] == "proton"
