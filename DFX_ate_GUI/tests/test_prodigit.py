"""Offline unit tests for the Prodigit 3300G/3315G electronic-load driver.

No hardware, no Prologix adapter, no serial port. A fake session captures the
exact command stream so the Prologix addressing + `CHAN n` channel routing are
verified offline.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import drivers.instruments.prodigit_3300.driver as drv
from drivers.base_driver import ConnectionLostError
from drivers.bench.instrument_base import ConnInfo, ElectronicLoad
from drivers.instruments.prodigit_3300 import protocol
from drivers.instruments.prodigit_3300.driver import Prodigit3300Load
from drivers.instruments.prodigit_3300.mock import Prodigit3300LoadMock


class _FakeSession:
    """Records writes/queries; returns canned query responses. Mimics SerialSession."""

    def __init__(self, resource, **kwargs):
        self.resource = resource
        self.kwargs = kwargs
        self.writes: list[str] = []
        self.queries: list[str] = []
        self.responses: dict[str, str] = {}
        self._open = False

    @property
    def is_open(self) -> bool:
        return self._open

    def open(self) -> None:
        self._open = True

    def write(self, command: str) -> None:
        self.writes.append(command)

    def query(self, command: str) -> str:
        self.queries.append(command)
        return self.responses.get(command, "0")

    def close(self) -> None:
        self._open = False


class ProtocolTests(unittest.TestCase):
    def test_prologix_init(self):
        self.assertEqual(protocol.prologix_init(6), ["++mode 1", "++addr 6", "++auto 1"])
        self.assertEqual(protocol.prologix_set_address(7), "++addr 7")

    def test_select_channel(self):
        self.assertEqual(protocol.select_channel(2), "CHAN 2")

    def test_mode_token(self):
        self.assertEqual(protocol.mode_token("cp"), "CP")
        self.assertEqual(protocol.mode_token(" cc "), "CC")
        with self.assertRaises(ValueError):
            protocol.mode_token("ZZ")

    def test_set_sequences(self):
        self.assertEqual(protocol.set_mode(2, "CP"), ["CHAN 2", "MODE CP"])
        self.assertEqual(protocol.set_power(3, 200), ["CHAN 3", "POW 200.000"])
        self.assertEqual(protocol.set_input(1, True), ["CHAN 1", "LOAD ON"])
        self.assertEqual(protocol.set_input(1, False), ["CHAN 1", "LOAD OFF"])

    def test_query_sequences(self):
        self.assertEqual(protocol.measure_voltage(2), (["CHAN 2"], "MEAS:VOLT?"))
        self.assertEqual(protocol.measure_current(2), (["CHAN 2"], "MEAS:CURR?"))
        self.assertEqual(protocol.identify(4), (["CHAN 4"], "NAME?"))


class MockTests(unittest.TestCase):
    def setUp(self):
        self.load = Prodigit3300LoadMock(load_slot=1, gpib_address=6, bus_voltage=28.0, seed=1)
        self.load.open(ConnInfo("prologix", "COM5"))

    def tearDown(self):
        self.load.close()

    def test_slot_validation(self):
        with self.assertRaises(ValueError):
            Prodigit3300LoadMock(load_slot=5, gpib_address=6)

    def test_is_available(self):
        self.assertTrue(Prodigit3300LoadMock.is_available())

    def test_structural_conformance(self):
        self.assertIsInstance(self.load, ElectronicLoad)

    def test_identify(self):
        self.assertIn("3315G", self.load.identify())

    def test_voltage_zero_when_input_off(self):
        self.assertLess(abs(self.load.measure_voltage()), 0.5)

    def test_constant_power_current(self):
        self.load.set_mode("CP")
        self.load.set_power(200.0)
        self.load.set_input(True)
        self.assertGreaterEqual(self.load.measure_voltage(), 27.9)   # bus ~28 V
        i = self.load.measure_current()                              # 200/28 ~= 7.14 A
        self.assertGreaterEqual(i, 6.9)
        self.assertLessEqual(i, 7.4)

    def test_current_zero_when_input_off(self):
        self.load.set_power(200.0)
        self.assertLess(self.load.measure_current(), 0.1)

    def test_calls_before_open_raise(self):
        fresh = Prodigit3300LoadMock(load_slot=1, gpib_address=6)
        with self.assertRaises(ConnectionLostError):
            fresh.measure_current()


class DriverGuardTests(unittest.TestCase):
    def test_slot_validation(self):
        with self.assertRaises(ValueError):
            Prodigit3300Load(load_slot=0, gpib_address=6)
        with self.assertRaises(ValueError):
            Prodigit3300Load(load_slot=5, gpib_address=6)

    def test_gpib_validation(self):
        with self.assertRaises(ValueError):
            Prodigit3300Load(load_slot=1, gpib_address=31)
        with self.assertRaises(ValueError):
            Prodigit3300Load(load_slot=1, gpib_address=-1)

    def test_is_available_returns_bool(self):
        self.assertIsInstance(Prodigit3300Load.is_available(), bool)

    def test_structural_conformance(self):
        self.assertIsInstance(Prodigit3300Load(load_slot=1, gpib_address=6), ElectronicLoad)

    def test_calls_before_open_raise(self):
        d = Prodigit3300Load(load_slot=2, gpib_address=6)
        with self.assertRaises(ConnectionLostError):
            d.identify()
        with self.assertRaises(ConnectionLostError):
            d.set_power(200.0)
        with self.assertRaises(ConnectionLostError):
            d.measure_voltage()

    def test_parse_float_tolerates_unit_suffix(self):
        self.assertEqual(Prodigit3300Load._parse_float("12.5A"), 12.5)
        self.assertEqual(Prodigit3300Load._parse_float("28.0V"), 28.0)
        self.assertEqual(Prodigit3300Load._parse_float("200.0W"), 200.0)
        with self.assertRaises(ConnectionLostError):
            Prodigit3300Load._parse_float("xyz")

    def test_check_name_empty_slot(self):
        with self.assertRaises(ConnectionLostError):
            Prodigit3300Load._check_name("NULL", 2)
        with self.assertRaises(ConnectionLostError):
            Prodigit3300Load._check_name("", 2)
        self.assertEqual(Prodigit3300Load._check_name("  3315G ", 2), "3315G")


@patch.object(drv, "SerialSession", _FakeSession)
class CommandStreamTests(unittest.TestCase):
    """Verify the exact Prologix + channel-routed command stream offline."""

    def _open(self, slot=2, gpib=6):
        load = Prodigit3300Load(load_slot=slot, gpib_address=gpib)
        load.open(ConnInfo("prologix", "COM5"))
        return load

    def test_open_sends_prologix_init(self):
        load = self._open(slot=2, gpib=6)
        self.assertEqual(load._session.writes, ["++mode 1", "++addr 6", "++auto 1"])

    def test_set_power_routes_channel(self):
        load = self._open(slot=2)
        load.set_power(200.0)
        self.assertEqual(load._session.writes[-2:], ["CHAN 2", "POW 200.000"])

    def test_set_mode_routes_channel(self):
        load = self._open(slot=3)
        load.set_mode("CP")
        self.assertEqual(load._session.writes[-2:], ["CHAN 3", "MODE CP"])

    def test_set_input_routes_channel(self):
        load = self._open(slot=1)
        load.set_input(True)
        self.assertEqual(load._session.writes[-2:], ["CHAN 1", "LOAD ON"])

    def test_measure_voltage_selects_then_queries(self):
        load = self._open(slot=3)
        load._session.responses["MEAS:VOLT?"] = "28.05"
        v = load.measure_voltage()
        self.assertEqual(v, 28.05)
        self.assertEqual(load._session.writes[-1], "CHAN 3")
        self.assertEqual(load._session.queries[-1], "MEAS:VOLT?")

    def test_identify_empty_slot_raises(self):
        load = self._open(slot=4)
        load._session.responses["NAME?"] = "NULL"
        with self.assertRaises(ConnectionLostError):
            load.identify()

    def test_close_drives_input_off(self):
        load = self._open(slot=1)
        session = load._session
        load.close()
        self.assertIn("LOAD OFF", session.writes)
        self.assertFalse(session.is_open)
        self.assertIsNone(load._session)


if __name__ == "__main__":
    unittest.main()
