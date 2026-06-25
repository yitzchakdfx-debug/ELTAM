"""Mock for the GW Instek GPP-3610H PS — Qt-free, no I/O.

Same `InstrumentDriver` + `VoltageSource` surface and constructor (no args) as
the real driver, so the factory can swap it in for Simulation. Standalone by
default; pass `bus` to couple it into the shared bench `SimBus` (the PS rail is
then read/written through the bus, exactly like `IdrcPowerSupplyMock`).
"""

from __future__ import annotations

import random

from drivers.base_driver import ConnectionLostError
from drivers.bench.instrument_base import ConnInfo, InstrumentDriver
from drivers.bench.sim_bus import SimBus, reading


class Gpp3610hPowerSupplyMock(InstrumentDriver):
    """Simulated GPP-3610H. Capability: VoltageSource."""

    def __init__(
        self,
        *,
        seed: int | None = None,
        bus: SimBus | None = None,
        fail_prob: float = 0.0,
    ) -> None:
        self._open = False
        self._output = False
        self._voltage = 0.0
        self._current_limit = 10.0
        self._rng = random.Random(seed)
        self._bus = bus
        self._fail_prob = fail_prob

    # --- InstrumentDriver lifecycle ---
    @classmethod
    def is_available(cls) -> bool:
        return True

    def open(self, conn: ConnInfo) -> None:
        self._open = True

    def close(self) -> None:
        self._output = False
        self._open = False

    def identify(self) -> str:
        self._require_open()
        return "GW-INSTEK,GPP-3610H,SIM0000,1.0"

    # --- VoltageSource capability ---
    def set_output(self, on: bool) -> None:
        self._require_open()
        self._output = bool(on)

    def set_voltage(self, volts: float) -> None:
        self._require_open()
        if self._bus is not None:
            self._bus.input_voltage = float(volts)
        else:
            self._voltage = float(volts)

    def set_current(self, amps: float) -> None:
        self._require_open()
        self._current_limit = float(amps)

    def measure_voltage(self) -> float:
        self._require_open()
        if self._bus is not None:
            nominal = self._bus.input_voltage if self._output else 0.0
            return reading(self._rng, nominal, fail_prob=self._fail_prob)
        if not self._output:
            return round(self._rng.uniform(-0.02, 0.02), 4)
        return round(self._voltage + self._rng.uniform(-0.05, 0.05), 4)

    def measure_current(self) -> float:
        self._require_open()
        if not self._output:
            return 0.0
        # Idle/quiescent draw (no load on the source rail itself).
        if self._bus is not None:
            return reading(self._rng, 0.21, jitter=0.09, fail_prob=self._fail_prob)
        return round(self._rng.uniform(0.12, 0.30), 4)

    def measure_power(self) -> float:
        self._require_open()
        return round(self.measure_voltage() * self.measure_current(), 4)

    # --- helpers ---
    def _require_open(self) -> None:
        if not self._open:
            raise ConnectionLostError("GPP-3610H mock is not open; call open() first.")
