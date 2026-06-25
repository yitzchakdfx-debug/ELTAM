"""BenchDriver — composes the SPREOS instruments and routes `.tst` commands.

This is the bench-level `BaseDriver` the runner talks to. It owns three
capability objects (a `VoltageSource` PS, an `ElectronicLoad`, and a DAQ that is
both `Multimeter` and `DiscreteIO`) and translates each script command into the
right capability call:

    setvoltage <v>      -> source.set_voltage(v)
    setload <w>         -> load: w>0 => CP + set_power(w) + input on; w==0 => input off
    setlogic on|off     -> dio.set_line(daq_relay_channel, state)
    relay <line> on|off -> dio.set_line(line, state)
    readchannel <n>     -> channel map + step Unit -> source/load/dmm measurement
    getid               -> identify() across all instruments (raises on failure)

It is **pure routing** — instrument-agnostic, so the same class drives the
Simulation mocks and (later) the real drivers. All connection/wiring facts are
injected by the factory (never hardcoded here): the per-instrument `ConnInfo`s
and the `daq_relay_channel`.
"""

from __future__ import annotations

from drivers.base_driver import BaseDriver, HardwareError, UnknownCommandError
from drivers.bench import command_map
from drivers.bench.instrument_base import ConnInfo

# True-ish text for on/off style arguments (matches the mock convention).
_ON_WORDS = frozenset({"on", "1", "true", "yes", "close", "closed"})

_MEASUREMENT_COMMANDS = frozenset({"readchannel"})


class BenchDriver(BaseDriver):
    """Routes script commands to composed instruments. Capability-agnostic."""

    def __init__(
        self,
        *,
        source,
        load,
        dmm,
        source_conn: ConnInfo,
        load_conn: ConnInfo,
        dmm_conn: ConnInfo,
        daq_relay_channel: int | None = None,
        channel_map: dict[int, str] | None = None,
        daq_channel_map: dict[int, int] | None = None,
        labels: dict[str, str] | None = None,
    ) -> None:
        self._source = source            # VoltageSource (PS)
        self._load = load                # ElectronicLoad
        self._dmm = dmm                  # Multimeter + DiscreteIO (DAQ)
        self._conns = {
            id(source): source_conn,
            id(load): load_conn,
            id(dmm): dmm_conn,
        }
        # Ordered, de-duplicated instrument list (dmm may equal dio elsewhere).
        self._instruments = [source, load, dmm]
        self._labels = labels or {
            id(source): "Power Supply",
            id(load): "Electronic Load",
            id(dmm): "DAQ-9600",
        }
        self._daq_relay_channel = (
            int(daq_relay_channel) if daq_relay_channel is not None else None
        )
        self._channel_map = channel_map or command_map.SPREOS_CHANNEL_MAP
        # Logical script channel -> physical DAQ mux channel (data-driven; empty
        # forwards the script channel unchanged). Populated from bench_config.
        self._daq_channel_map = daq_channel_map or {}
        self._unit = ""
        self._min: float | None = None
        self._max: float | None = None

    # --- BaseDriver lifecycle ---
    def connect(self) -> bool:
        opened: list = []
        try:
            for inst in self._instruments:
                inst.open(self._conns[id(inst)])
                opened.append(inst)
            self._source.set_output(True)  # energize the PS rail for the run
            return True
        except HardwareError:
            for inst in reversed(opened):
                try:
                    inst.close()
                except Exception:
                    pass
            raise

    def disconnect(self) -> None:
        # Safe order: stop the load drawing, then the source, then the DAQ.
        # Each driver's close() drives its own safe state (load off / output off).
        for inst in (self._load, self._source, self._dmm):
            try:
                inst.close()
            except Exception:
                pass

    @property
    def measurement_commands(self) -> frozenset[str]:
        return _MEASUREMENT_COMMANDS

    def identify(self) -> dict[str, str]:
        ids: dict[str, str] = {}
        for inst in self._instruments:
            ids[self._labels[id(inst)]] = inst.identify()  # raises on failure
        return ids

    # --- runner context hook (duck-typed; disambiguates V vs A) ---
    def set_active_step(
        self, unit: str = "", min_val: float | None = None, max_val: float | None = None
    ) -> None:
        self._unit = (unit or "").strip()
        self._min = min_val
        self._max = max_val

    # --- command routing ---
    def execute_command(self, command: str, args: list[str]) -> float:
        name = command.lower()

        if name == "setvoltage":
            self._source.set_voltage(self._float_arg(args, 0, "setvoltage"))
            return 0.0

        if name == "setload":
            watts = self._float_arg(args, 0, "setload")
            if watts > 0:
                self._load.set_mode("CP")
                self._load.set_power(watts)
                self._load.set_input(True)
            else:
                self._load.set_input(False)
                self._load.set_power(0.0)
            return 0.0

        if name == "setlogic":
            self._dio_set_line(self._daq_relay_channel, self._on_state(args))
            return 0.0

        if name == "relay":
            if not args:
                raise ValueError("'relay' requires: relay <line> <on|off>")
            self._dio_set_line(int(args[0]), self._on_state(args))
            return 0.0

        if name == "getid":
            self.identify()  # ping all; raises ConnectionLostError on a dead unit
            return 0.0

        if name == "readchannel":
            return self._read_channel(int(self._arg(args, 0, "readchannel")))

        raise UnknownCommandError(f"Unknown bench command: {command!r}")

    # --- helpers ---
    def _read_channel(self, channel: int) -> float:
        role = self._channel_map.get(channel)
        if role is None:
            raise UnknownCommandError(
                f"no channel-map entry for readchannel {channel}"
            )
        current = command_map.wants_current(self._unit)
        if role == command_map.SOURCE:
            return self._source.measure_current() if current else self._source.measure_voltage()
        if role == command_map.LOAD:
            return self._load.measure_current() if current else self._load.measure_voltage()
        if role == command_map.DMM:
            # Voltage tap. Remap the logical script channel to the physical DAQ
            # mux channel via the data-driven map (falls back to the script
            # channel if unmapped).
            physical = self._daq_channel_map.get(channel, channel)
            return self._dmm.read(physical)
        raise UnknownCommandError(f"unknown channel role {role!r} for readchannel {channel}")

    def _dio_set_line(self, line: int | None, state: bool) -> None:
        if line is None:
            # Not configured. Hardware mode (Phase 4) validates this at connect;
            # the Simulation DAQ ignores the channel, so pass a placeholder.
            line = 0
        self._dmm.set_line(line, state)

    @staticmethod
    def _on_state(args: list[str]) -> bool:
        return bool(args) and args[-1].strip().lower() in _ON_WORDS

    @staticmethod
    def _arg(args: list[str], idx: int, cmd: str) -> str:
        if len(args) <= idx:
            raise ValueError(f"'{cmd}' is missing argument {idx + 1}")
        return args[idx]

    def _float_arg(self, args: list[str], idx: int, cmd: str) -> float:
        return float(self._arg(args, idx, cmd))
