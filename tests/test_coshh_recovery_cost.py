"""Cost and provenance regression coverage for recovery without paid research."""
import json
from pathlib import Path
from types import SimpleNamespace

import fitz
import httpx

from agent import coshh_recovery
from agent.models import MaterialInput
from agent.sds import SDSStore


def _document(name="Safety Data Sheet - Levomepromazine maleate 7104-38-3"):
    pdf=fitz.open()
    page=pdf.new_page()
    page.insert_text((42,52),name)
    result=pdf.tobytes()
    pdf.close()
    return result


def _cached_stub():
    item=MaterialInput(material_name="Levomepromazine Maleate Powder", dosage_forms="Tablets", routes="Oral")
    identity=SimpleNamespace(
        chemical_identity="Levomepromazine Maleate",
        active_moiety="Levomepromazine",
    )
    return SimpleNamespace(material_input=item,identity=identity,coshh=None)


def test_missing_sds_coshh_only_recovery_never_calls_ai(tmp_path, monkeypatch):
    bundle=_cached_stub()
    monkeypatch.setattr(coshh_recovery, "load_existing_bundle", lambda _: bundle)
    monkeypatch.setattr(
        SDSStore, "acquire_known_reference", lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        coshh_recovery, "ResearchAgent",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("AI research must not run without SDS")),
    )
    settings=SimpleNamespace(
        require_runtime=lambda:None,
        coshh_template_path=Path("templates/ES.SOP.089.F01.V01 - COSHH Assessment.docx"),
    )
    status=coshh_recovery.regenerate_coshh_only(settings,tmp_path)
    assert status["status"]=="FAILED"
    assert status["stage"]=="SDS_PREFLIGHT"
    assert "No AI credits were used" in status["error"]
    assert json.loads((tmp_path/"COSHH_STATUS.json").read_text())["sds_status"]=="NOT_AVAILABLE"


def test_manual_upload_stores_original_sds_without_ai(tmp_path, monkeypatch):
    bundle=_cached_stub()
    monkeypatch.setattr(coshh_recovery, "load_existing_bundle", lambda _: bundle)
    document=_document()
    result=coshh_recovery.upload_sds_for_existing_run(tmp_path,document,"Supplier SDS.pdf")
    assert result.status=="STORED_UNCHANGED"
    assert Path(result.local_path).read_bytes()==document
    status=json.loads((tmp_path/"COSHH_STATUS.json").read_text())
    assert status["stage"]=="SDS_UPLOAD_AWAITING_EXTRACTION"
    assert status["template_verified"] is False
    assert status["sds_status"]=="STORED_UNCHANGED"


def test_official_reference_preflight_is_network_only(tmp_path, monkeypatch):
    pdf=_document()
    real_client=httpx.Client
    def handler(request):
        if request.url.path.endswith("/CAT-723_GB.pdf"):
            return httpx.Response(200,content=pdf,headers={"content-type":"application/pdf"})
        return httpx.Response(404)
    monkeypatch.setattr(httpx,"Client",lambda **kw:real_client(transport=httpx.MockTransport(handler),**kw))
    result=SDSStore().acquire_known_reference(
        "Levomepromazine Maleate Powder","Levomepromazine Maleate",
        "Levomepromazine",tmp_path,
    )
    assert result.status=="STORED_UNCHANGED"
    assert result.identity_match.startswith("NAME_MATCH:")
    assert Path(result.local_path).read_bytes()==pdf
