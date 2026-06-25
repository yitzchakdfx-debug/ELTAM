"""Thin pyvisa session wrapper used by VISA/GPIB instrument drivers.

pyvisa (and a VISA backend — NI-VISA, or the pure-Python `pyvisa-py`) is an
OPTIONAL runtime dependency. It is imported guarded so the app runs in
Simulation mode with no VISA stack present; `visa_available()` is the gate
Hardware mode checks. Drivers own the SCPI — this only manages the session and
maps pyvisa faults onto the project's `HardwareError` hierarchy.
"""

from __future__ import annotations

from drivers.base_driver import (
    CommandTimeoutError,
    ConnectionLostError,
    HardwareError,
)

try:  # optional dependency — absent in a pure-Simulation install
    import pyvisa
except Exception:  # pragma: no cover - import guard
    pyvisa = None


def visa_available() -> bool:
    """True iff pyvisa imports AND a VISA backend resource manager can open.

    Never raises — returns False on any missing dependency so the Sim/HW gate can
    stay in Simulation and name the offending instrument.
    """
    if pyvisa is None:
        return False
    try:
        rm = pyvisa.ResourceManager()
        rm.close()
        return True
    except Exception:
        return False


class VisaSession:
    """Minimal open/query/write/close over a single pyvisa resource."""

    def __init__(
        self,
        resource: str,
        *,
        timeout_ms: int = 5000,
        read_termination: str = "\n",
        write_termination: str = "\n",
    ) -> None:
        self._resource = resource
        self._timeout_ms = timeout_ms
        self._read_termination = read_termination
        self._write_termination = write_termination
        self._rm = None
        self._inst = None

    @property
    def is_open(self) -> bool:
        return self._inst is not None

    def open(self) -> None:
        if pyvisa is None:
            raise HardwareError("pyvisa is not installed; cannot open a VISA session.")
        try:
            self._rm = pyvisa.ResourceManager()
            self._inst = self._rm.open_resource(self._resource)
            self._inst.timeout = self._timeout_ms
            self._inst.read_termination = self._read_termination
            self._inst.write_termination = self._write_termination
        except Exception as exc:
            self.close()
            raise ConnectionLostError(
                f"Could not open VISA resource {self._resource!r}: {exc}"
            ) from exc

    def write(self, command: str) -> None:
        try:
            self._require_inst().write(command)
        except HardwareError:
            raise
        except Exception as exc:
            raise self._map_error(exc, command) from exc

    def query(self, command: str) -> str:
        try:
            return self._require_inst().query(command).strip()
        except HardwareError:
            raise
        except Exception as exc:
            raise self._map_error(exc, command) from exc

    def close(self) -> None:
        for obj in (self._inst, self._rm):
            try:
                if obj is not None:
                    obj.close()
            except Exception:
                pass
        self._inst = None
        self._rm = None

    def _require_inst(self):
        if self._inst is None:
            raise ConnectionLostError("VISA session is not open.")
        return self._inst

    @staticmethod
    def _map_error(exc: Exception, command: str) -> HardwareError:
        text = f"{type(exc).__name__}: {exc}".lower()
        if "timeout" in text:
            return CommandTimeoutError(f"VISA timeout on {command!r}: {exc}")
        return ConnectionLostError(f"VISA error on {command!r}: {exc}")
