"""Table creation and live migrations — run once per process via DatabaseManager."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import datetime

from logic.db.connection import open_conn


def create_tables(db_path, default_admin_username: str,
                  default_admin_password: str, default_admin_employee_id: str,
                  pbkdf2_iterations: int) -> None:
    from pathlib import Path
    path = Path(db_path)
    with open_conn(path) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS test_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operator TEXT,
            part_number TEXT,
            serial_number TEXT,
            overall_passed INTEGER,
            start_time TEXT,
            end_time TEXT
        );"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS test_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            test_name TEXT,
            value REAL,
            min_val REAL,
            max_val REAL,
            unit TEXT,
            passed INTEGER,
            FOREIGN KEY(run_id) REFERENCES test_runs(id)
        );"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL COLLATE NOCASE,
            password_hash BLOB NOT NULL,
            salt BLOB NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('Operator','Technician','Admin')),
            employee_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS test_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_name TEXT NOT NULL,
            uut_type TEXT NOT NULL,
            version_name TEXT NOT NULL,
            test_content TEXT NOT NULL,
            connection_params TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL,
            UNIQUE(test_name, version_name)
        );"""
        )
        existing_cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(test_versions);").fetchall()
        }
        if "connection_params" not in existing_cols:
            conn.execute(
                "ALTER TABLE test_versions "
                "ADD COLUMN connection_params TEXT NOT NULL DEFAULT '';"
            )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            username TEXT NOT NULL DEFAULT '',
            employee_id TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT ''
        );"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS instrument_connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            instrument_name TEXT UNIQUE NOT NULL COLLATE NOCASE,
            connection_string TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            updated_by TEXT NOT NULL DEFAULT ''
        );"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS bench_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        );"""
        )
        _seed_admin(conn, default_admin_username, default_admin_password,
                    default_admin_employee_id, pbkdf2_iterations)
        conn.commit()


def _seed_admin(conn: sqlite3.Connection, username: str, password: str,
                employee_id: str, iterations: int) -> None:
    now = datetime.now().isoformat()
    salt = secrets.token_bytes(16)
    pw_hash = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    conn.execute(
        """
        INSERT OR IGNORE INTO users
        (username, password_hash, salt, role, employee_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """,
        (username, pw_hash, salt, "Admin", employee_id, now, now),
    )
