"""Instrument capability layer for the DFX_ate bench driver.

Defines the device-facing contract each real or mock instrument implements.
Decoupled from (a) the runner's bench-level execute_command(name, args) -> float
contract (BenchDriver translates script commands into the capability calls here),
and (b) how connection details are stored (the factory decodes stored config into a
ConnInfo and hands it to open(); nothing here reads the DB or parses strings).

Rule 1 (no UI in logic/drivers): Qt-free. Rule 3 (all SQL in the DAL): no DB here.

Phase 0 scope: contract only — no transport code, no real device I/O. The SPREOS-3
instruments each implement InstrumentDriver plus the capability Protocol(s) they
support:

    IDRC-040-076HR PS  -> InstrumentDriver + VoltageSource
    GW DAQ-9600 + 901  -> InstrumentDriver + Multimeter + DiscreteIO
    Prodigit 3300F/15F -> InstrumentDriver + ElectronicLoad
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ConnInfo:
    """Transport-agnostic connection descriptor passed to open().

    Built by the factory from stored config; the capability layer never parses DB
    strings. `params` carries transport specifics the factory already decoded, e.g.
        serial   -> {"baud": 9600, "parity": "N", "stopbits": 1, "rtscts": True}
        visa     -> {}                       # everything in `resource`
        prologix -> {"gpib_address": 5}      # Prologix bridge COM in `resource`
    """

    transport: str          # "serial" | "visa" | "gpib" | "prologix" | "sim"
    resource: str           # "COM4" | "TCPIP0::192.168.0.50::INSTR" | "GPIB0::5::INSTR"
    params: dict[str, object] = field(default_factory=dict)


@runtime_checkable
class VoltageSource(Protocol):
    """Programmable DC source. SPREOS instrument: IDRC-040-076HR."""

    def set_output(self, on: bool) -> None: ...
    def set_voltage(self, volts: float) -> None: ...
    def measure_voltage(self) -> float: ...
    def measure_current(self) -> float: ...


@runtime_checkable
class ElectronicLoad(Protocol):
    """DC electronic load. SPREOS instrument: Prodigit 3315F module in a 3300F.

    set_power takes watts; the concrete driver selects the HIGH/LOW power band
    internally (the mainframe exposes CP:HIGH / CP:LOW, not one set-power command).
    set_input(False) is the safe state and must be driven on close()/abort.
    """

    def set_mode(self, mode: str) -> None: ...
    def set_power(self, watts: float) -> None: ...
    def set_input(self, on: bool) -> None: ...
    def measure_voltage(self) -> float: ...
    def measure_current(self) -> float: ...


@runtime_checkable
class Multimeter(Protocol):
    """DVM / scanner. SPREOS instrument: GW Instek DAQ-9600 + DAQ-901 mux.

    `channel` is the real DAQ-901 slot/channel; the script's logical readchannel N
    -> physical channel mapping lives in the per-version channel map, not here.
    """

    def configure(self, channel: int, function: str = "DCV") -> None: ...
    def read(self, channel: int) -> float: ...


@runtime_checkable
class DiscreteIO(Protocol):
    """Discrete on/off line control.

    For SPREOS, `setlogic` drives a relay wired to a DAQ-9600 switch channel (per
    bench wiring), so the DAQ driver implements this alongside Multimeter — there
    is no separate DIO instrument. `line` is the global bench-config relay channel.
    """

    def set_line(self, line: int, state: bool) -> None: ...
    def get_line(self, line: int) -> bool: ...


class InstrumentDriver(ABC):
    """Common lifecycle every instrument (real or mock) implements.

    A concrete device subclasses this AND the capability Protocol(s) it supports.
    The router checks Protocols at runtime, so adding an instrument never edits it.
    """

    @classmethod
    @abstractmethod
    def is_available(cls) -> bool:
        """True if this driver can run in Hardware mode.

        Checks transport/runtime presence (pyserial + COM port exists; a VISA
        backend present) and may probe the resource. MUST NOT raise — return False
        on any missing dependency so the Sim/HW gate can name the offender and stay
        in Simulation.
        """
        ...

    @abstractmethod
    def open(self, conn: ConnInfo) -> None:
        """Open the transport using the factory-provided descriptor.

        Raises on failure so the bench preflight/connect can report which
        instrument is down.
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """Drive to safe state and release the transport.

        Idempotent and safe after a failed open(). For the load: set_input(False);
        for the source: output off / 0 V.
        """
        ...

    @abstractmethod
    def identify(self) -> str:
        """Return a non-empty identity/version string, else raise.

        Identity is per-device protocol, not one shared SCPI string:
          * DAQ-9600        -> *IDN?
          * Prodigit 3300F  -> NAME? (no *IDN?); "NULL" = empty slot, which doubles
                               as the load-slot presence probe.
        A silent or "NULL" instrument must surface as a failure so the bench getid
        comms-check can abort the Critical INIT step.
        """
        ...
