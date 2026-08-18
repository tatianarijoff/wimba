"""Frequency and time units in imported tables.

The case that motivated these: the FCC-ee impedance model
(github.com/ImpedanCEI/fcc_ee_IW_model) writes '# Freq(GHz) Re(Z) Im(Z)'. Read as
Hz that is wrong by 1e9 in frequency, and nothing about the result looks broken.
"""
import numpy as np
import pytest

from wimba.io.tables import (FREQ_UNITS, read_impedance, read_impedance_table,
                             read_wake, unit_scale, write_impedance)


def _write(path, header, freqs, z):
    with open(path, "w") as fh:
        if header:
            fh.write(f"# {header}\n")
        for f, v in zip(freqs, z):
            fh.write(f"{f:.12e} {v.real:.12e} {v.imag:.12e}\n")
    return path


FCC_HEADER = "Freq(GHz) Re(Z) Im(Z)"
F = np.array([0.0, 1.0, 2.0, 50.0])            # GHz, as the FCC-ee model writes
Z = np.array([1 + 1j, 2 + 2j, 3 + 3j, 4 + 4j])


def test_unit_scale_reads_common_spellings():
    assert unit_scale("Freq(GHz)") == 1e9
    assert unit_scale("frequency[Hz]") == 1.0
    assert unit_scale("f [MHz]") == 1e6
    assert unit_scale("Re(ZLong)") is None


def test_ghz_header_is_applied(tmp_path):
    p = _write(tmp_path / "Z_long_pipe_rw.txt", FCC_HEADER, F, Z)
    f, z = read_impedance(p)
    assert f[-1] == pytest.approx(50e9)
    assert z[1] == pytest.approx(2 + 2j)        # only the frequency is scaled


def test_explicit_unit_beats_the_header(tmp_path):
    p = _write(tmp_path / "z.txt", FCC_HEADER, F, Z)
    f, _ = read_impedance(p, freq_unit="MHz")
    assert f[-1] == pytest.approx(50e6)


def test_unknown_unit_is_rejected(tmp_path):
    p = _write(tmp_path / "z.txt", FCC_HEADER, F, Z)
    with pytest.raises(ValueError, match="unknown frequency unit"):
        read_impedance(p, freq_unit="furlongs")


def test_implausible_hz_is_refused_rather_than_guessed(tmp_path):
    """No declared unit and a spectrum ending at 50: not credible in Hz."""
    p = _write(tmp_path / "z.txt", None, F, Z)
    with pytest.raises(ValueError, match="not credible in Hz"):
        read_impedance(p)
    f, _ = read_impedance(p, freq_unit="GHz")   # the fix the message asks for
    assert f[-1] == pytest.approx(50e9)


def test_plain_hz_file_is_unaffected(tmp_path):
    """WIMBA's own export must keep round-tripping."""
    p = tmp_path / "wimba.dat"
    freqs = np.logspace(3, 11, 50)
    write_impedance(p, freqs, Z[:1].repeat(50))
    f, _ = read_impedance(p)
    assert np.allclose(f, freqs)


def test_headerless_hz_file_still_reads(tmp_path):
    p = _write(tmp_path / "z.txt", None, np.array([1e5, 1e6, 1e9]),
               np.array([1 + 0j, 2 + 0j, 3 + 0j]))
    f, _ = read_impedance(p)
    assert f[-1] == pytest.approx(1e9)


def test_named_columns_carry_the_unit(tmp_path):
    p = tmp_path / "multi.csv"
    p.write_text("Freq(GHz),Re(ZLong),Im(ZLong)\n0,1,1\n1,2,2\n")
    table = read_impedance_table(p)
    f, _ = table["ZLong"]
    assert f[-1] == pytest.approx(1e9)


def test_wake_time_unit(tmp_path):
    p = tmp_path / "w.dat"
    p.write_text("# time(ns)  W\n0 0\n1 5\n2 7\n")
    t, w = read_wake(p)
    assert t[-1] == pytest.approx(2e-9)
    assert w[-1] == pytest.approx(7.0)
    t2, _ = read_wake(p, time_unit="ps")
    assert t2[-1] == pytest.approx(2e-12)


def test_every_declared_unit_is_usable(tmp_path):
    p = _write(tmp_path / "z.txt", None, np.array([1.0, 2.0]), Z[:2])
    for name, mult in FREQ_UNITS.items():
        f, _ = read_impedance(p, freq_unit=name)
        assert f[-1] == pytest.approx(2.0 * mult)
