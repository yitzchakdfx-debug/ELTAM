"""Real driver for the GW Instek GPP-3610H programmable DC power supply.

Capability: VoltageSource (bench SOURCE role). Transport: VISA (pyvisa) —
the GPP exposes USB (USB-CDC virtual COM, addressable as an ``ASRL`` VISA
resource), LAN (``TCPIP::...::INSTR``) and optional GPIB. `is_available()`
gates Hardware mode on a working VISA backend. SCPI lives in `protocol.py`
and is confirmed against the GPP programming manual.

On close()/abort the output is driven OFF for safety.
"""

from __future__ import annotations

from drivers.base_driver import ConnectionLostError
from drivers.bench.instrument_base import ConnInfo, InstrumentDriver
from drivers.bench.transports.visa import VisaSession, visa_available
from drivers.instruments.gpp_3610h import protocol


class Gpp3610hPowerSupply(InstrumentDriver):
    """GW Instek GPP-3610H over VISA. Capability: VoltageSource."""

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
                self.set_output(False)  # safe state before releasing the port
            except Exception:
                pass
            self._session.close()
            self._session = None

    def identify(self) -> str:
        idn = self._require_session().query(protocol.IDN)
        if not idn:
            raise ConnectionLostError("GPP-3610H returned an empty *IDN? response.")
        return idn

    # --- VoltageSource capability ---
    def set_output(self, on: bool) -> None:
        self._require_session().write(protocol.output(on))

    def set_voltage(self, volts: float) -> None:
        self._require_session().write(protocol.set_voltage(volts))

    def set_current(self, amps: float) -> None:
        """Set the output current limit (not part of VoltageSource; handy for INIT)."""
        self._require_session().write(protocol.set_current(amps))

    def measure_voltage(self) -> float:
        return self._parse_float(self._require_session().query(protocol.measure_voltage()))

    def measure_current(self) -> float:
        return self._parse_float(self._require_session().query(protocol.measure_current()))

    def measure_power(self) -> float:
        return self._parse_float(self._require_session().query(protocol.measure_power()))

    # --- helpers ---
    def _require_session(self) -> VisaSession:
        if self._session is None or not self._session.is_open:
            raise ConnectionLostError("GPP-3610H session is not open; call open() first.")
        return self._session

    @staticmethod
    def _parse_float(raw: str) -> float:
        # GPP returns a bare number (e.g. "28.0000"); tolerate a unit suffix anyway.
        try:
            return float(raw.split(",")[0].strip().rstrip("VAWvaw ").strip() or raw)
        except (ValueError, IndexError) as exc:
            raise ConnectionLostError(
                f"GPP-3610H returned a non-numeric reading: {raw!r}"
            ) from exc
