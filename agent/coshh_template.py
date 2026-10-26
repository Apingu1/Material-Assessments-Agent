from __future__ import annotations

import re
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree

from .models import COSHHArea, COSHHAssessment, GHSCode, MaterialInput, RiskBand
from .sds import StoredSDS


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NS = {"w": W_NS, "w14": W14_NS}

_GHS_CODES = [code.value for code in GHSCode]
_RISK_ORDER = {RiskBand.LOW: 1, RiskBand.MEDIUM: 2, RiskBand.HIGH: 3}
_PPE_SUFFIXES = (
    "LABCOAT_GOWNS",
    "GLASSES_GOGGLES",
    "FACE_GUARD_VISOR",
    "OVERSHOES",
    "NITRILE_GLOVES",
    "SURGICAL_MASK",
    "FULL_FACE_RESPIRATOR",
    "FUME_HOOD",
)
_HUMAN_TEXT_TAGS = (
    "HUM_CONDITIONS_RESTRICTIONS",
    # Auto-generated from the assessment completion date (+5 calendar years).
    "HUM_COMMUNICATION_DATE_RECORD",
    "HUM_ASSESSED_NAME_POSITION",
    "HUM_ASSESSED_SIGNATURE",
    "HUM_ASSESSED_DATE",
    "HUM_REVIEWED_NAME_POSITION",
    "HUM_REVIEWED_SIGNATURE",
    "HUM_REVIEWED_DATE",
    "HUM_APPROVED_NAME_POSITION",
    "HUM_APPROVED_SIGNATURE",
    "HUM_APPROVED_DATE",
)


def _normalise(value: str) -> str:
    return " ".join((value or "").split()).strip()


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = _normalise(value).strip(" ;.")
        if not value:
            continue
        key = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _short_join(values: list[str], *, limit: int = 4, max_chars: int = 260) -> str:
    text = "; ".join(_dedupe(values)[:limit])
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip(" ,;:-") + "…"


def _checkbox_content(sdt, selected: bool) -> None:
    """Toggle a native Word checkbox WITHOUT replacing its formatted content.

    The approved COSHH template deliberately uses 20pt MS Gothic checkboxes
    in the departmental PPE matrix (w:sz=40 in half-points), and 10pt
    checkboxes elsewhere. Rebuilding an unformatted w:r was shrinking
    all PPE marks to the surrounding paragraph's default font size.
    """
    checkbox = sdt.find(f"./{{{W_NS}}}sdtPr/{{{W14_NS}}}checkbox")
    if checkbox is None:
        return
    checked = checkbox.find(f"{{{W14_NS}}}checked")
    if checked is None:
        checked = etree.Element(f"{{{W14_NS}}}checked")
        checkbox.insert(0, checked)
    checked.set(f"{{{W14_NS}}}val", "1" if selected else "0")

    content = sdt.find(f"{{{W_NS}}}sdtContent")
    if content is None:
        raise ValueError("Controlled COSHH checkbox is missing w:sdtContent")

    # Preserve the template's original w:rPr (font, size, colour, styling),
    # paragraph formatting and checked/unchecked glyph definitions.
    text_nodes = content.xpath(".//w:t", namespaces=NS)
    if not text_nodes:
        raise ValueError("Controlled COSHH checkbox has no formatted glyph run")
    text_nodes[0].text = "☒" if selected else "☐"
    for text in text_nodes[1:]:
        text.text = ""


def _text_content(sdt, value: object) -> None:
    content = sdt.find(f"{{{W_NS}}}sdtContent")
    if content is None:
        return
    for child in list(content):
        content.remove(child)
    run = etree.SubElement(content, f"{{{W_NS}}}r")
    for index, line in enumerate(("" if value is None else str(value)).split("\n")):
        if index:
            etree.SubElement(run, f"{{{W_NS}}}br")
        text = etree.SubElement(run, f"{{{W_NS}}}t")
        if line.startswith(" ") or line.endswith(" "):
            text.set(f"{{{XML_NS}}}space", "preserve")
        text.text = line


def _template_bytes(template_path: Path) -> bytes:
    """Load only the controlled binary DOCX; never use an alternative form."""
    if not template_path.is_file():
        raise FileNotFoundError(f"Controlled COSHH Word form not found: {template_path}")
    return template_path.read_bytes()


def _fill_tagged_template(template_path: Path, output_path: Path, values: dict[str, object]) -> None:
    with ZipFile(BytesIO(_template_bytes(template_path)), "r") as source:
        files = {name: source.read(name) for name in source.namelist()}

    root = etree.fromstring(files["word/document.xml"])
    template_tags = set(root.xpath(".//w:sdt/w:sdtPr/w:tag/@w:val", namespaces=NS))
    missing = sorted(set(values) - template_tags)
    if missing:
        raise ValueError(
            "COSHH template does not match ES.SOP.089.F01.V01 mapping. Missing tags: "
            + ", ".join(missing)
        )

    for sdt in root.xpath(".//w:sdt", namespaces=NS):
        tags = sdt.xpath("./w:sdtPr/w:tag/@w:val", namespaces=NS)
        if not tags or tags[0] not in values:
            continue
        value = values[tags[0]]
        if sdt.find(f".//{{{W14_NS}}}checkbox") is not None:
            _checkbox_content(sdt, bool(value))
        else:
            _text_content(sdt, value)

    files["word/document.xml"] = etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", standalone="yes"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output_path, "w", ZIP_DEFLATED) as destination:
        for name, content in files.items():
            destination.writestr(name, content)


def validate_coshh_template(template_path: Path) -> None:
    """Fail fast when the running instance points at the wrong COSHH form."""
    with ZipFile(BytesIO(_template_bytes(template_path)), "r") as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    tags = set(root.xpath(".//w:sdt/w:sdtPr/w:tag/@w:val", namespaces=NS))
    required = {"RES_SUBSTANCE_PRODUCT", "SDS_HAZARD_STATEMENTS",
                "DER_FIRE_NA", "DER_PPE_QC_FUME_HOOD",
                "DER_PPE_PRODUCTION_FULL_FACE_RESPIRATOR", "HUM_APPROVED_SIGNATURE"}
    forbidden = {"USR_MATERIAL_CODE"}
    if len(tags) != 134 or not required.issubset(tags) or tags.intersection(forbidden):
        raise ValueError(
            f"Wrong COSHH template: expected 134 ES.SOP.089.F01.V01 tagged controls, "
            f"found {len(tags)} in {template_path}"
        )


def verify_generated_coshh_document(output_path: Path, template_path: Path) -> dict[str, str]:
    """Verify the output is populated from the actual controlled DOCX resource."""
    validate_coshh_template(template_path)
    template_data = _template_bytes(template_path)
    output_data = output_path.read_bytes()
    with ZipFile(BytesIO(template_data)) as source, ZipFile(BytesIO(output_data)) as output:
        for required in ("word/styles.xml", "word/document.xml", "word/header1.xml"):
            if required not in output.namelist() or required not in source.namelist():
                raise ValueError(f"COSHH output missing controlled package part {required}")
        template_root = etree.fromstring(source.read("word/document.xml"))
        root = etree.fromstring(output.read("word/document.xml"))
        expected = template_root.xpath(".//w:sdt/w:sdtPr/w:tag/@w:val", namespaces=NS)
        actual = root.xpath(".//w:sdt/w:sdtPr/w:tag/@w:val", namespaces=NS)
        missing = sorted(set(expected) - set(actual))
        obsolete = sorted(set(actual) - set(expected))
        if len(actual) != len(expected) or missing or obsolete:
            details = (
                f"Saved COSHH document uses a different master template "
                f"(found {len(actual)} tags, current master {len(expected)}). "
                f"Missing current fields: {', '.join(missing) or 'none'}. "
                f"Old/unexpected fields: {', '.join(obsolete) or 'none'}. "
                "Use 'Update and download COSHH (no AI)' on the existing assessment; "
                "do not start a new paid research run."
            )
            raise ValueError(details)
        if output.read("word/styles.xml") != source.read("word/styles.xml"):
            raise ValueError("Generated COSHH style part differs from the controlled template")
        if output.read("word/header1.xml") != source.read("word/header1.xml"):
            raise ValueError("Generated COSHH header differs from the controlled template")
    from hashlib import sha256
    return {
        "template_sha256": sha256(template_data).hexdigest(),
        "output_docx_sha256": sha256(output_data).hexdigest(),
    }


def _physical_form_flags(value: str) -> dict[str, bool]:
    text = _normalise(value).lower()
    powder = any(token in text for token in ("powder", "dust", "micronised", "micronized"))
    gas = bool(re.search(r"\bgas\b", text))
    liquid = any(token in text for token in ("liquid", "solution", "suspension", "oil"))
    solid = not powder and any(
        token in text for token in ("solid", "tablet", "crystal", "crystalline", "granule")
    )
    return {"SOLID": solid, "POWDER": powder, "LIQUID": liquid, "GAS": gas}


def _people_mentions(item: MaterialInput, pattern: str) -> bool:
    return re.search(pattern, item.people_exposed or "", re.I) is not None


def _open_activity(activity) -> bool:
    text = f"{activity.activity} {activity.exposure_scenario}".lower()
    return "primary material remains contained" not in text and not (
        "administrative" in text or "documentation" in text
    )


def _airborne_activity(activity) -> bool:
    text = f"{activity.activity} {activity.exposure_scenario} {' '.join(activity.controls)}".lower()
    return any(token in text for token in ("dust", "vapour", "vapor", "airborne", "fume hood"))


def _exposure_values(assessment: COSHHAssessment) -> dict[str, object]:
    research = assessment.research
    open_activities = [activity for activity in assessment.activities if _open_activity(activity)]
    inhalation = research.inhalation_hazard or any(_airborne_activity(x) for x in open_activities)
    skin = research.skin_hazard or bool(open_activities)
    eye = research.eye_hazard or any(
        _airborne_activity(x)
        or any(re.search(r"glasses|goggle|eye protection|visor|face shield", ppe, re.I) for ppe in x.ppe)
        for x in open_activities
    )
    ingestion = research.ingestion_hazard

    inhalation_how = ""
    if inhalation:
        if any("vapour" in x.exposure_scenario.lower() or "vapor" in x.exposure_scenario.lower() for x in open_activities):
            inhalation_how = "Open handling may result in airborne vapour exposure."
        elif any("dust" in x.exposure_scenario.lower() for x in open_activities):
            inhalation_how = "Open handling may generate airborne dust."
        else:
            inhalation_how = "Inhalation exposure may occur during relevant open handling or abnormal release."

    return {
        "DER_EXPOSURE_INHALATION_YES": inhalation,
        "DER_EXPOSURE_INHALATION_NO": not inhalation,
        "DER_EXPOSURE_INHALATION_HOW": inhalation_how,
        "DER_EXPOSURE_SKIN_YES": skin,
        "DER_EXPOSURE_SKIN_NO": not skin,
        "DER_EXPOSURE_SKIN_HOW": "Direct contact may occur during open handling, cleaning or spill response." if skin else "",
        "DER_EXPOSURE_EYE_YES": eye,
        "DER_EXPOSURE_EYE_NO": not eye,
        "DER_EXPOSURE_EYE_HOW": "Dust, splash or contaminated hands may result in eye contact during relevant tasks." if eye else "",
        "DER_EXPOSURE_INGESTION_OTHER_YES": ingestion,
        "DER_EXPOSURE_INGESTION_OTHER_NO": not ingestion,
        "DER_EXPOSURE_INGESTION_OTHER_HOW": "Accidental hand-to-mouth transfer; not a normal workplace route." if ingestion else "",
    }


def _ppe_flags(activities, *, qc: bool = False) -> dict[str, bool]:
    raw = " ".join(
        [value for activity in activities for value in (activity.ppe + activity.controls)]
    ).lower()
    flags = {
        "LABCOAT_GOWNS": bool(re.search(r"lab ?coat|gown|coverall|protective clothing|apron", raw)),
        "GLASSES_GOGGLES": bool(re.search(r"glasses|goggle|eye protection", raw)),
        "FACE_GUARD_VISOR": bool(re.search(r"face guard|face shield|visor", raw)),
        "OVERSHOES": bool(re.search(r"overshoe|shoe cover", raw)),
        "NITRILE_GLOVES": bool(re.search(r"nitrile glove", raw)),
        "SURGICAL_MASK": bool(re.search(r"surgical (face )?mask", raw)),
        "FULL_FACE_RESPIRATOR": bool(re.search(r"full[- ]face respirator", raw)),
        "FUME_HOOD": bool(re.search(r"fume hood|fume cupboard", raw)),
    }
    if qc:
        flags["FULL_FACE_RESPIRATOR"] = False
    return flags


def _matrix_values(assessment: COSHHAssessment) -> dict[str, bool]:
    """Apply mandatory Eaststone site PPE independently of model suggestions.

    The grouped Office/Warehouse row represents normally sealed material:
    warehouse operators are expressly exempt from routine gloves, and this
    combined checkbox is not ticked just because the LLM advised gloves.
    PPE for unusual exposed office tasks needs competent-person review.
    """
    activities = assessment.activities
    groups = {
        "PRODUCTION": [x for x in activities if x.area == COSHHArea.PRODUCTION],
        "RND": [x for x in activities if x.area == COSHHArea.R_AND_D],
        "QC": [x for x in activities if x.area in (COSHHArea.QC, COSHHArea.SAMPLING)],
        "OFFICE_WAREHOUSE": [
            x for x in activities if x.area in {COSHHArea.GOODS_IN_WAREHOUSE, COSHHArea.OFFICE}
        ],
        "SPILLAGE": [
            x for x in activities
            if x.area == COSHHArea.HOUSEKEEPING
            or "spill" in f"{x.activity} {x.exposure_scenario}".lower()
        ],
    }
    result = {}
    for prefix, group in groups.items():
        flags = _ppe_flags(group, qc=prefix == "QC")
        if prefix in {"PRODUCTION", "RND", "QC", "SPILLAGE"}:
            flags["LABCOAT_GOWNS"] = True
            flags["GLASSES_GOGGLES"] = True
            flags["NITRILE_GLOVES"] = True
        if prefix == "PRODUCTION":
            flags["OVERSHOES"] = True
            flags["SURGICAL_MASK"] = not flags["FULL_FACE_RESPIRATOR"]
        if prefix == "OFFICE_WAREHOUSE":
            # Sealed goods-in handling does not mandate nitrile gloves/goggles.
            flags["NITRILE_GLOVES"] = False
            flags["GLASSES_GOGGLES"] = False
        if prefix == "QC":
            # QC uses enclosed externally extracted fume hoods, not RPE.
            flags["FULL_FACE_RESPIRATOR"] = False
            flags["SURGICAL_MASK"] = False
        for suffix in _PPE_SUFFIXES:
            result[f"DER_PPE_{prefix}_{suffix}"] = flags[suffix]

    if result["DER_PPE_PRODUCTION_FULL_FACE_RESPIRATOR"]:
        result["DER_PPE_PRODUCTION_SURGICAL_MASK"] = False
        result["DER_PPE_RND_FULL_FACE_RESPIRATOR"] = True
        result["DER_PPE_RND_SURGICAL_MASK"] = False
        result["DER_PPE_QC_FUME_HOOD"] = True

    if result["DER_PPE_RND_FULL_FACE_RESPIRATOR"]:
        result["DER_PPE_RND_SURGICAL_MASK"] = False

    return result

def _worst_risk(activities, field: str) -> RiskBand:
    return max((getattr(activity, field) for activity in activities), key=lambda x: _RISK_ORDER[x])


def _activity_rows(assessment: COSHHAssessment) -> list[tuple[str, str, str, str, str]]:
    grouping = [
        ("Warehouse / Office", {COSHHArea.GOODS_IN_WAREHOUSE, COSHHArea.OFFICE}),
        ("QC / Sampling", {COSHHArea.QC, COSHHArea.SAMPLING}),
        ("Production / R&D", {COSHHArea.PRODUCTION, COSHHArea.R_AND_D}),
        ("Spillage / Housekeeping", {COSHHArea.HOUSEKEEPING}),
    ]
    rows: list[tuple[str, str, str, str, str]] = []
    site_ppe = _matrix_values(assessment)
    ppe_names = {
        "LABCOAT_GOWNS": "labcoat/gown",
        "GLASSES_GOGGLES": "goggles",
        "FACE_GUARD_VISOR": "face visor",
        "OVERSHOES": "overshoes",
        "NITRILE_GLOVES": "nitrile gloves",
        "SURGICAL_MASK": "surgical mask",
        "FULL_FACE_RESPIRATOR": "full-face respirator",
        "FUME_HOOD": "extracted fume hood",
    }
    for label, areas in grouping:
        group = [activity for activity in assessment.activities if activity.area in areas]
        if not group:
            continue
        preferred = [
            activity for activity in group
            if not re.search(r"\b(set up|checking|check / close)\b", activity.activity, re.I)
        ] or group
        names = _dedupe([activity.activity for activity in preferred])
        controls = _dedupe([control for activity in preferred for control in activity.controls])
        area_prefixes = {
            "Warehouse / Office": ("OFFICE_WAREHOUSE",),
            "QC / Sampling": ("QC",),
            "Production / R&D": ("PRODUCTION", "RND"),
            "Spillage / Housekeeping": ("SPILLAGE",),
        }[label]
        required_ppe = [
            name for suffix, name in ppe_names.items()
            if any(site_ppe[f"DER_PPE_{prefix}_{suffix}"] for prefix in area_prefixes)
        ]
        # The Section 6 narrative must agree with the mandatory site PPE grid
        # even when the SDS model has omitted labcoats, goggles or overshoes.
        controls_ppe = (["PPE: " + ", ".join(required_ppe)] if required_ppe else [])
        controls_ppe.extend(controls[:2])
        rows.append(
            (
                label + " - " + _short_join(names, limit=3, max_chars=100),
                _short_join([activity.exposure_scenario for activity in preferred], limit=2, max_chars=145),
                _short_join(controls_ppe, limit=4, max_chars=255),
                _worst_risk(group, "initial_risk").value.title(),
                _worst_risk(group, "residual_risk").value.title(),
            )
        )
    return rows[:3]


# Unambiguous CLP label pictograms that correspond to specific classified
# H-statements. An SDS often embeds its diamond as an image, which PyMuPDF
# text extraction cannot expose to the language model. Do not lose the
# pictogram just because structured PDF research returned pictograms=[].
# The map is intentionally explicit; H412 and H413 alone are not GHS09.
_GHS_FROM_H = {
    "GHS01": {"H200", "H201", "H202", "H203", "H204", "H205", "H240", "H241"},
    "GHS02": {"H220", "H221", "H222", "H223", "H224", "H225", "H226", "H228",
              "H242", "H250", "H251", "H252", "H260", "H261"},
    "GHS03": {"H270", "H271", "H272"},
    "GHS04": {"H280", "H281"},
    "GHS05": {"H290", "H314", "H318"},
    "GHS06": {"H300", "H301", "H310", "H311", "H330", "H331"},
    "GHS07": {"H302", "H312", "H315", "H317", "H319", "H332", "H335", "H336"},
    "GHS08": {"H304", "H334", "H340", "H341", "H350", "H351", "H360", "H361",
              "H362", "H370", "H371", "H372", "H373"},
    "GHS09": {"H400", "H410", "H411"},
}


def _pictograms_from_sds_hazards(research) -> set[str]:
    """Combine explicit SDS pictograms with definitive classified H-codes.

    Do not infer a pictogram from general health effects, product description,
    dose, or precautionary statements; only CLP H-codes reported as hazards.
    If the skull pictogram applies, the exclamation mark is suppressed under
    CLP label precedence rules.
    """
    selected = {code.value for code in research.pictograms}
    observed = set()
    for statement in research.hazard_statements:
        observed.update(re.findall(r"(?<![A-Z0-9])H[234]\d{2}(?!\d)", statement.upper()))
    for pictogram, codes in _GHS_FROM_H.items():
        if observed.intersection(codes):
            selected.add(pictogram)
    if "GHS06" in selected:
        selected.discard("GHS07")
    return selected


def _sds_title(assessment: COSHHAssessment) -> str:
    sds = assessment.research.sds
    parts = _dedupe([sds.product_name, sds.manufacturer])
    return " - ".join(parts) or sds.substance_name


def _sds_location(stored_sds: StoredSDS, assessment: COSHHAssessment) -> str:
    if stored_sds.status == "STORED_UNCHANGED" and stored_sds.local_path:
        return str(Path(stored_sds.local_path).name)
    return assessment.research.sds.url or stored_sds.original_url or ""


def build_coshh_template_values(
    assessment: COSHHAssessment,
    item: MaterialInput,
    stored_sds: StoredSDS,
    *,
    reference: str = "",
    completion_date: date | None = None,
) -> dict[str, object]:
    research = assessment.research
    physical = _physical_form_flags(research.physical_form)
    signal = research.signal_word.upper()
    selected_pictograms = _pictograms_from_sds_hazards(research)
    areas = set(item.coshh_areas)
    completed = completion_date or date.today()
    try:
        next_review = completed.replace(year=completed.year + 5)
    except ValueError:
        # February 29 to February 28 for a non-leap review year.
        next_review = completed.replace(year=completed.year + 5, day=28)
    fire_co2 = bool(re.search(r"carbon dioxide|\bco2\b|co₂", research.firefighting_media, re.I))
    fire_foam = bool(re.search(r"\bfoam\b", research.firefighting_media, re.I))

    values: dict[str, object] = {
        "USR_ASSESSMENT_REFERENCE": reference,
        "USR_ASSESSMENT_VERSION": "1",
        "RES_SUBSTANCE_PRODUCT": research.coshh_substance_name,
        "DER_ASSESSMENT_DATE": completed.strftime("%d%b%y").upper(),
        "HUM_NEXT_REVIEW_DATE": next_review.strftime("%d%b%y").upper(),
        "RES_CAS_NUMBER": research.sds.cas_number or "",
        "USR_PROCESS_INTENDED_USE": item.product_context or research.material_use_context,
        "USR_EXPOSED_WAREHOUSE": COSHHArea.GOODS_IN_WAREHOUSE in areas or _people_mentions(item, r"\bwarehouse\b|goods[ -]?in"),
        "USR_EXPOSED_OFFICE": COSHHArea.OFFICE in areas or _people_mentions(item, r"\boffice\b"),
        "USR_EXPOSED_PRODUCTION": COSHHArea.PRODUCTION in areas or _people_mentions(item, r"\bproduction\b|manufactur"),
        "USR_EXPOSED_QC": COSHHArea.QC in areas or _people_mentions(item, r"\bqc\b|quality control"),
        "USR_EXPOSED_QA": _people_mentions(item, r"\bqa\b|quality assurance"),
        "USR_EXPOSED_RND": COSHHArea.R_AND_D in areas or _people_mentions(item, r"\br\s*&\s*d\b|research and development"),
        "SDS_TITLE_SUPPLIER": _sds_title(assessment),
        "SDS_REVISION_DATE": research.sds.revision_date or "",
        "SDS_LOCATION_REFERENCE": _sds_location(stored_sds, assessment),
        "DER_SUPPLIER_MATCH_YES": research.sds.match_status == "MATCHED",
        "DER_SUPPLIER_MATCH_NO": research.sds.match_status != "MATCHED",
        "SDS_PHYSICAL_SOLID": physical["SOLID"],
        "SDS_PHYSICAL_POWDER": physical["POWDER"],
        "SDS_PHYSICAL_LIQUID": physical["LIQUID"],
        "SDS_PHYSICAL_GAS": physical["GAS"],
        "SDS_SIGNAL_DANGER": signal == "DANGER",
        "SDS_SIGNAL_WARNING": signal == "WARNING",
        "SDS_SIGNAL_NONE": signal == "NONE",
        "SDS_HAZARD_STATEMENTS": "\n".join(research.hazard_statements),
        "SDS_RELEVANT_HEALTH_EFFECTS": "\n".join(research.relevant_health_effects),
        "USR_AVERAGE_EXPOSURE_DURATION": item.duration or "",
        "SDS_FIRST_AID_INHALATION": research.first_aid_inhalation,
        "SDS_FIRST_AID_SKIN": research.first_aid_skin,
        "SDS_FIRST_AID_EYE": research.first_aid_eye,
        "SDS_FIRST_AID_INGESTION": research.first_aid_ingestion,
        "EAS_SPILLAGE_RESPONSE": research.spill_response,
        "EAS_ENVIRONMENTAL_RESPONSE": research.environmental_precautions,
        "DER_FIRE_CO2": fire_co2,
        "DER_FIRE_FOAM": fire_foam,
        "DER_FIRE_NA": not (fire_co2 or fire_foam),
        "USR_MONITORING_RESPONSIBLE_PERSON": "",
        "EAS_STORAGE_SEGREGATION": research.storage_handling,
        "EAS_WASTE_DISPOSAL": research.disposal,
        "HUM_CONTROLS_ADEQUATE_YES": False,
        "HUM_CONTROLS_ADEQUATE_NO": False,
    }

    for code in _GHS_CODES:
        values[f"SDS_PICTOGRAM_{code}"] = code in selected_pictograms

    values.update(_exposure_values(assessment))
    values.update(_matrix_values(assessment))

    rows = _activity_rows(assessment)
    for index in range(1, 4):
        if index <= len(rows):
            area_activity, scenario, controls_ppe, initial, residual = rows[index - 1]
        else:
            area_activity = scenario = controls_ppe = initial = residual = ""
        values[f"USR_ACTIVITY_{index}_AREA_ACTIVITY"] = area_activity
        values[f"DER_ACTIVITY_{index}_EXPOSURE_SCENARIO"] = scenario
        values[f"DER_ACTIVITY_{index}_CONTROLS_PPE"] = controls_ppe
        values[f"DER_ACTIVITY_{index}_INITIAL_RISK"] = initial
        values[f"DER_ACTIVITY_{index}_RESIDUAL_RISK"] = residual

    monitoring_needed = bool(
        research.workplace_exposure_limit_found and values["DER_EXPOSURE_INHALATION_YES"]
    )
    surveillance_needed = bool(research.health_surveillance_recommended)
    reason: list[str] = []
    if research.workplace_exposure_limit_found:
        reason.append(f"GB workplace exposure limit identified: {research.workplace_exposure_limit}")
    else:
        reason.append("No GB workplace exposure limit identified")
    if surveillance_needed and research.health_surveillance_rationale:
        reason.append(research.health_surveillance_rationale)
    elif research.health_surveillance_considered:
        reason.append("No specific health-surveillance requirement identified from the evidence reviewed")

    values.update(
        {
            "DER_EXPOSURE_MONITORING_YES": monitoring_needed,
            "DER_EXPOSURE_MONITORING_NO": not monitoring_needed,
            "DER_HEALTH_SURVEILLANCE_YES": surveillance_needed,
            "DER_HEALTH_SURVEILLANCE_NO": not surveillance_needed,
            "DER_MONITORING_REASON_ARRANGEMENTS": ". ".join(_dedupe(reason)) + ("." if reason else ""),
        }
    )

    for tag in _HUMAN_TEXT_TAGS:
        values[tag] = ""
    return values


def build_coshh_from_template(
    assessment: COSHHAssessment,
    item: MaterialInput,
    stored_sds: StoredSDS,
    template_path: Path,
    output_path: Path,
    *,
    reference: str = "",
    completion_date: date | None = None,
) -> None:
    """Populate ES.SOP.089.F01.V01 without resizing or restructuring the controlled form."""
    _fill_tagged_template(
        template_path,
        output_path,
        build_coshh_template_values(
            assessment, item, stored_sds,
            reference=reference, completion_date=completion_date,
        ),
    )
