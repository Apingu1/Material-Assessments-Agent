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


def test_completed_coshh_can_refresh_hazards_and_ppe_at_zero_ai_cost(tmp_path, monkeypatch):
    """Full file replacement from prior assessment without instantiating ResearchAgent."""
    from types import SimpleNamespace
    from agent import coshh_recovery
    from agent.coshh_template import verify_generated_coshh_document
    from agent.coshh_rules import build_coshh_assessment
    from agent.models import MaterialInput, COSHHArea
    from tests.test_coshh_document import _research
    import fitz, json
    from zipfile import ZipFile
    from lxml import etree

    item = MaterialInput(
        material_name="Levomepromazine Maleate Powder",
        coshh_areas=[COSHHArea.QC, COSHHArea.PRODUCTION],
    )
    research = _research()
    research.coshh_substance_name = "Levomepromazine maleate"
    research.sds.substance_name = "Levomepromazine maleate"
    research.sds.cas_number = "7104-38-3"
    research.pictograms = []
    research.hazard_statements = ["H302 - Harmful if swallowed", "H319 - Causes serious eye irritation"]
    assessment = build_coshh_assessment(item, research)
    (tmp_path / "coshh_assessment.json").write_text(assessment.model_dump_json(indent=2))
    (tmp_path / "COSHH_STATUS.json").write_text(json.dumps({
        "status": "REVIEW_REQUIRED", "sds_status": "STORED_UNCHANGED",
        "template_verified": True,
    }))
    original_docx = tmp_path / "Levomepromazine maleate - COSHH Assessment - DRAFT.docx"
    original_docx.write_bytes(b"original old style placeholder")
    doc = fitz.open()
    doc.new_page().insert_text((40,50),"Safety Data Sheet - Levomepromazine maleate 7104-38-3")
    data = doc.tobytes()
    doc.close()
    sds_dir = tmp_path / "sds"
    sds_dir.mkdir()
    (sds_dir / "Levomepromazine maleate - Safety Data Sheet.pdf").write_bytes(data)
    import hashlib
    (sds_dir / "SDS_METADATA.json").write_text(json.dumps({"sha256":hashlib.sha256(data).hexdigest()}))
    monkeypatch.setattr(
        coshh_recovery, "load_existing_bundle",
        lambda _: SimpleNamespace(
            material_input=item,
            identity=SimpleNamespace(
                chemical_identity="Levomepromazine maleate",
                active_moiety="Levomepromazine",
            ),
        ),
    )
    monkeypatch.setattr(coshh_recovery,"ResearchAgent",
        lambda *args,**kwargs: (_ for _ in ()).throw(AssertionError("No API permitted")))
    template = Path(__file__).resolve().parents[1] / "templates" / "ES.SOP.089.F01.V01 - COSHH Assessment.docx"
    settings = SimpleNamespace(
        require_runtime=lambda:None, generate_pdf=False, coshh_template_path=template,
        database_path=tmp_path / "agent.db",
    )
    outcome = coshh_recovery.refresh_existing_coshh_document(settings,tmp_path)
    assert outcome["document_refresh_ai_calls"] == 0
    assert outcome["stage"] == "CONTROLLED_FORM_REFRESHED_NO_AI"
    assert outcome["template_verified"] is True
    verify_generated_coshh_document(original_docx,template)
    with ZipFile(original_docx) as archive:
        xml=etree.fromstring(archive.read("word/document.xml"))
    ns={"w":"http://schemas.openxmlformats.org/wordprocessingml/2006/main","w14":"http://schemas.microsoft.com/office/word/2010/wordml"}
    def inspect(tag):
        sdts=xml.xpath('.//w:sdt[w:sdtPr/w:tag/@w:val="'+tag+'"]',namespaces=ns)
        assert len(sdts)==1
        return (
            sdts[0].xpath(".//w:sdtContent//w:t/text()",namespaces=ns),
            sdts[0].xpath("./w:sdtContent//w:rPr/w:sz/@w:val",namespaces=ns),
        )
    assert inspect("SDS_PICTOGRAM_GHS07")[0] == ["☒"]
    assert inspect("DER_PPE_QC_FUME_HOOD")[1] == ["40"]
    assert (tmp_path / "coshh_assessment.json").exists()



def test_no_ai_word_refresh_succeeds_without_pdf_converter(tmp_path, monkeypatch):
    """Regression for Dihydrocodeine #19 HTTP 409 from optional PDF generation."""
    from types import SimpleNamespace
    from agent import coshh_recovery
    from agent.coshh_rules import build_coshh_assessment
    from agent.models import MaterialInput
    from tests.test_coshh_document import _research
    import hashlib
    import fitz
    import json

    material=MaterialInput(material_name="Dihydrocodeine powder")
    research=_research()
    research.coshh_substance_name="Dihydrocodeine"
    research.sds.substance_name="Dihydrocodeine"
    research.hazard_statements=["H302 Harmful if swallowed"]
    assessment=build_coshh_assessment(material,research)
    (tmp_path/"coshh_assessment.json").write_text(assessment.model_dump_json(indent=2))
    (tmp_path/"COSHH_STATUS.json").write_text(json.dumps({
        "status":"REVIEW_REQUIRED","template_verified":True,"sds_status":"STORED_UNCHANGED"
    }))
    old_word=tmp_path/"Dihydrocodeine - COSHH Assessment - DRAFT.docx"
    old_word.write_bytes(b"OLD APPROVED-TEMPLATE DRAFT")
    old_pdf=old_word.with_suffix(".pdf")
    old_pdf.write_bytes(b"%PDF-old previous-version output")
    sdspath=tmp_path/"sds"
    sdspath.mkdir()
    pdf=fitz.open()
    pdf.new_page().insert_text((45,50),"Safety Data Sheet - Dihydrocodeine tartrate")
    pdfbytes=pdf.tobytes()
    pdf.close()
    (sdspath/"Dihydrocodeine - Safety Data Sheet.pdf").write_bytes(pdfbytes)
    (sdspath/"SDS_METADATA.json").write_text(json.dumps({
        "sha256":hashlib.sha256(pdfbytes).hexdigest(),
        "status":"STORED_UNCHANGED",
        "identity_match":"NAME_MATCH:dihydrocodeine"
    }))
    monkeypatch.setattr(coshh_recovery,"load_existing_bundle",lambda _:SimpleNamespace(
        material_input=material,identity=None,
    ))
    monkeypatch.setattr(coshh_recovery,"ResearchAgent",lambda *a,**k:(_ for _ in ()).throw(
        AssertionError("No AI is permitted for form-only refresh")))
    monkeypatch.setattr(coshh_recovery,"convert_docx_to_pdf",lambda *a,**k:None)
    template=Path(__file__).resolve().parents[1]/"templates"/"ES.SOP.089.F01.V01 - COSHH Assessment.docx"
    settings=SimpleNamespace(
        coshh_template_path=template,
        require_runtime=lambda:None,
        generate_pdf=True,
        database_path=tmp_path/"registry.db",
    )
    status=coshh_recovery.refresh_existing_coshh_document(settings,tmp_path)
    assert status["document_refresh_ai_calls"]==0
    assert status["template_verified"]
    assert status["coshh_pdf_current"] is False
    assert "Word refreshed" in status["coshh_pdf_warning"]
    assert old_word.read_bytes().startswith(b"PK")  # Real regenerated Word ZIP.
    from agent.coshh_template import verify_generated_coshh_document
    verify_generated_coshh_document(old_word,template)
    assert not old_pdf.exists()  # Do not offer a previous-version PDF.
    history=list((tmp_path/".coshh-superseded").glob("*"))
    assert len(history)==1
    assert (history[0]/old_word.name).read_bytes()==b"OLD APPROVED-TEMPLATE DRAFT"
    assert (history[0]/old_pdf.name).read_bytes()==b"%PDF-old previous-version output"
    assert json.loads((tmp_path/"COSHH_STATUS.json").read_text())["coshh_pdf_current"] is False


def test_no_ai_refresh_blocks_modified_sds_without_paying_for_research(tmp_path):
    from agent.coshh_recovery import _stored_sds_for_form_refresh
    import json,hashlib
    sds=tmp_path/"sds"
    sds.mkdir()
    (sds/"Original - Safety Data Sheet.pdf").write_bytes(b"%PDF-modified-source")
    (sds/"SDS_METADATA.json").write_text(json.dumps({
        "status":"STORED_UNCHANGED",
        "sha256":hashlib.sha256(b"%PDF-original-source").hexdigest(),
    }))
    import pytest
    with pytest.raises(ValueError,match="checksum"):
        _stored_sds_for_form_refresh(tmp_path)
