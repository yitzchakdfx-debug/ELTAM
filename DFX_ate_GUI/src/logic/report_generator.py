"""PDF and CSV test reports with role-based detail and archiving."""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from PyPDF2 import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as _pdfcanvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.platypus.tables import LongTable

from config import ADMIN_REPORT_PASSWORD, TESTER_SERIAL_NUMBER
from paths import resource_path, user_data_path
from version import __version__

_LOGO_PATH = resource_path("ui", "assets", "icons", "BirdLogo.png")

def sanitize_path_segment(value: str) -> str:
    """Flatten whitespace and strip characters that break filesystem paths."""
    cleaned = re.sub(r"\s+", "_", value.strip())
    return re.sub(r'[\\/:*?"<>|]+', "", cleaned) or "unknown"


class ReportGenerator:
    """Writes PDF archives under src/data/results/<UUT>/<Serial>/ and optional manual exports."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base = base_dir if base_dir is not None else user_data_path("results")

    def suggested_export_path(self, run_meta: dict[str, Any], suffix: str = ".pdf") -> Path:
        """Return the path that ``generate_pdf_auto_archive`` would write to.

        Useful for showing the operator a preview destination before the run
        completes.  The timestamp component will differ from the actual write
        time; callers should treat this as an *approximate* path.
        """
        archive_dir, stem = self._resolved_archive_paths(run_meta)
        return archive_dir / (stem + suffix)

    def _resolved_archive_paths(self, run_meta: dict[str, Any]) -> tuple[Path, str]:
        """Sanitized subdirectory (uut/serial), timestamp stem for filenames."""
        uut_seg = sanitize_path_segment(str(run_meta.get("uut_type", "")).strip())
        sn_seg = sanitize_path_segment(str(run_meta.get("serial_number", "")).strip())
        test_name_meta = str(run_meta.get("test_program_name", "report")).strip()
        stem_test = sanitize_path_segment(test_name_meta)

        archive_dir = self._base / uut_seg / sn_seg
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        stem = "_".join(
            [
                stem_test,
                ts,
                sn_seg,
            ]
        )
        return archive_dir, stem

    def generate_pdf_auto_archive(
        self,
        run_meta: dict[str, Any],
        results: list[dict[str, Any]],
        role: str,
    ) -> Path:
        """Persist only PDF under the structured archive folder (CSV is manual-export only)."""
        role_key = role.strip().title()
        archive_dir, stem = self._resolved_archive_paths(run_meta)
        archive_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = archive_dir / f"{stem}_{role_key.replace(' ', '_')}.pdf"
        write_pdf_report(pdf_path, run_meta, results, role_key)
        return pdf_path

    def generate_csv_file(
        self,
        dest: Path | str,
        run_meta: dict[str, Any],
        results: list[dict[str, Any]],
        role: str,
    ) -> Path:
        path = Path(dest)
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_csv(path, run_meta, results, role.strip().title())
        return path

    def generate_pdf_file(
        self,
        dest: Path | str,
        run_meta: dict[str, Any],
        results: list[dict[str, Any]],
        role: str,
    ) -> Path:
        path = Path(dest)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_pdf_report(path, run_meta, results, role.strip().title())
        return path

    # Backward-compat name used elsewhere
    def generate(
        self,
        run_meta: dict[str, Any],
        results: list[dict[str, Any]],
        role: str,
    ) -> Path:
        """Auto-archive PDF only."""
        return self.generate_pdf_auto_archive(run_meta, results, role)


def _fmt_num(v: Any) -> str:
    if v is None:
        return ""
    try:
        return f"{float(v):g}"
    except (TypeError, ValueError):
        return str(v)


def _header_rows(run_meta: dict[str, Any], role: str) -> list[tuple[str, str]]:
    overall = str(run_meta.get("overall_result", "—"))
    return [
        ("Result (Overall)", overall),
        ("User Name", str(run_meta.get("tester_name", ""))),
        ("Employee ID", str(run_meta.get("employee_id", ""))),
        ("Product Name", str(run_meta.get("test_program_name", ""))),
        ("UUT Type", str(run_meta.get("uut_type", ""))),
        ("PartNumber", str(run_meta.get("part_number", ""))),
        ("SN", str(run_meta.get("serial_number", ""))),
        ("Start Time", str(run_meta.get("start_time", ""))),
        ("End Time", str(run_meta.get("end_time", ""))),
        ("SW SN", TESTER_SERIAL_NUMBER),
        ("SW Version", __version__),
        ("Role / Report Detail", role),
    ]


def _write_csv(
    path: Path,
    run_meta: dict[str, Any],
    results: list[dict[str, Any]],
    role: str,
) -> None:
    is_admin = role == "Admin"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Field", "Value"])
        for k, v in _header_rows(run_meta, role):
            writer.writerow([k, v])
        writer.writerow([])
        if is_admin:
            writer.writerow(["Test Name", "Min", "Max", "Value", "Unit", "Result"])
            for row in results:
                writer.writerow(
                    [
                        row.get("test_name", ""),
                        _fmt_num(row.get("min")),
                        _fmt_num(row.get("max")),
                        _fmt_num(row.get("value")),
                        row.get("unit", ""),
                        "PASS" if row.get("passed") else "FAIL",
                    ]
                )
        else:
            writer.writerow(["Test Name", "Result"])
            for row in results:
                writer.writerow(
                    [
                        row.get("test_name", ""),
                        "PASS" if row.get("passed") else "FAIL",
                    ]
                )


_LOGO_TARGET_WIDTH = 1.6 * inch
_LOGO_RIGHT_MARGIN = 0.35 * inch
_LOGO_TOP_MARGIN = 0.30 * inch


def _build_logo_watermark_bytes(page_size: tuple[float, float]) -> bytes | None:
    """Single-page PDF with the company logo anchored to the top-right corner.

    Coordinates are computed from absolute page dimensions (independent of
    content length) so the stamp lands in the same spot on every page.
    Each call builds its own buffer/canvas — no shared state, safe for
    concurrent use with ``page.merge_page()``.
    """
    if not _LOGO_PATH.is_file():
        return None
    try:
        img_reader = ImageReader(str(_LOGO_PATH))
        src_w, src_h = img_reader.getSize()
    except Exception:
        return None
    if src_w <= 0 or src_h <= 0:
        return None

    aspect = src_h / src_w
    logo_w = _LOGO_TARGET_WIDTH
    logo_h = logo_w * aspect

    width, height = page_size
    x = width - logo_w - _LOGO_RIGHT_MARGIN
    y = height - logo_h - _LOGO_TOP_MARGIN

    buf = io.BytesIO()
    c = _pdfcanvas.Canvas(buf, pagesize=page_size)
    try:
        c.drawImage(
            img_reader,
            x,
            y,
            width=logo_w,
            height=logo_h,
            mask="auto",
            preserveAspectRatio=True,
            anchor="ne",
        )
    except Exception:
        return None
    c.showPage()
    c.save()
    return buf.getvalue()


def _stamp_logo_watermark(raw_pdf: bytes, page_size: tuple[float, float]) -> bytes:
    """Overlay the logo watermark on every page via ``page.merge_page()``.

    The watermark sits in the top margin (above the title area), so the
    underlying table text is not displaced and alignment is preserved.
    """
    watermark_bytes = _build_logo_watermark_bytes(page_size)
    if watermark_bytes is None:
        return raw_pdf
    src_reader = PdfReader(io.BytesIO(raw_pdf))
    wm_reader = PdfReader(io.BytesIO(watermark_bytes))
    wm_page = wm_reader.pages[0]
    writer = PdfWriter()
    for pg in src_reader.pages:
        pg.merge_page(wm_page)
        writer.add_page(pg)
    out_buf = io.BytesIO()
    writer.write(out_buf)
    return out_buf.getvalue()


def write_pdf_report(
    path: Path,
    run_meta: dict[str, Any],
    results: list[dict[str, Any]],
    role: str,
) -> None:
    """Build paginated PDF (SimpleDocTemplate + LongTable for results splits across pages)."""
    is_admin = role == "Admin"
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()
    flow: list[Any] = []

    flow.append(
        Paragraph(
            "<b>DFX Tester — Test Report</b>",
            styles["Heading1"],
        )
    )
    flow.append(Spacer(1, 0.15 * inch))

    header_data = [["Field", "Value"]]
    for h, v in _header_rows(run_meta, role):
        header_data.append([h, v])
    ht = Table(header_data, colWidths=[2.4 * inch, 4 * inch])
    ht.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f65ca")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    flow.append(ht)
    flow.append(Spacer(1, 0.25 * inch))

    if is_admin:
        headers = ["Test Name", "Min", "Max", "Value", "Unit", "Status"]
        col_w = [
            1.35 * inch,
            0.75 * inch,
            0.75 * inch,
            0.85 * inch,
            0.65 * inch,
            0.65 * inch,
        ]
    else:
        headers = ["Test Name", "Result"]
        col_w = [5.35 * inch, 1 * inch]

    n_cols = len(headers)
    loop_total = max(1, int(run_meta.get("loop_count", 1) or 1))
    has_loops = loop_total > 1 and any(int(r.get("loop", 1)) > 1 for r in results)

    data: list[list[Any]] = [headers]
    loop_header_rows: list[int] = []
    fail_rows: list[int] = []
    current_loop: int | None = None

    for row in results:
        loop_num = int(row.get("loop", 1))
        if has_loops and loop_num != current_loop:
            loop_header_rows.append(len(data))
            data.append(
                [f"Loop {loop_num} of {loop_total}"] + [""] * (n_cols - 1)
            )
            current_loop = loop_num

        ok = bool(row.get("passed"))
        if not ok:
            fail_rows.append(len(data))

        if is_admin:
            data.append(
                [
                    Paragraph(row.get("test_name", ""), styles["Normal"]),
                    _fmt_num(row.get("min")),
                    _fmt_num(row.get("max")),
                    _fmt_num(row.get("value")),
                    row.get("unit", ""),
                    "PASS" if ok else "FAIL",
                ]
            )
        else:
            data.append(
                [
                    Paragraph(row.get("test_name", ""), styles["Normal"]),
                    "PASS" if ok else "FAIL",
                ]
            )

    rt = LongTable(data, colWidths=col_w, repeatRows=1)

    fail_bg = colors.HexColor("#fee2e2")   # light pink — highlights the row
    fail_fg = colors.HexColor("#b91c1c")   # strong red — bold FAIL text

    style_cmds: list[Any] = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#444444")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for ridx in loop_header_rows:
        style_cmds.extend(
            [
                ("SPAN", (0, ridx), (-1, ridx)),
                ("BACKGROUND", (0, ridx), (-1, ridx), colors.HexColor("#2f65ca")),
                ("TEXTCOLOR", (0, ridx), (-1, ridx), colors.whitesmoke),
                ("FONTNAME", (0, ridx), (-1, ridx), "Helvetica-Bold"),
                ("ALIGN", (0, ridx), (-1, ridx), "CENTER"),
                ("TOPPADDING", (0, ridx), (-1, ridx), 6),
                ("BOTTOMPADDING", (0, ridx), (-1, ridx), 6),
            ]
        )
    for ridx in fail_rows:
        style_cmds.extend(
            [
                ("BACKGROUND", (0, ridx), (-1, ridx), fail_bg),
                ("TEXTCOLOR", (-1, ridx), (-1, ridx), fail_fg),
                ("FONTNAME", (-1, ridx), (-1, ridx), "Helvetica-Bold"),
            ]
        )
    rt.setStyle(TableStyle(style_cmds))
    flow.append(rt)

    doc.build(flow)
    raw_pdf = buffer.getvalue()
    buffer.close()

    stamped_pdf = _stamp_logo_watermark(raw_pdf, letter)

    if is_admin:
        reader = PdfReader(io.BytesIO(stamped_pdf))
        writer = PdfWriter()
        for pg in reader.pages:
            writer.add_page(pg)
        writer.encrypt(
            user_password=ADMIN_REPORT_PASSWORD,
            owner_password=ADMIN_REPORT_PASSWORD,
        )
        out_buf = io.BytesIO()
        writer.write(out_buf)
        path.write_bytes(out_buf.getvalue())
    else:
        path.write_bytes(stamped_pdf)
