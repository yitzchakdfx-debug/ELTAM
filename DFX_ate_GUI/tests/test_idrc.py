"""Offline unit tests for the IDRC-040-076HR PS driver layer.

No hardware and no serial port required. The protocol assertions pin the
*provisional* command set (see the driver's protocol.py) — update both together
when the manual is confirmed.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from drivers.base_driver import ConnectionLostError
from drivers.bench.instrument_base import ConnInfo, VoltageSource
from drivers.instruments.idrc_040_076hr import protocol
from drivers.instruments.idrc_040_076hr.driver import IdrcPowerSupply
from drivers.instruments.idrc_040_076hr.mock import IdrcPowerSupplyMock


class ProtocolTests(unittest.TestCase):
    def test_output(self):
        self.assertEqual(protocol.output(True), "OUTP ON")
        self.assertEqual(protocol.output(False), "OUTP OFF")

    def test_set_voltage_formats_fixed_precision(self):
        self.assertEqual(protocol.set_voltage(28), "VOLT 28.000")
        self.assertEqual(protocol.set_voltage(16.0), "VOLT 16.000")

    def test_measure_and_protection(self):
        self.assertEqual(protocol.measure_voltage(), "MEAS:VOLT?")
        self.assertEqual(protocol.measure_current(), "MEAS:CURR?")
        self.assertEqual(protocol.set_ovp(35), "VOLT:PROT 35.000")
        self.assertEqual(protocol.set_ocp(20), "CURR:PROT 20.000")


class MockTests(unittest.TestCase):
    def setUp(self):
        self.ps = IdrcPowerSupplyMock(seed=1)
        self.ps.open(ConnInfo("sim", "MOCK"))

    def tearDown(self):
        self.ps.close()

    def test_is_available(self):
        self.assertTrue(IdrcPowerSupplyMock.is_available())

    def test_structural_conformance(self):
        self.assertIsInstance(self.ps, VoltageSource)

    def test_identify_nonempty(self):
        self.assertIn("IDRC-040-076HR", self.ps.identify())

    def test_voltage_zero_when_output_off(self):
        self.ps.set_voltage(28.0)
        self.assertFalse(self.ps.measure_voltage() > 0.5)  # output still off
        self.assertEqual(self.ps.measure_current(), 0.0)

    def test_voltage_tracks_setpoint_when_on(self):
        self.ps.set_voltage(28.0)
        self.ps.set_output(True)
        v = self.ps.measure_voltage()
        self.assertGreaterEqual(v, 27.9)
        self.assertLessEqual(v, 28.1)
        i = self.ps.measure_current()
        self.assertGreater(i, 0.0)  # idle draw when energized
        self.assertLess(i, 0.5)

    def test_calls_before_open_raise(self):
        fresh = IdrcPowerSupplyMock()
        with self.assertRaises(ConnectionLostError):
            fresh.measure_voltage()


class DriverGuardTests(unittest.TestCase):
    def test_is_available_returns_bool(self):
        self.assertIsInstance(IdrcPowerSupply.is_available(), bool)

    def test_structural_conformance(self):
        self.assertIsInstance(IdrcPowerSupply(), VoltageSource)

    def test_calls_before_open_raise(self):
        d = IdrcPowerSupply()
        with self.assertRaises(ConnectionLostError):
            d.identify()
        with self.assertRaises(ConnectionLostError):
            d.set_voltage(28.0)
        with self.assertRaises(ConnectionLostError):
            d.measure_current()

    def test_parse_float_tolerates_unit_suffix(self):
        self.assertEqual(IdrcPowerSupply._parse_float("28.00V"), 28.0)
        self.assertEqual(IdrcPowerSupply._parse_float("1.234A"), 1.234)
        self.assertEqual(IdrcPowerSupply._parse_float("16.0"), 16.0)
        with self.assertRaises(ConnectionLostError):
            IdrcPowerSupply._parse_float("xyz")


if __name__ == "__main__":
    unittest.main()
