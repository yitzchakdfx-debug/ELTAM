"""Real driver for the IDRC-040-076HR programmable DC power supply (RS-232).

Capability: VoltageSource. Transport: pyserial. `is_available()` gates on
pyserial being importable. The SCPI strings live in `protocol.py` and are
PROVISIONAL until confirmed against the manual (TODO manual). On close()/abort
the output is driven off for safety.
"""

from __future__ import annotations

from drivers.base_driver import ConnectionLostError
from drivers.bench.instrument_base import ConnInfo, InstrumentDriver
from drivers.bench.transports.serial_port import SerialSession, serial_available
from drivers.instruments.idrc_040_076hr import protocol


class IdrcPowerSupply(InstrumentDriver):
    """IDRC-040-076HR over RS-232. Capability: VoltageSource."""

    def __init__(self) -> None:
        self._session: SerialSession | None = None

    # --- InstrumentDriver lifecycle ---
    @classmethod
    def is_available(cls) -> bool:
        return serial_available()

    def open(self, conn: ConnInfo) -> None:
        p = conn.params
        self._session = SerialSession(
            conn.resource,
            baud=int(p.get("baud", 9600)),
            parity=str(p.get("parity", "N")),
            stopbits=str(p.get("stopbits", "1")),
            bytesize=int(p.get("bytesize", 8)),
            timeout_s=float(p.get("timeout_s", 2.0)),
            rtscts=bool(p.get("rtscts", False)),
        )
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
            raise ConnectionLostError("IDRC PS returned an empty *IDN? response.")
        return idn

    # --- VoltageSource capability ---
    def set_output(self, on: bool) -> None:
        self._require_session().write(protocol.output(on))

    def set_voltage(self, volts: float) -> None:
        self._require_session().write(protocol.set_voltage(volts))

    def measure_voltage(self) -> float:
        return self._parse_float(self._require_session().query(protocol.measure_voltage()))

    def measure_current(self) -> float:
        return self._parse_float(self._require_session().query(protocol.measure_current()))

    # --- extra: SPREOS INIT sets OVP=35 V, OCP=20 A before power-up ---
    def set_protection(self, ovp_volts: float, ocp_amps: float) -> None:
        session = self._require_session()
        session.write(protocol.set_ovp(ovp_volts))
        session.write(protocol.set_ocp(ocp_amps))

    # --- helpers ---
    def _require_session(self) -> SerialSession:
        if self._session is None or not self._session.is_open:
            raise ConnectionLostError("IDRC PS session is not open; call open() first.")
        return self._session

    @staticmethod
    def _parse_float(raw: str) -> float:
        # Tolerate a trailing unit suffix some supplies append, e.g. "28.00V".
        try:
            return float(raw.split(",")[0].strip().rstrip("VAvavolts ").strip() or raw)
        except (ValueError, IndexError) as exc:
            raise ConnectionLostError(
                f"IDRC PS returned a non-numeric reading: {raw!r}"
            ) from exc
