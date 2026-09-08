from pathlib import Path

from docx import Document

from agent.coshh_document import build_coshh_docx
from agent.coshh_rules import build_coshh_assessment
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
    build_coshh_docx(assessment, item, stored, out)
    assert out.exists()
    doc = Document(out)
    text = "\n".join(p.text for p in doc.paragraphs)
    for table in doc.tables:
        for row in table.rows:
            text += "\n" + " | ".join(cell.text for cell in row.cells)
    assert "COSHH ASSESSMENT" in text
    assert "Miconazole nitrate" in text
    assert "H302" in text
    assert "Reviewed by" in text
    assert "Approved by" in text
    assert "AGENT-GENERATED DRAFT" in text
