"""Offline tests for the bench factory: connection parsing, hardware build,
DAQ logical->physical remap, and the preflight config-error path. No hardware."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from drivers.bench import bench_spec, factory
from drivers.bench.bench_driver import BenchDriver


class ParseSerialTests(unittest.TestCase):
    def test_full(self):
        ci = factory.parse_serial("COM3|115200|N|1")
        self.assertEqual(ci.transport, "serial")
        self.assertEqual(ci.resource, "COM3")
        self.assertEqual(ci.params, {"baud": 115200, "parity": "N", "stopbits": "1"})

    def test_port_only_uses_defaults(self):
        ci = factory.parse_serial("COM7")
        self.assertEqual(ci.resource, "COM7")
        self.assertEqual(ci.params, {})  # driver applies its own defaults

    def test_empty(self):
        self.assertEqual(factory.parse_serial("").resource, "")


class ParseVisaTests(unittest.TestCase):
    def test_resource_passthrough(self):
        ci = factory.parse_visa("TCPIP0::192.168.0.50::INSTR")
        self.assertEqual(ci.transport, "visa")
        self.assertEqual(ci.resource, "TCPIP0::192.168.0.50::INSTR")
        self.assertEqual(ci.params, {})


class ParsePrologixTests(unittest.TestCase):
    def test_port_and_gpib(self):
        ci = factory.parse_prologix("COM5|115200|N|1|GPIB:6")
        self.assertEqual(ci.transport, "prologix")
        self.assertEqual(ci.resource, "COM5")
        self.assertEqual(ci.params["gpib_address"], 6)
        self.assertEqual(ci.params["baud"], 115200)
        self.assertEqual(ci.params["parity"], "N")
        self.assertEqual(ci.params["stopbits"], "1")

    def test_gpib_variants(self):
        self.assertEqual(factory.parse_prologix("COM5|GPIB=6").params["gpib_address"], 6)
        self.assertEqual(factory.parse_prologix("COM5|gpib 12").params["gpib_address"], 12)

    def test_missing_gpib_is_none(self):
        self.assertIsNone(factory.parse_prologix("COM5").params["gpib_address"])


class ParseDaqMapTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(factory.parse_daq_channel_map("3=103, 4=104"), {3: 103, 4: 104})

    def test_skips_malformed(self):
        self.assertEqual(factory.parse_daq_channel_map("3=103, junk, 5=oops, 4=104"),
                         {3: 103, 4: 104})

    def test_empty(self):
        self.assertEqual(factory.parse_daq_channel_map(""), {})


class HardwareBuildTests(unittest.TestCase):
    def _good_connections(self):
        # All three bench instruments are VISA now (GPP-3610H PS, DAQ-9600, PEL-3031AE).
        return {
            bench_spec.POWER_SUPPLY: "USB0::0x2A8D::0x0000::SIM::INSTR",
            bench_spec.DAQ: "TCPIP0::192.168.0.50::INSTR",
            bench_spec.ELECTRONIC_LOAD: "ASRL5::INSTR",
        }

    def test_build_hardware_bench_with_valid_config(self):
        bench = factory.build_bench(
            hardware_mode=True,
            connections=self._good_connections(),
            bench_cfg={"daq_relay_channel": "101", "daq_channel_map": "3=103,4=104"},
        )
        self.assertIsInstance(bench, BenchDriver)

    def test_missing_config_raises_with_all_messages(self):
        with self.assertRaises(factory.BenchConfigError) as ctx:
            factory.build_bench(hardware_mode=True, connections={}, bench_cfg={})
        msgs = ctx.exception.messages
        # one per missing VISA resource: PS, DAQ, load
        self.assertGreaterEqual(len(msgs), 3)

    def test_preflight_reports_config_error(self):
        ok, report = factory.preflight(connections={}, bench_cfg={})
        self.assertFalse(ok)
        self.assertTrue(any("Configuration error" in line for line in report))


class DaqRemapTests(unittest.TestCase):
    """BenchDriver forwards the remapped physical DAQ channel to the DMM."""

    def test_logical_to_physical(self):
        from drivers.bench.instrument_base import ConnInfo

        reads: list[int] = []

        class FakeDmm:
            def open(self, conn): pass
            def close(self): pass
            def identify(self): return "DAQ"
            def read(self, channel): reads.append(channel); return 28.0
            def set_line(self, line, state): pass

        class Stub:
            def open(self, conn): pass
            def close(self): pass
            def identify(self): return "x"
            def set_output(self, on): pass
            def set_voltage(self, v): pass
            def measure_voltage(self): return 0.0
            def measure_current(self): return 0.0
            def set_mode(self, m): pass
            def set_power(self, w): pass
            def set_input(self, on): pass

        sim = ConnInfo("sim", "MOCK")
        bench = BenchDriver(
            source=Stub(), load=Stub(), dmm=FakeDmm(),
            source_conn=sim, load_conn=sim, dmm_conn=sim,
            daq_channel_map={3: 103, 4: 104},
        )
        bench.set_active_step("V", 27.6, 28.4)
        bench.execute_command("readchannel", ["3"])  # logical 3 -> physical 103
        bench.execute_command("readchannel", ["4"])  # logical 4 -> physical 104
        self.assertEqual(reads, [103, 104])


if __name__ == "__main__":
    unittest.main()
