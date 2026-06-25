"""Offline unit tests for the GW Instek DAQ-9600 driver layer.

No hardware and no pyvisa backend required. Run:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from drivers.base_driver import ConnectionLostError
from drivers.bench.instrument_base import ConnInfo, DiscreteIO, Multimeter
from drivers.instruments.daq_9600 import protocol
from drivers.instruments.daq_9600.driver import Daq9600
from drivers.instruments.daq_9600.mock import Daq9600Mock


class ProtocolTests(unittest.TestCase):
    def test_channel_list(self):
        self.assertEqual(protocol.channel_list(101), "(@101)")
        self.assertEqual(protocol.channel_list(7), "(@7)")

    def test_scpi_function_mapping_is_case_insensitive(self):
        self.assertEqual(protocol.scpi_function("DCV"), "VOLT:DC")
        self.assertEqual(protocol.scpi_function("dcv"), "VOLT:DC")
        self.assertEqual(protocol.scpi_function(" DCI "), "CURR:DC")

    def test_scpi_function_unknown_raises(self):
        with self.assertRaises(ValueError):
            protocol.scpi_function("BOGUS")

    def test_configure_and_measure(self):
        self.assertEqual(protocol.configure(101, "DCV"), "CONF:VOLT:DC (@101)")
        self.assertEqual(protocol.measure(104, "DCV"), "MEAS:VOLT:DC? (@104)")

    def test_route_commands(self):
        self.assertEqual(protocol.route_close(110), "ROUT:CLOS (@110)")
        self.assertEqual(protocol.route_open(110), "ROUT:OPEN (@110)")
        self.assertEqual(protocol.route_is_closed(110), "ROUT:CLOS? (@110)")

    def test_constants(self):
        self.assertEqual(protocol.IDN, "*IDN?")
        self.assertEqual(protocol.RESET, "*RST")


class MockTests(unittest.TestCase):
    def setUp(self):
        self.dev = Daq9600Mock(nominal=28.0, seed=1)
        self.dev.open(ConnInfo("sim", "MOCK"))

    def tearDown(self):
        self.dev.close()

    def test_is_available(self):
        self.assertTrue(Daq9600Mock.is_available())

    def test_structural_conformance(self):
        self.assertIsInstance(self.dev, Multimeter)
        self.assertIsInstance(self.dev, DiscreteIO)

    def test_identify_nonempty(self):
        self.assertTrue(self.dev.identify())

    def test_read_is_float_near_nominal(self):
        v = self.dev.read(103)
        self.assertIsInstance(v, float)
        self.assertGreaterEqual(v, 27.9)
        self.assertLessEqual(v, 28.1)

    def test_relay_toggle(self):
        self.assertFalse(self.dev.get_line(110))
        self.dev.set_line(110, True)
        self.assertTrue(self.dev.get_line(110))
        self.dev.set_line(110, False)
        self.assertFalse(self.dev.get_line(110))

    def test_relays_cleared_on_close(self):
        self.dev.set_line(110, True)
        self.dev.close()
        self.dev.open(ConnInfo("sim", "MOCK"))
        self.assertFalse(self.dev.get_line(110))

    def test_read_before_open_raises(self):
        fresh = Daq9600Mock()
        with self.assertRaises(ConnectionLostError):
            fresh.read(101)


class DriverGuardTests(unittest.TestCase):
    def test_is_available_returns_bool(self):
        self.assertIsInstance(Daq9600.is_available(), bool)

    def test_structural_conformance(self):
        d = Daq9600()
        self.assertIsInstance(d, Multimeter)
        self.assertIsInstance(d, DiscreteIO)

    def test_calls_before_open_raise(self):
        d = Daq9600()
        with self.assertRaises(ConnectionLostError):
            d.identify()
        with self.assertRaises(ConnectionLostError):
            d.read(101)
        with self.assertRaises(ConnectionLostError):
            d.set_line(110, True)

    def test_parse_float(self):
        self.assertEqual(Daq9600._parse_float("27.96"), 27.96)
        self.assertEqual(Daq9600._parse_float("27.96,extra"), 27.96)
        with self.assertRaises(ConnectionLostError):
            Daq9600._parse_float("abc")


if __name__ == "__main__":
    unittest.main()
