from __future__ import annotations

import re

from .models import (
    COSHHActivityAssessment,
    COSHHArea,
    COSHHAssessment,
    COSHHResearch,
    MaterialInput,
    RiskBand,
)


AREA_LABELS: dict[COSHHArea, str] = {
    COSHHArea.GOODS_IN_WAREHOUSE: "Goods In / Warehouse",
    COSHHArea.SAMPLING: "Sampling",
    COSHHArea.QC: "QC",
    COSHHArea.PRODUCTION: "Production",
    COSHHArea.R_AND_D: "R&D",
    COSHHArea.HOUSEKEEPING: "Housekeeping",
    COSHHArea.OFFICE: "Office",
}

# Exposure profile codes deliberately describe the task rather than the substance.
AREA_TASKS: dict[COSHHArea, tuple[tuple[str, str], ...]] = {
    COSHHArea.GOODS_IN_WAREHOUSE: (
        ("Check outer packaging", "CONTAINED"),
        ("Open outer packaging", "CONTAINED"),
        ("Clean spillage", "SPILL"),
    ),
    COSHHArea.SAMPLING: (
        ("Set up", "LOW_CONTACT"),
        ("Open / sample material", "OPEN_HANDLING"),
        ("Check / close container", "LOW_CONTACT"),
        ("Cleaning", "CLEANING"),
    ),
    COSHHArea.QC: (
        ("Set up", "LOW_CONTACT"),
        ("Weigh / prepare sample", "OPEN_HANDLING"),
        ("Checking", "LOW_CONTACT"),
        ("Cleaning", "CLEANING"),
    ),
    COSHHArea.PRODUCTION: (
        ("Set up", "LOW_CONTACT"),
        ("Weighing", "OPEN_HANDLING"),
        ("Compounding", "OPEN_HANDLING"),
        ("Checking", "LOW_CONTACT"),
        ("Cleaning", "CLEANING"),
    ),
    COSHHArea.R_AND_D: (
        ("Set up", "LOW_CONTACT"),
        ("Weighing", "OPEN_HANDLING"),
        ("Compounding", "OPEN_HANDLING"),
        ("Checking", "LOW_CONTACT"),
        ("Cleaning", "CLEANING"),
    ),
    COSHHArea.HOUSEKEEPING: (
        ("Spillage response", "SPILL"),
        ("Handle visibly contaminated laundry", "CLEANING"),
    ),
    COSHHArea.OFFICE: (
        ("Administrative handling / documentation", "CONTAINED"),
    ),
}

_HIGH_HAZARD_CODES = (
    "H300", "H310", "H330", "H334", "H340", "H341", "H350", "H351",
    "H360", "H361", "H370", "H372",
)
_MEDIUM_HAZARD_CODES = (
    "H301", "H302", "H311", "H312", "H314", "H315", "H317", "H318",
    "H319", "H331", "H332", "H335", "H336", "H371", "H373",
)
_CONTROL_TERMS = (
    "lev", "local exhaust", "extraction", "dispensing booth", "weighing booth",
    "fume cupboard", "fume hood", "isolator", "containment", "downflow booth",
    "closed transfer", "closed system",
)


def _codes(research: COSHHResearch) -> str:
    return " ".join(research.hazard_statements).upper()


def _hazard_severity(research: COSHHResearch) -> int:
    text = _codes(research)
    if any(code in text for code in _HIGH_HAZARD_CODES):
        return 3
    if any(code in text for code in _MEDIUM_HAZARD_CODES):
        return 2
    if research.signal_word == "DANGER":
        return 2
    return 1


def _powder_like(item: MaterialInput, research: COSHHResearch) -> bool:
    raw = " ".join(
        [research.physical_form, research.material_use_context, item.product_context]
    ).lower()
    return any(token in raw for token in ("powder", "dust", "crush", "crushed", "milled", "micronised", "micronized"))


def _volatile_like(research: COSHHResearch) -> bool:
    raw = " ".join([research.physical_form, research.odour, *research.hazard_statements]).lower()
    return any(token in raw for token in ("volatile", "vapour", "vapor", "flammable liquid", "highly flammable"))


def _has_engineering_controls(item: MaterialInput) -> bool:
    text = item.existing_controls.lower()
    return any(term in text for term in _CONTROL_TERMS)


def _risk_band(severity: int, exposure: int) -> RiskBand:
    score = severity * exposure
    if score >= 6:
        return RiskBand.HIGH
    if score >= 3:
        return RiskBand.MEDIUM
    return RiskBand.LOW


def _residual_band(initial: RiskBand, *, engineered: bool, contained: bool) -> RiskBand:
    if contained:
        return RiskBand.LOW
    if initial == RiskBand.LOW:
        return RiskBand.LOW
    if initial == RiskBand.MEDIUM:
        return RiskBand.LOW if engineered else RiskBand.MEDIUM
    return RiskBand.MEDIUM if engineered else RiskBand.MEDIUM


def _exposure_score(profile: str, *, powder: bool, volatile: bool) -> int:
    if profile == "CONTAINED":
        return 1
    if profile == "LOW_CONTACT":
        return 1
    if profile == "SPILL":
        return 3
    if profile in {"OPEN_HANDLING", "CLEANING"}:
        return 3 if (powder or volatile) else 2
    return 2


def _scenario(profile: str, *, powder: bool, volatile: bool) -> str:
    if profile == "CONTAINED":
        return "Primary material remains contained"
    if profile == "LOW_CONTACT":
        return "Limited contact / preparation activity"
    if profile == "SPILL":
        return "Foreseeable abnormal release"
    if powder:
        return "Open handling with credible dust/contact exposure"
    if volatile:
        return "Open handling with credible vapour/contact exposure"
    if profile == "CLEANING":
        return "Residual material contact during cleaning"
    return "Open material handling"


def _ppe_and_controls(
    item: MaterialInput,
    research: COSHHResearch,
    *,
    profile: str,
    severity: int,
    powder: bool,
    volatile: bool,
) -> tuple[list[str], list[str], bool]:
    contained = profile == "CONTAINED"
    open_task = profile in {"OPEN_HANDLING", "CLEANING", "SPILL"}
    controls: list[str] = []
    ppe: list[str] = []
    review = False

    if contained:
        controls.append("Keep primary material sealed; inspect packaging for damage before handling")
        ppe.append("Normal area PPE")
        return controls, ppe, False

    controls.extend(research.core_controls[:3])
    if open_task:
        controls.append("Minimise the quantity exposed and keep containers closed when not in use")

    engineered = _has_engineering_controls(item)
    if open_task and (powder or volatile):
        if engineered:
            controls.append(f"Use existing engineering/containment control: {item.existing_controls.strip()}")
        else:
            controls.append("Confirm suitable local engineering/containment controls before approval")
            review = True

    if open_task or research.skin_hazard:
        ppe.append("Nitrile gloves")
    if open_task and (research.eye_hazard or powder or profile == "SPILL"):
        ppe.append("Safety glasses / goggles")

    if powder and open_task:
        if severity >= 3 or "H334" in _codes(research) or "H330" in _codes(research):
            ppe.append("P3 RPE if residual airborne exposure remains")
            review = True
        else:
            ppe.append("P2 RPE if residual dust exposure remains")
    elif volatile and open_task:
        ppe.append("Task-specific vapour RPE only if required by exposure/control assessment")
        review = True

    if profile == "SPILL":
        controls.extend(
            [
                "Restrict access and use suitably trained personnel",
                "Avoid creating dust/aerosol and collect waste into a suitable closed container",
            ]
        )
        review = True

    return _dedupe(controls), _dedupe(ppe), review


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = " ".join((value or "").split()).strip()
        if not value:
            continue
        key = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def build_coshh_assessment(item: MaterialInput, research: COSHHResearch) -> COSHHAssessment:
    """Combine SDS-driven intrinsic hazard data with controlled Eaststone activity logic."""
    severity = _hazard_severity(research)
    powder = _powder_like(item, research)
    volatile = _volatile_like(research)
    engineered = _has_engineering_controls(item)
    activities: list[COSHHActivityAssessment] = []
    flags: list[str] = []

    if research.sds.match_status != "MATCHED":
        flags.append(
            "The COSHH uses a reference SDS rather than a confirmed current Eaststone supplier SDS; verify the supplier SDS before approval."
        )
    if not item.typical_quantity.strip():
        flags.append("Typical quantity/scale handled has not been supplied; confirm during human review.")
    if not item.existing_controls.strip():
        flags.append("Existing engineering/containment controls have not been supplied; confirm before approval.")
    if research.workplace_exposure_limit_found:
        flags.append(
            f"A workplace exposure limit was identified ({research.workplace_exposure_limit}); confirm exposure-control adequacy."
        )
    if research.health_surveillance_recommended:
        flags.append(
            f"Health surveillance requires human review: {research.health_surveillance_rationale}"
        )
    if COSHHArea.OFFICE in item.coshh_areas:
        flags.append("Office was selected; confirm that a genuine occupational exposure scenario exists in the office area.")

    for area in item.coshh_areas:
        for activity, profile in AREA_TASKS[area]:
            exposure = _exposure_score(profile, powder=powder, volatile=volatile)
            initial = _risk_band(severity, exposure)
            contained = profile == "CONTAINED"
            controls, ppe, task_review = _ppe_and_controls(
                item,
                research,
                profile=profile,
                severity=severity,
                powder=powder,
                volatile=volatile,
            )
            residual = _residual_band(initial, engineered=engineered, contained=contained)
            if initial == RiskBand.HIGH and not engineered and not contained:
                task_review = True
            if task_review:
                flags.append(
                    f"{AREA_LABELS[area]} - {activity}: task controls/PPE require confirmation."
                )

            activities.append(
                COSHHActivityAssessment(
                    area=area,
                    activity=activity,
                    exposure_scenario=_scenario(profile, powder=powder, volatile=volatile),
                    controls=controls,
                    ppe=ppe,
                    initial_risk=initial,
                    residual_risk=residual,
                    review_required=task_review,
                    rationale=(
                        f"Intrinsic hazard severity {severity}/3 combined with activity exposure potential "
                        f"{exposure}/3. Frequency {item.frequency or 'not supplied'}; duration "
                        f"{item.duration or 'not supplied'}."
                    ),
                )
            )

    if research.review_note.strip():
        flags.append(research.review_note.strip())

    return COSHHAssessment(
        research=research,
        activities=activities,
        review_flags=_dedupe(flags),
    )
