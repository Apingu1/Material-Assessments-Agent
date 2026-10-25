from __future__ import annotations

from pathlib import Path

from .models import COSHHAssessment, MaterialInput
from .sds import StoredSDS


def build_coshh_docx(
    assessment: COSHHAssessment,
    item: MaterialInput,
    stored_sds: StoredSDS,
    output_path: Path,
    template_path: Path | None = None,
) -> None:
    """Populate the controlled ES.SOP.089.F01.V01 layout; never generate a legacy form."""
    if template_path is None:
        raise ValueError(
            "COSHH generation requires the approved ES.SOP.089.F01.V01 Word template. "
            "The old programmatic COSHH form is disabled."
        )
    from .coshh_template import build_coshh_from_template

    build_coshh_from_template(assessment, item, stored_sds, template_path, output_path)


def coshh_review_summary(assessment: COSHHAssessment, stored_sds: StoredSDS) -> str:
    research = assessment.research
    lines = [
        f"COSHH substance: {research.coshh_substance_name}",
        f"Material/use context: {research.material_use_context}",
        f"SDS: {research.sds.manufacturer} - {research.sds.revision_date or 'revision not stated'}",
        f"SDS match: {research.sds.match_status}",
        f"Original SDS storage: {stored_sds.status}",
        f"GHS pictograms: {', '.join(code.value for code in research.pictograms) or 'None identified'}",
        f"Signal word: {research.signal_word}",
        "",
        "Human review flags:",
    ]
    lines.extend(f"- {flag}" for flag in assessment.review_flags) if assessment.review_flags else lines.append("- None generated.")
    lines.extend(
        [
            "",
            "Approval boundary:",
            "This document is a draft. Reviewer/approver names, signatures and dates are intentionally left blank for human completion.",
        ]
    )
    return "\n".join(lines)
