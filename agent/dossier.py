from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt

from .evidence import EvidenceCapture


def append_evidence_dossier(
    filled_form: Path,
    output_path: Path,
    captures: list[EvidenceCapture],
) -> None:
    doc = Document(filled_form)

    for capture in captures:
        doc.add_page_break()
        heading = doc.add_paragraph()
        heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = heading.add_run(f"APPENDIX {capture.appendix_label} - {capture.group} Evidence")
        run.bold = True
        run.font.size = Pt(14)

        _labelled_paragraph(doc, "Source", capture.source.title)
        _labelled_paragraph(doc, "Publisher", capture.source.publisher)
        _labelled_paragraph(doc, "Source tier", str(capture.source.tier))
        _labelled_paragraph(doc, "URL", capture.source.url)
        _labelled_paragraph(doc, "Relevant finding", capture.source.relevant_extract)
        _labelled_paragraph(doc, "Agent interpretation", capture.source.interpretation)
        _labelled_paragraph(doc, "Evidence capture", capture.capture_status)
        if capture.capture_note:
            _labelled_paragraph(doc, "Capture note", capture.capture_note)

        if capture.capture_path and capture.capture_path.exists():
            image_para = doc.add_paragraph()
            image_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            image_para.add_run().add_picture(str(capture.capture_path), width=Inches(6.15))
        else:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run("No automated screenshot was available. Review the source URL above.")
            r.italic = True

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)


def _labelled_paragraph(doc: Document, label: str, value: str) -> None:
    p = doc.add_paragraph()
    p.add_run(f"{label}: ").bold = True
    p.add_run(value or "N/A")


def find_soffice() -> str | None:
    candidates = [
        shutil.which("soffice"),
        shutil.which("libreoffice"),
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    return None


def convert_docx_to_pdf(docx_path: Path, output_dir: Path) -> Path | None:
    soffice = find_soffice()
    if not soffice:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(output_dir), str(docx_path)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        return None
    pdf_path = output_dir / f"{docx_path.stem}.pdf"
    return pdf_path if pdf_path.exists() else None
