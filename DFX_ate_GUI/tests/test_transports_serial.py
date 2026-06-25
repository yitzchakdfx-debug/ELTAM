"""Offline tests for the serial transport wrapper (no real port required)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from drivers.base_driver import ConnectionLostError
from drivers.bench.transports.serial_port import SerialSession, serial_available


class SerialTransportTests(unittest.TestCase):
    def test_serial_available_returns_bool_without_raising(self):
        self.assertIsInstance(serial_available(), bool)

    def test_not_open_calls_guard(self):
        s = SerialSession("COM99")
        self.assertFalse(s.is_open)
        with self.assertRaises(ConnectionLostError):
            s.write("OUTP OFF")
        with self.assertRaises(ConnectionLostError):
            s.query("*IDN?")

    def test_close_is_idempotent(self):
        s = SerialSession("COM99")
        s.close()  # never opened — safe no-op
        s.close()
        self.assertFalse(s.is_open)


if __name__ == "__main__":
    unittest.main()
