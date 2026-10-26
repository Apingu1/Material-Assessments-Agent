"""Controlled Word master migration: full-face -> half-face RPE.

Edits only the Section 5 respirator checkbox tags, their aliases and the
visible header label. Preserves every checkbox's original 20pt formatted run,
other 134 content controls, approval/signature blocks and page formatting.
"""
from __future__ import annotations

import re
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
N = {"w": W}
MASTER = Path(__file__).resolve().parents[1] / "templates/ES.SOP.089.F01.V01 - COSHH Assessment.docx"
OLD = "_FULL_FACE_RESPIRATOR"
NEW = "_HALF_FACE_RESPIRATOR"


def update_master(path: Path = MASTER) -> bool:
    with ZipFile(path) as original:
        infos = original.infolist()
        members = {part.filename: original.read(part.filename) for part in infos}
    root = etree.fromstring(members["word/document.xml"])
    tags = root.xpath(".//w:sdt/w:sdtPr/w:tag/@w:val", namespaces=N)
    old_tags = [tag for tag in tags if tag.endswith(OLD)]
    new_tags = [tag for tag in tags if tag.endswith(NEW)]
    if not old_tags and len(new_tags) == 5:
        print("Controlled half-face RPE template already installed")
        return False
    if len(old_tags) != 5 or new_tags:
        raise ValueError(f"Unexpected respirator controls: {old_tags}, new={new_tags}")
    for control in root.xpath(".//w:sdt", namespaces=N):
        for elem in control.xpath("./w:sdtPr/w:tag|./w:sdtPr/w:alias", namespaces=N):
            val = elem.get(f"{{{W}}}val", "")
            if OLD in val:
                elem.set(f"{{{W}}}val", val.replace(OLD, NEW))
            if re.search(r"full\s*[-–]?\s*face", val, re.I):
                elem.set(f"{{{W}}}val", re.sub(r"full\s*[-–]?\s*face", "Half-face", val, flags=re.I))
    label_changes = 0
    for paragraph in root.xpath(".//w:p", namespaces=N):
        words = paragraph.xpath(".//w:t", namespaces=N)
        if not words:
            continue
        joined = "".join(t.text or "" for t in words)
        regex = re.compile(r"full\s*[-–]?\s*face", flags=re.I)
        hits = list(regex.finditer(joined))
        if not hits:
            continue
        # Apply replacements right-to-left while preserving all unaffected
        # runs' formatting and layout.
        for match in reversed(hits):
            start, stop = match.span()
            offset = 0
            inserted = False
            for node in words:
                segment = node.text or ""
                first, last = offset, offset + len(segment)
                offset = last
                if stop <= first or start >= last:
                    continue
                left = segment[:max(0, start-first)]
                right = segment[min(len(segment), stop-first):]
                if not inserted and first <= start < last:
                    node.text = left + "Half-face" + right
                    inserted = True
                else:
                    node.text = left + right
            if not inserted:
                raise ValueError(f"Cannot update split Word label: {joined!r}")
            label_changes += 1
    if label_changes < 1:
        raise ValueError("RPE header not found in the Word master; no blind update permitted")
    new_all = root.xpath(".//w:sdt/w:sdtPr/w:tag/@w:val", namespaces=N)
    if len(new_all) != len(set(new_all)) or len(new_all) != 134:
        raise ValueError("Controlled template mapping changed unexpectedly")
    if sum(tag.endswith(NEW) for tag in new_all) != 5 or any(tag.endswith(OLD) for tag in new_all):
        raise ValueError("Five half-face checkbox controls were not mapped")
    members["word/document.xml"] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    temporary = path.with_suffix(".docx.tmp")
    try:
        with ZipFile(temporary, "w", ZIP_DEFLATED) as output:
            for info in infos:
                output.writestr(info, members[info.filename])
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Controlled COSHH Word updated: {len(new_all)} tags; {label_changes} half-face label replacement(s)")
    return True


if __name__ == "__main__":
    update_master()
