"""Shared fixtures.

`pytest.importorskip` only catches ImportError. IW2D does not fail that way:
importing it loads a C++ core through cppyy, which raises RuntimeError when a
shared library is missing or is packaged under another name — on Debian and
Ubuntu, Arb ships as flint-arb, so IW2D needs IW2D_FLINT_ARB=1 to find it (see
docs/IW2D.md). Guarding those tests with importorskip therefore did not guard
them at all: on a machine where the engine is installed but cannot load, the
suite failed instead of skipping.
"""
import pytest


@pytest.fixture
def iw2d():
    """The IW2D module, or skip the test if the engine cannot be loaded."""
    from wimba.sources.iw2d_bridge import iw2d_available
    if not iw2d_available():
        pytest.skip("IW2D is installed but not loadable, or not installed; "
                    "see docs/IW2D.md (on Debian/Ubuntu: IW2D_FLINT_ARB=1)")
    import IW2D
    return IW2D
