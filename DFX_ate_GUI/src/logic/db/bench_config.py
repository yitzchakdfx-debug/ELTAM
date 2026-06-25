"""Global bench-wiring settings — a tiny key/value store.

Holds station-wide facts that are NOT per-instrument connection resources (those
live in `instrument_connections`) and NOT per-test (those live in
`test_versions.connection_params` / the per-version channel map). Currently:

    daq_relay_channel  DAQ-9600 switch channel the `setlogic` relay is wired to
    load_slot          3300F mainframe slot (1-4) holding the load module

Values are stored as TEXT; callers cast (e.g. ``int(...)``) at read time.
"""

from __future__ import annotations

from pathlib import Path

from logic.db.connection import open_conn

# Known keys — callers should use these constants, not raw strings.
DAQ_RELAY_CHANNEL = "daq_relay_channel"
LOAD_SLOT = "load_slot"
DAQ_CHANNEL_MAP = "daq_channel_map"   # logical->physical, e.g. "3=103,4=104"


def get_bench_config(db_path: Path) -> dict[str, str]:
    """Return all stored bench-config key/value pairs."""
    with open_conn(db_path) as conn:
        rows = conn.execute("SELECT key, value FROM bench_config;").fetchall()
    return {str(r["key"]): str(r["value"]) for r in rows}


def set_bench_config(db_path: Path, key: str, value: str) -> None:
    """Insert or update one bench-config value."""
    with open_conn(db_path) as conn:
        conn.execute(
            """
            INSERT INTO bench_config (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value;
            """,
            (key.strip(), value.strip()),
        )
        conn.commit()
