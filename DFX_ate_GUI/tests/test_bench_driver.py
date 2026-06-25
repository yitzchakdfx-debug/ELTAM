"""Tests for the BenchDriver router and the coupled Simulation bench.

Two layers, both offline:
- `RoutingTests` drive a BenchDriver built from recording fakes, asserting each
  `.tst` command maps to the right capability call (and V/A disambiguation).
- `SimBenchTests` run the actual SPREOS `.tst` end-to-end through the coupled
  Simulation bench and assert a clean pass (fail injection disabled, fixed seed).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from drivers.base_driver import ConnectionLostError, UnknownCommandError
from drivers.bench.bench_driver import BenchDriver
from drivers.bench.factory import build_sim_bench
from drivers.bench.instrument_base import ConnInfo
from logic.script_manager import ScriptManager

SPREOS = SRC / "data" / "SPREOS Power Supply Main Card Fix.tst"


# --- recording fakes (capability objects) ----------------------------------
class FakeSource:
    def __init__(self):
        self.calls = []
        self.opened = False
    def open(self, conn): self.opened = True; self.calls.append(("open", conn.transport))
    def close(self): self.calls.append(("close",))
    def identify(self): return "FAKE-PS"
    def set_output(self, on): self.calls.append(("set_output", on))
    def set_voltage(self, v): self.calls.append(("set_voltage", v))
    def measure_voltage(self): self.calls.append(("measure_voltage",)); return 28.0
    def measure_current(self): self.calls.append(("measure_current",)); return 0.2


class FakeLoad:
    def __init__(self):
        self.calls = []
    def open(self, conn): self.calls.append(("open",))
    def close(self): self.calls.append(("close",))
    def identify(self): return "FAKE-LOAD"
    def set_mode(self, m): self.calls.append(("set_mode", m))
    def set_power(self, w): self.calls.append(("set_power", w))
    def set_input(self, on): self.calls.append(("set_input", on))
    def measure_voltage(self): self.calls.append(("measure_voltage",)); return 28.0
    def measure_current(self): self.calls.append(("measure_current",)); return 7.1


class FakeDmm:
    def __init__(self, *, fail_identify=False):
        self.calls = []
        self._fail = fail_identify
    def open(self, conn): self.calls.append(("open",))
    def close(self): self.calls.append(("close",))
    def identify(self):
        if self._fail:
            raise ConnectionLostError("DAQ down")
        return "FAKE-DAQ"
    def read(self, channel): self.calls.append(("read", channel)); return 28.0
    def set_line(self, line, state): self.calls.append(("set_line", line, state))
    def get_line(self, line): return False


def _bench(source=None, load=None, dmm=None, daq_relay_channel=105):
    source = source or FakeSource()
    load = load or FakeLoad()
    dmm = dmm or FakeDmm()
    sim = ConnInfo("sim", "MOCK")
    return BenchDriver(
        source=source, load=load, dmm=dmm,
        source_conn=sim, load_conn=sim, dmm_conn=sim,
        daq_relay_channel=daq_relay_channel,
    )


class RoutingTests(unittest.TestCase):
    def test_measurement_commands(self):
        self.assertEqual(_bench().measurement_commands, frozenset({"readchannel"}))

    def test_connect_opens_all_and_energizes(self):
        s, l, d = FakeSource(), FakeLoad(), FakeDmm()
        bench = _bench(s, l, d)
        self.assertTrue(bench.connect())
        self.assertTrue(s.opened)
        self.assertIn(("set_output", True), s.calls)
        self.assertIn(("open",), l.calls)
        self.assertIn(("open",), d.calls)

    def test_setvoltage_routes_to_source(self):
        s = FakeSource()
        _bench(source=s).execute_command("setvoltage", ["28.0"])
        self.assertIn(("set_voltage", 28.0), s.calls)

    def test_setload_on_sequence(self):
        l = FakeLoad()
        _bench(load=l).execute_command("setload", ["200"])
        self.assertEqual(l.calls, [("set_mode", "CP"), ("set_power", 200.0), ("set_input", True)])

    def test_setload_zero_turns_off(self):
        l = FakeLoad()
        _bench(load=l).execute_command("setload", ["0"])
        self.assertEqual(l.calls, [("set_input", False), ("set_power", 0.0)])

    def test_setlogic_uses_configured_relay_channel(self):
        d = FakeDmm()
        bench = _bench(dmm=d, daq_relay_channel=105)
        bench.execute_command("setlogic", ["on"])
        bench.execute_command("setlogic", ["off"])
        self.assertEqual(d.calls, [("set_line", 105, True), ("set_line", 105, False)])

    def test_relay_routes_to_dio(self):
        d = FakeDmm()
        _bench(dmm=d).execute_command("relay", ["110", "on"])
        self.assertEqual(d.calls, [("set_line", 110, True)])

    def test_readchannel_source_v_and_a(self):
        s = FakeSource()
        bench = _bench(source=s)
        bench.set_active_step("V", 27.6, 28.4)
        self.assertEqual(bench.execute_command("readchannel", ["1"]), 28.0)
        bench.set_active_step("A", 0.0, 0.5)
        self.assertEqual(bench.execute_command("readchannel", ["1"]), 0.2)
        self.assertEqual(s.calls, [("measure_voltage",), ("measure_current",)])

    def test_readchannel_load_v_and_a(self):
        l = FakeLoad()
        bench = _bench(load=l)
        bench.set_active_step("V", 27.6, 28.4)
        bench.execute_command("readchannel", ["5"])
        bench.set_active_step("A", 6.5, 7.8)
        bench.execute_command("readchannel", ["5"])
        self.assertEqual(l.calls, [("measure_voltage",), ("measure_current",)])

    def test_readchannel_dmm_forwards_channel(self):
        d = FakeDmm()
        bench = _bench(dmm=d)
        bench.set_active_step("V", 27.6, 28.4)
        bench.execute_command("readchannel", ["3"])
        self.assertEqual(d.calls, [("read", 3)])

    def test_readchannel_unmapped_raises(self):
        bench = _bench()
        bench.set_active_step("V", 0, 1)
        with self.assertRaises(UnknownCommandError):
            bench.execute_command("readchannel", ["9"])

    def test_getid_aggregates_identities(self):
        ids = _bench().identify()
        self.assertEqual(set(ids.values()), {"FAKE-PS", "FAKE-LOAD", "FAKE-DAQ"})

    def test_getid_propagates_failure(self):
        bench = _bench(dmm=FakeDmm(fail_identify=True))
        with self.assertRaises(ConnectionLostError):
            bench.execute_command("getid", [])

    def test_unknown_command_raises(self):
        with self.assertRaises(UnknownCommandError):
            _bench().execute_command("frobnicate", [])

    def test_disconnect_closes_all(self):
        s, l, d = FakeSource(), FakeLoad(), FakeDmm()
        bench = _bench(s, l, d)
        bench.disconnect()
        self.assertIn(("close",), s.calls)
        self.assertIn(("close",), l.calls)
        self.assertIn(("close",), d.calls)


def _evaluate_step(step, driver, *, answer_yes=True):
    """Mirror TestRunnerThread._run_step for one step (offline, Qt-free)."""
    driver.set_active_step(step.unit, step.min_val, step.max_val)
    last = None
    has_yesno = False
    for cmd in step.commands:
        name = str(cmd["cmd"]).lower()
        args = cmd["args"]
        if name == "promptyesno":
            has_yesno = True
            last = 1.0 if answer_yes else 0.0
            continue
        if name in ("delay", "log", "prompt"):
            continue
        value = driver.execute_command(name, args)
        if name in driver.measurement_commands:
            last = value
    if step.has_limits:
        if last is None:
            return False, None
        return step.min_val <= last <= step.max_val, last
    if has_yesno and last is not None:
        return last > 0.5, last
    return True, last


class SimBenchTests(unittest.TestCase):
    def test_full_spreos_passes_in_sim(self):
        self.assertTrue(SPREOS.is_file(), f"missing script: {SPREOS}")
        driver = build_sim_bench(fail_prob=0.0, seed=1)  # deterministic, no injected fails
        steps = ScriptManager().load_script(SPREOS)
        driver.connect()
        try:
            for step in steps:
                passed, value = _evaluate_step(step, driver, answer_yes=True)
                self.assertTrue(passed, f"step failed in sim: {step.name} (value={value})")
        finally:
            driver.disconnect()

    def test_getid_step_succeeds_after_connect(self):
        driver = build_sim_bench(fail_prob=0.0, seed=2)
        driver.connect()
        try:
            ids = driver.identify()
            self.assertEqual(len(ids), 3)
            self.assertTrue(all(ids.values()))
        finally:
            driver.disconnect()


class CrossInstrumentTests(unittest.TestCase):
    """A rapid sequence mixing instruments stays ordered, with one persistent
    session per instrument (no per-command reconnect, no interleaving)."""

    def test_mixed_sequence_keeps_sessions_open_and_ordered(self):
        log: list = []

        class Rec:
            def __init__(self, name):
                self.name = name
                self.opens = 0
                self.closes = 0
            def open(self, conn): self.opens += 1
            def close(self): self.closes += 1
            def identify(self): return self.name
            def set_output(self, on): log.append((self.name, "set_output"))
            def set_voltage(self, v): log.append((self.name, "set_voltage", v))
            def measure_voltage(self): log.append((self.name, "measure_voltage")); return 28.0
            def measure_current(self): log.append((self.name, "measure_current")); return 1.0
            def set_mode(self, m): log.append((self.name, "set_mode", m))
            def set_power(self, w): log.append((self.name, "set_power", w))
            def set_input(self, on): log.append((self.name, "set_input", on))
            def read(self, ch): log.append((self.name, "read", ch)); return 28.0
            def set_line(self, line, state): log.append((self.name, "set_line"))

        src, load, dmm = Rec("PS"), Rec("LOAD"), Rec("DAQ")
        sim = ConnInfo("sim", "MOCK")
        bench = BenchDriver(
            source=src, load=load, dmm=dmm,
            source_conn=sim, load_conn=sim, dmm_conn=sim,
            daq_relay_channel=101,
            channel_map={1: "source", 2: "dmm", 5: "load"},
        )

        bench.connect()
        self.assertEqual((src.opens, load.opens, dmm.opens), (1, 1, 1))
        log.clear()  # drop the connect-time set_output

        # Rapid mix across all three targets in one sequence.
        bench.set_active_step("V", 0, 99); bench.execute_command("setvoltage", ["28.0"])
        bench.execute_command("readchannel", ["1"])              # PS volts
        bench.execute_command("setload", ["10"])                 # LOAD: CP/power/input
        bench.set_active_step("V", 0, 99); bench.execute_command("readchannel", ["2"])  # DAQ
        bench.execute_command("setvoltage", ["16.0"])            # PS
        bench.set_active_step("A", 0, 99); bench.execute_command("readchannel", ["5"])  # LOAD amps

        # No reconnects mid-sequence; sessions still open exactly once each.
        self.assertEqual((src.closes, load.closes, dmm.closes), (0, 0, 0))
        self.assertEqual((src.opens, load.opens, dmm.opens), (1, 1, 1))

        # Commands hit the right instrument, in the exact order issued.
        self.assertEqual(
            [entry[0] for entry in log],
            ["PS", "PS", "LOAD", "LOAD", "LOAD", "DAQ", "PS", "LOAD"],
        )

        bench.disconnect()
        self.assertEqual((src.closes, load.closes, dmm.closes), (1, 1, 1))


if __name__ == "__main__":
    unittest.main()
