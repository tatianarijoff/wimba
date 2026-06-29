<p align="center">
  <img src="wimba_logo_small.png" alt="WIMBA" width="190">
</p>

# Fourier transforms (wake ↔ impedance)

`wimba.analysis.FourierTransform` converts between a wake and an impedance by
direct numerical quadrature. It is meant to be run **on demand** on a specific
dataset — to check that a wake and an impedance are a consistent transform pair,
or to obtain one from the other for a tabulated source that ships only one of
them. It is *not* part of the normal build/query path: the cost scales as
(number of frequencies) × (number of times), so it is deliberately explicit.

## Conventions

Pinned to the analytic resonator (and therefore to xwakes):

$$Z(\omega) = \texttt{factor}\int_0^\infty W(t)\,e^{-i\omega t}\,dt, \qquad
W(t) = \frac{1}{\pi}\int_0^\infty \mathrm{Re}\!\left[\frac{Z(\omega)}{\texttt{factor}}\,e^{+i\omega t}\right]d\omega,$$

with `factor` $= 1$ for the longitudinal plane and `factor` $= i$ for the
transverse planes. The wake is assumed causal ($t \ge 0$); the impedance is
assumed sampled on positive frequencies, the negative axis being recovered from
the reality of the wake.

## Methods

```python
from wimba.analysis import FourierTransform as FT

Z = FT.impedance_from_wake(times, wake, freqs, plane="z")   # -> complex array
W = FT.wake_from_impedance(freqs, impedance, times, plane="z")  # -> real array

# directly on .dat files
FT.impedance_dat_from_wake_dat("W_zlong.dat", "Z_from_W.dat", freqs, plane="z")
FT.wake_dat_from_impedance_dat("Z_zlong.dat", "W_from_Z.dat", times, plane="z")
```

## Accuracy

The result is only as good as the supplied grids; the transforms do **not**
resample for you.

- The wake must be sampled finely (to resolve the oscillation at $f_r$) and long
  enough to have decayed.
- The impedance must be sampled finely and up to a high enough frequency. The
  longitudinal wake has a step at $t=0$, so $Z_\parallel$ decays only as $1/f$:
  reconstructing it needs a wide frequency band, and a truncated band leaves a
  visible (Gibbs-type) error near $t=0$ that shrinks as the upper frequency
  grows. Transverse impedances decay faster and invert more accurately.
