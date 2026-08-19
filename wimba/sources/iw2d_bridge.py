"""Bridge to IW2D (the 'iw2d' method).

IW2D ships a Python API on top of its C++ core (loaded through ``cppyy``), so a
run is an import and a function call, not a subprocess: WIMBA builds a
``RoundIW2DInput`` for the chamber and calls ``iw2d_round_impedance`` on the
requested frequencies. The legacy path -- writing an input file and executing
``roundchamber.x`` -- is not used.

The chamber interface mirrors the pytlwall bridge, so the same element
definition can be computed with either method and the results compared.

Two IW2D conventions differ from pytlwall and are handled here:

* **No perfect conductor.** IW2D's outermost layer is semi-infinite; there is no
  PEC. A layer declared ``PEC`` is approximated by a very low resistivity
  (:data:`PEC_RESISTIVITY`), as the IW2D documentation suggests. This is an
  approximation, not an equivalence, and it is reported to the caller.
* **Indirect space charge is included.** IW2D returns the *wall* impedance,
  which contains the indirect space-charge term; pytlwall keeps it as a separate
  component. The comparable pytlwall quantity is therefore ``ZLong + ZLongISC``,
  not ``ZLong`` alone.

See docs/IW2D.md for the full mapping and the comparison recipe.
"""
from __future__ import annotations

import numpy as np

from .pytlwall_bridge import require_gamma

#: Resistivity [Ohm.m] standing in for a perfect conductor. IW2D has no PEC
#: layer; its documentation suggests a very low resistivity instead, warning
#: that numerical issues may occur.
PEC_RESISTIVITY = 1.0e-15

#: IW2D column name -> WIMBA component name.
COLUMN_MAP = {
    "Zlong": "ZLong",
    "Zxdip": "ZDipX",
    "Zydip": "ZDipY",
    "Zxquad": "ZQuadX",
    "Zyquad": "ZQuadY",
}


def iw2d_available() -> bool:
    """True if the IW2D Python package can be imported.

    Importing IW2D loads its C++ core through cppyy, which needs GSL, MPFR and
    Arb present; a failure here usually means those libraries are missing
    rather than IW2D itself.
    """
    from ..config import iw2d_available as _available
    return _available()


def _import_iw2d():
    """Import the IW2D pieces the bridge needs.

    ``IW2D/__init__.py`` only loads the C++ libraries; the input dataclasses
    live in ``IW2D.interface``, so they are imported from there rather than from
    the package namespace.
    """
    from ..config import _ensure_iw2d_on_path
    _ensure_iw2d_on_path()          # a checkout named in the config, if any
    try:
        import IW2D  # noqa: F401   -- loads the C++ core through cppyy
    except ImportError as exc:
        raise ImportError(
            "IW2D is required for 'iw2d' calculations but is not importable in "
            "this environment.\n"
            "Install it into the same environment as WIMBA, as with pytlwall:\n"
            "    pip install cppyy\n"
            "    pip install -e <path to IW2D>\n"
            "IW2D is a binding over a C++ core, so its shared libraries must be "
            "available too (GSL, GMP, MPFR, Arb) -- from the system package "
            "manager or from conda.\n"
            "On Debian and Ubuntu Arb is packaged as 'flint-arb': set "
            "IW2D_FLINT_ARB=1 or the import fails on a library that is present.\n"
            "See docs/IW2D.md for the full procedure."
        ) from exc

    # IW2D itself imported cleanly, so the C++ libraries are in place. Anything
    # failing below is a layout difference in IW2D, not a missing dependency:
    # report it as such instead of repeating the installation advice.
    try:
        from IW2D.interface import (RoundIW2DInput, IW2DLayer,
                                    Eps1FromResistivity, Mu1FromSusceptibility)
        from IW2D.round_impedance import iw2d_round_impedance
    except ImportError as exc:
        raise ImportError(
            f"IW2D is installed but does not expose the expected interface "
            f"({exc}). This bridge targets the Python API with "
            "IW2D.interface.RoundIW2DInput / IW2DLayer and "
            "IW2D.round_impedance.iw2d_round_impedance, plus the "
            "Eps1FromResistivity / Mu1FromSusceptibility helpers; a different "
            "IW2D version may have moved them."
        ) from exc

    return (RoundIW2DInput, IW2DLayer, iw2d_round_impedance,
            Eps1FromResistivity, Mu1FromSusceptibility)


def _one_layer(lay, IW2DLayer, Eps1FromResistivity, Mu1FromSusceptibility):
    """Turn one WIMBA layer dict into an IW2D layer.

    The permittivity and permeability are built with IW2D's own function
    objects rather than with formulas rewritten here, so the material model is
    IW2D's by construction and stays correct if IW2D refines it.

    Unit and definition differences from pytlwall, all applied here:

    ==================  =========================  ===========================
    WIMBA / pytlwall    IW2D                       conversion
    ==================  =========================  ===========================
    ``sigma`` [S/m]     dc_resistivity [Ohm.m]     reciprocal
    ``tau``             resistivity relaxation [s] none
    ``epsr``            re_dielectric_constant     none
    ``muinf_Hz``        magnetic susceptibility    none
    ``k_Hz`` [Hz]       permeability relax. f [Hz] none
    ``thickness`` [m]   thickness [m]              none
    ==================  =========================  ===========================

    ``muinf_Hz`` reads like a relative permeability and is not one. pytlwall
    computes ``mur = 1 + muinf / (1 + j f/k)`` (pytlwall/layer.py, calc_mur), so
    the quantity it stores is already the susceptibility and passes through
    unchanged. Subtracting one from it - as this did - turned the default
    muinf = 0 into chi = -1, that is a relative permeability of zero, on every
    non-magnetic wall computed with IW2D.
    """
    ltype = str(lay.get("type", "CW")).upper()
    thick = lay.get("thickness", lay.get("thick_m", 0.002))
    thick = float("inf") if str(thick).lower() == "inf" else float(thick)

    sigma = lay.get("sigma", lay.get("sigmaDC"))
    if sigma is None and lay.get("material") is not None:
        # A layer can name its material instead of giving a number. The config
        # loader normally resolves that before we get here; doing it again means
        # the two engines agree even when this bridge is called directly, rather
        # than IW2D quietly falling back to 1e6 for a wall that says copper.
        from ..materials import sigma_of
        sigma = sigma_of(lay["material"])
    sigma = float(sigma) if sigma is not None else None

    if ltype == "V":
        # vacuum: infinite resistivity, no magnetisation
        rho, tau, epsr, chi, k_hz = float("inf"), 0.0, 1.0, 0.0, float("inf")
    elif ltype == "PEC":
        rho, tau, epsr, chi, k_hz = PEC_RESISTIVITY, 0.0, 1.0, 0.0, float("inf")
    else:
        if sigma is None:
            from ..materials import DEFAULT_SIGMA
            sigma = DEFAULT_SIGMA
        rho = float("inf") if sigma == 0 else 1.0 / sigma
        tau = float(lay.get("tau", 0.0))
        epsr = float(lay.get("epsr", 1.0))
        # pytlwall's muinf IS the susceptibility (see the docstring above), so
        # it is what IW2D wants. Its default is 0: a non-magnetic wall.
        chi = float(lay.get("muinf_Hz", lay.get("muinf", 0.0)) or 0.0)
        k_hz = lay.get("k_Hz", lay.get("k", float("inf")))
        k_hz = float("inf") if str(k_hz).lower() == "inf" else float(k_hz)

    if k_hz <= 0:
        raise ValueError(
            f"the permeability relaxation frequency must be positive; "
            f"got k_Hz={k_hz!r}. Use 'inf' for a non-dispersive material.")

    return IW2DLayer(
        thickness=thick,
        eps1=Eps1FromResistivity(dc_resistivity=rho,
                                 resistivity_relaxation_time=tau,
                                 re_dielectric_constant=epsr),
        mu1=Mu1FromSusceptibility(magnetic_susceptibility=chi,
                                  permeability_relaxation_frequency=k_hz),
    )


def _build_layers(layers, IW2DLayer, Eps1FromResistivity, Mu1FromSusceptibility):
    """Build the IW2D layer stack, innermost first.

    IW2D's last layer is semi-infinite by construction, so the outermost layer
    is extended to infinite thickness whatever the input says.
    """
    # The same wall pytlwall assumes when a chamber states no layers: naming
    # the material rather than a number is what keeps the two engines from
    # computing different default chambers (this used to say 5.96e7 while the
    # other bridge used copper's 5.9e7).
    layers = layers or [{"type": "CW", "thickness": 0.002, "material": "copper"}]
    built = []
    for i, lay in enumerate(layers):
        is_last = (i == len(layers) - 1) or bool(lay.get("boundary"))
        lay = dict(lay)
        if is_last:
            lay["thickness"] = float("inf")
        built.append(_one_layer(lay, IW2DLayer, Eps1FromResistivity,
                                Mu1FromSusceptibility))
        if is_last:
            break
    return tuple(built)


def compute_iw2d(freqs, radius_m, layers=None, length_m=1.0, shape="CIRCULAR",
                 betax=1.0, betay=1.0, gamma=None,
                 yokoya=None, return_notes=False):
    """Compute a round chamber's impedance with IW2D.

    Args:
        freqs: frequencies in Hz.
        radius_m: inner radius of the first layer, in metres.
        layers: WIMBA layer dicts, innermost first (the same shape the pytlwall
            bridge accepts).
        length_m: length of the structure in metres.
        shape: only ``CIRCULAR`` is supported here; IW2D does support flat
            geometries, through a different input object, but that path is not
            wired yet.
        gamma: relativistic gamma.
        yokoya: optional 5-tuple overriding the Yokoya factors
            (long, xdip, ydip, xquad, yquad). The default is the round-chamber
            set ``(1, 1, 1, 0, 0)``: the quadrupolar terms of a circular
            chamber are exactly zero.
        return_notes: also return a list of notes about approximations applied
            (currently: a PEC layer replaced by a low resistivity).

    Returns:
        A dict mapping WIMBA component names to complex arrays; with
        ``return_notes``, a ``(dict, notes)`` tuple.

    Raises:
        ImportError: IW2D or its C++ dependencies are not importable.
        ValueError: a non-circular shape was requested.
    """
    (RoundIW2DInput, IW2DLayer, iw2d_round_impedance,
     Eps1FromResistivity, Mu1FromSusceptibility) = _import_iw2d()

    if str(shape).upper() != "CIRCULAR":
        raise ValueError(
            f"the IW2D bridge computes circular chambers; got shape={shape!r}. "
            "IW2D does support flat geometries, through a different input "
            "object, but that path is not wired yet.")

    notes = []
    if any(str(l.get("type", "")).upper() == "PEC" for l in (layers or [])):
        notes.append(
            f"IW2D has no perfect-conductor layer: the PEC boundary was "
            f"approximated by a resistivity of {PEC_RESISTIVITY:g} Ohm.m. "
            "This is an approximation, and very low resistivities can cause "
            "numerical issues.")

    yk = tuple(yokoya) if yokoya else (1.0, 1.0, 1.0, 0.0, 0.0)
    inp = RoundIW2DInput(
        length=float(length_m),
        relativistic_gamma=require_gamma(gamma, 'an IW2D impedance'),
        calculate_wake=False,
        layers=_build_layers(layers, IW2DLayer, Eps1FromResistivity,
                             Mu1FromSusceptibility),
        inner_layer_radius=float(radius_m),
        yokoya_Zlong=yk[0], yokoya_Zxdip=yk[1], yokoya_Zydip=yk[2],
        yokoya_Zxquad=yk[3], yokoya_Zyquad=yk[4],
    )

    df, _meta = iw2d_round_impedance(inp, np.asarray(freqs, dtype=float))
    out = {COLUMN_MAP[c]: df[c].to_numpy() for c in df.columns if c in COLUMN_MAP}
    return (out, notes) if return_notes else out


class IW2DProvider:
    """Build-flow provider for IW2D, mirroring pytlwall's ChamberProvider."""

    def __init__(self, radius_m, layers=None, length_m=1.0, gamma=None,
                 iw2d_yokoya=None, **kw):
        self.radius = float(radius_m)
        self.layers = layers
        self.length = float(length_m)
        self.gamma = require_gamma(gamma, f'IW2D chamber of radius {radius_m} m')
        #: five factors that turn the round solve into another geometry; the
        #: IW2D path reads them, pytlwall applies its own tables instead
        self.yokoya = tuple(iw2d_yokoya) if iw2d_yokoya else None

    def terms(self, element):
        from ..core.terms import STANDARD_TERMS
        from ..core.impedance_term import ImpedanceTerm

        def z(f):
            return compute_iw2d(f, self.radius, self.layers,
                                length_m=self.length, gamma=self.gamma,
                                yokoya=self.yokoya)["ZLong"]
        return [ImpedanceTerm(id="zlong", tid=STANDARD_TERMS["zlong"],
                              origin="resistive_wall", z=z, w=None)]
