<p align="center">
  <img src="wimba_logo_small.png" alt="WIMBA" width="190">
</p>

# Resonator source

The resonator source produces analytic broad- and narrow-band resonator terms
using the standard resonator (Chao) formulas. It matches xwakes / pywit term by
term, including the sign convention, and depends only on `numpy`.

A `ResonatorProvider` holds a list of `Resonator` specifications and, for each,
emits one `ImpedanceTerm` with `origin = "resonator"`.

## Parameters

```python
Resonator(term, Rs, Q, fr)
```

| field  | meaning |
|--------|---------|
| `term` | which standard term: `"zlong"`, `"zxdip"`, `"zydip"`, `"zxquad"`, `"zyquad"` |
| `Rs`   | shunt impedance — Ω for longitudinal, Ω/m for transverse |
| `Q`    | quality factor |
| `fr`   | resonant frequency, in Hz |

With $\omega = 2\pi f$ and $\omega_r = 2\pi f_r$, the damped quantities are

$$\alpha = \frac{\omega_r}{2Q}, \qquad \bar\omega = \omega_r\sqrt{1 - \frac{1}{4Q^{2}}}.$$

The square root is evaluated in the complex plane, so the same expressions cover
the underdamped ($Q > 1/2$, $\bar\omega$ real) and overdamped ($Q < 1/2$,
$\bar\omega$ imaginary → hyperbolic) cases; the real part of the result is taken.

## Longitudinal terms (`zlong`)

Impedance:

$$Z_\parallel(\omega) = \frac{R_s}{1 + iQ\left(\dfrac{\omega}{\omega_r} - \dfrac{\omega_r}{\omega}\right)}.$$

Wake (causal, $W_\parallel = 0$ for $t<0$):

$$W_\parallel(t) = \frac{\omega_r R_s}{Q}\, e^{-\alpha t}\left[\cos(\bar\omega t) - \frac{\alpha}{\bar\omega}\sin(\bar\omega t)\right], \quad t \ge 0.$$

`wake()` returns the **full** value at $t=0$ (i.e. $\omega_r R_s/Q = 2\alpha R_s$).
The factor $1/2$ of the fundamental theorem of beam loading is a sampling-time
concern, applied where the wake is binned (as xwakes does in `function_vs_t`),
not baked into the wake itself.

## Transverse terms (`zxdip`, `zydip`, `zxquad`, `zyquad`)

Impedance:

$$Z_\perp(\omega) = \frac{\omega_r}{\omega}\,\frac{R_\perp}{1 + iQ\left(\dfrac{\omega}{\omega_r} - \dfrac{\omega_r}{\omega}\right)}.$$

Wake (causal, zero at $t=0$):

$$W_\perp(t) = \frac{\omega_r^{2} R_\perp}{Q\,\bar\omega}\, e^{-\alpha t}\sin(\bar\omega t), \quad t \ge 0.$$

Both the impedance and the wake reproduce xwakes to machine precision.

## Conventions and limitations

- **Sign / Fourier convention.** It matches xwakes: the longitudinal and
  transverse impedances above pair with the wakes under
  $Z(\omega) = \texttt{factor}\int_0^\infty W(t)\,e^{-i\omega t}\,dt$, with
  `factor` $=1$ longitudinally and $=i$ transversely (see the Fourier-transform
  utility).
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
        Resonator(term="zlong", Rs=1.0e4, Q=1.0, fr=1.0e9),
        Resonator(term="zxdip", Rs=1.0e6, Q=1.0, fr=1.0e9),
    ]),
)
```

## Reference

A. W. Chao, *Physics of Collective Beam Instabilities in High Energy
Accelerators*, Wiley (1993) — resonator impedance and wake functions.
