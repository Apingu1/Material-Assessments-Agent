from __future__ import annotations

import json
import os
import re
import traceback
from datetime import datetime
from uuid import uuid4
from pathlib import Path

from .config import Settings
from .coshh_document import build_coshh_docx, coshh_review_summary
from .coshh_rules import build_coshh_assessment
from .curation import (
    curate_hazard_sources,
    curate_sources,
    evidence_key,
    merge_evidence_sources,
)
from .docx_template import checkbox, fill_content_controls
from .dossier import append_evidence_dossier, convert_docx_to_pdf
from .evidence import _is_bnf_url, EvidenceCapture, EvidenceCollector
from .models import Conclusion, EvidenceSource, MaterialInput, ResearchBundle
from .research import ResearchAgent
from .rules import calculate_scoring
from .sds import SDSStore, known_authoritative_sds_urls, sds_search_names
from .source_waterfall import rescue_source_families


SECTION1_MAX_CHARS = 55
_SOLUBILITY_GROUPS = {"Water Solubility", "70% IPA Solubility", "2% Decon Solubility", "Solubility"}


def _slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return value or "material"


def _new_run_directory(output_dir: Path, material_name: str) -> Path:
    """New folder for every run, even when material names are identical."""
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:10]
    return output_dir / _slug(material_name) / run_id


def _issue_date() -> str:
    return datetime.now().strftime("%d%b%y").upper()


def _compact_55(value: str) -> str:
    value = " ".join((value or "").split())
    if len(value) <= SECTION1_MAX_CHARS:
        return value
    shortened = value[: SECTION1_MAX_CHARS - 1].rstrip(" ,;:-")
    return shortened + "…"


def _source_alias(source: EvidenceSource) -> str:
    raw = f"{source.publisher} {source.title} {source.url}".lower()
    aliases = [
        (("british national formulary", "bnf.nice.org.uk"), "BNF/NICE"),
        (("nice.org.uk",), "NICE"),
        (("electronic medicines compendium", "medicines.org.uk"), "eMC/SmPC"),
        (("medicines and healthcare products", "mhra", "gov.uk"), "MHRA"),
        (("british pharmacopoeia",), "British Pharmacopoeia"),
        (("european pharmacopoeia", "ph. eur", "edqm"), "European Pharmacopoeia"),
        (("european medicines agency", "ema.europa.eu"), "EMA"),
        (("european chemicals agency", "echa.europa.eu"), "ECHA"),
        (("pubchem", "pubchem.ncbi.nlm.nih.gov"), "PubChem"),
        (("pubmed", "pubmed.ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov"), "PubMed"),
        (("drugbank",), "DrugBank"),
        (("food and drug administration", "fda.gov", "dailymed.nlm.nih.gov"), "FDA/DailyMed"),
    ]
    for needles, alias in aliases:
        if any(needle in raw for needle in needles):
            return alias
    name = source.publisher.strip() or source.title.strip()
    return name[:28].rstrip()


def _appendix_list(captures: list[EvidenceCapture]) -> str:
    labels: list[str] = []
    for capture in captures:
        if capture.appendix_label not in labels:
            labels.append(capture.appendix_label)
    return ", ".join(labels)


def _short_reference(captures: list[EvidenceCapture]) -> str:
    if not captures:
        return "No captured source - operator review"
    names: list[str] = []
    for capture in captures:
        alias = _source_alias(capture.source)
        if alias not in names:
            names.append(alias)
        if len(names) == 2:
            break
    extra = " + others" if len({_source_alias(c.source) for c in captures}) > 2 else ""
    return f"{' / '.join(names)}{extra} - See App. {_appendix_list(captures)}"


def _selected_hazard(bundle: ResearchBundle, field_name: str) -> bool:
    return getattr(bundle.hazard, field_name).conclusion == Conclusion.YES


def _checkbox_score(selected_score: int | None, row_score: int) -> str:
    return checkbox(selected_score == row_score)


def build_template_values(bundle: ResearchBundle, settings: Settings, refs: dict[str, str]) -> dict[str, object]:
    scoring = bundle.scoring
    if scoring is None:
        raise ValueError("Bundle has not been scored")

    b = scoring.potency_score_b
    d = scoring.overall_screening_risk_d
    pde = scoring.pde_requirement
    hazard_therapeutic = scoring.hazard_selected == "therapeutic_category_risk"

    return {
        "assessment_issue_date": _issue_date(),
        "material_name": bundle.material_input.material_name,
        "dosage_forms": _compact_55(bundle.material_input.dosage_forms or bundle.identity.dosage_forms),
        "routes_of_administration": _compact_55(bundle.material_input.routes or bundle.identity.routes_of_administration),
        "therapeutic_class": _compact_55(bundle.identity.therapeutic_class),
        "assessment_performed_by": settings.default_assessment_performed_by,
        "hazard_mutagenicity": checkbox(_selected_hazard(bundle, "mutagenicity_genotoxicity")),
        "hazard_carcinogenicity": checkbox(_selected_hazard(bundle, "carcinogenicity")),
        "hazard_reproductive_developmental": checkbox(_selected_hazard(bundle, "reproductive_developmental_toxicity")),
        "hazard_sensitisation": checkbox(_selected_hazard(bundle, "sensitisation_potential")),
        "hazard_therapeutic_category": checkbox(hazard_therapeutic),
        "hazard_references": refs["Hazard"], "hazard_score_a": scoring.hazard_score_a,
        "potency_band_5": _checkbox_score(b, 5), "potency_band_4": _checkbox_score(b, 4),
        "potency_band_3": _checkbox_score(b, 3), "potency_band_2": _checkbox_score(b, 2),
        "potency_band_1": _checkbox_score(b, 1), "potency_references": refs["Potency"],
        "potency_score_b": b if b is not None else "REVIEW",
        "water_solubility_score_1": _checkbox_score(scoring.water_score, 1),
        "water_solubility_score_3": _checkbox_score(scoring.water_score, 3),
        "water_solubility_score_5": _checkbox_score(scoring.water_score, 5),
        "water_solubility_references": refs["Water Solubility"],
        "ipa70_solubility_score_1": _checkbox_score(scoring.ipa70_score, 1),
        "ipa70_solubility_score_3": _checkbox_score(scoring.ipa70_score, 3),
        "ipa70_solubility_score_5": _checkbox_score(scoring.ipa70_score, 5),
        "ipa70_solubility_references": refs["70% IPA Solubility"],
        "decon2_solubility_score_1": _checkbox_score(scoring.decon2_score, 1),
        "decon2_solubility_score_3": _checkbox_score(scoring.decon2_score, 3),
        "decon2_solubility_score_5": _checkbox_score(scoring.decon2_score, 5),
        "decon2_solubility_references": refs["2% Decon Solubility"],
        "physical_cleanability_score_1": _checkbox_score(scoring.physical_score, 1),
        "physical_cleanability_score_3": _checkbox_score(scoring.physical_score, 3),
        "physical_cleanability_score_5": _checkbox_score(scoring.physical_score, 5),
        "physical_cleanability_references": refs["Physical Cleanability"],
        "cleanability_score_c": scoring.cleanability_score_c,
        "overall_hazard_score_a": scoring.hazard_score_a,
        "overall_potency_score_b": b if b is not None else "REVIEW",
        "overall_cleanability_score_c": scoring.cleanability_score_c,
        "overall_screening_calculation_d": (
            f"{scoring.hazard_score_a} x {b} x {scoring.cleanability_score_c} = {d}"
            if d is not None else "PENDING POTENCY REVIEW"
        ),
        "pde_requirement_not_required": checkbox(pde == "NOT_REQUIRED"),
        "pde_requirement_recommended": checkbox(pde == "RECOMMENDED"),
        "pde_requirement_mandatory": checkbox(pde == "MANDATORY"),
        "pde_value": "N/A" if pde == "NOT_REQUIRED" else "PENDING",
        "pde_risk_score_e": "N/A" if pde == "NOT_REQUIRED" else "PENDING",
        "final_toxicity_score_f": "N/A" if pde == "NOT_REQUIRED" else "PENDING",
    }


def _review_summary(bundle: ResearchBundle) -> str:
    s = bundle.scoring
    if s is None:
        return "Scoring not available."
    lines = [
        f"Material: {bundle.material_input.material_name}",
        f"Research chemical identity: {bundle.identity.chemical_identity}",
        f"Research active moiety: {bundle.identity.active_moiety}",
        f"Population basis for dose: {bundle.identity.population_basis}",
        f"Hazard Score (A): {s.hazard_score_a}",
        f"Potency Score (B): {s.potency_score_b if s.potency_score_b is not None else 'REVIEW REQUIRED'}",
        f"Cleanability Score (C): {s.cleanability_score_c}",
        f"Overall Screening Risk (D): {s.overall_screening_risk_d if s.overall_screening_risk_d is not None else 'UNDETERMINED'}",
        f"PDE Requirement: {s.pde_requirement}", "",
    ]
    if not bundle.potency.bnf_nice_checked:
        lines.append("BNF/NICE: suitable source was not successfully checked; the canonical UK evidence waterfall was used for appendix support.")
    if s.hard_escalation_reason:
        lines.append(f"Hard escalation: {s.hard_escalation_reason}")
    lines.append("Operator review flags:")
    lines.extend(f"- {flag}" for flag in s.review_flags) if s.review_flags else lines.append("- None generated by the agent.")
    lines.extend(["", "PDE boundary: Phase 1 does not research, infer or calculate a PDE value. Where Section 6 recommends or requires a PDE, Section 7 remains pending for completion from the approved internal toxicologist report."])
    if bundle.coshh is None:
        lines.extend(["", "COSHH: COSHH output was not generated successfully; see COSHH_ERROR.txt if present."])
    else:
        lines.extend(["", f"COSHH substance: {bundle.coshh.coshh_substance_name}"])
    return "\n".join(lines)


def _appendix_label(number: int, index: int) -> str:
    suffix = chr(64 + index) if index <= 26 else str(index)
    return f"{number}{suffix}"


def _merge_capture_group(existing_group: str, new_group: str) -> str:
    if existing_group == new_group:
        return existing_group
    if existing_group in _SOLUBILITY_GROUPS and new_group in _SOLUBILITY_GROUPS:
        return "Solubility"
    return "Supporting"


def _capture_curated_group(
    collector: EvidenceCollector,
    *,
    group: str,
    appendix_number: int,
    candidates: list[EvidenceSource],
    max_successful: int,
    evidence_dir: Path,
    registry: dict[str, EvidenceCapture],
) -> tuple[list[EvidenceCapture], list[EvidenceCapture]]:
    """Return group references plus only newly-created source-document captures."""
    group_captures: list[EvidenceCapture] = []
    new_captures: list[EvidenceCapture] = []
    next_index = 1

    for source in candidates:
        key = evidence_key(source)
        if key in registry:
            existing = registry[key]
            existing.source = merge_evidence_sources(existing.source, source)
            existing.group = _merge_capture_group(existing.group, group)
            if existing not in group_captures:
                group_captures.append(existing)
            if len(group_captures) >= max_successful:
                break
            continue

        label = _appendix_label(appendix_number, next_index)
        capture = collector.capture_source(source, group, label, evidence_dir)
        if capture.capture_status != "CAPTURED" or not capture.capture_path:
            continue

        registry[key] = capture
        group_captures.append(capture)
        new_captures.append(capture)
        next_index += 1
        if len(group_captures) >= max_successful:
            break

    return group_captures, new_captures


def _group_target_summary(bundle: ResearchBundle, group: str) -> str:
    if group == "Hazard":
        selected = []
        for field in (
            "mutagenicity_genotoxicity",
            "carcinogenicity",
            "reproductive_developmental_toxicity",
            "sensitisation_potential",
        ):
            item = getattr(bundle.hazard, field)
            if item.conclusion == Conclusion.YES:
                selected.append(f"{field}: {item.rationale}")
        return "; ".join(selected) or bundle.hazard.overall_notes
    if group == "Potency":
        return f"{bundle.potency.dose_statement}; {bundle.potency.dose_calculation}; {bundle.potency.review_note}"
    if group == "Water Solubility":
        return f"{bundle.cleanability.water.classification.value}: {bundle.cleanability.water.rationale}"
    if group == "70% IPA Solubility":
        return f"{bundle.cleanability.ipa70.classification.value}: {bundle.cleanability.ipa70.rationale}"
    if group == "2% Decon Solubility":
        return f"{bundle.cleanability.decon2.classification.value}: {bundle.cleanability.decon2.rationale}"
    if group == "Physical Cleanability":
        return f"{bundle.cleanability.physical.classification.value}: {bundle.cleanability.physical.rationale}"
    return ""


def _curate_rescue_sources(
    sources: list[EvidenceSource],
    *,
    group: str,
    material_name: str,
    limit: int,
) -> list[EvidenceSource]:
    return curate_sources(
        sources,
        group=group,
        limit=limit,
        material_name=material_name if group == "2% Decon Solubility" else "",
    )


def _unique_captures(captures: list[EvidenceCapture]) -> list[EvidenceCapture]:
    seen: set[str] = set()
    result: list[EvidenceCapture] = []
    for capture in captures:
        key = evidence_key(capture.source)
        if key in seen:
            continue
        seen.add(key)
        result.append(capture)
    return result


class AssessmentPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.researcher = ResearchAgent(settings)
        self.evidence = EvidenceCollector(settings)
        self.sds_store = SDSStore()

    def run(self, item: MaterialInput) -> tuple[ResearchBundle, Path]:
        bundle = self.researcher.research(item)
        bundle.scoring = calculate_scoring(bundle.hazard, bundle.potency, bundle.cleanability)

        # Never serve files from a previous assessment for the same material.
        material_dir = _new_run_directory(self.settings.output_dir, item.material_name)
        run_id = material_dir.name
        evidence_dir = material_dir / "evidence"
        material_dir.mkdir(parents=True, exist_ok=True)
        evidence_dir.mkdir(parents=True, exist_ok=True)

        # A successful alternative source must not prevent the requested BNF check.
        if not any(_is_bnf_url(source.url) for source in bundle.potency.sources):
            try:
                bnf = self.researcher.rescue_evidence_from_family(
                    item=item, identity=bundle.identity, family="BNF_NICE", group="Potency",
                    target_summary=_group_target_summary(bundle, "Potency"),
                    existing_urls=[source.url for source in bundle.potency.sources],
                )
                if bnf.supports_existing_conclusion:
                    bundle.potency.sources.extend(source for source in bnf.sources if _is_bnf_url(source.url))
                (evidence_dir / "BNF-source-check.json").write_text(
                    bnf.model_dump_json(indent=2), encoding="utf-8")
            except Exception as exc:
                (evidence_dir / "BNF-source-check-DIAGNOSTIC.txt").write_text(str(exc), encoding="utf-8")

        groups: list[tuple[str, int, list[EvidenceSource], int]] = [
            ("Hazard", 1, curate_hazard_sources(bundle.hazard, limit=5), 5),
            ("Potency", 2, curate_sources(bundle.potency.sources, group="Potency", limit=4), 2),
            ("Water Solubility", 3, curate_sources(bundle.cleanability.water.sources, group="Water Solubility", limit=3), 1),
            ("70% IPA Solubility", 4, curate_sources(bundle.cleanability.ipa70.sources, group="70% IPA Solubility", limit=3), 1),
            (
                "2% Decon Solubility",
                5,
                curate_sources(
                    bundle.cleanability.decon2.sources,
                    group="2% Decon Solubility",
                    limit=4,
                    material_name=item.material_name,
                ),
                2,
            ),
            ("Physical Cleanability", 6, curate_sources(bundle.cleanability.physical.sources, group="Physical Cleanability", limit=3), 1),
        ]

        dossier_captures: list[EvidenceCapture] = []
        refs: dict[str, str] = {}
        registry: dict[str, EvidenceCapture] = {}
        selection_log: dict[str, dict[str, object]] = {}

        for group, number, candidates, max_successful in groups:
            group_captures, new_captures = _capture_curated_group(
                self.evidence,
                group=group,
                appendix_number=number,
                candidates=candidates,
                max_successful=max_successful,
                evidence_dir=evidence_dir,
                registry=registry,
            )
            rescue_attempted = False
            rescue_attempts: list[dict[str, object]] = []
            attempted_urls = [source.url for source in candidates]

            if not group_captures:
                rescue_attempted = True
                for family in rescue_source_families(group):
                    rescue = self.researcher.rescue_evidence_from_family(
                        item=item,
                        identity=bundle.identity,
                        family=family,
                        group=group,
                        target_summary=_group_target_summary(bundle, group),
                        existing_urls=attempted_urls,
                    )
                    rescue_attempts.append(
                        {
                            "family": family,
                            "supports_existing_conclusion": rescue.supports_existing_conclusion,
                            "review_note": rescue.review_note,
                            "urls": [source.url for source in rescue.sources],
                        }
                    )
                    attempted_urls.extend(source.url for source in rescue.sources)
                    if not rescue.supports_existing_conclusion or not rescue.sources:
                        continue

                    rescue_candidates = _curate_rescue_sources(
                        rescue.sources,
                        group=group,
                        material_name=item.material_name,
                        limit=max(2, max_successful * 2),
                    )
                    rescued_group, rescued_new = _capture_curated_group(
                        self.evidence,
                        group=group,
                        appendix_number=number,
                        candidates=rescue_candidates,
                        max_successful=max_successful,
                        evidence_dir=evidence_dir,
                        registry=registry,
                    )
                    for capture in rescued_group:
                        if capture not in group_captures:
                            group_captures.append(capture)
                    for capture in rescued_new:
                        if capture not in new_captures:
                            new_captures.append(capture)
                    if group_captures:
                        break

            if not group_captures and bundle.scoring is not None:
                flag = f"{group}: no verified appendix evidence was captured after the canonical source waterfall."
                if flag not in bundle.scoring.review_flags:
                    bundle.scoring.review_flags.append(flag)

            dossier_captures.extend(new_captures)
            refs[group] = _short_reference(group_captures)
            selection_log[group] = {
                "rescue_attempted": rescue_attempted,
                "rescue_attempts": rescue_attempts,
                "sources": [
                    {
                        "appendix": capture.appendix_label,
                        "url": capture.source.url,
                        "source": _source_alias(capture.source),
                        "applicability": [tag.value for tag in capture.source.applicability],
                    }
                    for capture in group_captures
                ],
            }

        dossier_captures = _unique_captures(dossier_captures)
        (evidence_dir / "APPENDIX_SELECTION.json").write_text(
            json.dumps(selection_log, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        filled_form = material_dir / f"{_slug(item.material_name)} - F01 V02 - DRAFT.docx"
        fill_content_controls(self.settings.template_path, filled_form, build_template_values(bundle, self.settings, refs))

        dossier = material_dir / f"{_slug(item.material_name)} - Assessment Dossier - DRAFT.docx"
        append_evidence_dossier(filled_form, dossier, dossier_captures)
        if self.settings.generate_pdf:
            convert_docx_to_pdf(dossier, material_dir)

        # COSHH is deliberately a second output stream. Failure here is recorded for
        # human review but does not discard a completed cleaning-validation assessment.
        coshh_status = {"status": "NOT_GENERATED", "error": ""}
        try:
            # Do not spend any COSHH API credits before trying confirmed,
            # publisher-hosted reference SDS links for the chemical.
            found_reference = self.sds_store.acquire_known_reference(
                item.material_name, bundle.identity.chemical_identity,
                bundle.identity.active_moiety, material_dir,
            )
            if found_reference and found_reference.status == "STORED_UNCHANGED":
                stored_sds = found_reference
                selected_lane = "authoritative_reference"
                bundle.coshh = self.researcher.research_coshh_from_verified_pdf(
                    item, bundle.identity, stored_sds, reference=True,
                )
                self.sds_store.write_metadata(stored_sds, bundle.coshh, material_dir)
            else:
                bundle.coshh = self.researcher.research_coshh(item, bundle.identity)
                stored_sds = self.sds_store.acquire(
                    bundle.coshh, material_dir,
                    previous_attempts=found_reference.attempts if found_reference else None,
                    acceptable_names=sds_search_names(
                        item.material_name, bundle.identity.chemical_identity,
                        bundle.identity.active_moiety,
                    ),
                )
                selected_lane = "primary"
            sds_names = sds_search_names(
                item.material_name, bundle.identity.chemical_identity,
                bundle.identity.active_moiety,
            )
            # Prefer a verified publisher-hosted source over an AI-invented or
            # inaccessible URL. Exact chemical/CAS is still verified, and the
            # SDS content is then re-extracted into a matching research package.
            if stored_sds.status != "STORED_UNCHANGED":
                reference_urls = known_authoritative_sds_urls(sds_names)
                if reference_urls:
                    stored_sds = self.sds_store.acquire(
                        bundle.coshh, material_dir,
                        previous_attempts=stored_sds.attempts,
                        extra_urls=reference_urls,
                        acceptable_names=sds_names,
                    )
                    if stored_sds.status == "STORED_UNCHANGED":
                        bundle.coshh = self.researcher.research_coshh_from_verified_pdf(
                            item, bundle.identity, stored_sds, reference=True
                        )
                        self.sds_store.write_metadata(stored_sds, bundle.coshh, material_dir)
                        selected_lane = "authoritative_reference"
            rescue_errors: list[str] = []
            # A failed or blocked first SDS is not the end of the search.
            # Each fresh web-research pass returns a complete matching COSHH
            # hazard package, so a fallback SDS cannot inherit a different
            # supplier's H-statements and first-aid content.
            # Repeated full web research is expensive and may be fruitless if
            # the Codespace cannot access external supplier SDS endpoints.
            max_searches = max(0, min(3, int(os.getenv("COSHH_MAX_RESCUE_SEARCHES", "1"))))
            for lane in ("manufacturer", "distributor", "alternative")[:max_searches]:
                if stored_sds.status == "STORED_UNCHANGED":
                    break
                try:
                    alternate = self.researcher.research_coshh_alternative(
                        item,
                        bundle.identity,
                        bundle.coshh,
                        [x["url"] for x in stored_sds.attempts],
                        lane,
                    )
                    initial_cas = bundle.coshh.sds.cas_number.strip()
                    proposed_cas = alternate.sds.cas_number.strip()
                    # Allow a verified parent/base-substance reference SDS even
                    # when its CAS differs from the starting-material salt.
                    # It must remain reference-only and must not silently
                    # replace an SDS for a different salt/mixture.
                    alternative_name = alternate.sds.substance_name.strip().lower()
                    same_base_reference = alternative_name in {
                        name.lower() for name in sds_names
                    }
                    if initial_cas and proposed_cas and initial_cas != proposed_cas and not same_base_reference:
                        rescue_errors.append(
                            f"{lane}: alternate SDS CAS {proposed_cas} conflicts with {initial_cas}; rejected"
                        )
                        continue
                    candidate = self.sds_store.acquire(
                        alternate, material_dir, previous_attempts=stored_sds.attempts,
                        acceptable_names=sds_names,
                    )
                    stored_sds = candidate
                    if candidate.status == "STORED_UNCHANGED":
                        bundle.coshh = self.researcher.research_coshh_from_verified_pdf(
                            item, bundle.identity, candidate, reference=True,
                        )
                        self.sds_store.write_metadata(candidate, bundle.coshh, material_dir)
                        selected_lane = lane
                except Exception as exc:
                    rescue_errors.append(f"{lane}: {type(exc).__name__}: {str(exc)[:180]}")
            coshh_assessment = build_coshh_assessment(item, bundle.coshh)
            if stored_sds.status != "STORED_UNCHANGED":
                coshh_assessment.review_flags.append(
                    "No downloadable, identity-matched SDS PDF was located after primary, "
                    "manufacturer, distributor and alternative-source searches. Obtain "
                    "and check the correct supplier SDS before approving this draft."
                )
            if selected_lane != "primary":
                coshh_assessment.review_flags.append(
                    "A replacement reference SDS was obtained from another source; "
                    "confirm substance/CAS, supplier applicability, revision and all hazards "
                    "against the actual material supplier SDS before approval."
                )
            if (
                sds_names and stored_sds.status == "STORED_UNCHANGED"
                and stored_sds.identity_match.startswith("NAME_MATCH:")
                and stored_sds.identity_match.removeprefix("NAME_MATCH:").lower() != sds_names[0]
            ):
                coshh_assessment.review_flags.append(
                    "The SDS was matched using an alternative/base substance name. "
                    "Confirm salt form and hazard applicability for the actual incoming material."
                )
            coshh_assessment.review_flags.extend(
                f"SDS recovery search issue: {error}" for error in rescue_errors
            )

            (material_dir / "coshh_assessment.json").write_text(
                coshh_assessment.model_dump_json(indent=2), encoding="utf-8"
            )
            coshh_docx = material_dir / f"{_slug(bundle.coshh.coshh_substance_name)} - COSHH Assessment - DRAFT.docx"
            build_coshh_docx(
                coshh_assessment,
                item,
                stored_sds,
                coshh_docx,
                template_path=self.settings.coshh_template_path,
            )
            from .coshh_template import verify_generated_coshh_document
            coshh_verification = verify_generated_coshh_document(
                coshh_docx, self.settings.coshh_template_path
            )
            if self.settings.generate_pdf:
                convert_docx_to_pdf(coshh_docx, material_dir)
            (material_dir / "COSHH_REVIEW_SUMMARY.txt").write_text(
                coshh_review_summary(coshh_assessment, stored_sds), encoding="utf-8"
            )
            coshh_status = {
                "status": "REVIEW_REQUIRED" if coshh_assessment.review_flags else "READY_FOR_REVIEW",
                "error": "",
                "sds_status": stored_sds.status,
                "substance": bundle.coshh.coshh_substance_name,
                "template": self.settings.coshh_template_path.name,
                "sds_source_lane": selected_lane,
                "sds_attempt_count": len(stored_sds.attempts),
                "sds_identity_match": stored_sds.identity_match,
                "run_id": run_id,
                "template_verified": True,
                "template_sha256": coshh_verification["template_sha256"],
                "output_docx_sha256": coshh_verification["output_docx_sha256"],
            }
        except Exception as exc:
            message = str(exc)[:2000]
            (material_dir / "COSHH_ERROR.txt").write_text(
                traceback.format_exc(), encoding="utf-8"
            )
            coshh_status = {
                "status": "FAILED",
                "error": message,
                "sds_status": (
                    stored_sds.status if "stored_sds" in locals() else "NOT_AVAILABLE"
                ),
                "template_verified": False,
                "run_id": run_id,
                "stage": "COSHH_RESEARCH_OR_GENERATION",
                "template": self.settings.coshh_template_path.name,
            }

        (material_dir / "COSHH_STATUS.json").write_text(
            json.dumps(coshh_status, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (material_dir / "assessment.json").write_text(bundle.model_dump_json(indent=2), encoding="utf-8")
        (material_dir / "REVIEW_SUMMARY.txt").write_text(_review_summary(bundle), encoding="utf-8")
        return bundle, material_dir
