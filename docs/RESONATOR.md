<p align="center">
  <img src="wimba_logo_small.png" alt="WIMBA" width="190">
</p>

# Resonator source

The resonator source produces analytic broad- and narrow-band resonator terms
using the standard resonator (Chao) formulas. It depends only on `numpy`, so it
also serves as a self-contained reference to validate the core data model
without an external impedance engine.

A `ResonatorProvider` holds a list of `Resonator` specifications and, for each,
emits one `ImpedanceTerm` with `origin = "resonator"`.

## Parameters

```python
Resonator(term, Rs, Q, fr)
```

| field  | meaning |
|--------|---------|
| `term` | which standard term this resonator feeds: `"zlong"`, `"zxdip"`, `"zydip"`, `"zxquad"`, `"zyquad"` |
| `Rs`   | shunt impedance — Ω for longitudinal, Ω/m for transverse |
| `Q`    | quality factor (the formulas below assume the underdamped case `Q > 1/2`) |
| `fr`   | resonant frequency, in Hz |

Two derived quantities appear throughout, with $\omega = 2\pi f$ and
$\omega_r = 2\pi f_r$:

$$\alpha = \frac{\omega_r}{2Q}, \qquad \bar\omega = \sqrt{\omega_r^{2} - \alpha^{2}}.$$

## Longitudinal terms (`zlong`)

Both impedance and wake are provided in closed form.

Impedance:

$$Z_\parallel(\omega) = \frac{R_s}{1 + iQ\left(\dfrac{\omega}{\omega_r} - \dfrac{\omega_r}{\omega}\right)}.$$

Wake (causal, $W_\parallel = 0$ for $t<0$):

$$W_\parallel(t) = 2\alpha R_s\, e^{-\alpha t}\left[\cos(\bar\omega t) - \frac{\alpha}{\bar\omega}\sin(\bar\omega t)\right], \quad t>0,$$

$$W_\parallel(0) = \alpha R_s.$$

The value at $t=0$ is **half** the right-hand limit ($2\alpha R_s$): this is the
fundamental theorem of beam loading — a particle sees half of its own wake.

## Transverse terms (`zxdip`, `zydip`, `zxquad`, `zyquad`)

Impedance is provided in closed form:

$$Z_\perp(\omega) = \frac{\omega_r}{\omega}\,\frac{R_\perp}{1 + iQ\left(\dfrac{\omega}{\omega_r} - \dfrac{\omega_r}{\omega}\right)}.$$

**The transverse wake is not yet implemented** (`w = None`). The functional shape
is settled — $W_\perp(t) \propto e^{-\alpha t}\sin(\bar\omega t)$, zero at
$t=0$ — but the normalisation constant is not yet pinned down with confidence.
The candidate Chao form is

$$W_\perp(t) = \frac{\omega_r^{2} R_\perp}{Q\,\bar\omega}\, e^{-\alpha t}\sin(\bar\omega t), \quad t>0,$$

but this constant, and the exact convention for $R_\perp$, differ between common
references and must be validated against pytlwall before being shipped. The
intended robust route is to obtain $W_\perp$ as the numerical inverse transform
of $Z_\perp$, so the normalisation follows from the impedance automatically and
stays self-consistent.

## Conventions and limitations

- **Sign / Fourier convention.** The pair above corresponds to one choice of the
  $e^{\mp i\omega t}$ convention; the opposite choice flips the sign of
  $\mathrm{Im}\,Z$ and of the wake. This is to be aligned with pytlwall / xwakes.
- **Underdamped only.** The formulas assume $Q > 1/2$, so that $\bar\omega$ is
  real. The overdamped case $Q \le 1/2$ (hyperbolic form) is not handled.
- **Behaviour at $f=0$.** Both $Z_\parallel$ and $Z_\perp$ contain a
  $\omega_r/\omega$ term and are singular at $f=0$; evaluate on grids with
  $f > 0$.

## Example

```python
from wimba import Element, Resonator, ResonatorProvider

element = Element(
    name="bb",
    category="broadband",
    length=1.0,
    provider=ResonatorProvider([
        Resonator(term="zlong", Rs=1.0e4, Q=1.0, fr=1.0e9),  # Z and W
        Resonator(term="zxdip", Rs=1.0e6, Q=1.0, fr=1.0e9),  # Z only (W not yet available)
    ]),
)
```

## Reference

A. W. Chao, *Physics of Collective Beam Instabilities in High Energy
Accelerators*, Wiley (1993) — resonator impedance and wake functions.
