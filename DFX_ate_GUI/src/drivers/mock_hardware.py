"""Qt-free mock hardware driver for ATE simulation.

Exposes a generic `execute_command(name, args) -> float` interface used by
the script-driven runner. Returns a measurement value for commands listed in
`MEASUREMENT_COMMANDS`; for side-effect commands (`setvoltage`, `relay`,
`getid`) the return value is ignored by the runner.
"""

from __future__ import annotations

import random
import time
from typing import ClassVar

from drivers.base_driver import BaseDriver, UnknownCommandError


class MockHardware(BaseDriver):
    """Simulates hardware instrument responses without any Qt dependencies."""

    MEASUREMENT_COMMANDS: ClassVar[frozenset[str]] = frozenset({"readchannel"})

    _CHANNEL_NOMINALS: ClassVar[dict[int, tuple[float, float, int]]] = {
        0: (5.0, 0.05, 3),    # 5 V rail, +/- ~50 mV jitter, 3 decimals
        1: (12.0, 0.10, 3),   # 12 V rail, +/- ~100 mV jitter
        2: (28.0, 0.20, 3),   # 28 V rail, +/- ~200 mV jitter
        3: (1.2, 0.30, 3),    # 1.2 A current, wider jitter
        10: (0.0, 0.05, 3),   # 0 V rail, +/- ~50 mV jitter
    }
    _OUT_OF_SPEC_PROB: ClassVar[float] = 0.25

    def __init__(self) -> None:
        self.connected = False
        self._rng = random.Random()

    def connect(self) -> bool:
        time.sleep(0.5)
        self.connected = True
        return True

    def disconnect(self) -> None:
        self.connected = False

    @property
    def measurement_commands(self) -> frozenset[str]:
        return self.MEASUREMENT_COMMANDS

    def execute_command(self, command: str, args: list[str]) -> float:
        cmd = command.lower()

        if cmd == "readchannel":
            channel = int(args[0]) if args else 0
            return self._read_channel(channel)

        if cmd in ("setvoltage", "relay", "getid"):
            time.sleep(0.05)
            return 0.0

        if cmd == "setlogic":
            # args: [<line: int>, <on|off>]  — side-effect only, no measurement.
            time.sleep(0.05)
            return 0.0

        raise UnknownCommandError(f"Unknown hardware command: {command!r}")

    def _read_channel(self, channel: int) -> float:
        nominal, jitter, decimals = self._CHANNEL_NOMINALS.get(
            channel, (50.0, 35.0, 2)
        )
        time.sleep(self._rng.uniform(0.2, 0.6))
        outside = self._rng.random() < self._OUT_OF_SPEC_PROB
        spread = jitter * (3.0 if outside else 1.0)
        value = nominal + self._rng.uniform(-spread, spread)
        return round(value, decimals)
