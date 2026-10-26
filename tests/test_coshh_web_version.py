from pathlib import Path
from types import SimpleNamespace

from agent import web


def test_running_server_reports_controlled_template_and_no_legacy_renderer(monkeypatch):
    monkeypatch.setattr(
        web, "_settings",
        lambda: SimpleNamespace(
            coshh_template_path=Path("templates/ES.SOP.089.F01.V01 - COSHH Assessment.docx"),
            template_path=Path("ES.SOP.272.F01.V02 - Material Hazard & Cleanability Screening Assessment.docx"),
        ),
    )
    result = web.version()
    assert result["coshh_template"] == "ES.SOP.089.F01.V01 - COSHH Assessment.docx"
    assert result["coshh_template_fields"] == 134
    assert result["legacy_coshh_renderer"] is False
    assert result["loaded_engine_build"] == web.COSHH_ENGINE_BUILD
    assert result["coshh_template_path"].endswith("/templates/ES.SOP.089.F01.V01 - COSHH Assessment.docx") or result["coshh_template_path"].startswith("templates/")



def test_old_unverified_coshh_download_is_blocked(tmp_path, monkeypatch):
    from fastapi import HTTPException
    import pytest
    monkeypatch.setattr(web, "_output_dir", lambda _: tmp_path)
    monkeypatch.setattr(web, "_coshh_payload", lambda _: {"template_verified": False})
    with pytest.raises(HTTPException) as exc:
        web.download(100, "coshh")
    assert exc.value.status_code == 409
    assert "unverified" in exc.value.detail


def test_legacy_coshh_status_without_stage_keeps_full_queue_visible(tmp_path, monkeypatch):
    """Regression for real Codespaces KeyError: stage in /api/queue."""
    import json
    from agent.models import MaterialInput
    from agent.queue import MaterialQueue
    db = tmp_path / "data" / "agent.db"
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    queue = MaterialQueue(db)
    before = queue.add(MaterialInput(material_name="Previous cleaning generation"))
    current = queue.add(MaterialInput(material_name="Levomepromazine Maleate Powder"))
    prevdir = outputs / "previous"
    prevdir.mkdir()
    # A historic assessment created before 'stage' metadata was introduced.
    (prevdir / "COSHH_STATUS.json").write_text(
        json.dumps({"status": "REVIEW_REQUIRED", "template_verified": True,
                    "sds_status": "NOT_AVAILABLE"}), encoding="utf-8",
    )
    queue.update(before, "READY_FOR_REVIEW", str(prevdir),
                 cleaning_status="READY_FOR_REVIEW", coshh_status="REVIEW_REQUIRED")
    queue.update(current, "RESEARCHING", None,
                 cleaning_status="RESEARCHING", coshh_status="RESEARCHING")
    settings = SimpleNamespace(database_path=db)
    monkeypatch.setattr(web, "_settings", lambda: settings)
    records = web.queue_rows()
    assert [x["id"] for x in records] == [current, before]
    assert records[0]["material_name"] == "Levomepromazine Maleate Powder"
    assert records[0]["status"] == "RESEARCHING"
    assert records[1]["coshh_stage"] == ""
    assert records[1]["sds_attempt_count"] == 0
    assert records[1]["coshh_status"] == "REVIEW_REQUIRED"
    assert len(queue.list_rows()) == 2  # Must not alter or delete queue records.


def test_legacy_and_invalid_status_always_have_all_consumer_keys(tmp_path):
    import json
    old = tmp_path / "COSHH_STATUS.json"
    for payload in [
        {"status": "FAILED"},
        {"status": "REVIEW_REQUIRED", "sds_status": "STORED_UNCHANGED"},
        {"status": "FAILED", "sds_attempt_count": "not-an-integer"},
        [],
        "invalid",
    ]:
        old.write_text(json.dumps(payload), encoding="utf-8")
        result = web._coshh_payload(tmp_path)
        for key in ("status", "stage", "error", "template", "template_verified",
                    "sds_status", "sds_attempt_count"):
            assert key in result, (payload, key)
        assert isinstance(result["sds_attempt_count"], int)
    old.write_text("{invalid-json", encoding="utf-8")
    assert web._coshh_payload(tmp_path)["stage"] == ""
    old.unlink()
    assert web._coshh_payload(tmp_path)["sds_status"] == "NOT_AVAILABLE"


def test_old_master_has_same_tag_count_but_different_mapping(tmp_path):
    """Regression for Dihydrocodeine /api/download: count 134 is insufficient."""
    import zipfile
    from lxml import etree
    import pytest
    from agent.coshh_template import verify_generated_coshh_document
    template = Path(__file__).resolve().parents[1] / "templates" / "ES.SOP.089.F01.V01 - COSHH Assessment.docx"
    document = tmp_path / "Dihydrocodeine - COSHH Assessment - DRAFT.docx"
    with zipfile.ZipFile(template) as source:
        payload = {item.filename: source.read(item.filename) for item in source.infolist()}
    root = etree.fromstring(payload["word/document.xml"])
    ns = {"w":"http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    tags = root.xpath('.//w:sdt/w:sdtPr/w:tag[@w:val="DER_FIRE_NA"]',namespaces=ns)
    assert len(tags)==1
    tags[0].set("{"+ns["w"]+"}val","USR_MATERIAL_CODE")
    payload["word/document.xml"] = etree.tostring(root,encoding="UTF-8",xml_declaration=True,standalone=True)
    with zipfile.ZipFile(document,"w",zipfile.ZIP_DEFLATED) as destination:
        for name,content in payload.items():destination.writestr(name,content)
    with pytest.raises(ValueError,match="DER_FIRE_NA") as exc:
        verify_generated_coshh_document(document,template)
    assert "USR_MATERIAL_CODE" in str(exc.value)
    valid,reason=web._coshh_docx_current(tmp_path,template)
    assert valid is False
    assert "Update and download COSHH" in reason


def test_queue_marks_old_finished_form_needing_no_ai_refresh(tmp_path,monkeypatch):
    import json
    from agent.models import MaterialInput
    from agent.queue import MaterialQueue
    queue=MaterialQueue(tmp_path/"data"/"agent.db")
    output=tmp_path/"outputs"/"old-material"/"run-1"
    output.mkdir(parents=True)
    # Complete historic research was retained, but the master Word file is
    # missing or from the prior 134-field mapping.
    (output/"COSHH_STATUS.json").write_text(json.dumps({
        "status":"REVIEW_REQUIRED","template_verified":True,
        "sds_status":"STORED_UNCHANGED"
    }))
    material=queue.add(MaterialInput(material_name="Dihydrocodeine"))
    queue.update(material,"READY_FOR_REVIEW",str(output),
                 cleaning_status="READY_FOR_REVIEW",coshh_status="REVIEW_REQUIRED")
    master=Path(__file__).resolve().parents[1]/"templates"/"ES.SOP.089.F01.V01 - COSHH Assessment.docx"
    monkeypatch.setattr(web,"_settings",lambda:SimpleNamespace(database_path=queue.db_path,coshh_template_path=master))
    rows=web.queue_rows()
    assert len(rows)==1
    assert rows[0]["coshh_template_verified"] is False
    assert rows[0]["coshh_refresh_needed"] is True
    assert "Word file" in rows[0]["coshh_template_reason"]


def test_download_reports_actionable_mismatch_instead_of_generic_134(tmp_path,monkeypatch):
    from fastapi import HTTPException
    import json,pytest
    document=tmp_path/"Dihydrocodeine - COSHH Assessment - DRAFT.docx"
    document.write_bytes(b"older docx placeholder")
    (tmp_path/"COSHH_STATUS.json").write_text(json.dumps({
        "status":"REVIEW_REQUIRED","template_verified":True
    }))
    master=Path(__file__).resolve().parents[1]/"templates"/"ES.SOP.089.F01.V01 - COSHH Assessment.docx"
    monkeypatch.setattr(web,"_output_dir",lambda _:tmp_path)
    monkeypatch.setattr(web,"_settings",lambda:SimpleNamespace(coshh_template_path=master))
    with pytest.raises(HTTPException) as exc:
        web.download(18,"coshh")
    assert exc.value.status_code==409
    assert "earlier master" in exc.value.detail


def test_refresh_error_explained_in_browser_ui():
    assert "window.alert(detail)" in web.HTML
    assert "No additional AI run was started." in web.HTML
    assert "Unable to update COSHH without AI" not in web.HTML
