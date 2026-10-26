"""Controlled, zero-AI bulk export of completed material-assessment outputs.

The export manifest is resolved against the SQLite queue and on-disk outputs,
never arbitrary client paths. COSHH must match the *current* controlled Word
master; an earlier Word revision cannot be silently included in a ZIP.
"""
from __future__ import annotations

import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import quote
from zipfile import ZipFile, ZIP_DEFLATED

from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator

from .coshh_template import verify_generated_coshh_document

ExportKind = Literal["cv_dossier", "cv_form", "cv_pdf", "coshh", "coshh_pdf"]
PATTERNS = {
    "cv_dossier": "*Assessment Dossier - DRAFT.docx",
    "cv_form": "*F01 V02 - DRAFT.docx",
    "cv_pdf": "*Assessment Dossier - DRAFT.pdf",
    "coshh": "*COSHH Assessment - DRAFT.docx",
    "coshh_pdf": "*COSHH Assessment - DRAFT.pdf",
}
CV_COMPLETED = {"READY_FOR_REVIEW", "PDE_REQUIRED", "PDE_RECOMMENDED", "EVIDENCE_GAP"}
COSHH_COMPLETED = {"READY_FOR_REVIEW", "REVIEW_REQUIRED"}


class ExportSelection(BaseModel):
    material_id: int = Field(ge=1)
    kinds: list[ExportKind] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def unique_kinds(self):
        if len(self.kinds) != len(set(self.kinds)):
            raise ValueError("Each document type must be selected only once per material")
        return self


class BulkExportRequest(BaseModel):
    entries: list[ExportSelection] = Field(min_length=1, max_length=250)

    @model_validator(mode="after")
    def unique_materials(self):
        ids = [entry.material_id for entry in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("Each material may appear only once in the export request")
        if sum(len(entry.kinds) for entry in self.entries) > 500:
            raise ValueError("Export a maximum of 500 documents at once")
        return self


@dataclass(frozen=True)
class ExportFile:
    material_id: int
    kind: ExportKind
    source: Path
    relative_path: str

    def public(self) -> dict:
        return {
            "material_id": self.material_id,
            "kind": self.kind,
            "relative_path": self.relative_path,
            "url": f"/api/download/{self.material_id}/{self.kind}",
            "size_bytes": self.source.stat().st_size,
        }


def _safe_segment(text: str) -> str:
    # Avoid directory traversal and file-system reserved characters on Windows.
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", text)
    safe = re.sub(r"\s+", " ", safe).strip(" .")
    return safe[:72] or "Material"


def resolve_export(request: BulkExportRequest, queue, settings) -> list[ExportFile]:
    root = settings.output_dir.resolve()
    result: list[ExportFile] = []
    for entry in request.entries:
        row = queue.get_row(entry.material_id)
        if row is None or not row["output_dir"]:
            raise HTTPException(409, f"Assessment #{entry.material_id} has no completed outputs")
        output_dir = Path(row["output_dir"]).resolve()
        if not output_dir.is_relative_to(root):
            raise HTTPException(403, f"Assessment #{entry.material_id} output path is not authorised")
        folder = f"{entry.material_id:04d} - {_safe_segment(row['material_name'])}"
        for kind in entry.kinds:
            if kind.startswith("cv_") and row["cleaning_status"] not in CV_COMPLETED:
                raise HTTPException(409, f"Assessment #{entry.material_id}: Cleaning Validation is not completed")
            if kind.startswith("coshh") and row["coshh_status"] not in COSHH_COMPLETED:
                raise HTTPException(409, f"Assessment #{entry.material_id}: COSHH is not completed")
            matches = sorted(output_dir.glob(PATTERNS[kind]))
            if len(matches) != 1 or not matches[0].is_file():
                raise HTTPException(409, f"Assessment #{entry.material_id}: {kind} is missing or ambiguous")
            path = matches[0].resolve()
            if not path.is_relative_to(output_dir):
                raise HTTPException(403, f"Assessment #{entry.material_id}: invalid output location")
            if kind.startswith("coshh"):
                # Match /api/download's provenance gate so directory saving
                # can't pass preflight and then fail on each individual GET.
                status_path = output_dir / "COSHH_STATUS.json"
                try:
                    status_record = json.loads(status_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    status_record = {}
                if status_record.get("template_verified") is not True:
                    raise HTTPException(
                        409, f"Assessment #{entry.material_id}: COSHH has no "
                        "completed controlled-template verification. Refresh "
                        "the form with no AI before exporting."
                    )
                docx = sorted(output_dir.glob(PATTERNS["coshh"]))
                if len(docx) != 1:
                    raise HTTPException(409, f"Assessment #{entry.material_id}: COSHH DOCX is missing")
                try:
                    verify_generated_coshh_document(docx[0], settings.coshh_template_path)
                except Exception as exc:
                    raise HTTPException(
                        409, f"Assessment #{entry.material_id}: outdated or invalid COSHH form. "
                        "Select 'Update and download COSHH (no AI)' on that assessment "
                        f"before exporting. Details: {exc}"
                    ) from exc
            result.append(ExportFile(entry.material_id, kind, path, f"{folder}/{_safe_segment(path.name)}"))
    return result


def write_export_zip(files: list[ExportFile]) -> Path:
    """Create an ordinary ZIP for non-Chromium browsers/portable delivery."""
    with tempfile.NamedTemporaryFile(prefix="coshh-cv-export-", suffix=".zip", delete=False) as tmp:
        destination = Path(tmp.name)
    try:
        with ZipFile(destination, "w", ZIP_DEFLATED, compresslevel=5) as archive:
            for file in files:
                archive.write(file.source, arcname=file.relative_path)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return destination
