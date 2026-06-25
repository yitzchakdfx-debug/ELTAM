"""Offline tests for the VISA transport wrapper (no backend required)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from drivers.base_driver import ConnectionLostError
from drivers.bench.transports.visa import VisaSession, visa_available


class VisaTransportTests(unittest.TestCase):
    def test_visa_available_returns_bool_without_raising(self):
        self.assertIsInstance(visa_available(), bool)

    def test_not_open_calls_guard(self):
        s = VisaSession("GPIB0::9::INSTR")
        self.assertFalse(s.is_open)
        with self.assertRaises(ConnectionLostError):
            s.write("*CLS")
        with self.assertRaises(ConnectionLostError):
            s.query("*IDN?")

    def test_close_is_idempotent(self):
        s = VisaSession("GPIB0::9::INSTR")
        s.close()  # never opened — must be a safe no-op
        s.close()
        self.assertFalse(s.is_open)


if __name__ == "__main__":
    unittest.main()
