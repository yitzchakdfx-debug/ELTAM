"""Thin pyserial session wrapper used by RS-232 instrument drivers.

pyserial is a declared dependency but imported guarded so the package still
imports if it is somehow absent; `serial_available()` is the Hardware-mode gate.
Drivers own the protocol; this manages the port and maps faults onto the
project's `HardwareError` hierarchy.
"""

from __future__ import annotations

from drivers.base_driver import (
    CommandTimeoutError,
    ConnectionLostError,
    HardwareError,
)

try:  # pyserial; guarded so a pure-Simulation install still imports
    import serial
except Exception:  # pragma: no cover - import guard
    serial = None


def serial_available() -> bool:
    """True iff pyserial is importable. Never raises."""
    return serial is not None


# Logical config strings -> pyserial constant attribute names (resolved lazily,
# only when serial is present, so the module imports without pyserial).
_PARITY = {"N": "PARITY_NONE", "E": "PARITY_EVEN", "O": "PARITY_ODD",
           "M": "PARITY_MARK", "S": "PARITY_SPACE"}
_STOPBITS = {"1": "STOPBITS_ONE", "1.5": "STOPBITS_ONE_POINT_FIVE", "2": "STOPBITS_TWO"}
_BYTESIZE = {5: "FIVEBITS", 6: "SIXBITS", 7: "SEVENBITS", 8: "EIGHTBITS"}


class SerialSession:
    """Minimal open/query/write/close over a single pyserial port."""

    def __init__(
        self,
        port: str,
        *,
        baud: int = 9600,
        parity: str = "N",
        stopbits: str = "1",
        bytesize: int = 8,
        timeout_s: float = 2.0,
        rtscts: bool = False,
        read_termination: str = "\n",
        write_termination: str = "\n",
    ) -> None:
        self._port = port
        self._baud = int(baud)
        self._parity = str(parity).upper()
        self._stopbits = str(stopbits)
        self._bytesize = int(bytesize)
        self._timeout_s = float(timeout_s)
        self._rtscts = bool(rtscts)
        self._read_termination = read_termination
        self._write_termination = write_termination
        self._inst = None

    @property
    def is_open(self) -> bool:
        return self._inst is not None

    def open(self) -> None:
        if serial is None:
            raise HardwareError("pyserial is not installed; cannot open a serial session.")
        try:
            self._inst = serial.Serial(
                port=self._port,
                baudrate=self._baud,
                bytesize=getattr(serial, _BYTESIZE.get(self._bytesize, "EIGHTBITS")),
                parity=getattr(serial, _PARITY.get(self._parity, "PARITY_NONE")),
                stopbits=getattr(serial, _STOPBITS.get(self._stopbits, "STOPBITS_ONE")),
                timeout=self._timeout_s,
                rtscts=self._rtscts,
            )
        except Exception as exc:
            self.close()
            raise ConnectionLostError(
                f"Could not open serial port {self._port!r}: {exc}"
            ) from exc

    def write(self, command: str) -> None:
        inst = self._require_inst()
        try:
            inst.write((command + self._write_termination).encode())
        except Exception as exc:
            raise self._map_error(exc, command) from exc

    def query(self, command: str) -> str:
        self.write(command)
        inst = self._require_inst()
        try:
            raw = inst.read_until(self._read_termination.encode())
        except Exception as exc:
            raise self._map_error(exc, command) from exc
        text = raw.decode(errors="replace").strip()
        if not text:
            raise CommandTimeoutError(
                f"No response to {command!r} within {self._timeout_s}s."
            )
        return text

    def close(self) -> None:
        try:
            if self._inst is not None:
                self._inst.close()
        except Exception:
            pass
        self._inst = None

    def _require_inst(self):
        if self._inst is None:
            raise ConnectionLostError("Serial session is not open.")
        return self._inst

    @staticmethod
    def _map_error(exc: Exception, command: str) -> HardwareError:
        text = f"{type(exc).__name__}: {exc}".lower()
        if "timeout" in text:
            return CommandTimeoutError(f"Serial timeout on {command!r}: {exc}")
        return ConnectionLostError(f"Serial error on {command!r}: {exc}")
