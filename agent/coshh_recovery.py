"""COSHH-only recovery from the SAVED assessment and original SDS.

No cleaning-validation research, evidence capture or source-rescue calls occur
here. A document with no captured, identity-relevant SDS is NOT presented as a
completed COSHH assessment.
"""
from __future__ import annotations

import hashlib
import json
import traceback
from pathlib import Path
from types import SimpleNamespace
from zipfile import BadZipFile

from .config import Settings
from .coshh_document import build_coshh_docx, coshh_review_summary
from .coshh_rules import build_coshh_assessment
from .coshh_template import verify_generated_coshh_document
from .dossier import convert_docx_to_pdf
from .models import MaterialInput, ResearchBundle
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
        name = _slug(research.coshh_substance_name)
        output_docx = output_dir / f"{name} - COSHH Assessment - DRAFT.docx"
        build_coshh_docx(
            assessment, item, stored, output_docx,
            template_path=settings.coshh_template_path,
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
