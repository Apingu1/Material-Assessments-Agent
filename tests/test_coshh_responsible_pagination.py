"""Regression for the Dihydrocodeine four-page gap and site responsible person.

No OpenAI research or paid service calls are made.
"""
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

from agent.coshh_template import build_coshh_template_values, validate_coshh_template
from agent.coshh_rules import build_coshh_assessment
from agent.models import MaterialInput
from agent.sds import StoredSDS
from tests.test_coshh_document import _research

MASTER = (
    Path(__file__).resolve().parents[1] / "templates"
    / "ES.SOP.089.F01.V01 - COSHH Assessment.docx"
)
N = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def test_master_has_imran_patel_and_section_nine_has_no_forced_break():
    validate_coshh_template(MASTER)
    with ZipFile(MASTER) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    section_nine = [
        paragraph for paragraph in root.xpath("./w:body/w:p", namespaces=N)
        if " ".join(" ".join(paragraph.xpath(".//w:t/text()", namespaces=N)).split())
           == "Review And Approval"
    ]
    assert len(section_nine) == 1
    assert not section_nine[0].xpath("./w:pPr/w:pageBreakBefore", namespaces=N)
    person = root.xpath(
        './/w:sdt[w:sdtPr/w:tag/@w:val="USR_MONITORING_RESPONSIBLE_PERSON"]',
        namespaces=N,
    )
    assert len(person) == 1
    assert "".join(person[0].xpath(".//w:sdtContent//w:t/text()", namespaces=N)) == "Imran Patel"
    tags = root.xpath(".//w:sdt/w:sdtPr/w:tag/@w:val", namespaces=N)
    assert len(tags) == len(set(tags)) == 134
    assert "DER_FIRE_NA" in tags


def test_responsible_person_filled_but_approvals_remain_unassigned():
    material = MaterialInput(material_name="Dihydrocodeine")
    assessment = build_coshh_assessment(material, _research())
    stored = StoredSDS(
        status="STORED_UNCHANGED", original_url="",
        resolved_pdf_url="", local_path="", sha256="", note="",
    )
    values = build_coshh_template_values(assessment, material, stored)
    assert values["USR_MONITORING_RESPONSIBLE_PERSON"] == "Imran Patel"
    for field in (
        "HUM_ASSESSED_NAME_POSITION",
        "HUM_ASSESSED_SIGNATURE",
        "HUM_REVIEWED_NAME_POSITION",
        "HUM_REVIEWED_SIGNATURE",
        "HUM_APPROVED_NAME_POSITION",
        "HUM_APPROVED_SIGNATURE",
    ):
        assert values[field] == ""
