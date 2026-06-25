"""Admin: configure global instrument connection strings (COM ports / VISA resources)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from config import INSTRUMENTS
from drivers.bench.bench_spec import BENCH_INSTRUMENT_NAMES
from logic.database_manager import DatabaseManager
from logic.db.bench_config import DAQ_CHANNEL_MAP, DAQ_RELAY_CHANNEL
from ui.preflight_worker import PreflightWorker


class ConnectionsDialog(QDialog):
    def __init__(self, username: str, employee_id: str, parent=None) -> None:
        super().__init__(parent)
        self._db = DatabaseManager()
        self._username = username
        self._employee_id = employee_id

        # Show the configured instrument list plus the SPREOS bench instruments
        # (deduped, order preserved) so their addresses are always editable.
        names = list(dict.fromkeys(list(INSTRUMENTS) + list(BENCH_INSTRUMENT_NAMES)))

        self.setWindowTitle("Connections")
        self.resize(560, 120 + len(names) * 36)

        root = QVBoxLayout(self)
        root.addWidget(
            QLabel(
                "Per-instrument address. Examples:\n"
                "  • VISA (PS / Load / DAQ):  TCPIP0::192.168.0.50::INSTR\n"
                "      USB0::0x2A8D::…::INSTR   or   ASRL3::INSTR (USB-CDC COM3)\n"
                "  • Serial (e.g. Arduinos):  COM3|115200|N|1"
            )
        )

        form = QFormLayout()
        form.setContentsMargins(0, 8, 0, 8)
        form.setVerticalSpacing(6)
        form.setHorizontalSpacing(12)

        stored = self._db.list_instrument_connections()
        self._fields: dict[str, QLineEdit] = {}
        for name in names:
            edit = QLineEdit()
            edit.setObjectName(f"conn_field_{name.replace(' ', '_')}")
            edit.setPlaceholderText("COM9  or  USB0::…::INSTR  or  COM5|115200|N|1|GPIB:6")
            edit.setText(stored.get(name, ""))
            form.addRow(name, edit)
            self._fields[name] = edit

        root.addLayout(form)

        # --- Global bench wiring (station-wide; not per-instrument resources) ---
        bench = self._db.get_bench_config()
        bench_group = QGroupBox("Bench wiring (global)")
        bench_group.setObjectName("bench_wiring_group")
        bench_form = QFormLayout(bench_group)
        bench_form.setContentsMargins(8, 8, 8, 8)
        bench_form.setVerticalSpacing(6)
        bench_form.setHorizontalSpacing(12)

        self._daq_relay_field = QLineEdit()
        self._daq_relay_field.setObjectName("bench_field_daq_relay_channel")
        self._daq_relay_field.setPlaceholderText("DAQ-9600 switch channel for setlogic, e.g. 101")
        self._daq_relay_field.setText(bench.get(DAQ_RELAY_CHANNEL, ""))
        bench_form.addRow("DAQ relay channel:", self._daq_relay_field)

        self._daq_map_field = QLineEdit()
        self._daq_map_field.setObjectName("bench_field_daq_channel_map")
        self._daq_map_field.setPlaceholderText("logical=physical, e.g. 3=103,4=104")
        self._daq_map_field.setText(bench.get(DAQ_CHANNEL_MAP, ""))
        bench_form.addRow("DAQ channel map:", self._daq_map_field)

        root.addWidget(bench_group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        self._btn_test = buttons.addButton(
            "Test Connection", QDialogButtonBox.ButtonRole.ActionRole
        )
        self._btn_test.setObjectName("btn_test_connection")
        self._btn_test.setToolTip(
            "Open each instrument and read its ID using the values entered above "
            "(runs in the background; does not save)."
        )
        self._btn_test.clicked.connect(self._test_connection)
        self._preflight_thread: PreflightWorker | None = None
        root.addWidget(buttons)

    def _current_values(self) -> tuple[dict[str, str], dict[str, str]]:
        """Connections + bench_config dicts from the *current* field contents."""
        connections = {name: edit.text().strip() for name, edit in self._fields.items()}
        bench_cfg = {
            DAQ_RELAY_CHANNEL: self._daq_relay_field.text().strip(),
            DAQ_CHANNEL_MAP: self._daq_map_field.text().strip(),
        }
        return connections, bench_cfg

    def _test_connection(self) -> None:
        connections, bench_cfg = self._current_values()
        self._btn_test.setEnabled(False)
        self._btn_test.setText("Testing...")
        self._preflight_thread = PreflightWorker(connections, bench_cfg, parent=self)
        self._preflight_thread.completed.connect(self._on_test_completed)
        self._preflight_thread.finished.connect(self._preflight_thread.deleteLater)
        self._preflight_thread.start()

    def _on_test_completed(self, ok: bool, report: list) -> None:
        self._btn_test.setEnabled(True)
        self._btn_test.setText("Test Connection")
        body = "\n".join(report) if report else "(no instruments checked)"
        if ok:
            QMessageBox.information(
                self, "Test Connection", "All instruments responded:\n\n" + body
            )
        else:
            QMessageBox.warning(
                self, "Test Connection", "Some instruments are not available:\n\n" + body
            )

    def _save(self) -> None:
        changed: list[str] = []
        stored = self._db.list_instrument_connections()
        for name, edit in self._fields.items():
            value = edit.text().strip()
            if value != stored.get(name, ""):
                changed.append(name)
            self._db.upsert_instrument_connection(name, value, self._username)

        # Global bench wiring
        bench_before = self._db.get_bench_config()
        daq_val = self._daq_relay_field.text().strip()
        map_val = self._daq_map_field.text().strip()
        if daq_val != bench_before.get(DAQ_RELAY_CHANNEL, ""):
            changed.append(DAQ_RELAY_CHANNEL)
        if map_val != bench_before.get(DAQ_CHANNEL_MAP, ""):
            changed.append(DAQ_CHANNEL_MAP)
        self._db.set_bench_config(DAQ_RELAY_CHANNEL, daq_val)
        self._db.set_bench_config(DAQ_CHANNEL_MAP, map_val)

        if changed:
            try:
                self._db.log_audit_action(
                    "Updated instrument connections",
                    username=self._username,
                    employee_id=self._employee_id,
                    details=f"changed={changed!r}",
                )
            except Exception:
                pass

        QMessageBox.information(self, "Connections", "Instrument connections saved.")
        self.accept()
