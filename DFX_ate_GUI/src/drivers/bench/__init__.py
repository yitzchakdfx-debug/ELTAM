"""Bench layer: the composite driver, instrument capability contract, and factory.

The runner talks to a single bench-level `BaseDriver`. `BenchDriver` (later
phases) composes per-instrument drivers and routes script commands to them via
the capability Protocols in `instrument_base`. `factory.build_bench(...)` is the
single construction seam the UI/runner uses to pick Simulation vs Hardware.
"""
