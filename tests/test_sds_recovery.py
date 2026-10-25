from pathlib import Path
from types import SimpleNamespace

import fitz
import httpx
import pytest

from agent.coshh_document import build_coshh_docx
from agent.coshh_template import validate_coshh_template
from agent.prompts import coshh_rescue_prompt
from agent.sds import SDSStore


def _sds_pdf(title="Safety Data Sheet - Miconazole nitrate CAS 22832-87-7"):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((60, 60), title)
    data = doc.tobytes()
    doc.close()
    return data


def _research(primary, secondary=""):
    first = SimpleNamespace(
        url=primary, substance_name="Miconazole nitrate", cas_number="22832-87-7",
        manufacturer="Test supplier", product_name="Miconazole nitrate",
        product_number="", revision_date="", match_status="REFERENCE_SDS",
        match_rationale="", is_supplier_specific=False,
        source=SimpleNamespace(url=primary),
    )
    sources = [SimpleNamespace(url=secondary, title="Alternative safety data sheet")] if secondary else []
    return SimpleNamespace(coshh_substance_name="Miconazole nitrate", sds=first, sources=sources)


def test_downloader_tries_second_source_and_embedded_pdf(tmp_path, monkeypatch):
    pdf = _sds_pdf()
    def handler(request):
        if request.url.path == "/blocked":
            return httpx.Response(403)
        if request.url.path == "/product":
            return httpx.Response(200, text='<iframe src="/sds.pdf"></iframe>')
        if request.url.path == "/sds.pdf":
            return httpx.Response(200, content=pdf, headers={"content-type": "application/pdf"})
        return httpx.Response(404)

    real_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    result = SDSStore().acquire(_research("https://sds.example/blocked", "https://sds.example/product"), tmp_path)
    assert result.status == "STORED_UNCHANGED"
    assert Path(result.local_path).read_bytes() == pdf
    assert len(result.attempts) >= 2
    assert result.attempts[0]["result"] == "HTTPStatusError"
    assert result.resolved_pdf_url.endswith("/sds.pdf")
    assert (tmp_path / "sds" / "SDS_METADATA.json").exists()


def test_downloader_rejects_unrelated_pdf(tmp_path, monkeypatch):
    unrelated = _sds_pdf("Safety Data Sheet - Unrelated chemical CAS 64-17-5")
    real_client = httpx.Client
    monkeypatch.setattr(
        httpx, "Client",
        lambda **kw: real_client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=unrelated)), **kw),
    )
    result = SDSStore().acquire(_research("https://sds.example/wrong.pdf"), tmp_path)
    assert result.status == "NOT_AVAILABLE"
    assert any("did not match" in row["result"] for row in result.attempts)


def test_missing_source_does_not_create_fake_sds(tmp_path):
    result = SDSStore().acquire(_research(""), tmp_path)
    assert result.status == "NOT_AVAILABLE"
    assert not list((tmp_path / "sds").glob("*.pdf"))


def test_coshh_cannot_generate_old_programmatic_form():
    with pytest.raises(ValueError, match="old programmatic COSHH form is disabled"):
        build_coshh_docx(None, None, None, Path("not-created.docx"))


def test_controlled_coshh_template_detects_wrong_file(tmp_path):
    template = Path(__file__).resolve().parents[1] / "templates" / "ES.SOP.089.F01.V01 - COSHH Assessment.docx"
    validate_coshh_template(template)
    with pytest.raises(Exception):
        validate_coshh_template(tmp_path / "absent.docx")


def test_sds_rescue_prompt_avoids_previously_failed_urls():
    prompt = coshh_rescue_prompt(
        material_name="Miconazole nitrate", chemical_identity="Miconazole nitrate",
        active_moiety="Miconazole", synonyms=[], process_material_description="Powder",
        product_context="Weighing", expected_cas="22832-87-7",
        excluded_urls=["https://example.org/failed-sds"], lane="distributor",
    )
    assert "NEW, independent web search" in prompt
    assert "https://example.org/failed-sds" in prompt
    assert "different" in prompt.lower()
