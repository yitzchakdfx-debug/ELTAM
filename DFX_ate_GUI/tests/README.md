# tests/

Offline unit tests for the instrument-driver layer. **No hardware, no VISA/serial
backend required** — they exercise the SCPI/command string builders, the mock
drivers, and the real drivers' guard logic (not their I/O).

## Run

Zero extra dependencies (stdlib `unittest`):

```
python -m unittest discover -s tests -v
```

Or, if you have it installed, `pytest`:

```
pytest tests/
```

Each test file prepends `src/` to `sys.path`, so no install/PYTHONPATH is needed.

## What's covered

- `test_transports_visa.py` / `test_transports_serial.py` — transport availability
  gates return a bool without raising; not-open calls raise `ConnectionLostError`;
  `close()` is idempotent.
- `test_daq_9600.py` — DAQ-9600 SCPI builders (exact strings), the mock's
  Multimeter/DiscreteIO behavior, and the real driver's guards + `_parse_float`.
- `test_idrc.py` — IDRC PS command builders (**provisional** — see the driver's
  `protocol.py`), the mock's VoltageSource behavior, and the real driver's guards.
