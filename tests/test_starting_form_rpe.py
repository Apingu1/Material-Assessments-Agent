"""Incoming material state drives occupational exposure independently of dosage form.

All examples use mocked/reused SDS data, with no research or OpenAI calls.
"""
import copy
import csv
from pathlib import Path
from zipfile import ZipFile

from fastapi.testclient import TestClient
from lxml import etree

from agent import web
from agent.coshh_rules import build_coshh_assessment
from agent.coshh_template import build_coshh_template_values, validate_coshh_template
from agent.models import COSHHArea, MaterialInput, StartingForm
from agent.queue import MaterialQueue
from agent.sds import StoredSDS
from tests.test_coshh_document import _research


MASTER = Path(__file__).resolve().parents[1] / "templates/ES.SOP.089.F01.V01 - COSHH Assessment.docx"


def _stored():
    return StoredSDS(status="STORED_UNCHANGED", original_url="", resolved_pdf_url="",
                     local_path="", sha256="", note="")


def _research_for_tests(*, harmful):
    r=copy.deepcopy(_research())
    r.hazard_statements=["H302 Harmful if swallowed"] if harmful else []
    r.signal_word="WARNING" if harmful else "NONE"
    r.inhalation_hazard=False
    r.physical_form="solid powder"
    r.material_use_context="Material used in manufacturing"
    return r


def test_incoming_tablets_force_crushing_and_half_face_rpe_regardless_finished_dosage():
    item=MaterialInput(
        material_name="Example therapeutic material",
        starting_form=StartingForm.TABLETS,
        dosage_forms="Oral solution",
        routes="Oral",
        coshh_areas=[COSHHArea.PRODUCTION, COSHHArea.QC, COSHHArea.R_AND_D],
    )
    assessment=build_coshh_assessment(item,_research_for_tests(harmful=False))
    crush=[x for x in assessment.activities if x.activity=="Crush tablets into powder"]
    assert len(crush)==1
    assert crush[0].area==COSHHArea.PRODUCTION
    assert "airborne dust" in crush[0].exposure_scenario
    assert any("Half-face respirator" in p for p in crush[0].ppe)
    assert any("containment" in c.lower() for c in crush[0].controls)
    assert crush[0].review_required
    values=build_coshh_template_values(assessment,item,_stored())
    assert values["DER_PPE_PRODUCTION_HALF_FACE_RESPIRATOR"]
    assert values["DER_PPE_RND_HALF_FACE_RESPIRATOR"]
    assert values["DER_PPE_QC_FUME_HOOD"]
    assert not values["DER_PPE_QC_HALF_FACE_RESPIRATOR"]
    assert not values["DER_PPE_PRODUCTION_SURGICAL_MASK"]
    assert "crushes incoming tablets into powder" in values["USR_PROCESS_INTENDED_USE"]


def test_starting_powder_with_tablet_finished_dosage_is_not_crushed_twice():
    item=MaterialInput(
        material_name="API powder",
        starting_form="POWDER",
        dosage_forms="Tablets",
        coshh_areas=[COSHHArea.PRODUCTION],
    )
    assessment=build_coshh_assessment(item,_research_for_tests(harmful=True))
    assert not any("Crush tablets" in a.activity for a in assessment.activities)
    values=build_coshh_template_values(assessment,item,_stored())
    assert values["DER_PPE_PRODUCTION_HALF_FACE_RESPIRATOR"]
    assert not values["DER_PPE_PRODUCTION_SURGICAL_MASK"]


def test_low_hazard_powder_has_site_surgical_mask_not_automatic_half_face_rpe():
    item=MaterialInput(
        material_name="Inert example powder",
        starting_form="POWDER",
        dosage_forms="Tablets",
        coshh_areas=[COSHHArea.PRODUCTION],
    )
    assessment=build_coshh_assessment(item,_research_for_tests(harmful=False))
    assert not any("Half-face respirator" in p for a in assessment.activities for p in a.ppe)
    values=build_coshh_template_values(assessment,item,_stored())
    assert values["DER_PPE_PRODUCTION_SURGICAL_MASK"]
    assert not values["DER_PPE_PRODUCTION_HALF_FACE_RESPIRATOR"]
    assert not any("Crush tablets" in a.activity for a in assessment.activities)


def test_starting_material_context_reaches_research_independent_of_dosage_form():
    incoming=MaterialInput(material_name="Example material",starting_form="TABLETS",
                           dosage_forms="Oral suspension",routes="Oral")
    context=incoming.process_context_for_research()
    assert "Incoming starting form: tablets" in context
    assert "crushes them to powder" in context
    assert "Oral suspension" not in context
    powder=MaterialInput(material_name="Example powder",starting_form="POWDER",
                         dosage_forms="Tablets")
    assert "tablets" not in powder.process_context_for_research().lower()


def test_starting_form_is_persisted_in_queue_and_csv_without_wiping_old_rows(tmp_path):
    queue=MaterialQueue(tmp_path/"storage"/"queue.db")
    tablet=MaterialInput(material_name="Incoming drug tablets",starting_form="TABLETS",
                         dosage_forms="Oral suspension")
    id1=queue.add(tablet)
    assert queue.get_row(id1)["starting_form"]=="TABLETS"
    claimed=queue.claim_next()
    assert claimed is not None and claimed[1].starting_form==StartingForm.TABLETS
    source=tmp_path/"materials.csv"
    with source.open("w",newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=["material_name","starting_form","dosage_forms"])
        writer.writeheader()
        writer.writerow({"material_name":"Powder API","starting_form":"POWDER","dosage_forms":"Tablets"})
        writer.writerow({"material_name":"Legacy record","starting_form":"","dosage_forms":"Tablets"})
    assert queue.import_csv(source)==2
    rows=queue.list_rows()
    assert rows[0]["starting_form"]=="UNSPECIFIED"
    assert rows[1]["starting_form"]=="POWDER"
    assert rows[2]["starting_form"]=="TABLETS"


def test_controlled_master_retagged_half_face_and_20pt_checkboxes_intact():
    validate_coshh_template(MASTER)
    ns={"w":"http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with ZipFile(MASTER) as archive:
        root=etree.fromstring(archive.read("word/document.xml"))
    tags=root.xpath(".//w:sdt/w:sdtPr/w:tag/@w:val",namespaces=ns)
    assert len(tags)==len(set(tags))==134
    mask_tags=[x for x in tags if x.endswith("_HALF_FACE_RESPIRATOR")]
    assert len(mask_tags)==5
    assert all(not x.endswith("_FULL_FACE_RESPIRATOR") for x in tags)
    full_text=" ".join(root.xpath(".//w:t/text()",namespaces=ns)).lower()
    assert "half-face" in full_text
    assert "full-face respirator" not in full_text
    control=root.xpath(
        './/w:sdt[w:sdtPr/w:tag/@w:val="DER_PPE_PRODUCTION_HALF_FACE_RESPIRATOR"]',
        namespaces=ns,
    )
    assert len(control)==1
    assert control[0].xpath(".//w:sdtContent//w:rPr/w:sz/@w:val",namespaces=ns)==["40"]


def test_tablet_starting_form_adds_required_production_area_without_dosage_confusion():
    item=MaterialInput(
        material_name="Example incoming tablets", starting_form="TABLETS",
        dosage_forms="Oral suspension",
        coshh_areas=[COSHHArea.QC],
    )
    assert COSHHArea.PRODUCTION in item.coshh_areas
    assert COSHHArea.QC in item.coshh_areas
    # A finished tablet product manufactured from incoming powder is different.
    powder=MaterialInput(
        material_name="Raw API Powder", starting_form="POWDER",
        dosage_forms="Tablets", coshh_areas=[COSHHArea.QC],
    )
    assert COSHHArea.PRODUCTION not in powder.coshh_areas


def test_starting_form_ui_and_api(tmp_path,monkeypatch):
    assert 'id="starting-form"' in web.HTML
    assert "Tablets (crushed to powder in Production)" in web.HTML
    assert "starting_form:document.getElementById('starting-form').value" in web.HTML
    queue=MaterialQueue(tmp_path/"agent.db")
    monkeypatch.setattr(web,"_settings",lambda: type("Config",(),{"database_path":queue.db_path})())
    client=TestClient(web.app)
    reply=client.post("/api/materials",json={
        "material_name":"Dihydrocodeine tablets", "starting_form":"TABLETS",
        "dosage_forms":"Oral suspension", "routes":"Oral"
    })
    assert reply.status_code==200,reply.text
    assert queue.get_row(reply.json()["id"])["starting_form"]=="TABLETS"
