"""Idempotent update of the actual approved COSHH Word master.

Fixes the forced Section 9 page break and populates the site Responsible
Person placeholder. All other Word content controls, drawings and media remain
unchanged. The generation engine still overrides the responsible field.
"""
from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}
MASTER = (
    Path(__file__).resolve().parents[1] / "templates"
    / "ES.SOP.089.F01.V01 - COSHH Assessment.docx"
)


def update_master(path: Path = MASTER) -> bool:
    with ZipFile(path) as archive:
        info = archive.infolist()
        parts = {member.filename: archive.read(member.filename) for member in info}
    root = etree.fromstring(parts["word/document.xml"])
    tags = root.xpath(".//w:sdt/w:sdtPr/w:tag/@w:val", namespaces=NS)
    if len(tags) != len(set(tags)) or len(tags) != 134:
        raise ValueError("Controlled COSHH form must have 134 unique fields")
    if not {"DER_FIRE_NA", "USR_MONITORING_RESPONSIBLE_PERSON"}.issubset(tags):
        raise ValueError("Required controlled fields are missing")

    headings = [
        p for p in root.xpath("./w:body/w:p", namespaces=NS)
        if " ".join(" ".join(p.xpath(".//w:t/text()", namespaces=NS)).split())
           == "Review And Approval"
    ]
    if len(headings) != 1:
        raise ValueError("Controlled Section 9 heading is missing or ambiguous")
    ppr = headings[0].find(f"{{{W}}}pPr")
    if ppr is None:
        raise ValueError("Section 9 heading has no paragraph properties")
    forced = ppr.find(f"{{{W}}}pageBreakBefore")
    changed = forced is not None
    if forced is not None:
        ppr.remove(forced)

    fields = root.xpath(
        './/w:sdt[w:sdtPr/w:tag/@w:val="USR_MONITORING_RESPONSIBLE_PERSON"]',
        namespaces=NS,
    )
    if len(fields) != 1:
        raise ValueError("Responsible Person content control is missing")
    content = fields[0].find(f"{{{W}}}sdtContent")
    if content is None:
        raise ValueError("Responsible Person has no content control body")
    existing = "".join(content.xpath(".//w:t/text()", namespaces=NS))
    if existing != "Imran Patel":
        changed = True
        for child in list(content):
            content.remove(child)
        run = etree.SubElement(content, f"{{{W}}}r")
        etree.SubElement(run, f"{{{W}}}t").text = "Imran Patel"

    if not changed:
        print("Controlled master already updated")
        return False
    assert len(root.xpath(".//w:sdt/w:sdtPr/w:tag/@w:val", namespaces=NS)) == 134
    assert not headings[0].xpath("./w:pPr/w:pageBreakBefore", namespaces=NS)
    parts["word/document.xml"] = etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    temporary = path.with_suffix(".docx.new")
    try:
        with ZipFile(temporary, "w", ZIP_DEFLATED) as output:
            for member in info:
                output.writestr(member, parts[member.filename])
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    print("Controlled COSHH master updated: Imran Patel + Section 9 flow")
    return True


if __name__ == "__main__":
    update_master()
