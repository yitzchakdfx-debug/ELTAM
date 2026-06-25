"""Mock for the GW Instek DAQ-9600 — Qt-free, no I/O. Phase 1 scaffolding.

Exposes the same `InstrumentDriver` + `Multimeter` + `DiscreteIO` surface as the
real driver, returning plausible per-channel voltages and tracking relay state,
so the bench sim path and unit tests run against an identical API. Full SPREOS
sim parity (readings driven by shared PS/load state) lands with the BenchDriver
in Phase 3; this mock is intentionally standalone for now.
"""

from __future__ import annotations

import random

from drivers.base_driver import ConnectionLostError
from drivers.bench.instrument_base import ConnInfo, InstrumentDriver
from drivers.bench.sim_bus import SimBus, reading


class Daq9600Mock(InstrumentDriver):
    """Simulated DAQ-9600. Capabilities: Multimeter, DiscreteIO.

    Standalone by default; pass `bus` to couple it into a shared bench
    simulation (voltage taps then follow the PS rail and `set_line` drives the
    shared logic-power state).
    """

    def __init__(
        self,
        *,
        nominal: float = 28.0,
        seed: int | None = None,
        bus: SimBus | None = None,
        fail_prob: float = 0.0,
    ) -> None:
        self._open = False
        self._nominal = nominal
        self._rng = random.Random(seed)
        self._functions: dict[int, str] = {}
        self._closed: set[int] = set()
        self._bus = bus
        self._fail_prob = fail_prob

    # --- InstrumentDriver lifecycle ---
    @classmethod
    def is_available(cls) -> bool:
        return True

    def open(self, conn: ConnInfo) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False
        self._closed.clear()
        self._functions.clear()

    def identify(self) -> str:
        self._require_open()
        return "GW INSTEK,DAQ-9600,SIM0000,1.00"

    # --- Multimeter capability ---
    def configure(self, channel: int, function: str = "DCV") -> None:
        self._require_open()
        self._functions[int(channel)] = function.strip().upper()

    def read(self, channel: int) -> float:
        self._require_open()
        if self._bus is not None:
            return reading(self._rng, self._bus.input_voltage, fail_prob=self._fail_prob)
        return round(self._nominal + self._rng.uniform(-0.05, 0.05), 4)

    # --- DiscreteIO capability ---
    def set_line(self, line: int, state: bool) -> None:
        self._require_open()
        if self._bus is not None:
            self._bus.logic_on = bool(state)  # the relay drives logic power
            return
        if state:
            self._closed.add(int(line))
        else:
            self._closed.discard(int(line))

    def get_line(self, line: int) -> bool:
        self._require_open()
        if self._bus is not None:
            return self._bus.logic_on
        return int(line) in self._closed

    # --- helpers ---
    def _require_open(self) -> None:
        if not self._open:
            raise ConnectionLostError("DAQ-9600 mock is not open; call open() first.")
