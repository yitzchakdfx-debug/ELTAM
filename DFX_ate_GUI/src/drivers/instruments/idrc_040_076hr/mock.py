"""Mock for the IDRC-040-076HR PS — Qt-free, no I/O. Phase 2 scaffolding.

Exposes the same `InstrumentDriver` + `VoltageSource` surface as the real driver:
tracks output state / setpoint and returns plausible readings (set voltage when
the output is on, ~0 V off; a small idle current). Full SPREOS sim parity
(readings coupled to the load) lands with the BenchDriver in Phase 3.
"""

from __future__ import annotations

import random

from drivers.base_driver import ConnectionLostError
from drivers.bench.instrument_base import ConnInfo, InstrumentDriver
from drivers.bench.sim_bus import SimBus, reading


class IdrcPowerSupplyMock(InstrumentDriver):
    """Simulated IDRC-040-076HR. Capability: VoltageSource.

    Standalone by default; pass `bus` to couple it into a shared bench
    simulation (the PS rail is then read/written via the shared `SimBus`).
    """

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
        self._ovp = 35.0
        self._ocp = 20.0
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
        return "IDRC,IDRC-040-076HR,SIM0000,1.0"

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
        # Quiescent PS draw (no load on CH1 in the SPREOS current check).
        if self._bus is not None:
            return reading(self._rng, 0.21, jitter=0.09, fail_prob=self._fail_prob)
        return round(self._rng.uniform(0.12, 0.30), 4)

    # --- extra ---
    def set_protection(self, ovp_volts: float, ocp_amps: float) -> None:
        self._require_open()
        self._ovp = float(ovp_volts)
        self._ocp = float(ocp_amps)

    # --- helpers ---
    def _require_open(self) -> None:
        if not self._open:
            raise ConnectionLostError("IDRC PS mock is not open; call open() first.")
