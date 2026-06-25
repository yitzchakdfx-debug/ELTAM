"""Background worker that probes the real bench off the GUI thread.

Hardware preflight opens each instrument and queries `identify()`, which can
block for seconds on a VISA/serial timeout when a unit is powered off. Running it
in this `QThread` keeps the UI responsive; the result is delivered via `completed`.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from drivers.bench.factory import preflight


class PreflightWorker(QThread):
    """Runs `factory.preflight()` and emits `completed(ok, report_lines)`."""

    completed = Signal(bool, list)

    def __init__(
        self,
        connections: dict[str, str],
        bench_cfg: dict[str, str],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._connections = dict(connections)
        self._bench_cfg = dict(bench_cfg)

    def run(self) -> None:
        try:
            ok, report = preflight(
                connections=self._connections, bench_cfg=self._bench_cfg
            )
        except Exception as exc:  # defensive: never let the worker die silently
            ok, report = False, [f"Preflight error: {exc}"]
        self.completed.emit(bool(ok), list(report))
