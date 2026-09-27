# ChimeraThickness_Project

A [parametric project](../../docs/PARAMETRIC.md): CHIMERA at injection
(γ = 2.279), with the innermost layer of COLL.H alone — the chimeranium, over
3 mm of copper — 10 µm, 50 µm, 200 µm, 1 mm and 5 mm thick. Everything else is
the base config, `../Chimera_Project/injection_config.yaml`, whose data this
project reads by relative path: keep the two folders side by side.

Open it with *File → Open Project*, then *Calculate → Calculate Project…*.
A thin layer lets the field reach the copper behind it; once the layer is a few
skin depths thick the curves meet, at lower frequency the thicker the layer. Plot
`Re ZDipX` of COLL.H, then the machine's ZDipX and ZDipY: COLL.H is a horizontal
collimator, and the vertical plane barely moves.

CHIMERA is invented. Do not quote a number out of it.
