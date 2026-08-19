"""Bridge to pytlwall: single-chamber impedance calculation (WIMBA does not
replace pytlwall - it calls it).

Builds a pytlwall Chamber + Beam + Frequencies and returns get_all_impedances()
computed at beta = 1, so WIMBA applies the beta weighting afterwards. Both the
wall terms and the space-charge terms (ISC/DSC) are in the returned dict.

Material conductivities are approximate placeholders for now; they will be set to
proper values later.
"""
from __future__ import annotations

import numpy as np

# approximate DC conductivities [S/m] - placeholders, to be refined
# The name -> conductivity table used to live here. It is data, not physics
# this module performs, and keeping it in code meant a second copy appeared the
# moment anything else needed the same list. It is now wimba/defaults/materials.yaml,
# read through wimba.materials, which is also what the interface offers.
from ..materials import DEFAULT_SIGMA, sigma_of  # noqa: E402,F401


def _one_layer(pytlwall, lay, boundary=False):
    """Build a pytlwall Layer, passing through the full parameter set."""
    thick = lay.get("thickness", lay.get("thick_m", 0.002))
    thick = np.inf if str(thick).lower() == "inf" else float(thick)
    ltype = str(lay.get("type", "CW"))
    sigma = lay.get("sigma", lay.get("sigmaDC"))
    if sigma is not None:
        sigma = float(sigma)
    elif ltype.upper() in ("V", "PEC", "PMC"):
        sigma = 1.0e6                    # vacuum / perfect conductors: value unused
    else:
        sigma = _sigma(lay.get("material"))
    k = lay.get("k_Hz", lay.get("k", np.inf))
    k = np.inf if str(k).lower() == "inf" else float(k)
    return pytlwall.Layer(
        layer_type=ltype,
        thick_m=thick,
        sigmaDC=sigma,
        muinf_Hz=float(lay.get("muinf_Hz", lay.get("muinf", 0.0))),
        k_Hz=k,
        epsr=float(lay.get("epsr", 1.0)),
        tau=float(lay.get("tau", 0.0)),
        RQ=float(lay.get("RQ", 0.0)),
        boundary=boundary,
    )


def _build_layers(pytlwall, layers):
    """Build the layer stack. Each layer dict may carry any pytlwall Layer field
    (type, thickness/thick_m, sigma/sigmaDC or material, muinf_Hz, k_Hz, epsr,
    tau, RQ). The boundary is the layer marked ``boundary: true``; if none is,
    a vacuum boundary is appended (back-compatible default)."""
    layers = layers or [{"material": "copper", "thickness": 0.002}]
    has_boundary = any(lay.get("boundary") for lay in layers)
    built = [_one_layer(pytlwall, lay, boundary=bool(lay.get("boundary"))) for lay in layers]
    if not has_boundary:
        built.append(pytlwall.Layer(layer_type="V", thick_m=np.inf, boundary=True))
    return built


def _sigma(material):
    return sigma_of(material)


def require_gamma(gamma, what="this calculation"):
    """No gamma, no result.

    There used to be a default of 7000 in every signature that takes a gamma, so a
    machine that never mentioned one was quietly computed as if it were the LHC at
    top energy. Nothing in the output said so. An explicit error is the only honest
    behaviour: gamma is physics, not a formatting detail.
    """
    if gamma is None:
        raise ValueError(
            f"{what} needs a relativistic gamma and none was given. Set the beam "
            "on the scenario (beam: {particle: proton, gamma: ...}) or pass gamma "
            "explicitly.")
    return float(gamma)


#: pytlwall's own default for the test particle's transverse offset. WIMBA
#: never invents a value: it passes what the config states, and leaves the
#: default to pytlwall when nothing is stated - but it reports which one is in
#: use, because a number that decides a result should not be invisible.
#:
#: Only the space-charge terms depend on it; ZLong does not use it at all. It
#: still matters that it travels: a chamber cfg written with 0.01 and read back
#: at 0.001 is not the same calculation.
PYTLWALL_TEST_BEAM_SHIFT = None      # None = leave pytlwall's own default


def _beam(pytlwall, gamma, test_beam_shift=None):
    """pytlwall's Beam, with the test shift only when one was stated.

    Passing None would override pytlwall's own default with nothing; not
    passing it at all is what leaves the engine in charge of its default.
    """
    if test_beam_shift is None:
        return pytlwall.Beam(gammarel=float(gamma))
    return pytlwall.Beam(gammarel=float(gamma),
                         test_beam_shift=float(test_beam_shift))


def compute_chamber(freqs, radius_m, layers=None, length_m=1.0,
                    shape="CIRCULAR", hor_m=None, ver_m=None,
                    gamma=None, betax=1.0, betay=1.0, test_beam_shift=None):
    """Return pytlwall's get_all_impedances() for one chamber on `freqs`."""
    gamma = require_gamma(gamma, "a chamber impedance")
    try:
        import pytlwall
    except ImportError as exc:
        raise ImportError(
            "pytlwall is required for 'pytlwall' calculations but is not installed "
            "in this environment. Install it into your venv, e.g.\n"
            "    pip install -e <path to pytlwall>\n"
            "    pip install git+https://github.com/tatianarijoff/pytlwall.git"
        ) from exc

    chamber = pytlwall.Chamber(pipe_len_m=float(length_m), pipe_rad_m=float(radius_m),
                               pipe_hor_m=hor_m, pipe_ver_m=ver_m, chamber_shape=shape,
                               betax=float(betax), betay=float(betay),
                               layers=_build_layers(pytlwall, layers))
    beam = _beam(pytlwall, gamma, test_beam_shift)
    frequencies = pytlwall.Frequencies(freq_list=list(np.asarray(freqs, dtype=float)))
    wall = pytlwall.TlWall(chamber=chamber, beam=beam, frequencies=frequencies)
    return wall.get_all_impedances()


# standard WIMBA components produced from a chamber
COMPONENTS = ("ZLong", "ZDipX", "ZDipY", "ZQuadX", "ZQuadY")


def chamber_terms(freqs, radius_m, layers=None, length_m=1.0, betax=1.0, betay=1.0,
                  gamma=None, space_charge=False, shape="CIRCULAR",
                  hor_m=None, ver_m=None, test_beam_shift=None):
    """Compute a chamber and return the beta-weighted WIMBA components.

    The chamber is evaluated at beta = 1 (beta-free), then WIMBA applies the beta
    weighting: dipolar and quadrupolar scale with beta, longitudinal does not. If
    space_charge is True the indirect space charge is returned as SEPARATE
    components (ZLongISC, ZDipXISC, ...), beta-weighted; the full impedance is
    wall + ISC, summed downstream.
    """
    imp = compute_chamber(freqs, radius_m, layers=layers, length_m=length_m,
                          shape=shape, hor_m=hor_m, ver_m=ver_m, gamma=gamma,
                          betax=1.0, betay=1.0,
                          test_beam_shift=test_beam_shift)
    out = {
        "ZLong":  imp["ZLong"],
        "ZDipX":  imp["ZDipX"] * betax,
        "ZDipY":  imp["ZDipY"] * betay,
        "ZQuadX": imp["ZQuadX"] * betax,
        "ZQuadY": imp["ZQuadY"] * betay,
    }
    if space_charge:
        out["ZLongISC"] = imp["ZLongISC"]
        out["ZDipXISC"] = imp["ZDipISC"] * betax
        out["ZDipYISC"] = imp["ZDipISC"] * betay
        out["ZQuadXISC"] = imp["ZQuadISC"] * betax
        out["ZQuadYISC"] = imp["ZQuadISC"] * betay
    return out


WAKE_COMPONENTS = ("WLong", "WDipX", "WDipY", "WQuadX", "WQuadY")


def chamber_wake(times, radius_m, layers=None, length_m=1.0, betax=1.0, betay=1.0,
                 test_beam_shift=None,
                 gamma=None, shape="CIRCULAR", hor_m=None, ver_m=None):
    """Compute a chamber's wake with pytlwall (TLWallWake), beta-weighted.

    Evaluated at beta = 1; WIMBA applies the beta weighting (transverse scale with
    beta, longitudinal does not). This is the real wake from pytlwall, not a
    Fourier transform of the impedance.
    """
    try:
        import pytlwall
    except ImportError as exc:
        raise ImportError(
            "pytlwall is required for 'pytlwall' wake calculations but is not "
            "installed. Install it, e.g.  pip install -e <path to pytlwall>"
        ) from exc

    chamber = pytlwall.Chamber(pipe_len_m=float(length_m), pipe_rad_m=float(radius_m),
                               pipe_hor_m=hor_m, pipe_ver_m=ver_m, chamber_shape=shape,
                               betax=1.0, betay=1.0, layers=_build_layers(pytlwall, layers))
    beam = _beam(pytlwall, gamma, test_beam_shift)
    times_obj = pytlwall.Times(time_list=list(
        np.where(np.asarray(times, dtype=float) <= 0.0, 1.0e-15,
                 np.asarray(times, dtype=float))))
    w = pytlwall.TLWallWake(chamber=chamber, beam=beam, times=times_obj)
    return {
        "WLong":  np.asarray(w.WLong),
        "WDipX":  np.asarray(w.WDipX) * betax,
        "WDipY":  np.asarray(w.WDipY) * betay,
        "WQuadX": np.asarray(w.WQuadX) * betax,
        "WQuadY": np.asarray(w.WQuadY) * betay,
    }


# ---------------------------------------------------------------------------
# Provider for the build flow (Machine/materialize): same engine, lazy terms.
# The chamber is evaluated at beta = 1; the Machine applies the beta weighting.
# ---------------------------------------------------------------------------
from ..core.impedance_term import ImpedanceTerm   # noqa: E402
from ..core.terms import STANDARD_TERMS            # noqa: E402

# standard term -> (impedance key, wake key, indirect-space-charge key)
_CHAMBER_MAP = {
    "zlong":  ("ZLong",  "WLong",  "ZLongISC"),
    "zxdip":  ("ZDipX",  "WDipX",  "ZDipISC"),
    "zydip":  ("ZDipY",  "WDipY",  "ZDipISC"),
    "zxquad": ("ZQuadX", "WQuadX", "ZQuadISC"),
    "zyquad": ("ZQuadY", "WQuadY", "ZQuadISC"),
}


class ChamberProvider:
    """pytlwall-backed provider: gives a Machine element its wall (and optional
    space-charge) impedance/wake, computed lazily on whatever grid is supplied."""

    def __init__(self, radius_m, layers=None, length_m=1.0, gamma=None,
                 space_charge=False, shape="CIRCULAR", hor_m=None, ver_m=None,
                 test_beam_shift=None):
        self.radius = float(radius_m)
        self.layers = layers
        self.length = float(length_m)
        self.gamma = require_gamma(gamma, f'chamber of radius {radius_m} m')
        self.space_charge = bool(space_charge)
        self.shape = shape
        self.hor = hor_m
        self.ver = ver_m
        #: None means "leave pytlwall's own default"; a number means the config
        #: asked for it, and it must reach every calculation of this chamber
        self.test_beam_shift = test_beam_shift
        self._imp_cache = {}
        self._wake_cache = {}

    def _imp(self, freqs):
        freqs = np.asarray(freqs, dtype=float)
        key = freqs.tobytes()
        if key not in self._imp_cache:
            self._imp_cache[key] = compute_chamber(
                freqs, self.radius, self.layers, length_m=self.length,
                shape=self.shape, hor_m=self.hor, ver_m=self.ver,
                betax=1.0, betay=1.0, gamma=self.gamma,
                test_beam_shift=self.test_beam_shift)
        return self._imp_cache[key]

    def _wake(self, times):
        times = np.asarray(times, dtype=float)
        key = times.tobytes()
        if key not in self._wake_cache:
            self._wake_cache[key] = chamber_wake(
                times, self.radius, self.layers, length_m=self.length,
                shape=self.shape, hor_m=self.hor, ver_m=self.ver,
                betax=1.0, betay=1.0, gamma=self.gamma,
                test_beam_shift=self.test_beam_shift)
        return self._wake_cache[key]

    def _zfun(self, comp):
        return lambda f: self._imp(f)[comp]

    def _wfun(self, comp):
        return lambda t: self._wake(t)[comp]

    def terms(self, element):
        out = []
        for tkey, (zc, wc, isc) in _CHAMBER_MAP.items():
            tid = STANDARD_TERMS[tkey]
            out.append(ImpedanceTerm(id=tkey, tid=tid, origin="resistive_wall",
                                     z=self._zfun(zc), w=self._wfun(wc)))
            if self.space_charge:
                out.append(ImpedanceTerm(id=tkey, tid=tid, origin="space_charge",
                                         z=self._zfun(isc), w=None))
        return out
