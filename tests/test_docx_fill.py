from pathlib import Path
from zipfile import ZipFile

from lxml import etree

from agent.docx_template import NS, checkbox, fill_content_controls


def test_fill_preserves_template_and_writes_values(tmp_path):
    template = Path("ES.SOP.272.F01.V02 - Material Hazard & Cleanability Screening Assessment.docx")
    output = tmp_path / "filled.docx"
    fill_content_controls(template, output, {"material_name": "Test Material", "hazard_mutagenicity": checkbox(True), "hazard_score_a": 5})
    assert output.exists()
    with ZipFile(output) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    text = "".join(root.xpath(".//w:t/text()", namespaces=NS))
    assert "Test Material" in text
    assert "☒" in text
