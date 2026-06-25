"""Background monitor loop (simulated voltage/current until hardware is wired)."""

from __future__ import annotations

import random

from PySide6.QtCore import QThread, Signal


class MonitorThread(QThread):
    """Emits synthetic readings on an interval; replace simulation with driver polling later."""

    values_updated = Signal(dict)

    def __init__(
        self,
        parent: object | None = None,
        *,
        interval_ms: int = 500,
        simulate: bool = True,
    ) -> None:
        super().__init__(parent)
        self._interval_ms = max(1, interval_ms)
        self._simulate = simulate
        self._stop_requested = False

    def run(self) -> None:
        while not self._stop_requested:
            if self._simulate:
                voltage = 12.0 + random.uniform(-0.15, 0.15)
                current = 0.5 + random.uniform(-0.05, 0.05)
                self.values_updated.emit({"V": voltage, "A": current})
            self.msleep(self._interval_ms)

    def stop(self) -> None:
        self._stop_requested = True
        self.wait()
