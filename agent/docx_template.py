from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
CHECKED = "☒"
UNCHECKED = "☐"


REQUIRED_TAGS = {
    "assessment_issue_date", "material_name", "dosage_forms", "routes_of_administration",
    "therapeutic_class", "assessment_performed_by", "hazard_mutagenicity", "hazard_references",
    "hazard_carcinogenicity", "hazard_reproductive_developmental", "hazard_sensitisation",
    "hazard_therapeutic_category", "hazard_score_a", "potency_band_5", "potency_references",
    "potency_band_4", "potency_band_3", "potency_band_2", "potency_band_1", "potency_score_b",
    "water_solubility_score_1", "water_solubility_references", "water_solubility_score_3",
    "water_solubility_score_5", "ipa70_solubility_score_1", "ipa70_solubility_references",
    "ipa70_solubility_score_3", "ipa70_solubility_score_5", "decon2_solubility_score_1",
    "decon2_solubility_references", "decon2_solubility_score_3", "decon2_solubility_score_5",
    "physical_cleanability_score_1", "physical_cleanability_references", "physical_cleanability_score_3",
    "physical_cleanability_score_5", "cleanability_score_c", "overall_hazard_score_a",
    "overall_potency_score_b", "overall_cleanability_score_c", "overall_screening_calculation_d",
    "pde_requirement_not_required", "pde_requirement_recommended", "pde_requirement_mandatory",
    "pde_value", "pde_risk_score_e", "final_toxicity_score_f",
}


def list_content_control_tags(template_path: Path) -> set[str]:
    with ZipFile(template_path, "r") as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    tags = root.xpath(".//w:sdt/w:sdtPr/w:tag/@w:val", namespaces=NS)
    return set(tags)


def validate_template(template_path: Path) -> None:
    tags = list_content_control_tags(template_path)
    missing = sorted(REQUIRED_TAGS - tags)
    if missing:
        raise ValueError(
            "The DOCX template is not the agent-ready form. Missing content-control tags: "
            + ", ".join(missing)
        )


def fill_content_controls(template_path: Path, output_path: Path, values: dict[str, object]) -> None:
    validate_template(template_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with ZipFile(template_path, "r") as source:
        files = {name: source.read(name) for name in source.namelist()}

    root = etree.fromstring(files["word/document.xml"])
    for sdt in root.xpath(".//w:sdt", namespaces=NS):
        tags = sdt.xpath("./w:sdtPr/w:tag/@w:val", namespaces=NS)
        if not tags or tags[0] not in values:
            continue
        tag = tags[0]
        value = "" if values[tag] is None else str(values[tag])
        text_nodes = sdt.xpath(".//w:sdtContent//w:t", namespaces=NS)
        if text_nodes:
            text_nodes[0].text = value
            for node in text_nodes[1:]:
                node.text = ""
        else:
            content = sdt.find(f"{{{W_NS}}}sdtContent")
            if content is None:
                continue
            paragraph = etree.SubElement(content, f"{{{W_NS}}}p")
            run = etree.SubElement(paragraph, f"{{{W_NS}}}r")
            text = etree.SubElement(run, f"{{{W_NS}}}t")
            text.text = value

    files["word/document.xml"] = etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", standalone="yes"
    )
    with ZipFile(output_path, "w", ZIP_DEFLATED) as destination:
        for name, content in files.items():
            destination.writestr(name, content)


def checkbox(selected: bool) -> str:
    return CHECKED if selected else UNCHECKED
