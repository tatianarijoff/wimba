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
MATERIALS = {
    "cu": 5.9e7, "copper": 5.9e7,
    "stainless_steel": 1.4e6, "ss": 1.4e6, "ss304": 1.4e6,
    "graphite": 1.0e5, "cfc": 1.0e5,
    "mogr": 1.0e6, "inermet180": 4.0e6, "inermet": 4.0e6,
    "beam_screen": 5.9e7, "w": 1.8e7, "mo": 1.9e7,
}
DEFAULT_SIGMA = 1.0e6


def _sigma(material):
    if material is None:
        return DEFAULT_SIGMA
    return MATERIALS.get(str(material).lower(), DEFAULT_SIGMA)


def compute_chamber(freqs, radius_m, layers=None, length_m=1.0,
                    shape="CIRCULAR", hor_m=None, ver_m=None,
                    gamma=7000.0, betax=1.0, betay=1.0):
    """Return pytlwall's get_all_impedances() for one chamber on `freqs`."""
    import pytlwall

    built = []
    for lay in (layers or [{"material": "copper", "thickness": 0.002}]):
        built.append(pytlwall.Layer(layer_type="CW",
                                    thick_m=float(lay.get("thickness", 0.002)),
                                    sigmaDC=_sigma(lay.get("material"))))
    built.append(pytlwall.Layer(layer_type="V", thick_m=np.inf, boundary=True))

    chamber = pytlwall.Chamber(pipe_len_m=float(length_m), pipe_rad_m=float(radius_m),
                               pipe_hor_m=hor_m, pipe_ver_m=ver_m, chamber_shape=shape,
                               betax=float(betax), betay=float(betay), layers=built)
    beam = pytlwall.Beam(gammarel=float(gamma))
    frequencies = pytlwall.Frequencies(freq_list=list(np.asarray(freqs, dtype=float)))
    wall = pytlwall.TlWall(chamber=chamber, beam=beam, frequencies=frequencies)
    return wall.get_all_impedances()


# standard WIMBA components produced from a chamber
COMPONENTS = ("ZLong", "ZDipX", "ZDipY", "ZQuadX", "ZQuadY")


def chamber_terms(freqs, radius_m, layers=None, length_m=1.0, betax=1.0, betay=1.0,
                  gamma=7000.0, space_charge=False, shape="CIRCULAR",
                  hor_m=None, ver_m=None):
    """Compute a chamber and return the beta-weighted WIMBA components.

    The chamber is evaluated at beta = 1 (beta-free), then WIMBA applies the beta
    weighting: dipolar and quadrupolar scale with beta, longitudinal does not. If
    space_charge is True the indirect space charge (ISC) is added, matching
    pytlwall's Total = wall + ISC.
    """
    imp = compute_chamber(freqs, radius_m, layers=layers, length_m=length_m,
                          shape=shape, hor_m=hor_m, ver_m=ver_m, gamma=gamma,
                          betax=1.0, betay=1.0)
    out = {
        "ZLong":  imp["ZLong"],
        "ZDipX":  imp["ZDipX"] * betax,
        "ZDipY":  imp["ZDipY"] * betay,
        "ZQuadX": imp["ZQuadX"] * betax,
        "ZQuadY": imp["ZQuadY"] * betay,
    }
    if space_charge:
        out["ZLong"] = out["ZLong"] + imp["ZLongISC"]
        out["ZDipX"] = out["ZDipX"] + imp["ZDipISC"] * betax
        out["ZDipY"] = out["ZDipY"] + imp["ZDipISC"] * betay
        out["ZQuadX"] = out["ZQuadX"] + imp["ZQuadISC"] * betax
        out["ZQuadY"] = out["ZQuadY"] + imp["ZQuadISC"] * betay
    return out
