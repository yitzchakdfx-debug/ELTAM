"""Real driver for the GW Instek DAQ-9600 mainframe + DAQ-901 multiplexer.

Transport: VISA (pyvisa). Implements `InstrumentDriver` plus — structurally —
the `Multimeter` and `DiscreteIO` capabilities (the BenchDriver router dispatches
via runtime_checkable isinstance, so explicit Protocol subclassing isn't needed).

pyvisa is optional at import time; `is_available()` gates Hardware mode. All comms
faults surface as the project's `HardwareError` subclasses so the bench
comms-check / Critical INIT can abort cleanly.
"""

from __future__ import annotations

from drivers.base_driver import ConnectionLostError
from drivers.bench.instrument_base import ConnInfo, InstrumentDriver
from drivers.bench.transports.visa import VisaSession, visa_available
from drivers.instruments.daq_9600 import protocol


class Daq9600(InstrumentDriver):
    """GW Instek DAQ-9600 over VISA. Capabilities: Multimeter, DiscreteIO."""

    def __init__(self) -> None:
        self._session: VisaSession | None = None
        # Remember the configured function per channel so read() measures correctly.
        self._functions: dict[int, str] = {}

    # --- InstrumentDriver lifecycle ---
    @classmethod
    def is_available(cls) -> bool:
        return visa_available()

    def open(self, conn: ConnInfo) -> None:
        timeout = int(conn.params.get("timeout_ms", 5000))
        self._session = VisaSession(conn.resource, timeout_ms=timeout)
        self._session.open()

    def close(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None
        self._functions.clear()

    def identify(self) -> str:
        idn = self._require_session().query(protocol.IDN)
        if not idn:
            raise ConnectionLostError("DAQ-9600 returned an empty *IDN? response.")
        return idn

    # --- Multimeter capability ---
    def configure(self, channel: int, function: str = "DCV") -> None:
        # Validates the function (raises ValueError on unknown) and sends CONF.
        self._require_session().write(protocol.configure(channel, function))
        self._functions[int(channel)] = function.strip().upper()

    def read(self, channel: int) -> float:
        function = self._functions.get(int(channel), "DCV")
        raw = self._require_session().query(protocol.measure(channel, function))
        return self._parse_float(raw)

    # --- DiscreteIO capability ---
    def set_line(self, line: int, state: bool) -> None:
        cmd = protocol.route_close(line) if state else protocol.route_open(line)
        self._require_session().write(cmd)

    def get_line(self, line: int) -> bool:
        raw = self._require_session().query(protocol.route_is_closed(line))
        return raw.strip().startswith("1")

    # --- helpers ---
    def _require_session(self) -> VisaSession:
        if self._session is None or not self._session.is_open:
            raise ConnectionLostError("DAQ-9600 session is not open; call open() first.")
        return self._session

    @staticmethod
    def _parse_float(raw: str) -> float:
        try:
            return float(raw.split(",")[0])
        except (ValueError, IndexError) as exc:
            raise ConnectionLostError(
                f"DAQ-9600 returned a non-numeric reading: {raw!r}"
            ) from exc
