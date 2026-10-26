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
    assert values["DER_PPE_QC_HALF_FACE_RESPIRATOR"] is False
    assert values["DER_PPE_PRODUCTION_HALF_FACE_RESPIRATOR"] is True
    assert values["DER_PPE_PRODUCTION_LABCOAT_GOWNS"] is True
    assert values["DER_PPE_PRODUCTION_GLASSES_GOGGLES"] is True
    assert values["DER_PPE_PRODUCTION_OVERSHOES"] is True
    assert values["DER_PPE_PRODUCTION_SURGICAL_MASK"] is False
    assert values["DER_PPE_RND_HALF_FACE_RESPIRATOR"] is True
    assert values["DER_FIRE_NA"] is True
    assert values["USR_ASSESSMENT_VERSION"] == "1"
    assert values["HUM_NEXT_REVIEW_DATE"] != ""
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
        database_path=tmp_path / "agent.db",
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


def test_ghs07_derived_from_levomepromazine_sds_when_pdf_image_not_extracted():
    """BP Levomepromazine Maleate SDS Section 2 has GHS07 image + H codes."""
    from agent.coshh_template import _pictograms_from_sds_hazards
    from types import SimpleNamespace

    source = SimpleNamespace(
        pictograms=[],  # PDF image is invisible to text-only research
        hazard_statements=[
            "H302 - Harmful if swallowed",
            "H317 - May cause an allergic skin reaction",
            "H319 - Causes serious eye irritation",
            "H336 - May cause drowsiness or dizziness",
            "H413 - May cause long lasting harmful effects to aquatic life",
        ],
    )
    symbols = _pictograms_from_sds_hazards(source)
    assert symbols == {"GHS07"}  # H413 does not give GHS09
    item = MaterialInput(material_name="Levomepromazine Maleate Powder")
    research = _research()
    research.pictograms = []
    research.hazard_statements = source.hazard_statements
    research.coshh_substance_name = "Levomepromazine maleate"
    assessment = build_coshh_assessment(item, research)
    sds = StoredSDS(
        status="STORED_UNCHANGED", original_url="", resolved_pdf_url="",
        local_path="", sha256="", note="",
    )
    fields = build_coshh_template_values(assessment, item, sds)
    assert fields["SDS_PICTOGRAM_GHS07"] is True
    assert fields["SDS_PICTOGRAM_GHS09"] is False


def test_pictogram_precedence_and_other_common_sds_h_codes():
    from agent.coshh_template import _pictograms_from_sds_hazards
    from types import SimpleNamespace

    cases = [
        (["H314", "H318"], {"GHS05"}),
        (["H350", "H411"], {"GHS08", "GHS09"}),
        (["H400", "H412"], {"GHS09"}),
        (["H413"], set()),
        (["H301", "H302"], {"GHS06"}),
    ]
    for statements, expected in cases:
        assert _pictograms_from_sds_hazards(
            SimpleNamespace(pictograms=[], hazard_statements=statements)
        ) == expected


def test_all_80_checkbox_controls_preserve_original_font_sizes_and_styles(tmp_path):
    """A checked PPE glyph MUST stay the 20 pt size from the approved Word form."""
    from agent.coshh_template import _fill_tagged_template

    template = Path(__file__).resolve().parents[1] / "templates" / "ES.SOP.089.F01.V01 - COSHH Assessment.docx"
    output = tmp_path / "checkbox_fidelity.docx"
    input_values = {
        "SDS_PICTOGRAM_GHS07": True,
        "DER_PPE_QC_FUME_HOOD": True,
        "DER_PPE_PRODUCTION_HALF_FACE_RESPIRATOR": True,
        "DER_PPE_RND_NITRILE_GLOVES": False,
        "DER_EXPOSURE_INHALATION_YES": True,
    }
    _fill_tagged_template(template, output, input_values)
    ns = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
        "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    }

    def checkboxes(path):
        with ZipFile(path, "r") as zf:
            root = etree.fromstring(zf.read("word/document.xml"))
        checks = {}
        for sdt in root.xpath(".//w:sdt[w:sdtPr/w14:checkbox]", namespaces=ns):
            tag = sdt.xpath("./w:sdtPr/w:tag/@w:val", namespaces=ns)[0]
            rpr = sdt.xpath("./w:sdtContent//w:r/w:rPr", namespaces=ns)
            checks[tag] = {
                "styles": [etree.tostring(x, method="c14n") for x in rpr],
                "size": sdt.xpath("./w:sdtContent//w:rPr/w:sz/@w:val", namespaces=ns),
                "glyph": sdt.xpath("./w:sdtContent//w:t/text()", namespaces=ns),
                "checked": sdt.xpath("./w:sdtPr/w14:checkbox/w14:checked/@w14:val", namespaces=ns),
            }
        return checks

    before, after = checkboxes(template), checkboxes(output)
    assert len(before) == len(after) == 81
    assert before.keys() == after.keys()
    for tag in before:
        assert before[tag]["styles"] == after[tag]["styles"], tag
        assert before[tag]["size"] == after[tag]["size"], tag
    assert before["DER_PPE_QC_FUME_HOOD"]["size"] == ["40"]
    assert after["DER_PPE_QC_FUME_HOOD"]["glyph"] == ["☒"]
    assert after["DER_PPE_QC_FUME_HOOD"]["checked"] == ["1"]
    assert after["SDS_PICTOGRAM_GHS07"]["glyph"] == ["☒"]
    assert after["SDS_PICTOGRAM_GHS07"]["checked"] == ["1"]
    assert after["DER_PPE_RND_NITRILE_GLOVES"]["glyph"] == ["☐"]


def test_site_wide_ppe_rules_without_model_selected_ppe():
    """Site PPE must apply even when an SDS/model does not explicitly list it."""
    import copy
    from agent.coshh_template import build_coshh_template_values
    research = copy.deepcopy(_research())
    item = MaterialInput(
        material_name="Dihydrocodeine powder",
        coshh_areas=list(COSHHArea),
        people_exposed="Warehouse, Office, Production, QC, R&D",
    )
    assessment = build_coshh_assessment(item,research)
    for activity in assessment.activities:
        activity.ppe = []
        activity.controls = []
    stored = StoredSDS(
        status="STORED_UNCHANGED",original_url="",resolved_pdf_url="",
        local_path="",sha256="",note="",
    )
    v = build_coshh_template_values(assessment,item,stored)
    for area in ("PRODUCTION","RND","QC","SPILLAGE"):
        for gear in ("LABCOAT_GOWNS","GLASSES_GOGGLES","NITRILE_GLOVES"):
            assert v[f"DER_PPE_{area}_{gear}"],f"{area} missing {gear}"
    assert v["DER_PPE_PRODUCTION_OVERSHOES"]
    assert v["DER_PPE_PRODUCTION_SURGICAL_MASK"]
    assert v["DER_PPE_OFFICE_WAREHOUSE_NITRILE_GLOVES"] is False
    assert v["DER_PPE_QC_HALF_FACE_RESPIRATOR"] is False


def test_production_rpe_is_shared_with_rnd_but_qc_uses_fume_hood():
    import copy
    research = copy.deepcopy(_research())
    item = MaterialInput(material_name="Test API",coshh_areas=list(COSHHArea))
    assessment = build_coshh_assessment(item,research)
    for activity in assessment.activities:
        if activity.area == COSHHArea.PRODUCTION:
            activity.ppe.append("Half-face respirator with appropriate filters")
    stored = StoredSDS(status="STORED_UNCHANGED",original_url="",resolved_pdf_url="",local_path="",sha256="",note="")
    v = build_coshh_template_values(assessment,item,stored)
    assert v["DER_PPE_PRODUCTION_HALF_FACE_RESPIRATOR"]
    assert v["DER_PPE_RND_HALF_FACE_RESPIRATOR"]
    assert v["DER_PPE_QC_FUME_HOOD"]
    assert not v["DER_PPE_PRODUCTION_SURGICAL_MASK"]
    assert not v["DER_PPE_RND_SURGICAL_MASK"]
    assert not v["DER_PPE_QC_HALF_FACE_RESPIRATOR"]


def test_coshh_fire_none_checkbox_and_auto_dates():
    from datetime import date
    import copy
    research=copy.deepcopy(_research())
    research.firefighting_media="Use methods appropriate for surroundings."
    item=MaterialInput(material_name="Test API")
    assessment=build_coshh_assessment(item,research)
    stored=StoredSDS(status="STORED_UNCHANGED",original_url="",resolved_pdf_url="",local_path="",sha256="",note="")
    v=build_coshh_template_values(
        assessment,item,stored,reference="ES.COSHH.001",completion_date=date(2026,10,26)
    )
    assert v["DER_FIRE_NA"] is True
    assert not v["DER_FIRE_CO2"] and not v["DER_FIRE_FOAM"]
    assert v["USR_ASSESSMENT_REFERENCE"]=="ES.COSHH.001"
    assert v["USR_ASSESSMENT_VERSION"]=="1"
    assert v["DER_ASSESSMENT_DATE"]=="26OCT26"
    assert v["HUM_NEXT_REVIEW_DATE"]=="26OCT31"
    research.firefighting_media="Use carbon dioxide (CO2) or foam."
    v=build_coshh_template_values(assessment,item,stored)
    assert v["DER_FIRE_CO2"] and v["DER_FIRE_FOAM"]
    assert v["DER_FIRE_NA"] is False


def test_activity_controls_ppe_mentions_mandatory_site_protection():
    from agent.coshh_template import _activity_rows
    research = _research()
    item = MaterialInput(
        material_name="Dihydrocodeine powder",
        coshh_areas=[COSHHArea.GOODS_IN_WAREHOUSE,COSHHArea.QC,
                     COSHHArea.PRODUCTION,COSHHArea.R_AND_D],
    )
    assessment = build_coshh_assessment(item,research)
    for activity in assessment.activities:
        activity.ppe.clear()
    rows = _activity_rows(assessment)
    qc = next(row for row in rows if row[0].startswith("QC / Sampling"))
    prod = next(row for row in rows if row[0].startswith("Production / R&D"))
    for row in (qc,prod):
        assert "labcoat/gown" in row[2]
        assert "goggles" in row[2]
        assert "nitrile gloves" in row[2]
    assert "overshoes" in prod[2]
