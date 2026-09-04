from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from .config import Settings
from .curation import curate_hazard_sources, curate_sources, evidence_key
from .docx_template import checkbox, fill_content_controls
from .dossier import append_evidence_dossier, convert_docx_to_pdf
from .evidence import EvidenceCapture, EvidenceCollector
from .models import Conclusion, EvidenceSource, MaterialInput, ResearchBundle
from .research import ResearchAgent
from .rules import calculate_scoring


SECTION1_MAX_CHARS = 55


def _slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return value or "material"


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
        (("british national formulary", "bnf.nice.org.uk", "nice.org.uk"), "BNF/NICE"),
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
        f"Hazard Score (A): {s.hazard_score_a}",
        f"Potency Score (B): {s.potency_score_b if s.potency_score_b is not None else 'REVIEW REQUIRED'}",
        f"Cleanability Score (C): {s.cleanability_score_c}",
        f"Overall Screening Risk (D): {s.overall_screening_risk_d if s.overall_screening_risk_d is not None else 'UNDETERMINED'}",
        f"PDE Requirement: {s.pde_requirement}", "",
    ]
    if not bundle.potency.bnf_nice_checked:
        lines.append("BNF/NICE: suitable source was not successfully checked/captured; review dose evidence manually if required.")
    if s.hard_escalation_reason:
        lines.append(f"Hard escalation: {s.hard_escalation_reason}")
    lines.append("Operator review flags:")
    lines.extend(f"- {flag}" for flag in s.review_flags) if s.review_flags else lines.append("- None generated by the agent.")
    lines.extend(["", "PDE boundary: Phase 1 does not research, infer or calculate a PDE value. Where Section 6 recommends or requires a PDE, Section 7 remains pending for completion from the approved internal toxicologist report."])
    return "\n".join(lines)


def _appendix_label(number: int, index: int) -> str:
    suffix = chr(64 + index) if index <= 26 else str(index)
    return f"{number}{suffix}"


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
    """Return group references plus only newly-created captures for dossier appending."""
    group_captures: list[EvidenceCapture] = []
    new_captures: list[EvidenceCapture] = []
    next_index = 1

    for source in candidates:
        key = evidence_key(source)
        if key in registry:
            existing = registry[key]
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


class AssessmentPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.researcher = ResearchAgent(settings)
        self.evidence = EvidenceCollector(settings)

    def run(self, item: MaterialInput) -> tuple[ResearchBundle, Path]:
        bundle = self.researcher.research(item)
        bundle.scoring = calculate_scoring(bundle.hazard, bundle.potency, bundle.cleanability)

        material_dir = self.settings.output_dir / _slug(item.material_name)
        evidence_dir = material_dir / "evidence"
        material_dir.mkdir(parents=True, exist_ok=True)

        # Research remains broad in assessment.json. The dossier receives only a curated,
        # verified evidence set, with exact repeated evidence cross-referenced rather than re-appended.
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
        selection_log: dict[str, list[dict[str, str]]] = {}

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
            dossier_captures.extend(new_captures)
            refs[group] = _short_reference(group_captures)
            selection_log[group] = [
                {"appendix": capture.appendix_label, "url": capture.source.url, "source": _source_alias(capture.source)}
                for capture in group_captures
            ]

        (material_dir / "assessment.json").write_text(bundle.model_dump_json(indent=2), encoding="utf-8")
        (material_dir / "REVIEW_SUMMARY.txt").write_text(_review_summary(bundle), encoding="utf-8")
        (evidence_dir / "APPENDIX_SELECTION.json").write_text(
            json.dumps(selection_log, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        filled_form = material_dir / f"{_slug(item.material_name)} - F01 V02 - DRAFT.docx"
        fill_content_controls(self.settings.template_path, filled_form, build_template_values(bundle, self.settings, refs))

        dossier = material_dir / f"{_slug(item.material_name)} - Assessment Dossier - DRAFT.docx"
        append_evidence_dossier(filled_form, dossier, dossier_captures)
        if self.settings.generate_pdf:
            convert_docx_to_pdf(dossier, material_dir)
        return bundle, material_dir
