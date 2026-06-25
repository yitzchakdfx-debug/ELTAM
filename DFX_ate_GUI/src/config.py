"""System feature flags and configuration, sourced from the environment (.env).

`.env` is the single source of truth (see DOC/.env.example). Non-secret values
fall back to safe defaults; password values must be supplied by the environment.
"""
from __future__ import annotations

from env import get_bool, get_list, get_required_str, get_str

# --- Feature flags ---
SHOW_LIVE_MONITOR: bool = get_bool("SHOW_LIVE_MONITOR", True)
SHOW_SEARCH_BAR: bool = get_bool("SHOW_SEARCH_BAR", False)
SHOW_NIGHT_MODE: bool = get_bool("SHOW_NIGHT_MODE", False)

# --- Pre-test dialog UUT options ---
UUT_TYPES: list[str] = get_list("UUT_TYPES", ["Power main", "Power Ctrl DSP", "Demo UUT"])

# --- Global instrument list (Admin → Connections dialog) ---
INSTRUMENTS: list[str] = get_list(
    "INSTRUMENTS",
    ["Power Supply", "Main Board", "Agilent 34980A", "QEI Arduino", "Outputs Arduino", "I2C Arduino"],
)

# --- Secrets (required in .env) ---
LOG_ENCRYPTION_PASSWORD: str = get_required_str("LOG_ENCRYPTION_PASSWORD")
ADMIN_REPORT_PASSWORD: str = get_required_str("ADMIN_REPORT_PASSWORD")

# --- Default admin seed (used only on first DB init) ---
DEFAULT_ADMIN_USERNAME: str = get_str("DEFAULT_ADMIN_USERNAME", "lior")
DEFAULT_ADMIN_PASSWORD: str = get_required_str("DEFAULT_ADMIN_PASSWORD")
DEFAULT_ADMIN_EMPLOYEE_ID: str = get_str("DEFAULT_ADMIN_EMPLOYEE_ID", "0000")

# --- Station / report identity ---
TESTER_SERIAL_NUMBER: str = get_str("TESTER_SERIAL_NUMBER", "ATE-DFX-001")
