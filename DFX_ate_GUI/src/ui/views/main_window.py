"""Main ATE window: layout, styling, and wiring to the script-driven runner."""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QBrush, QColor, QDesktopServices, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from config import SHOW_LIVE_MONITOR, SHOW_NIGHT_MODE, SHOW_SEARCH_BAR
from drivers.base_driver import BaseDriver
from drivers.bench.factory import build_bench
from logic.database_manager import DatabaseManager
from ui.preflight_worker import PreflightWorker
from ui.report_worker import ReportWorker
from logic.models import TestResultPayload
from logic.monitor_engine import MonitorThread
from logic.report_generator import ReportGenerator, sanitize_path_segment
from logic.script_manager import ScriptManager, ScriptParseError
from logic.secure_logger import get_secure_logger
from logic.test_engine import TestRunnerThread
from paths import resource_path, user_data_path
from ui.views.audit_viewer_dialog import AuditViewerDialog
from ui.views.connections_dialog import ConnectionsDialog
from ui.views.limits_editor_dialog import LimitsEditorDialog
from ui.views.pre_test_dialog import PreTestDialog
from ui.views.select_test_dialog import SelectTestDialog

from ui.views.test_result_dialog import TestResultDialog
from ui.views.user_management_dialog import UserManagementDialog
from ui.views.version_manager_dialog import VersionManagerDialog
from ui.widgets.control_panel import ControlPanelWidget
from ui.widgets.instrument_panel import InstrumentPanelWidget
from ui.widgets.result_row_delegate import ResultRowDelegate
from version import __version__


_DEFAULT_SCRIPT_NAME = "sequence.tst"
_NA = "-"


def _format_measurement(value: float) -> str:
    """Human-readable numeric string without excessive trailing zeros."""
    return f"{value:g}"


class MainWindow(QMainWindow):
    _ICONS_DIR = resource_path("ui", "assets", "icons")
    _RESULTS_DIR = user_data_path("results")

    sequence_finished = Signal(bool)

    def __init__(self, user_info: dict) -> None:
        super().__init__()
        self._user_info = user_info
        self.setWindowTitle("DFX Tester - Component ATE")
        icon_path = self._ICONS_DIR / "DFXAppIcon.png"
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(1200, 800)
        self._setup_menu_bar()
        self.test_thread: TestRunnerThread | None = None
        self.is_dark_mode: bool = False
        self._script_manager = ScriptManager()
        self._active_script_path: Path = (
            self._script_manager.scripts_dir / _DEFAULT_SCRIPT_NAME
        )
        self._trace_history: list[dict] = []
        self._part_number_user_edited = False
        self._catalog_test_name: str = Path(_DEFAULT_SCRIPT_NAME).stem
        self._catalog_uut_type: str = ""
        self._operator_temp_script: Path | None = None
        self._pre_test_locked: bool = False
        try:
            self._secure = get_secure_logger()
        except Exception:
            self._secure = None
        self._last_run_meta: dict | None = None
        self._last_run_rows: list[dict] = []
        self._report_worker: ReportWorker | None = None
        self._setup_ui()
        if SHOW_LIVE_MONITOR:
            self.monitor_thread = MonitorThread(parent=self)
            self.monitor_thread.values_updated.connect(self.instrument_panel.update_values)
            self.monitor_thread.start()
        self._apply_theme_file()
        self._update_icons(self.is_dark_mode)
        self._apply_role_permissions()
        if self._is_operator():
            self._active_script_path = Path()
            self.label_active_script.setText("No test — use Select Product.")
            self.test_list.clear()
            self._catalog_test_name = ""
            self._catalog_uut_type = ""
        else:
            self._reload_script_into_list()
        self._fit_initial_size_to_screen()
        QTimer.singleShot(0, self.load_script)

    def _make_ribbon_button(self, object_name: str, text: str) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName(object_name)
        btn.setText(text)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        btn.setFixedSize(80, 70)
        btn.setIconSize(QSize(28, 28))
        btn.setAutoRaise(True)
        return btn

    def _icon(self, name: str, fallback: QStyle.StandardPixmap) -> QIcon:
        for ext in (".svg", ".png"):
            candidate = self._ICONS_DIR / f"{name}{ext}"
            if candidate.is_file():
                return QIcon(str(candidate))
        return self.style().standardIcon(fallback)

    def _update_icons(self, is_dark: bool) -> None:
        """Load theme-aware and ribbon icons; falls back to standard icons if assets missing."""
        SP = QStyle.StandardPixmap
        if SHOW_NIGHT_MODE:
            theme_name = "sun" if is_dark else "moon"
            theme_fallback = SP.SP_DialogYesButton if is_dark else SP.SP_DialogNoButton
            self.btn_toggle_theme.setIcon(self._icon(theme_name, theme_fallback))
        self.btn_load_script.setIcon(self._icon("folder", SP.SP_DirOpenIcon))
        self.btn_limits.setIcon(self._icon("list", SP.SP_FileDialogListView))
        self.btn_versions.setIcon(self._icon("list", SP.SP_FileDialogDetailedView))
        self.btn_audit.setIcon(self._icon("list", SP.SP_FileDialogListView))
        self.btn_logout.setIcon(self._icon("logout", SP.SP_ArrowBack))
        self.btn_exit.setIcon(self._icon("power", SP.SP_DialogCloseButton))

    def show_about_dialog(self) -> None:
        QMessageBox.about(
            self,
            "About DFX Tester",
            "<b>DFX Tester - Component ATE</b><br>"
            f"Version {__version__}<br><br>"
            "In development.",
        )

    def _setup_menu_bar(self) -> None:
        menu = self.menuBar()

        file_menu = menu.addMenu("&File")
        file_menu.addAction("&Select Product...", self.load_script)
        file_menu.addSeparator()
        file_menu.addAction("E&xit", self.close)

        test_menu = menu.addMenu("&Test")
        test_menu.addAction("&Run", self._on_start_clicked)
        test_menu.addAction("&Stop", self.stop_tests)
        test_menu.addSeparator()
        test_menu.addAction("Re&set Counters", self.reset_counters)

        results_menu = menu.addMenu("&Results")
        results_menu.addAction("Open Results &Folder", self.open_results_folder)
        results_menu.addSeparator()
        results_menu.addAction("Export to &CSV...", self.export_results_csv)
        results_menu.addAction("Export to &PDF...", self.export_results_pdf)

        if self._is_admin():
            users_menu = menu.addMenu("&Users")
            users_menu.addAction("&Logs...", self.open_audit_viewer)
            users_menu.addAction("&User Management...", self.open_user_management)

            conn_menu = menu.addMenu("C&onnections")
            conn_menu.addAction("&Instrument Setup...", self.open_connections_dialog)

        help_menu = menu.addMenu("&Help")
        help_menu.addAction("&About", self.show_about_dialog)

    def _current_role(self) -> str:
        return str(self._user_info.get("role", "")).strip().title()

    def _is_operator(self) -> bool:
        return self._current_role() == "Operator"

    def _is_admin(self) -> bool:
        return self._current_role() == "Admin"

    def _is_technician(self) -> bool:
        return self._current_role() == "Technician"

    def _apply_role_permissions(self) -> None:
        hide_detail_cols = self._is_operator() or self._is_technician()
        if hide_detail_cols:
            self.results_table.setColumnHidden(1, True)
            self.results_table.setColumnHidden(2, True)
            self.results_table.setColumnHidden(3, True)
        else:
            self.results_table.setColumnHidden(1, False)
            self.results_table.setColumnHidden(2, False)
            self.results_table.setColumnHidden(3, False)

        self.btn_versions.setVisible(self._is_admin())
        self.btn_audit.setVisible(self._is_admin())
        self.btn_limits.setVisible(self._is_admin())

        self.btn_load_script.setText("Product")

        if self._is_operator() or self._is_technician():
            self.trace_container.hide()
        else:
            self.trace_container.show()

        self.control_panel.chk_save_log.setVisible(self._is_admin())

        list_actions_visible = not self._is_operator()
        self.btn_select_all_tests.setVisible(list_actions_visible)
        self.btn_clear_all_tests.setVisible(list_actions_visible)

    def open_version_manager(self) -> None:
        if not self._is_admin():
            return
        VersionManagerDialog(
            current_username=str(self._user_info.get("username", "")),
            script_manager=self._script_manager,
            employee_id=str(self._user_info.get("employee_id", "")),
            parent=self,
        ).exec()

    def open_audit_viewer(self) -> None:
        if not self._is_admin():
            QMessageBox.warning(self, "Not allowed", "Only Admin users can open the audit log.")
            return
        AuditViewerDialog(parent=self).exec()

    def open_user_management(self) -> None:
        if not self._is_admin():
            QMessageBox.warning(self, "Not allowed", "Only Admin users can manage users.")
            return
        dialog = UserManagementDialog(
            current_username=str(self._user_info.get("username", "")),
            parent=self,
        )
        dialog.exec()

    def open_connections_dialog(self) -> None:
        if not self._is_admin():
            return
        ConnectionsDialog(
            username=str(self._user_info.get("username", "")),
            employee_id=str(self._user_info.get("employee_id", "")),
            parent=self,
        ).exec()

    def open_limits_editor(self) -> None:
        if not self._is_admin():
            return
        if not self._active_script_path.is_file():
            QMessageBox.information(self, "Limits", "Load a test first.")
            return
        try:
            document = self._script_manager.load_document(self._active_script_path)
        except ScriptParseError as exc:
            QMessageBox.warning(
                self,
                "Script parse error",
                f"Could not parse {self._active_script_path.name}:\n"
                f"line {exc.line_no}: {exc.msg}",
            )
            return
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Limits", f"Could not load script:\n{exc}")
            return

        dialog = LimitsEditorDialog(
            document=document,
            script_manager=self._script_manager,
            catalog_test_name=self._catalog_test_name or self._active_script_path.stem,
            catalog_uut_type=self._catalog_uut_type,
            catalog_version=getattr(self, "_catalog_version", ""),
            username=str(self._user_info.get("username", "")),
            employee_id=str(self._user_info.get("employee_id", "")),
            db=DatabaseManager(),
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Rejected:
            return
        if dialog.is_apply_mode():
            tmp = dialog.temp_path()
            if tmp and tmp.is_file():
                self._cleanup_operator_temp()
                self._active_script_path = tmp
                self._reload_script_into_list()
        else:
            self._reload_script_into_list()

    def reset_counters(self) -> None:
        self.control_panel.label_pass.setText("PASS: 0")
        self.control_panel.label_fail.setText("FAIL: 0")
        self.control_panel.progress_total.setValue(0)
        self.control_panel.progress_test.setValue(0)
        self.control_panel.edit_current_test.clear()

    def _ensure_results_dir(self) -> Path:
        self._RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        return self._RESULTS_DIR

    def _default_export_basename(self) -> str:
        part = sanitize_path_segment(self.control_panel.edit_part_number.text())
        serial = sanitize_path_segment(self.control_panel.edit_serial_number.text())
        if part != "unknown" and serial != "unknown":
            return f"{part}_{serial}"
        return "report"

    def _export_metadata(self, title: str) -> dict[str, str]:
        return {
            "title": title,
            "part_number": self.control_panel.edit_part_number.text().strip(),
            "serial_number": self.control_panel.edit_serial_number.text().strip(),
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "user_name": str(self._user_info.get("name", "")),
            "user_role": str(self._user_info.get("role", "")),
        }

    def _format_text_header(self, meta: dict[str, str]) -> str:
        return (
            f"Title: {meta['title']}\n"
            f"Part Number: {meta['part_number']}\n"
            f"Serial Number: {meta['serial_number']}\n"
            f"Date: {meta['date']}\n"
            f"User: {meta['user_name']} ({meta['user_role']})\n"
            "-------------------\n"
        )

    def open_results_folder(self) -> None:
        folder = self._ensure_results_dir()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder.resolve())))

    def export_results_csv(self) -> None:
        if self._last_run_meta is None:
            QMessageBox.information(
                self,
                "Export",
                "No completed test results are cached. Run a test sequence first.",
            )
            return
        
        rg = ReportGenerator()
        archive_dir, stem = rg._resolved_archive_paths(self._last_run_meta)
        role_key = self._current_role().replace(" ", "_")
        suggested = archive_dir / f"{stem}_{role_key}.csv"
        
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Export results as CSV",
            str(suggested),
            "CSV Files (*.csv)",
        )
        if not selected:
            return
        path = Path(selected)
        if path.suffix.lower() != ".csv":
            path = path.with_suffix(".csv")
        try:
            rg.generate_csv_file(
                path,
                self._last_run_meta,
                self._last_run_rows,
                self._current_role(),
            )
            QMessageBox.information(self, "Export", f"Saved:\n{path}")
        except Exception as exc:
            QMessageBox.warning(self, "Export failed", str(exc))

    def export_results_pdf(self) -> None:
        if self._last_run_meta is None:
            QMessageBox.information(
                self,
                "Export",
                "No completed test results are cached. Run a test sequence first.",
            )
            return
        
        rg = ReportGenerator()
        archive_dir, stem = rg._resolved_archive_paths(self._last_run_meta)
        role_key = self._current_role().replace(" ", "_")
        suggested = archive_dir / f"{stem}_{role_key}.pdf"
        
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Export results as PDF",
            str(suggested),
            "PDF Files (*.pdf)",
        )
        if not selected:
            return
        path = Path(selected)
        if path.suffix.lower() != ".pdf":
            path = path.with_suffix(".pdf")
        try:
            rg.generate_pdf_file(
                path,
                self._last_run_meta,
                self._last_run_rows,
                self._current_role(),
            )
            QMessageBox.information(self, "Export", f"Saved:\n{path}")
        except Exception as exc:
            QMessageBox.warning(self, "Export failed", str(exc))

    def _make_log_button(
        self,
        name: str,
        tip: str,
        fallback: QStyle.StandardPixmap,
        icon_name: str,
    ) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName(name)
        btn.setToolTip(tip)
        btn.setAutoRaise(True)
        btn.setFixedSize(28, 28)
        btn.setIconSize(QSize(18, 18))
        btn.setIcon(self._icon(icon_name, fallback))
        return btn

    def save_log_to_file(self) -> None:
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Save trace log",
            str(self._ensure_results_dir() / f"{self._default_export_basename()}.txt"),
            "Text Files (*.txt)",
        )
        if not selected:
            return
        meta = self._export_metadata("DFX Tester - Trace Log")
        payload = self._format_text_header(meta) + "\n" + self.trace_log.toPlainText()
        Path(selected).write_text(payload, encoding="utf-8")

    def copy_log_to_clipboard(self) -> None:
        self.trace_log.selectAll()
        self.trace_log.copy()
        cursor = self.trace_log.textCursor()
        cursor.clearSelection()
        self.trace_log.setTextCursor(cursor)

    def _setup_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        ribbon = QHBoxLayout()
        if SHOW_NIGHT_MODE:
            self.btn_toggle_theme = self._make_ribbon_button("btn_toggle_theme", "Theme")
            self.btn_toggle_theme.clicked.connect(self.toggle_theme)
            ribbon.addWidget(self.btn_toggle_theme)

        self.btn_load_script = self._make_ribbon_button(
            "btn_load_script", "Select Product"
        )
        self.btn_load_script.clicked.connect(self.load_script)
        ribbon.addWidget(self.btn_load_script)

        self.btn_limits = self._make_ribbon_button("btn_limits", "Limits")
        self.btn_limits.clicked.connect(self.open_limits_editor)
        ribbon.addWidget(self.btn_limits)

        self.btn_versions = self._make_ribbon_button("btn_versions", "Versions")
        self.btn_versions.clicked.connect(self.open_version_manager)
        ribbon.addWidget(self.btn_versions)

        self.btn_audit = self._make_ribbon_button("btn_audit", "Logs")
        self.btn_audit.clicked.connect(self.open_audit_viewer)
        ribbon.addWidget(self.btn_audit)

        self.label_active_script = QLabel("")
        ribbon.addSpacing(12)
        ribbon.addWidget(self.label_active_script)

        ribbon.addStretch()

        self.lbl_brand_icon = QLabel()
        self.lbl_brand_icon.setObjectName("brand_icon")
        self.lbl_brand_icon.setFixedSize(220, 64)
        self.lbl_brand_icon.setScaledContents(False)
        self.lbl_brand_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_brand_icon.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        bird_path = self._ICONS_DIR / "DFXLogo.png"
        if bird_path.is_file():
            pix = QPixmap(str(bird_path)).scaled(
                self.lbl_brand_icon.width(),
                self.lbl_brand_icon.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.lbl_brand_icon.setPixmap(pix)
        self.lbl_brand_icon.setToolTip("DFX Tester")
        ribbon.addWidget(self.lbl_brand_icon, 0, Qt.AlignmentFlag.AlignVCenter)
        ribbon.addSpacing(12)

        self.btn_logout = self._make_ribbon_button("btn_logout", "Log Out")
        self.btn_logout.clicked.connect(self.logout)
        ribbon.addWidget(self.btn_logout)

        self.btn_exit = self._make_ribbon_button("btn_exit", "Exit")
        self.btn_exit.clicked.connect(self.close)
        ribbon.addWidget(self.btn_exit)

        main_layout.addLayout(ribbon)

        main_row = QHBoxLayout()
        main_row.setContentsMargins(0, 0, 0, 0)
        main_row.setSpacing(8)

        self.control_panel = ControlPanelWidget(self._user_info)
        self.control_panel.setObjectName("control_panel")
        self.control_panel.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding
        )
        self.control_panel.setMinimumWidth(280)
        self.control_panel.setMaximumWidth(340)

        self.test_list = QListWidget()
        self.test_list.setObjectName("test_list")
        self.test_list.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        self.test_list.setItemAlignment(Qt.AlignmentFlag.AlignTop)

        self.left_sidebar = QWidget()
        self.left_sidebar.setMinimumWidth(220)
        self.left_sidebar.setMaximumWidth(340)
        sidebar_layout = QVBoxLayout(self.left_sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(8)

        sidebar_layout.addWidget(self.control_panel.take_user_box())

        self.lbl_test_cases = QLabel("Test Cases")
        self.lbl_test_cases.setObjectName("lbl_test_cases")
        sidebar_layout.addWidget(self.lbl_test_cases)
        sidebar_layout.addWidget(self.test_list, stretch=1)

        test_list_actions = QHBoxLayout()
        test_list_actions.setSpacing(4)
        test_list_actions.setContentsMargins(0, 0, 0, 0)
        self.btn_select_all_tests = QPushButton("Select All")
        self.btn_select_all_tests.setObjectName("btn_select_all_tests")
        self.btn_select_all_tests.setMinimumHeight(26)
        self.btn_select_all_tests.clicked.connect(self._on_select_all_tests)
        self.btn_clear_all_tests = QPushButton("Clear All")
        self.btn_clear_all_tests.setObjectName("btn_clear_all_tests")
        self.btn_clear_all_tests.setMinimumHeight(26)
        self.btn_clear_all_tests.clicked.connect(self._on_clear_all_tests)
        test_list_actions.addWidget(self.btn_select_all_tests)
        test_list_actions.addWidget(self.btn_clear_all_tests)
        sidebar_layout.addLayout(test_list_actions)

        results_table_container = QWidget()
        center_layout = QVBoxLayout(results_table_container)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(6)

        if SHOW_SEARCH_BAR:
            self.edit_filter_results = QLineEdit()
            self.edit_filter_results.setObjectName("edit_filter_results")
            self.edit_filter_results.setClearButtonEnabled(True)
            self.edit_filter_results.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            self.edit_filter_results.setPlaceholderText(
                "\U0001F50D Search results (Test Name, Status...)"
            )
            self.edit_filter_results.textChanged.connect(self._filter_table_results)
            center_layout.addWidget(self.edit_filter_results)
        else:
            self.edit_filter_results = None

        self.results_table = QTableWidget(0, 5)
        self.results_table.setObjectName("results_table")
        self.results_table.setHorizontalHeaderLabels(
            ["Test Name", "Value", "Min", "Max", "Result"]
        )
        header = self.results_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionsMovable(True)
        for col in range(4):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.results_table.setColumnWidth(0, 250)
        self.results_table.setColumnWidth(1, 100)
        self.results_table.setColumnWidth(2, 100)
        self.results_table.setColumnWidth(3, 100)
        self.results_table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.results_table.setItemDelegateForColumn(
            4, ResultRowDelegate(self.results_table)
        )
        center_layout.addWidget(self.results_table, stretch=1)

        self.trace_log = QTextEdit()
        self.trace_log.setObjectName("trace_log")
        self.trace_log.setReadOnly(True)
        self.trace_log.setMinimumHeight(80)

        log_bar = QHBoxLayout()
        log_bar.addWidget(QLabel("HW Trace"))
        log_bar.addStretch()

        SP = QStyle.StandardPixmap
        self.btn_save_log = self._make_log_button(
            "btn_save_log", "Save log", SP.SP_DialogSaveButton, "save"
        )
        self.btn_save_log.clicked.connect(self.save_log_to_file)
        log_bar.addWidget(self.btn_save_log)

        self.btn_copy_log = self._make_log_button(
            "btn_copy_log", "Copy log", SP.SP_FileIcon, "copy"
        )
        self.btn_copy_log.clicked.connect(self.copy_log_to_clipboard)
        log_bar.addWidget(self.btn_copy_log)

        self.btn_clear_log = self._make_log_button(
            "btn_clear_log", "Clear log", SP.SP_TrashIcon, "clear"
        )
        self.btn_clear_log.clicked.connect(self._clear_trace)
        log_bar.addWidget(self.btn_clear_log)

        log_bar.addSpacing(16)
        self.chk_display_cmds = QCheckBox("Display tst file commands")
        self.chk_display_cmds.setChecked(True)
        self.chk_display_cmds.toggled.connect(self._refresh_trace_display)
        log_bar.addWidget(self.chk_display_cmds)

        self.trace_container = QWidget()
        trace_layout = QVBoxLayout(self.trace_container)
        trace_layout.setContentsMargins(0, 0, 0, 0)
        trace_layout.addLayout(log_bar)
        trace_layout.addWidget(self.trace_log)

        v_splitter = QSplitter(Qt.Vertical)
        v_splitter.setObjectName("center_splitter")
        v_splitter.addWidget(results_table_container)
        v_splitter.addWidget(self.trace_container)
        v_splitter.setStretchFactor(0, 7)
        v_splitter.setStretchFactor(1, 3)
        v_splitter.setSizes([700, 300])
        v_splitter.setCollapsible(0, False)
        v_splitter.setCollapsible(1, False)
        v_splitter.setHandleWidth(4)

        self.control_panel.start_requested.connect(self._on_start_clicked)
        self.control_panel.stop_requested.connect(self.stop_tests)
        self.control_panel.edit_part_number.textEdited.connect(
            self._mark_part_number_user_edited
        )

        right_panel = QWidget()
        right_panel.setObjectName("right_panel_contents")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(2)
        if SHOW_LIVE_MONITOR:
            self.instrument_panel = InstrumentPanelWidget()
            right_layout.addWidget(self.instrument_panel, stretch=0)
        right_layout.addWidget(self.control_panel, stretch=1)

        right_scroll = QScrollArea()
        right_scroll.setObjectName("right_panel_scroll")
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        right_scroll.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        right_scroll.setMinimumWidth(340)
        right_scroll.setMaximumWidth(420)
        right_scroll.setWidget(right_panel)

        main_row.addWidget(self.left_sidebar)
        main_row.addWidget(v_splitter, stretch=1)
        main_row.addWidget(right_scroll)

        main_layout.addLayout(main_row, stretch=1)

        self.sequence_finished.connect(self._show_result_dialog)

    def _fit_initial_size_to_screen(self) -> None:
        """Keep the first show inside the usable desktop area on scaled displays."""
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            self.resize(1200, 800)
            return

        available = screen.availableGeometry()
        margin = 24
        min_size = self.minimumSizeHint()
        width = min(1200, max(min_size.width(), available.width() - margin))
        height = min(800, max(min_size.height(), available.height() - margin))
        self.resize(width, height)

    def _filter_table_results(self, text: str) -> None:
        needle = text.strip().lower()
        for row in range(self.results_table.rowCount()):
            if not needle:
                self.results_table.setRowHidden(row, False)
                continue
            name_item = self.results_table.item(row, 0)
            result_item = self.results_table.item(row, 4)
            haystack = " ".join(
                i.text().lower() for i in (name_item, result_item) if i is not None
            )
            self.results_table.setRowHidden(row, needle not in haystack)

    def _theme_path(self) -> Path:
        name = "dark_theme.qss" if self.is_dark_mode else "light_theme.qss"
        return resource_path("ui", "assets", name)

    def _apply_theme_file(self) -> None:
        path = self._theme_path()
        qss = path.read_text(encoding="utf-8")
        self.setStyleSheet(qss)

    def toggle_theme(self) -> None:
        self.is_dark_mode = not self.is_dark_mode
        self._apply_theme_file()
        self._update_icons(self.is_dark_mode)

    def _apply_test_item_permissions(self, item: QListWidgetItem) -> None:
        flags = item.flags() | Qt.ItemFlag.ItemIsUserCheckable
        if self._is_operator():
            flags &= ~Qt.ItemFlag.ItemIsUserCheckable
        item.setFlags(flags)

    def _mark_part_number_user_edited(self, _text: str) -> None:
        self._part_number_user_edited = True

    def _cleanup_operator_temp(self) -> None:
        if self._operator_temp_script is None:
            return
        path = self._operator_temp_script
        self._operator_temp_script = None
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            pass

    @staticmethod
    def _parse_labeled_counter(text: str, prefix: str) -> int:
        needle = prefix + ":"
        if needle in text:
            try:
                return int(text.split(needle, 1)[1].strip())
            except ValueError:
                return 0
        return 0

    def _unlock_pre_test_fields(self) -> None:
        self._pre_test_locked = False
        self.control_panel.edit_serial_number.setReadOnly(False)
        self.control_panel.edit_uut_type.setReadOnly(False)
        self.control_panel.edit_user_name.setReadOnly(True)
        self.control_panel.edit_user_name.setText(str(self._user_info.get("name", "")))
        self.control_panel.edit_serial_number.clear()
        self.control_panel.edit_uut_type.clear()

    def _finalize_run_reports(self) -> None:
        th = self.test_thread
        if th is None:
            return
        meta, rows = th.report_snapshot()
        logical_name = f"{self._catalog_test_name} {getattr(self, '_catalog_version', '')}".strip()
        meta["test_program_name"] = logical_name
        self._last_run_meta = meta
        self._last_run_rows = list(rows)
        if not self.control_panel.chk_save_log.isChecked():
            self.append_trace("Save as log disabled — skipping PDF archive.")
            return
        self._report_worker = ReportWorker(meta, rows, self._current_role(), parent=self)
        self._report_worker.archived.connect(
            lambda p: self.append_trace(f"Report archived: {Path(p).name}")
        )
        self._report_worker.failed.connect(
            lambda e: self.append_trace(f"Report generation failed: {e}")
        )
        self._report_worker.finished.connect(self._report_worker.deleteLater)
        self._report_worker.finished.connect(lambda: setattr(self, "_report_worker", None))
        self._report_worker.start()

    def load_script(self) -> None:
        """Load a test from the database catalog (temp file) for every role."""
        dlg = SelectTestDialog(parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        path = dlg.selected_path()
        if path is None:
            return
        catalog = dlg.selected_catalog() or {}
        uut_type = str(catalog.get("uut_type", ""))
        self._cleanup_operator_temp()
        self._operator_temp_script = path
        self._active_script_path = path
        self._catalog_test_name = str(catalog.get("test_name", path.stem))
        self._catalog_version = str(catalog.get("version_name", ""))
        self._catalog_uut_type = uut_type
        self.control_panel.edit_uut_type.setText(uut_type)
        self._reload_script_into_list()

    def _reload_script_into_list(self) -> None:
        """Parse the active script and repopulate the test list checkboxes."""
        self.test_list.clear()
        logical_name = f"{self._catalog_test_name} {getattr(self, '_catalog_version', '')}".strip()
        self.label_active_script.setText(logical_name)

        if not self._active_script_path.is_file():
            self.append_trace(
                f"Active script not found: {self._active_script_path}"
            )
            return

        try:
            document = self._script_manager.load_document(self._active_script_path)
            steps = document.steps
        except ScriptParseError as exc:
            QMessageBox.warning(
                self,
                "Script parse error",
                f"Could not parse {self._active_script_path.name}:\n"
                f"line {exc.line_no}: {exc.msg}",
            )
            self.append_trace(
                f"Script parse error at line {exc.line_no}: {exc.msg}"
            )
            return
        except (OSError, ValueError) as exc:
            QMessageBox.warning(
                self,
                "Script load error",
                f"Could not load {self._active_script_path.name}:\n{exc}",
            )
            return

        for step in steps:
            item = QListWidgetItem(step.name)
            self._apply_test_item_permissions(item)
            item.setCheckState(Qt.CheckState.Checked)
            self.test_list.addItem(item)

        script_part_number = document.metadata.get("part_number", "").strip()
        if script_part_number and not self._part_number_user_edited:
            self.control_panel.edit_part_number.setText(script_part_number)

        self.append_trace(
            f"Loaded {len(steps)} step(s) from {logical_name}."
        )
        self.control_panel.edit_part_number.setReadOnly(True)

    def _selected_test_names(self) -> list[str]:
        """Return only checked test names from the list widget."""
        names: list[str] = []
        for i in range(self.test_list.count()):
            item = self.test_list.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                names.append(item.text())
        return names

    def _rebuild_test_list_from_names(self, names: list[str]) -> None:
        self.test_list.clear()
        for name in names:
            item = QListWidgetItem(name)
            self._apply_test_item_permissions(item)
            item.setCheckState(Qt.CheckState.Checked)
            self.test_list.addItem(item)

    def _on_start_clicked(self) -> None:
        txt = self.control_panel.btn_start.text()
        if txt == "Pause":
            if self.test_thread and self.test_thread.isRunning():
                self.test_thread.pause()
            self.control_panel.btn_start.setText("Resume")
            return

        if txt == "Resume":
            if self.test_thread and self.test_thread.isRunning():
                self.test_thread.resume_pause()
            self.control_panel.btn_start.setText("Pause")
            return

        dlg = PreTestDialog(
            tester_name_default=str(self._user_info.get("name", "")),
            default_uut_type=self.control_panel.edit_uut_type.text(),
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        dialog_results = dlg.result_dict()
        self.control_panel.edit_serial_number.setText(dialog_results["serial_number"])
        self.control_panel.edit_user_name.setText(dialog_results["tester_name"])

        tests_to_run = self._selected_test_names()
        if not tests_to_run:
            self.append_trace("No tests selected (check at least one item in the list).")
            return

        if not self._active_script_path.is_file():
            QMessageBox.warning(
                self,
                "No script",
                f"Active script does not exist: {self._active_script_path}",
            )
            return

        part_number = self.control_panel.edit_part_number.text().strip()
        serial_number = self.control_panel.edit_serial_number.text().strip()
        if not part_number or not serial_number:
            QMessageBox.warning(
                self,
                "Missing unit info",
                "Part Number and Serial Number are required before starting a test.",
            )
            return

        self.control_panel.edit_uut_type.setText(dialog_results["uut_type"])
        self.control_panel.edit_serial_number.setReadOnly(True)
        self.control_panel.edit_uut_type.setReadOnly(True)
        self.control_panel.edit_user_name.setReadOnly(True)
        self._pre_test_locked = True

        self._clear_trace()
        self._start_test_run(dialog_results)

    def _start_test_run(self, pre_meta: dict) -> None:
        """Decide Sim vs Hardware and start the run.

        Simulation launches immediately. Hardware first runs a non-blocking
        preflight on a background thread; the run starts (or falls back) in
        `_on_preflight_completed` so the UI never freezes on a VISA/serial timeout.
        """
        db = DatabaseManager()
        connections = db.list_instrument_connections()
        bench_cfg = db.get_bench_config()

        if self.control_panel.chk_simulation.isChecked():
            self._launch_runner(
                pre_meta, build_bench(connections=connections, bench_cfg=bench_cfg)
            )
            return

        self.append_trace("Hardware mode: checking instrument connections...")
        self.control_panel.btn_start.setEnabled(False)
        self._pending_pre_meta = dict(pre_meta)
        self._pending_connections = connections
        self._pending_bench_cfg = bench_cfg
        self._preflight_thread = PreflightWorker(connections, bench_cfg)
        self._preflight_thread.completed.connect(self._on_preflight_completed)
        self._preflight_thread.finished.connect(self._preflight_thread.deleteLater)
        self._preflight_thread.start()

    def _on_preflight_completed(self, ok: bool, report: list) -> None:
        """Resume the run after the background hardware preflight reports back."""
        self.control_panel.btn_start.setEnabled(True)
        for line in report:
            self.append_trace(line)

        pre_meta = getattr(self, "_pending_pre_meta", {})
        connections = getattr(self, "_pending_connections", {})
        bench_cfg = getattr(self, "_pending_bench_cfg", {})

        if ok:
            self.append_trace("All instruments responded; starting on real hardware.")
            self._launch_runner(
                pre_meta,
                build_bench(
                    hardware_mode=True, connections=connections, bench_cfg=bench_cfg
                ),
            )
            return

        choice = QMessageBox.warning(
            self,
            "Hardware not ready",
            "Some instruments are not available:\n\n"
            + "\n".join(report)
            + "\n\nRun in Simulation mode instead?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice == QMessageBox.StandardButton.Yes:
            self.append_trace("Falling back to Simulation mode.")
            self._launch_runner(
                pre_meta, build_bench(connections=connections, bench_cfg=bench_cfg)
            )
        else:
            self.append_trace("Run aborted: hardware not ready.")

    def _launch_runner(self, pre_meta: dict, driver: BaseDriver) -> None:
        tests_to_run = self._selected_test_names()

        self.results_table.setRowCount(0)
        self.control_panel.progress_total.setValue(0)
        self.control_panel.progress_test.setValue(0)
        self.control_panel.edit_current_test.clear()
        self.control_panel.label_pass.setText("PASS: 0")
        self.control_panel.label_fail.setText("FAIL: 0")

        self.control_panel.btn_stop.setEnabled(True)
        self.control_panel.btn_start.setText("Pause")

        loop_count = (
            self.control_panel.spin_loops.value()
            if self.control_panel.chk_loops.isChecked()
            else 1
        )
        stop_on_fail = self.control_panel.chk_stop_on_fail.isChecked()

        operator = self.control_panel.edit_user_name.text().strip()
        part_number = self.control_panel.edit_part_number.text().strip()
        serial_number = self.control_panel.edit_serial_number.text().strip()

        started = datetime.now()
        employee_id = str(self._user_info.get("employee_id", ""))
        logical_script_name = (
            f"{self._catalog_test_name} {getattr(self, '_catalog_version', '')}"
        ).strip()

        self.test_thread = TestRunnerThread(
            self._active_script_path,
            set(tests_to_run),
            loop_count=loop_count,
            stop_on_fail=stop_on_fail,
            operator=operator,
            tester_name=pre_meta["tester_name"].strip(),
            employee_id=employee_id,
            uut_type=pre_meta["uut_type"].strip(),
            part_number=part_number,
            serial_number=serial_number,
            script_manager=self._script_manager,
            start_time=started,
            logical_script_name=logical_script_name,
            driver=driver,
        )
        self.test_thread.log_msg.connect(self.append_trace)
        self.test_thread.test_result.connect(self.update_results_table)
        self.test_thread.loop_started.connect(self._on_loop_started)
        self.test_thread.progress_total.connect(self.control_panel.progress_total.setValue)
        self.test_thread.progress_test.connect(self.control_panel.progress_test.setValue)
        self.test_thread.current_test.connect(self.control_panel.edit_current_test.setText)
        self.test_thread.prompt_request.connect(self._on_prompt_request)
        self.test_thread.prompt_yesno_request.connect(self._on_prompt_yesno_request)
        self.test_thread.script_log.connect(self._on_script_log)
        self.test_thread.finished.connect(self.on_tests_finished)
        self.test_thread.finished.connect(self.test_thread.deleteLater)

        try:
            DatabaseManager().log_audit_action(
                "Test run started",
                username=str(self._user_info.get("username", "")),
                employee_id=employee_id,
                details=(
                    f"script={logical_script_name} "
                    f"part={part_number!r} sn={serial_number!r} "
                    f"steps={len(tests_to_run)}"
                ),
            )
        except Exception:
            pass

        self.test_thread.start()

    def _on_prompt_request(self, msg: str) -> None:
        """Show a modal prompt; resume the runner once the operator clicks OK."""
        QMessageBox.information(self, "Test Prompt", msg)
        if self.test_thread is not None:
            self.test_thread.resume()

    def _on_prompt_yesno_request(self, msg: str) -> None:
        """Show a Yes/No prompt; relay the answer to the runner thread."""
        result = QMessageBox.question(
            self,
            "Test Prompt",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        answer = result == QMessageBox.StandardButton.Yes
        if self.test_thread is not None:
            self.test_thread.submit_yesno_answer(answer)

    def _on_script_log(self, msg: str) -> None:
        """Append an operator-authored Log line to the trace, distinctly styled."""
        stamped = f"{datetime.now().strftime('[%H:%M:%S]')} {msg}"
        self._record_trace("log", stamped)
        if self._secure is not None:
            try:
                self._secure.log(
                    "script_log",
                    {"message": msg, "display": stamped},
                )
            except Exception:
                pass

    def _format_trace_html(self, entry_type: str, text: str) -> str:
        if entry_type == "log":
            return (
                '<span style="color:#22d3ee;"><i>[LOG]</i> '
                f"{html.escape(text)}</span>"
            )
        return html.escape(text)

    def _entry_passes_filter(self, entry: dict) -> bool:
        if self.chk_display_cmds.isChecked():
            return True
        return entry["type"] != "cmd"

    def _record_trace(self, entry_type: str, text: str) -> None:
        entry = {
            "type": entry_type,
            "text": text,
            "html": self._format_trace_html(entry_type, text),
        }
        self._trace_history.append(entry)
        if self._entry_passes_filter(entry):
            self.trace_log.append(entry["html"])

    def _refresh_trace_display(self) -> None:
        self.trace_log.clear()
        for entry in self._trace_history:
            if self._entry_passes_filter(entry):
                self.trace_log.append(entry["html"])

    def _clear_trace(self) -> None:
        self._trace_history.clear()
        self.trace_log.clear()

    def stop_tests(self) -> None:
        if self.test_thread and self.test_thread.isRunning():
            self.test_thread.stop()
            self.append_trace("Stopping sequence...")

    def _shutdown_threads(self) -> None:
        if self.test_thread is not None and self.test_thread.isRunning():
            self.test_thread.stop()
            if not self.test_thread.wait(5000):
                self.append_trace("Warning: test thread did not stop within 5s.")
        if self._report_worker is not None and self._report_worker.isRunning():
            self._report_worker.wait(5000)
        if hasattr(self, "monitor_thread") and self.monitor_thread.isRunning():
            self.monitor_thread.stop()

    def logout(self) -> None:
        """Closes the main window and signals the application to restart the login flow."""
        confirm = QMessageBox.question(
            self,
            "Log Out",
            "Are you sure you want to log out and switch users?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            try:
                DatabaseManager().log_audit_action(
                    "User Logged Out",
                    username=str(self._user_info.get("username", "")),
                    employee_id=str(self._user_info.get("employee_id", "")),
                    details="",
                )
            except Exception:
                pass
            self._cleanup_operator_temp()
            self._shutdown_threads()
            self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            self.setProperty("logout_requested", True)
            app = QApplication.instance()
            if app is not None:
                app.setProperty("logout_requested", True)
            self.close()

    def closeEvent(self, event) -> None:
        if self.test_thread is not None and self.test_thread.isRunning():
            confirm = QMessageBox.question(
                self,
                "Test in progress",
                "A test is still running. Stop it and exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        app = QApplication.instance()
        if app is not None and not bool(app.property("logout_requested")):
            try:
                DatabaseManager().log_audit_action(
                    "User Logged Out",
                    username=str(self._user_info.get("username", "")),
                    employee_id=str(self._user_info.get("employee_id", "")),
                    details="",
                )
            except Exception:
                pass
        self._shutdown_threads()
        self._cleanup_operator_temp()
        super().closeEvent(event)

    def _on_loop_started(self, loop_number: int, loop_total: int) -> None:
        """Insert a visual separator row before each new loop iteration."""
        col_count = self.results_table.columnCount()
        row = self.results_table.rowCount()
        self.results_table.insertRow(row)
        self.results_table.setSpan(row, 0, 1, col_count)

        item = QTableWidgetItem(f"──  Loop {loop_number} of {loop_total}  ──")
        font = QFont()
        font.setBold(True)
        item.setFont(font)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setBackground(QBrush(QColor("#2f65ca")))
        item.setForeground(QBrush(QColor("white")))
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self.results_table.setItem(row, 0, item)

    def update_results_table(self, test_name: str, result: TestResultPayload) -> None:
        row = self.results_table.rowCount()
        self.results_table.insertRow(row)

        passed = bool(result["passed"])
        status = "PASS" if passed else "FAIL"
        is_measurement = bool(result.get("is_measurement", True))

        if is_measurement:
            unit = result["unit"]
            val_str = (
                f"{_format_measurement(result['value'])} {unit}".rstrip()
            )
            min_str = _format_measurement(result["min"])
            max_str = _format_measurement(result["max"])
        else:
            val_str = _NA
            min_str = _NA
            max_str = _NA

        self.results_table.setItem(row, 0, QTableWidgetItem(test_name))
        self.results_table.setItem(row, 1, QTableWidgetItem(val_str))
        self.results_table.setItem(row, 2, QTableWidgetItem(min_str))
        self.results_table.setItem(row, 3, QTableWidgetItem(max_str))

        status_item = QTableWidgetItem(status)
        status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.results_table.setItem(row, 4, status_item)

        if passed:
            n = self._parse_labeled_counter(self.control_panel.label_pass.text(), "PASS") + 1
            self.control_panel.label_pass.setText(f"PASS: {n}")
        else:
            n = self._parse_labeled_counter(self.control_panel.label_fail.text(), "FAIL") + 1
            self.control_panel.label_fail.setText(f"FAIL: {n}")

    def append_trace(self, msg: str) -> None:
        stamped = f"{datetime.now().strftime('[%H:%M:%S]')} {msg}"
        entry_type = "cmd" if msg.startswith("Executing:") else "info"
        self._record_trace(entry_type, stamped)

    def on_tests_finished(self) -> None:
        th = self.test_thread
        if th is None:
            return

        self.append_trace("Sequence Complete.")

        overall_passed = False
        try:
            self._finalize_run_reports()
        finally:
            try:
                meta, _rows = th.report_snapshot()
                overall_passed = (
                    str(meta.get("overall_result", "")).strip().upper() == "PASS"
                )
                DatabaseManager().log_audit_action(
                    "Test run completed",
                    username=str(self._user_info.get("username", "")),
                    employee_id=str(self._user_info.get("employee_id", "")),
                    details=(
                        f"overall={meta.get('overall_result', '?')} "
                        f"script={meta.get('test_program_name', '')}"
                    ),
                )
            except Exception:
                pass
            th.resume_pause()

        self.control_panel.set_running_state(False)
        self.control_panel.edit_part_number.setReadOnly(False)
        if self._active_script_path.is_file():
            self.control_panel.edit_part_number.setReadOnly(True)
        self._unlock_pre_test_fields()
        self.test_thread = None

        self.sequence_finished.emit(overall_passed)

    def _show_result_dialog(self, passed: bool) -> None:
        TestResultDialog(passed, parent=self).exec()

    def _on_select_all_tests(self) -> None:
        for i in range(self.test_list.count()):
            item = self.test_list.item(i)
            if item is not None:
                item.setCheckState(Qt.CheckState.Checked)

    def _on_clear_all_tests(self) -> None:
        for i in range(self.test_list.count()):
            item = self.test_list.item(i)
            if item is not None:
                item.setCheckState(Qt.CheckState.Unchecked)


