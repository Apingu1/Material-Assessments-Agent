from pathlib import Path

from docx import Document
from lxml import etree
from zipfile import ZipFile

from agent.coshh_document import build_coshh_docx
from agent.coshh_rules import build_coshh_assessment
from agent.coshh_template import build_coshh_template_values, verify_generated_coshh_document
from agent.models import (
    COSHHArea,
    COSHHResearch,
    EvidenceApplicability,
    EvidenceSource,
    GHSCode,
    MaterialInput,
    SDSResearch,
    SourceType,
)
from agent.sds import StoredSDS


def _research():
    src = EvidenceSource(
        title="Example Safety Data Sheet",
        publisher="Example Manufacturer",
        url="https://example.com/sds.pdf",
        tier=2,
        source_type=SourceType.MANUFACTURER,
        relevant_extract="H302 Harmful if swallowed. H317 May cause an allergic skin reaction.",
        interpretation="The SDS identifies acute oral toxicity and skin sensitisation.",
        applicability=[EvidenceApplicability.CHEMICAL_SPECIES],
    )
    return COSHHResearch(
        coshh_substance_name="Miconazole nitrate",
        material_use_context="Miconazole nitrate raw material",
        sds=SDSResearch(
            substance_name="Miconazole nitrate",
            cas_number="22832-87-7",
            synonyms=[],
            manufacturer="Example Manufacturer",
            product_name="Miconazole nitrate",
            product_number="M123",
            revision_date="01 Jan 2026",
            url=src.url,
            is_supplier_specific=False,
            match_status="REFERENCE_SDS",
            match_rationale="Exact substance reference SDS.",
            source=src,
        ),
        physical_form="powder",
        colour="white",
        odour="not stated",
        signal_word="WARNING",
        pictograms=[GHSCode.GHS07, GHSCode.GHS08],
        hazard_statements=["H302 - Harmful if swallowed", "H317 - May cause an allergic skin reaction"],
        relevant_health_effects=["Harmful if swallowed", "May cause an allergic skin reaction"],
        precautionary_statements=[],
        inhalation_hazard=False,
        skin_hazard=True,
        eye_hazard=False,
        ingestion_hazard=True,
        first_aid_inhalation="Move to fresh air.",
        first_aid_skin="Wash with soap and water.",
        first_aid_eye="Rinse with water.",
        first_aid_ingestion="Rinse mouth and seek medical advice.",
        spill_response="Avoid dust and collect into a suitable container.",
        storage_handling="Keep container tightly closed in a dry place.",
        firefighting_media="Use media suitable for surrounding fire.",
        environmental_precautions="Avoid release to drains.",
        disposal="Dispose through the approved waste route.",
        workplace_exposure_limit_found=False,
        workplace_exposure_limit="No GB WEL identified",
        health_surveillance_considered=True,
        health_surveillance_recommended=True,
        health_surveillance_rationale="Skin sensitisation should be reviewed.",
        core_controls=["Avoid dust formation", "Avoid unnecessary skin contact", "Keep container closed"],
        review_note="",
        sources=[src],
    )


def test_coshh_document_is_generated_with_blank_human_approval(tmp_path: Path):
    item = MaterialInput(
        material_name="Miconazole nitrate",
        coshh_areas=[COSHHArea.GOODS_IN_WAREHOUSE, COSHHArea.SAMPLING, COSHHArea.QC, COSHHArea.PRODUCTION],
        existing_controls="dispensing booth / local extraction",
        typical_quantity="10 g",
    )
    assessment = build_coshh_assessment(item, _research())
    stored = StoredSDS(
        status="STORED_UNCHANGED",
        original_url="https://example.com/sds.pdf",
        resolved_pdf_url="https://example.com/sds.pdf",
        local_path=str(tmp_path / "sds.pdf"),
        sha256="abc123",
        note="Stored unchanged",
    )
    out = tmp_path / "coshh.docx"
    template = Path(__file__).resolve().parents[1] / "templates" / "ES.SOP.089.F01.V01 - COSHH Assessment.docx"
    build_coshh_docx(assessment, item, stored, out, template_path=template)
    assert out.exists()
    verification = verify_generated_coshh_document(out, template)
    assert len(verification["template_sha256"]) == 64
    assert len(verification["output_docx_sha256"]) == 64

    values = build_coshh_template_values(assessment, item, stored)
    assert values["DER_PPE_QC_FUME_HOOD"] is True
    assert values["DER_PPE_QC_FULL_FACE_RESPIRATOR"] is False
    assert values["DER_PPE_PRODUCTION_FULL_FACE_RESPIRATOR"] is True
    assert values["HUM_ASSESSED_NAME_POSITION"] == ""
    assert values["HUM_REVIEWED_SIGNATURE"] == ""
    assert values["HUM_APPROVED_DATE"] == ""
    with ZipFile(out, "r") as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    tagged = {}
    for sdt in root.xpath(".//w:sdt", namespaces=ns):
        tags = sdt.xpath("./w:sdtPr/w:tag/@w:val", namespaces=ns)
        if tags:
            tagged[tags[0]] = "".join(sdt.xpath(".//w:sdtContent//w:t/text()", namespaces=ns))

    assert len(tagged) == 134
    assert set(values) == set(tagged), "Every controlled content-control tag must be mapped exactly once"
    assert tagged["RES_SUBSTANCE_PRODUCT"] == "Miconazole nitrate"
    assert "H302" in tagged["SDS_HAZARD_STATEMENTS"]
    assert "Harmful if swallowed" in tagged["SDS_RELEVANT_HEALTH_EFFECTS"]
    for tag in (
        "HUM_ASSESSED_NAME_POSITION", "HUM_ASSESSED_SIGNATURE", "HUM_ASSESSED_DATE",
        "HUM_REVIEWED_NAME_POSITION", "HUM_REVIEWED_SIGNATURE", "HUM_REVIEWED_DATE",
        "HUM_APPROVED_NAME_POSITION", "HUM_APPROVED_SIGNATURE", "HUM_APPROVED_DATE",
    ):
        assert tagged[tag] == ""

    doc = Document(out)
    body_text = "\\n".join(p.text for p in doc.paragraphs)
    for table in doc.tables:
        for row in table.rows:
            body_text += "\\n" + " | ".join(cell.text for cell in row.cells)
    header_text = "\\n".join(
        cell.text for section in doc.sections for table in section.header.tables
        for row in table.rows for cell in row.cells
    )
    assert "COSHH ASSESSMENT" in header_text.upper()
    assert "ES.SOP.089.F01.V01" in header_text
    assert "Departmental Personal Protective Equipment" in body_text
    assert "Reviewed by" in body_text
    assert "Approved by" in body_text
    assert "AGENT-GENERATED DRAFT" not in body_text



def test_coshh_only_rebuild_populates_exact_controlled_template_offline(tmp_path, monkeypatch):
    """End-to-end render using a saved SDS and cached research; no OpenAI call."""
    from types import SimpleNamespace
    import fitz
    from agent import coshh_recovery

    material = MaterialInput(
        material_name="Miconazole nitrate Powder", dosage_forms="Tablets", routes="Oral",
        coshh_areas=[COSHHArea.QC, COSHHArea.PRODUCTION],
    )
    cached = SimpleNamespace(
        material_input=material,
        identity=SimpleNamespace(
            chemical_identity="Miconazole nitrate",
            active_moiety="Miconazole",
        ),
        coshh=_research(),
        model_dump_json=lambda indent=2: '{"recovered": true}',
    )
    monkeypatch.setattr(coshh_recovery, "load_existing_bundle", lambda _: cached)
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((40, 50), "Safety Data Sheet - Miconazole nitrate CAS 22832-87-7")
    payload = pdf.tobytes()
    pdf.close()
    coshh_recovery.upload_sds_for_existing_run(tmp_path, payload, "original.pdf")

    class OfflineResearcher:
        def __init__(self, settings):
            pass

        def research_coshh_from_verified_pdf(self, item, identity, stored_sds, *, reference):
            assert stored_sds.sha256
            assert Path(stored_sds.local_path).read_bytes() == payload
            assert reference is True
            return _research()

    monkeypatch.setattr(coshh_recovery, "ResearchAgent", OfflineResearcher)
    settings = SimpleNamespace(
        require_runtime=lambda: None,
        coshh_template_path=Path(__file__).resolve().parents[1] / "templates" /
            "ES.SOP.089.F01.V01 - COSHH Assessment.docx",
        generate_pdf=False,
    )
    result = coshh_recovery.regenerate_coshh_only(settings, tmp_path)
    assert result["status"] == "REVIEW_REQUIRED", result
    assert result["template_verified"] is True
    assert result["sds_status"] == "STORED_UNCHANGED"
    output = next(tmp_path.glob("*COSHH Assessment - DRAFT.docx"))
    verified = verify_generated_coshh_document(output, settings.coshh_template_path)
    assert verified["template_sha256"] == result["template_sha256"]
    assert (tmp_path / "coshh_assessment.json").exists()
