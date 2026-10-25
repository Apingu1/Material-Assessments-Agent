from pathlib import Path
from types import SimpleNamespace

import fitz
import httpx
import pytest

from agent.coshh_document import build_coshh_docx
from agent.coshh_template import validate_coshh_template
from agent.prompts import coshh_rescue_prompt
from agent.sds import SDSStore, _valid_sds_pdf, sds_search_names, known_authoritative_sds_urls


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


def test_levomepromazine_sds_uses_chemical_without_powder_tablet_route():
    names = sds_search_names(
        "Levomepromazine Maleate Powder",
        "Levomepromazine Maleate",
        "Levomepromazine",
    )
    assert names == ["levomepromazine maleate", "levomepromazine"]
    urls = known_authoritative_sds_urls(names)
    assert urls and urls[0].endswith("/CAT-723_GB.pdf")


def test_reject_wrong_salt_for_regulator_reference():
    assert not known_authoritative_sds_urls(
        ["levomepromazine hydrochloride", "levomepromazine"]
    )


def test_levomepromazine_pdf_accepts_powder_input_and_base_reference_name():
    data = _sds_pdf("Safety Data Sheet - Levomepromazine maleate CAS 7104-38-3")
    assert _valid_sds_pdf(
        data, "Levomepromazine Maleate Powder", "7104-38-3",
        acceptable_names=["Levomepromazine maleate", "Levomepromazine"],
    )[0]
    base_data = _sds_pdf("Safety Data Sheet - Levomepromazine")
    ok, reason = _valid_sds_pdf(
        base_data, "Levomepromazine Maleate Powder", "",
        acceptable_names=["Levomepromazine"],
    )
    assert ok and reason == "NAME_MATCH:levomepromazine"


def test_official_reference_sds_url_retrieval_is_recorded(tmp_path, monkeypatch):
    expected = known_authoritative_sds_urls(["levomepromazine maleate"])[0]
    data = _sds_pdf("Safety Data Sheet - Levomepromazine maleate CAS 7104-38-3")
    real_client = httpx.Client
    def handler(request):
        if str(request.url) == expected:
            return httpx.Response(200, content=data, headers={"content-type":"application/pdf"})
        return httpx.Response(404)
    monkeypatch.setattr(
        httpx, "Client",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )
    original = _research("")
    original.coshh_substance_name = "Levomepromazine Maleate"
    original.sds.substance_name = "Levomepromazine Maleate Powder"
    original.sds.cas_number = "7104-38-3"
    result = SDSStore().acquire(
        original, tmp_path, extra_urls=[expected],
        acceptable_names=["levomepromazine maleate","levomepromazine"],
    )
    assert result.status == "STORED_UNCHANGED"
    assert result.resolved_pdf_url == expected
    assert result.identity_match == "CAS_MATCH"
    assert Path(result.local_path).read_bytes() == data
