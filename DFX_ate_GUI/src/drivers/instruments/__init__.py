"""Per-device drivers, one folder per instrument.

Each instrument folder ships a real `driver.py`, a `mock.py`, a `protocol.py`
(SCPI/framing), and a `README.md`. Concrete drivers subclass
`drivers.bench.instrument_base.InstrumentDriver` and structurally implement the
capability Protocol(s) they support; the `BenchDriver` router dispatches via
`runtime_checkable` isinstance, so no explicit Protocol subclassing is needed.
"""
