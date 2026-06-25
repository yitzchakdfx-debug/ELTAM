"""Mock for the Prodigit 3300G/3315G electronic load — Qt-free, no I/O.

Same `InstrumentDriver` + `ElectronicLoad` surface and constructor
(`load_slot`, `gpib_address`) as the real driver. Standalone: in constant-power
mode it reports I = P / V using an internal nominal bus voltage; full coupling to
the PS output lands with the BenchDriver (Phase 3).
"""

from __future__ import annotations

import random

from drivers.base_driver import ConnectionLostError
from drivers.bench.instrument_base import ConnInfo, InstrumentDriver
from drivers.bench.sim_bus import SimBus, reading


class Prodigit3300LoadMock(InstrumentDriver):
    """Simulated 3300G/3315G load. Capability: ElectronicLoad.

    Standalone by default (uses `bus_voltage` as a fixed rail); pass `bus` to
    couple it into a shared bench simulation (voltage follows the PS rail and
    `set_power` feeds the shared load state).
    """

    def __init__(
        self,
        *,
        load_slot: int,
        gpib_address: int,
        bus_voltage: float = 28.0,
        seed: int | None = None,
        bus: SimBus | None = None,
        fail_prob: float = 0.0,
    ) -> None:
        slot = int(load_slot)
        if not 1 <= slot <= 4:
            raise ValueError(f"load_slot must be 1-4 (got {load_slot!r}).")
        self._slot = slot
        self._gpib = int(gpib_address)
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
        return f"PRODIGIT,3315G,SIM000{self._slot},1.0"

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

    # --- helpers ---
    def _require_open(self) -> None:
        if not self._open:
            raise ConnectionLostError("Prodigit load mock is not open; call open() first.")
