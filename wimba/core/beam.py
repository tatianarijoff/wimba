"""The beam a scenario is computed with: a particle, and one number that fixes
its velocity.

Only one number is free. Gamma, beta, total energy, kinetic energy and momentum
are five ways of writing the same degree of freedom, so `Beam` stores *which one
the user gave* and derives the rest. Storing the input rather than a canonical
gamma matters at both ends of the range: gamma is the well-conditioned variable
for the LHC and beta is the well-conditioned one for ELENA, and converting a
badly-written input into a canonical one only hides the problem.

Hence the guard in `_check_precision`: an input pins down the quantities derived
from it only to the precision it was written with, and the derived error is not
the input error. Writing beta = 0.99999 gives gamma = 223.6 +- 56; writing
gamma = 1.0001 gives beta to 25%. Both are refused, with the message saying which
variable to use instead. The check is symmetric by construction: it propagates the
input's own last-digit uncertainty and complains about whatever comes out badly
determined, without a hard-coded threshold on beta or gamma anywhere.

Only beta enters the field solution the impedance codes solve, so the particle
choice does not by itself change an impedance; it fixes the rest mass used for the
energy modes, and the charge and mass number that later matter for kicks and for
per-nucleon energies of ions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# relative precision demanded of any quantity *derived* from the user's input
TOLERANCE = 1e-6
# how much the conversion may amplify a relative wobble before the input is the
# wrong variable to be using at all
AMPLIFICATION = 1.0e3

MODES = ("gamma", "beta", "energy", "kinetic", "momentum")
_MODE_UNITS = {"gamma": "", "beta": "", "energy": "eV", "kinetic": "eV",
               "momentum": "eV/c"}


@dataclass(frozen=True)
class Particle:
    """Rest energy in eV, charge and mass number in units of the proton's."""
    name: str
    mass_eV: float
    charge: int = 1
    mass_number: int = 1


PARTICLES = {p.name: p for p in (
    Particle("proton",     938.272088e6,  1, 1),
    Particle("antiproton", 938.272088e6, -1, 1),
    Particle("electron",   0.51099895e6, -1, 1),
    Particle("positron",   0.51099895e6,  1, 1),
    Particle("lead208",    193.687e9,    82, 208),   # Pb 82+, fully stripped
)}


def particle(name) -> Particle:
    if isinstance(name, Particle):
        return name
    try:
        return PARTICLES[str(name).strip().lower()]
    except KeyError:
        raise ValueError(f"unknown particle '{name}'; known: "
                         f"{', '.join(sorted(PARTICLES))}") from None


def _last_digit(value, text: Optional[str] = None) -> float:
    """Half a unit in the last digit written - how much the input actually says.

    With no text, `repr` of the float is used: Python prints the shortest string
    that round-trips, which recovers the digits as they were typed in the YAML.
    """
    t = (text if text is not None else repr(float(value))).strip().lower()
    t = t.lstrip("+-")
    mant, _, exp = t.partition("e")
    shift = int(exp) if exp else 0
    decimals = len(mant.partition(".")[2])
    return 0.5 * 10.0 ** (shift - decimals)


def _gamma_from(mode: str, value: float, part: Particle) -> float:
    if mode == "gamma":
        if value < 1.0:
            raise ValueError(f"gamma = {value} is below 1")
        return float(value)
    if mode == "beta":
        if not 0.0 <= abs(value) < 1.0:
            raise ValueError(f"beta = {value} is not below 1")
        return 1.0 / (1.0 - value * value) ** 0.5
    if mode == "energy":                       # total energy per particle
        return float(value) / part.mass_eV
    if mode == "kinetic":
        return 1.0 + float(value) / part.mass_eV
    if mode == "momentum":                     # p c, in eV
        r = float(value) / part.mass_eV
        return (1.0 + r * r) ** 0.5
    raise ValueError(f"unknown mode '{mode}'; use one of {', '.join(MODES)}")


def _beta_from_gamma(gamma: float) -> float:
    return (1.0 - 1.0 / (gamma * gamma)) ** 0.5


@dataclass
class Beam:
    """A particle and the one number that fixes its velocity.

    Build it with the value the user gave and the mode they gave it in:

        Beam("proton", "gamma", 7461.0)          # LHC at flat top
        Beam("proton", "beta", 0.0146)           # ELENA
        Beam("proton", "energy", 7.0e12)         # same as the first, in eV

    Pass `text` when the value came from a widget, so the guard sees the digits
    the user actually typed rather than the float they became.
    """
    particle: str = "proton"
    mode: str = "gamma"
    value: float = 0.0
    text: Optional[str] = None

    def __post_init__(self):
        self.mode = str(self.mode).strip().lower()
        if self.mode not in MODES:
            raise ValueError(f"unknown mode '{self.mode}'; use one of {', '.join(MODES)}")
        part = particle(self.particle)
        self.particle = part.name
        self.value = float(self.value)
        self._gamma = _gamma_from(self.mode, self.value, part)
        self._beta = _beta_from_gamma(self._gamma)
        self._check_precision(part)

    # ---- the guard ----
    def _check_precision(self, part: Particle):
        """Refuse an input that does not determine what will be derived from it.

        Two things have to go wrong together, and requiring both is what keeps the
        guard from crying wolf:

          * the conversion is ill-conditioned - a relative wobble in the input
            comes out amplified by more than AMPLIFICATION in the derived
            quantity. beta -> gamma is amplified by (gamma*beta)**2, so beta stops
            being usable above gamma ~ 30 and gamma stops being usable below
            gamma ~ 1.0005, with a wide overlap in between where either is fine;
          * *and* the digits actually written are too few to survive that
            amplification.

        So beta = 0.9 is accepted (gamma = 2.294 follows from it exactly, the
        amplification is only 4), while beta = 0.99999 is refused (gamma = 224
        +- 67). Note that at LHC energies no number of digits rescues beta: at
        gamma = 2.2e5 pinning gamma down to 1e-6 would need beta to 1e-17, past
        what a double can hold. The message says so rather than inviting the user
        to keep typing nines.
        """
        rel_in = _last_digit(self.value, self.text) / abs(self.value or 1.0)
        for derived in ("gamma", "beta"):
            if derived == self.mode:
                continue
            cond = self._condition(derived, part)
            if cond > AMPLIFICATION and cond * rel_in > TOLERANCE:
                raise ValueError(self._message(derived, cond, cond * rel_in))

    def _condition(self, derived: str, part: Particle) -> float:
        """d ln(derived) / d ln(input), numerically. Independent of how the input
        was written: it is a property of the conversion at this working point."""
        step = abs(self.value) * 1e-7 or 1e-7
        try:
            g_lo = _gamma_from(self.mode, self.value - step, part)
            g_hi = _gamma_from(self.mode, self.value + step, part)
        except ValueError:
            return float("inf")     # against a physical edge: worst conditioning
        if derived == "gamma":
            lo, hi, here = g_lo, g_hi, self._gamma
        else:
            lo, hi, here = _beta_from_gamma(g_lo), _beta_from_gamma(g_hi), self._beta
        if here == 0.0:
            return float("inf")
        return abs(hi - lo) / (2.0 * step) * abs(self.value) / abs(here)

    def _message(self, derived: str, cond: float, spread: float) -> str:
        unit = _MODE_UNITS[self.mode]
        given = f"{self.mode} = {self.text or self.value}" + (f" {unit}" if unit else "")
        other = "gamma" if derived == "gamma" else "beta"
        why = ("this beam is relativistic enough that beta cannot say what gamma is"
               if derived == "gamma" else
               "this beam is slow enough that gamma cannot say what beta is")
        return (f"{given} fixes {derived} only to {spread:.1e} relative "
                f"({derived} = {getattr(self, derived):.10g} "
                f"+- {spread * abs(getattr(self, derived)):.3g}): {why} "
                f"(the conversion amplifies the input by {cond:.1e}). "
                f"Give the beam as {other} instead"
                + (", or as energy or momentum." if other == "gamma" else "."))

    # ---- derived quantities ----
    @property
    def gamma(self) -> float:
        return self._gamma

    @property
    def beta(self) -> float:
        return self._beta

    @property
    def one_minus_beta(self) -> float:
        """Readable where beta itself prints as 1.0."""
        return 1.0 - self._beta

    @property
    def energy_eV(self) -> float:
        return self._gamma * PARTICLES[self.particle].mass_eV

    @property
    def kinetic_eV(self) -> float:
        return (self._gamma - 1.0) * PARTICLES[self.particle].mass_eV

    @property
    def momentum_eV(self) -> float:
        return self._gamma * self._beta * PARTICLES[self.particle].mass_eV

    # ---- serialisation ----
    def to_dict(self) -> dict:
        """What goes in the YAML: the input exactly as given, plus the derived
        values for readers that just want a number.

        The input key is written last-resort-proof: for mode 'beta' the 'beta'
        entry is the user's 0.0146, not the 0.014599999999993955 that comes back
        from gamma. Round-tripping through the derived value is precisely the
        precision loss this class exists to avoid.
        """
        d = {"particle": self.particle, "mode": self.mode, self.mode: self.value}
        for key, derived in (("gamma", self._gamma), ("beta", self._beta)):
            d.setdefault(key, derived)
        return d

    @classmethod
    def from_dict(cls, data) -> "Beam":
        if isinstance(data, Beam):
            return data
        if data is None:
            raise ValueError("no beam given")
        if not isinstance(data, dict):                 # bare number: a gamma
            return cls(mode="gamma", value=float(data))
        d = dict(data)
        part = d.pop("particle", "proton")
        mode = d.pop("mode", None)
        if mode is None:                               # infer from which key is there
            for m in MODES:
                if m in d:
                    mode = m
                    break
        if mode is None:
            raise ValueError("beam needs one of: " + ", ".join(MODES))
        if mode not in d:
            raise ValueError(f"beam says mode '{mode}' but carries no '{mode}' value")
        return cls(particle=part, mode=mode, value=float(d[mode]),
                   text=d.get("text"))

    def label(self) -> str:
        """Short form for plot legends and result headers."""
        if self.mode == "beta" or self._gamma < 1.01:
            return f"{self.particle}, \u03b2={self._beta:.6g}"
        return f"{self.particle}, \u03b3={self._gamma:.6g}"

    def __str__(self) -> str:
        return self.label()
