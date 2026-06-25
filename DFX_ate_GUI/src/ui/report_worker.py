"""Background worker that renders/archives a PDF report off the GUI thread."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from logic.report_generator import ReportGenerator


class ReportWorker(QThread):
    archived = Signal(str)
    failed = Signal(str)

    def __init__(self, meta: dict, rows: list[dict], role: str, parent=None) -> None:
        super().__init__(parent)
        self._meta, self._rows, self._role = dict(meta), list(rows), role

    def run(self) -> None:
        try:
            path = ReportGenerator().generate_pdf_auto_archive(self._meta, self._rows, self._role)
            self.archived.emit(str(path))
        except Exception as exc:
            self.failed.emit(str(exc))
