"""Real driver for the Prodigit 3300G mainframe + 3315G electronic load.

Capability: `ElectronicLoad`. Transport: a **Prologix GPIB-USB** adapter over
pyserial (`SerialSession`). The mainframe has one GPIB address and up to 4 load
slots; this driver targets one slot (`load_slot` 1-4). It addresses the mainframe
once via Prologix `++addr` on open, then selects the slot with SCPI `CHAN n`
before every command.

`is_available()` gates on pyserial being importable. On `close()`/abort the load
input is switched off for safety.
"""

from __future__ import annotations

from drivers.base_driver import ConnectionLostError
from drivers.bench.instrument_base import ConnInfo, InstrumentDriver
from drivers.bench.transports.serial_port import SerialSession, serial_available
from drivers.instruments.prodigit_3300 import protocol


class Prodigit3300Load(InstrumentDriver):
    """Prodigit 3300G/3315G via a Prologix bridge. Capability: ElectronicLoad."""

    def __init__(self, *, load_slot: int, gpib_address: int) -> None:
        slot = int(load_slot)
        if not 1 <= slot <= 4:
            raise ValueError(f"load_slot must be 1-4 (got {load_slot!r}).")
        addr = int(gpib_address)
        if not 0 <= addr <= 30:
            raise ValueError(f"gpib_address must be 0-30 (got {gpib_address!r}).")
        self._slot = slot
        self._gpib = addr
        self._session: SerialSession | None = None

    # --- InstrumentDriver lifecycle ---
    @classmethod
    def is_available(cls) -> bool:
        return serial_available()

    def open(self, conn: ConnInfo) -> None:
        p = conn.params
        self._session = SerialSession(
            conn.resource,
            baud=int(p.get("baud", 115200)),  # Prologix is USB-CDC; baud nominal
            parity=str(p.get("parity", "N")),
            stopbits=str(p.get("stopbits", "1")),
            bytesize=int(p.get("bytesize", 8)),
            timeout_s=float(p.get("timeout_s", 3.0)),
            rtscts=bool(p.get("rtscts", False)),
        )
        self._session.open()
        # Point the Prologix bridge at the mainframe and enable auto read-after-write.
        for cmd in protocol.prologix_init(self._gpib):
            self._session.write(cmd)

    def close(self) -> None:
        if self._session is not None:
            try:
                self.set_input(False)  # safe state before releasing the port
            except Exception:
                pass
            self._session.close()
            self._session = None

    def identify(self) -> str:
        pre, query = protocol.identify(self._slot)
        name = self._write_then_query(pre, query)
        return self._check_name(name, self._slot)

    # --- ElectronicLoad capability ---
    def set_mode(self, mode: str) -> None:
        self._write_all(protocol.set_mode(self._slot, mode))

    def set_power(self, watts: float) -> None:
        self._write_all(protocol.set_power(self._slot, watts))

    def set_input(self, on: bool) -> None:
        self._write_all(protocol.set_input(self._slot, on))

    def measure_voltage(self) -> float:
        pre, query = protocol.measure_voltage(self._slot)
        return self._parse_float(self._write_then_query(pre, query))

    def measure_current(self) -> float:
        pre, query = protocol.measure_current(self._slot)
        return self._parse_float(self._write_then_query(pre, query))

    # --- helpers ---
    def _write_all(self, commands: list[str]) -> None:
        session = self._require_session()
        for cmd in commands:
            session.write(cmd)

    def _write_then_query(self, pre: list[str], query: str) -> str:
        session = self._require_session()
        for cmd in pre:
            session.write(cmd)
        return session.query(query)

    def _require_session(self) -> SerialSession:
        if self._session is None or not self._session.is_open:
            raise ConnectionLostError(
                "Prodigit load session is not open; call open() first."
            )
        return self._session

    @staticmethod
    def _check_name(name: str, slot: int) -> str:
        cleaned = (name or "").strip()
        if not cleaned or cleaned.upper() == "NULL":
            raise ConnectionLostError(
                f"Prodigit slot {slot} reports no module (NAME? -> {name!r}); "
                "check load_slot and that the module is seated."
            )
        return cleaned

    @staticmethod
    def _parse_float(raw: str) -> float:
        # Tolerate a trailing unit suffix (e.g. "12.5A", "28.0V", "200.0W").
        try:
            return float(raw.split(",")[0].strip().rstrip("VAWvaw ").strip() or raw)
        except (ValueError, IndexError) as exc:
            raise ConnectionLostError(
                f"Prodigit load returned a non-numeric reading: {raw!r}"
            ) from exc
