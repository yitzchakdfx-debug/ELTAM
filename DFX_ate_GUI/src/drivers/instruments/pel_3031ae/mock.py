"""Mock for the GW Instek PEL-3031AE electronic load — Qt-free, no I/O.

Same `InstrumentDriver` + `ElectronicLoad` surface and constructor (`channel`)
as the real driver, so the factory can swap it in for Simulation. Standalone by
default (uses a fixed nominal bus voltage); pass `bus` to couple it into the
shared bench `SimBus` — voltage then follows the PS rail and `set_power` feeds
the shared load state (mirrors `Prodigit3300LoadMock`).
"""

from __future__ import annotations

import random

from drivers.base_driver import ConnectionLostError
from drivers.bench.instrument_base import ConnInfo, InstrumentDriver
from drivers.bench.sim_bus import SimBus, reading


class Pel3031LoadMock(InstrumentDriver):
    """Simulated PEL-3031AE load. Capability: ElectronicLoad."""

    def __init__(
        self,
        *,
        bus_voltage: float = 28.0,
        seed: int | None = None,
        bus: SimBus | None = None,
        fail_prob: float = 0.0,
    ) -> None:
        self._bus_voltage = float(bus_voltage)
        self._rng = random.Random(seed)
        self._open = False
        self._mode = "CP"
        self._watts = 0.0
        self._input = False
        self._bus = bus
        self._fail_prob = fail_prob

    # --- InstrumentDriver lifecycle ---
    @classmethod
    def is_available(cls) -> bool:
        return True

    def open(self, conn: ConnInfo) -> None:
        self._open = True

    def close(self) -> None:
        self._input = False
        self._open = False

    def identify(self) -> str:
        self._require_open()
        return "GW-INSTEK,PEL-3031AE,SIM0000,1.0"

    # --- ElectronicLoad capability ---
    def set_mode(self, mode: str) -> None:
        self._require_open()
        self._mode = mode.strip().upper()

    def set_power(self, watts: float) -> None:
        self._require_open()
        self._watts = float(watts)
        if self._bus is not None:
            self._bus.load_watts = float(watts)

    def set_input(self, on: bool) -> None:
        self._require_open()
        self._input = bool(on)

    def measure_voltage(self) -> float:
        self._require_open()
        if self._bus is not None:
            # The load terminals see the shared bus rail.
            return reading(self._rng, self._bus.input_voltage, fail_prob=self._fail_prob)
        if not self._input:
            return round(self._rng.uniform(-0.02, 0.02), 4)
        return round(self._bus_voltage + self._rng.uniform(-0.05, 0.05), 4)

    def measure_current(self) -> float:
        self._require_open()
        if self._bus is not None:
            v = self._bus.input_voltage
            if self._input and self._bus.load_watts > 0 and v > 0:
                return reading(self._rng, self._bus.load_watts / v, fail_prob=self._fail_prob)
            return round(self._rng.uniform(0.0, 0.02), 4)
        if self._input and self._watts > 0 and self._bus_voltage > 0:
            return round(self._watts / self._bus_voltage + self._rng.uniform(-0.05, 0.05), 4)
        return round(self._rng.uniform(0.0, 0.02), 4)

    def measure_power(self) -> float:
        self._require_open()
        return round(self.measure_voltage() * self.measure_current(), 4)

    # --- helpers ---
    def _require_open(self) -> None:
        if not self._open:
            raise ConnectionLostError("PEL-3031AE mock is not open; call open() first.")
