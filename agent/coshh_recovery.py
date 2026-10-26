"""COSHH-only recovery from the SAVED assessment and original SDS.

No cleaning-validation research, evidence capture or source-rescue calls occur
here. A document with no captured, identity-relevant SDS is NOT presented as a
completed COSHH assessment.
"""
from __future__ import annotations

import hashlib
import json
import traceback
from datetime import datetime, timezone
from uuid import uuid4
from pathlib import Path
from types import SimpleNamespace
from zipfile import BadZipFile

from .config import Settings
from .coshh_document import build_coshh_docx, coshh_review_summary
from .coshh_references import reserve_coshh_reference
from .coshh_rules import build_coshh_assessment
from .coshh_template import verify_generated_coshh_document
from .dossier import convert_docx_to_pdf
from .models import COSHHAssessment, MaterialInput, ResearchBundle
from .research import ResearchAgent
from .sds import SDSStore, StoredSDS, _slug, _valid_sds_pdf, sds_search_names


def load_existing_bundle(output_dir: Path) -> ResearchBundle:
    """Reuse expensive research already completed in this material's prior run."""
    source = output_dir / "assessment.json"
    if not source.is_file():
        raise FileNotFoundError(
            "Saved Cleaning Validation assessment.json is missing. "
            "Cannot recover COSHH without repeating the primary assessment."
        )
    return ResearchBundle.model_validate_json(source.read_text(encoding="utf-8"))


def _stub_for_upload(bundle: ResearchBundle):
    """Minimum SDS locator for upload validation; never used for hazards."""
    item = bundle.material_input
    name = bundle.identity.chemical_identity or item.material_name
    if bundle.coshh is not None:
        return bundle.coshh
    sds = SimpleNamespace(
        substance_name=name, cas_number="", source=SimpleNamespace(url=""),
        url="", manufacturer="", product_name="", product_number="",
        revision_date="", match_status="REFERENCE_SDS",
        match_rationale="Operator provided SDS; extraction pending",
        is_supplier_specific=False,
    )
    return SimpleNamespace(coshh_substance_name=name, sds=sds, sources=[])


def upload_sds_for_existing_run(
    output_dir: Path, pdf_bytes: bytes, original_filename: str,
) -> StoredSDS:
    bundle = load_existing_bundle(output_dir)
    store = SDSStore()
    research = _stub_for_upload(bundle)
    names = sds_search_names(
        bundle.material_input.material_name,
        bundle.identity.chemical_identity,
        bundle.identity.active_moiety,
    )
    stored = store.import_uploaded_pdf(
        pdf_bytes, research, bundle.material_input.material_name, output_dir,
        extra_names=names, filename=original_filename,
    )
    # The uploaded PDF is trusted for its BYTES only; it has not yet been
    # extracted or assessed. Human supplier confirmation remains required.
    (output_dir / "COSHH_STATUS.json").write_text(
        json.dumps({
            "status": "FAILED",
            "error": "SDS uploaded successfully. Use 'Rebuild COSHH only' to extract "
                     "its hazard information and populate the controlled form.",
            "sds_status": stored.status,
            "template_verified": False,
            "stage": "SDS_UPLOAD_AWAITING_EXTRACTION",
        }, indent=2),
        encoding="utf-8",
    )
    return stored


def _existing_sds(output_dir: Path, bundle: ResearchBundle) -> StoredSDS | None:
    metadata_path = output_dir / "sds" / "SDS_METADATA.json"
    if not metadata_path.is_file():
        return None
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    files = sorted((output_dir / "sds").glob("*Safety Data Sheet.pdf"))
    if not files:
        return None
    path = files[-1]
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if metadata.get("sha256") and metadata["sha256"] != digest:
        raise ValueError("Saved SDS SHA-256 has changed; re-upload the original document")
    names = sds_search_names(
        bundle.material_input.material_name,
        bundle.identity.chemical_identity,
        bundle.identity.active_moiety,
    )
    ok, match = _valid_sds_pdf(
        content, names[0] if names else bundle.material_input.material_name,
        "", acceptable_names=names,
    )
    if not ok:
        raise ValueError(f"Saved SDS failed identity/readability validation: {match}")
    return StoredSDS(
        status="STORED_UNCHANGED",
        original_url=metadata.get("original_url") or "USER_UPLOAD",
        resolved_pdf_url=metadata.get("resolved_pdf_url") or "USER_UPLOAD",
        local_path=str(path),
        sha256=digest,
        note=metadata.get("note") or "Original SDS stored unchanged.",
        attempts=metadata.get("attempts") or [],
        identity_match=match,
    )


def _stored_sds_for_form_refresh(output_dir: Path) -> StoredSDS:
    """Check the original archived SDS bytes without starting NEW SDS research.

    A historical assessment may intentionally use a reference SDS named for
    the parent compound rather than the incoming salt/presentation. The
    initial generation already recorded identity suitability for review; a
    formatting-only operation must not reclassify or second-guess that choice.
    """
    from zipfile import BadZipFile
    import fitz

    path = output_dir / "sds" / "SDS_METADATA.json"
    if not path.is_file():
        raise ValueError(
            "The saved SDS provenance record is missing. The COSHH can only be "
            "refreshed without AI when the original downloaded SDS is retained."
        )
    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("Saved SDS metadata is unreadable") from exc
    # Earlier stored SDS metadata may omit the status key. Its immutable
    # SHA-256 record still proves the archived bytes were not changed.
    if metadata.get("status") not in (None, "STORED_UNCHANGED"):
        raise ValueError("The original SDS was explicitly marked unavailable")
    digest = metadata.get("sha256", "")
    if not digest:
        raise ValueError("Original SDS checksum missing: manual provenance check needed")
    candidates = sorted((output_dir / "sds").glob("*Safety Data Sheet.pdf"))
    if len(candidates) != 1:
        raise ValueError("Expected one original SDS PDF in the saved assessment")
    actual = candidates[0]
    payload = actual.read_bytes()
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError("Original SDS checksum does not match its recorded value")
    if not payload.startswith(b"%PDF-"):
        raise ValueError("The saved SDS is not a PDF file")
    try:
        with fitz.open(stream=payload, filetype="pdf") as pdf:
            if pdf.page_count < 1:
                raise ValueError("The saved SDS PDF has no pages")
    except Exception as exc:
        raise ValueError("The archived SDS PDF cannot be opened") from exc
    return StoredSDS(
        status="STORED_UNCHANGED",
        original_url=metadata.get("original_url") or "ARCHIVED_SDS",
        resolved_pdf_url=metadata.get("resolved_pdf_url") or "ARCHIVED_SDS",
        local_path=str(actual), sha256=digest,
        note=metadata.get("note") or "Original SDS preserved unchanged",
        attempts=metadata.get("attempts") or [],
        identity_match=metadata.get("identity_match") or "PREVIOUSLY_REVIEWED_REFERENCE",
    )


def refresh_existing_coshh_document(settings: Settings, output_dir: Path) -> dict:
    """Re-render a completed COSHH from saved data; NEVER invoke an AI client.

    Use the original saved research/assessment and SDS, preserving GxP source
    provenance. Atomically replace Word/PDF outputs only after verifying their
    controlled template formatting. The original research JSON is not changed.
    """
    import shutil

    assessment_file = output_dir / "coshh_assessment.json"
    if not assessment_file.is_file():
        raise FileNotFoundError(
            "A completed saved COSHH research record is required for no-AI form "
            "refresh. Use COSHH-only research recovery if none is available."
        )
    settings.require_runtime()
    bundle = load_existing_bundle(output_dir)
    assessment = COSHHAssessment.model_validate_json(
        assessment_file.read_text(encoding="utf-8")
    )
    # No new hazard classification or substance matching is performed during
    # a purely documentary refresh. SDS with no applicable classified hazards
    # is a valid possible state; we reuse the saved assessment as it stands.
    stored = _stored_sds_for_form_refresh(output_dir)

    existing = sorted(output_dir.glob("*COSHH Assessment - DRAFT.docx"))
    if len(existing) != 1:
        raise ValueError(
            "Expected exactly one existing COSHH draft; will not replace an "
            "ambiguous or missing controlled document."
        )
    old_status_path = output_dir / "COSHH_STATUS.json"
    old_status = json.loads(old_status_path.read_text(encoding="utf-8"))
    if old_status.get("status") not in {"READY_FOR_REVIEW", "REVIEW_REQUIRED"}:
        raise ValueError("COSHH must have completed before a no-AI form refresh")

    assessment_reference, completed_on = reserve_coshh_reference(
        settings.database_path, output_dir
    )
    staging = output_dir / (".coshh-refresh-" + uuid4().hex[:12])
    staging.mkdir()
    try:
        staged_docx = staging / existing[0].name
        build_coshh_docx(
            assessment, bundle.material_input, stored, staged_docx,
            template_path=settings.coshh_template_path,
            reference=assessment_reference, completion_date=completed_on,
        )
        verification = verify_generated_coshh_document(
            staged_docx, settings.coshh_template_path
        )
        staged_pdf = None
        pdf_warning = ""
        if settings.generate_pdf:
            try:
                converted = convert_docx_to_pdf(staged_docx, staging)
                if converted and converted.is_file():
                    staged_pdf = converted
                else:
                    pdf_warning = (
                        "Word refreshed and verified. PDF conversion is unavailable "
                        "on this Codespace; the old PDF is retained in the superseded "
                        "archive, not offered as the current form."
                    )
            except Exception as exc:
                pdf_warning = (
                    f"Word refreshed and verified, but PDF conversion failed: "
                    f"{type(exc).__name__}. The older PDF is not offered as current."
                )

        # Preserve previous drafts for inspection traceability before
        # replacing their Word/PDF files. No changes to SDS/research JSON.
        history = output_dir / ".coshh-superseded" / (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:8]
        )
        history.mkdir(parents=True)
        shutil.copy2(existing[0], history / existing[0].name)
        old_pdf = existing[0].with_suffix(".pdf")
        if old_pdf.is_file():
            shutil.copy2(old_pdf, history / old_pdf.name)

        staged_docx.replace(existing[0])
        if staged_pdf is not None:
            staged_pdf.replace(old_pdf)
        else:
            # Prevent accidentally exporting a stale PDF linked to the
            # previous master when only Word conversion succeeded.
            old_pdf.unlink(missing_ok=True)

        status = {
            **old_status,
            **verification,
            "template": settings.coshh_template_path.name,
            "template_verified": True,
            "stage": "CONTROLLED_FORM_REFRESHED_NO_AI",
            "document_refreshed_at": datetime.now(timezone.utc).isoformat(),
            "document_refresh_ai_calls": 0,
            "coshh_pdf_current": staged_pdf is not None,
            "coshh_pdf_warning": pdf_warning,
            "assessment_reference": assessment_reference,
            "assessment_version": "1",
            "completion_date": completed_on.isoformat(),
        }
        old_status_path.write_text(
            json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return status
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def regenerate_coshh_only(settings: Settings, output_dir: Path) -> dict:
    """One SDS-specific extraction, then deterministic controlled-template fill.

    Returns an explicit failure status instead of corrupting a completed
    Cleaning Validation result. A missing SDS incurs ZERO OpenAI calls.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    stage = "SDS_PREFLIGHT"
    stored: StoredSDS | None = None
    try:
        settings.require_runtime()
        bundle = load_existing_bundle(output_dir)
        item = bundle.material_input
        stored = _existing_sds(output_dir, bundle)
        store = SDSStore()
        if stored is None:
            stored = store.acquire_known_reference(
                item.material_name, bundle.identity.chemical_identity,
                bundle.identity.active_moiety, output_dir,
            )
        if stored is None or stored.status != "STORED_UNCHANGED":
            raise FileNotFoundError(
                "No matching SDS PDF is present or retrievable from the official "
                "reference URL. Upload the original SDS using 'Attach SDS PDF' "
                "and retry COSHH only. No AI credits were used for this attempt."
            )

        stage = "SDS_PDF_EXTRACTION"
        researcher = ResearchAgent(settings)
        research = researcher.research_coshh_from_verified_pdf(
            item, bundle.identity, stored, reference=True,
        )
        # The original SDS is the source of the hazard statements. Do not
        # inherit facts from a failed previous supplier/research result.
        store.write_metadata(stored, research, output_dir)
        stage = "CONTROLLED_DOCX_FILL"
        assessment = build_coshh_assessment(item, research)
        assessment.review_flags.append(
            "Original reference SDS requires review against the actual incoming "
            "material supplier, salt/formulation and current classification."
        )
        assessment_reference, completed_on = reserve_coshh_reference(
            settings.database_path, output_dir
        )
        name = _slug(research.coshh_substance_name)
        output_docx = output_dir / f"{name} - COSHH Assessment - DRAFT.docx"
        build_coshh_docx(
            assessment, item, stored, output_docx,
            template_path=settings.coshh_template_path,
            reference=assessment_reference, completion_date=completed_on,
        )
        verification = verify_generated_coshh_document(
            output_docx, settings.coshh_template_path
        )
        # Remove stale duplicate COSHH documents only AFTER a verified
        # replacement has been saved. Cleaning assessment files untouched.
        for obsolete in output_dir.glob("*COSHH Assessment - DRAFT.docx"):
            if obsolete != output_docx:
                obsolete.unlink()
        for obsolete in output_dir.glob("*COSHH Assessment - DRAFT.pdf"):
            obsolete.unlink()
        if settings.generate_pdf:
            convert_docx_to_pdf(output_docx, output_dir)

        (output_dir / "coshh_assessment.json").write_text(
            assessment.model_dump_json(indent=2), encoding="utf-8",
        )
        (output_dir / "COSHH_REVIEW_SUMMARY.txt").write_text(
            coshh_review_summary(assessment, stored), encoding="utf-8",
        )
        bundle.coshh = research
        (output_dir / "assessment.json").write_text(
            bundle.model_dump_json(indent=2), encoding="utf-8",
        )
        result = {
            "status": "REVIEW_REQUIRED",
            "error": "",
            "sds_status": stored.status,
            "sds_identity_match": stored.identity_match,
            "sds_attempt_count": len(stored.attempts),
            "sds_source_lane": "COSHH_ONLY_STORED_PDF",
            "assessment_reference": assessment_reference,
            "assessment_version": "1",
            "completion_date": completed_on.isoformat(),
            "template": settings.coshh_template_path.name,
            "template_verified": True,
            **verification,
            "stage": "COMPLETE_DRAFT_FOR_HUMAN_REVIEW",
        }
        (output_dir / "COSHH_ERROR.txt").unlink(missing_ok=True)
    except Exception as exc:
        result = {
            "status": "FAILED",
            "error": f"{type(exc).__name__}: {exc}",
            "stage": stage,
            "sds_status": stored.status if stored else "NOT_AVAILABLE",
            "template_verified": False,
            "template": settings.coshh_template_path.name,
        }
        (output_dir / "COSHH_ERROR.txt").write_text(
            traceback.format_exc(), encoding="utf-8",
        )
    (output_dir / "COSHH_STATUS.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    return result
