"""Apply the uploaded 2026-10-26 COSHH Word template ZIP member delta.

This deterministic one-off update preserves the exact user-supplied original
DOCX layout and graphics. The compressed patch records only changed XML
members relative to the previously approved template, not the entire binary.
Do not re-run against unknown/modified documents.
"""
from __future__ import annotations
import base64
import hashlib
import json
import re
import zlib
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree

DELTA_B64 = "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"
ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "templates/ES.SOP.089.F01.V01 - COSHH Assessment.docx"
EXPECTED_TAGS = 134


def update_template(path: Path = TARGET) -> bool:
    patch = json.loads(zlib.decompress(base64.b64decode(DELTA_B64)))
    with ZipFile(path, "r") as source:
        contents = {name: source.read(name) for name in source.namelist()}
        metadata = source.infolist()
    updated_sha = hashlib.sha256(contents["word/document.xml"]).hexdigest()
    if updated_sha == patch["target_document_sha256"]:
        return False
    actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual_sha != patch["source_sha256"]:
        raise ValueError(
            "COSHH master template changed unexpectedly. Refusing to apply "
            "the historical delta to an unrecognised controlled document."
        )
    for name, edits in patch["parts"].items():
        tokens = re.split(r"(<[^>]*>)", contents[name].decode("utf-8"))
        for i, j, replacement in reversed(edits):
            tokens[i:j] = [replacement]
        contents[name] = "".join(tokens).encode("utf-8")
    if hashlib.sha256(contents["word/document.xml"]).hexdigest() != patch["target_document_sha256"]:
        raise ValueError("Rebuilt controlled COSHH template failed integrity verification")
    n = {"w":"http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    root = etree.fromstring(contents["word/document.xml"])
    tags = root.xpath(".//w:sdt/w:sdtPr/w:tag/@w:val", namespaces=n)
    if len(tags) != EXPECTED_TAGS or "DER_FIRE_NA" not in tags or "USR_MATERIAL_CODE" in tags:
        raise ValueError("Controlled COSHH content-control map is invalid")
    temp = path.with_suffix(".docx.tmp")
    try:
        with ZipFile(temp, "w", ZIP_DEFLATED) as dest:
            for info in metadata:
                dest.writestr(info, contents[info.filename])
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
    print(f"Updated {path}; {len(tags)} mapped Word controls")
    return True


if __name__ == "__main__":
    update_template()
