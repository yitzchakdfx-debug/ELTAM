"""Bench-driver factory + hardware preflight.

`build_bench(...)` is what `main_window` calls; it configures the bench
*dynamically* from the stored definitions the caller passes in — per-instrument
resources (`instrument_connections`) and bench wiring (`bench_config`). Nothing
here hardcodes a COM port, GPIB address, load slot, or DAQ channel.

- **Simulation** (default): three coupled mocks sharing a `SimBus`.
- **Hardware**: real drivers built from the parsed connection strings.

`preflight(...)` probes the real instruments (`is_available()` + open/identify)
and returns a human-readable report so the GUI can refuse to start a run against
an instrument that is powered off / unplugged, with a clear message.
"""

from __future__ import annotations

from drivers.base_driver import BaseDriver, HardwareError
from drivers.bench import bench_spec, command_map
from drivers.bench.bench_driver import BenchDriver
from drivers.bench.instrument_base import ConnInfo
from drivers.bench.sim_bus import SimBus
from drivers.instruments.daq_9600.driver import Daq9600
from drivers.instruments.daq_9600.mock import Daq9600Mock
from drivers.instruments.idrc_040_076hr.driver import IdrcPowerSupply
from drivers.instruments.idrc_040_076hr.mock import IdrcPowerSupplyMock
from drivers.instruments.prodigit_3300.driver import Prodigit3300Load
from drivers.instruments.prodigit_3300.mock import Prodigit3300LoadMock

# bench_config keys (mirror logic.db.bench_config; duplicated to keep drivers/
# free of a logic/ import).
_KEY_DAQ_RELAY_CHANNEL = "daq_relay_channel"
_KEY_LOAD_SLOT = "load_slot"
_KEY_DAQ_CHANNEL_MAP = "daq_channel_map"

# Default per-measurement out-of-spec probability for the Simulation bench.
SIM_FAIL_PROB = 0.02

_PARITY_CODES = frozenset({"N", "E", "O", "M", "S"})
_STOPBITS_CODES = frozenset({"1", "1.5", "2"})


class BenchConfigError(Exception):
    """Raised when the stored config is incomplete/invalid for Hardware mode."""

    def __init__(self, messages: list[str]) -> None:
        super().__init__("; ".join(messages))
        self.messages = messages


# --------------------------------------------------------------------------- #
# Public entry points
# --------------------------------------------------------------------------- #
def build_bench(
    *,
    hardware_mode: bool = False,
    connections: dict[str, str] | None = None,
    bench_cfg: dict[str, str] | None = None,
) -> BaseDriver:
    """Return the driver the runner should use, configured from stored definitions."""
    if hardware_mode:
        return _build_hardware_bench(connections or {}, bench_cfg or {})
    return build_sim_bench(bench_cfg=bench_cfg or {})


def build_sim_bench(
    *,
    bench_cfg: dict[str, str] | None = None,
    fail_prob: float = SIM_FAIL_PROB,
    seed: int | None = None,
) -> BenchDriver:
    """Coupled Simulation bench: three mocks sharing one `SimBus`."""
    cfg = bench_cfg or {}
    bus = SimBus()
    source = IdrcPowerSupplyMock(bus=bus, fail_prob=fail_prob, seed=_seed(seed, 0))
    dmm = Daq9600Mock(bus=bus, fail_prob=fail_prob, seed=_seed(seed, 1))
    load = Prodigit3300LoadMock(
        load_slot=_int(cfg.get(_KEY_LOAD_SLOT), default=1, lo=1, hi=4),
        gpib_address=0,  # placeholder; the mock ignores it (never a real address)
        bus=bus,
        fail_prob=fail_prob,
        seed=_seed(seed, 2),
    )
    sim_conn = ConnInfo("sim", "MOCK")
    return BenchDriver(
        source=source, load=load, dmm=dmm,
        source_conn=sim_conn, load_conn=sim_conn, dmm_conn=sim_conn,
        daq_relay_channel=_int(cfg.get(_KEY_DAQ_RELAY_CHANNEL), default=None),
        daq_channel_map=parse_daq_channel_map(cfg.get(_KEY_DAQ_CHANNEL_MAP, "")),
    )


def preflight(
    *,
    connections: dict[str, str] | None = None,
    bench_cfg: dict[str, str] | None = None,
) -> tuple[bool, list[str]]:
    """Check the real bench is usable. Returns (ok, human-readable report lines).

    For each instrument: gate on `is_available()` (transport/runtime present),
    then open + `identify()` (reachable). Never raises — connectivity faults are
    captured as report lines so the GUI can show them and offer a fallback.
    """
    try:
        specs = _hardware_specs(connections or {}, bench_cfg or {})
    except BenchConfigError as exc:
        return False, ["Configuration error:"] + [f"  - {m}" for m in exc.messages]

    overall = True
    report: list[str] = []
    for _role, label, driver, conn in specs:
        if not type(driver).is_available():
            overall = False
            report.append(
                f"[X] {label}: driver/runtime unavailable "
                f"(VISA or serial backend not installed)"
            )
            continue
        try:
            driver.open(conn)
            name = driver.identify()
            report.append(f"[OK] {label}: {name}  [{conn.transport} {conn.resource}]")
        except HardwareError as exc:
            overall = False
            report.append(f"[X] {label}: not responding — {exc}")
        finally:
            try:
                driver.close()
            except Exception:
                pass
    return overall, report


# --------------------------------------------------------------------------- #
# Hardware construction
# --------------------------------------------------------------------------- #
def _build_hardware_bench(connections: dict[str, str], bench_cfg: dict[str, str]) -> BaseDriver:
    specs = _hardware_specs(connections, bench_cfg)
    by_role = {role: (label, drv, conn) for role, label, drv, conn in specs}
    return BenchDriver(
        source=by_role["source"][1],
        load=by_role["load"][1],
        dmm=by_role["dmm"][1],
        source_conn=by_role["source"][2],
        load_conn=by_role["load"][2],
        dmm_conn=by_role["dmm"][2],
        daq_relay_channel=_int(bench_cfg.get(_KEY_DAQ_RELAY_CHANNEL), default=None),
        daq_channel_map=parse_daq_channel_map(bench_cfg.get(_KEY_DAQ_CHANNEL_MAP, "")),
    )


def _hardware_specs(connections: dict[str, str], bench_cfg: dict[str, str]):
    """Build (role, label, driver, ConnInfo) for each instrument; validate config.

    Raises BenchConfigError listing every missing/invalid item so the operator
    sees them all at once.
    """
    ps_conn = parse_serial(connections.get(bench_spec.POWER_SUPPLY, ""))
    daq_conn = parse_visa(connections.get(bench_spec.DAQ, ""))
    load_conn = parse_prologix(connections.get(bench_spec.ELECTRONIC_LOAD, ""))
    gpib = load_conn.params.get("gpib_address")
    slot = _int(bench_cfg.get(_KEY_LOAD_SLOT), default=None, lo=1, hi=4)

    errors: list[str] = []
    if not ps_conn.resource:
        errors.append(f"{bench_spec.POWER_SUPPLY}: COM port not set in Connections")
    if not daq_conn.resource:
        errors.append(f"{bench_spec.DAQ}: VISA resource not set in Connections")
    if not load_conn.resource:
        errors.append(f"{bench_spec.ELECTRONIC_LOAD}: COM port not set in Connections")
    if gpib is None:
        errors.append(
            f"{bench_spec.ELECTRONIC_LOAD}: GPIB address missing "
            "(add 'GPIB:<n>' to its connection string)"
        )
    if slot is None:
        errors.append("bench_config 'load_slot' not set (1-4)")
    if errors:
        raise BenchConfigError(errors)

    return [
        ("source", bench_spec.POWER_SUPPLY, IdrcPowerSupply(), ps_conn),
        ("dmm", bench_spec.DAQ, Daq9600(), daq_conn),
        ("load", bench_spec.ELECTRONIC_LOAD,
         Prodigit3300Load(load_slot=slot, gpib_address=gpib), load_conn),
    ]


# --------------------------------------------------------------------------- #
# Connection-string parsing (robust; missing parts -> defaults, with no raise)
# --------------------------------------------------------------------------- #
def parse_serial(conn_str: str) -> ConnInfo:
    """`PORT|BAUD|PARITY|STOPBITS` -> serial ConnInfo. Missing fields omitted."""
    parts = [p.strip() for p in str(conn_str or "").split("|")]
    port = parts[0] if parts else ""
    params: dict[str, object] = {}
    if len(parts) > 1 and parts[1]:
        params["baud"] = _int(parts[1], default=9600)
    if len(parts) > 2 and parts[2]:
        params["parity"] = parts[2].upper()
    if len(parts) > 3 and parts[3]:
        params["stopbits"] = parts[3]
    return ConnInfo("serial", port, params)


def parse_visa(conn_str: str) -> ConnInfo:
    """A raw VISA resource string -> visa ConnInfo (no pipe parsing)."""
    return ConnInfo("visa", str(conn_str or "").strip(), {})


def parse_prologix(conn_str: str) -> ConnInfo:
    """`PORT[|BAUD|PARITY|STOP][|GPIB:<addr>]` -> prologix ConnInfo.

    The COM port is the first field; the GPIB address is a token like `GPIB:6`
    (or `GPIB=6` / `GPIB 6`); serial params are recognized positionally-agnostic.
    """
    parts = [p.strip() for p in str(conn_str or "").split("|")]
    port = parts[0] if parts else ""
    params: dict[str, object] = {"gpib_address": None}
    for tok in parts[1:]:
        if not tok:
            continue
        upper = tok.upper()
        if upper.startswith("GPIB"):
            digits = "".join(ch for ch in upper if ch.isdigit())
            if digits:
                params["gpib_address"] = int(digits)
        elif upper in _PARITY_CODES:
            params["parity"] = upper
        elif tok in _STOPBITS_CODES:
            params["stopbits"] = tok
        elif tok.isdigit():
            params["baud"] = int(tok)
    return ConnInfo("prologix", port, params)


def parse_daq_channel_map(text: str) -> dict[int, int]:
    """`"3=103, 4=104"` -> {3: 103, 4: 104}. Malformed pairs are skipped."""
    result: dict[int, int] = {}
    for pair in str(text or "").split(","):
        pair = pair.strip()
        if "=" not in pair:
            continue
        logical, _, physical = pair.partition("=")
        try:
            result[int(logical.strip())] = int(physical.strip())
        except ValueError:
            continue
    return result


# --- small helpers --------------------------------------------------------- #
def _int(value, *, default, lo: int | None = None, hi: int | None = None):
    """Parse a stored TEXT value to int; fall back to default; optionally clamp."""
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    if lo is not None and n < lo:
        return default
    if hi is not None and n > hi:
        return default
    return n


def _seed(base: int | None, offset: int) -> int | None:
    return None if base is None else base + offset
