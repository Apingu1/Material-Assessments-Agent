"""Offline coverage for filtering/exporting CV and controlled COSHH documents.

No researcher, AI service, external SDS service or browser automation required.
"""
from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile, ZIP_DEFLATED

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from lxml import etree
from pydantic import ValidationError

from agent import web
from agent.bulk_export import (
    BulkExportRequest,
    resolve_export,
    write_export_zip,
)
from agent.models import MaterialInput
from agent.queue import MaterialQueue


TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "templates/ES.SOP.089.F01.V01 - COSHH Assessment.docx"
)


def _fixture(tmp_path, monkeypatch):
    root = tmp_path / "outputs"
    root.mkdir()
    queue = MaterialQueue(tmp_path / "data/agent.db")
    settings = SimpleNamespace(
        database_path=queue.db_path,
        output_dir=root,
        coshh_template_path=TEMPLATE,
    )
    monkeypatch.setattr(web, "_settings", lambda: settings)
    item_id = queue.add(MaterialInput(material_name="Dihydrocodeine Powder"))
    output_dir = root / "Dihydrocodeine" / "run-01"
    output_dir.mkdir(parents=True)
    cv = output_dir / "Dihydrocodeine - Assessment Dossier - DRAFT.docx"
    cv.write_bytes(b"Saved CV dossier bytes")
    cv_form = output_dir / "Dihydrocodeine - F01 V02 - DRAFT.docx"
    cv_form.write_bytes(b"Saved CV screening form bytes")
    coshh = output_dir / "Dihydrocodeine - COSHH Assessment - DRAFT.docx"
    coshh.write_bytes(TEMPLATE.read_bytes())  # Exact approved layout.
    # Single-file and bulk downloads must both honour the stored verification
    # flag; the fixture represents a *completed* previously verified run.
    import json
    (output_dir / "COSHH_STATUS.json").write_text(json.dumps({
        "status": "REVIEW_REQUIRED",
        "sds_status": "STORED_UNCHANGED",
        "template_verified": True,
    }), encoding="utf-8")
    queue.update(
        item_id,
        "PDE_REQUIRED",
        str(output_dir),
        cleaning_status="PDE_REQUIRED",
        coshh_status="REVIEW_REQUIRED",
    )
    return queue, settings, item_id, output_dir, cv, coshh


def test_export_per_material_cv_dossier_and_coshh_docx_with_original_names(tmp_path, monkeypatch):
    queue, settings, id, folder, cv, coshh = _fixture(tmp_path, monkeypatch)
    selection = BulkExportRequest(
        entries=[{"material_id": id, "kinds": ["cv_dossier", "coshh"]}]
    )
    files = resolve_export(selection, queue, settings)
    assert [file.kind for file in files] == ["cv_dossier", "coshh"]
    assert files[0].relative_path.startswith(f"{id:04d} - Dihydrocodeine Powder/")
    assert files[0].source == cv
    assert files[1].source == coshh
    archive = write_export_zip(files)
    try:
        with ZipFile(archive) as zipped:
            assert len(zipped.namelist()) == 2
            assert zipped.read(files[0].relative_path) == cv.read_bytes()
            assert zipped.read(files[1].relative_path) == coshh.read_bytes()
    finally:
        archive.unlink(missing_ok=True)


def test_prepare_and_zip_endpoints_return_real_saved_files(tmp_path, monkeypatch):
    queue, settings, id, folder, cv, coshh = _fixture(tmp_path, monkeypatch)
    client = TestClient(web.app)
    request = {"entries": [{"material_id": id, "kinds": ["cv_dossier", "coshh"]}]}
    plan = client.post("/api/bulk-export/prepare", json=request)
    assert plan.status_code == 200, plan.text
    files = plan.json()["files"]
    assert len(files) == 2
    assert files[0]["url"].endswith(f"/{id}/cv_dossier")
    assert files[1]["url"].endswith(f"/{id}/coshh")
    assert all(x["size_bytes"] > 0 for x in files)
    for item in files:
        response = client.get(item["url"])
        assert response.status_code == 200
    response = client.post("/api/bulk-export/zip", json=request)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    with ZipFile(io.BytesIO(response.content)) as archive:
        assert sorted(archive.namelist()) == sorted(x["relative_path"] for x in files)


def test_queue_reports_cv_and_verified_coshh_availability(tmp_path, monkeypatch):
    queue, settings, id, folder, cv, coshh = _fixture(tmp_path, monkeypatch)
    rows = web.queue_rows()
    assert len(rows) == 1
    assert rows[0]["cv_dossier_available"]
    assert rows[0]["cv_form_available"]
    assert rows[0]["coshh_docx_available"]
    assert not rows[0]["cv_pdf_available"]
    assert not rows[0]["coshh_pdf_available"]


def test_old_coshh_form_rejected_by_bulk_without_blocking_cv(tmp_path, monkeypatch):
    queue, settings, id, folder, cv, coshh = _fixture(tmp_path, monkeypatch)
    with ZipFile(coshh) as source:
        payload = {name: source.read(name) for name in source.namelist()}
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    root = etree.fromstring(payload["word/document.xml"])
    tags = root.xpath('.//w:sdt/w:sdtPr/w:tag[@w:val="DER_FIRE_NA"]', namespaces=ns)
    assert len(tags) == 1
    tags[0].set("{"+ns["w"]+"}val", "USR_MATERIAL_CODE")
    payload["word/document.xml"] = etree.tostring(root, encoding="UTF-8")
    with ZipFile(coshh, "w", ZIP_DEFLATED) as dest:
        for name, content in payload.items():
            dest.writestr(name, content)
    request = BulkExportRequest(entries=[{"material_id": id, "kinds": ["cv_dossier", "coshh"]}])
    with pytest.raises(HTTPException, match="outdated or invalid COSHH"):
        resolve_export(request, queue, settings)
    assert [x.kind for x in resolve_export(
        BulkExportRequest(entries=[{"material_id": id, "kinds": ["cv_dossier"]}]),
        queue, settings
    )] == ["cv_dossier"]
    assert web.queue_rows()[0]["coshh_docx_available"] is False


def test_bulk_export_does_not_serve_failed_or_pending_materials(tmp_path, monkeypatch):
    queue, settings, id, folder, cv, coshh = _fixture(tmp_path, monkeypatch)
    queue.update(id, "PENDING", str(folder), cleaning_status="PENDING", coshh_status="FAILED")
    selection = BulkExportRequest(entries=[{"material_id": id, "kinds": ["cv_dossier"]}])
    with pytest.raises(HTTPException, match="Cleaning Validation is not completed"):
        resolve_export(selection, queue, settings)
    selection = BulkExportRequest(entries=[{"material_id": id, "kinds": ["coshh"]}])
    with pytest.raises(HTTPException, match="COSHH is not completed"):
        resolve_export(selection, queue, settings)


def test_bulk_export_disallows_output_paths_outside_configured_root(tmp_path, monkeypatch):
    queue, settings, id, folder, cv, coshh = _fixture(tmp_path, monkeypatch)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / cv.name).write_bytes(b"off-root")
    queue.update(id, "PDE_REQUIRED", str(outside), cleaning_status="PDE_REQUIRED")
    selection = BulkExportRequest(entries=[{"material_id": id, "kinds": ["cv_dossier"]}])
    with pytest.raises(HTTPException) as exc:
        resolve_export(selection, queue, settings)
    assert exc.value.status_code == 403


def test_duplicate_selection_is_rejected_before_file_access():
    with pytest.raises(ValidationError):
        BulkExportRequest(entries=[
            {"material_id": 1, "kinds": ["coshh", "coshh"]},
        ])
    with pytest.raises(ValidationError):
        BulkExportRequest(entries=[
            {"material_id": 1, "kinds": ["cv_dossier"]},
            {"material_id": 1, "kinds": ["coshh"]},
        ])


def test_html_contains_filter_and_folder_zip_controls():
    assert 'id="queue-filter"' in web.HTML
    for value in (
        "cv_completed", "cv_review", "pde_required", "coshh_completed",
        "failed", "pending", "running",
    ):
        assert f'value="{value}"' in web.HTML
    assert "Save All / Export" in web.HTML
    assert "showDirectoryPicker" in web.HTML
    assert "/api/bulk-export/zip" in web.HTML
    assert "/api/bulk-export/prepare" in web.HTML
    assert "Select all COSHH Word" in web.HTML


def test_bulk_export_honours_coshh_verification_flag(tmp_path, monkeypatch):
    import json
    queue, settings, id, folder, cv, coshh = _fixture(tmp_path, monkeypatch)
    (folder / "COSHH_STATUS.json").write_text(json.dumps({
        "status": "REVIEW_REQUIRED", "template_verified": False
    }), encoding="utf-8")
    selection = BulkExportRequest(entries=[{
        "material_id": id, "kinds": ["cv_dossier", "coshh"]
    }])
    with pytest.raises(HTTPException, match="no completed controlled-template verification"):
        resolve_export(selection, queue, settings)
    assert len(resolve_export(
        BulkExportRequest(entries=[{"material_id": id, "kinds": ["cv_dossier"]}]),
        queue, settings,
    )) == 1



def _add_original_sds(folder):
    """Store a real original PDF plus integrity/provenance metadata."""
    import hashlib
    import json
    import fitz
    doc = fitz.open()
    doc.new_page().insert_text((48, 55), "Safety Data Sheet - Dihydrocodeine")
    payload = doc.tobytes()
    doc.close()
    sdspath = folder / "sds"
    sdspath.mkdir(exist_ok=True)
    original = sdspath / "Dihydrocodeine - Safety Data Sheet.pdf"
    original.write_bytes(payload)
    (sdspath / "SDS_METADATA.json").write_text(json.dumps({
        "status": "STORED_UNCHANGED",
        "sha256": hashlib.sha256(payload).hexdigest(),
    }), encoding="utf-8")
    return original


def test_save_all_includes_original_sds_with_word_assessments(tmp_path, monkeypatch):
    queue, settings, material_id, folder, dossier, coshh = _fixture(tmp_path, monkeypatch)
    sds = _add_original_sds(folder)
    assert web.queue_rows()[0]["sds_available"] is True
    selection = {
        "entries": [{
            "material_id": material_id, "kinds": ["cv_dossier", "coshh", "sds"]
        }]
    }
    client = TestClient(web.app)
    response = client.post("/api/bulk-export/prepare", json=selection)
    assert response.status_code == 200, response.text
    plan = response.json()["files"]
    assert [x["kind"] for x in plan] == ["cv_dossier", "coshh", "sds"]
    assert plan[2]["relative_path"].endswith(sds.name)
    assert plan[2]["url"] == f"/api/download/{material_id}/sds"
    direct = client.get(plan[2]["url"])
    assert direct.status_code == 200
    assert direct.content == sds.read_bytes()
    response = client.post("/api/bulk-export/zip", json=selection)
    assert response.status_code == 200
    with ZipFile(io.BytesIO(response.content)) as zipped:
        assert len(zipped.namelist()) == 3
        assert zipped.read(plan[2]["relative_path"]) == sds.read_bytes()


def test_original_sds_can_export_even_if_coshh_form_failed(tmp_path, monkeypatch):
    queue, settings, material_id, folder, dossier, coshh = _fixture(tmp_path, monkeypatch)
    sds = _add_original_sds(folder)
    queue.update(material_id, "PDE_REQUIRED", str(folder),
                 cleaning_status="PDE_REQUIRED", coshh_status="FAILED")
    (folder / "COSHH_STATUS.json").write_text(__import__("json").dumps({
        "status": "FAILED", "sds_status": "STORED_UNCHANGED",
        "template_verified": False,
    }))
    assert web.queue_rows()[0]["sds_available"] is True
    files = resolve_export(
        BulkExportRequest(entries=[{"material_id": material_id, "kinds": ["sds"]}]),
        queue, settings
    )
    assert len(files) == 1 and files[0].source == sds
    with pytest.raises(HTTPException, match="COSHH is not completed"):
        resolve_export(
            BulkExportRequest(entries=[{"material_id": material_id, "kinds": ["coshh"]}]),
            queue, settings
        )


def test_bulk_sds_export_rejects_modified_or_unverified_pdf(tmp_path, monkeypatch):
    import json
    queue, settings, material_id, folder, dossier, coshh = _fixture(tmp_path, monkeypatch)
    sds = _add_original_sds(folder)
    selection = BulkExportRequest(entries=[
        {"material_id": material_id, "kinds": ["sds"]}
    ])
    sds.write_bytes(sds.read_bytes() + b"tampered")
    with pytest.raises(HTTPException, match="SHA-256"):
        resolve_export(selection, queue, settings)
    sds.write_bytes(b"%PDF-not-a-real-sds")
    with pytest.raises(HTTPException, match="SHA-256"):
        resolve_export(selection, queue, settings)
    (folder / "sds" / "SDS_METADATA.json").write_text(json.dumps({
        "status": "NOT_AVAILABLE", "sha256": "0"*64,
    }))
    with pytest.raises(HTTPException, match="no confirmed stored-original checksum"):
        resolve_export(selection, queue, settings)


def test_bulk_export_rejects_generated_pdf_options(tmp_path, monkeypatch):
    queue, settings, material_id, folder, dossier, coshh = _fixture(tmp_path, monkeypatch)
    for kind in ("cv_pdf", "coshh_pdf"):
        with pytest.raises(ValidationError):
            BulkExportRequest(entries=[{"material_id": material_id, "kinds": [kind]}])


def test_save_all_dialog_shows_sds_and_no_generated_pdf_options():
    text = web.HTML
    assert "['sds','Original SDS (PDF)','sds_available',true]" in text
    assert "Select all SDS" in text
    assert "['cv_pdf','CV dossier (PDF)'" not in text
    assert "['coshh_pdf','COSHH form (PDF)'" not in text
