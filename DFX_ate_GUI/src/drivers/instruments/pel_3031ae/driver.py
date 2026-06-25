"""Real driver for the GW Instek PEL-3031AE DC electronic load.

Capability: ElectronicLoad (bench LOAD role). Transport: VISA (pyvisa) — the
PEL enumerates over USB as a USB-CDC virtual COM (addressable as an ``ASRL``
VISA resource) or via optional GPIB/LAN. `is_available()` gates Hardware mode
on a working VISA backend. SCPI lives in `protocol.py` and is VERIFIED against
the PEL-3000(H) Programming Manual.

The PEL addresses a single load per unit (no channel select). On close()/abort
the load input is switched OFF for safety.
"""

from __future__ import annotations

from drivers.base_driver import ConnectionLostError
from drivers.bench.instrument_base import ConnInfo, InstrumentDriver
from drivers.bench.transports.visa import VisaSession, visa_available
from drivers.instruments.pel_3031ae import protocol


class Pel3031Load(InstrumentDriver):
    """GW Instek PEL-3031AE over VISA. Capability: ElectronicLoad."""

    def __init__(self) -> None:
        self._session: VisaSession | None = None

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
            try:
                self.set_input(False)  # safe state before releasing the port
            except Exception:
                pass
            self._session.close()
            self._session = None

    def identify(self) -> str:
        idn = self._require_session().query(protocol.IDN)
        if not idn:
            raise ConnectionLostError("PEL-3031AE returned an empty *IDN? response.")
        return idn

    # --- ElectronicLoad capability ---
    def set_mode(self, mode: str) -> None:
        self._require_session().write(protocol.set_mode(mode))

    def set_power(self, watts: float) -> None:
        self._require_session().write(protocol.set_power(watts))

    def set_input(self, on: bool) -> None:
        self._require_session().write(protocol.set_input(on))

    def measure_voltage(self) -> float:
        return self._parse_float(self._require_session().query(protocol.measure_voltage()))

    def measure_current(self) -> float:
        return self._parse_float(self._require_session().query(protocol.measure_current()))

    def measure_power(self) -> float:
        return self._parse_float(self._require_session().query(protocol.measure_power()))

    # --- helpers ---
    def _require_session(self) -> VisaSession:
        if self._session is None or not self._session.is_open:
            raise ConnectionLostError("PEL-3031AE session is not open; call open() first.")
        return self._session

    @staticmethod
    def _parse_float(raw: str) -> float:
        # PEL appends a unit suffix on some firmware (e.g. "0.50000A"); strip it.
        try:
            return float(raw.split(",")[0].strip().rstrip("VAWvaw ").strip() or raw)
        except (ValueError, IndexError) as exc:
            raise ConnectionLostError(
                f"PEL-3031AE returned a non-numeric reading: {raw!r}"
            ) from exc
